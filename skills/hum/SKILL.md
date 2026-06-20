---
name: hum
description: >
  Experimental persona humming diagnostic workflow. Licensed song segment →
  melody transcription or guide carrier → Orpheus TTS reference → Seed-VC
  conversion attempt, or bounded ElevenLabs STS voice bakeoff for static guide
  artifacts. Dynamic Embry humming is not established.
  Orchestrates: /brave-search, /ingest-youtube, /create-stems, /tts-voice
  (Orpheus), Basic Pitch, Seed-VC, ElevenLabs STS comparison.
triggers:
  - hum
  - add hum
  - teach humming
  - hum a song
  - humming pipeline
  - convert vocals
  - persona singing
allowed-tools:
  - Bash
  - Python
  - Read
  - Write
metadata:
  short-description: "Persona humming feasibility boundary + diagnostics"
  author: graham
  version: "0.3.2"

provides:
  - hum
composes:
  - brave-search
  - create-stems
  - tts-voice
  - ingest-youtube
  - task-monitor
complies:
  - best-practices-skills
  - best-practices-python
---

# /hum

Document and run bounded diagnostics toward persona humming for idle /converse
playback. The current workflow does **not** prove dynamic Embry humming. It can
produce static or diagnostic artifacts from licensed local segments, imported
guide audio, an Orpheus speech reference, and Seed-VC conversion attempts.

> Orpheus is TTS — it does **not** carry melody. Melody comes from MIDI/guide hum;
> Seed-VC (`--f0-condition True`) attempts to map that melody onto the Orpheus
> clone, but this has not established usable Embry humming.

## Failure Boundary

Dynamic Embry humming is **not established** and is blocked without authorized
Embry-like singing/humming data. `$hum` has **not** solved "Embry can hum
arbitrary melodies in her own voice."

Operational constraints:

- Orpheus/Embry speech reference is **not enough** for dynamic
  humming/singing. It supplies speech timbre, not a musical singing/humming
  voice model.
- Seed-VC, Kits/RVC, Suno, ACE-Step, and DiffSinger-direct have failed or only
  produced static/diagnostic artifacts for this goal.
- ElevenLabs Music/Sound Effects audio-reference generation is also a manual
  comparison/import path only. It may produce useful texture, but it is not
  established as exact MIDI-following humming or Embry-like dynamic voice
  synthesis.
- ElevenLabs Speech-to-Speech (Voice Changer) may be used for a bounded static
  guide bakeoff when the guide audio already carries melody/cadence and the
  task is to audition target voice identity. This is a comparison artifact, not
  proof of dynamic Embry humming.
- Numeric audio checks such as non-silence, duration, sample rate, channel
  count, and no clipping are **not proof** of usable humming.
- Human listening is the release gate. A candidate is not publishable unless a
  human listening review confirms musical usability and non-lexicality.
- Cache presence is not approval. Do not treat a generated WAV or manifest
  entry as idle-playback-ready without listening evidence and rights
  provenance.

### Do Not Retry Without New Input

Do not run more model/tool experiments for dynamic Embry humming unless at
least one of these exists:

- an authorized Embry-like humming/singing dataset
- a verified MIDI/F0 melody plus a credible musical carrier
- explicit human approval for one bounded WebGPT-reviewed experiment

Do not cache generated outputs unless they pass human listening review and a
non-lexicality review confirming that no intelligible source lyrics remain.

### Known Failed Paths

| Path | Result |
|------|--------|
| Suno | Inconsistent melody, backing/harmony leakage, unreliable control. Manual exports are comparison artifacts only. |
| ACE-Step | Unusable low-noise/generic outputs; no proven target voice conditioning for Embry humming. |
| Seed-VC/Orpheus | Artifacted, broken, or gibberish outputs when asked to create dynamic Embry humming from speech reference plus guide. |
| Kits/RVC | Best static conversion observed, but not dynamic; guide-dependent and not cache-ready. |
| DiffSinger direct ONNX | Rendered a non-silent WAV, but human listening rejected it as junk/gibberish MIDI-autotuned output. Treat as model-execution proof only. |

### ElevenLabs STS Voice Bakeoff Boundary

Use ElevenLabs Speech-to-Speech only when the source guide is already plausible:
the audio must contain the intended hum/chant timing, mouth shape, breath,
phoneme texture, and emotional performance. STS does **not** accept a documented
freeform `style_prompt`, `text`, `lyrics`, `transcript`, or pronunciation
dictionary field. The only documented conditioning surface is:

