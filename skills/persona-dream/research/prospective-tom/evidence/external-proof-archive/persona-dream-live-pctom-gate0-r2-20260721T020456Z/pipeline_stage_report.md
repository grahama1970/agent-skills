# Persona Dream Pipeline Stage Report

Run: `persona-dream-live-pctom-gate0-r2`
Mode: `static_dream`

## Report Summary

**Overall Finding:** Partially Verified

The run has deterministic planning artifacts, but model generation and final video assembly remain unproven until their receipts exist.

## Source-of-Truth Inventory

| Source | Type | Used For | Limitation |
|---|---|---|---|
| `dream_request.json` | request artifact | intake | does not prove downstream execution |
| `residue_links.json` | memory/fixture receipt | source residue | depends on recall quality |
| `character_scene_bible.json` | planning artifact | continuity | not a VLM validation result |
| `timed_transcript.json` | planning artifact | 30-second shot schedule | not a rendered video |
| `multimodal_prompts.json` | model prompt packet | z-image and Wan handoff | model calls not run yet |
| `voice_handoff_plan.json` | audio planning artifact | TTS, voice conversion, and eval handoff | not rendered audio |

## Stage Ledger

### stage_01_intake

Status: `ok`

Did: Normalized the user request into a persona-dream run request.

Text outputs: `dream_request.json`

Visual outputs: none

Failure or gap: none

### stage_02_memory_recall

Status: `ok`

Did: Collected residue from fixture or memory recall and preserved source ids.

Text outputs: `residue_links.json`

Visual outputs: none

Failure or gap: none

### stage_03_tension_detection

Status: `ok`

Did: Detected simple bridge tensions across residue items.

Text outputs: `contradiction_report.json`

Visual outputs: none

Failure or gap: none

### stage_04_static_dream_packet

Status: `ok`

Did: Created dream prompt, frame prompts, contact sheet, packet, and reflection.

Text outputs: `dream_packet.json`, `dream_prompt.txt`, `frame_prompts.json`, `dream_reflection.md`

Visual outputs: `contact_sheet.png`

Failure or gap: Contact sheet is deterministic planning art, not final generated model output.

## Plan-Ready Next Actions

1. Start Dockerized ComfyUI and prove `/system_stats` plus `/object_info` readiness.
2. Mount or download TurboDiffusion TurboWan2.2 I2V model files and required UMT5/VAE files.
3. Generate per-shot keyframes and actor/pose sheets with receipts.
4. Generate short I2V clips from accepted keyframes through ComfyUI TurboDiffusion receipts.
5. Run continuity checks against `character_scene_bible.json` and the immediately previous accepted clip; regenerate or fallback on mismatch.
6. Stitch accepted clips with FFmpeg and record `assembly_manifest.json` plus `ffmpeg_command.txt`.

## Non-Claims

- This report does not prove Chutes keyframe generation has run.
- This report does not prove Wan I2V clips exist.
- This report does not prove FFmpeg assembly exists.
- This report does not prove the final 30-second video has passed visual continuity checks.
