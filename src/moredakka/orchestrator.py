from __future__ import annotations

import json
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from moredakka.config import AppConfig, _default_config, load_config
from moredakka.context import ContextPacket, build_context_packet, render_context_packet
from moredakka.providers import build_provider
from moredakka.providers.base import ProviderResult
from moredakka.roles import ROLE_SPECS, default_role_sequence, load_prompt, mode_instruction
from moredakka.runlog import (
    accumulate_usage,
    config_metadata,
    context_rendering_stats,
    estimate_cost_usd,
    isoformat_z,
    make_invocation_id,
    normalize_usage,
    repo_metadata,
    to_jsonable,
    utc_now,
    write_run_artifact,
)
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
    run_artifact: dict[str, Any]
    run_artifact_path: str


@dataclass
class CachedCallResult:
    result: ProviderResult
    cache_key: str
    cache_hit: bool
    duration_ms: int


@dataclass
class CallTrace:
    stage: str
    role_name: str
    round_index: int | None
    provider: str
    model: str
    response_id: str | None
    previous_response_id: str | None
    schema_name: str
    cache_key: str
    cache_hit: bool
    duration_ms: int
    usage: dict[str, Any]
    estimated_cost_usd: float | None
    system_prompt: str
    user_prompt: str
    raw_text: str
    parsed_data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = to_jsonable(self)
        if isinstance(payload, dict):
            return payload
        raise TypeError("CallTrace serialization failed")


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
) -> CachedCallResult:
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
        return CachedCallResult(
            result=ProviderResult(
                provider=payload["provider"],
                model=payload["model"],
                data=payload["data"],
                raw_text=payload["raw_text"],
                response_id=payload.get("response_id"),
                usage=payload.get("usage"),
            ),
            cache_key=key,
            cache_hit=True,
            duration_ms=0,
        )
    started = time.perf_counter()
    result = provider.generate_json(
        system=system,
        user=user,
        schema_name=schema_name,
        schema=schema,
        previous_response_id=previous_response_id,
    )
    duration_ms = int((time.perf_counter() - started) * 1000)
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
    return CachedCallResult(result=result, cache_key=key, cache_hit=False, duration_ms=duration_ms)


def _call_trace(
    *,
    stage: str,
    role_name: str,
    round_index: int | None,
    provider_config,
    cached: CachedCallResult,
    previous_response_id: str | None,
    schema_name: str,
    system_prompt: str,
    user_prompt: str,
) -> CallTrace:
    usage_summary = normalize_usage(cached.result.usage)
    estimated_cost_usd = estimate_cost_usd(usage_summary, provider_config)
    usage_summary["estimated_cost_usd"] = estimated_cost_usd
    return CallTrace(
        stage=stage,
        role_name=role_name,
        round_index=round_index,
        provider=cached.result.provider,
        model=cached.result.model,
        response_id=cached.result.response_id,
        previous_response_id=previous_response_id,
        schema_name=schema_name,
        cache_key=cached.cache_key,
        cache_hit=cached.cache_hit,
        duration_ms=cached.duration_ms,
        usage=usage_summary,
        estimated_cost_usd=estimated_cost_usd,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        raw_text=cached.result.raw_text,
        parsed_data=cached.result.data,
    )


def _budget_exceeded(config: AppConfig, usage_totals: dict[str, Any], elapsed_seconds: float) -> str | None:
    max_total_tokens = config.defaults.max_total_tokens
    if max_total_tokens is not None:
        total_tokens = usage_totals.get("total_tokens")
        if isinstance(total_tokens, int) and total_tokens > max_total_tokens:
            return "max_total_tokens"
    max_cost_usd = config.defaults.max_cost_usd
    if max_cost_usd is not None:
        total_cost = usage_totals.get("estimated_cost_usd")
        if isinstance(total_cost, (int, float)) and float(total_cost) > max_cost_usd:
            return "max_cost_usd"
    max_wall_seconds = config.defaults.max_wall_seconds
    if max_wall_seconds is not None and elapsed_seconds > max_wall_seconds:
        return "max_wall_seconds"
    return None