- `audio` — guide WAV/MP3 carrying timing, cadence, melody, and articulation
- `voice_id` — target voice identity
- `model_id` — use `eleven_multilingual_sts_v2` for multilingual/phoneme nuance
- `voice_settings` — numeric controls described below
- optional `seed`, `remove_background_noise`, and `file_format`

Do not try to force Hawaiian phonemes by adding undocumented `text` fields to
STS. If the guide pronunciation is wrong, fix or replace the guide audio, or
run a separate Dubbing API experiment with an explicit transcript. Whisper may
be useful for rough timing, but it is not source truth for chant syllables or
Hawaiian phonemes.

### ElevenLabs Voice Library Discovery

Do not select ElevenLabs voice IDs by stale UI memory alone. Use the Voice
Library API as the first-pass discovery source when an API key is available,
then use `hum-reviewer` and human listening to choose the final bakeoff slate.

Use `GET /v1/shared-voices` for intent search:

```bash
curl -G "https://api.elevenlabs.io/v1/shared-voices" \
  -H "xi-api-key: $ELEVENLABS_API_KEY" \
  --data-urlencode "search=husky female" \
  --data-urlencode "gender=female" \
  --data-urlencode "age=young" \
  --data-urlencode "page_size=20"
```

Useful filters include `search`, `gender`, `age`, `accent`, `language`,
`locale`, `category`, `use_cases`, `descriptives`, `featured`, and `sort`.
Preserve the raw response and a normalized shortlist containing at least
`voice_id`, `public_owner_id`, `name`, `gender`, `age`, `accent`,
`descriptive`, `use_case`, `category`, `description`, `preview_url`,
`free_users_allowed`, and usage/popularity fields when present.

Use `POST /v1/similar-voices` when an Embry spoken voice reference, EQ/cadence
reference, or approved target sample is available:

```bash
curl -X POST "https://api.elevenlabs.io/v1/similar-voices" \
  -H "xi-api-key: $ELEVENLABS_API_KEY" \
  -F "audio_file=@/absolute/path/to/embry_reference.wav" \
  -F "top_k=20"
```

The API shortlist is not the winner. It is the candidate pool. The hum workflow
must still run STS bakeoff variants, rank candidates with `hum-reviewer`, and
preserve the human listening gate. If a shared-library voice must be saved to
the account for stable reuse, use `POST /v1/voices/add/{public_user_id}/{voice_id}`
with a deterministic `new_name` and save the request/response receipt.

### E2E Regression Test Mode

When the human frames a `$hum` run as an **E2E test**, the goal is to exercise
the workflow from source discovery/import through final bakeoff and to fix
bugs found along the way. Do not treat the task as merely producing one audio
file. The hum agent owns the loop:

1. Run the full source → stem → guide selection → merge → tempo variants →
   voice search → STS bakeoff → HTML/CSS review page workflow.
2. Capture every blocker with the exact command, path, stderr/stdout excerpt,
   missing dependency, API response, or malformed artifact.
3. Fix deterministic bugs in scripts, payload formatting, file routing, naming,
   HTML generation, or local preview wiring before asking for help.
4. Re-run the failing step after each fix and preserve before/after evidence.
5. Stop only when the final review page exists and is browser-verifiable, or
   when the remaining blocker is external authorization, missing credentials,
   API quota, unavailable source media, or a human listening decision.

#### Mandatory Project-Agent Status Packets

The hum subagent must report status back to the project agent throughout an E2E
run. No exceptions. Do not wait until the final artifact to surface progress,
blockers, or drift.

Send a status packet:

- after source metadata/download completes or fails
- after Demucs/create-stems completes or fails
- after guide segment selection is made
- after tempo variants are created
- after ElevenLabs voice search/selection completes
- after each STS batch completes or fails
- after hum-reviewer ranking completes
- after HTML/CSS review page generation
- after CDP/browser verification
- whenever a deterministic bug is found and again after it is repaired
- before stopping for any external blocker

Each status packet must include these fields:

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

The project agent is the workflow owner. The hum subagent owns execution and
status receipts; it must not leave the project agent to infer progress from
files appearing on disk.

Expected bug classes from prior `$hum` work:

- YouTube metadata/download failures from `yt-dlp` client/runtime drift.
- Demucs output paths or stem names differing from assumptions.
- Guide selection UX choosing the wrong segment or including lyric-heavy/audio
  that should have been removed.
- Tempo transforms that change pitch, clip audio, or produce the wrong duration.
- ElevenLabs multipart payload mistakes, especially `voice_settings` not being
  JSON-encoded.
- Unsupported STS text/style-prompt fields being sent from UI assumptions.
- Voice ID/name mismatches from stale library assumptions.
- Voice-library search skipped even though an API key was available.
- Voice shortlist missing `voice_id`, `public_owner_id`, preview URL, metadata,
  search query, or raw API receipt.
