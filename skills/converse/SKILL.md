---
name: converse
description: >
  Real-time two-way voice conversation with persona. Full-duplex audio via
  PersonaPlex (Moshi-based) with barge-in, backchannels, emotional state
  tracking, humming (Federated Taxonomy-driven song selection from /consume-music,
  episodic memory, and dream motifs), and conversation steering. Supports
  Discord voice, KDE PipeWire, and Horus WebRTC surfaces.
allowed-tools: [Bash, Read]
triggers:
  - converse
  - voice conversation
  - talk to embry
  - real-time voice
  - full duplex
  - barge-in
  - humming
  - conversation session
  - voice chat
  - two-way audio
metadata:
  short-description: "Real-time two-way voice conversation with persona"
  author: "Horus"
  version: "0.1.0"

provides:
  - converse
composes:
  - task-monitor
  - agentic-evals
disciplines:
  - voice-audio
  - persona-simulation
---

# converse - Real-Time Two-Way Voice Conversation

Full-duplex voice conversation engine for personas. Not chatbot request-response —
real conversation with interruptions, backchannels, emotional state, humming, and
natural idle behaviors.

## Architecture

```
ConversationOrchestrator
├── Listener  (VAD + Whisper STT, barge-in detection)
├── Thinker   (EmbrySPARTAIntern + memory + mood + steering)
├── Speaker   (PersonaPlex TTS with register switching)
├── Idler     (humming, self-talk, backchannels, sighs)
├── Emotion   (state machine with bridge attribute modifiers)
├── Mixer     (audio ducking: speech > humming > background)
└── Surface   (Discord / KDE PipeWire / Horus WebRTC)
```

## Quick Start

```bash
cd .pi/skills/converse

# Check everything is wired up
./run.sh sanity

# Start conversation on KDE desktop
./run.sh start --surface kde --persona embry

# With scenario attached
./run.sh start --surface kde --persona embry \
    --scenario ../surf-qml/scenarios/design_review.yaml

# Recorded mode (Qwen3-TTS fallback, not live PersonaPlex)
./run.sh start --surface kde --mode recorded

# Discord voice
./run.sh start --surface discord
```

## State Machine

```
IDLE → (user speaks) → LISTENING → (VAD end-of-turn) → THINKING
THINKING → (response ready) → SPEAKING → (utterance complete) → IDLE
SPEAKING → (barge-in: >300ms user speech) → INTERRUPTED → LISTENING
IDLE → (>5s silence) → idler kicks in (humming, self-talk, backchannels)
```

## Humming: Federated Taxonomy Graph Traversal

Song selection for humming is not random. It uses multihop graph traversal:

1. **Current emotion** → active bridge attributes (Precision, Fragility, Resilience, etc.)
2. **Bridge attributes** → query episodic memory (`/episodic-archiver`) for resonant past experiences
3. **Bridge attributes** → query dream motifs (`/create-movie` → `horus-dreams` scope) for subconscious associations
4. **All of the above** → filter `/consume-music` registry for matching tracks per persona preferences
5. **Score candidates** by bridge overlap + episodic resonance + dream resonance
6. **Respect forbidden list** (persona-specific trauma triggers, e.g., Kamakawiwoole for Embry)

Two-layer humming approach:
- **PersonaPlex native**: Voice prompt conditioning with `[soft hum]`, `[mm]` tokens (Moshi fine-tuning)
- **External music mixing**: Pre-generated fragments via `/create-music` MusicGen → RVC inference with Embry's voice model

## Emotion State Machine

Tracks persona emotional state with bridge attribute modifiers:

| State | Bridge Effect |
|-------|--------------|
| CURIOUS | Precision +0.1, Stealth -0.1 |
| FRUSTRATED | Fragility +0.15, Corruption +0.05, Resilience -0.1 |
| MELANCHOLIC | Fragility +0.2, Stealth +0.1, Corruption +0.05 |
| OVERWHELMED | Fragility +0.25, Precision -0.15, Resilience -0.15 |

Avoidance triggers (Embry-specific):
- **Hard**: james, december 2023, ku'uipo, kamakawiwoole → deflection + anxious state
- **Soft**: cabernet, steak salad, new haven winter → register shift to uncertain

## Components

### Listener (`listener.py`)
- WebRTC VAD (aggressiveness=2) with energy-based fallback
- Whisper large-v3 STT via faster-whisper or CLI
- Barge-in: >300ms speech during playback → interrupt persona

### Thinker (`thinker.py`)
- EmbrySPARTAIntern for grounded domain responses
- Memory recall (persona + ToM scopes)
- Persona journal mood context
- Conversation steering presets
- Avoidance trigger deflection
- Interruption acknowledgment weaving

### Speaker (`speaker.py`)
- PersonaPlex streaming TTS (live mode)
- Qwen3-TTS / espeak-ng fallback (recorded mode)
- Register-aware voice anchor selection (.pt files)
- Sentence-boundary splitting for streaming

### Idler (`idler.py`)
- Weighted behavior pool: backchannel (30%), self-talk (20%), hum (15%), sigh (10%), ambient (5%), silence (20%)
- Cooldown per behavior to avoid repetition
- Music selection via MusicSelector (Federated Taxonomy graph traversal)

### Mixer (`mixer.py`)
- Named channels: speech, humming, background
- Volume ducking with fade transitions
- Rules: speech ducks humming to 0%, background to 10%; barge-in ducks everything

### Surfaces (`surfaces.py`)
- Discord: Opus 48kHz via discord_voice_client
- KDE: PipeWire pw-record/pw-play at 48kHz
- Horus: WebSocket to gateway voice endpoint

## Session Storage

All session data persists to `/mnt/storage12tb/converse-sessions/<persona>/<session_id>/`:
- `transcript.jsonl` — timestamped turns with taxonomy tags
- `emotion_log.json` — emotion state transitions over time
- `session_summary.json` — duration, turn count, mood arc

## Dependencies

### Required
- Python 3.10+, numpy, loguru
- PipeWire tools (pw-record, pw-play) for KDE surface

### Optional (graceful degradation)
- webrtcvad — falls back to energy-based VAD
- faster-whisper — falls back to whisper CLI
- PersonaPlex — falls back to Qwen3-TTS → espeak-ng
- EmbrySPARTAIntern — falls back to Ollama llama3.1:8b
- websockets — needed for Horus surface only

### Skill Dependencies
- `/memory` — EmbrySPARTAIntern, persona_journal, MemoryClient
- `/common` — memory_client
- `/surf-qml` — taxonomy extraction pattern
- `/train-convo-steering` — steering presets
- `/consume-music` — music registry for humming
- `/episodic-archiver` — past experiences for song selection
- `/create-movie` — dream motifs for subconscious music associations
- `/create-music` — RVC inference for Embry-voice humming
- `/create-persona` — PersonaPlex config, detect_register()

## Preparation Steps (Before First Run)

1. **Train Embry humming voice model** via `/learn-voice`
2. **Pre-generate melodic fragments** via `/create-music` MusicGen → RVC
3. **Create humming voice prompt (.pt)** for PersonaPlex native backchannels
4. **Fine-tune Moshi LoRA** with labeled humming data (`[humming]`, `[mm]`, `[soft hum]` tokens)

## Troubleshooting

Run `./run.sh sanity` to check all dependencies and assets.

Common issues:
- **No audio**: Check PipeWire is running (`pw-cli info`)
- **VAD too sensitive**: Increase aggressiveness in listener.py (0-3)
- **Slow transcription**: Ensure CUDA available for faster-whisper
- **No humming**: Check consume-music registry has tracks and hum-cache exists
