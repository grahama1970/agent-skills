## GOAL LOCK - read first, obey throughout
Work on ONLY the single current gate / goal stated in this request. You are
FORBIDDEN from drifting into easier, adjacent, or tangential work - no unrelated
refactors, renames, new tooling, extra features, unrequested tests, or broader
architecture - none of which close the stated gate. If the stated gate is
unclear, out of scope, or blocked, say so and stop; do NOT substitute a
different, easier problem to look productive.

## GOAL PROOF (machine-checkable - echo verbatim)
goal_hash: sha256:71eb0721c70622d86df28f5451d5d071f9d21570a8fc5c3b3257a5b565be4f89
current_milestone: row-10 annotation reducer smoke is exposed through npm test
top_blocker: skills/watch/ui/package.json has no test script for row-10 reducer replay semantics
blocker_evidence.command: npm --prefix skills/watch/ui test
required_live_proof: npm --prefix skills/watch/ui test exits 0 and exercises row-10 UNASSIGN_STOP hydration/reassignment semantics
allowed_paths: skills/watch/ui/package.json, skills/watch/ui/scripts/watchAnnotationSession.smoke.ts, skills/watch/ui/src/watchAnnotationSession.ts, skills/watch/ui/tests/**
forbidden_scope: skills/watch/ui/components/WatchReportView.tsx, skills/watch/scripts/**, skills/watch/docs/**, skills/watch/docs/architecture/generated/**, skills/watch/README.md, skills/watch/SKILL.md, PROJECT_KNOWLEDGE.md

Begin your answer with the line `goal_hash: <value>` echoing the value
above, then return exactly ONE TOP_BLOCKER, ONE next action, and ONE live
stop condition for THIS gate before any broader discussion. Work only within
allowed_paths; anything in forbidden_scope is rejected even if valuable.

## Research directive
Before answering, use your own web search to research current, authoritative
sources for this problem, and cite the source URLs you relied on. The bundle may
also include a "## Research context" section the project agent gathered via
brave-search; treat it as a starting point, not a limit.

## Output contract: CODE
Return a unified diff (diff --git / *** Begin Patch) or a single finished-file zip.
Scope: the one current gate and allowed files only. A roadmap, staged architecture,
status analysis, or prose-only plan does NOT satisfy this contract.

---

# Watch Row-10 CI Test Gate

## Immutable goal

Watch turns video into source-grounded, inspectable evidence: scene frames, transcripts, visual descriptions, scene tables, reports, and Memory-backed recall, without guessing beyond extracted evidence.

For annotation/YOLO work, the same immutable goal means Watch owns reviewed temporal evidence. Detector boxes, interpolation, Qdrant suggestions, and human labels must become durable, replayable evidence with explicit gaps and stop points. Tentative suggestions must not become truth.

## Current gate

Promote the existing row-10 annotation reducer smoke behavior into a package-level deterministic test command.

## One blocking defect

`skills/watch/ui/package.json` has no `test` script, so the row-10 sequence semantics are not runnable as a normal package/CI check.

Current failing evidence:

```bash
npm --prefix skills/watch/ui test
```

Current output:

```text
npm error Missing script: "test"
```

## Required behavior

Add the smallest code patch so this command passes:

```bash
npm --prefix skills/watch/ui test
```

The test command must exercise the existing row-10 reducer replay semantics:

```text
assign Marcus
→ hold/interpolate
→ UNASSIGN_STOP/offscreen marker
→ persist marker success
→ hydrate from persisted records
→ Marcus remains absent at and after the stop
→ explicit Willie reassignment starts a new held sequence
→ runtime-derived overlays are not persisted as canonical keyframes
```

## Allowed files / module boundary

Allowed paths:

```text
skills/watch/ui/package.json
skills/watch/ui/scripts/watchAnnotationSession.smoke.ts
skills/watch/ui/src/watchAnnotationSession.ts
skills/watch/ui/tests/**
```

Prefer the smallest patch. If the existing smoke file already contains the semantic checks, make it runnable via `npm test` rather than inventing a new framework.

## Forbidden adjacent scope

Do not modify:

```text
skills/watch/ui/components/WatchReportView.tsx
skills/watch/scripts/**
skills/watch/docs/**
Memory/Qdrant code
YOLO tracker code
streaming/source-session code
F-36 contracts
README/SKILL documentation
```

Do not add new UI, Qdrant, browser, or streaming features.

## Required live/local proof

The required proof after applying your patch is:

```bash
npm --prefix skills/watch/ui test
npm --prefix skills/watch/ui run typecheck
```

These are deterministic local checks. They do not prove live browser, Qdrant, Memory, or movie pipeline behavior.

## Stop condition

Return only a unified diff or finished-file replacement that makes the required proof commands pass. If this cannot be done inside the allowed path boundary, return:

```text
BLOCKED_CURRENT_GATE: <one concrete blocker>
```

## Research context

Brave Search was run before this submission as required by the WebGPT skill contract.

Query:

```text
TypeScript reducer event sourcing unassign stop persistence replay tests CI npm test
```

Relevant findings:

- TypeScript event-sourcing examples emphasize deterministic reducer replay into a read model from persisted events.
  Source: https://github.com/xolvio/typescript-event-sourcing
- Event sourcing guidance frames state reconstruction as replaying immutable state changes.
  Source: https://softwarepatternslexicon.com/ts/reactive-programming-patterns/event-sourcing/implementing-event-sourcing-in-typescript/
- Replay tests are used in CI to guard against non-deterministic workflow behavior.
  Source: https://www.bitovi.com/blog/replay-testing-to-avoid-non-determinism-in-temporal-workflows

Application to Watch: row-10 annotation semantics should be a reducer/replay test first. Browser screenshots and live UI checks are secondary.

## Browser oracle / WebGPT target

Resolved with `browser-oracle` from `skills/watch`:

```json
{
  "project": "watch",
  "tab_id": "837357102",
  "conversation_url": "https://chatgpt.com/g/g-p-6a3c1fa17b00819181834439378267b1-watch/c/6a453096-f1ac-83ea-b610-eb238c4a4177",
  "readiness": "ready"
}
```

Use this exact tab and URL. Do not create another tab.

## Current code context

`skills/watch/ui/package.json` currently has scripts:

```json
{
  "dev": "vite",
  "dev:api": "tsx watch server/index.ts",
  "dev:all": "concurrently \"vite\" \"tsx watch server/index.ts\"",
  "build": "vite build",
  "start": "node server/prod.js",
  "typecheck": "tsc --noEmit"
}
```

`skills/watch/ui/scripts/watchAnnotationSession.smoke.ts` already imports the reducer and asserts:

- active selected character remains stable after hydration;
- exact keyframe deletion affects only the selected character;
- offscreen marker stops runtime overlay after the marker;
- stale hydrated records are cleared;
- runtime interpolated overlays are non-editable and do not create persistence operations;
- row 10 persisted Marcus → offscreen stop → Willie reassignment replay remains correct;
- persisted offscreen marker success clears the persistence queue and becomes memory-backed.

The issue is packaging and CI visibility, not the need for a new architecture.


---

## GOAL LOCK - final check (this is the last instruction; it wins)
Before you send your answer, re-read the stated gate/goal above and verify EVERY
line of your response directly serves it. Delete anything that is a side-quest,
nice-to-have, or adjacent improvement. Do not expand scope. Return only what the
output contract requires. If you cannot make real progress on the stated gate,
return the contract's block/ruling instead of solving an easier, unrelated
problem.