# Free-Prose Operator Compiler Plan

> For Hermes: keep this narrow. Do not turn `moredakka` into a general chat wrapper or autonomous swarm. Treat this as a bounded compiler from free operator prose into explicit query plans for disciplined software-work cognition.

Goal: let an operator speak in natural language and have a front-end compiler infer a concrete LLM query plan: context policy, role mix, critique passes, compare/contrast behavior, and final condensation behavior.

Architecture: add a small front-end compiler layer before orchestration. The compiler should parse free-form directive prose, infer a diverse candidate set of canonical operations, score which ones actually fit, and compile the survivors into an explicit `QueryPlan` object. The existing bounded context packet, role loop, and typed synthesis stay intact. The new layer should shape how the loop runs, not broaden the product into unbounded agent chat theater.

Tech stack: Python 3.11+, argparse CLI, dataclasses, deterministic preprocessing plus bounded scoring, unit tests, markdown docs.

---

## Why this exists

There is real leverage in a system that can read operator prose, over-generate plausible cognitive moves, and then compile the best-fitting ones into an inspectable plan.

Right now the repo already has strong building blocks:
- bounded local context gathering
- differentiated roles
- typed outputs
- bounded rounds
- preserved disagreement
- decisive synthesis

But the operator vocabulary is still mostly implicit:
- use the right mode
- maybe increase rounds
- maybe ask for critique
- maybe ask for compare/contrast
- maybe ask for a tighter summary

The next quality jump is not “more agents.”
It is a visible solver layer between user prose and execution.

## Product guardrails

This work must preserve the repo’s narrow purpose.

Allowed:
- free prose that is compiled into a bounded software-work query
- explicit context policy controls
- explicit compare / critique / condense passes
- explicit final-output style controls
- a query-plan artifact that is inspectable in logs and reports

Not allowed:
- open-ended chatbot behavior
- hidden background branching
- arbitrary autonomous subagent swarms
- vague natural-language magic with no inspectable compiled plan
- features that sever the tool from the local work surface

## Design principles

1. Free prose should over-propose candidate operations before narrowing.
2. Surface phrases should normalize to canonical operations.
3. Multiple plausible operations may coexist until a solver scores them.
4. Compilation should be inspectable.
5. Illegal or contradictory combinations should fail explicitly or be down-ranked visibly.
6. The final execution plan should stay bounded.
7. Final output should preserve disagreement rather than laundering it away.

## Core model

Add a query compiler layer with four concepts:

### 1. Surface cues
Words, phrases, tone, and structural hints in user prose.

Examples:
- "what actually matters here"
- "give me multiple angles"
- "tighten this way down"
- "continue but first tell me what's left"
- "be adversarial"
- "keep this local to the diff"
- "compare options then pick"

The compiler should not require exact trigger words. It should infer candidate operations from natural language.

### 2. Canonical operations
Normalized internal meanings.

Examples:
- `intent` -> extract the durable governing objective
- `critique` -> add adversarial or failure-seeking analysis weight
- `compare` -> force multiple candidate paths and a tradeoff decision
- `condense` -> require a tighter operator-facing synthesis artifact
- `close` -> verify done / remaining / blocked / next
- `fresh` -> run without using previous response continuation state
- `local` -> bias hard toward local work-surface evidence over broad speculation

The canonical layer is where ambiguity gets collapsed. Surface phrasing can stay flexible.

### 3. Candidate operation set
Before final compilation, keep a scored set of candidate operations.

Suggested shape:

```python
@dataclass(frozen=True)
class CandidateOperation:
    canonical_op: str
    score: float
    evidence: list[str]
    rationale: str
    status: Literal["selected", "rejected", "uncertain"]
```

This is the solver seam.
The system should be biased toward proposing many diverse candidate operations, then selecting a bounded subset that actually improves the run.

### 4. Query plan
Compiled structured plan that execution can follow and logs can show.

Suggested shape:

```python
@dataclass(frozen=True)
class QueryPlan:
    mode: str
    objective_strategy: str
    context_policy: ContextPolicy
    role_plan: list[RoleInvocation]
    synthesis_policy: SynthesisPolicy
    final_artifacts: list[str]
    stop_policy: StopPolicy
    selected_ops: list[str]
    notes: list[str]
```

The important point is that this is explicit and inspectable, not hidden prompt massaging.

## Compilation pipeline

Use a visible staged pipeline:

1. Parse free prose into surface cues.
2. Over-generate a diverse candidate set of canonical operations.
3. Score candidates for relevance, compatibility, and boundedness.
4. Select a bounded subset.
5. Compile to a `QueryPlan`.
6. Show the user what was inferred and why.

This is closer to a solver than a fixed command parser.

## Recommended canonical operation families

### A. Objective operations
- `intent` — extract the durable strategic goal before deeper work
- `next` — bias to immediate next move
- `review` — bias to risk/correctness review
- `patch` — bias to minimal concrete edit path
- `close` — summarize done / remaining / blocked / next

