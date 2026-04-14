from __future__ import annotations

import json
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from moredakka.config import AppConfig, load_config
from moredakka.context import ContextPacket, build_context_packet, render_context_packet
from moredakka.providers import build_provider
from moredakka.providers.base import ProviderResult
from moredakka.roles import ROLE_SPECS, default_role_sequence, load_prompt, mode_instruction
from moredakka.schemas import (
    ROLE_ANALYSIS_SCHEMA_NAME,
    SYNTHESIS_SCHEMA_NAME,
    minimal_shape_ok,
    role_analysis_schema,
    synthesis_schema,
)
from moredakka.util import ensure_dir, flatten_strings, normalize_phrase, sha256_json


@dataclass
class WorkflowResult:
    packet: ContextPacket
    rounds: list[list[dict[str, Any]]]
    synthesis: dict[str, Any]
    provider_notes: list[str]


def _global_system_prompt() -> str:
    return (
        "You are one role inside moredakka, a bounded multi-model plan-improvement loop for live software work. "
        "Use only the provided context. Prefer operational clarity over ornament. Surface uncertainty explicitly. "
        "Return strictly valid JSON matching the supplied schema. Do not wrap JSON in markdown."
    )


def _role_user_prompt(
    *,
    mode: str,
    objective: str,
    role_name: str,
    context_text: str,
    round_index: int,
    peer_summaries: str = "",
) -> str:
    role_prompt = load_prompt(role_name)
    pieces = [
        f"MODE\n{mode}",
        f"OBJECTIVE\n{objective}",
        f"ROLE\n{role_name}",
        f"MODE BIAS\n{mode_instruction(mode)}",
        f"ROLE MANDATE\n{role_prompt}",
    ]
    if round_index > 1:
        pieces.append(
            "ROUND RULE\n"
            "This is a later round. Preserve only changed conclusions, stronger evidence, sharper sequencing, "
            "or materially better risk analysis. Do not waste output space repeating unchanged generic points."
        )
    if peer_summaries:
        pieces.append(f"PEER OUTPUTS\n{peer_summaries}")
    pieces.append(f"LOCAL CONTEXT\n{context_text}")
    return "\n\n".join(pieces)


def _synthesis_prompt(
    *,
    mode: str,
    objective: str,
    context_text: str,
    round_summaries: str,
) -> str:
    synth_prompt = load_prompt("synthesizer")
    return "\n\n".join(
        [
            f"MODE\n{mode}",
            f"OBJECTIVE\n{objective}",
            f"MODE BIAS\n{mode_instruction(mode)}",
            f"SYNTHESIS MANDATE\n{synth_prompt}",
            f"ROLE OUTPUTS\n{round_summaries}",
            f"LOCAL CONTEXT\n{context_text}",
        ]
    )


