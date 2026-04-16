# Embry Humming Pipeline — Implementation Plan

## Vision

Embry hums songs she "likes" while she works — in her own voice, selected by
Federated Taxonomy bridge attributes matching her current emotional state.
When she or the human starts talking, the humming ducks to zero and conversation
takes over. PersonaPlex handles short vocal textures (backchannels: "mmm",
"mm-hmm") natively; actual melodies are pre-processed external audio mixed
through the AudioMixer.

## Why Two Layers

Research confirms no production voice model can generate melodic humming natively.
Moshi's Mimi codec is speech-optimized — it strips musical information.

| Layer | What | How | Latency |
|-------|------|-----|---------|
| **PersonaPlex native** | Backchannels, thinking sounds | Text tokens: `[mm-hmm]`, `[soft hum]` | Real-time (~200ms) |
| **External audio** | Actual melodies, song humming | Pre-processed WAV via mixer | Zero (pre-cached) |

The mixer already ducks humming to 0% when speech starts. This is built.

## Existing Tools (What We Have)

| Skill | Purpose | Status |
|-------|---------|--------|
| `/ingest-youtube` | Download YouTube audio | Working |
| `/create-stems` | Demucs stem separation (vocals, drums, bass, etc.) | Working, 46 trained models |
| `/learn-artist` | Train RVC voice models from artist vocals | Working, 46 models trained |
| `/create-music` | RVC inference (`rvc-infer` command) | Working |
| `/consume-music` | Music registry + HMT taxonomy | Working, 2,844 tracks |
| `/converse` | Orchestrator with AudioMixer + ducking | Working |

## What's Missing

1. **Embry RVC voice model** — 46 artist models exist, but no Embry model
2. **Hum-cache pipeline** — No automated: consume → stem → convert → cache flow
3. **Hawaiian War Chant in library** — Not yet ingested

## Pipeline: Song → Embry Humming

```
┌─────────────────┐     ┌──────────────┐     ┌──────────────────┐
│  ingest-youtube  │────▶│ create-stems │────▶│  RVC inference   │
│  (yt-dlp audio)  │     │  (Demucs 6s) │     │  (Embry model)   │
└─────────────────┘     └──────────────┘     └──────────────────┘
        │                      │                       │
    full mix              vocals.wav            embry_vocals.wav
                                                       │
                                                       ▼
                                              ┌──────────────────┐
                                              │    hum-cache     │
                                              │  /mnt/storage12tb│
                                              │  .../hum-cache/  │
                                              └──────────────────┘
                                                       │
                                                       ▼
                                              ┌──────────────────┐
                                              │  converse idler  │
                                              │  AudioMixer ch:  │
                                              │  "humming" 0.6   │
                                              │  → ducks on talk │
                                              └──────────────────┘
```

## Implementation Steps

### Step 0: Train Embry RVC Voice Model (one-time, ~2 hours)

**Problem:** No Embry RVC model exists. 43 WAV files (~153MB) of synthesized
speech exist at `/mnt/storage12tb/media/personas/embry/tts_output/`.

**Approach:** Use `/learn-voice` or `/learn-artist` with Embry's existing
TTS output as training data. The voice samples are Qwen3-TTS synthesized, which
is fine for RVC training — the model learns timbre, not content.

```bash
# Option A: learn-artist (has the full pipeline)
cd .pi/skills/learn-artist
./run.sh train "embry" \
  --source-dir /mnt/storage12tb/media/personas/embry/tts_output \
  --category voice \
  --epochs 200

# Option B: learn-voice (may have persona-specific features)
cd .pi/skills/learn-voice
./run.sh train "embry" \
  --samples /mnt/storage12tb/media/personas/embry/tts_output/*.wav
```

**Output:** `/mnt/storage12tb/media/music/rvc-models/voice/embry/`
- `embry-infer.pth` — inference weights
- `embry.index` — FAISS retrieval index

### Step 1: Ingest Hawaiian War Chant

```bash
cd .pi/skills/ingest-youtube
./run.sh "https://youtu.be/Dordpe3KX_I"
```

This downloads audio. The video is "Hawaiian War Chant" by the Lennon Sisters —
a nonsense Hawaiian song that fits Embry's Linguistics degree persona.

### Step 2: Stem Separation

```bash
cd .pi/skills/create-stems
./run.sh separate \
  --mix /path/to/downloaded/hawaiian_war_chant.wav \
  --out /tmp/stems/hawaiian-war-chant \
  --instrument vocals
```

**Output:** `vocals.wav` — isolated Lennon Sisters vocal performance.

### Step 3: Convert Vocals to Embry's Voice

