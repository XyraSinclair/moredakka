---
name: moredakka
description: Use when you need a hard, bounded, multi-model improvement loop over the current software work surface. Best for prompts like "what should I do next here?", "review this branch brutally", "turn this diff into a minimal patch plan", or "give me the next 3 commits for this mess". Do not use for trivial one-file edits, non-software tasks, or broad research detached from the current working tree.
---

## What this skill is for

This skill turns the current local software task into a disciplined multi-role analysis loop.

It should stay glued to the current work surface:
- current directory
- git branch
- changed files
- diff
- nearby docs like `README.md`, `AGENTS.md`, `PLAN.md`, `TODO.md`, `SPEC.md`
- repo-local skill manifests if relevant

Then it should apply a bounded role loop:
- planner
- implementer
- breaker
- minimalist
- synthesizer

The output must be an operating report, not a brainstorm.

## When to use it

Use this skill when the user is effectively asking for one of these:

- tell me what I am actually working on and what to do next
- review the current branch or diff hard
- turn a messy work surface into a plan of operations
- extract a minimal patch path
- get a stronger next-step sequence than one single model pass would give

## When not to use it

Do not use this skill when:

- the task is a trivial direct edit
- there is no meaningful local software context
- the user wants broad open-ended research rather than action on the current working tree
- the user needs actual patch application more than planning or review

## Required behavior

1. **Stay local first.**
   Read the current work surface before making recommendations.

2. **Prefer diffs over file dumps.**
   The delta matters more than the entire repo.

3. **Use bounded loops.**
   Usually 2 rounds is enough. Stop when novelty collapses.

4. **Assign distinct roles.**
   Do not ask every model the same thing.

5. **Use typed outputs.**
   Preserve clear fields: problems, actions, tests, risks, edits, commit plan, disagreements.

6. **Emit one recommended path.**
   The user should get a concrete next move.

## If the CLI is installed

Run the CLI from the repo root or current module root:

```bash
moredakka here
moredakka plan --objective "<objective>"
moredakka review --base-ref main
moredakka patch --objective "<objective>"
moredakka loop --rounds 3
```

If you want the raw local context packet:

```bash
moredakka pack --mode plan
```

If you want saved reports:

```bash
moredakka review --base-ref main --write-prefix .moredakka/latest
```

If you are in the source repo and have not installed the package yet, the repo-local wrapper works too:

```bash
bin/moredakka here
```

## If the CLI is not installed

Emulate the same contract manually:

1. Inspect current branch, status, recent commits, and working diff.
2. Read nearby docs.
3. Infer the immediate objective.
4. Run the equivalent role loop in a bounded way.
5. Return the same report sections the CLI would produce.

## Report contract

Your final report should contain these sections:

- inferred objective
- one-line take
- selected path
- top problems
- next actions
- commit plan
- tests
- edit targets
- major risks
- disagreements
- stop conditions
- open questions
- confidence

## Quality bar

The report must be:

- operational
- falsifiable
- tied to files and commands when possible
- explicit about uncertainty
- minimal enough to act on now

Read `references/moredakka-contract.md` if you need a compact contract summary.
