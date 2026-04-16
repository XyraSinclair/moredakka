from __future__ import annotations

import json
from typing import Any

from moredakka.context import ContextPacket
from moredakka.problem_surface import ProblemSurface


SurfaceLike = ContextPacket | ProblemSurface


def _bullet_list(items: list[str]) -> str:
    if not items:
        return "- none"
    return "\n".join(f"- {item}" for item in items)


def _surface_summary_lines(surface: SurfaceLike) -> list[str]:
    if isinstance(surface, ProblemSurface):
        lines = [
            f"surface_type={surface.surface_type}",
            f"mode={surface.mode}",
            f"cwd={surface.cwd}",
            f"branch={surface.branch or '(none)'}",
            f"changed_files={', '.join(surface.changed_files) if surface.changed_files else '(none)'}",
            f"base_ref={surface.base_ref or '(none)'}",
        ]
        if surface.state_summary:
            lines.extend(surface.state_summary)
        return list(dict.fromkeys(lines))
    return [
        f"mode={surface.mode}",
        f"branch={surface.branch or '(none)'}",
        f"changed_files={', '.join(surface.changed_files) if surface.changed_files else '(none)'}",
        f"base_ref={surface.base_ref}",
    ]


def _render_issue(issue: dict[str, Any]) -> str:
    severity = issue.get("severity", "unknown")
    title = issue.get("title", "")
    detail = issue.get("detail", "")
    evidence = issue.get("evidence", []) or []
    text = f"- **{title}** ({severity}) — {detail}"
    if evidence:
        text += f"\n  - evidence: {'; '.join(evidence)}"
    return text


def _render_action(step: dict[str, Any]) -> str:
    lines = [f"- **{step.get('title', '')}** — {step.get('why', '')}"]
    artifacts = step.get("artifacts", []) or []
    files = step.get("files", []) or []
    commands = step.get("commands", []) or []
    acceptance = step.get("acceptance", []) or []
    if artifacts:
        lines.append(f"  - artifacts: {', '.join(artifacts)}")
    if files:
        lines.append(f"  - files: {', '.join(files)}")
    if commands:
        lines.append(f"  - commands: {' | '.join(commands)}")
    if acceptance:
        lines.append(f"  - acceptance: {'; '.join(acceptance)}")
    return "\n".join(lines)


def _render_validation_check(check: dict[str, Any]) -> str:
    return f"- **{check.get('name', '')}** ({check.get('kind', '')}) — `{check.get('command', '')}` — {check.get('purpose', '')}"


def _render_edit(edit: dict[str, Any]) -> str:
    return (
        f"- **{edit.get('file', '')}** [{edit.get('change_type', '')}] — "
        f"{edit.get('reason', '')}. {edit.get('summary', '')}"
    )


def _render_risk(risk: dict[str, Any]) -> str:
    return (
        f"- **{risk.get('name', '')}** ({risk.get('likelihood', '')}) — "
        f"{risk.get('impact', '')}. Mitigation: {risk.get('mitigation', '')}"
    )


def _render_commit(commit: dict[str, Any]) -> str:
    files = ", ".join(commit.get("files", []) or [])
    return f"- **{commit.get('title', '')}** — {commit.get('summary', '')} — files: {files}"


def _render_disagreement(disagreement: dict[str, Any]) -> str:
    positions = disagreement.get("positions", []) or []
    return (
        f"- **{disagreement.get('topic', '')}** — "
        f"{' | '.join(positions)}. Resolve by: {disagreement.get('recommended_resolution', '')}"
    )


def _usage_lines(run_artifact: dict[str, Any] | None) -> list[str]:
    if not run_artifact:
        return ["- none"]
    totals = run_artifact.get("usage_totals", {}) or {}
    out: list[str] = []
    for key in [
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "reasoning_tokens",
        "cached_input_tokens",
        "estimated_cost_usd",
    ]:
        value = totals.get(key)
        if value is None:
            continue
        out.append(f"- {key}={value}")
    return out or ["- none"]


