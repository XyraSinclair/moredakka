from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from typing import Iterable


@dataclass(frozen=True)
class RoleSpec:
    name: str
    prompt_resource: str
    purpose: str


ROLE_SPECS: dict[str, RoleSpec] = {
    "planner": RoleSpec(
        name="planner",
        prompt_resource="planner.md",
        purpose="Sequence the work, infer the real objective, and optimize the next operating path.",
    ),
    "implementer": RoleSpec(
        name="implementer",
        prompt_resource="implementer.md",
        purpose="Translate context into the smallest useful concrete actions, artifacts, files, commands, or interactions.",
    ),
    "breaker": RoleSpec(
        name="breaker",
        prompt_resource="breaker.md",
        purpose="Hunt for hidden failures, edge cases, bad assumptions, and operational risks.",
    ),
    "minimalist": RoleSpec(
        name="minimalist",
        prompt_resource="minimalist.md",
        purpose="Cut speculative work and compress the plan to the smallest safe move.",
    ),
    "synthesizer": RoleSpec(
        name="synthesizer",
        prompt_resource="synthesizer.md",
        purpose="Merge role outputs into one decisive operating recommendation and handoff-ready report.",
    ),
}


def default_role_sequence(mode: str) -> list[str]:
    mode = mode.lower()
    if mode in {"plan", "here"}:
        return ["planner", "implementer", "breaker", "minimalist"]
    if mode == "review":
        return ["breaker", "planner", "implementer", "minimalist"]
    if mode == "patch":
        return ["implementer", "breaker", "minimalist", "planner"]
    if mode == "loop":
        return ["planner", "implementer", "breaker", "minimalist"]
    raise ValueError(f"Unsupported mode: {mode}")


def load_prompt(role_name: str) -> str:
    spec = ROLE_SPECS[role_name]
    return resources.files("moredakka").joinpath("prompts", spec.prompt_resource).read_text(encoding="utf-8")


def mode_instruction(mode: str) -> str:
    mode = mode.lower()
    if mode in {"plan", "here"}:
        return (
            "Bias toward operational sequencing, validation steps, and the fastest path "
            "to a safer, clearer state."
        )
    if mode == "review":
        return (
            "Bias toward correctness, maintainability, missing validation, reversibility, and the most credible "
            "ways the current approach could fail or damage future work."
        )
    if mode == "patch":
        return (
            "Bias toward concrete intervention targets, minimal shape, exact levers, and the smallest safe move "
            "set that solves the apparent problem."
        )
    if mode == "loop":
        return (
            "Bias toward convergence over rounds: sharpen the plan, remove repeated points, and preserve only "
            "high-value disagreements."
        )
    raise ValueError(f"Unsupported mode: {mode}")
