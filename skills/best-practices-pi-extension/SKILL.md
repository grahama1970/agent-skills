---
name: best-practices-pi-extension
description: >
  Singular alias and typo-tolerant entrypoint for best-practices-pi-extensions.
  Use when the human or an agent says best-practices-pi-extension, pi extension,
  Pi extension standard, lazy-report-shame-shame-shame, final-report guard, or asks
  to build/review Pi extension code under ~/.pi/agent/extensions or .pi/extensions.
triggers:
  - best-practices-pi-extension
  - best-practices-pi-extenstion
  - pi extension
  - pi extenstion
  - pi extension standard
  - lazy-report-shame-shame-shame
  - shame shame shame extension
  - final report guard extension
  - message_end guard
provides:
  - pi-extension-patterns
  - extension-validation
  - typo-compatible-routing
composes:
  - best-practices-pi-extensions
  - unlazy
  - agentic-evals
  - memory
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-security
  - typescript-code
taxonomy:
  - developer-tooling
  - validation
  - resilience
disciplines:
  - developer-tooling
  - engineering-standards
---

# best-practices-pi-extension

This is a compatibility alias for the singular invocation
`/best-practices-pi-extension`.

The canonical skill is:

```text
skills/best-practices-pi-extensions/SKILL.md
```

Use that canonical skill for the actual Pi extension standard.

## Required behavior

When this skill is selected, do not invent a second extension standard. Load and follow:

1. `skills/best-practices-pi-extensions/SKILL.md`
2. `skills/best-practices-pi-extensions/README.md`
3. `skills/best-practices-pi-extensions/PROJECT_KNOWLEDGE.md`
4. Pi extension docs under the installed Pi package
5. `github.com/nicobailon` extension repos as the implementation standard

## Why this alias exists

Agents should not fail because the human typed `extenstion` instead of `extension`.
The whole point of the Shame-Shame-Shame work is to reduce human babysitting, not add a
new spelling trap.

## Non-negotiable

If the task is a Pi extension, especially a guard like `lazy-report-shame-shame-shame`,
use deterministic checks, receipts, immutable goal boundaries, and the `nicobailon`
extension patterns before writing code.
