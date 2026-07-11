# Project Agent Instructions — Persona-Dream Full Bake-off Bundle

## Purpose

This bundle lets a project agent run a controlled persona-dream media experiment:

```text
validated persona residue
→ dream packet
→ short story
→ timecoded scenes/script YAML + JSON
→ character perspective contact sheets
→ A/V bake-off:
    Lane A: ElevenLabs TTS → Kling LipSync
    Lane B: WavTTS local voice clone → Kling LipSync
    Lane C: NAVA joint audio-video generation
→ receipts and review reports
```

The central test is whether audio, video, script, and scene timing stay aligned.

## Hard rules

The project agent must preserve these rules:

1. **No lore invention.**
   Generated story, shots, prompts, audio, and video must derive from the locked contract and `source_grounded_residue_ids`.

2. **No memory writes.**
   This bundle must not write to memory, ArangoDB, Qdrant, or any canonical store.

3. **No unconsented voice cloning.**
   WavTTS and NAVA speaker reference WAVs require an owned, licensed, or explicitly consented voice.

4. **One shared base video for lip-sync lanes.**
   ElevenLabs and WavTTS must use the same base video. Otherwise the bake-off is invalid.

5. **NAVA is a joint AV lane, not a TTS lane.**
   NAVA should be compared as joint audio-video generation from the same dream packet.

6. **Manual visual review is mandatory.**
   Machine receipts check transcript and duration. They do not prove visual mouth quality or persona fit.

## Safe default path

Use this when starting from scratch or validating the package without spending credits:

```bash
./run.sh research-bakeoff smoke
```

Expected outputs:

```text
runs/embry_agent_smoke_001/story_assets/
├─ dream_packet.json
├─ dream_packet.yaml
├─ short_story.md
├─ scenes_script.json
├─ scenes_script.yaml
├─ contact_sheets.json
├─ contact_sheets.yaml
├─ contact_sheets.html
└─ contact_sheet_renders/
```

This path should not call fal, WavTTS, NAVA, ArangoDB, Qdrant, or memory.

Committed fixtures are intentionally small. Generated runs, rendered contact
sheets, downloaded media, audio files, and video files are ignored and must not
be treated as source fixtures.

Paid/external jobs require explicit commands:

```bash
./run.sh research-bakeoff elevenlabs
./run.sh research-bakeoff wavtts --confirm-voice-consent --ref-audio /path/to/voice.wav --ref-text "Exact reference transcript."
./run.sh research-bakeoff nava-dry-run --nava-repo /path/to/NAVA
```

The default hosted voice lane is ElevenLabs. WavTTS is opt-in and requires
consented reference audio. NAVA is research-only and compares joint A/V
generation against the TTS plus lip-sync lanes.

## Phase 1 — Build and inspect story assets

Command:

```bash
./run.sh research-bakeoff story --out-dir research/bakeoff/runs/embry_story_001
```

Inspect:

```bash
cat runs/embry_story_001/story_assets/short_story.md
cat runs/embry_story_001/story_assets/scenes_script.yaml
cat runs/embry_story_001/story_assets/contact_sheets.yaml
```

Acceptance:

- `short_story.md` exists.
- `dream_packet.json` and `dream_packet.yaml` exist.
- `scenes_script.json` and `scenes_script.yaml` exist.
- `contact_sheets.json`, `contact_sheets.yaml`, and `contact_sheets.html` exist.
- Scene/shot entries include start, end, and duration fields.
- Story assertions cite `source_grounded_residue_ids`.
- Synthetic dream symbolism is labeled as dream-symbolic, not source lore.

Failure guidance:

- If outputs are missing, stop and fix script/import/runtime issues.
- If persona facts are uncited, stop and repair `story.py` or contract inputs.
- If there are no durations, stop and repair `scenes_script` generation.

## Phase 2 — Render contact sheets

Dry-run, no fal credits:

```bash
./run.sh research-bakeoff contact-sheet \
  --out-dir research/bakeoff/runs/embry_story_001 \
  --dry-run
```

Optional fal image rendering:

```bash
export FAL_KEY="YOUR_FAL_KEY"  # FAL_API_KEY is also accepted.

./run.sh research-bakeoff contact-sheet \
  --out-dir research/bakeoff/runs/embry_story_001 \
  --backend fal_flux
```

