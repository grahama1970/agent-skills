# hum - Persona Humming Diagnostics and STS Bakeoffs

`/hum` is the bounded workflow for finding, preparing, and reviewing static
persona humming or chant candidates. It does not prove that Embry can hum any
song dynamically. It gives agents a disciplined way to discover source audio,
extract or import a guide, audition voice settings, and hand a browser-review
page back to the human.

Use it for work like:

- "Find female humming sources Embry could use during idle time."
- "Demucs this YouTube track, isolate the vocal, and make a guide."
- "Try Light Rasp at 0.85x and compare ElevenLabs settings."
- "Make an HTML bakeoff page with every candidate and the request receipts."
- "Record why this source failed before spending more STS credits."

```text
human or project agent gives a song, URL, or mood
    |
    v
source discovery/import
    |-- brave-search for candidates
    |-- ingest-youtube for metadata/transcript receipts
    |-- yt-dlp/local file for diagnostic audio
    v
guide preparation
    |-- Demucs/create-stems vocals.wav
    |-- full-track segment selection
    |-- tempo variants: 0.90x, 0.85x, 0.80x
    |-- optional light pitch-corrected guide
    v
ElevenLabs STS bakeoff
    |-- voice_id + model_id + JSON voice_settings
    |-- receipts + MP3 + WAV per candidate
    v
HTML/CSS review page
    |-- source guide players
    |-- ranked candidate players
    |-- settings, paths, risks, and bug ledger
    v
human listening gate before cache publication
```

**One core principle:** STS changes the voice; it does not fix the guide. If the
guide is off-pitch, lyric-heavy, wobbly, too breathy, or wrong in mood, the
output will usually inherit that problem.

## Try this first

You do not need to memorize the whole skill. Start with the workflow state:

```bash
cd skills/hum

# Inspect the skill contract before agent runs.
sed -n '1,220p' SKILL.md

# Check the CLI surface.
./run.sh help

# Analyze an existing guide without publishing anything.
./run.sh decompose /path/to/guide.wav --out-dir /tmp/hum_decompose --max-duration 60 --json

# Lightly pitch-center a close-but-off guide before STS.
./run.sh pitch-correct-guide /path/to/guide.wav \
  --out-dir /tmp/hum_pitch_corrected \
  --max-correction-cents 35 \
  --json
```

The current production boundary is strict: generated candidates are comparison
artifacts until human listening confirms musical usability and non-lexicality.
Cache presence is not approval.

## Quick Start

The fastest useful loop is source -> guide -> STS bakeoff -> HTML review page.

```bash
cd skills/hum

# 1. Search for source candidates when the human gives only a mood.
cd ../brave-search
./run.sh web "site:youtube.com/watch female humming ASMR soft voice" --count 10

# 2. Ingest metadata/transcript receipts for likely YouTube sources.
cd ../ingest-youtube
./run.sh get --video-id VIDEO_ID --no-enrich --no-whisper

# 3. Isolate a vocal guide when the source is a song or full mix.
cd ../create-stems
./run.sh separate \
  --mix /path/to/source.wav \
  --out /path/to/run/stems \
  --instrument vocals \
  --model htdemucs \
  --device cpu \
  --segment 7

# 4. Return to hum for guide analysis and optional pitch preprocessing.
cd ../hum
./run.sh pitch-correct-guide /path/to/0p85x_guide.wav \
  --out-dir /path/to/run/pitch_corrected_guides \
  --max-correction-cents 35 \
  --json
```

For the full agent contract, status packet schema, and safety boundary, see
[SKILL.md](SKILL.md).

## When to Use Each Path

| Path | Reach for it when... | Main artifact |
| --- | --- | --- |
| Source discovery | The human gives a mood or persona intent, not a file | `review/source_bakeoff.html` |
| Vocal-stem guide | A song has a useful lead vocal or chant phrase | `stems/.../vocals.wav` |
| Actual humming source | The source is already non-lexical humming | trimmed guide WAV, often no Demucs needed |
| Tempo bakeoff | The guide is close but too fast/slow for idle humming | `0p90x`, `0p85x`, `0p80x` guide variants |
| Pitch-correction axis | The guide is close but audibly off-pitch | `pitch_corrected_guides/*__pitch_global_*.wav` |
| Voice bakeoff | The guide is plausible and the question is target timbre | `sts/*.wav` plus `receipts/*.json` |
| Settings polish | Voice/tempo won, but artifacts or wobble remain | controlled variants of `stability`, `similarity_boost`, `style` |
| Cache publication | Human has approved the audio and rights/provenance are acceptable | hum-cache manifest entry |

