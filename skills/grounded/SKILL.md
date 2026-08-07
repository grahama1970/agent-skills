---
name: grounded
description: >
  Ground architecture recommendations in source evidence before advising. Use when a user asks
  for architecture recommendations, refactor options, system design critique, migration plans,
  cross-module tradeoffs, asks whether enough files have been read to understand the relevant
  architecture, or invokes /grounded. This skill prevents premature recommendations by requiring file-backed evidence,
  explicit architectural boundaries, confidence labels, and unknowns before final advice.
triggers:
  - grounded
  - /grounded
  - architecture recommendations
  - refactor options
  - system design critique
  - migration plan
  - have you read enough files
  - understand the relevant architecture
  - evidence-backed recommendation
  - architecture grounding
provides:
  - architecture-evidence-gate
  - recommendation-readiness
  - source-grounded-analysis
composes: []
taxonomy:
  - validation
  - architecture
  - precision
  - compliance
disciplines:
  - evaluation-quality
  - research-retrieval
---

# Grounded

## Overview

Use this skill to slow down architecture advice until the relevant system shape is
source-derived. The goal is not impossible certainty; the goal is to avoid confident
recommendations that are not anchored in files, call sites, tests, configuration, and
observed project boundaries.

## Grounding Workflow

1. Define the recommendation scope in one or two sentences.
   Include the specific user decision being supported and the architectural surfaces likely affected.

2. Build a reading map before recommending.
   Identify likely entry points, core modules, adapters, schemas, tests, configs, docs, and call sites.
   Use fast repository search first, then read the files that establish ownership and behavior.

3. Keep reading until each recommendation candidate has evidence.
   Stop only when the relevant boundaries, data flow, control flow, dependencies, and tests are either
   found or explicitly marked `not established`.

4. Produce an evidence map before final recommendations.
   For each architectural claim, cite the source files or commands that support it. Use retrieval
   language: `found`, `observed`, `not established`, `not found`.

5. Label confidence honestly.
   Use `established`, `probable`, or `unknown`. Do not use `100% confident`. If a claim depends on
   unread code, stale docs, missing tests, or inferred intent, label it `probable` or `unknown`.

6. Re-analyze after new evidence.
   If additional reading changes the architecture model, revise the recommendation options instead
   of defending the earlier answer.

## Readiness Gate

Before giving final recommendation options, classify the evidence state:

- `READY_TO_RECOMMEND`: Core surfaces, call paths, data models, configuration, tests, and
  known contradictions have been checked or marked not applicable. Each recommendation has
  file-backed evidence.
- `PARTIAL`: Enough evidence exists for scoped options, but exclusions or unknowns remain.
  Recommendations must name the limited scope and avoid claims beyond it.
- `NOT_READY`: Missing evidence could reverse the recommendation. Keep reading when files are
  available; otherwise report the missing evidence instead of recommending.

Treat missing entry points, data models, ownership boundaries, or call sites as `NOT_READY`
unless the user explicitly narrows the decision away from those surfaces.

## Minimum Evidence

Before giving architecture recommendations, establish or explicitly mark missing:

- Runtime entry points and user-facing workflows affected by the recommendation.
- Core domain objects, data models, schemas, or persisted state involved.
- Module boundaries, ownership boundaries, and public APIs.
- Call sites in both directions: who calls the target and what the target calls.
- Configuration, environment, dependency injection, build, and deployment assumptions.
- Tests, fixtures, golden files, or validation scripts covering the behavior.
- Existing docs or project knowledge that agree with or contradict the code.

## Stop Conditions

Stop reading and recommend only when:

- Each recommendation option has direct evidence from files, tests, configs, docs, or commands.
- Remaining unknowns are outside the user's decision scope and are listed under `Not established`.
- Additional likely files would refine details but would not change the chosen architecture direction.

Continue reading when:

- An unknown could reverse the recommendation.
- A claim relies on inferred intent instead of source evidence.
- A doc and implementation appear to disagree.
- Callers, callees, data models, or runtime entry points are still not established.

## Recommendation Format

Use this structure when the user wants options:

```text
Scope:
- <decision and affected surfaces>

Readiness:
- READY_TO_RECOMMEND|PARTIAL|NOT_READY

Evidence read:
- <file or command>: <what it established>

Not established:
- <unknown or excluded area>

Architecture model:
- <source-derived summary>

Options:
1. <option>
   Confidence: established|probable|unknown
   Evidence: <files/commands>
   Tradeoff: <practical consequence>
2. <option>
   Confidence: established|probable|unknown
   Evidence: <files/commands>
   Tradeoff: <practical consequence>

Recommendation:
- <preferred option and why>
```

## Fail Closed

If the evidence map is thin, do not invent a complete architecture. Say what is missing,
keep reading if the files are available, or downgrade the output to hypotheses. If the user
asks whether enough has been read, answer from the evidence map, not from intuition.
