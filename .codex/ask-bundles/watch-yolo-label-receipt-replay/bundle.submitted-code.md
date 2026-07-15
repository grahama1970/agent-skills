## GOAL LOCK - read first, obey throughout
Work on ONLY the single current gate / goal stated in this request. You are
FORBIDDEN from drifting into easier, adjacent, or tangential work - no unrelated
refactors, renames, new tooling, extra features, unrequested tests, or broader
architecture - none of which close the stated gate. If the stated gate is
unclear, out of scope, or blocked, say so and stop; do NOT substitute a
different, easier problem to look productive.

## GOAL PROOF (machine-checkable - echo verbatim)
goal_hash: sha256:9ba5e72ad3171fccb56513f2ebf1f6aa6196c379b24e3f8f14514336544f1e7d
current_milestone: deterministic yolo-label receipt replay test covers accept, unassign stop, reload readback, and reassignment
top_blocker: no test exercises the /api/projects/watch/yolo-labels receipt persistence and reload semantics
blocker_evidence.command: npm --prefix skills/watch/ui run test:yolo-label-receipt
required_live_proof: test:yolo-label-receipt passes and the normal Watch UI test/typecheck still pass
allowed_paths: skills/watch/ui/package.json, skills/watch/ui/scripts/**, skills/watch/ui/server/**, skills/watch/ui/components/WatchReportView.tsx
forbidden_scope: skills/persona-dream/**, skills/battle/**, skills/ux-lab/**, agents/**, PROJECT_KNOWLEDGE.md, skills/watch/docs/**

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

# Watch WebGPT Code Gate: YOLO Label Receipt Replay

## Immutable Goal

Make `$watch` use YOLOAnalytics person boxes as the source regions, identify each box by querying `$memory`/Qdrant multimodal crop recall against human-labeled character crops, surface tentative labels with confidence, persist accepted/rejected labels, stop propagation on identity conflicts, and prove the row 9/10 Marcus/Willie flow end to end in the browser and backend.

## Current Gate

Add the missing deterministic receipt replay test for Watch YOLO labels.

The existing tests prove reducer/projection behavior but do **not** exercise the server receipt persistence boundary:

```text
POST /api/projects/watch/yolo-labels accept Marcus
→ GET /api/projects/watch/yolo-labels rehydrates Marcus
→ POST reject_box at 1.79s creates UNASSIGN_STOP
→ GET rehydrates the stop
→ POST accept Willie at 4.54s starts a new segment
→ GET rehydrates the new label and full event ledger
```

## One Blocking Defect

There is no `npm --prefix skills/watch/ui run test:yolo-label-receipt` command and no test that exercises `/api/projects/watch/yolo-labels` persistence and reload semantics.

The current command fails because the script is missing:

```bash
npm --prefix skills/watch/ui run test:yolo-label-receipt
```

## Research Context

Brave search for browser/UI persistence testing surfaced general guidance that persistence across reload should be tested explicitly, usually by writing state, reloading, and asserting state restoration. Relevant references from the search:

- Playwright/localStorage persistence article: https://faruk-hasan.com/blog_post/local_storage_testing_with_playwright.html
- Playwright test/debug docs: https://playwright.dev/docs/running-tests
- BrowserStack persistent-context overview: https://www.browserstack.com/guide/playwright-persistent-context

For this gate, repository evidence is stronger than the web search. Do not add Playwright unless it is already necessary. A deterministic server/receipt replay smoke is the next smallest useful proof and should not require broad browser automation.

## Current Relevant Code

Primary files:

- `skills/watch/ui/server/index.ts`
- `skills/watch/ui/components/WatchReportView.tsx`
- `skills/watch/ui/scripts/watchYoloSequenceProjection.smoke.ts`
- `skills/watch/ui/scripts/watchAnnotationSession.smoke.ts`
- `skills/watch/ui/package.json`

Important current behavior in `server/index.ts`:

- `WATCH_YOLO_LABEL_DIR` controls receipt storage.
- `GET /api/projects/watch/yolo-labels` reads or creates a default receipt.
- `POST /api/projects/watch/yolo-labels` writes a receipt and attempts Memory sync.
- `accept` stores `labels[trackId]` and appends an accepted event.
- `reject_box` / `reset_box` stores `box_rejections[boxKey]` and appends a rejected-box event.
- `reset` / `reject` deletes `labels[trackId]` and appends a reset/reject event.
- Memory sync failure should not prevent local receipt persistence.

Important current behavior in `WatchReportView.tsx`:

- `yoloLabelForOverlay(...)` uses event replay first.
- If a track has events but no prior event at the current time, no future legacy label may leak backward.
- A `reject_box` event is a stop/unassign point until a later accepted event.

Existing projection smoke:

```text
events:
  accept Marcus at 1.00s
  reject_box at 1.79s
  accept Willie at 4.54s

assertions:
  0.50s -> null
  1.20s -> Marcus
  2.02s -> null
  5.00s -> Willie
```

## Required Change

Add a deterministic test script and package script, preferably:

```text
skills/watch/ui/scripts/watchYoloLabelReceiptReplay.smoke.ts
package.json script: "test:yolo-label-receipt"
package.json "test" should include the new script
```

The test must:

1. Use a temporary `WATCH_YOLO_LABEL_DIR`.
2. Start or exercise the Watch API server in a way that does not depend on the developer's live row files.
3. Use real HTTP requests against `/api/projects/watch/yolo-labels` if practical. If the current server structure makes import/start hard, make the smallest server refactor needed to allow a local test instance without changing runtime behavior.
4. Make Memory unavailable intentionally or point `MEMORY_DAEMON_URL` at a closed local port, and assert local receipt persistence still succeeds while `memory_sync` reports failure.
5. POST accept Marcus at `time_seconds: 1`.
6. GET and assert Marcus accepted event is present.
7. POST `reject_box` at `time_seconds: 1.79` with a stable `box_key`.
8. GET and assert the rejection/stop event and `box_rejections` entry are present.
9. POST accept Willie at `time_seconds: 4.54`.
10. GET and assert event order is preserved and the final event is Willie.
11. Reuse `yoloLabelForOverlay` against the rehydrated events to assert:
    - before first event: `null`
    - after Marcus: `Marcus`
    - after stop before Willie: `null`
    - after reassignment: `Willie`
12. Clean up the temporary receipt directory.

## Allowed Files

Only change:

```text
skills/watch/ui/package.json
skills/watch/ui/scripts/**
skills/watch/ui/server/**
skills/watch/ui/components/WatchReportView.tsx
```

Avoid touching docs, project knowledge, unrelated skills, generated movie receipts, or architecture prose.

## Forbidden Adjacent Scope

Do not:

- redesign Watch UI;
- add F-36 schemas;
- modify persona-dream, battle, ux-lab, or agents;
- add broad architecture plans;
- add a fake Memory implementation as proof;
- treat mocked Memory sync as semantic proof of Qdrant recall;
- change production receipt semantics unless the test exposes a real defect.

## Required Live Proof After Patch

These commands must pass:

```bash
npm --prefix skills/watch/ui run test:yolo-label-receipt
npm --prefix skills/watch/ui test
npm --prefix skills/watch/ui run typecheck
```

Then the project agent will run browser-oracle/CDP against:

```text
http://localhost:3002/watch#watch?clipRow=10
```

to capture visible Watch route state. The screenshot is not the primary semantic proof; the receipt replay test is.

## Stop Condition

Return a unified diff or finished-file zip that implements only this gate. If the server cannot be tested without a larger refactor, return `BLOCKED_CURRENT_GATE:` with the one concrete blocker and the smallest refactor required.


---

## GOAL LOCK - final check (this is the last instruction; it wins)
Before you send your answer, re-read the stated gate/goal above and verify EVERY
line of your response directly serves it. Delete anything that is a side-quest,
nice-to-have, or adjacent improvement. Do not expand scope. Return only what the
output contract requires. If you cannot make real progress on the stated gate,
return the contract's block/ruling instead of solving an easier, unrelated
problem.