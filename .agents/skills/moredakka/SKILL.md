---
name: moredakka
description: >-
  Throw a multi-model planning swarm at the current coding task. Uses repeated
  GPT-5.4-Pro passes plus Gemini 3.1, Codex, Claude, Kimi, and optional Grok
  to tighten the plan of operations before implementation. Use when the user
  asks for "more dakka", more tokens, more diverse models, or wants a stronger
  plan before coding.
---

# Moredakka

Use this skill when the user wants to brute-force better planning with more
model diversity instead of debating the plan manually.

## What it does

`bin/moredakka` snapshots the current workspace, fans out a planning prompt to
multiple top models, then runs one or more synthesis passes to produce a single
actionable plan.

Default stack:
- repeated `gpt-5.4-pro` planning passes
- `gpt-5.4-codex` repo recon
- `gemini-3.1-pro-preview`
- `claude-sonnet-4.6` through OpenRouter when available
- `moonshotai/kimi-k2.5` through OpenRouter when available
- `x-ai/grok-4` in `--profile heavy`

## How to use it

1. Summarize the current task in one sentence.
2. Pass any relevant paths with `--focus`.
3. Read the synthesized plan and use it to drive implementation.

Basic:

```bash
bin/moredakka "Implement X in the current repo"
```

Focused:

```bash
bin/moredakka \
  --focus path/to/file.py \
  --focus path/to/tests \
  "Figure out the best plan to implement X safely"
```

Cheaper / faster:

```bash
bin/moredakka --profile fast --iterations 1 "..."
```

Heavier:

```bash
bin/moredakka --profile heavy --iterations 2 "..."
```

Preview without spending tokens:

```bash
bin/moredakka --dry-run "..."
```

## Rules

- Use this before substantial implementation work, not after the code is already done.
- Give it the real task, not a vague "help me think".
- Add `--focus` paths when you already know the hot files.
- Treat the output as a planning artifact, not gospel. Execute the good parts.
- Artifacts are written under `.moredakka/runs/`.
