# Handoff Report: persona-dream

**Timestamp**: 2026-06-30T20:00:00-04:00
**Status**: See canonical current handoff at `local/HANDOFF.md`.

This top-level file redirects to the detailed handoff. The current handoff covers UX Lab Dream/Kling preflight React surface implementation — 12-phase pipeline, Gemini design packet mostly implemented, blocked on image modal click not working through draggable parent.

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