### B. Context operations
- `local` — prioritize cwd, diff, nearby docs
- `pack` — show the context packet or include a packet summary artifact
- `fresh` — do not treat previous response state as authoritative
- `resume` — continue from prior artifact / prior summary if available
- `tail` — bias toward end-of-chat or latest-run state rather than whole-history recap

Important note:
`resume` should not mean “blindly continue the last thing.” It should compile to:
- inspect the latest artifact
- restate done / remaining / blocked
- then act

### C. Analysis operations
- `critique` — increase breaker weight or run explicit failure pass
- `minimal` — strengthen minimalist role and scope-cutting
- `branch` — request multiple candidate paths
- `compare` — compare named candidate paths and pick one
- `contrast` — seek differentiated failure profiles, not just parallel agreement
- `integrate` — merge outputs into one chosen path while preserving disagreements

Recommended distinction:
- `branch` = generate alternatives
- `compare` = evaluate alternatives
- `integrate` = converge to one operating path

### D. Output operations
- `condense` — short, readable operator summary
- `ledger` — preserve disagreements / assumptions / open questions explicitly
- `handoff` — generate a continuation-ready paragraph for a fresh agent
- `operator` — produce terse human-facing action report

Recommended artifact set when these are invoked:
- `report` — normal structured output
- `intent_card` — compact durable-goal note
- `handoff_paragraph` — continuation paragraph for another agent/session
- `operator_summary` — terse terminal-native summary

## Minimal starter canon

Start with a very small internal canon. Do not ship fifty magic words first.

Phase-1 canonical set:
- `intent`
- `next`
- `review`
- `patch`
- `close`
- `local`
- `resume`
- `fresh`
- `critique`
- `minimal`
- `branch`
- `compare`
- `integrate`
- `condense`
- `handoff`

Phase-1 surface-cue examples:
- "continue, but first tell me what remains" -> `resume close`
- "tighten this summary" -> `condense`
- "show me options and choose" -> `branch compare integrate`
- "be critical" -> `critique`
- "keep it small" -> `minimal`
- "what is the real goal here" -> `intent`
- "stay close to the diff" -> `local`

## Initial compiled patterns

These should exist as deterministic compile targets once candidate selection settles.

### Pattern 1: intent + compare + condense
Meaning:
- infer durable goal first
- produce at least two candidate paths
- compare tradeoffs
- end with concise operator summary

### Pattern 2: resume + close
Meaning:
- inspect latest artifact or prior summary
- restate done / remaining / blocked
- pick highest-leverage safe next step

### Pattern 3: review + critique + minimal
Meaning:
- adversarial review with explicit scope cutting
- do not propose ornamental rewrites

### Pattern 4: branch + compare + integrate
Meaning:
- create alternatives
- compare them cleanly
- collapse to one chosen path without hiding disagreement

## Implementation plan

### Task 1: Add canonical query-plan types

Objective: define an inspectable internal representation for compiled operator queries.

Files:
- Create: `src/moredakka/query_plan.py`
- Test: `tests/test_query_plan.py`

Add dataclasses for:
- `ContextPolicy`
- `RoleInvocation`
- `SynthesisPolicy`
- `StopPolicy`
- `CandidateOperation`
- `QueryPlan`

Requirements:
- serializable to dict for logs
- no hidden defaults that make runs hard to inspect
- enough fields to explain why a run behaved a certain way

### Task 2: Add deterministic free-prose inference and normalization

Objective: turn natural-language directive prose into scored canonical operations.

Files:
- Create: `src/moredakka/query_language.py`
- Test: `tests/test_query_language.py`

Behavior:
- extract surface cues from free prose safely
- infer a diverse candidate set of canonical operations
- score candidates with explicit evidence/rationale
- reject or down-rank contradictory pairs like `fresh resume` unless the meaning is explicitly defined
- compile the selected canonical operation list in stable order

Important rule:
Bias toward over-generation at the candidate stage, not at the execution stage. Many candidate ops may be considered; only a bounded subset may survive into the final plan.

### Task 3: Compile operations into query plans

Objective: map inferred canonical operations to concrete execution settings.

Files:
- Modify: `src/moredakka/query_language.py`
- Modify: `src/moredakka/roles.py`
- Modify: `src/moredakka/orchestrator.py`
- Test: `tests/test_query_language.py`
- Test: `tests/test_orchestrator.py`

Behavior:
- support baseline plans for existing modes
- allow inferred canonical operations to alter:
  - role ordering
  - role emphasis
  - whether comparison is required
  - whether status ledger is required
  - whether intent extraction artifact is required
  - final-summary style
- keep actual provider count bounded

Important rule:
Prefer changing obligations of the existing loop over adding new model calls.

### Task 4: Expose the compiler in CLI without breaking the narrow contract

Objective: make the feature usable without turning the CLI into vague prompt soup.

