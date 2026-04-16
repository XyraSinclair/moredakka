from __future__ import annotations

from moredakka.context import ContextPacket, build_context_packet, render_context_packet
from moredakka.problem_surface import ProblemArtifact, ProblemEvent, ProblemSurface


class RepoSurfaceAdapter:
    name = "repo"

    def build_surface(
        self,
        *,
        cwd,
        mode: str,
        objective: str | None,
        base_ref: str,
        char_budget: int,
    ) -> tuple[ProblemSurface, ContextPacket]:
        packet = build_context_packet(
            cwd=cwd,
            mode=mode,
            objective=objective,
            base_ref=base_ref,
            char_budget=char_budget,
        )
        return problem_surface_from_context_packet(packet), packet

    def render_surface(self, packet_or_surface: ContextPacket | ProblemSurface, *, char_budget: int) -> str:
        if isinstance(packet_or_surface, ContextPacket):
            return render_context_packet(packet_or_surface, char_budget=char_budget)
        context_packet = packet_or_surface.context_packet
        if not context_packet:
            raise RuntimeError("repo surface is missing compatibility context_packet metadata")
        packet = ContextPacket(**context_packet)
        return render_context_packet(packet, char_budget=char_budget)


def problem_surface_from_context_packet(packet: ContextPacket) -> ProblemSurface:
    artifacts: list[ProblemArtifact] = []
    for doc in packet.docs:
        artifacts.append(
            ProblemArtifact(
                kind="doc",
                label=doc.path,
                locator=doc.path,
                excerpt=doc.excerpt,
            )
        )
    for item in packet.file_excerpts:
        artifacts.append(
            ProblemArtifact(
                kind="file_excerpt",
                label=item.path,
                locator=item.path,
                excerpt=item.excerpt,
            )
        )

    events: list[ProblemEvent] = []
    for line in packet.status_summary:
        events.append(
            ProblemEvent(
                kind="status",
                title=line,
                summary=line,
                tags=["repo", "status"],
            )
        )
    for line in packet.recent_commits:
        events.append(
            ProblemEvent(
                kind="recent_commit",
                title=line,
                summary=line,
                tags=["repo", "commit"],
            )
        )
    if packet.diff_stats:
        events.append(
            ProblemEvent(
                kind="diff_stats",
                title="diff stats",
                summary=packet.diff_stats,
                body=packet.diff_stats,
                tags=["repo", "diff"],
            )
        )
    if packet.diff_excerpt:
        artifacts.append(
            ProblemArtifact(
                kind="diff_excerpt",
                label="diff excerpt",
                locator="diff",
                excerpt=packet.diff_excerpt,
                metadata={"diff_stats": packet.diff_stats},
            )
        )

    state_summary = [
        f"surface_type=repo",
        f"repo_root={packet.repo_root or '(none)'}",
        f"branch={packet.branch or '(none)'}",
        f"base_ref={packet.base_ref}",
        f"changed_files={', '.join(packet.changed_files) if packet.changed_files else '(none)'}",
    ]

    return ProblemSurface(
        surface_type="repo",
        cwd=packet.cwd,
        mode=packet.mode,
        objective=packet.objective,
        inferred_objective=packet.inferred_objective,
        state_summary=state_summary,
        artifacts=artifacts,
        events=events,
        metadata={
            "repo_root": packet.repo_root,
            "branch": packet.branch,
            "base_ref": packet.base_ref,
            "changed_files": packet.changed_files,
            "status_summary": packet.status_summary,
            "recent_commits": packet.recent_commits,
            "diff_stats": packet.diff_stats,
            "diff_excerpt": packet.diff_excerpt,
            "context_packet": packet.to_dict(),
        },
    )