- Missing request receipts, response metadata, or stable version labels.
- HTML review pages that omit source guide, candidate players, paths, settings,
  or ranking/risk notes.
- UI verification that relies on DOM/text only instead of a fresh rendered
  screenshot.

For an E2E regression test, the hum agent should submit a concise bug ledger in
the final review artifact:

```json
{
  "e2e_test": true,
  "source_url": "https://youtu.be/...",
  "fixed_bugs": [
    {
      "symptom": "what failed",
      "root_cause": "why",
      "fix": "what changed",
      "verification": "command/artifact proving the fix"
    }
  ],
  "remaining_blockers": [],
  "final_review_page": "/path/or/url/to/bakeoff.html"
}
```

## Quick Start

```bash
cd skills/hum

# Ensure Orpheus infer is warm (once)
../tts-voice/run.sh docker-up

# Clone Seed-VC once (if missing)
git clone https://github.com/Plachtaa/seed-vc /mnt/storage12tb/tools/seed-vc
cd /mnt/storage12tb/tools/seed-vc && pip install -r requirements.txt

# Preferred: licensed local file + segment window
./run.sh add --song /path/to/song.wav \
  --persona embry \
  --start 00:00:08 \
  --duration 00:00:20 \
  --mood playful,curious \
  --bridges Loyalty,Resilience

./run.sh list --persona embry
./run.sh play hawaiian_war_chant --persona embry
./run.sh sanity
```

## Decomposition Artifact

Before any voice-conversion experiment, isolate the melody/cadence problem into
explicit artifacts:

```bash
./run.sh decompose /path/to/source.wav --out-dir /tmp/hum_decompose --max-duration 60 --json
./run.sh decompose-dataset /path/to/humming_wavs --out-dir /tmp/hum_dataset --max-duration 60 --json
./run.sh decompose-youtube 'https://youtu.be/...' --out-dir /tmp/hum_youtube --limit 1 --max-duration 60 --json
./run.sh build-female-humming-dataset \
  --youtube-url 'https://youtu.be/TbhLGmA-UdE' \
  --out-dir /tmp/female_humming_dataset \
  --youtube-limit 1 \
  --max-duration 60 \
  --json

./run.sh render-female-hum \
  --dataset-index /tmp/female_humming_dataset/decomposition/index.json \
  --out-dir /tmp/female_hum_render_mvp \
  --json

./run.sh generate-elevenlabs-articulations \
  --output-dir /tmp/hwc_articulations \
  --duration-seconds 1.2 \
  --prompt-influence 0.72 \
  --json

./run.sh render-articulated-psola \
  --midi /path/to/melody.mid \
  --samples /tmp/hwc_articulations/samples \
  --output-dir /tmp/hwc_articulated_psola \
  --json
```

This writes:

- `melody.json` — frame-level F0, RMS, and voiced/unvoiced decisions
- `cadence.json` — onset times and onset-strength envelope
- `sound.json` — MFCC/spectral timbre features plus coarse `hum_articulation`
  labels such as `closed_mouth_m`, `nasal_ng_or_open_oo`, and
  `breath_or_unvoiced_noise`. This is **not** literal phoneme recognition;
  humming has no lexical phonemes.
- `text.json` — skipped by default. With `--transcribe`, attempts Whisper word
  timestamps and phonemizer/espeak approximate phones when those optional tools
  are installed. This is not a substitute for Montreal Forced Aligner phone
  boundaries.
- `neutral_hum.wav` — synthetic closed-mouth hum rendered from the extracted
  pitch and energy curves
- `index.json` for dataset and YouTube runs, pointing at each clip's artifacts

`build-female-humming-dataset` currently collects:

- Hugging Face `ylacombe/tiny-humming` rows whose descriptions contain
  `female` or `woman`
- provided YouTube video/playlist/album URLs through `yt-dlp`
- HumTrans metadata as a supervised melody source candidate. It records the
  Hugging Face URLs and sizes for `all_wav.zip`, `all_midi.zip`, and split keys
  but does not auto-download the full WAV zip because it is large.

It writes `manifest.json` for source provenance and then decomposes the source
audio into the artifact set above. This is a female-humming carrier dataset for
analysis, not an Embry voice dataset.

`render-female-hum` is the fastest MVP viability check. It uses decomposed
female-humming `neutral_hum.wav` carriers, selects voiced sample runs by F0,
pitch-shifts/time-stretches them into a short note sequence, and writes:

- `female_hum.wav` — sample-based controllable hum render
- `render_manifest.json` — source sample IDs, source F0, target notes, shift
  amounts, output peak, and explicit limitations

