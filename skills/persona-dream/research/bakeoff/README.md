# Persona-Dream Full Bake-off Agent Bundle

This is the consolidated bundle. It includes:

```text
story + scene/script YAML/JSON
contact-sheet prompts and rendering
ElevenLabs → Kling LipSync lane
WavTTS → Kling LipSync lane
NAVA joint audio-video lane
project-agent runbook and manifest
```

Start here for automated/project-agent use:

```text
PROJECT_AGENT_INSTRUCTIONS.md
PROJECT_AGENT_MANIFEST.json
AGENT_QUICKSTART.md
```

Inside the `persona-dream` skill, prefer the promoted wrapper:

```bash
./run.sh research-bakeoff smoke
./run.sh research-bakeoff story
./run.sh research-bakeoff contact-sheet --dry-run
./run.sh research-bakeoff elevenlabs
./run.sh research-bakeoff wavtts --confirm-voice-consent --ref-audio /path/to/voice.wav --ref-text "Exact reference transcript."
./run.sh research-bakeoff nava-inputs
./run.sh research-bakeoff nava-dry-run --nava-repo /path/to/NAVA
```

The default smoke path is no-credit and writes under
`research/bakeoff/runs/`. Generated runs and media are ignored; committed
fixtures live under `fixtures/`.

---

# Persona-Dream Story + A/V Bake-off

This updated package includes the missing production assets:

```text
short story
→ timecoded scenes/script
→ YAML + JSON exports
→ character-perspective contact-sheet prompts
→ optional contact-sheet image rendering
→ ElevenLabs vs WavTTS lip-sync bake-off
```

The original bake-off code is still present. The new story layer is reviewable before any media generation call.

## Build story assets only

```bash
python scripts/build_story_assets.py \
  --out-dir runs/embry_story_001/story_assets
```

This writes:

```text
dream_packet.json / dream_packet.yaml
short_story.md
scenes_script.json / scenes_script.yaml
contact_sheets.json / contact_sheets.yaml
contact_sheets.html
```

## Render contact sheets as local prompt cards

No fal credits required:

```bash
python scripts/render_contact_sheets_fal.py \
  --contact-sheets runs/embry_story_001/story_assets/contact_sheets.json \
  --out-dir runs/embry_story_001/story_assets/contact_sheet_renders \
  --dry-run
```

## Render contact sheets with fal images

```bash
export FAL_KEY="YOUR_FAL_KEY"  # FAL_API_KEY is also accepted.

python scripts/render_contact_sheets_fal.py \
  --contact-sheets runs/embry_story_001/story_assets/contact_sheets.json \
  --out-dir runs/embry_story_001/story_assets/contact_sheet_renders
```

The default image model is `fal-ai/flux/dev`.

## Full story + contact sheet + bake-off wrapper

```bash
python scripts/run_story_pipeline.py \
  --out-dir runs/embry_story_001 \
  --render-contact-sheets \
  --contact-sheet-dry-run \
  --run-bakeoff \
  --skip-wavtts
```

Full WavTTS bake-off:

```bash
python scripts/run_story_pipeline.py \
  --out-dir runs/embry_story_001 \
  --render-contact-sheets \
  --run-bakeoff \
  --ref-audio /path/to/consented_reference_voice.wav \
  --ref-text "Exact transcript of the reference audio." \
  --confirm-voice-consent
```

---

# Persona-Dream A/V Bake-off: ElevenLabs vs WavTTS + Lip-sync

This package runs a controlled bake-off:

```text
same source-grounded A/V contract
same generated base video
├─ Lane A: fal ElevenLabs v3 TTS → Kling LipSync
└─ Lane B: local WavTTS voice clone → upload WAV/MP3 to fal → Kling LipSync
→ Whisper + ffprobe verifier
→ comparison receipt + Markdown/HTML report
```

The key design choice is **one shared base video**. That isolates the variable under test:

```text
voice backend + generated audio timing
```

not video-prompt randomness.

