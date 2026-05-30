# Profound Simplification Plan

> For Hermes: keep behavior stable while deleting architectural fiction. Prefer removals and collapses over renames. Run focused tests after each task.

Goal: remove the abstractions that make `moredakka` feel bloated without losing current functionality.

Architecture:
- Make `ContextPacket` the only internal work-surface model.
- Make query compilation produce only data that actually changes runtime behavior.
- Normalize provider outputs and report inputs to one internal schema shape.
- Deduplicate OpenAI-Responses provider logic and repo/git helpers.

Tech stack: Python 3.11, unittest, argparse, dataclasses, existing OpenAI/Gemini/OpenRouter provider adapters.

Non-negotiable invariants:
- `bin/moredakka doctor` stays fast, deterministic, non-destructive.
- `pack` still emits the same user-facing payload keys unless intentionally changed in one explicit tranche.
- `here|plan|review|patch|loop` still preserve bounded rounds, typed outputs, disagreement preservation, and durable run artifacts.
- No silent provider downgrade.

Verification baseline before any edits:
- `bin/moredakka doctor`
- `PYTHONPATH=src /opt/homebrew/bin/python3.11 -m unittest discover -s tests -p 'test_*.py'`
- `cargo test -q`

---

## Target end-state

Module shape after simplification:
- `src/moredakka/context.py` — canonical context model and rendering
- `src/moredakka/query_language.py` — compile only selected ops / role names / artifacts / context signals
- `src/moredakka/orchestrator.py` — orchestration loop, slimmer than today
- `src/moredakka/report.py` — render one canonical synthesis shape
- `src/moredakka/repo.py` — shared git/repo helpers
- `src/moredakka/providers/responses_provider.py` — shared OpenAI/OpenRouter flow
- `src/moredakka/providers/openrouter_provider.py` — OpenRouter-specific capability checks/hooks only
- `src/moredakka/providers/openai_provider.py` — OpenAI-specific thin wrapper only
- `src/moredakka/doctor.py`
- `src/moredakka/runlog.py`
- `src/moredakka/cli.py`

Things that should likely disappear:
- `src/moredakka/problem_surface.py`
- `src/moredakka/surface_registry.py`
- `src/moredakka/surfaces/__init__.py`
- most of `src/moredakka/surfaces/repo.py`
- `StopPolicy`, `ContextPolicy`, `RoleInvocation`, `SynthesisPolicy`
- compatibility glue for multiple synthesis vocabularies living deep in runtime

---

## Tranche 1: Collapse fake multi-surface architecture

### Task 1: Freeze existing surface behavior with tests
Objective: make the current JSON/report contract explicit before deleting abstractions.

Files:
- Modify: `tests/test_cli.py`
- Modify: `tests/test_orchestrator.py`
- Modify: `tests/test_report.py`

Steps:
1. Add/extend tests that assert `pack` JSON still contains:
   - `context_packet`
   - `problem_surface`
   - `synthesis`
   - `rounds`
   - `providers`
2. Add/extend tests that assert orchestration can still render context and produce report output without directly depending on `ProblemSurface` semantics.
3. Run:
   - `PYTHONPATH=src /opt/homebrew/bin/python3.11 -m unittest tests.test_cli tests.test_orchestrator tests.test_report -v`
4. Commit.

### Task 2: Stop using `ProblemSurface` as an internal transport type
Objective: make `ContextPacket` the only internal work-surface object.

Files:
- Modify: `src/moredakka/orchestrator.py`
- Modify: `src/moredakka/report.py`
- Modify: `src/moredakka/runlog.py`
- Modify: `src/moredakka/cli.py`

Steps:
1. Replace internal `ContextPacket | ProblemSurface` unions with `ContextPacket` only.
2. Keep any `problem_surface` JSON output as a derived view created at the boundary.
3. Remove any runtime path that reconstructs `ContextPacket` from `ProblemSurface.metadata["context_packet"]`.
4. Run:
   - `PYTHONPATH=src /opt/homebrew/bin/python3.11 -m unittest tests.test_cli tests.test_orchestrator tests.test_report tests.test_runlog -v`
5. Commit.

### Task 3: Inline or delete repo-surface adapter scaffolding
Objective: remove the “multi-surface” framework while only one surface exists.

Files:
- Delete or gut: `src/moredakka/problem_surface.py`
- Delete: `src/moredakka/surface_registry.py`
- Delete: `src/moredakka/surfaces/__init__.py`
- Modify or delete: `src/moredakka/surfaces/repo.py`
- Modify: `src/moredakka/cli.py`
- Modify: `src/moredakka/orchestrator.py`
- Modify: `src/moredakka/config.py`
- Modify tests that reference the adapter layer