This proves only whether a sample-based carrier approach is worth improving. It
does **not** prove dynamic Embry-like humming, and its output still requires
human listening/non-lexicality review before any cache publication.

Use this artifact to prove the source can be reduced to pitch and cadence before
testing Embry timbre transfer. If `neutral_hum.wav` does not preserve the
melody, stop at decomposition; do not run Seed-VC/Orpheus.

`generate-elevenlabs-articulations` uses ElevenLabs Sound Effects
(`/v1/sound-generation`) to create the required local non-lexical articulation
WAV inventory (`hm`, `m_held`, `m`, `ng`, `oo`, gliss/breath tokens, etc.)
under `samples/`, preserving raw API outputs and request receipts. Prompts use
phonetic texture strings such as `TAH-HOO-WAH`, `TAH-HOO-WAY`, and
`AH, EH, EE, OH, OO` because Sound Effects recreates described sound textures
rather than reading lyrics. It requires `ELEVENLABS_API_KEY`; it does not use a
voice ID.

`render-articulated-psola` is a deterministic diagnostic renderer for a
monophonic MIDI `Melody` track plus that local inventory. It writes a review
bundle including inventory, syllable-note alignment, articulation timeline,
humanized MIDI, dry WAV, QA metrics, and manifest. It is not an Embry voice
model and does not publish to cache. A failed local QA still produces
inspectable artifacts and must not be treated as approval.

If native Hawaiian cadence/phonemes are available as authorized audio, prefer
the existing imported-guide path (`--source-hum-renderer real_hum` or
`elevenlabs_manual` with `--source-hum`) for a full guide track. Common Voice or
other native-speaker source audio should be treated as a cadence/phoneme source
for manual Speech-to-Speech comparison, not as token inventory proof.

## Pipeline (v2 Diagnostic/Fallback)

Bounded artifact node: **produce and gate `source_hum.wav`**, then run a
static/diagnostic voice-conversion attempt. This is not a production path for
dynamic Embry humming.

```
Licensed song segment (local WAV preferred)
    |
    v
[ffmpeg] trim segment
    |
    v
[create-stems] Demucs → vocals.wav (melody transcription input only)
    |
    v
[source_hum_renderer] → source_hum.wav  (GATED before Seed-VC)
    |-- vocal_stem (static fallback/diagnostic for vintage vocal sources)
    |-- ace (manual import; not proven for the dynamic Embry goal)
    |-- suno_manual (import Suno Cover/Voice export — comparison only)
    |-- elevenlabs_manual (import ElevenLabs audio-reference export — comparison only)
    |-- real_hum (human recording via --source-hum)
    |-- old_synth (Basic Pitch → oscillator hum — tests only)
    |-- vocal_stem_diag (diagnostic, not cached by default)
    |
    v
[Orpheus infer] /v1/synthesize → orpheus_ref.wav (cached per persona)
    |
    v
[Seed-VC] source_hum + orpheus_ref → candidate artifact (f0-condition)
    |
    v
[hum-cache] /mnt/storage12tb/media/personas/<name>/hum-cache/ (only after gates)
```

### Static fallback for vintage vocal sources: vocal stem

For vintage vocal and hapa-haole material, the Demucs `vocals.wav` stem is the
least-bad static fallback observed so far. It may preserve timing, phrasing,
slides, and performance shape better than Basic Pitch on these sources, but it
does not establish dynamic Embry humming and remains guide-dependent.

```bash
./run.sh add --song /path/to/song.wav \
  --source-hum-renderer vocal_stem \
  --start 00:00:10 --duration 00:00:20
```

The output must be reviewed as a **non-lexical idle hum** before any cache
publication. Do not treat a persona-converted vocal stem as acceptable if
intelligible source lyrics remain, if the timbre is artifacted, or if the result
only passes numeric checks.

### Manual/import option: ACE Studio

ACE accepts **MIDI + lyrics**. For humming, lyrics are closed-mouth syllables (`mmm`, `hm`, `ng`).
Use ACE only when a dry imported guide sounds natural for the source class and
the human has approved that bounded experiment. ACE/ACE-Step is not a proven
dynamic Embry humming path. Export dry `source_hum.wav`, then:

```bash
./run.sh add --song /path/to/song.wav --source-hum /path/to/ace_hum.wav \
  --source-hum-renderer ace --start 00:00:10 --duration 00:00:20
```

### Comparison path: Suno (manual, not automated default)

1. Upload rights-cleared segment or hummed reference
2. Cover / Voice / Persona with prompt: solo closed-mouth humming, dry vocal, preserve melody
3. Export WAV → `--source-hum` with `--source-hum-renderer suno_manual`