def _invocation_lines(run_artifact: dict[str, Any] | None, run_artifact_path: str | None) -> list[str]:
    if not run_artifact:
        return ["- none"]
    invocation = run_artifact.get("invocation", {}) or {}
    repo = run_artifact.get("repo", {}) or {}
    problem_surface = run_artifact.get("problem_surface", {}) or {}
    lines = [
        f"- invocation_id={invocation.get('invocation_id', '(none)')}",
        f"- run_status={invocation.get('run_status', '(none)')}",
        f"- stop_reason={invocation.get('stop_reason', '(none)')}",
        f"- started_at={invocation.get('started_at', '(none)')}",
        f"- duration_ms={invocation.get('duration_ms', '(none)')}",
        f"- surface_type={problem_surface.get('surface_type', '(none)')}",
    ]
    if repo.get("head_sha") is not None:
        lines.append(f"- head_sha={repo.get('head_sha', '(none)')}")
    if repo.get("merge_base") is not None:
        lines.append(f"- merge_base={repo.get('merge_base', '(none)')}")
    if run_artifact_path:
        lines.append(f"- run_artifact={run_artifact_path}")
    return lines


def _context_render_lines(run_artifact: dict[str, Any] | None) -> list[str]:
    if not run_artifact:
        return ["- none"]
    stats = run_artifact.get("context_rendering", {}) or {}
    lines = []
    for key in [
        "char_budget",
        "rendered_chars",
        "source_excerpt_chars",
        "truncated",
        "artifact_count",
        "event_count",
        "doc_count",
        "file_excerpt_count",
        "changed_file_count",
    ]:
        value = stats.get(key)
        if value is None:
            continue
        lines.append(f"- {key}={value}")
    return lines or ["- none"]


def _query_compilation_lines(run_artifact: dict[str, Any] | None) -> list[str]:
    if not run_artifact:
        return ["- none"]
    query = run_artifact.get("query_compilation", {}) or {}
    directive = query.get("directive") or "(none)"
    selected = query.get("selected_ops", []) or []
    plan = query.get("query_plan", {}) or {}
    lines = [
        f"- directive={directive}",
        f"- selected_ops={', '.join(selected) if selected else '(none)'}",
    ]
    if plan:
        objective_strategy = plan.get("objective_strategy")
        final_artifacts = plan.get("final_artifacts")
        schema_profile = plan.get("schema_profile")
        context_signals = plan.get("context_signals")
        if objective_strategy:
            lines.append(f"- objective_strategy={objective_strategy}")
        if schema_profile:
            lines.append(f"- schema_profile={schema_profile}")
        if final_artifacts:
            lines.append(f"- final_artifacts={', '.join(final_artifacts)}")
        if context_signals:
            lines.append(f"- context_signals={', '.join(context_signals)}")
    return lines


def _render_status_ledger(ledger: dict[str, Any]) -> str:
    lines: list[str] = []
    for key in ["done", "remaining", "blocked", "next"]:
        values = ledger.get(key, []) or []
        label = key.replace("_", " ")
        if values:
            lines.append(f"- {label}: {'; '.join(str(value) for value in values)}")
        else:
            lines.append(f"- {label}: none")
    return "\n".join(lines)


def _field_items(synthesis: dict[str, Any], *names: str) -> list[dict[str, Any]]:
    for name in names:
        value = synthesis.get(name)
        if isinstance(value, list):
            return value
    return []


def _has_field(synthesis: dict[str, Any], *names: str) -> bool:
    return any(name in synthesis for name in names)


