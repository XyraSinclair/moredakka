# Premium Hardening Tranche 1

> For Hermes: execute this plan with small reversible diffs. Keep the product narrow.

Goal: raise `moredakka` from serious MVP to premium-feeling bootstrap and trust surface without broadening scope.

Architecture: keep the existing context-packet + differentiated-role design intact. Improve the edges first: environment diagnosis, repo governance, and first-run clarity. Do not expand into patch-application or autonomous-agent scope in this tranche.

Tech stack: Python 3.11+, argparse CLI, mocked unit tests, markdown docs.

---

## Why this tranche exists

The repo already has a coherent core:
- bounded local context gathering
- differentiated roles
- structured outputs
- clear synthesis contract

The main gap is not concept. It is trust.

A premium user experience here means:
- the tool tells you exactly why it can or cannot run
- repo operating intent is explicit
- the first-run path is short and legible
- docs do not oversell

## Priority order

1. Add `moredakka doctor`
2. Add root `AGENTS.md`
3. Tighten README around canonical bootstrap and doctor usage
4. Verify with focused tests and smoke runs

## Acceptance criteria

- `bin/moredakka doctor` exists and exits nonzero on blocking failures
- doctor checks python version, git availability, config loading, cache-dir writeability, and provider readiness
- provider readiness distinguishes active-role blockers from optional-provider warnings
- root `AGENTS.md` defines product intent, constraints, and quality bar
- README shows one canonical source-tree happy path and includes doctor
- focused unit tests cover doctor behavior and command wiring

## Task 1: Add doctor behavior

Objective: create a deterministic preflight command that explains bootstrap status.

Files:
- Create: `src/moredakka/doctor.py`
- Modify: `src/moredakka/cli.py`
- Test: `tests/test_doctor.py`

Implementation notes:
- doctor should be fast and non-destructive
- no network requirements
- output should be compact and actionable
- blocking issues are `fail`; optional misconfigurations are `warn`

Checks to include:
- python version
- git on PATH
- config load result
- cache dir write test
- provider SDK + env readiness for each configured provider

## Task 2: Add repo governance contract

Objective: make the repo publish its own operating rules.

Files:
- Create: `AGENTS.md`

Content requirements:
- narrow product intent
- architecture invariants
- quality bar
- bootstrap expectations
- documentation and testing rules
- anti-goals against feature creep and ornamental AI sprawl

## Task 3: Tighten README first-run path

Objective: make the happy path obvious.

Files:
- Modify: `README.md`

Changes:
- introduce `doctor` in the command list
- make source-tree wrapper the primary bootstrap path
- show one short setup sequence
- present install/editable mode as secondary
- mention that the wrapper prefers Python 3.11+ automatically

## Task 4: Verify

Objective: prove the tranche works.

Files:
- Test: `tests/test_cli.py`
- Test: `tests/test_doctor.py`
- Test: `tests/test_config.py`

Verification commands:
- `PYTHONPATH=src /opt/homebrew/bin/python3.11 -m unittest tests.test_doctor tests.test_cli tests.test_config tests.test_context tests.test_orchestrator`
- `PYTHONPATH=src /opt/homebrew/bin/python3.11 -m moredakka.cli doctor --format json`
- `bin/moredakka doctor`

## Out of scope for this tranche

Do not do these yet:
- patch application mode
- automatic graceful multi-provider runtime degradation in the main orchestration path
- benchmark corpus expansion beyond small targeted eval/docs updates
- new roles or larger swarm behavior

## Exit condition

This tranche is done when a fresh serious user can clone the repo, run one command, and understand whether the tool is ready, misconfigured, or blocked, with exact next steps.