Steps:
1. Replace `resolve_surface_adapter(...)` calls with direct repo-context building.
2. If you must preserve `--surface repo`, validate it directly in CLI/config without a registry.
3. Delete `SurfaceAdapter` protocol and adapter package unless a second surface is actually landing now.
4. Run:
   - `PYTHONPATH=src /opt/homebrew/bin/python3.11 -m unittest tests.test_cli tests.test_config tests.test_context tests.test_orchestrator -v`
5. Commit.

Expected payoff:
- removes the worst bounce-cast in the repo
- eliminates a whole fake axis of abstraction

---

## Tranche 2: Flatten query-plan complexity to runtime truth

### Task 4: Replace `QueryPlan` with a minimal runtime plan
Objective: keep only fields that change execution or visible output.

Files:
- Modify: `src/moredakka/query_plan.py`
- Modify: `src/moredakka/query_language.py`
- Modify: `src/moredakka/orchestrator.py`
- Modify: `tests/test_query_language.py`
- Modify: `tests/test_orchestrator.py`

Target minimal shape:
```python
@dataclass(frozen=True)
class QueryPlan:
    mode: str
    directive: str
    objective_strategy: str
    selected_ops: list[str]
    role_names: list[str]
    final_artifacts: list[str]
    context_signals: list[str]
    notes: list[str] = field(default_factory=list)
```

Steps:
1. Delete `ContextPolicy`, `RoleInvocation`, `SynthesisPolicy`, `StopPolicy`.
2. Replace `_role_plan(...)` with direct `role_names` computation.
3. Update orchestrator to use `query_plan.role_names` directly instead of extracting `item.role_name`.
4. Keep `selected_ops`, `final_artifacts`, and `context_signals` because they affect prompts/reports.
5. Run:
   - `PYTHONPATH=src /opt/homebrew/bin/python3.11 -m unittest tests.test_query_language tests.test_orchestrator -v`
6. Commit.

### Task 5: Delete decorative query-compiler behavior that never reaches prompts
Objective: remove scoring/metadata branches that do not affect execution.

Files:
- Modify: `src/moredakka/query_language.py`
- Modify: `tests/test_query_language.py`

Steps:
1. Audit each computed field in `query_language.py` and keep only values used by:
   - prompt construction
   - role selection
   - final artifact obligations
   - user-visible query-compilation output
2. Delete `render_candidate_operations(...)` if still unused.
3. Remove any unused `mode` parameter plumbing such as `_role_plan(mode, ...)` if no longer needed.
4. Run:
   - `PYTHONPATH=src /opt/homebrew/bin/python3.11 -m unittest tests.test_query_language -v`
5. Commit.

Expected payoff:
- query compiler becomes a sharp front-end instead of a mini policy engine

---

## Tranche 3: Normalize internal synthesis schema

### Task 6: Pick one canonical synthesis vocabulary
Objective: stop carrying dual output vocabularies through the runtime.

Files:
- Modify: `src/moredakka/schemas.py`
- Modify: `src/moredakka/orchestrator.py`
- Modify: `src/moredakka/report.py`
- Modify: `tests/test_schemas.py`
- Modify: `tests/test_report.py`
- Modify: `tests/test_orchestrator.py`

Canonical internal names:
- `next_actions`
- `tests`
- `commit_plan`
- `edit_targets`
- `major_risks`
- `disagreements`

Steps:
1. Normalize provider outputs into the canonical shape immediately after parsing.
2. Delete `_action_items()` and `_validation_items()` compatibility branching if possible.
3. Delete `_field_items()` / `_has_field()` style compatibility scanning in report rendering.
4. If `generic` schema profile must survive, translate at the schema boundary only.
5. Run:
   - `PYTHONPATH=src /opt/homebrew/bin/python3.11 -m unittest tests.test_schemas tests.test_report tests.test_orchestrator -v`
6. Commit.

Expected payoff:
- less compatibility glue
- simpler reports
- smaller schemas/orchestrator surface area

---

## Tranche 4: Deduplicate providers and repo helpers

### Task 7: Create shared Responses-API provider helper
Objective: merge duplicated OpenAI/OpenRouter code paths.

Files:
- Create: `src/moredakka/providers/responses_provider.py`
- Modify: `src/moredakka/providers/openai_provider.py`
- Modify: `src/moredakka/providers/openrouter_provider.py`
- Modify: `tests/test_provider_timeouts.py`
- Modify: `tests/test_providers_openrouter.py`

Shared flow to centralize:
- import `OpenAI`
- client construction
- request emission
- `output_text` extraction
- JSON parsing
- `ProviderResult` creation

Keep separate hooks for:
- OpenRouter supported-parameter fetch
- OpenRouter schema sanitization
- OpenRouter default headers
- OpenAI `previous_response_id`

