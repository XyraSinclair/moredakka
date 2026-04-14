# moredakka eval starter

This folder is a small starter pack for evaluating the `moredakka` skill or CLI behavior.

## What to test

### Triggering
Does the skill activate when it should, and avoid activating when it should not?

### Context quality
Does the packed local context actually include the right branch, diff, and docs?

### Output quality
Does the result include:
- a clear inferred objective
- at least one validation step
- at least one explicit risk
- a concrete next-action sequence

## Minimal workflow

For Codex skill evals, use a small prompt set first. Ten to twenty prompts is enough to catch obvious regressions.

Suggested loop:

1. Run the prompt against the skill explicitly.
2. Run the prompt again without naming the skill to test implicit activation.
3. Capture outputs and traces.
4. Score deterministic checks first.
5. Add rubric-based grading only where deterministic checks stop being enough.

## Example checks

- Did the output name the current branch or changed files?
- Did it include a selected path?
- Did it include at least one test?
- Did it include at least one risk?
- Did it avoid spawning a huge architecture rewrite for a small diff?

## Starter dataset

See `moredakka.prompts.csv`.
