# Handoff Report: persona-dream

**Timestamp**: 2026-06-30T20:00:00-04:00
**Status**: See canonical current handoff at `local/HANDOFF.md`.

This top-level file redirects to the detailed handoff. The current handoff covers UX Lab Dream/Kling preflight React surface implementation — 12-phase pipeline, Gemini design packet mostly implemented, blocked on image modal click not working through draggable parent.

## 2026-07-18 Reviewer hardening (identity continuity) — action required

- A negative-control probe proved the Phase C identity reviewer was too lenient (PASSed 2/3 known-bad montage frames), so the successor 8/8 first-attempt Phase C PASS was partly false confidence for specific-identity fidelity.
- Hardened `phase07_storyboard_tau_node._identity_review_prompt` (contained to the review prompt contract). Hardened prompt `sha256:ee09dd57d8d06953d2039b4085cab7e481a5f09c09984a290b97b41cb3f626d7`.
- Recalibration `reviewer_calibration_receipt.v2.json` = REVIEWER_CALIBRATION_FAILED but improved (known-bad FAILs 1/3 -> 2/3; positives 2/2, tamper 1/1). Residual: subtlest montage frame `known_bad_sb_001` still passes pixel-only review after the 3-revision cap.
- Hardened re-review of the 8 accepted successor frames = 8/8 STILL PASS (`hardened_rereview/hardened_rereview_summary.v2.json`).
- `acceptance_rung_receipt.v2.json` = RUNG_NOT_RESTORED_BLOCKED_ON_REVIEWER_CALIBRATION. Lane C SB_003 end-frame regen + supersession/requalification are DEFERRED until the sb_001 calibration gap is resolved (face-crop-only comparison, a second stricter reviewer, or human adjudication), then re-run calibration to PASS before restoring/certifying the rung. No paid call made or authorized.

## Current Truth

- The active handoff is:

```text
/home/graham/workspace/experiments/agent-skills/.opencode/skills/persona-dream/local/HANDOFF.md
```

- The React file is:

```text
/home/graham/workspace/experiments/pi-mono/packages/ux-lab/src/components/dream/DreamWorkspace.tsx
```

- The server routes are in:

```text
/home/graham/workspace/experiments/pi-mono/packages/ux-lab/server/index.ts
```

- The live route is:

```text
http://localhost:3002/watch#dream
```

- TypeScript compiles clean (exit 0).
- API servers running on ports 3001/3002.
- Memory daemon at `http://127.0.0.1:8601`.
- Persona media endpoint at `/api/persona-media` returns HTTP 200.

## Next Required Step

Fix the image modal click-through issue in `MemoryLinker` (draggable parent intercepts events). Then proceed to Phase 03 StoryMatrix wiring.

## Watch Post-Return Gauntlet (Phase 12 perception)

`watch` is now wired into the post-return gauntlet as the sole owner of
rendered-media perception, replacing the bespoke fixed 12-frame contact-sheet +
`watch-codex-vision` lane.

- **Harness**: `scripts/watch_post_return_gauntlet.py` — runs `watch`
  (scene-driven frames, Whisper transcript) over a returned MP4 and emits
  `watch_gauntlet/<video_sha_prefix>/dream_observation_packet.v1.json`
  (schema `persona_dream.watch_gauntlet_observation_packet.v1`) with per-frame
  observed entities, timestamps, coverage gaps, and hooks for GOAL steps
  35 (frame sheet), 36 (identity continuity), 38 (visible-speaker lip sync).
- **Proven**: validated against the frozen historical Kling return
  (`muxed_provider_return.mp4`, `sha256:991c311f…`). Receipt:
  `reports/pipeline-complete/.persona-dream/revisions/rev_successor_943b01ecd9a3/watch_gauntlet/991c311f365f/watch_gauntlet_validation_receipt.v1.json`
  → `PASS_WATCH_GAUNTLET_VALIDATED` (5/5 expectations). Codex-oauth vision
  independently corroborated `EMBRY_IDENTITY_DRIFT_00_03`; Whisper recovered the
  canonical Kai line consistent with the forced-alignment receipt.
- **Known degradation**: per-frame VLM entity descriptions are unavailable
  (`watch` default `vlm-chutes` model returns HTTP 401); recorded as a coverage
  gap, not faked. Vision drift corroboration is an independent probabilistic
  check — the frozen human continuity review remains authoritative.

**Next steps**: (1) restore a working `watch` per-frame VLM model to fill the
entity coverage gap; (2) once a freshly authorized successor Kling return exists,
run the same gauntlet against it (`--source-revision-id rev_successor_…`) to
observe the repaired output; Phase 12 is only *complete* when a successor return
is observed and its identity/lip-sync outcomes are recorded.