Do **not** wire Suno into the core SCILLM backend (control, ToS,
non-determinism). Suno has not provided reliable melody control or dry,
solo non-lexical Embry humming.

### Comparison path: ElevenLabs audio reference (manual, not automated default)

ElevenLabs does not make `$hum` MIDI-controlled. Treat it as a manual
audio-reference comparison path:

1. Export the verified MIDI/score melody to a simple dry audio reference
   (`.wav` preferred).
2. Upload that audio reference to ElevenLabs Music or Sound Effects if the UI
   supports reference/upload for the selected tool.
3. Prompt for a dry, solo, closed-mouth female alto hum following the uploaded
   melody. Prefer terms such as `closed-mouth humming`, `dry`, `chest voice`,
   `alto`, `resonant`, `non-lexical`, and `no backing instruments`.
4. Export WAV and import it explicitly:

```bash
./run.sh add --song /path/to/song.wav --source-hum /path/to/elevenlabs_hum.wav \
  --source-hum-renderer elevenlabs_manual --start 00:00:10 --duration 00:00:20
```

This path is useful only if the exported WAV passes listening review for:

- melody/cadence following against the verified MIDI/F0
- dry solo vocal quality with no backing bed
- non-lexical humming with no intelligible lyrics
- no claim of Embry/Kristen-Stewart-like identity without authorized data

Do **not** treat an ElevenLabs export as training data unless its license and
terms permit that use. Do **not** treat it as proof that the dynamic `$hum`
goal is solved; it is a carrier/comparison artifact.

### Comparison path: ElevenLabs Speech-to-Speech voice bakeoff

Use this path when the best current strategy is a static guide artifact:
preserve the source hum/chant performance and audition the target voice identity
that best fits the persona. The recommended operator workflow is:

1. **Find candidate source tracks.** Use `/brave-search` for YouTube/web
   discovery when the human has not supplied a track. Search for the song,
   specific performer/version, and likely isolated or clean vocal references.
2. **Ingest or download the source.** Use `/ingest-youtube` for transcript or
   metadata extraction when text/timing is useful. Use `yt-dlp`/existing media
   ingestion only for authorized diagnostic source audio, and keep provenance.
3. **Separate stems.** Run Demucs/create-stems and prefer `vocals.wav` for
   guide-candidate selection. Keep the full mix available as a fallback for
   orientation.
4. **Select and merge clips.** Use a full-file scrubber/waveform workflow. Pick
   useful vocal/hum phrases, remove wrong/acapella/lyric-heavy portions, merge
   ranges, and create a short guide WAV. For initial tests, keep the guide
   under roughly 15-45 seconds.
5. **Create tempo variants only after a guide is close.** For humming, audition
   small tempo changes such as `0.90x`, `0.85x`, and `0.80x`; avoid slowing so
   much that the result becomes ceremonial or dragged unless that is the intent.
6. **Search voices against persona intent.** Query ElevenLabs voices by
   descriptors that match the persona, not generic "best" voices. For Embry-like
   humming, prefer `young adult`, `husky`, `light rasp`, `mid-low/alto`,
   `grounded`, `comforting`, and `dry smirk`; reject `cute`, `quirky`,
   `bubbly`, `anime`, `seductive`, `corporate`, or narrator-heavy voices unless
   the human explicitly chooses that direction.
7. **Run an STS bakeoff.** Hold settings constant for the first comparison and
   vary only `voice_id` and/or guide tempo. Save every API request receipt,
   response metadata, MP3, converted WAV, and voice descriptor.
8. **Render the final bakeoff artifact.** The final output of this workflow is
   an HTML/CSS review page with one player per candidate/version, paths, voice
   IDs, settings, and explicit listen-for/risk notes. The page is the human
   decision surface; do not substitute a prose summary, chart, or hidden
   manifest for it. For UI surfaces, verify with CDP screenshot and write the
   latest marker.
9. **Pick version winners.** The hum agent must rank each bakeoff version using
   the persona rubric, reject obvious mismatches, and name a recommended winner
   and fallback. This ranking must be grounded in the candidate descriptors,
   controlled variables, and human-stated intent; do not call API success or
   waveform validity a winner.
10. **Human listening gate.** The recommended winner is not publishable until
   human listening confirms it. Numeric checks and API success are only artifact
   validity proof. If the human explicitly delegates selection, record that
   delegation in the manifest/review artifact with the chosen version and why.

Recommended STS payload shape:

