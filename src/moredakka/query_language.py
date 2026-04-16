from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from moredakka.context import ContextPacket
from moredakka.query_plan import (
    CandidateOperation,
    ContextPolicy,
    QueryPlan,
    RoleInvocation,
    StopPolicy,
    SynthesisPolicy,
)
from moredakka.roles import default_role_sequence
from moredakka.util import normalize_phrase


OP_ORDER = [
    "intent",
    "resume",
    "fresh",
    "close",
    "critique",
    "minimal",
    "branch",
    "compare",
    "integrate",
    "condense",
    "handoff",
    "local",
]

SELECTED_ORDER = [
    "intent",
    "resume",
    "fresh",
    "close",
    "critique",
    "minimal",
    "branch",
    "compare",
    "integrate",
    "condense",
    "handoff",
    "local",
]


def _contains_any(text: str, phrases: Iterable[str]) -> list[str]:
    hits: list[str] = []
    for phrase in phrases:
        if phrase in text:
            hits.append(phrase)
    return hits


def _candidate_specs(text: str, *, mode: str) -> list[tuple[str, float, list[str], str]]:
    specs: list[tuple[str, float, list[str], str]] = []

    def add(op: str, score: float, evidence: list[str], rationale: str) -> None:
        if evidence:
            specs.append((op, score, evidence, rationale))

    add(
        "resume",
        0.92,
        _contains_any(text, ["continue from where we were", "continue from the last run", "continue from where we were", "continue"]),
        "resume/continuation cues in directive prose",
    )
    add(
        "fresh",
        0.96,
        _contains_any(text, ["start fresh", "fresh take", "do not continue", "ignore the last run"]),
        "fresh-start cues in directive prose",
    )
    add(
        "close",
        0.9,
        _contains_any(text, ["what remains", "what's left", "what is left", "done / remaining", "blocked", "status first"]),
        "closure/status cues in directive prose",
    )
    add(
        "condense",
        0.88,
        _contains_any(text, ["keep it tight", "tighten", "tight", "condense", "short summary", "concise"]),
        "conciseness cues in directive prose",
    )
    add(
        "critique",
        0.86,
        _contains_any(text, ["be critical", "be adversarial", "brutally", "critique", "stress it"]),
        "adversarial/critique cues in directive prose",
    )
    add(
        "minimal",
        0.84,
        _contains_any(text, ["keep it small", "keep it minimal", "smallest safe", "minimal", "keep it small"]),
        "scope-cutting cues in directive prose",
    )
    add(
        "intent",
        0.9,
        _contains_any(text, ["what actually matters", "real goal", "what is the real goal", "what matters here", "core intent"]),
        "core-intent cues in directive prose",
    )
    add(
        "branch",
        0.82,
        _contains_any(text, ["multiple angles", "multiple options", "show me options", "give me options", "different angles", "multiple patch shapes"]),
        "alternative-generation cues in directive prose",
    )
    add(
        "compare",
        0.83,
        _contains_any(text, ["compare", "weigh options", "tradeoffs", "contrast options", "which is better"]),
        "comparison cues in directive prose",
    )
    add(
        "integrate",
        0.81,
        _contains_any(text, ["pick one", "choose", "select one", "recommend one"]),
        "selection/integration cues in directive prose",
    )
    add(
        "handoff",
        0.8,
        _contains_any(text, ["handoff", "continuation prompt", "for another agent"]),
        "handoff cues in directive prose",
    )
    add(
        "local",
        0.8,
        _contains_any(text, ["local to the diff", "stay close to the diff", "keep this local", "local only"]),
        "local-context cues in directive prose",
    )

    if mode == "review":
        specs.append(("critique", 0.81, ["mode=review"], "review mode defaults toward criticism and risk discovery"))
    if mode == "patch":
        specs.append(("minimal", 0.81, ["mode=patch"], "patch mode defaults toward smaller concrete changes"))
    return specs