def _fallback_synthesis(packet: ContextPacket | None, round_outputs: list[list[dict[str, Any]]], *, stop_reason: str) -> dict[str, Any]:
    latest_round = round_outputs[-1] if round_outputs else []
    latest_take = next((item.get("one_sentence_take", "") for item in latest_round if item.get("one_sentence_take")), "")
    latest_problems = []
    latest_tests = []
    latest_risks = []
    for item in latest_round:
        latest_problems.extend(item.get("top_problems", [])[:2])
        latest_tests.extend(item.get("tests", [])[:2])
        latest_risks.extend(item.get("risks", [])[:2])
    objective = packet.inferred_objective if packet else ""
    return {
        "inferred_objective": objective,
        "one_sentence_take": latest_take or f"Stopped after bounded evidence collection due to {stop_reason}.",
        "selected_path": {
            "name": "bounded-stop",
            "summary": f"Stop additional model calls because {stop_reason} was reached; continue from the latest collected evidence.",
            "tradeoffs": ["Synthesis was downgraded to a local fallback to honor configured bounds."],
        },
        "top_problems": latest_problems,
        "next_actions": [],
        "commit_plan": [],
        "tests": latest_tests,
        "edit_targets": [],
        "major_risks": latest_risks,
        "disagreements": [],
        "stop_conditions": [f"Stopped because {stop_reason} was reached."],
        "open_questions": [],
        "confidence": 0.25,
        "confidence_rationale": f"Fallback synthesis because {stop_reason} prevented another model call.",
    }