def _summarize_role_outputs(outputs: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    for item in outputs:
        role = item.get("role", "unknown")
        chunks.append(
            "\n".join(
                [
                    f"ROLE: {role}",
                    f"TAKE: {item.get('one_sentence_take', '')}",
                    "TOP_PROBLEMS:",
                    *(f"- {problem.get('title', '')}: {problem.get('detail', '')}" for problem in item.get("top_problems", [])[:3]),
                    "RECOMMENDED_STEPS:",
                    *(f"- {step.get('title', '')}: {step.get('why', '')}" for step in item.get("recommended_steps", [])[:4]),
                    "RISKS:",
                    *(f"- {risk.get('name', '')}: {risk.get('mitigation', '')}" for risk in item.get("risks", [])[:3]),
                ]
            )
        )
    return "\n\n".join(chunks)


def _salient_items(outputs: list[dict[str, Any]]) -> set[str]:
    items: set[str] = set()
    for output in outputs:
        for text in flatten_strings(
            [
                output.get("one_sentence_take", ""),
                [problem.get("title", "") for problem in output.get("top_problems", [])],
                [step.get("title", "") for step in output.get("recommended_steps", [])],
                [risk.get("name", "") for risk in output.get("risks", [])],
                [test.get("name", "") for test in output.get("tests", [])],
            ]
        ):
            norm = normalize_phrase(text)
            if norm:
                items.add(norm)
    return items


def estimate_novelty(previous_round: list[dict[str, Any]], current_round: list[dict[str, Any]]) -> float:
    prev = _salient_items(previous_round)
    cur = _salient_items(current_round)
    if not cur:
        return 0.0
    return len(cur - prev) / max(1, len(cur))


def _cache_path(cache_dir: Path, key: str) -> Path:
    return cache_dir / f"{key}.json"


def _cached_generate(
    *,
    provider,
    cache_dir: Path,
    system: str,
    user: str,
    schema_name: str,
    schema: dict[str, Any],
    previous_response_id: str | None,
    use_cache: bool,
) -> ProviderResult:
    signature = {
        "provider": provider.name,
        "model": provider.model,
        "system": system,
        "user": user,
        "schema_name": schema_name,
        "schema": schema,
        "previous_response_id": previous_response_id,
    }
    key = sha256_json(signature)
    path = _cache_path(cache_dir, key)
    if use_cache and path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        return ProviderResult(
            provider=payload["provider"],
            model=payload["model"],
            data=payload["data"],
            raw_text=payload["raw_text"],
            response_id=payload.get("response_id"),
            usage=payload.get("usage"),
        )
    result = provider.generate_json(
        system=system,
        user=user,
        schema_name=schema_name,
        schema=schema,
        previous_response_id=previous_response_id,
    )
    if use_cache:
        ensure_dir(cache_dir)
        path.write_text(
            json.dumps(
                {
                    "provider": result.provider,
                    "model": result.model,
                    "data": result.data,
                    "raw_text": result.raw_text,
                    "response_id": result.response_id,
                    "usage": result.usage,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    return result


def run_workflow(
    *,
    cwd: Path,
    mode: str,
    objective: str | None,
    config_path: str | None = None,
    base_ref: str | None = None,
    rounds: int | None = None,
    char_budget: int | None = None,
    use_cache: bool = True,
) -> WorkflowResult:
    config = load_config(cwd=cwd, explicit_path=config_path)
    base_ref = base_ref or config.defaults.base_ref
    rounds = rounds or config.defaults.max_rounds
    char_budget = char_budget or config.defaults.char_budget

    packet = build_context_packet(
        cwd=cwd,
        mode=mode,
        objective=objective,
        base_ref=base_ref,
        char_budget=char_budget,
    )
    objective_text = packet.inferred_objective
    context_text = render_context_packet(packet, char_budget=char_budget)

    cache_dir_config = Path(config.defaults.cache_dir).expanduser()
    cache_dir = (cache_dir_config if cache_dir_config.is_absolute() else cwd / cache_dir_config).resolve()
    providers = {name: build_provider(provider_cfg) for name, provider_cfg in config.providers.items()}
    role_names = default_role_sequence(mode)
    system = _global_system_prompt()

    all_rounds: list[list[dict[str, Any]]] = []
    provider_notes: list[str] = []
    previous_ids: dict[str, str | None] = {}

    prior_round_for_novelty: list[dict[str, Any]] | None = None
    peer_summary = ""
    for round_index in range(1, rounds + 1):
        round_outputs_by_role: dict[str, dict[str, Any]] = {}
        round_notes_by_role: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=len(role_names)) as executor:
            future_to_role: dict[Future[ProviderResult], str] = {}
            for role_name in role_names:
                role_cfg = config.roles[role_name]
                provider = providers[role_cfg.provider]
                user_prompt = _role_user_prompt(
                    mode=mode,
                    objective=objective_text,
                    role_name=role_name,
                    context_text=context_text,
                    round_index=round_index,
                    peer_summaries=peer_summary,
                )
                prev_id = (
                    previous_ids.get(role_name)
                    if getattr(provider, "supports_previous_response_id", False)
                    else None
                )
                future = executor.submit(
                    _cached_generate,
                    provider=provider,
                    cache_dir=cache_dir,
                    system=system,
                    user=user_prompt,
                    schema_name=ROLE_ANALYSIS_SCHEMA_NAME,
                    schema=role_analysis_schema(),
                    previous_response_id=prev_id,
                    use_cache=use_cache,
                )
                future_to_role[future] = role_name

            for future in as_completed(future_to_role):
                role_name = future_to_role[future]
                result = future.result()
                if not minimal_shape_ok(result.data, synthesis=False):
                    raise RuntimeError(
                        f"Provider {result.provider}/{result.model} returned malformed role output for {role_name}."
                    )
                round_outputs_by_role[role_name] = result.data
                previous_ids[role_name] = result.response_id
                round_notes_by_role[role_name] = f"{role_name}: {result.provider}/{result.model}"

        round_outputs = [round_outputs_by_role[role_name] for role_name in role_names]
        provider_notes.extend(round_notes_by_role[role_name] for role_name in role_names)
        all_rounds.append(round_outputs)
        if prior_round_for_novelty is not None:
            novelty = estimate_novelty(prior_round_for_novelty, round_outputs)
            if novelty < config.defaults.novelty_threshold:
                break
        peer_summary = _summarize_role_outputs(round_outputs)
        prior_round_for_novelty = round_outputs

    synth_provider_name = config.roles["synthesizer"].provider
    synth_provider = providers[synth_provider_name]
    round_summaries = "\n\n".join(
        f"ROUND {i}\n{_summarize_role_outputs(items)}" for i, items in enumerate(all_rounds, start=1)
    )
    synthesis_result = _cached_generate(
        provider=synth_provider,
        cache_dir=cache_dir,
        system=system,
        user=_synthesis_prompt(
            mode=mode,
            objective=objective_text,
            context_text=context_text,
            round_summaries=round_summaries,
        ),
        schema_name=SYNTHESIS_SCHEMA_NAME,
        schema=synthesis_schema(),
        previous_response_id=None,
        use_cache=use_cache,
    )
    if not minimal_shape_ok(synthesis_result.data, synthesis=True):
        raise RuntimeError(
            f"Provider {synthesis_result.provider}/{synthesis_result.model} returned malformed synthesis output."
        )
    provider_notes.append(f"synthesizer: {synthesis_result.provider}/{synthesis_result.model}")
    deduped_notes = list(dict.fromkeys(provider_notes))
    return WorkflowResult(
        packet=packet,
        rounds=all_rounds,
        synthesis=synthesis_result.data,
        provider_notes=deduped_notes,
    )
