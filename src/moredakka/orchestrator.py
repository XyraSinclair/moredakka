from __future__ import annotations

import json
import os
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from moredakka.config import AppConfig, _default_config, load_config
from moredakka.context import ContextPacket, build_context_packet, render_context_packet
from moredakka.errors import MoreDakkaRuntimeError
from moredakka.problem_surface import ProblemSurface
from moredakka.providers import build_provider
from moredakka.providers.base import ProviderResult
from moredakka.query_language import (
    compile_query_plan,
    render_candidate_operations,
    render_query_plan_summary,
    render_selected_ops,
)
from moredakka.query_plan import QueryPlan
from moredakka.roles import ROLE_SPECS, default_role_sequence, load_prompt, mode_instruction
from moredakka.surface_registry import resolve_surface_adapter
from moredakka.surfaces.repo import problem_surface_from_context_packet
from moredakka.runlog import (
    accumulate_usage,
    config_metadata,
    context_rendering_stats,
    estimate_cost_usd,
    isoformat_z,
    latest_run_artifact_summary,
    make_invocation_id,
    preflight_run_dir,
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
    schema_name_for_profile,
    synthesis_schema,
)
from moredakka.util import ensure_dir, flatten_strings, normalize_phrase, sha256_json, write_text_atomic


@dataclass
class WorkflowResult:
    packet: ContextPacket
    surface: ProblemSurface
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
        "You are one role inside moredakka, a bounded multi-model plan-improvement loop for live problem solving. "
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
    directive: str = "",
    query_plan_summary: str = "",
    selected_ops_text: str = "",
) -> str:
    role_prompt = load_prompt(role_name)
    pieces = [
        f"MODE\n{mode}",
        f"OBJECTIVE\n{objective}",
        f"ROLE\n{role_name}",
        f"MODE BIAS\n{mode_instruction(mode)}",
        f"ROLE MANDATE\n{role_prompt}",
    ]
    if directive:
        pieces.append(f"DIRECTIVE PROSE\n{directive}")
    if selected_ops_text:
        pieces.append(f"SELECTED OPERATIONS\n{selected_ops_text}")
    if query_plan_summary:
        pieces.append(f"COMPILED PLAN\n{query_plan_summary}")
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
    directive: str = "",
    query_plan_summary: str = "",
    selected_ops_text: str = "",
    final_artifact_text: str = "",
) -> str:
    synth_prompt = load_prompt("synthesizer")
    pieces = [
        f"MODE\n{mode}",
        f"OBJECTIVE\n{objective}",
        f"MODE BIAS\n{mode_instruction(mode)}",
        f"SYNTHESIS MANDATE\n{synth_prompt}",
    ]
    if directive:
        pieces.append(f"DIRECTIVE PROSE\n{directive}")
    if selected_ops_text:
        pieces.append(f"SELECTED OPERATIONS\n{selected_ops_text}")
    if query_plan_summary:
        pieces.append(f"COMPILED PLAN\n{query_plan_summary}")
    if final_artifact_text:
        pieces.append(f"FINAL ARTIFACT OBLIGATIONS\n{final_artifact_text}")
    pieces.extend([
        f"ROLE OUTPUTS\n{round_summaries}",
        f"LOCAL CONTEXT\n{context_text}",
    ])
    return "\n\n".join(pieces)


def _action_items(payload: dict[str, Any], *, synthesis: bool = False) -> list[dict[str, Any]]:
    if synthesis:
        return (payload.get("next_actions") or payload.get("recommended_actions") or [])[:]
    return (payload.get("recommended_steps") or payload.get("recommended_actions") or [])[:]