def _merge_candidates(specs: list[tuple[str, float, list[str], str]]) -> list[CandidateOperation]:
    merged: dict[str, CandidateOperation] = {}
    for op, score, evidence, rationale in specs:
        current = merged.get(op)
        if current is None or score > current.score:
            merged[op] = CandidateOperation(
                canonical_op=op,
                score=score,
                evidence=evidence,
                rationale=rationale,
                status="uncertain",
            )
        else:
            merged[op] = CandidateOperation(
                canonical_op=current.canonical_op,
                score=current.score,
                evidence=list(dict.fromkeys(current.evidence + evidence)),
                rationale=current.rationale,
                status=current.status,
            )
    return sorted(merged.values(), key=lambda item: (-item.score, OP_ORDER.index(item.canonical_op) if item.canonical_op in OP_ORDER else 999))


def _choose_selected(candidates: list[CandidateOperation]) -> list[CandidateOperation]:
    selected: list[CandidateOperation] = []
    rejected: dict[str, CandidateOperation] = {}

    by_op = {candidate.canonical_op: candidate for candidate in candidates}
    if "fresh" in by_op and "resume" in by_op:
        winner = "fresh" if by_op["fresh"].score >= by_op["resume"].score else "resume"
        loser = "resume" if winner == "fresh" else "fresh"
        rejected[loser] = replace(by_op[loser], status="rejected", rationale=by_op[loser].rationale + "; rejected because it conflicts with higher-scored state policy")
        by_op[winner] = replace(by_op[winner], status="selected")

    threshold = 0.8
    for op in OP_ORDER:
        candidate = by_op.get(op)
        if candidate is None:
            continue
        if op in rejected:
            continue
        if candidate.score >= threshold:
            selected.append(replace(candidate, status="selected"))
        else:
            rejected[op] = replace(candidate, status="rejected", rationale=candidate.rationale + "; rejected because score was below selection threshold")

    selected_ops = {item.canonical_op for item in selected}
    finalized: list[CandidateOperation] = []
    for candidate in candidates:
        if candidate.canonical_op in rejected:
            finalized.append(rejected[candidate.canonical_op])
        elif candidate.canonical_op in selected_ops:
            finalized.append(next(item for item in selected if item.canonical_op == candidate.canonical_op))
        else:
            finalized.append(replace(candidate, status="uncertain"))
    return finalized


def _selected_ops(candidates: list[CandidateOperation]) -> list[str]:
    selected = [item.canonical_op for item in candidates if item.status == "selected"]
    return sorted(selected, key=lambda item: SELECTED_ORDER.index(item) if item in SELECTED_ORDER else 999)


def _objective_strategy(selected_ops: list[str]) -> str:
    if "resume" in selected_ops and "close" in selected_ops:
        return "continue_with_status_first"
    if "intent" in selected_ops:
        return "extract_intent_then_plan"
    return "direct_plan"


def _context_policy(selected_ops: list[str]) -> ContextPolicy:
    return ContextPolicy(
        local_first=True,
        use_latest_run="resume" in selected_ops,
        fresh_start="fresh" in selected_ops,
        tail_bias="resume" in selected_ops or "close" in selected_ops,
    )


def _role_plan(mode: str, selected_ops: list[str], base_role_names: list[str]) -> list[RoleInvocation]:
    emphasis: dict[str, str] = {role_name: "normal" for role_name in base_role_names}
    obligations: dict[str, list[str]] = {role_name: [] for role_name in base_role_names}

    if "critique" in selected_ops and "breaker" in emphasis:
        emphasis["breaker"] = "high"
        obligations["breaker"].append("Push harder on failure modes and hidden risks.")
    if "minimal" in selected_ops and "minimalist" in emphasis:
        emphasis["minimalist"] = "high"
        obligations["minimalist"].append("Cut ornamental scope and compress to the smallest safe move.")
    if "branch" in selected_ops:
        for role_name in [name for name in base_role_names if name in {"planner", "implementer"}]:
            obligations[role_name].append("Propose at least two meaningfully distinct candidate paths.")
    if "compare" in selected_ops:
        for role_name in [name for name in base_role_names if name in {"planner", "breaker"}]:
            obligations[role_name].append("Explicitly compare candidate paths and note tradeoffs.")

    return [RoleInvocation(role_name=role_name, emphasis=emphasis[role_name], obligations=obligations[role_name]) for role_name in base_role_names]


