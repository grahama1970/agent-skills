---
name: best-practices-port
description: >
  Best practices for porting features from one codebase, app, harness, TUI, API,
  or workflow into another without losing destination-specific behavior. Use
  when users ask to port, clone, migrate, replicate parity, achieve functional
  equivalence, borrow features, compare source vs destination, or preserve custom
  work while importing behavior from a reference implementation.
triggers:
  - port features
  - clone functionality
  - migrate from one codebase to another
  - achieve parity
  - functional equivalence
  - borrow from upstream
  - compare source and destination
  - preserve custom work
  - port TUI features
provides:
  - porting-discipline
  - parity-mapping
  - preservation-guard
  - migration-proof
composes:
  - memory
  - best-practices-skills
  - agentic-evals
complies:
  - best-practices-skills
taxonomy:
  - migration
  - validation
  - preservation
  - resilience
disciplines:
  - engineering-standards
  - developer-tooling
---

# Best Practices Port

Use this skill to turn a messy parity effort into bounded porting loops. The
goal is not to make the destination look like the source at all costs. The goal
is to make the destination satisfy the same user jobs while preserving the
destination's own architecture, integrations, data, and safety boundaries.

## Core Rule

Never start by copying files from the source. Start by proving what the source
feature does, what destination behavior must be preserved, and which user-visible
gap is being closed in this slice.

## Porting Loop

1. **Name the user job.**
   State the concrete workflow the human wants, such as "select a prior
   session from the TUI" or "see provider readiness before sending a prompt."

2. **Inventory the source feature from source code.**
   Record the exact source files, component names, commands, data contracts,
   keyboard bindings, and visible states. Do not rely on README claims alone.

3. **Inventory the destination feature and preservation boundaries.**
   Record the destination files and behaviors that must survive. Identify
   destination-only features explicitly, such as Memory-first routing, SciLLM,
   DAG receipts, approval gates, project trust, or local proof artifacts.

4. **Write or update a parity matrix.**
   Each row should include: source behavior, destination behavior, status
   (`matched`, `partial`, `missing`, `defer`, `destination-only`), next action,
   and proof needed. A parity matrix is a work queue, not proof.

5. **Choose one bounded slice.**
   Pick the highest-value missing behavior that can be implemented without
   rewiring unrelated systems. Prefer user-visible harness ergonomics over
   decorative equivalence.

6. **Patch through destination architecture.**
   Adapt the behavior into the destination's existing abstractions. Do not
   replace destination internals with source internals unless the human
   explicitly asks for a rewrite.

7. **Prove the slice at the right layer.**
   Use deterministic local checks for formatting and contracts, plus rendered UI,
   CLI, endpoint, or receipt artifacts when the slice is user-facing. Label
   mocked, fixture-backed, local-live, provider-live, and browser-live evidence
   separately.

8. **Update the matrix and commit only the slice.**
   Mark what changed and what remains. Stage only relevant files. Do not include
   unrelated dirty work from either repository.

## Required Artifacts

For any non-trivial port, leave these artifacts in the destination repo or a
documented proof directory:

- `parity matrix`: source feature map and destination status.
- `source inventory`: exact source files/components/commands inspected.
- `preservation list`: destination-specific features that must not be overwritten.
- `slice proof`: commands, rendered artifacts, receipts, screenshots, or endpoint
  responses that prove the chosen slice.
- `remaining gaps`: explicit rows that are still partial, missing, or deferred.

## Classification Rules

Use these labels consistently:

- `matched`: destination satisfies the same user job well enough for daily use.
- `partial`: destination has a related surface but an important affordance is
  missing.
- `missing`: destination lacks the user-visible behavior.
- `destination-only`: keep it even if the source has no equivalent.
- `defer`: intentionally not ported because it lacks a destination backend,
  violates destination architecture, or is not required for the active migration.

## Anti-Patterns

- Copying source files before writing the preservation list.
- Chasing every source detail instead of the next user job.
- Replacing a destination-specific subsystem with source assumptions.
- Treating unit tests as proof of visual, interactive, provider, or workflow
  parity.
- Declaring parity from a component name match without exercising the behavior.
- Building new dashboards around a missing behavior instead of porting the
  behavior.
- Expanding scope after each slice instead of updating the matrix and choosing
  the next row.

## Proof Language

Every status report for a porting slice must state:

```text
source inspected: <files/commands>
destination preserved: <features/files>
changed: <files>
mocked: yes|no
live: yes|no
provider_live: yes|no
proof: <commands/artifacts>
remaining gap: <next matrix row>
```

Do not say "parity achieved" unless every matrix row required by the human's
scope is `matched`, `destination-only`, or explicitly accepted as `defer`.

## Tau/Pi Harness Porting Notes

For Tau porting from Pi:

- Preserve Tau's Memory-first, SciLLM, DAG, receipt, approval, trust, workflow,
  and proof-index surfaces.
- Use Pi as the behavioral reference for TUI ergonomics, session operations,
  extension affordances, prompt editing, tool readability, and footer/status
  cues.
- Do not replace Tau's Python/Textual architecture with Pi's TypeScript runtime.
- Do not treat source-level resemblance as proof. A Tau slice needs a Tau proof:
  focused Python checks plus TUI render, CLI receipt, endpoint response, DAG
  receipt, or browser/CDP artifact as appropriate.
