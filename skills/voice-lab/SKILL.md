---
name: voice-lab
description: >
  Unified voice workbench: TTS quality eval, waveform visualization, RVC parameter
  sweep, PipeWire recording, follow-along sessions, and voice lesson packages for
  Horus to learn Graham's voice.
allowed-tools: ["Bash", "Read", "Write", "Task"]
triggers:
  - voice lab
  - test voice
  - voice quality
  - compare voices
  - voice evaluation
  - waveform
  - voice iteration
  - voice-lab
  - record audio
  - record voice
  - follow along
  - voice lesson
  - hum lab
  - hum-lab
  - sweep
  - devices
  - audio devices
  - voice training
  - voice learning
  - voice editor
  - edit voice
  - segment editor
metadata:
  short-description: "Unified voice workbench with recording, evaluation, and voice lesson packages"
  author: "Horus"
  version: "0.3.0"

provides:
  - voice-lab
composes: [task-monitor]
disciplines:
  - voice-audio
  - evaluation-quality
---

# voice-lab

Unified voice workbench for the human-AI voice collaboration loop. Combines TTS
quality evaluation, RVC parameter sweep (formerly hum-lab), PipeWire recording,
follow-along sessions, and voice lesson package creation.

## What Horus Receives

A **voice lesson package** per session:
- `SRT` — text + timing (what was said, when)
- `stems` — original artist vocals (from create-stems)
- `.pt file` — current PersonaPlex voice anchor
- `graham.wav` — human performance aligned to the same content
- `prompt.md` — learning guidance (what register, what emotion, what to focus on)
- `training_data.jsonl` — Qwen3-TTS fine-tuning format

## Quick Start

```bash
cd .pi/skills/voice-lab

# List audio devices
./run.sh devices

# Record audio
./run.sh record --device Jabra --duration 30 --output /tmp/test.wav

# Follow along to a movie clip
./run.sh follow --clip scene.wav --srt scene.srt --stem vocals.wav --persona embry

# Create voice lesson package
./run.sh lesson session_output/ --persona embry --source "blade_runner"

# RVC parameter sweep
./run.sh sweep --persona embry --track hawaiian_war_chant

# TTS quality evaluation
./run.sh eval embry --json
```

## Commands

### TTS Quality (original voice-lab)

| Command | Description |
|---------|-------------|
| `test <persona>` | Generate test audio from trained model |
| `waveform <file>` | ASCII or HTML waveform visualization |
| `eval <persona>` | Quality evaluation (similarity, naturalness, artifacts) |
| `compare <persona>` | Compare different checkpoints |
| `iterate <persona>` | Self-improvement loop |
| `status [persona]` | Show voice training status |

### RVC Parameter Sweep (merged from hum-lab)

| Command | Description |
|---------|-------------|
| `sweep` | Full parameter sweep (diagnostic + cross phases) |
| `rank` | Show ranked results from last sweep |
| `preset` | Save or load parameter presets |
| `presets` | List all presets for a persona |

### PipeWire Recording

| Command | Description |
|---------|-------------|
| `devices` | List PipeWire audio devices |
| `record` | Record audio from PipeWire device |

### Follow-Along Sessions

| Command | Description |
|---------|-------------|
| `follow` | Play clip + record simultaneously with SRT karaoke display |
| `edit <ref_audio> <srt>` | Open QML visual editor — dual waveform, record, drag segments |

### Voice Lessons

| Command | Description |
|---------|-------------|
| `lesson <dir>` | Assemble voice lesson package for Horus |
| `lessons` | List all voice lessons for a persona |
| `align <graham> <original> <srt>` | SRT-aligned audio segmentation |
| `gate <audio>` | Per-segment quality gate |

## Follow-Along Recording Editor (QML)

Visual editor for creating aligned voice training data. Opens a PySide6/QML window
with dual waveform display, PipeWire recording, and segment editing.

```bash
# Open editor with reference audio and subtitles
./run.sh edit vocals.wav subtitles.srt

# With custom output directory
./run.sh edit vocals.wav subtitles.srt --output-dir /tmp/session
```

**Features**:
- Dual waveform: reference (blue) + recording (green)
- SRT karaoke text synced to playback position
- Record via PipeWire while hearing reference
- Draggable segment boundaries
- Per-segment MFCC similarity scoring (auto-computed after recording)
- Per-segment playback (P key)
- Segment navigation (Left/Right arrows)
- Saves alignment.json with segment boundaries + similarity scores

**Keyboard shortcuts**: Space=Play/Pause, R=Record, P=Play Segment, Left/Right=Navigate Segments, Ctrl+S=Save

**Requires**: `PySide6>=6.6.0` (optional dependency, install: `uv pip install 'voice-lab[editor]'`)