def _synthesis_policy(selected_ops: list[str]) -> SynthesisPolicy:
    return SynthesisPolicy(
        require_candidate_comparison="compare" in selected_ops or "branch" in selected_ops,
        require_status_ledger="close" in selected_ops,
        require_operator_summary="condense" in selected_ops,
        require_intent_card="intent" in selected_ops,
        require_handoff="handoff" in selected_ops,
    )


def _final_artifacts(selected_ops: list[str]) -> list[str]:
    artifacts = ["report"]
    if "intent" in selected_ops:
        artifacts.append("intent_card")
    if "close" in selected_ops:
        artifacts.append("status_ledger")
    if "condense" in selected_ops:
        artifacts.append("operator_summary")
    if "handoff" in selected_ops:
        artifacts.append("handoff_paragraph")
    return artifacts


def _context_signals(
    *,
    packet: ContextPacket | None,
    has_recent_run_artifact: bool,
    recent_run_summary: dict[str, object] | None,
) -> list[str]:
    signals: list[str] = []
    if packet:
        if packet.changed_files:
            signals.append(f"changed_files={len(packet.changed_files)}")
        if packet.diff_excerpt:
            signals.append("has_diff")
        if packet.branch and packet.branch not in {"main", "master"}:
            signals.append(f"branch={packet.branch}")
    if has_recent_run_artifact:
        signals.append("recent_run_artifact")
    if recent_run_summary:
        run_status = recent_run_summary.get("run_status")
        stop_reason = recent_run_summary.get("stop_reason")
        selected_ops = recent_run_summary.get("selected_ops") or []
        if isinstance(run_status, str) and run_status:
            signals.append(f"recent_run_status={run_status}")
        if isinstance(stop_reason, str) and stop_reason:
            signals.append(f"recent_stop_reason={stop_reason}")
        if isinstance(selected_ops, list) and selected_ops:
            signals.append("recent_selected_ops=" + ",".join(str(item) for item in selected_ops[:5]))
    return signals


def _apply_contextual_adjustments(
    candidates: list[CandidateOperation],
    *,
    mode: str,
    packet: ContextPacket | None,
    has_recent_run_artifact: bool,
    recent_run_summary: dict[str, object] | None,
) -> list[CandidateOperation]:
    adjusted = list(candidates)
    by_op = {item.canonical_op: item for item in adjusted}

    def upsert(op: str, score: float, evidence: list[str], rationale: str) -> None:
        current = by_op.get(op)
        if current is None:
            item = CandidateOperation(canonical_op=op, score=score, evidence=evidence, rationale=rationale, status="uncertain")
            adjusted.append(item)
            by_op[op] = item
            return
        merged = replace(
            current,
            score=max(current.score, score),
            evidence=list(dict.fromkeys(current.evidence + evidence)),
            rationale=current.rationale if current.rationale == rationale else f"{current.rationale}; {rationale}".strip("; "),
        )
        by_op[op] = merged
        adjusted[adjusted.index(current)] = merged

    if packet and (packet.changed_files or packet.diff_excerpt):
        upsert("local", 0.87 if mode in {"review", "patch"} else 0.81, ["live repo diff/worktree"], "repo surface contains active local changes")
    if has_recent_run_artifact:
        upsert("resume", 0.78, ["recent run artifact"], "recent run artifacts make continuation semantics more plausible")
        upsert("close", 0.76, ["recent run artifact"], "recent run artifacts make closure/status reporting more plausible")
    if recent_run_summary:
        run_status = str(recent_run_summary.get("run_status") or "")
        stop_reason = str(recent_run_summary.get("stop_reason") or "")
        selected_ops = [str(item) for item in (recent_run_summary.get("selected_ops") or [])]
        if run_status in {"degraded", "failed"}:
            upsert("critique", 0.82, [f"recent run status={run_status}"], "degraded or failed recent runs justify a stronger failure-seeking pass")
        if stop_reason in {"max_total_tokens", "max_cost_usd", "max_wall_seconds"}:
            upsert("close", 0.84, [f"recent stop reason={stop_reason}"], "budget-bounded recent runs increase the value of explicit closure and handoff")
            upsert("handoff", 0.81, [f"recent stop reason={stop_reason}"], "budget-bounded recent runs increase the value of a clean continuation artifact")
        if "branch" in selected_ops or "compare" in selected_ops:
            upsert("integrate", 0.8, ["recent run explored multiple paths"], "recent multi-path exploration increases the value of converging on one path")
        if "resume" in selected_ops and not any(item.canonical_op == "fresh" for item in adjusted):
            upsert("resume", 0.82, ["recent run selected resume-like behavior"], "recent compiled plans suggest continuity may still matter")
    if mode == "review" and packet and packet.diff_excerpt:
        upsert("local", 0.9, ["review mode + diff"], "review mode should stay glued to the live delta when a diff exists")
    if mode == "patch" and packet and packet.diff_excerpt:
        upsert("minimal", 0.86, ["patch mode + diff"], "patch mode with a live diff should bias toward smaller concrete changes")
    return _merge_candidates([(item.canonical_op, item.score, item.evidence, item.rationale) for item in adjusted])


