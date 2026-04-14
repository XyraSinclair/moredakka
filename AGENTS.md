# AGENTS.md

This repo builds `moredakka`, a bounded multi-model CLI for sharpening the next move on live software work.

## Product intent

`moredakka` is for this narrow job:
- inspect the current work surface
- build a tight local context packet
- run differentiated model roles
- emit one disciplined next move

It is not:
- an open-ended chat wrapper
- a general autonomous coding agent
- a repo-wide semantic search engine
- a CI replacement

Keep the product narrow. Resist feature creep that turns it into generic orchestration pageantry.

## Quality bar

A change is good only if it improves at least one of these without degrading the others:
- first-run trust
- recommendation quality
- operational clarity
- failure legibility
- boundedness

Premium here means:
- the bootstrap path is obvious
- failures are explicit and actionable
- output is typed, inspectable, and falsifiable
- small diffs do not trigger grandiose rewrites
- the tool stays glued to the local work surface

## Architecture constraints

Preserve these core invariants:
1. Context is local before broad.
2. Diffs beat file dumps.
3. Each role has a distinct job.
4. Outputs remain structured.
5. Synthesis collapses to one path.
6. Disagreement is preserved, not smoothed away.
7. The loop stays bounded.

Do not add hidden background behavior that makes runs harder to inspect.

## Implementation guidance

When changing behavior:
- prefer small, reversible edits
- keep file layout legible
- avoid speculative abstractions
- add or tighten tests for touched behavior
- update README.md, SPEC.md, or eval docs when user-facing behavior changes

When adding provider behavior:
- fail explicitly on illegal configuration
- avoid silent fallback that hides quality loss
- if degrading gracefully, make the downgrade visible in output

## Bootstrap and CLI UX

Treat first-run trust as a product surface.

Important expectations:
- `bin/moredakka` is the canonical source-tree entrypoint
- bootstrap failures should point to exact fixes
- `moredakka doctor` should stay fast, deterministic, and non-destructive
- docs should show one blessed happy path before listing optional variants

## Testing discipline

For code changes:
- write or extend focused tests near the touched behavior
- prefer deterministic unit tests over networked tests
- keep provider tests mocked
- preserve fresh-checkout behavior where possible

Useful local verification commands:
- `PYTHONPATH=src /opt/homebrew/bin/python3.11 -m unittest tests.test_cli tests.test_context tests.test_config tests.test_orchestrator tests.test_doctor`
- `bin/moredakka doctor`
- `bin/moredakka pack --mode plan`

## Docs and evals

If you change:
- CLI commands -> update README.md
- product contract -> update SPEC.md
- evaluation expectations -> update evals/README.md

Add docs for real behavior, not aspirational fluff.

## Anti-goals

Avoid:
- ornamental AI language
- giant architecture rewrites for small problems
- adding more roles without strong evidence
- hidden magic that makes outputs harder to trust
- broadening scope before bootstrap and quality are premium