Acceptance:

- `contact_sheet.png` exists.
- `contact_sheet.html` exists.
- Panel prompts preserve character perspective.
- Panel prompts do not add unsupported lore, labels, names, or on-screen text.
- The speaking panel keeps mouth-visible / front-facing constraints.

## Phase 3 — ElevenLabs baseline lane

Preconditions:

- `FAL_KEY` or `FAL_API_KEY` is set.
- `ffmpeg` and `ffprobe` are installed.

Command:

```bash
export FAL_KEY="YOUR_FAL_KEY"  # FAL_API_KEY is also accepted.

./run.sh research-bakeoff elevenlabs \
  --out-dir research/bakeoff/runs/embry_eleven_baseline_001
```

Inspect:

```bash
cat runs/embry_eleven_baseline_001/av_bakeoff/bakeoff_receipt.json
xdg-open runs/embry_eleven_baseline_001/av_bakeoff/report.html
```

Acceptance:

- `base_video.json` exists.
- `lanes/elevenlabs/tts.json` exists.
- `lanes/elevenlabs/lipsync.json` exists.
- `lanes/elevenlabs/lane_receipt.json` exists.
- Machine verdict is `pass` or `needs_review`.
- Transcript similarity is acceptable.
- Audio duration fits inside the base video window.
- Manual review confirms visible face and acceptable lip movement.

Failure guidance:

- If audio is longer than base video, shorten dialogue or increase base video duration within endpoint limits.
- If ASR transcript diverges, simplify TTS text and remove expressive tags.
- If face is occluded or not frontal, tighten `visual_prompt` and regenerate the shared base video.

## Phase 4 — Full ElevenLabs vs WavTTS bake-off

Preconditions:

- WavTTS installed and `wavtts_infer-cli` available.
- Reference WAV is owned/licensed/consented.
- Exact reference transcript is available.
- `FAL_KEY` or `FAL_API_KEY` is set.

Command:

```bash
./run.sh research-bakeoff wavtts \
  --out-dir research/bakeoff/runs/embry_wavtts_bakeoff_001 \
  --ref-audio /path/to/consented_reference_voice.wav \
  --ref-text "Exact transcript of the reference audio." \
  --confirm-voice-consent
```

Alternative if WavTTS audio is already generated:

```bash
python scripts/run_bakeoff.py \
  --out-dir runs/embry_wavtts_bakeoff_001/av_bakeoff \
  --wavtts-audio-path /path/to/wavtts_output.wav \
  --confirm-voice-consent
```

Acceptance:

- Both `lanes/elevenlabs` and `lanes/wavtts` exist.
- Both lanes use the same `base_video.video_url`.
- Both lanes have TTS JSON, lip-sync JSON, lane receipts, and downloaded media.
- `bakeoff_receipt.json` includes `comparison.machine_winner`.
- Manual review scores voice persona fit and lip-sync quality for both lanes.

Failure guidance:

- If WavTTS CLI output is not found, generate audio manually and use `--wavtts-audio-path`.
- If WavTTS output exceeds fal audio size limits, use the built-in compression path or shorten dialogue.
- If WavTTS transcript is poor, improve reference audio quality/transcript or try a different reference.

## Phase 5 — NAVA joint AV lane

NAVA is optional and off by default.

Preconditions:

- NAVA repo cloned locally.
- Checkpoints downloaded.
- GPU resources available.
- Optional consented speaker WAV.
- Optional first-frame image/contact-sheet panel.

Build NAVA JSONL:

```bash
python scripts/build_nava_inputs.py \
  --dream-packet runs/embry_story_001/story_assets/dream_packet.json \
  --out-dir runs/embry_story_001/nava_lane \
  --speaker-wav /path/to/consented_reference_voice.wav \
  --first-frame-image /path/to/contact_sheet_panel_or_reference.png
```

Dry-run command manifest:

```bash
python scripts/run_nava_local.py \
  --nava-repo ~/src/NAVA \
  --data-file runs/embry_story_001/nava_lane/nava_prompts.jsonl \
  --out-dir runs/embry_story_001/nava_lane/outputs \
  --ckpt NAVA_fp8.safetensors \
  --fp8 \
  --single-gpu \
  --dry-run
```