Steps:
1. Extract the common Responses API call flow.
2. Make OpenAI/OpenRouter thin wrappers over the shared helper.
3. Preserve explicit failure text for unsupported structured outputs/reasoning.
4. Run:
   - `PYTHONPATH=src /opt/homebrew/bin/python3.11 -m unittest tests.test_provider_timeouts tests.test_providers_openrouter -v`
5. Commit.

### Task 8: Centralize git/repo helpers
Objective: remove triplicated `_git()` and shared repo metadata logic.

Files:
- Create: `src/moredakka/repo.py`
- Modify: `src/moredakka/context.py`
- Modify: `src/moredakka/doctor.py`
- Modify: `src/moredakka/runlog.py`
- Modify tests if needed

Suggested helpers:
```python
def git(args: list[str], cwd: Path) -> str | None: ...
def repo_root(cwd: Path) -> Path | None: ...
def branch(cwd: Path) -> str | None: ...
def head_sha(cwd: Path) -> str | None: ...
def merge_base(cwd: Path, base_ref: str) -> str | None: ...
```

Steps:
1. Replace local `_git()` helpers in three modules.
2. Keep behavior unchanged: empty-string-or-None handling must stay explicit.
3. Run:
   - `PYTHONPATH=src /opt/homebrew/bin/python3.11 -m unittest tests.test_context tests.test_doctor tests.test_runlog -v`
4. Commit.

Expected payoff:
- obvious reduction in duplication
- easier future bug fixes in repo inspection

---

## Tranche 5: Shrink the orchestrator after simplification, not before

### Task 9: Delete unused imports, dead helpers, and second-pass compile clutter
Objective: remove obvious residue after the earlier collapses.

Files:
- Modify: `src/moredakka/orchestrator.py`
- Modify: `tests/test_orchestrator.py`

Steps:
1. Remove unused imports like `build_context_packet` / `render_context_packet` if still unused.
2. Reassess whether the pre-context `compile_query_plan(...)` call is still necessary.
3. Inline tiny helpers whose only job was schema/surface compatibility.
4. Run:
   - `PYTHONPATH=src /opt/homebrew/bin/python3.11 -m unittest tests.test_orchestrator -v`
5. Commit.

### Task 10: Split the orchestrator only if it is still ugly after deletion
Objective: avoid cargo-cult file splitting.

Files:
- Modify or create only if still justified after Tasks 1-9

Rule:
- Do not split first.
- Split only once fake abstractions are gone and the remaining responsibilities are stable.

If still too large, extract only these:
- prompt builders
- cached provider execution / trace building
- run artifact assembly

Verification:
- `PYTHONPATH=src /opt/homebrew/bin/python3.11 -m unittest tests.test_orchestrator tests.test_runlog tests.test_report -v`

---

## Docs cleanup tranche

### Task 11: Make docs honest about the simplified architecture
Objective: update product docs to match the real code after simplification.

Files:
- Modify: `README.md`
- Modify: `SPEC.md`
- Modify: `AGENTS.md` only if architecture rules need changing
- Modify: `pyproject.toml` description if still stale
- Modify: `evals/README.md` if output contract changed

Steps:
1. Remove references to abstractions that no longer exist.
2. Keep the product narrow: bounded local problem-surface cognition, not generic orchestration theater.
3. If package description still says “live software work” after simplification, decide whether it should now say “live problems” or remain repo-heavy by intent.
4. Run:
   - `bin/moredakka doctor`
   - `bin/moredakka pack --mode plan`
5. Commit.

---

## Suggested commit sequence

1. `test: freeze surface/report contracts before simplification`
2. `refactor: collapse internal surface model to context packet`
3. `refactor: remove unused surface adapter scaffolding`
4. `refactor: flatten query plan to runtime fields`
5. `refactor: delete decorative query compiler metadata`
6. `refactor: normalize internal synthesis schema`
7. `refactor: share responses api provider flow`
8. `refactor: centralize repo inspection helpers`
9. `refactor: trim orchestrator after abstraction collapse`
10. `docs: align docs with simplified architecture`

---

## Success criteria

You succeeded if:
- tests still pass
- CLI behavior is materially unchanged
- `orchestrator.py` is smaller and less haunted
- there is only one internal work-surface model
- there is only one internal synthesis vocabulary
- OpenAI/OpenRouter duplication is mostly gone
- a newcomer can explain the runtime in one sentence:
  - build repo context -> compile selected ops -> run fixed roles -> synthesize -> render -> log

You failed if:
- you only moved code around
- you added more abstractions in the name of simplification
- you preserved dead future-proof seams “just in case”
- runtime behavior still depends on compatibility glue deep inside the core
