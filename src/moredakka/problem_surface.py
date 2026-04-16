from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol


@dataclass
class ProblemArtifact:
    kind: str
    label: str
    locator: str
    excerpt: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProblemEvent:
    kind: str
    title: str
    summary: str = ""
    body: str = ""
    importance: str = "normal"
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProblemSurface:
    surface_type: str
    cwd: str
    mode: str
    objective: str
    inferred_objective: str
    state_summary: list[str] = field(default_factory=list)
    artifacts: list[ProblemArtifact] = field(default_factory=list)
    events: list[ProblemEvent] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def base_ref(self) -> str:
        return str(self.metadata.get("base_ref", ""))

    @property
    def branch(self) -> str | None:
        value = self.metadata.get("branch")
        return str(value) if value else None

    @property
    def changed_files(self) -> list[str]:
        value = self.metadata.get("changed_files")
        return list(value) if isinstance(value, list) else []

    @property
    def context_packet(self) -> dict[str, Any] | None:
        value = self.metadata.get("context_packet")
        return dict(value) if isinstance(value, dict) else None


class SurfaceAdapter(Protocol):
    name: str

    def build_surface(
        self,
        *,
        cwd,
        mode: str,
        objective: str | None,
        base_ref: str,
        char_budget: int,
    ) -> tuple[ProblemSurface, Any]: ...

    def render_surface(self, packet_or_surface: Any, *, char_budget: int) -> str: ...


def excerpt_char_count(surface: ProblemSurface) -> int:
    return sum(len(item.excerpt) for item in surface.artifacts if item.excerpt)


def artifact_count(surface: ProblemSurface, *, kind: str | None = None) -> int:
    if kind is None:
        return len(surface.artifacts)
    return sum(1 for item in surface.artifacts if item.kind == kind)
