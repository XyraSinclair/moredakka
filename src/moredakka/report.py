from __future__ import annotations

import json
from typing import Any

from moredakka.context import ContextPacket


def _bullet_list(items: list[str]) -> str:
    if not items:
        return "- none"
    return "\n".join(f"- {item}" for item in items)


def _render_issue(issue: dict[str, Any]) -> str:
    severity = issue.get("severity", "unknown")
    title = issue.get("title", "")
    detail = issue.get("detail", "")
    evidence = issue.get("evidence", []) or []
    text = f"- **{title}** ({severity}) — {detail}"
    if evidence:
        text += f"\n  - evidence: {'; '.join(evidence)}"
    return text


def _render_step(step: dict[str, Any]) -> str:
    lines = [f"- **{step.get('title', '')}** — {step.get('why', '')}"]
    files = step.get("files", []) or []
    commands = step.get("commands", []) or []
    acceptance = step.get("acceptance", []) or []
    if files:
        lines.append(f"  - files: {', '.join(files)}")
    if commands:
        lines.append(f"  - commands: {' | '.join(commands)}")
    if acceptance:
        lines.append(f"  - acceptance: {'; '.join(acceptance)}")
    return "\n".join(lines)


def _render_test(test: dict[str, Any]) -> str:
    return f"- **{test.get('name', '')}** ({test.get('kind', '')}) — `{test.get('command', '')}` — {test.get('purpose', '')}"


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
    lines = [
        f"- invocation_id={invocation.get('invocation_id', '(none)')}",
        f"- run_status={invocation.get('run_status', '(none)')}",
        f"- stop_reason={invocation.get('stop_reason', '(none)')}",
        f"- started_at={invocation.get('started_at', '(none)')}",
        f"- duration_ms={invocation.get('duration_ms', '(none)')}",
        f"- head_sha={repo.get('head_sha', '(none)')}",
        f"- merge_base={repo.get('merge_base', '(none)')}",
    ]
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
        "doc_count",
        "file_excerpt_count",
        "changed_file_count",
    ]:
        value = stats.get(key)
        if value is None:
            continue
        lines.append(f"- {key}={value}")
    return lines or ["- none"]


def render_markdown(
    *,
    packet: ContextPacket,
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
    lines.append(synthesis.get("inferred_objective", packet.inferred_objective))
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
    actions = synthesis.get("next_actions", []) or []
    lines.append("\n".join(_render_step(item) for item in actions) or "- none")
    lines.append("")
    lines.append("## commit plan")
    commits = synthesis.get("commit_plan", []) or []
    lines.append("\n".join(_render_commit(item) for item in commits) or "- none")
    lines.append("")
    lines.append("## tests")
    tests = synthesis.get("tests", []) or []
    lines.append("\n".join(_render_test(item) for item in tests) or "- none")
    lines.append("")
    lines.append("## edit targets")
    edits = synthesis.get("edit_targets", []) or []
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
    lines.append(
        _bullet_list(
            [
                f"mode={packet.mode}",
                f"branch={packet.branch or '(none)'}",
                f"changed_files={', '.join(packet.changed_files) if packet.changed_files else '(none)'}",
                f"base_ref={packet.base_ref}",
            ]
        )
    )
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
    packet: ContextPacket,
    synthesis: dict[str, Any],
    rounds: list[list[dict[str, Any]]],
    provider_notes: list[str],
    run_artifact: dict[str, Any] | None = None,
    run_artifact_path: str | None = None,
) -> str:
    payload = {
        "context_packet": packet.to_dict(),
        "synthesis": synthesis,
        "rounds": rounds,
        "providers": provider_notes,
        "run": run_artifact,
        "run_artifact_path": run_artifact_path,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