def render_markdown(
    *,
    packet: SurfaceLike,
    synthesis: dict[str, Any],
    rounds: list[list[dict[str, Any]]],
    provider_notes: list[str],
    run_artifact: dict[str, Any] | None = None,
    run_artifact_path: str | None = None,
) -> str:
    lines: list[str] = []
    lines.append("# moredakka report")
    lines.append("")
    lines.append("## invocation")
    lines.extend(_invocation_lines(run_artifact, run_artifact_path))
    lines.append("")
    lines.append("## inferred objective")
    lines.append(synthesis.get("inferred_objective", getattr(packet, "inferred_objective", "")))
    lines.append("")
    lines.append("## query compilation")
    lines.extend(_query_compilation_lines(run_artifact))
    lines.append("")
    lines.append("## one-line take")
    lines.append(synthesis.get("one_sentence_take", ""))
    lines.append("")
    lines.append("## selected path")
    selected = synthesis.get("selected_path", {}) or {}
    lines.append(f"**{selected.get('name', '')}** — {selected.get('summary', '')}")
    tradeoffs = selected.get("tradeoffs", []) or []
    if tradeoffs:
        lines.append(_bullet_list(tradeoffs))
    lines.append("")
    lines.append("## top problems")
    problems = synthesis.get("top_problems", []) or []
    lines.append("\n".join(_render_issue(item) for item in problems) or "- none")
    lines.append("")
    lines.append("## next actions")
    actions = _field_items(synthesis, "next_actions")
    lines.append("\n".join(_render_action(item) for item in actions) or "- none")
    lines.append("")
    if _has_field(synthesis, "validation_checks", "tests"):
        lines.append("## validation")
        checks = _field_items(synthesis, "validation_checks", "tests")
        lines.append("\n".join(_render_validation_check(item) for item in checks) or "- none")
        lines.append("")
    if _has_field(synthesis, "commit_plan"):
        lines.append("## commit plan")
        commits = _field_items(synthesis, "commit_plan")
        lines.append("\n".join(_render_commit(item) for item in commits) or "- none")
        lines.append("")
    if _has_field(synthesis, "edit_targets"):
        lines.append("## edit targets")
        edits = _field_items(synthesis, "edit_targets")
        lines.append("\n".join(_render_edit(item) for item in edits) or "- none")
        lines.append("")
    lines.append("## major risks")
    risks = synthesis.get("major_risks", []) or []
    lines.append("\n".join(_render_risk(item) for item in risks) or "- none")
    lines.append("")
    lines.append("## disagreements")
    disagreements = synthesis.get("disagreements", []) or []
    lines.append("\n".join(_render_disagreement(item) for item in disagreements) or "- none")
    lines.append("")
    lines.append("## stop conditions")
    lines.append(_bullet_list(synthesis.get("stop_conditions", []) or []))
    lines.append("")
    lines.append("## open questions")
    lines.append(_bullet_list(synthesis.get("open_questions", []) or []))
    lines.append("")
    if synthesis.get("operator_summary"):
        lines.append("## operator summary")
        lines.append(str(synthesis.get("operator_summary", "")))
        lines.append("")
    if synthesis.get("status_ledger"):
        lines.append("## status ledger")
        lines.append(_render_status_ledger(synthesis.get("status_ledger", {}) or {}))
        lines.append("")
    if synthesis.get("intent_card"):
        lines.append("## intent card")
        lines.append("```json")
        lines.append(json.dumps(synthesis.get("intent_card", {}), indent=2, ensure_ascii=False))
        lines.append("```")
        lines.append("")
    if synthesis.get("handoff_paragraph"):
        lines.append("## handoff paragraph")
        lines.append(str(synthesis.get("handoff_paragraph", "")))
        lines.append("")
    lines.append("## confidence")
    lines.append(f"{synthesis.get('confidence', 0):.2f} — {synthesis.get('confidence_rationale', '')}")
    lines.append("")
    lines.append("## usage and cost")
    lines.extend(_usage_lines(run_artifact))
    lines.append("")
    lines.append("## context rendering")
    lines.extend(_context_render_lines(run_artifact))
    lines.append("")
    lines.append("## provider roster")
    lines.append(_bullet_list(provider_notes))
    lines.append("")
    lines.append("## context summary")
    lines.append(_bullet_list(_surface_summary_lines(packet)))
    lines.append("")
    lines.append("## role rounds")
    for idx, round_outputs in enumerate(rounds, start=1):
        lines.append(f"### round {idx}")
        for item in round_outputs:
            role = item.get("role", "unknown")
            take = item.get("one_sentence_take", "")
            lines.append(f"- **{role}** — {take}")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def render_json(
    *,
    packet: SurfaceLike,
    synthesis: dict[str, Any],
    rounds: list[list[dict[str, Any]]],
    provider_notes: list[str],
    run_artifact: dict[str, Any] | None = None,
    run_artifact_path: str | None = None,
    surface: ProblemSurface | None = None,
) -> str:
    payload = {
        "context_packet": packet.to_dict() if hasattr(packet, "to_dict") else {},
        "problem_surface": (surface or packet).to_dict() if hasattr(surface or packet, "to_dict") else {},
        "synthesis": synthesis,
        "rounds": rounds,
        "providers": provider_notes,
        "run": run_artifact,
        "run_artifact_path": run_artifact_path,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
