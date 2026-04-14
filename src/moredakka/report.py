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


def render_markdown(
    *,
    packet: ContextPacket,
    synthesis: dict[str, Any],
    rounds: list[list[dict[str, Any]]],
    provider_notes: list[str],
) -> str:
    lines: list[str] = []
    lines.append("# moredakka report")
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
    lines.append("## provider roster")
    lines.append(_bullet_list(provider_notes))
    lines.append("")
    lines.append("## context summary")
    lines.append(_bullet_list([
        f"mode={packet.mode}",
        f"branch={packet.branch or '(none)'}",
        f"changed_files={', '.join(packet.changed_files) if packet.changed_files else '(none)'}",
        f"base_ref={packet.base_ref}",
    ]))
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
) -> str:
    payload = {
        "context_packet": packet.to_dict(),
        "synthesis": synthesis,
        "rounds": rounds,
        "providers": provider_notes,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