```bash
cd .pi/skills/create-music
./run.sh rvc-infer \
  --input /tmp/stems/hawaiian-war-chant/htdemucs_6s/*/vocals.wav \
  --model embry \
  --output /mnt/storage12tb/media/personas/embry/hum-cache/hawaiian_war_chant.wav
```

**Result:** Hawaiian War Chant sung in Embry's voice.

### Step 4: Add to Hum Cache with Taxonomy

Store the converted audio with metadata for the idler's taxonomy-driven selection:

```
/mnt/storage12tb/media/personas/embry/hum-cache/
├── hawaiian_war_chant.wav          # Embry-voiced audio
├── hawaiian_war_chant.json         # Metadata:
│   {
│     "title": "Hawaiian War Chant",
│     "artist": "Lennon Sisters",
│     "source_video": "Dordpe3KX_I",
│     "bridge_attributes": ["Loyalty", "Resilience"],
│     "mood": ["playful", "curious", "neutral"],
│     "persona_connection": "Linguistics degree, Hawaiian cultural ties",
│     "forbidden": false,
│     "duration_s": 120
│   }
└── manifest.json                   # Index of all cached hums
```

### Step 5: Wire Hum Cache into Converse Idler

The idler (`idler.py`) already has a `MusicSelector` that does taxonomy-driven
music selection via graph traversal. Update it to:

1. Check hum-cache first (Embry-voiced audio > raw music)
2. Fall back to consume-music registry for discovery
3. Play through mixer channel "humming" at volume 0.6
4. Mixer ducks to 0% when speech channel activates

**Already built in converse.py:**
```python
# mixer.duck() already handles this
if self.state == ConversationState.SPEAKING:
    self.mixer.duck("speech")  # humming → 0%, background → 10%
```

## Ducking Behavior (Already Implemented)

The AudioMixer in `/converse` already implements:

| Event | Humming Volume | Speech Volume |
|-------|---------------|---------------|
| Idle (>5s silence) | 60% | 0% |
| Embry speaking | **0%** (ducked) | 100% |
| Human speaking (barge-in) | **0%** (ducked) | 0% (stopped) |
| Embry listening | 0% | 0% |

**"Stop humming when conversation starts"** — this is already handled by
`mixer.duck("speech")` which ducks the humming channel to 0% with a 200ms fade.

## PersonaPlex Native Layer (Backchannels)

For short non-melodic vocal textures, PersonaPlex handles these via text tokens
in the idler:

```python
behavior_tokens = {
    "backchannel": "[mm-hmm]",    # Moshi learned from Fisher corpus
    "sigh": "[sigh]",
    "hum_tune": "[soft hum]",     # Short tonal sound, not a melody
    "self_talk": "",               # Natural text
}
```

These are ~0.5-2 second sounds generated in real-time by PersonaPlex.
They complement the external humming (which is full melodies).

## Hawaiian War Chant: Why It Works for Embry

- **Nonsense Hawaiian syllables** — fits her Linguistics degree (phonological play)
- **The Lennon Sisters' arrangement** — mid-century Americana meets Polynesian
  kitsch, which maps to Embry's Charleston-Hawaiian-Yale code-switching
- **Bridge attributes:** Loyalty (cultural tradition), Resilience (enduring folk form)
- **Taxonomy connection:** The song's playful register matches Embry's PLAYFUL
  emotional state, providing contrast when she shifts to FOCUSED during work

## Future: General Pipeline

Once this works for Hawaiian War Chant, generalize:

```bash
# Add any song Embry "likes" to her humming library
./run.sh add-hum "https://youtu.be/VIDEO_ID" --mood playful
```

This would:
1. Download audio (ingest-youtube)
2. Stem vocals (create-stems)
3. Convert to Embry's voice (create-music rvc-infer)
4. Tag with Federated Taxonomy bridges
5. Add to hum-cache manifest
6. Available immediately in next converse session

## Open Questions

1. **Vocal quality:** Will RVC conversion of the Lennon Sisters' close harmony
   sound natural as a single-voice Embry performance? May need to isolate
   a single voice track or accept the ensemble quality.

2. **Humming vs singing:** Should we process the vocal to sound more like
   humming (low-pass filter, reduce consonants) or keep it as full singing?

3. **Segment length:** Should we split the song into 5-10 second fragments
   for varied playback, or play the full track?

4. **Kamakawiwoole guard:** The consume-music registry marks certain Hawaiian
   music as FORBIDDEN for Embry (triggers grief). Hawaiian War Chant is safe
   (playful, not sentimental), but the guard needs to remain active.