OP_FAMILIES = {
    "intent": "objective",
    "resume": "state",
    "fresh": "state",
    "close": "closure",
    "critique": "analysis",
    "minimal": "analysis",
    "branch": "exploration",
    "compare": "exploration",
    "integrate": "exploration",
    "condense": "output",
    "handoff": "output",
    "local": "context",
}


def _apply_solver(
    candidates: list[CandidateOperation],
    *,
    has_recent_run_artifact: bool,
    recent_run_summary: dict[str, object] | None,
) -> list[CandidateOperation]:
    selected: list[CandidateOperation] = []
    rejected: dict[str, CandidateOperation] = {}
    by_op = {candidate.canonical_op: candidate for candidate in candidates}

    def reject(op: str, reason: str) -> None:
        candidate = by_op.get(op)
        if candidate is None:
            return
        rejected[op] = replace(candidate, status="rejected", rationale=candidate.rationale + "; " + reason)

    def soften(op: str, amount: float, reason: str) -> None:
        candidate = by_op.get(op)
        if candidate is None or op in rejected:
            return
        softened = replace(candidate, score=max(0.0, candidate.score - amount), rationale=candidate.rationale + "; " + reason)
        by_op[op] = softened

    if "fresh" in by_op and "resume" in by_op:
        winner = "fresh" if by_op["fresh"].score >= by_op["resume"].score else "resume"
        loser = "resume" if winner == "fresh" else "fresh"
        reject(loser, "rejected because it conflicts with higher-scored state policy")
        by_op[winner] = replace(by_op[winner], status="selected")

    if "resume" in by_op and not has_recent_run_artifact and all(token not in " ".join(by_op["resume"].evidence) for token in ["continue", "last run"]):
        reject("resume", "rejected because no recent run artifact exists")

    recent_selected_ops = {str(item) for item in (recent_run_summary or {}).get("selected_ops", [])}
    if "integrate" in by_op and "branch" not in by_op and "compare" not in by_op and not ({"branch", "compare"} & recent_selected_ops):
        reject("integrate", "rejected because there are no alternative paths to integrate")

    if "compare" in by_op and "branch" not in by_op and "integrate" not in by_op:
        soften("compare", 0.04, "softened because no explicit alternative-generation operator was selected")

    if "handoff" in by_op and not has_recent_run_artifact and not recent_run_summary:
        soften("handoff", 0.03, "softened because there is no prior run state to hand off from")

    threshold = 0.8
    for op in OP_ORDER:
        candidate = by_op.get(op)
        if candidate is None or op in rejected:
            continue
        if candidate.score >= threshold:
            selected.append(replace(candidate, status="selected"))
        else:
            reject(op, "rejected because score was below selection threshold")

    selected_ops = {item.canonical_op for item in selected}
    finalized: list[CandidateOperation] = []
    for candidate in candidates:
        candidate_now = by_op.get(candidate.canonical_op, candidate)
        if candidate.canonical_op in rejected:
            finalized.append(rejected[candidate.canonical_op])
        elif candidate.canonical_op in selected_ops:
            finalized.append(next(item for item in selected if item.canonical_op == candidate.canonical_op))
        else:
            finalized.append(replace(candidate_now, status="uncertain"))
    return finalized