## What this tests

This answers:

1. Does ElevenLabs or WavTTS produce audio that fits the scene clock better?
2. Does each audio lane preserve the exact expected transcript?
3. Does each lip-sync result keep the transcript after final video generation?
4. Which final video needs less manual repair?
5. Did either lane create unsupported persona/lore claims?

This does **not** fully automate visual/lip-sync quality judgment. The generated receipt includes manual review fields for mouth visibility, persona fit, and visual lore drift.

## Safety / rights rule

Use WavTTS only with a voice you own, created, licensed, or have explicit consent to clone.

For Embry/Horus production voices, prefer an original synthetic reference voice and store a voice card:

```json
{
  "voice_asset_id": "embry_voice_v001",
  "reference_audio_sha256": "...",
  "rights": "owned_or_consented",
  "persona": "embry"
}
```

Do not clone a real actor, streamer, narrator, or YouTube voice without rights.

## Install

```bash
cd persona_dream_av_bakeoff

python3.11 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

export FAL_KEY="YOUR_FAL_KEY"  # FAL_API_KEY is also accepted.

sudo apt-get update
sudo apt-get install -y ffmpeg
```

## Optional: install WavTTS

WavTTS should live in its own repo/env. The bake-off script calls the `wavtts_infer-cli` command.

```bash
git clone https://github.com/cwx-worst-one/WavTTS ~/src/WavTTS
cd ~/src/WavTTS

conda create -n wavtts python=3.10
conda activate wavtts

pip install torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124
pip install -e .
```

Then run this bake-off while that env is active.

## Fast baseline: ElevenLabs only

Use this first to prove fal/video/lip-sync is wired correctly:

```bash
python scripts/run_bakeoff.py \
  --out-dir runs/embry_bakeoff_001 \
  --skip-wavtts
```

## Full bake-off: ElevenLabs vs WavTTS

```bash
python scripts/run_bakeoff.py \
  --out-dir runs/embry_bakeoff_001 \
  --ref-audio /path/to/consented_reference_voice.wav \
  --ref-text "Exact transcript of the reference audio." \
  --confirm-voice-consent
```

## Use an already-generated WavTTS audio file

If WavTTS CLI changes or you want to hand-generate the audio first:

```bash
python scripts/run_bakeoff.py \
  --out-dir runs/embry_bakeoff_001 \
  --wavtts-audio-path /path/to/wavtts_output.wav \
  --confirm-voice-consent
```

The script will upload that local audio to fal and use it for the WavTTS lip-sync lane.

## Use an existing base video URL

Useful when you already have a good 2–10 second front-facing clip:

```bash
python scripts/run_bakeoff.py \
  --out-dir runs/embry_bakeoff_001 \
  --base-video-url "https://..." \
  --ref-audio /path/to/consented_reference_voice.wav \
  --ref-text "Exact transcript of the reference audio." \
  --confirm-voice-consent
```

## Outputs

Each run writes:

```text
runs/embry_bakeoff_001/
├─ contract.json
├─ base_video.json
├─ lanes/
│  ├─ elevenlabs/
│  │  ├─ tts.json
│  │  ├─ lipsync.json
│  │  └─ media/
│  └─ wavtts/
│     ├─ tts.json
│     ├─ lipsync.json
│     └─ media/
├─ bakeoff_receipt.json
├─ report.md
└─ report.html
```

Open:

```bash
cat runs/embry_bakeoff_001/bakeoff_receipt.json
xdg-open runs/embry_bakeoff_001/report.html
```

## What “pass” means

The machine verifier can check transcript and timing. It cannot fully judge whether the mouth looks good.

A good run has:

```json
{
  "overall": "needs_manual_review",
  "machine_verdict": "pass"
}
```

That means the automated checks passed and the next step is visual review.

A machine failure usually means:

- ASR transcript diverged from the expected line.
- Audio duration exceeded video duration.
- Generated audio/video duration drifted too far.
- Required source residue IDs were missing from the contract.