Single-GPU FP8 run:

```bash
python scripts/run_nava_local.py \
  --nava-repo ~/src/NAVA \
  --data-file runs/embry_story_001/nava_lane/nava_prompts.jsonl \
  --out-dir runs/embry_story_001/nava_lane/outputs \
  --ckpt NAVA_fp8.safetensors \
  --fp8 \
  --single-gpu
```

8-GPU sequence-parallel run:

```bash
python scripts/run_nava_local.py \
  --nava-repo ~/src/NAVA \
  --data-file runs/embry_story_001/nava_lane/nava_prompts.jsonl \
  --out-dir runs/embry_story_001/nava_lane/outputs \
  --ckpt NAVA.safetensors \
  --use-sp \
  --nproc-per-node 8
```

Verify NAVA output:

```bash
export FAL_KEY="YOUR_FAL_KEY"  # FAL_API_KEY is also accepted.

python scripts/verify_nava_output.py \
  --dream-packet runs/embry_story_001/story_assets/dream_packet.json \
  --video-path runs/embry_story_001/nava_lane/outputs/YOUR_OUTPUT.mp4 \
  --out runs/embry_story_001/nava_lane/nava_receipt.json \
  --upload-to-fal
```

Acceptance:

- `nava_prompts.jsonl` exists and contains `<S>dialogue<E>`.
- `nava_prompt_manifest.json` preserves source residue IDs.
- NAVA output MP4 exists.
- `nava_receipt.json` exists.
- ASR transcript preserves the expected dialogue.
- Manual review confirms joint AV sync, scene compliance, and no unsupported lore.

Failure guidance:

- If NAVA drifts story or adds unsupported text, reduce prompt complexity and use first-frame conditioning.
- If dialogue is wrong, simplify `<S>...<E>` span and rerun.
- If GPU memory fails, use FP8/single-gpu path or move NAVA to a larger GPU.

## Phase 6 — Final review report

After any full bake-off, the project agent should produce a concise review:

```text
VERDICT: PASS | NEEDS_CHANGES | BLOCKED

Evidence:
- story_assets paths
- contact_sheet paths
- bakeoff_receipt path
- lane_receipt paths
- final video URLs or local paths
- NAVA receipt path, if run

Decision:
- Best hosted lane
- Best local-voice lane
- Whether NAVA improves sync enough to keep
- Specific repairs before next run
```

## Expected directory layout after a full run

```text
runs/<run_id>/
├─ story_assets/
│  ├─ dream_packet.json
│  ├─ dream_packet.yaml
│  ├─ short_story.md
│  ├─ scenes_script.json
│  ├─ scenes_script.yaml
│  ├─ contact_sheets.json
│  ├─ contact_sheets.yaml
│  ├─ contact_sheets.html
│  └─ contact_sheet_renders/
├─ av_bakeoff/
│  ├─ contract.json
│  ├─ base_video.json
│  ├─ lanes/
│  │  ├─ elevenlabs/
│  │  └─ wavtts/
│  ├─ bakeoff_receipt.json
│  ├─ report.md
│  └─ report.html
└─ nava_lane/
   ├─ nava_prompts.jsonl
   ├─ nava_prompt_manifest.json
   ├─ nava_prompt_preview.md
   ├─ outputs/
   └─ nava_receipt.json
```

## Stop conditions

Stop and report `BLOCKED` if:

- No valid source-grounded residue IDs are available.
- The package attempts memory/Arango/Qdrant writes.
- Voice consent is missing for WavTTS or NAVA reference audio.
- The environment lacks `FAL_KEY` or `FAL_API_KEY` for fal phases.
- NAVA dependency/checkpoint/GPU setup is unavailable for NAVA phase.

Report `NEEDS_CHANGES` if:

- Outputs exist but transcript/duration checks fail.
- Contact sheets introduce unsupported lore.
- Base video is unusable for lip-sync.
- NAVA output improves sync but drifts scene/lore.

Report `PASS` only if:

- Story assets, scene script, and contact sheets are generated.
- At least one AV lane produces a reviewable final video.
- Machine receipt is pass or reviewable.
- Manual review confirms no unsupported lore and acceptable A/V sync.