Files:
- Modify: `src/moredakka/cli.py`
- Modify: `README.md`
- Modify: `SPEC.md`
- Test: `tests/test_cli.py`

Recommended UX:
- add `--ask "free prose here"` or `--directive "free prose here"` to existing commands
- optionally keep `--ops` later as an expert/debug surface, not the primary interface

Strong preference:
Do not add a free-form `chat` command.
Use free-prose query overlays on the existing bounded commands.

Examples:
- `moredakka here --ask "what actually matters here; give me options and then tighten the answer"`
- `moredakka review --ask "be adversarial, keep it small, and tell me what's left"`
- `moredakka patch --ask "show me multiple patch shapes, compare them, then give me a clean handoff"`

### Task 5: Add compiled-plan visibility to reports and run artifacts

Objective: preserve inspectability and trust.

Files:
- Modify: `src/moredakka/report.py`
- Modify: `src/moredakka/runlog.py`
- Test: `tests/test_report.py`

Show:
- raw directive prose
- candidate operations with scores/evidence
- selected canonical operations
- compiled query plan summary
- any rejected or down-ranked operations

This is critical. Users should be able to see what their prose caused the compiler to infer.

### Task 6: Add phase-1 artifacts for handoff and concise closure

Objective: produce the specific high-value outputs the operator keeps wanting.

Files:
- Modify: `src/moredakka/schemas.py`
- Modify: `src/moredakka/report.py`
- Modify: `src/moredakka/orchestrator.py`
- Test: `tests/test_schemas.py`
- Test: `tests/test_report.py`

Add optional synthesis fields:
- `intent_card`
- `handoff_paragraph`
- `status_ledger`
- `operator_summary`

Rules:
- only require these when corresponding operations are active
- keep default report compact
- preserve terminal-native readability

## Prompt-layer changes

The compiler should shape prompt sections explicitly instead of relying on untracked prose heuristics.

Recommended additions to user prompt construction:
- `DIRECTIVE PROSE`
- `CANDIDATE OPERATIONS`
- `SELECTED OPERATIONS`
- `COMPILED PLAN`
- `FINAL ARTIFACT OBLIGATIONS`

Example insertion:

```text
DIRECTIVE PROSE
what actually matters here; give me options and then tighten the answer

CANDIDATE OPERATIONS
- intent (0.91) because the user is asking for the real goal
- branch (0.78) because the user asked for options
- compare (0.74) because the user wants options judged
- condense (0.88) because the user asked for a tighter answer

SELECTED OPERATIONS
intent branch compare condense

COMPILED PLAN
- Extract the durable objective before sequencing work.
- Produce at least two candidate paths with tradeoffs.
- Compare candidate paths and select one.
- End with a terse operator-facing summary.

FINAL ARTIFACT OBLIGATIONS
- intent_card
- operator_summary
```

This keeps the magic inspectable.

## Evaluation plan

Add focused eval prompts for the new layer.

Suggested checks:
- does prose like "continue, but first tell me what remains" infer `resume close` visibly?
- does prose like "review this brutally and keep it small" elevate risks and scope-cutting?
- does prose like "show me options and choose" produce at least two distinct candidate paths and then pick one?
- does prose like "what actually matters here" infer `intent`?
- does prose like "tighten this way down" materially shorten the operator summary without deleting the disagreement log?
- do contradictory inferred ops fail clearly or get down-ranked visibly?

Suggested prompt examples for eval corpus:
- "what actually matters here; give me options and tighten the answer"
- "review this diff brutally, keep it small, and tell me what's left"
- "continue from the last run, but first tell me what remains"
- "show me options and choose"

## Risks

### Risk 1: accidental broadening into general chat orchestration
Mitigation:
- keep compiler overlays attached to existing bounded commands
- keep local-context-first invariant
- refuse chatty free-form modes that bypass the work surface

### Risk 2: vocabulary sprawl
Mitigation:
- ship a tiny canonical set first
- allow broad surface phrasing but narrow internal canon
- keep docs opinionated

### Risk 3: hidden prompt magic
Mitigation:
- surface candidate ops, selected ops, and compiled plans in reports and run artifacts
- make prompt-layer obligations explicit

### Risk 4: role duplication instead of real contrast
Mitigation:
- use inferred operations to change obligations first
- only add extra calls when existing roles cannot express the needed distinction

## Acceptance criteria

This tranche is successful when:
- users can express common orchestration intent in natural language
- the tool shows exactly how that prose was compiled
- output quality improves for compare/contrast, closure, handoff, and concise summaries
- the repo still reads as a bounded software-work tool rather than a generic agent shell

## Recommended first cut

If only one thin slice is implemented first, do this:
1. add `--ask`
2. infer only `intent`, `critique`, `compare`, `condense`, `resume`, `close`, `minimal`
3. log candidate ops, selected ops, and compiled plan
4. add `operator_summary` and `status_ledger`
5. do not add new commands yet

That slice is enough to test whether the compiler actually sharpens cognition instead of just adding ceremony.