## Hawaiian War Chant Example

The Hawaiian War Chant run is the clearest example of the workflow finding a
usable static guide. The human wanted a humorous, rhythmic, non-lexical Embry
idle hum/chant. The first attempts showed why the workflow exists: wrong
segments, unsupported STS text fields, and overly fast or unstable outputs were
rejected before cache publication.

### 1. Start From a Source and Extract the Vocal

For the accepted War Chant test, the useful guide came from an extracted/merged
audio segment rather than asking ElevenLabs to invent the chant from text.

```text
source track
    -> Demucs/create-stems vocal extraction
    -> human-selected useful vocal/hum ranges
    -> merged 15s guide
    -> 0.85x slowdown for natural humming pace
```

The guide that moved the test forward was:

```text
/tmp/watch-audio-merge/1781966968962-hwc_fulltrack_1_ranges_0p85x.wav
```

The earlier full source segment workflow also proved a key UX lesson: selecting
segments from the whole audio file with clear in/out controls is simpler than
trying to accept automatically guessed clip cards.

### 2. Use STS Correctly

ElevenLabs Speech-to-Speech does not accept a documented `text`,
`style_prompt`, `lyrics`, `transcript`, or pronunciation-dictionary field. The
correct payload surface is the guide audio, target voice, model, and numeric
voice settings.

```python
import json
import os
import requests

VOICE_ID = "xYa75LlayhWHCRl1yJSH"  # Light Rasp
INPUT = "/tmp/watch-audio-merge/1781966968962-hwc_fulltrack_1_ranges_0p85x.wav"
OUTPUT = "/tmp/watch-audio-merge/elevenlabs_light_rasp_0p85_hwc_sts.mp3"

url = f"https://api.elevenlabs.io/v1/speech-to-speech/{VOICE_ID}?output_format=mp3_44100_128"
headers = {
    "xi-api-key": os.environ["ELEVENLABS_API_KEY"],
    "accept": "audio/mpeg",
}
data = {
    "model_id": "eleven_multilingual_sts_v2",
    "voice_settings": json.dumps({
        "stability": 0.40,
        "similarity_boost": 0.80,
        "style": 0.45,
        "use_speaker_boost": True,
    }),
    "remove_background_noise": "false",
    "file_format": "other",
}

with open(INPUT, "rb") as audio:
    response = requests.post(
        url,
        headers=headers,
        data=data,
        files={"audio": ("guide.wav", audio, "audio/wav")},
        timeout=180,
    )
response.raise_for_status()
with open(OUTPUT, "wb") as f:
    f.write(response.content)
```

### 3. Bake Off Voice and Tempo

The useful comparison was not "one file exists." It was a listening bakeoff over
voice identity and speed:

| Axis | Result |
| --- | --- |
| Voice | Light Rasp was preferred over cuter/quirkier female voices |
| Tempo | `0.90x` felt too fast for someone to hum |
| Tempo | `0.85x` felt natural and retained humor |
| Tempo | `0.80x` became slower and more ceremonial |
| Settings | Moderate stability plus low style reduced artifacts |

The accepted War Chant candidate was:

```text
/tmp/watch-audio-merge/elevenlabs_final_light_rasp_0p85_hwc_sts.wav
```

That file is still a static comparison artifact. It is not proof of arbitrary
dynamic Embry singing.

### 4. Preserve the Decision

Every run should keep the decision surface and proof artifacts together:

```text
run/
|-- source/
|   |-- youtube_metadata.json
|   `-- source.wav
|-- stems/
|   `-- htdemucs/.../vocals.wav
|-- guides/
|   |-- guide_selection.json
|   `-- *_0p85x_rawguide.wav
|-- pitch_corrected_guides/
|   |-- *_pitch_analysis.json
|   |-- *_pitch_correction_manifest.json
|   `-- *_pitch_global_*.wav
|-- sts/
|   `-- <track>__<voice>__<speed>__<settings>.wav
|-- receipts/
|   `-- <track>__<voice>__<speed>__<settings>.json
|-- review/
|   |-- bakeoff_manifest.json
|   `-- bakeoff.html
`-- status/
    `-- status.jsonl
