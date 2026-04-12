# moredakka

Throw more tokens and more model diversity at planning.

`moredakka` snapshots the current workspace, fans out a planning prompt across
multiple strong models, then synthesizes the results back into a single
execution plan.

Default stack:
- repeated `gpt-5.4-pro` planning passes
- `gpt-5.4-codex` repo recon
- `gemini-3.1-pro-preview`
- `claude-sonnet-4.6` through OpenRouter when available
- `moonshotai/kimi-k2.5` through OpenRouter when available
- `x-ai/grok-4` in `--profile heavy`

## Layout

- `bin/moredakka`: Python CLI
- `.agents/skills/moredakka/SKILL.md`: repo-local skill entry

## Usage

```bash
bin/moredakka --dry-run "Figure out the best plan for this task"
bin/moredakka --profile heavy --iterations 2 --focus path/to/file "Implement X safely"
```

Artifacts are written under `.moredakka/runs/`.

## Requirements

- `codex` on `PATH` for the Codex recon pass
- `pi` on `PATH` for OpenAI, Gemini, OpenRouter-backed passes
- relevant API keys in your environment or local secrets files

