# best-practices-pi-extensions

Pi extensions are where agent behavior becomes mechanical instead of aspirational.

This skill exists because prose rules were not enough. An agent can read “do not claim progress without proof,” then still write “committed and pushed, done” while the actual artifact is broken, untested, or not even the requested thing. Humans then become the quality gate for basic instruction-following.

`lazy-report-shame-shame-shame` is the memorable example: a serious final-report rejection guard wrapped in a joke. The joke is the shame bell. The point is stopping fake progress reports before they land as the final answer.

## Why this skill is necessary

Agentic engineering fails in a repeatable way:

1. The human gives a concrete instruction.
2. The agent substitutes an adjacent task that is easier to satisfy.
3. The agent reports tool success, Git metadata, or unit tests as if they were user-visible progress.
4. The human notices the artifact still does not meet the goal.
5. The agent apologizes, tweaks something else, and repeats the loop.

A Pi extension can break that loop because it runs outside the model’s self-assessment. It can reject the answer after generation, replace it with a visible failure notice, and force another model turn with the exact unmet gates.

## The Shame-Shame-Shame pattern

Use this pattern when a failure mode is too costly to trust to reminders:

- deterministic checker decides pass/fail;
- `message_end` intercepts the assistant’s final prose;
- rejected output is replaced, not merely warned about;
- retry is queued with `pi.sendUserMessage(..., { deliverAs: "followUp" })`;
- every retry must satisfy the same checker;
- the report must compare against an immutable `$goal-drift` goal.

The extension should be funny enough that engineers remember it and serious enough that agents cannot bypass it.

## What counts as progress

Progress is a verified change in the user-visible or project-visible artifact.

Not progress by itself:

- `Committed and pushed`
- branch names or SHAs
- hook status
- unit tests over code the agent just wrote
- “mostly done”
- “remaining gates”
- “needs follow-up”

A valid report leads with the actual change and proof boundary:

```text
Progress:
- VERIFIED: The extension rejected a commit-only final answer and forced a retry.
MET: 1
UNMET: 0
ABANDONED: 0
Immutable Goal: ACHIEVED_WITH_RECEIPT:/path/to/receipt.json
goal_hash: sha256:<goal-drift-hash>
```

## Required proof boundary

Every claim must say what command or artifact proved it. If the extension plays audio, the receipt must name:

- source audio path;
- voice source and reference identity;
- timing contract;
- output path;
- hash;
- playback command result;
- what remains subjective or unproven.

## Relationship to `lazy-report-shame-shame-shame`

`lazy-report-shame-shame-shame` is local machine state under:

```text
~/.pi/agent/extensions/lazy-report-shame-shame-shame/
```

This skill is the reusable engineering rulebook for future Pi extensions, so the next agent does not reinvent the same guard badly.

## Compliance

This skill follows:

- `$best-practices-skills` for frontmatter, triggers, `provides`, `composes`, and `complies` metadata;
- `$best-practices-python` by avoiding Python runtime code in the skill itself; any future Python helper must use Typer, pathlib, httpx, validation, and non-mocked sanity checks;
- `$project-knowledge` by maintaining `PROJECT_KNOWLEDGE.md` beside the skill.
