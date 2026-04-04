## Interview Integration

### Voice Design Question Types

The `/interview` skill is extended with voice-specific question types:

```json
{
  "id": "voice_reference",
  "header": "Voice",
  "text": "Select actors whose voice might inspire this character:",
  "type": "voice_reference",
  "options": [
    {
      "label": "Morgan Freeman",
      "description": "Warm, authoritative, measured",
      "image": "actors/morgan_freeman.jpg",
      "audio_sample": "samples/freeman_sample.mp3"
    },
    {
      "label": "Sam Elliott",
      "description": "Deep, folksy, trustworthy",
      "image": "actors/sam_elliott.jpg"
    }
  ],
  "allow_custom_image": true,
  "multi_select": true
}
```

### Geographic Accent Database

Built-in knowledge of regional accents:

| Region | Era | Characteristics | Modern Reference |
|--------|-----|-----------------|------------------|
| Charleston, SC | 1800s | Softened R's, musical cadence | Kevin Spacey (House of Cards) |
| Boston | Colonial | Non-rhotic, broad A | JFK recordings |
| Philadelphia | Colonial | Rhotic, less formal | Period film references |
| London | Victorian | Received Pronunciation | Helena Bonham Carter |
| Hawaii Pidgin | Modern | Mixed syntax, unique vocabulary | Local recordings |

## Workflow: Fictional Character (Embry Example)

```bash
# 1. Define references (done during /create-persona)
./run.sh train "Embry" \
  --type fictional \
  --references "Hailee Steinfeld:confident,Kristen Stewart:uncertain"

# 2. Auto-discovers and downloads clips from YouTube
# 3. Extracts PersonaPlex embeddings (.pt files)
# 4. Prepares Qwen3-TTS training data (JSONL)
# 5. Runs Qwen3-TTS training in background
# 6. Reports status

# Check progress
./run.sh status "Embry"
```

## Workflow: Historical Figure (Marcus Aurelius Example)

```bash
# 1. Start voice design interview
./run.sh design "Marcus Aurelius"

# Interview wizard opens:
# Q1: Where was Marcus Aurelius from?
#     > Rome, Italy (with Greek education)
#
# Q2: What was his speaking context?
#     > Philosophical discourse, leadership
#
# Q3: What modern voice might fit?
#     > [User pastes image of Richard Harris]
#     > Reason: "Gravitas but warmth"
#
# Q4: Any accent considerations?
#     > Classical Latin influence, educated Greek

# 2. Interview saves voice_design.json
# 3. System suggests: "Download Richard Harris clips for reference?"
# 4. If yes, proceeds to training
```

## Integration with Other Skills

| Skill | Integration |
|-------|-------------|
| `/create-persona` | Gets voice_references from persona definition |
| `/interview` | Voice design collaboration for unknown voices |
| `/tts-train` | Qwen3-TTS training infrastructure |
| `/create-persona` (personaplex.py) | PersonaPlex embedding extraction |
| `/discover-movies` | Find actor filmography for references |
| `/ingest-youtube` | Download reference clips |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VOICE_STORAGE` | /mnt/storage12tb/media/personas | Base storage path |
| `PERSONAPLEX_CACHE` | ~/.cache/personaplex | Download cache |
| `QWEN3_MODEL` | Qwen/Qwen3-TTS-12Hz-1.7B-Base | Base model for training |

## Examples

### Train Fictional Character

```bash
# Embry: dual-register voice (confident + uncertain)
./run.sh train "Embry" \
  --type fictional \
  --references "Hailee Steinfeld:confident,Kristen Stewart:uncertain" \
  --epochs 5 \
  --background
```

### Design Historical Voice

```bash
# Marcus Aurelius: no recordings exist
./run.sh design "Marcus Aurelius"
# Interview guides through geographic/era inference
```

### Train Learning Persona

```bash
# Dan Kieft: YouTuber with existing content
./run.sh train "Dan Kieft" \
  --type learning \
  --source youtube:@DanKieft \
  --skip-personaplex  # Only need Qwen3 for narration
```

### Batch Training

```bash
# Train all fictional personas
./run.sh train-batch \
  --type fictional \
  --from-file personas.txt \
  --background
```

## Troubleshooting

### No Reference Clips Found

```bash
# Manually provide clip paths
./run.sh train "Embry" \
  --clips /path/to/clips/*.wav \
  --register confident
```

### Training Out of Memory

```bash
# Use smaller model
./run.sh train "Embry" \
  --qwen3-model Qwen/Qwen3-TTS-12Hz-0.6B-Base \
  --batch-size 1
```

### Interview Mode Not Opening

```bash
# Force TUI mode
./run.sh design "Marcus Aurelius" --mode tui
```

## Files

```
.pi/skills/train-voice/
├── SKILL.md              # This file
├── run.sh                # Entry point
├── train.py              # Main training orchestrator
├── design.py             # Voice design interview generator
├── accents.py            # Geographic accent database
├── interview_questions/  # Voice design question templates
│   ├── geographic.json
│   ├── era.json
│   ├── personality.json
│   └── reference.json
├── pyproject.toml
└── sanity.sh
```
