---
name: verbosity-cleaner
description: Review and clean up needless verbosity in code, docs, status text, tests, and UI copy. Use when the user asks to tighten code, reduce cruft, make code more direct, address verbosity, or run a less-is-more cleanup pass after implementation.
triggers:
  - tighten code
  - reduce cruft
  - verbosity cleanup
  - make code more direct
  - less-is-more cleanup
  - clean up verbose tests
provides:
  - verbosity-review
  - verbosity-cleanup
  - test-economy-review
composes:
  - memory
  - agentic-evals
complies:
  - best-practices-skills
disciplines:
  - engineering-standards
  - content-creation
---

# Verbosity Cleaner

Use this skill for a focused cleanup pass that makes code and prose easier to scan without changing behavior.

This is not a minification or cleverness pass. Shorter is only better when it is still clearer and preserves behavior, error signals, cleanup semantics, useful invariants, and local style.

## What to look for

Prioritize issues that are clearly visible in the requested scope or recent diff:

- single-use helpers that merely paraphrase an expression or make the call site less direct
- temporary variables that only name an obvious expression
- nested returns or branches that can become one direct return without hiding intent
- multi-line `try` / cleanup scaffolding that can use the local direct pattern while still guaranteeing cleanup
- pass-through wrappers that add no validation, normalization, metrics, boundary crossing, or API adaptation
- repeated boilerplate that can use an existing local helper or fixture
- comments that restate nearby code, narrate obvious steps, use placeholder TODOs, or no longer match behavior
- docs, status text, notifications, and UI copy that say the same thing in too many words or sound generic instead of concrete
- decorative emojis, unnecessary Start Case, or copy that visibly clashes with the surrounding product voice
- defensive checks after a trusted parser/type boundary when the local code already guarantees the shape
- tests added at multiple layers for the same behavior, especially async/process/e2e tests duplicating cheaper parser, helper, or executor coverage
- wrapper tests that only reprove a lower-level helper regression without adding a distinct user-visible guarantee

## What to preserve

Do not remove code just because it is long. Preserve:

- error context and `cause` chains
- cleanup and cancellation semantics
- type narrowing at real trust boundaries
- comments that explain non-obvious constraints, invariants, or product decisions
- explicit branching when it is easier to debug than a compressed expression
- tests that document behavior, even if they are repetitive, unless a local fixture already exists and the cleanup is obvious
- test matrices, platform cases, migrations, and compatibility regressions where each case protects a distinct user-visible guarantee

## Concurrency and write mode

When running as part of a parallel review, a concurrent cleanup pass, or one of multiple reviewers, operate in review-only mode. Do not edit files. Return concise findings with file/line references and suggested changes.

Only edit files when the task is clearly a single-writer cleanup pass, or when the prompt explicitly says: “You have exclusive write access.” If write access is ambiguous, default to review-only.

## Test economy

When tests are touched, check for AI-style defensive test bloat. More tests are not automatically more confidence. Keep the smallest test set that protects distinct behavior.

- Keep one test per distinct behavior or risk unless another layer would fail for a meaningfully different reason.
- Prefer the cheapest layer that catches the bug: helper/unit before executor, executor before async/process, integration before e2e.
- Remove tests that only restate implementation mechanics already covered by a more direct test.
- Avoid async, browser, temp-dir, process-spawn, or broad-suite tests when a synchronous parser, helper, or executor test proves the behavior.
- Keep compatibility regressions only when they protect realistic previous behavior, not hypothetical invalid combinations.
- Preserve repetitive matrix, platform, migration, and regression tests when each row protects a distinct guarantee.

A good regression test is usually the smallest failing example at the layer where the bug lived. If a helper-level test proves the real break, delete adjacent wrapper tests unless they protect separate wiring, rendering, or user-visible behavior.

Before deleting a test, name the behavior claim it protects, map that claim to the cheapest test that catches it, and confirm another kept test still fails for the real regression. Then run the narrowed test file and the relevant suite.

## Procedure

1. Read the requested scope and nearby non-slop code before editing.
2. Identify verbosity with evidence: quote the expression, helper, branch, or prose that feels heavier than the behavior requires.
3. Ask whether deletion or inlining makes the code easier to scan without spreading complexity or losing behavior. If it does, the extra structure is probably not earning its place.
4. Keep validation at user input, IO, network, parsing, and third-party API boundaries. Remove defensive checks only after trusted internal boundaries.
5. Match the nearest strong non-slop local pattern, not verbose code that merely happens to be nearby.
6. Apply the smallest local edit that removes the verbosity. Prefer deletion, inlining, or direct returns over adding new helpers.
7. Avoid broad refactors, file moves, public API changes, or speculative abstractions.
8. Rerun the narrowest relevant validation after edits. If no validation exists, explain what you inspected instead.

## Good cleanups

A guaranteed cleanup can be concise:

```ts
const result = await runtime.waitForVirtualCompaction(timeoutMs).finally(() => {
  releaseHold();
  runtime.updateStatus(ctx, policy);
});
```

A direct conditional return can replace nested ceremony:

```ts
return messagesChanged ? { messages } : undefined;
```

A single-use helper can often be inlined when it only wraps an obvious loop or expression.

## Bad cleanups

Do not replace clear code with clever code:

- no nested ternaries just to save lines
- no comma operators or surprising expression tricks
- no swallowing errors to make a branch shorter
- no removing validation at JSON/file/network/user-input boundaries
- no merging unrelated cleanup into the pass

## Final response

If you changed anything, list only the meaningful fixes and end with:

`Fixed [N] issue(s). Ready for another review.`

If no changes were warranted, describe what you inspected and end with:

`No issues found.`