def compile_query_plan(
    mode: str,
    directive: str | None,
    base_role_names: list[str] | None = None,
    *,
    packet: ContextPacket | None = None,
    has_recent_run_artifact: bool = False,
    recent_run_summary: dict[str, object] | None = None,
) -> QueryPlan:
    directive_text = (directive or "").strip()
    normalized = normalize_phrase(directive_text)
    roles = list(base_role_names or default_role_sequence(mode))
    base_candidates = _merge_candidates(_candidate_specs(normalized, mode=mode)) if normalized else _merge_candidates(_candidate_specs("", mode=mode))
    contextual_candidates = _apply_contextual_adjustments(
        base_candidates,
        mode=mode,
        packet=packet,
        has_recent_run_artifact=has_recent_run_artifact,
        recent_run_summary=recent_run_summary,
    )
    finalized = _apply_solver(
        contextual_candidates,
        has_recent_run_artifact=has_recent_run_artifact,
        recent_run_summary=recent_run_summary,
    ) if contextual_candidates else []
    selected_ops = _selected_ops(finalized)
    context_signals = _context_signals(
        packet=packet,
        has_recent_run_artifact=has_recent_run_artifact,
        recent_run_summary=recent_run_summary,
    )
    notes = ["free-prose directive compiler"] if directive_text else []
    if context_signals:
        notes.append("context-aware inference")
    return QueryPlan(
        mode=mode,
        directive=directive_text,
        objective_strategy=_objective_strategy(selected_ops),
        context_policy=_context_policy(selected_ops),
        role_plan=_role_plan(mode, selected_ops, roles),
        synthesis_policy=_synthesis_policy(selected_ops),
        final_artifacts=_final_artifacts(selected_ops),
        stop_policy=StopPolicy(),
        candidate_operations=finalized,
        selected_ops=selected_ops,
        context_signals=context_signals,
        notes=notes,
    )


def render_query_plan_summary(plan: QueryPlan) -> str:
    lines = [
        f"- objective_strategy={plan.objective_strategy}",
        f"- local_first={plan.context_policy.local_first}",
        f"- use_latest_run={plan.context_policy.use_latest_run}",
        f"- fresh_start={plan.context_policy.fresh_start}",
        f"- require_candidate_comparison={plan.synthesis_policy.require_candidate_comparison}",
        f"- require_status_ledger={plan.synthesis_policy.require_status_ledger}",
        f"- require_operator_summary={plan.synthesis_policy.require_operator_summary}",
        f"- final_artifacts={', '.join(plan.final_artifacts)}",
    ]
    if plan.context_signals:
        lines.append(f"- context_signals={', '.join(plan.context_signals)}")
    if plan.role_plan:
        lines.append("- role_plan=" + ", ".join(f"{item.role_name}:{item.emphasis}" for item in plan.role_plan))
    return "\n".join(lines)


def render_candidate_operations(plan: QueryPlan) -> str:
    if not plan.candidate_operations:
        return "(none)"
    return "\n".join(
        f"- {item.canonical_op} ({item.score:.2f}) [{item.status}] because {'; '.join(item.evidence) or 'implicit cue'}"
        for item in plan.candidate_operations
    )


def render_selected_ops(plan: QueryPlan) -> str:
    return " ".join(plan.selected_ops) if plan.selected_ops else "(none)"