```

The War Chant lesson now used by later runs:

```text
Light Rasp + 0.85x is the default Embry-like humming center.
Use controlled settings when glissando or sustained vowels distort.
Reject source guides that are off-pitch before trying to polish STS output.
```

## Source Selection Rules

Good sources tend to have:

- solo or near-solo female voice
- non-lexical humming, chant texture, or simple open vowels
- clear pitch center with low wobble
- dry or close-mic audio
- short useful segments, roughly 15-45 seconds
- mood that fits Embry: young adult, husky, grounded, comforting, dry smirk

Avoid sources with:

- heavy vibrato, tremolo, or pitch bends
- dense full-band bleed
- harmony stacks, doubled vocals, chorus effects, or strong reverb
- lyric-heavy hooks
- baby/maternal framing unless explicitly requested
- scary/mystery SFX tone
- "cute", "quirky", anime, seductive, or corporate-narrator voice identity

## ElevenLabs STS Controls

| Control | Use | Risk |
| --- | --- | --- |
| `stability` | Higher values make output steadier | Too high can flatten humor |
| `similarity_boost` | Keeps the target voice identity | Too high can over-impose the library voice |
| `style` | Adds expressive character | Too high can create wobble, theater, or artifacts |
| `use_speaker_boost` | Strengthens voice identity | Can make output less intimate |
| `remove_background_noise` | Can reduce guide leakage | Can strip breath, rasp, consonants, or hum texture |

Known stable Embry-ish settings from the Hawaiian Eye and War Chant work:

```json
{
  "stability": 0.50,
  "similarity_boost": 0.84,
  "style": 0.15,
  "use_speaker_boost": true
}
```

Use lower `style` when a guide has glissando, sustained vowels, or wobble risk.
Changing settings cannot rescue a bad guide; it can only reduce how badly STS
amplifies the problem.

## Source Bakeoff Workflow

When the human asks for more possible idle hums, do not immediately spend STS
credits. Build a source page first.

```bash
cd skills/brave-search
./run.sh batch -f /path/to/queries.json -w 4 > /path/to/run/search/brave_batch_raw.json

cd ../ingest-youtube
./run.sh get --video-id VIDEO_ID --no-enrich --no-whisper \
  > /path/to/run/ingest/transcripts/VIDEO_ID.json

yt-dlp --dump-single-json --no-playlist \
  "https://www.youtube.com/watch?v=VIDEO_ID" \
  > /path/to/run/ingest/metadata/VIDEO_ID.json
```

The source bakeoff page should rank candidates by Embry fit and expose:

- embedded YouTube preview
- title, channel, duration, and video ID
- transcript/metadata receipt status
- reasons it might work
- risks that should block ElevenLabs spending

Only after the human picks 2-3 sources should the agent run guide extraction and
ElevenLabs STS.

## Status Packets

E2E runs must write status packets for the project agent. The ledger lives at:

```text
<run>/status/status.jsonl
```

Each packet must include:

```json
{
  "phase": "source|stems|guide_selection|tempo|voice_search|sts|review|html|verification|blocked",
  "current_artifact": "/absolute/path/or/url",
  "command_or_api": "exact command or endpoint just run",
  "evidence": {
    "counts": {},
    "paths": [],
    "status_code": null,
    "duration_seconds": null
  },
  "bug_or_blocker": null,
  "next_step": "concrete next action",
  "stop_condition": "what will end the current phase"
}
```

If a deterministic bug appears, record the failing command and the repair. Prior
bugs found this way include a wrong `create-stems` wrapper invocation and a
missing `pitch-correct-guide` route in `hum/run.sh`.

## Hum Subagent

The transport worker for this workflow lives at:

```text
agents/hum/
|-- AGENTS.md
`-- persona.yaml
```

`agents/hum` is the end-to-end execution subagent. It owns bounded source
discovery, YouTube metadata/transcript receipts, Demucs vocal extraction, guide
selection, tempo variants, light pitch-correction branches, ElevenLabs STS
bakeoffs, HTML/CSS review pages, CDP verification, and the `status/status.jsonl`
ledger. It also owns repairing deterministic workflow bugs found during a run,
such as bad wrapper flags or missing CLI routes.

