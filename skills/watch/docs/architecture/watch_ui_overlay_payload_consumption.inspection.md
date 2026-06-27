# Watch UI Overlay Payload Consumption Inspection

Date: 2026-06-27

## Scope

This inspection records the first local UX Lab proof that a Watch clip modal can
render annotation geometry from a `watch.ui_overlay_payload.v1` payload instead
of a hard-coded modal bounding box.

This is not a live tracking proof. The payload is still `DRY_RUN_ONLY` and its
`proof_scope` is `geometry_plumbing`.

## Local implementation surface

- Repo: `/home/graham/workspace/experiments/pi-mono`
- Branch observed: `persona/tim-blazytko-1774553751276`
- File changed locally: `packages/ux-lab/src/components/watch/WatchReportView.tsx`
- Rendered route: `http://127.0.0.1:3002/#watch`

The app worktree already had broad unrelated edits in the same file. The scoped
Watch overlay consumption patch was therefore not committed from this inspection
pass, to avoid sweeping unrelated UI changes into a Watch tracking commit.

## Payload source

- Payload schema:
  `skills/watch/docs/architecture/watch_ui_overlay_payload.schema.json`
- Payload fixture:
  `skills/watch/docs/architecture/generated/bad_santa_marcus_0248_overlay_payload/watch_ui_overlay_payload.bad_santa_marcus.json`
- Payload producer:
  `skills/watch/scripts/build_tracking_overlay_payload.py`

Payload facts used by the local modal:

```json
{
  "schema_version": "watch.ui_overlay_payload.v1",
  "status": "DRY_RUN_ONLY",
  "proof_scope": ["geometry_plumbing"],
  "excluded_proofs": ["live_ml", "identity", "memory_write", "qdrant_write", "recall"],
  "overlay_id": "watch_overlay_movie_bad_santa_2003_unrated_seg_0007_track_07",
  "track_id": "track_07",
  "identity_candidate": "Marcus",
  "identity_status": "PROVISIONAL",
  "bbox_policy": "median_source_events"
}
```

## Positive UI proof

Command:

```bash
node - <<'NODE'
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1800, height: 1100 } });
  await page.goto('http://127.0.0.1:3002/#watch', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForSelector('[data-qid="watch:table:evidence-expand"]', { timeout: 15000 });
  const clicked = await page.evaluate(() => {
    const buttons = Array.from(document.querySelectorAll('[data-qid="watch:table:evidence-expand"]'));
    const target = buttons.find((button) => button.closest('tr')?.textContent?.includes('02:48'));
    if (!target) return false;
    (target instanceof HTMLElement ? target : null)?.click();
    return true;
  });
  await page.waitForTimeout(1000);
  const proof = await page.evaluate(() => {
    const modal = document.querySelector('[data-qid="watch:clip-modal"]');
    const overlays = Array.from(document.querySelectorAll('[data-qid="watch:clip-modal:event-overlay"]'));
    const labels = Array.from(document.querySelectorAll('[data-qid="watch:clip-modal:event-overlay-label"]')).map((el) => el.textContent?.trim());
    const contract = document.querySelector('[data-qid="watch:clip-modal:overlay-contract"]')?.textContent?.trim();
    return {
      modal: Boolean(modal),
      overlayCount: overlays.length,
      labels,
      contract,
      overlayData: overlays.map((el) => ({
        overlayId: el.getAttribute('data-overlay-id'),
        trackId: el.getAttribute('data-track-id'),
        identityStatus: el.getAttribute('data-identity-status')
      }))
    };
  });
  await page.screenshot({ path: '/tmp/watch-modal-event-overlay-proof.png', fullPage: false });
  console.log(JSON.stringify({ clicked, ...proof, screenshot: '/tmp/watch-modal-event-overlay-proof.png' }, null, 2));
  await browser.close();
})();
NODE
```

Observed output:

```json
{
  "clicked": true,
  "modal": true,
  "overlayCount": 1,
  "labels": ["MarcusTony CoxPROVISIONAL"],
  "contract": "DRY_RUN_ONLY geometry_plumbing overlay",
  "overlayData": [
    {
      "overlayId": "watch_overlay_movie_bad_santa_2003_unrated_seg_0007_track_07",
      "trackId": "track_07",
      "identityStatus": "PROVISIONAL"
    }
  ],
  "screenshot": "/tmp/watch-modal-event-overlay-proof.png"
}
```

## Negative UI proof

Command:

```bash
node - <<'NODE'
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1800, height: 1100 } });
  await page.goto('http://127.0.0.1:3002/#watch', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForSelector('[data-qid="watch:table:evidence-expand"]', { timeout: 15000 });
  const clicked = await page.evaluate(() => {
    const buttons = Array.from(document.querySelectorAll('[data-qid="watch:table:evidence-expand"]'));
    const target = buttons.find((button) => button.closest('tr')?.textContent?.includes('01:36'));
    if (!target) return false;
    (target instanceof HTMLElement ? target : null)?.click();
    return true;
  });
  await page.waitForTimeout(1000);
  const proof = await page.evaluate(() => {
    const overlays = Array.from(document.querySelectorAll('[data-qid="watch:clip-modal:event-overlay"]'));
    const contract = document.querySelector('[data-qid="watch:clip-modal:overlay-contract"]')?.textContent?.trim();
    return { overlayCount: overlays.length, contract };
  });
  console.log(JSON.stringify({ clicked, ...proof }, null, 2));
  await browser.close();
})();
NODE
```

Observed output:

```json
{
  "clicked": true,
  "overlayCount": 0,
  "contract": "Tracking overlay unavailable: no event-backed bbox for this segment"
}
```

## Static checks

Targeted lint:

```bash
npx eslint src/components/watch/WatchReportView.tsx
```

Result: exit code 0.

Full package build was also attempted:

```bash
npm run build
```

Result: exit code 2 from existing unrelated shared-chat/type errors across
`ChatFab`, `BinaryExplorer`, `DatalakeExplorer`, `SpartaExplorer`, and other
surfaces. No Watch-specific TypeScript error was observed before the unrelated
error list.

## CDP marker

The first CDP hook attempt failed with a Chrome `Trace/breakpoint trap` and a
blank screenshot. The rerun succeeded:

- Marker:
  `/tmp/codex-ui-verification/agent-skills/watch-modal-event-overlay-payload-rerun/20260627T204747Z.read.json`
- Screenshot:
  `/tmp/codex-ui-verification/agent-skills/watch-modal-event-overlay-payload-rerun/20260627T204747Z.png`

## What this proves

- The modal can render an annotation box from event-derived overlay payload data.
- The modal can show the payload proof scope (`DRY_RUN_ONLY geometry_plumbing`).
- A clip without matching overlay payload does not render a fake annotation box.

## What this does not prove

- Live YOLO/ByteTrack inference.
- Real-time bbox updates while the movie plays.
- Character identity correctness.
- Brave Search domain seeding correctness.
- Memory writes to `watch_track_observations` or `watch_evidence_cases`.
- Qdrant/Jina embedding writes.
- `/memory recall` retrieval of tracked character observations.

## Next proof rung

Move the modal overlay payload from an inline/local fixture to a loaded Watch API
or static report artifact, then repeat the positive and negative browser proofs
against the loaded artifact. Only after that should the live YOLO/ByteTrack event
stream replace the dry-run payload fixture.
