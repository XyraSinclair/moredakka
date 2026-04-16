# moredakka spec

## Purpose

`moredakka` exists to increase the amount of disciplined cognition applied to the user’s current problem without requiring them to manually restage the same context for multiple models.

The CLI should feel like this:

> “Take what I am already working on, inspect it ruthlessly, and give me the best next operating sequence you can justify.”

## Non-goals

- Not a general chat wrapper.
- Not an unbounded model swarm.
- Not hidden autonomy masquerading as structure.
- Not a repo-wide search engine.
- Not a replacement for domain-specific safety controls, verification, or execution discipline.

## Core invariants

1. **Context is local before it is broad.** Start with the current problem surface and nearby evidence.
2. **Each model call has a distinct job.** No duplicate vague prompts across providers.
3. **All outputs are typed.** Every role returns strict JSON.
4. **The loop is bounded.** Default 2 rounds. Hard stop on low novelty.
5. **Deltas beat dumps.** Prioritize the most decision-relevant local change or evidence first.
6. **Disagreement is preserved.** Do not over-smooth conflicting views away.
7. **Synthesis must collapse to one recommended path.** The user gets a move, not a committee transcript.

## Commands

### `moredakka here`

Fast default entrypoint. Equivalent to `plan` with inferred objective.

Use when:
- the user is already in a repo and wants “what next here?”
- the objective is implicit in the current work surface
- the user wants to steer the run with free directive prose via `--ask`, which the compiler should translate into bounded canonical operations

### `moredakka plan`

Return a plan-of-operations for the current work.

Bias:
- sequencing
- blockers
- acceptance criteria
- next 3 commits

### `moredakka review`

Review current branch against a base ref.

Bias:
- correctness
- regressions
- test gaps
- maintainability
- rollback and safety

### `moredakka patch`

Same engine, but synthesis emphasizes concrete file edits and a minimal patch plan.

### `moredakka loop`

Run more than one critique cycle. Default still bounded.

### `moredakka pack`

Print only the context packet. Useful for debugging context quality and budget allocation.

## Context packet

The context packet is the entire leverage point. It should be compact, specific, and heavily biased toward the most decision-relevant local evidence.

Today the strongest built-in surface is repo/code work. That is an adapter choice, not the product ontology.

### Inputs

The engine should support multiple surface adapters over time. For the current repo/code adapter, inputs are:

- current working directory
- git root
- current branch
- git status
- changed files
- diff stats
- working-tree diff or branch-vs-base diff
- recent commits
- nearby docs:
  - `README.md`
  - `AGENTS.md`
  - `PLAN.md`
  - `TODO.md`
  - `SPEC.md`
  - `DESIGN.md`
  - repo skill manifests where relevant

### Selection rules

1. Changed files are highest priority.
2. Root and local docs outrank distant docs.
3. New and untracked files get a short excerpt if there is no meaningful diff yet.
4. Binary files are not inlined.
5. Total context is char-budgeted and truncated in the middle where needed.

### Default char budget split

- 15% repo summary and metadata
- 45% diff
- 20% nearby docs
- 20% new-file excerpts and notes

## Roles

### Planner

Job:
- infer the real immediate objective
- sequence work
- identify dependencies and ordering mistakes

### Implementer

Job:
- turn the situation into concrete actions
- propose the smallest viable move that materially advances the objective
- name domain-specific artifacts, files, commands, or other levers only when the current surface supports them

### Breaker

Job:
- find hidden failure modes
- identify correctness, security, or operational risks
- stress assumptions

### Minimalist

Job:
- remove speculative work
- cut scope to the smallest safe move
- reject ornamental complexity

### Synthesizer

Job:
- merge the above into one path
- preserve disagreements
- return the final operating report

## Loop

### Round 1

Independent role analyses over the same context packet.

### Round 2+

Each role sees:
- context packet
- prior role outputs
- latest aggregate summary

It returns a full schema again, but should only change conclusions that actually moved.

### Stop conditions

Stop when any of the following occur:

- `rounds == max_rounds`
- novelty falls below threshold
- all major risks are stable across successive rounds
- commit plan converges
- total-token budget is exceeded
- cost budget is exceeded
- wall-clock budget is exceeded

### Novelty heuristic

The current implementation computes novelty from normalized titles of problems, steps, risks, tests, and commit summaries. If the latest round adds less than the configured fraction of new salient items, stop.

## Output schema

The current concrete schema is still software-heavy and will be generalized in follow-on tranches. The stable requirement is that synthesis produces a typed chosen path, top problems, next actions, risks, disagreements, stop conditions, and confidence, with domain-specific artifacts included when relevant.

The synthesis report must produce:

- `inferred_objective`
- `one_sentence_take`
- `selected_path`
- `top_problems`
- `next_actions`
- `commit_plan`
- `tests`
- `edit_targets`
- `major_risks`
- `disagreements`
- `stop_conditions`
- `open_questions`
- `confidence`
- `confidence_rationale`

Optional synthesis artifacts may also be attached when the compiled plan requires them:
- `operator_summary`
- `status_ledger`
- `intent_card`
- `handoff_paragraph`

The final user-visible report should also surface invocation provenance:
- invocation id
- run artifact path
- stop reason
- query compilation summary:
  - directive prose
  - candidate operations
  - selected operations
  - compiled plan
- usage / cost summary
- context rendering / truncation summary

## Why this architecture

This design is grounded in a few current platform realities:

- OpenAI’s Responses API supports structured outputs via JSON schema, can preserve reasoning across turns with `previous_response_id`, and explicitly recommends preserving assistant `phase` for long-running or tool-heavy GPT-5.4 workflows. That makes multi-round orchestration materially cleaner than naive chat-completions loops.
- OpenAI’s current skills format is a `SKILL.md` manifest plus optional scripts and references, with progressive disclosure based on `name` and `description`.
- Codex subagents are explicitly framed as specialized agents running in parallel for complex, highly parallel tasks, which is exactly the pattern this tool compresses into a local CLI.
- OpenRouter exposes live model metadata including `supported_parameters`, which lets the tool validate structured-output and reasoning compatibility before sending a request. That makes a mixed-model OpenRouter roster viable without relying on stale assumptions.
- A strong default roster should use genuine contrast models for different failure profiles rather than five copies of one model wearing different prompts.

## Reliability rules

- Never pretend the inferred objective is certain.
- Always separate:
  - facts from local context
  - model inference
  - unresolved ambiguity
- Prefer a reversible move over a sweeping one.
- Every report should contain at least one explicit validation step.
- Every report should contain at least one explicit “do not do this yet” line when appropriate.
- Every orchestration invocation should leave behind a durable run artifact with prompts, responses, usage, and stop reason.

## Quality bar

The tool should feel useful even when it is wrong.

That means the report must still be:

- well-structured
- inspectable
- falsifiable
- tied to files and commands
- explicit about uncertainty

## Extension points

Planned but not required for the first serious version:

- patch application mode
- branch creation for proposed paths
- CI signal ingestion
- issue / PR / incident context plugins
- external grader integration
- provider adapters for additional models beyond the current OpenAI, Gemini, and OpenRouter set