**UX tokens** (Horus Surface 4 — desk mode):
- Background: `#141414`, Accent: `#4a9eff`, Recording: `#00ff88`
- Font: JetBrains Mono (timestamps), Inter (labels)
- Corner radius: 12px

## Architecture

```
voice-lab/
├── SKILL.md              # This file
├── pyproject.toml         # uv deps
├── run.sh                 # uv-based dispatcher
├── sanity.sh              # Environment checks (13 checks)
│
│ # --- TTS Quality (original) ---
├── voice_lab.py           # Main CLI (typer app, 19 commands)
├── waveform.py            # ASCII + HTML waveform visualization
├── quality.py             # TTS quality metrics (MOS, similarity, artifacts)
│
│ # --- RVC Sweep (from hum-lab) ---
├── sweep.py               # RVC parameter sweep engine
├── evaluate.py            # Timbre/melody/naturalness scoring
├── presets.py             # RVC preset management
│
│ # --- PipeWire Recording ---
├── devices.py             # PipeWire device enumeration
├── capture.py             # PipeWire recording + post-processing
│
│ # --- QML Visual Editor ---
├── editor.py              # Editor launch function
├── editor_bridge.py       # PySide6 QObject bridge (recording, peaks, segments)
├── waveform_painter.py    # QQuickPaintedItem (GPU-composited waveform)
├── qml/
│   ├── Editor.qml         # Main editor UI (dual waveform + transport)
│   ├── SegmentHandle.qml  # Draggable segment boundary handle
│   ├── HorusStyle.qml     # Horus design tokens singleton
│   └── qmldir             # QML module registration
│
│ # --- Follow-Along + Lessons ---
├── session.py             # Follow-along session orchestration
├── alignment.py           # SRT-aligned segmentation + comparison
├── lesson.py              # Voice lesson package creation
├── quality_gate.py        # Per-segment quality gate
│
│ # --- Tests + Sanity ---
├── tests/
│   ├── test_editor.py     # 19 integration tests (headless)
│   └── fixtures/           # Test WAV + SRT
└── sanity/
    ├── pyside6_qml.py     # PySide6 + QtMultimedia sanity
    └── pipewire_duplex.sh  # PipeWire duplex recording
```

## Storage

```
/mnt/storage12tb/media/personas/{persona}/
├── voice-lessons/                # Voice lesson packages
│   └── {source}_{scene}_{date}/
│       ├── manifest.json         # Metadata
│       ├── original_vocals.wav   # Stem
│       ├── graham.wav            # Human performance
│       ├── subtitles.srt         # Timing
│       ├── voice_anchor.pt       # Current embedding
│       ├── alignment.json        # Per-segment timing + scores
│       ├── prompt.md             # Learning guidance
│       └── training_data.jsonl   # Qwen3-TTS fine-tuning format
├── hum-cache/                    # RVC sweep data
│   ├── references/               # Human hum references
│   ├── lab-results/              # Sweep results
│   └── presets/                  # RVC parameter presets
├── qwen3_tts/                    # TTS checkpoints
├── personaplex/voices/           # .pt voice anchors
└── tts_output/                   # Generated audio
```

## Voice Lesson Workflow

```
1. /create-stems → extract vocals from movie/youtube clip
2. ./run.sh follow → play clip + record Graham + SRT display
3. ./run.sh align → segment + compare Graham vs original
4. ./run.sh gate → quality check per segment
5. ./run.sh lesson → assemble package for Horus
6. Horus receives: SRT, stems, .pt, graham.wav, prompt.md, training_data.jsonl
```

## Qwen3-TTS Integration

Voice lessons export to Qwen3-TTS fine-tuning JSONL format:
```json
{"audio": "segments/graham_001.wav", "text": "transcript", "ref_audio": "graham.wav"}
```

The `qwen-tts-demo` web UI can be launched for A/B comparison:
```bash
qwen-tts-demo Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice --ip 0.0.0.0 --port 8000
```

## Acoustic Feedback Mitigation

When using follow-along mode (speaker playing + mic recording):
- **Default**: Warns about speaker-to-mic feedback
- `--headphones`: Route playback to headphones, record from mic
- Use separate devices: play through USB Audio, record from Jabra

## Known Devices

| Device | ID | Type | Notes |
|--------|-----|------|-------|
| Jabra SPEAK 510 | 61/60 | Source/Sink | Default mic, USB full-speed |
| USB Audio Microphone | 55 | Source | Secondary mic |
| Cam Link 4K | 63 | Source | HDMI capture |

## AEC Module Warning

The OpenClaw `99-openclaw-aec.conf` echo-cancel module causes ALSA XRUNs on USB
full-speed devices like the Jabra SPEAK 510. The recording commands detect this
and warn if it's active.