```python
import json
import os
import requests

VOICE_ID = "selected_voice_id"
INPUT = "/path/to/guide.wav"
OUTPUT = "/path/to/output.mp3"

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
    files = {"audio": ("guide.wav", audio, "audio/wav")}
    response = requests.post(url, headers=headers, data=data, files=files, timeout=180)
response.raise_for_status()
with open(OUTPUT, "wb") as f:
    f.write(response.content)
```

STS controls:

| Control | Use | Risk |
|---------|-----|------|
| `stability` | Lower values allow more performance variation and can preserve smirk/breath; higher values make the output steadier. Start around `0.40`. | Too low can wobble or hallucinate; too high can flatten humor. |
| `similarity_boost` | Keeps the selected ElevenLabs voice identity. Start around `0.80`. | Too high can over-impose the library voice and reduce guide nuance. |
| `style` | Increases the chosen voice's character and expressiveness. Start around `0.45`. | Too high can become theatrical, cute, sultry, or narrator-like. |
| `use_speaker_boost` | Usually keep enabled for stronger voice identity. | Can make the output more polished or less intimate in some voices. |
| `seed` | Optional rough repeatability for bakeoffs. | Do not treat it as deterministic proof. |
| `remove_background_noise` | Consider only when guide artifacts leak into output. Default `false` for hum/chant tests. | Can strip breath, rasp, consonant attack, or hum texture. |
| `file_format` | Set to `other` for WAV guide inputs unless the API requires a more specific enum. | Wrong values may be rejected by the API. |

For fair bakeoffs, change one axis at a time:

- voice search round: same guide and settings, multiple `voice_id`s
- tempo final: same voice/settings, guide variants such as `0.90x`, `0.85x`,
  `0.80x`
- pitch-correction round: same voice/settings/tempo, raw guide versus a lightly
  pitch-centered guide created before STS
- settings polish: same winning voice/tempo, small changes to `stability` or
  `style`

#### Light pitch-correction guide preprocessing

When a Demucs vocal guide is close but human listening flags it as off-pitch,
add pitch preprocessing as a **pre-ElevenLabs bakeoff axis**. Do not post-fix
the ElevenLabs output first; the question is whether a cleaner guide helps STS
track the melody before voice conversion.

Use the conservative guide command:

```bash
./run.sh pitch-correct-guide /path/to/demucs_or_tempo_guide.wav \
  --out-dir /path/to/run/pitch_corrected_guides \
  --max-correction-cents 35 \
  --json
```

This command writes a corrected WAV, `pitch_analysis.json`, and
`pitch_correction_manifest.json`. It uses `librosa` to estimate voiced F0,
computes the guide's median detune to the nearest equal-tempered pitch, caps the
global correction in cents, and writes the corrected guide. It is intentionally
light; it is not hard autotune and it will not repair a bad melody, wrong
segment, heavy lyrics, or a guide that is musically unusable.

For the next STS run, include both raw and corrected guide variants with stable
labels, for example:

- `<track>__jenna__0p85x__rawguide__s0p40__sty0p45`
- `<track>__jenna__0p85x__pitchguide__s0p40__sty0p45`

The review page must expose the guide-preprocessing axis, the applied correction
in cents, the analysis/manifest paths, and a warning that human listening is the
gate. Reject the pitch-corrected branch if it sounds robotic, stepped,
MIDI-like, or loses the vocal smirk/breath.

Versioned bakeoff naming:

- Each generated version must have a stable label such as
  `<track>__<voice_slug>__<speed>__s<stability>__sty<style>`.
- Store the input guide path, source track URL/path, stem path, selected ranges,
  voice ID/name/descriptor, STS settings, output MP3/WAV paths, request ID, and
  history item ID.
- The review page should group versions by comparison axis, not by creation
  time, so the human can quickly choose the best voice/tempo/settings.
- The review page must be plain HTML/CSS or a rendered ux-lab page that can be
  opened in a browser. It must include audio players for every candidate, the
  source guide player, copyable artifact paths, and the ranking/rubric visible
  on the page.
- The agent should provide a ranked recommendation and a short reason, for
  example: `winner: light_rasp_0p85 because it preserves humor and breath while
  avoiding 0.90x rushed humming and 0.80x ceremonial drag`.

Example Embry-like voice-selection rubric:

- Prefer: young adult, husky/light rasp, mid-low or alto, intimate, grounded,
  comforting, dry humor/smirk.
- Reject: cute/quirky/bubbly, anime, seductive/sultry unless chosen by the
  human, corporate/customer-service, old, announcer/narrator-heavy.
- Humming tempo: `0.90x` may feel too fast for natural humming; `0.85x` is a
  common center; `0.80x` is a slower/ceremonial fallback.

### Test-only: old_synth

```bash
./run.sh add --song ... --source-hum-renderer old_synth --melody-audio mix
```

