from __future__ import annotations

from moredakka.problem_surface import SurfaceAdapter
from moredakka.surfaces.repo import RepoSurfaceAdapter


_SURFACE_ADAPTERS: dict[str, SurfaceAdapter] = {
    "repo": RepoSurfaceAdapter(),
}


def supported_surfaces() -> set[str]:
    return set(_SURFACE_ADAPTERS)


def resolve_surface_adapter(surface: str) -> SurfaceAdapter:
    try:
        return _SURFACE_ADAPTERS[surface]
    except KeyError as exc:
        raise RuntimeError(
            f"Unsupported surface: {surface}. Supported surfaces: {', '.join(sorted(_SURFACE_ADAPTERS))}"
        ) from exc
