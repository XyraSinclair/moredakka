from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


CandidateStatus = Literal["selected", "rejected", "uncertain"]


@dataclass(frozen=True)
class CandidateOperation:
    canonical_op: str
    score: float
    evidence: list[str] = field(default_factory=list)
    rationale: str = ""
    status: CandidateStatus = "uncertain"


@dataclass(frozen=True)
class ContextPolicy:
    local_first: bool = True
    use_latest_run: bool = False
    fresh_start: bool = False
    tail_bias: bool = False


@dataclass(frozen=True)
class RoleInvocation:
    role_name: str
    emphasis: str = "normal"
    obligations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SynthesisPolicy:
    require_candidate_comparison: bool = False
    require_status_ledger: bool = False
    require_operator_summary: bool = False
    require_intent_card: bool = False
    require_handoff: bool = False


@dataclass(frozen=True)
class StopPolicy:
    bounded_rounds: bool = True
    preserve_disagreements: bool = True


@dataclass(frozen=True)
class QueryPlan:
    mode: str
    directive: str
    objective_strategy: str
    context_policy: ContextPolicy
    role_plan: list[RoleInvocation]
    synthesis_policy: SynthesisPolicy
    final_artifacts: list[str]
    stop_policy: StopPolicy
    candidate_operations: list[CandidateOperation] = field(default_factory=list)
    selected_ops: list[str] = field(default_factory=list)
    context_signals: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