def _run_artifact_payload(
    *,
    invocation_id: str,
    cwd: Path,
    base_ref: str,
    started_at,
    ended_at,
    config: AppConfig,
    config_info: dict[str, Any],
    packet: ContextPacket | None,
    context_text: str,
    context_stats: dict[str, Any] | None,
    mode: str,
    explicit_objective: str | None,
    rounds_requested: int,
    rounds_completed: int,
    provider_notes: list[str],
    role_traces: list[CallTrace],
    synthesis_trace: CallTrace | None,
    all_rounds: list[list[dict[str, Any]]],
    synthesis: dict[str, Any],
    stop_reason: str,
    run_status: str,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    repo_info = repo_metadata(cwd, base_ref=base_ref)
    usage_totals = accumulate_usage([trace.usage for trace in role_traces + ([synthesis_trace] if synthesis_trace else [])])
    return {
        "invocation": {
            "invocation_id": invocation_id,
            "started_at": isoformat_z(started_at),
            "ended_at": isoformat_z(ended_at),
            "duration_ms": int((ended_at - started_at).total_seconds() * 1000),
            "mode": mode,
            "explicit_objective": explicit_objective,
            "inferred_objective": packet.inferred_objective if packet else "",
            "rounds_requested": rounds_requested,
            "rounds_completed": rounds_completed,
            "run_status": run_status,
            "stop_reason": stop_reason,
            "cache_dir": config.defaults.cache_dir,
            "run_dir": config.defaults.run_dir,
            "max_total_tokens": config.defaults.max_total_tokens,
            "max_cost_usd": config.defaults.max_cost_usd,
            "max_wall_seconds": config.defaults.max_wall_seconds,
        },
        "repo": repo_info,
        "config": config_info,
        "context_packet": packet.to_dict() if packet else None,
        "context_rendering": context_stats,
        "context_text": context_text,
        "provider_roster": provider_notes,
        "usage_totals": usage_totals,
        "role_calls": [trace.to_dict() for trace in role_traces],
        "synthesis_call": synthesis_trace.to_dict() if synthesis_trace else None,
        "rounds": all_rounds,
        "synthesis": synthesis,
        "error": error,
    }


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
    started_at = utc_now()
    invocation_id = make_invocation_id(started_at)
    config = _default_config()
    config_info = config_metadata(config, cwd=cwd, explicit_config_path=None)
    packet: ContextPacket | None = None
    context_text = ""
    context_stats: dict[str, Any] | None = None
    providers: dict[str, Any] = {}
    all_rounds: list[list[dict[str, Any]]] = []
    provider_notes: list[str] = []
    previous_ids: dict[str, str | None] = {}
    role_traces: list[CallTrace] = []
    synthesis_trace: CallTrace | None = None
    stop_reason = "max_rounds"
    run_status = "success"
    artifact_path: str | None = None
    deduped_notes: list[str] = []

    try:
        config = load_config(cwd=cwd, explicit_path=config_path)
        config_info = config_metadata(config, cwd=cwd, explicit_config_path=config_path)
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
        context_stats = context_rendering_stats(packet, context_text, char_budget=char_budget)

        cache_dir_config = Path(config.defaults.cache_dir).expanduser()
        cache_dir = (cache_dir_config if cache_dir_config.is_absolute() else cwd / cache_dir_config).resolve()
        providers = {name: build_provider(provider_cfg) for name, provider_cfg in config.providers.items()}
        role_names = default_role_sequence(mode)
        system = _global_system_prompt()

        prior_round_for_novelty: list[dict[str, Any]] | None = None
        peer_summary = ""
        for round_index in range(1, rounds + 1):
            round_outputs_by_role: dict[str, dict[str, Any]] = {}
            round_notes_by_role: dict[str, str] = {}
            with ThreadPoolExecutor(max_workers=len(role_names)) as executor:
                future_to_role: dict[Future[CachedCallResult], str] = {}
                prompts_by_role: dict[str, str] = {}
                previous_by_role: dict[str, str | None] = {}
                for role_name in role_names:
                    role_cfg = config.roles[role_name]
                    provider_cfg = config.providers[role_cfg.provider]
                    provider = providers[role_cfg.provider]
                    user_prompt = _role_user_prompt(
                        mode=mode,
                        objective=objective_text,
                        role_name=role_name,
                        context_text=context_text,
                        round_index=round_index,
                        peer_summaries=peer_summary,
                    )
                    prompts_by_role[role_name] = user_prompt
                    prev_id = (
                        previous_ids.get(role_name)
                        if getattr(provider, "supports_previous_response_id", False)
                        else None
                    )
                    previous_by_role[role_name] = prev_id
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
                    cached = future.result()
                    role_cfg = config.roles[role_name]
                    provider_cfg = config.providers[role_cfg.provider]
                    trace = _call_trace(
                        stage="role",
                        role_name=role_name,
                        round_index=round_index,
                        provider_config=provider_cfg,
                        cached=cached,
                        previous_response_id=previous_by_role[role_name],
                        schema_name=ROLE_ANALYSIS_SCHEMA_NAME,
                        system_prompt=system,
                        user_prompt=prompts_by_role[role_name],
                    )
                    role_traces.append(trace)
                    if not minimal_shape_ok(cached.result.data, synthesis=False):
                        raise RuntimeError(
                            f"Provider {cached.result.provider}/{cached.result.model} returned malformed role output for {role_name}."
                        )
                    round_outputs_by_role[role_name] = cached.result.data
                    previous_ids[role_name] = cached.result.response_id
                    round_notes_by_role[role_name] = f"{role_name}: {cached.result.provider}/{cached.result.model}"

            round_outputs = [round_outputs_by_role[role_name] for role_name in role_names]
            provider_notes.extend(round_notes_by_role[role_name] for role_name in role_names)
            all_rounds.append(round_outputs)

            usage_totals = accumulate_usage([trace.usage for trace in role_traces])
            budget_stop = _budget_exceeded(
                config,
                usage_totals,
                (utc_now() - started_at).total_seconds(),
            )
            if budget_stop:
                stop_reason = budget_stop
                run_status = "degraded"
                break

            if prior_round_for_novelty is not None:
                novelty = estimate_novelty(prior_round_for_novelty, round_outputs)
                if novelty < config.defaults.novelty_threshold:
                    stop_reason = "low_novelty"
                    break
            peer_summary = _summarize_role_outputs(round_outputs)
            prior_round_for_novelty = round_outputs

        synthesis_data: dict[str, Any]
        if stop_reason in {"max_total_tokens", "max_cost_usd", "max_wall_seconds"}:
            synthesis_data = _fallback_synthesis(packet, all_rounds, stop_reason=stop_reason)
        else:
            synth_provider_name = config.roles["synthesizer"].provider
            synth_provider = providers[synth_provider_name]
            synth_provider_cfg = config.providers[synth_provider_name]
            round_summaries = "\n\n".join(
                f"ROUND {i}\n{_summarize_role_outputs(items)}" for i, items in enumerate(all_rounds, start=1)
            )
            synthesis_prompt = _synthesis_prompt(
                mode=mode,
                objective=objective_text,
                context_text=context_text,
                round_summaries=round_summaries,
            )
            synthesis_cached = _cached_generate(
                provider=synth_provider,
                cache_dir=cache_dir,
                system=system,
                user=synthesis_prompt,
                schema_name=SYNTHESIS_SCHEMA_NAME,
                schema=synthesis_schema(),
                previous_response_id=None,
                use_cache=use_cache,
            )
            synthesis_trace = _call_trace(
                stage="synthesis",
                role_name="synthesizer",
                round_index=None,
                provider_config=synth_provider_cfg,
                cached=synthesis_cached,
                previous_response_id=None,
                schema_name=SYNTHESIS_SCHEMA_NAME,
                system_prompt=system,
                user_prompt=synthesis_prompt,
            )
            if not minimal_shape_ok(synthesis_cached.result.data, synthesis=True):
                raise RuntimeError(
                    f"Provider {synthesis_cached.result.provider}/{synthesis_cached.result.model} returned malformed synthesis output."
                )
            synthesis_data = synthesis_cached.result.data
            provider_notes.append(f"synthesizer: {synthesis_cached.result.provider}/{synthesis_cached.result.model}")

            post_synthesis_budget = _budget_exceeded(
                config,
                accumulate_usage([trace.usage for trace in role_traces + [synthesis_trace]]),
                (utc_now() - started_at).total_seconds(),
            )
            if post_synthesis_budget:
                stop_reason = post_synthesis_budget
                run_status = "degraded"

        deduped_notes = list(dict.fromkeys(provider_notes))
        artifact = _run_artifact_payload(
            invocation_id=invocation_id,
            cwd=cwd,
            base_ref=base_ref,
            started_at=started_at,
            ended_at=utc_now(),
            config=config,
            config_info=config_info,
            packet=packet,
            context_text=context_text,
            context_stats=context_stats,
            mode=mode,
            explicit_objective=objective,
            rounds_requested=rounds,
            rounds_completed=len(all_rounds),
            provider_notes=deduped_notes,
            role_traces=role_traces,
            synthesis_trace=synthesis_trace,
            all_rounds=all_rounds,
            synthesis=synthesis_data,
            stop_reason=stop_reason,
            run_status=run_status,
        )
        artifact_path = str(
            write_run_artifact(
                cwd=cwd,
                run_dir=config.defaults.run_dir,
                invocation_id=invocation_id,
                artifact=artifact,
            )
        )
        return WorkflowResult(
            packet=packet,
            rounds=all_rounds,
            synthesis=synthesis_data,
            provider_notes=deduped_notes,
            run_artifact=artifact,
            run_artifact_path=artifact_path,
        )
    except Exception as exc:
        resolved_base_ref = base_ref or config.defaults.base_ref
        artifact = _run_artifact_payload(
            invocation_id=invocation_id,
            cwd=cwd,
            base_ref=resolved_base_ref,
            started_at=started_at,
            ended_at=utc_now(),
            config=config,
            config_info=config_info,
            packet=packet,
            context_text=context_text,
            context_stats=context_stats,
            mode=mode,
            explicit_objective=objective,
            rounds_requested=rounds or config.defaults.max_rounds,
            rounds_completed=len(all_rounds),
            provider_notes=list(dict.fromkeys(provider_notes)),
            role_traces=role_traces,
            synthesis_trace=synthesis_trace,
            all_rounds=all_rounds,
            synthesis={},
            stop_reason="error",
            run_status="failed",
            error={"type": type(exc).__name__, "message": str(exc)},
        )
        write_run_artifact(
            cwd=cwd,
            run_dir=config.defaults.run_dir,
            invocation_id=invocation_id,
            artifact=artifact,
        )
        raise
