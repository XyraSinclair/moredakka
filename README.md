# moredakka

`moredakka` is a CLI for one specific job:

take the current working surface of a software task, build a tight context packet, run a bounded multi-model loop with differentiated roles, and return a disciplined next move instead of a pile of vibes.

It is deliberately narrower than an open-ended coding agent. It does not try to become your IDE, your issue tracker, or your CI system. It does one thing: it sharpens what to do next on the work already under your hands.

## What it does

- Inspects the local work surface:
  - current repo root and working directory
  - branch, status, recent commits
  - working-tree diff or branch-vs-base diff
  - nearby docs such as `README.md`, `AGENTS.md`, `PLAN.md`, `TODO.md`, `SPEC.md`
- Builds a bounded context packet instead of dumping the whole repo into every model call.
- Fans out to specialized roles rather than asking every model the same generic question.
- Runs 1 to N bounded rounds, with optional cross-critique.
- Synthesizes a single operating recommendation with:
  - top problems
  - next actions
  - suggested commit plan
  - edit targets
  - tests
  - risks
  - disagreement log
- Caches identical calls locally so repeated inspection is cheaper.
- Writes one durable run artifact per invocation with provenance, prompts, responses, usage, and stop reason.

## Default model roster

The canonical roster is OpenRouter-backed, fresh-model-first, and intentionally lean:

- Planner → Claude Opus 4.6 via OpenRouter
- Implementer → OpenAI GPT-5.4 via OpenRouter
- Breaker → Gemini 3.1 Pro Preview via OpenRouter
- Minimalist → OpenAI GPT-5.4 Mini via OpenRouter
- Synthesizer → OpenAI GPT-5.4 via OpenRouter

The point is not to cosplay diversity with five copies of one model. The point is to keep the workflow lean, use fresh models, spend bounded tokens on distinct failure profiles, and still collapse to one coherent final recommendation.

## Commands

```bash
moredakka doctor
moredakka here
moredakka plan --objective "stabilize auth refresh and reduce deploy risk"
moredakka review --base-ref main
moredakka patch --objective "turn this diff into a minimal safe patch plan"
moredakka loop --rounds 3
moredakka pack --base-ref main
```

`moredakka here` is the fast smoke-test path. It defaults to one round unless you pass `--rounds`, which keeps the default invocation practical without changing the deeper planning modes.

## Quick start

Requires Python 3.11+.

The canonical source-tree path is the repo-local wrapper. It prefers `python3.12`, then `python3.11`, and fails clearly if no supported interpreter is available. Repo-local `.env` files are loaded automatically from the current directory upward without overriding already-exported variables.

```bash
cat > .env <<'EOF'
OPENROUTER_API_KEY=***
EOF

bin/moredakka doctor
bin/moredakka here
```

If you want an editable install for development:

```bash
python3.11 -m pip install -e .
python3.11 -m moredakka doctor
python3.11 -m moredakka here
```

If you want the direct Gemini provider path in addition to the default OpenRouter path:

```bash
python3.11 -m pip install -e '.[gemini]'
```

## Compact Rust sidecar

There is now a compact Rust sidecar for the deterministic local-work-surface path:

```bash
cargo run -p moredakka-core -- doctor
cargo run -p moredakka-core -- pack --mode plan
```

The Rust crate is intentionally narrow for now:
- `doctor`
- `pack`

Python remains the canonical orchestration surface for `here`, `plan`, `review`, `patch`, and `loop`.

The current foundational completeness seam is:
- Rust owns the compact deterministic local-surface sidecar (`doctor`, `pack`)
- Python still owns provider orchestration
- each orchestration run now emits a durable run artifact under `.moredakka/runs/`

## Development

```bash
python3.11 -m pip install -e '.[dev]'
python3.11 -m pytest -q
```

The tests are configured to run directly from a fresh checkout without requiring
manual `PYTHONPATH=src` setup.

## Configuration

Copy the example config and edit as needed:

```bash
cp moredakka.toml.example moredakka.toml
```

Config lets you change:

- provider models
- API key env vars
- role-to-provider mapping
- round count
- char budgets
- base ref
- cache directory
- run artifact directory
- optional hard bounds for total tokens, cost, and wall time
- optional per-provider price hints for local cost estimation

Example contrast-role override:

```toml
[providers.openrouter_breaker]
kind = "openrouter"
model = "google/gemini-2.5-pro"
api_key_env = "OPENROUTER_API_KEY"
base_url = "https://openrouter.ai/api/v1"
app_name = "moredakka"

[roles.breaker]
provider = "openrouter_breaker"
```

`moredakka` checks OpenRouter's live model metadata before sending requests. If a selected model does not advertise structured outputs, or if you configure reasoning for a model that does not advertise reasoning support, it fails explicitly instead of silently sending an illegal parameter set.

## Output contract

Every non-`pack` command returns a unified report with:

- invocation id and run artifact path
- inferred objective
- top problems
- selected path
- next actions
- commit plan
- test plan
- edit targets
- major risks
- disagreements
- stop conditions
- confidence
- usage/cost summary
- context rendering/truncation summary

## Philosophy

`moredakka` is not “AI orchestration” as pageantry.

It is a bounded operational primitive:

1. stay glued to the local work surface
2. assign distinct jobs to distinct models
3. force typed outputs
4. make disagreement explicit
5. stop when novelty collapses
6. emit actions, not atmosphere

## Layout

```text
.
├── .agents/skills/moredakka/
│   ├── SKILL.md
│   └── references/
├── evals/
├── src/moredakka/
│   ├── prompts/
│   └── providers/
├── tests/
├── SPEC.md
└── moredakka.toml.example
```

## Status

This repo is an MVP with serious architecture rather than a toy. It includes:

- a real CLI
- repo context gathering
- structured multi-role orchestration
- provider adapters for OpenAI, Gemini, and OpenRouter
- a Codex-compatible skill
- an eval starter pack
- unit tests for non-network logic

It does not yet apply code patches automatically. It emits the patch plan, edit targets, and commit plan first.