def _validation_items(payload: dict[str, Any], *, synthesis: bool = False) -> list[dict[str, Any]]:
    if synthesis:
        return (payload.get("tests") or payload.get("validation_checks") or [])[:]
    return (payload.get("tests") or payload.get("validation_checks") or [])[:]


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
                    "RECOMMENDED_ACTIONS:",
                    *(f"- {step.get('title', '')}: {step.get('why', '')}" for step in _action_items(item)[:4]),
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
                output.get("observations", []),
                [problem.get("title", "") for problem in output.get("top_problems", [])],
                [step.get("title", "") for step in _action_items(output)],
                [risk.get("name", "") for risk in output.get("risks", [])],
                [test.get("name", "") for test in _validation_items(output)],
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
        try:
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
        except Exception:
            corrupt_path = path.with_suffix(".corrupt")
            try:
                os.replace(path, corrupt_path)
            except OSError:
                pass
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
        write_text_atomic(
            path,
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


def _fallback_synthesis(
    packet: ContextPacket | None,
    round_outputs: list[list[dict[str, Any]]],
    *,
    stop_reason: str,
    schema_profile: str,
) -> dict[str, Any]:
    latest_round = round_outputs[-1] if round_outputs else []
    latest_take = next((item.get("one_sentence_take", "") for item in latest_round if item.get("one_sentence_take")), "")
    latest_problems = []
    latest_validation = []
    latest_risks = []
    for item in latest_round:
        latest_problems.extend(item.get("top_problems", [])[:2])
        latest_validation.extend(_validation_items(item)[:2])
        latest_risks.extend(item.get("risks", [])[:2])
    objective = packet.inferred_objective if packet else ""
    payload = {
        "inferred_objective": objective,
        "one_sentence_take": latest_take or f"Stopped after bounded evidence collection due to {stop_reason}.",
        "selected_path": {
            "name": "bounded-stop",
            "summary": f"Stop additional model calls because {stop_reason} was reached; continue from the latest collected evidence.",
            "tradeoffs": ["Synthesis was downgraded to a local fallback to honor configured bounds."],
        },
        "top_problems": latest_problems,
        "next_actions": [],
        "major_risks": latest_risks,
        "disagreements": [],
        "stop_conditions": [f"Stopped because {stop_reason} was reached."],
        "open_questions": [],
        "operator_summary": None,
        "handoff_paragraph": None,
        "status_ledger": None,
        "intent_card": None,
        "confidence": 0.25,
        "confidence_rationale": f"Fallback synthesis because {stop_reason} prevented another model call.",
    }
    if schema_profile == "software":
        payload["commit_plan"] = []
        payload["tests"] = latest_validation
        payload["edit_targets"] = []
    else:
        payload["validation_checks"] = latest_validation
    return payload


def _artifact_lines(items: list[str]) -> str:
    return "\n".join(items) if items else "(none)"


def _query_compilation_payload(plan: QueryPlan, *, schema_profile: str) -> dict[str, Any]:
    return {
        "directive": plan.directive,
        "selected_ops": plan.selected_ops,
        "candidate_operations": [
            {
                "canonical_op": item.canonical_op,
                "score": round(item.score, 3),
                "evidence": item.evidence,
                "rationale": item.rationale,
                "status": item.status,
            }
            for item in plan.candidate_operations
        ],
        "query_plan": to_jsonable(
            {
                "mode": plan.mode,
                "schema_profile": schema_profile,
                "objective_strategy": plan.objective_strategy,
                "context_policy": plan.context_policy,
                "role_plan": plan.role_plan,
                "synthesis_policy": plan.synthesis_policy,
                "final_artifacts": plan.final_artifacts,
                "stop_policy": plan.stop_policy,
                "context_signals": plan.context_signals,
                "notes": plan.notes,
            }
        ),
    }


def _augment_synthesis_artifacts(
    synthesis: dict[str, Any],
    *,
    plan: QueryPlan,
    rounds: list[list[dict[str, Any]]],
    stop_reason: str,
) -> dict[str, Any]:
    updated = dict(synthesis)
    selected_path = updated.get("selected_path", {}) or {}
    next_actions = updated.get("next_actions", []) or []
    next_titles = [item.get("title", "") for item in next_actions if item.get("title")]

    allowed = set(plan.final_artifacts)
    if "operator_summary" not in allowed:
        updated["operator_summary"] = None
    if "status_ledger" not in allowed:
        updated["status_ledger"] = None
    if "intent_card" not in allowed:
        updated["intent_card"] = None
    if "handoff_paragraph" not in allowed:
        updated["handoff_paragraph"] = None

    if "operator_summary" in plan.final_artifacts and not updated.get("operator_summary"):
        summary_parts = [updated.get("one_sentence_take", "").strip()]
        if selected_path.get("name"):
            summary_parts.append(f"Path: {selected_path.get('name')}.")
        if next_titles:
            summary_parts.append("Next: " + "; ".join(next_titles[:2]) + ".")
        updated["operator_summary"] = " ".join(part for part in summary_parts if part).strip()

    if "status_ledger" in plan.final_artifacts and not updated.get("status_ledger"):
        updated["status_ledger"] = {
            "done": [f"Collected {len(rounds)} bounded role round(s)."] if rounds else [],
            "remaining": next_titles[:3] or ["Review selected path and execute the highest-leverage next step."],
            "blocked": [f"Stopped because {stop_reason}."] if stop_reason in {"max_total_tokens", "max_cost_usd", "max_wall_seconds", "error"} else [],
            "next": next_titles[:2] or [selected_path.get("summary", "Proceed with the selected path.")],
        }

    if "intent_card" in plan.final_artifacts and not updated.get("intent_card"):
        updated["intent_card"] = {
            "goal": updated.get("inferred_objective", ""),
            "selected_path": selected_path.get("name", ""),
            "open_questions": updated.get("open_questions", []) or [],
        }

    if "handoff_paragraph" in plan.final_artifacts and not updated.get("handoff_paragraph"):
        updated["handoff_paragraph"] = (
            f"Continue from the current state. Objective: {updated.get('inferred_objective', '')}. "
            f"Selected path: {selected_path.get('name', '')} — {selected_path.get('summary', '')}. "
            f"Next actions: {'; '.join(next_titles[:3]) if next_titles else 'inspect the latest report and execute the highest-leverage safe next step.'}"
        ).strip()

    return updated


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
    surface: ProblemSurface | None,
    context_text: str,
    context_stats: dict[str, Any] | None,
    mode: str,
    explicit_objective: str | None,
    directive: str | None,
    query_plan: QueryPlan,
    schema_profile: str,
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
            "directive": directive,
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
        "problem_surface": surface.to_dict() if surface else None,
        "context_rendering": context_stats,
        "context_text": context_text,
        "query_compilation": _query_compilation_payload(query_plan, schema_profile=schema_profile),
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
    directive: str | None = None,
    config_path: str | None = None,
    surface_name: str | None = None,
    schema_profile: str | None = None,
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
    surface: ProblemSurface | None = None
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
    query_plan = compile_query_plan(mode=mode, directive=directive, base_role_names=default_role_sequence(mode))

    try:
        config = load_config(cwd=cwd, explicit_path=config_path)
        config_info = config_metadata(config, cwd=cwd, explicit_config_path=config_path)
        resolved_surface_name = surface_name or config.defaults.surface
        base_ref = base_ref or config.defaults.base_ref
        rounds = rounds or config.defaults.max_rounds
        char_budget = char_budget or config.defaults.char_budget
        resolved_schema_profile = schema_profile or config.defaults.schema_profile
        if resolved_schema_profile == "auto":
            resolved_schema_profile = "software" if resolved_surface_name == "repo" else "generic"

        recent_run_summary = latest_run_artifact_summary(cwd=cwd, run_dir=config.defaults.run_dir)
        has_recent_run_artifact = recent_run_summary is not None
        preflight_run_dir(cwd=cwd, run_dir=config.defaults.run_dir)

        if resolved_surface_name == "repo":
            packet = build_context_packet(
                cwd=cwd,
                mode=mode,
                objective=objective,
                base_ref=base_ref,
                char_budget=char_budget,
            )
            surface = problem_surface_from_context_packet(packet)
            context_text = render_context_packet(packet, char_budget=char_budget)
            context_stats = context_rendering_stats(surface, context_text, char_budget=char_budget)
        else:
            surface_adapter = resolve_surface_adapter(resolved_surface_name)
            surface, packet = surface_adapter.build_surface(
                cwd=cwd,
                mode=mode,
                objective=objective,
                base_ref=base_ref,
                char_budget=char_budget,
            )
            context_text = surface_adapter.render_surface(packet, char_budget=char_budget)
            context_stats = context_rendering_stats(surface, context_text, char_budget=char_budget)
        query_plan = compile_query_plan(
            mode=mode,
            directive=directive,
            base_role_names=default_role_sequence(mode),
            packet=packet,
            has_recent_run_artifact=has_recent_run_artifact,
            recent_run_summary=recent_run_summary,
        )
        objective_text = surface.inferred_objective

        cache_dir_config = Path(config.defaults.cache_dir).expanduser()
        cache_dir = (cache_dir_config if cache_dir_config.is_absolute() else cwd / cache_dir_config).resolve()
        providers = {name: build_provider(provider_cfg) for name, provider_cfg in config.providers.items()}
        role_names = [item.role_name for item in query_plan.role_plan if item.role_name in config.roles]
        system = _global_system_prompt()
        selected_ops_text = render_selected_ops(query_plan)
        query_plan_summary = render_query_plan_summary(query_plan)
        final_artifact_text = _artifact_lines(query_plan.final_artifacts)

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
                        directive=directive or "",
                        query_plan_summary=query_plan_summary,
                        selected_ops_text=selected_ops_text,
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
                        schema_name=schema_name_for_profile(ROLE_ANALYSIS_SCHEMA_NAME, resolved_schema_profile),
                        schema=role_analysis_schema(resolved_schema_profile),
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
                        schema_name=schema_name_for_profile(ROLE_ANALYSIS_SCHEMA_NAME, resolved_schema_profile),
                        system_prompt=system,
                        user_prompt=prompts_by_role[role_name],
                    )
                    role_traces.append(trace)
                    if not minimal_shape_ok(cached.result.data, synthesis=False, profile=resolved_schema_profile):
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
            synthesis_data = _fallback_synthesis(packet, all_rounds, stop_reason=stop_reason, schema_profile=resolved_schema_profile)
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
                directive=directive or "",
                query_plan_summary=query_plan_summary,
                selected_ops_text=selected_ops_text,
                final_artifact_text=final_artifact_text,
            )
            synthesis_cached = _cached_generate(
                provider=synth_provider,
                cache_dir=cache_dir,
                system=system,
                user=synthesis_prompt,
                schema_name=schema_name_for_profile(SYNTHESIS_SCHEMA_NAME, resolved_schema_profile),
                schema=synthesis_schema(resolved_schema_profile),
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
                schema_name=schema_name_for_profile(SYNTHESIS_SCHEMA_NAME, resolved_schema_profile),
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

        synthesis_data = _augment_synthesis_artifacts(
            synthesis_data,
            plan=query_plan,
            rounds=all_rounds,
            stop_reason=stop_reason,
        )
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
            surface=surface,
            context_text=context_text,
            context_stats=context_stats,
            mode=mode,
            explicit_objective=objective,
            directive=directive,
            query_plan=query_plan,
            schema_profile=resolved_schema_profile,
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
            surface=surface,
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
            surface=surface,
            context_text=context_text,
            context_stats=context_stats,
            mode=mode,
            explicit_objective=objective,
            directive=directive,
            query_plan=query_plan,
            schema_profile=resolved_schema_profile if 'resolved_schema_profile' in locals() else 'software',
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
        artifact_path = None
        try:
            artifact_path = str(
                write_run_artifact(
                    cwd=cwd,
                    run_dir=config.defaults.run_dir,
                    invocation_id=invocation_id,
                    artifact=artifact,
                )
            )
        except Exception:
            artifact_path = None
        raise MoreDakkaRuntimeError(str(exc), run_artifact_path=artifact_path) from exc