Fail-closed melody gate blocks weak Basic Pitch output unless `--force`.
`old_synth`, `neural_hum`, and DiffSinger-direct style synthesis are diagnostic
only unless new authorized musical voice data changes the evidence.

## Audio-to-MIDI options

**Canonical (this skill):** [Spotify Basic Pitch](https://github.com/spotify/basic-pitch) via
`melody.transcribe_to_midi()` — Python-native, scriptable, already in the hum venv. Used by
`old_synth`, `neural_hum`, and `prepare-ace` (ACE Studio bundle export).

| Option | Role in `/hum` |
|--------|----------------|
| **Basic Pitch** (local) | Default transcription path; output gated by `source_hum_gate` |
| **Manual `--midi PATH`** | Override when Basic Pitch is weak or wrong |
| **Hosted converters** (OpenMusic AI, acestep.io browser tool, etc.) | Manual one-offs only — no documented API worth wiring in yet |
| **Pixazo ACE-Step API** | **Not** audio-to-MIDI — text/prompt → generated audio; wrong tool for melody-locked hum |

### When to skip MIDI entirely

For diagnostic work, use a real melody carrier instead of transcribing when
the carrier is more trustworthy than Basic Pitch:

1. **`vocal_stem`** — static fallback for vintage vocal/hapa-haole sources;
   isolated stems can preserve the sung melody better than Basic Pitch on
   Welk-era harmony and steel-guitar beds, but this is not dynamic humming.
2. **`--source-hum`** — approved ACE Studio, Suno comparison, or human recording
   already encodes melody.
3. **MIDI path** — only when you need `prepare-ace`, `old_synth`/`neural_hum` tests, or a
   hand-corrected `.mid` via `--midi`.

### Source-material quality

Transcription quality depends heavily on the source:

- **Works well:** monophonic lead vocal, solo piano, clean isolated stems.
- **Often fails gate:** full mixes, close harmony, noisy or compressed vintage vocals.

On gate failure, prefer `vocal_stem` or import a guide hum for a bounded
diagnostic artifact; do not assume Basic Pitch alone is publishable or
production-ready for persona cache.

## Commands

| Command | Description |
|---------|-------------|
| `decompose AUDIO` | Extract `melody.json`, `cadence.json`, and `neutral_hum.wav` without cache writes |
| `decompose-dataset PATH` | Batch extract pitch, cadence, sound/phoneme-proxy, and neutral hum artifacts from a local audio dataset |
| `decompose-youtube URL` | Download YouTube video/playlist/album audio with `yt-dlp`, then batch decompose it |
| `build-female-humming-dataset` | Collect female humming source audio from HF/YouTube and decompose it |
| `render-female-hum` | MVP viability render: notes + decomposed female carriers → `female_hum.wav` and `render_manifest.json` |
| `generate-elevenlabs-articulations` | Generate local required articulation WAV inventory with ElevenLabs Sound Effects |
| `render-articulated-psola` | Deterministic PSOLA review bundle from MIDI + local articulation WAV inventory |
| `elevenlabs-sts-bakeoff` | Manual/agent-assisted static guide voice bakeoff; compare voice IDs, tempo variants, and settings through a human review page |
| `add` | Diagnostic v2 pipeline → gated candidate/cache only after review |
| `train` | **Deprecated** — use `/tts-voice finish` |
| `list` | List cached hums |
| `play <track>` | Play via PipeWire |
| `info <track>` | Track metadata |
| `sanity` | Dependency + service checks |

## Options (`add`)

| Flag | Description | Default |
|------|-------------|---------|
| `--song PATH` | Licensed local audio (**preferred**) | — |
| `[url]` | YouTube URL (fallback through `/ingest-youtube`; local `--song` preferred) | — |
| `--persona NAME` | Target persona | `embry` |
| `--start TIME` | Segment start (`ffmpeg -ss`) | `00:00:00` |
| `--duration TIME` | Segment length | `00:00:20` |
| `--source-hum-renderer` | `vocal_stem`, `ace`, `suno_manual`, `elevenlabs_manual`, `real_hum`, `old_synth`, `neural_hum`, `vocal_stem_diag` | `vocal_stem` |
| `--source-hum PATH` | Imported guide hum (ACE/Suno/human) | required for any reviewed candidate; production remains blocked without new data |
| `--midi PATH` | Manual MIDI override (`old_synth` only) | auto Basic Pitch |
| `--melody-audio` | `auto`, `vocals`, or `mix` for transcription | `auto` |
| `--force` | Skip melody/source-hum gates | false |
| `--allow-diagnostic-cache` | Allow caching `vocal_stem_diag` | false |
| `--semi-tone-shift N` | Seed-VC semitone shift | `0` |
| `--diffusion-steps N` | Seed-VC quality/latency | `45` |
| `--mood TAGS` | Comma-separated mood tags | auto |
| `--bridges ATTRS` | Bridge attributes | auto |
| `--json` | JSON output | false |

## Prerequisites

| Component | Purpose | Setup |
|-----------|---------|-------|
| `/tts-voice` | Orpheus LoRA + infer Docker | `finish --speaker <persona>` |
| Orpheus infer | Reference clip generation | `tts-voice/run.sh docker-up` (port **8767**) |
| Seed-VC | Singing voice conversion attempt | `SEEDVC_DIR` → cloned repo |
| `/create-stems` | Vocal isolation | existing skill |
| Basic Pitch | Melody → MIDI | hum `uv sync` |

Environment:

- `ORPHEUS_INFER_URL` — default `http://127.0.0.1:8767`
- `SEEDVC_DIR` — default `/mnt/storage12tb/tools/seed-vc`
- `ELEVENLABS_API_KEY` — required for STS, Sound Effects, Voice Library, and
  similar-voice calls. Store local ElevenLabs credentials in
  `skills/hum/.env_temp`, copied from `skills/hum/.env_temp.example`; the
  wrapper loads project root `.env` first and hum-local `.env_temp` second.
  `.env_temp` is untracked and must never be copied into generated HTML,
  request receipts, review pages, logs, or status packets.

## Storage Layout

```
/mnt/storage12tb/media/personas/<persona>/hum-cache/
  manifest.json
  orpheus_ref.wav           # cached Orpheus VC target (regenerated if missing)
  hawaiian_war_chant.wav
  hawaiian_war_chant.json
```

### Track metadata (v2 fields)

```json
{
  "id": "hawaiian_war_chant",
  "title": "Hawaiian War Chant",
  "pipeline": "orpheus_seedvc_v2",
  "melody_source": "vocal_stem",
  "source_hum_renderer": "vocal_stem",
  "f0_method": "seedvc_f0",
  "diffusion_steps": 45,
  "pitch_shift": 0,
  "forbidden": false
}
```

Legacy RVC tracks remain readable (`pipeline` absent → treated as `rvc_v1`).

## Integration

### /converse

The idler reads `HumCache` manifest and plays the `humming` channel only for
permitted tracks. Production readiness for idle playback is not established by
cache presence alone. A release gate must prove:

- idle eligibility and track selection from the manifest
- immediate interruption/cancellation when the user speaks
- no overlapping playback across consecutive idle periods
- anti-repetition behavior or telemetry for repeated idle intervals
- fail-closed behavior when no permitted hum exists

### Cache publication gates

Before treating a cached hum as publishable or eligible for idle playback,
capture:

- source-license provenance and persona voice authorization
- artifact path, hash, duration, sample rate, channel count, clipping/silence
  checks, and pipeline version
- human listening result with a non-lexicality rubric confirming no intelligible
  source lyrics remain
- atomic cache publication, rollback, purge, and rights-revocation behavior

### /tts-voice (replaces RVC train)

```bash
skills/tts-voice/run.sh finish --job-dir "$JOB" --speaker embry
skills/tts-voice/run.sh docker-up
```

### Diagnostic fallback order

Use this order for bounded diagnostics, not as proof that the dynamic goal is
solved:

1. **`vocal_stem`** for vintage vocal/hapa-haole sources after listening review
2. **ACE export** or **human hum** via `--source-hum` when an imported guide
   sounds natural and non-lexical
3. **Suno or ElevenLabs manual rescue** for one-off comparisons
4. **`old_synth`** only for pipeline tests (`--melody-audio mix`, `--midi corrected.mid`)
5. **`vocal_stem_diag`** only for diagnostics when the static vocal-stem
   fallback is intentionally bypassed

## Safety

- Use **licensed/local** sources for `--song`; YouTube URL is an explicit
  convenience fallback through `/ingest-youtube`, and must fail closed if the
  downloader or credentials are unavailable.
- Kamakawiwoole guard: mark grief-triggering Hawaiian tracks `forbidden: true`.
- Bridge `Fragility` > 0.7 → human review before caching.

## Migration from RVC v1

| v1 (removed) | v2 replacement |
|--------------|----------------|
| `./run.sh train` | `/tts-voice finish` |
| RVC vocal stem conversion | Diagnostic `source_hum.wav` + Seed-VC candidate artifact |
| `--pitch` / `--f0method` | `--semi-tone-shift` / Seed-VC f0-condition |
| Requires RVC Docker | Requires Orpheus infer + Seed-VC |