It does **not** own final human listening approval, rights approval, runtime
cache publication, global project completion, or unrelated repo cleanup.

`skills/hum/subagents/hum-reviewer.yaml` is different: it is a read-only review
persona for ranking source tracks, voice IDs, guide variants, and STS candidates
against the Embry voice/persona rubric. The project agent or `agents/hum`
worker may ask it for a bounded review, but it must not download sources, mutate
audio, call ElevenLabs, generate pages, or approve cache publication.

## Self-contained Layout

```text
skills/hum/
|-- README.md                 human-facing guide
|-- SKILL.md                  agent contract and failure boundary
|-- run.sh                    CLI wrapper
|-- sanity.sh                 dependency checks
|-- pyproject.toml            skill-local Python environment
|-- src/
|   |-- cli.py                Typer command surface
|   |-- decomposition.py      melody/cadence/sound artifacts
|   |-- pitch_correction.py   light guide pitch-centering
|   `-- ...
|-- tests/                    targeted regression tests
`-- jobs/                     run artifacts, review pages, ledgers
```

## Commands

```bash
./run.sh help
./run.sh sanity
./run.sh decompose AUDIO --out-dir OUT --max-duration 60 --json
./run.sh decompose-youtube URL --out-dir OUT --limit 1 --max-duration 60 --json
./run.sh build-female-humming-dataset --youtube-url URL --out-dir OUT --json
./run.sh render-female-hum --dataset-index INDEX_JSON --out-dir OUT --json
./run.sh generate-elevenlabs-articulations --output-dir OUT --duration-seconds 1.2 --json
./run.sh render-articulated-psola --midi MELODY.mid --samples SAMPLES --output-dir OUT --json
./run.sh pitch-correct-guide GUIDE.wav --out-dir OUT --max-correction-cents 35 --json
./run.sh add --song SOURCE.wav --persona embry --start 00:00:08 --duration 00:00:20
./run.sh list --persona embry
./run.sh play hawaiian_war_chant --persona embry
```

## Environment

| Variable | Purpose |
| --- | --- |
| `ELEVENLABS_API_KEY` | Required for STS and Sound Effects API calls |
| `ORPHEUS_INFER_URL` | Orpheus infer endpoint, default `http://127.0.0.1:8767` |
| `SEEDVC_DIR` | Seed-VC checkout, default `/mnt/storage12tb/tools/seed-vc` |
| `BRAVE_API_KEY` | Source discovery through `/brave-search` |
| `WEBSHARE_API_KEY` | Optional `/ingest-youtube` proxy tier |

## Troubleshooting

| Problem | What it usually means | Fix |
| --- | --- | --- |
| STS output is off-pitch | The guide is off-pitch or unstable | Pick a cleaner segment; try light pitch correction before STS |
| STS output wobbles | Style too high or guide has glissando/vibrato | Lower `style`, raise `stability`, or reject the guide |
| Lyrics leak through | Source guide is too lexical | Choose humming/chant ranges or reject source |
| `text` field has no effect in STS | STS does not document text prompting | Remove text field; fix the guide audio |
| Demucs path missing | Output path/model assumptions are wrong | Read `stems/manifest.json` and locate actual `vocals.wav` |
| Source page has unavailable videos | Brave result is stale or removed | Keep the failure visible; do not spend STS credits |
| Review page cannot be reached | Local `http.server` stopped | Restart from the run directory on an open port |

## Related Skills

| Skill | Relationship |
| --- | --- |
| `/brave-search` | Finds candidate source tracks and humming videos |
| `/ingest-youtube` | Captures transcript and metadata receipts |
| `/create-stems` | Runs Demucs vocal isolation |
| `/tts-voice` | Orpheus reference voice infrastructure |
| `/surf` | Browser/CDP verification for review pages |
| `/ask` | External review/oracle handoff when the agent is blocked |

## For Agents

Read [SKILL.md](SKILL.md) before acting. It defines:

- the dynamic-humming failure boundary
- the STS payload contract
- required status packets
- source and cache safety rules
- human listening gate
- E2E bug-ledger expectations

Do not claim a hum is publishable from generated files alone. The required
closure evidence is a review page, receipts, status ledger, browser screenshot,
and an explicit human listening decision.
