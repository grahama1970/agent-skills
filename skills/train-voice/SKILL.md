---
name: train-voice
description: >
  Unified voice training for personas. Orchestrates PersonaPlex (real-time conversation)
  and Qwen3-TTS (recorded narration) from a single workflow. Uses /interview for
  collaborative voice design when source material is unavailable.
allowed-tools: [Bash, Read, Write, Task]
triggers:
  - train voice
  - create voice
  - voice for persona
  - persona voice
  - train-voice
  - give voice to
  - voice training
  - design voice
metadata:
  short-description: "Unified voice training: PersonaPlex + Qwen3-TTS with interview collaboration"
  author: "Horus"
  version: "1.0.0"

provides:
  - train-voice
composes:
  - task-monitor
  - agentic-evals
disciplines:
  - ml-training
  - voice-audio
---

# train-voice

Unified voice training for personas. Creates both real-time conversation capability
(PersonaPlex) and recorded narration (Qwen3-TTS) from a single workflow.

## Architecture

```
                         /train-voice
                              |
          +-------------------+-------------------+
          |                                       |
     Known Voice                            Unknown Voice
   (source exists)                     (historical/obscure)
          |                                       |
          v                                       v
  +-----------------+                   +-------------------+
  | Auto-Discovery  |                   | /interview        |
  | - YouTube       |                   | Voice Design      |
  | - Audiobooks    |                   | Collaboration     |
  | - Podcasts      |                   +-------------------+
  +-----------------+                            |
          |                   +------------------+
          v                   v
  +-----------------------------------------+
  |         Reference Audio Available        |
  +-----------------------------------------+
          |                   |
          v                   v
  +-----------------+  +-----------------+
  | PersonaPlex     |  | Qwen3-TTS       |
  | Speaker Embed   |  | Fine-tuning     |
  | (.pt files)     |  | (LoRA training) |
  +-----------------+  +-----------------+
          |                   |
          v                   v
  +-----------------------------------------+
  |         Persona Ready for Voice         |
  |  Real-time: PersonaPlex embeddings      |
  |  Recorded:  Qwen3-TTS trained model     |
  +-----------------------------------------+
```

## Two Paths: Known vs Unknown Voice

### Path 1: Known Voice (Source Material Exists)

For personas where we have audio:
- YouTubers, podcasters, public speakers
- Actors (for fictional character inspiration)
- Musicians, audiobook narrators

```bash
./run.sh train "Embry" --references "Hailee Steinfeld,Kristen Stewart"
```

### Path 2: Unknown Voice (No Source Material)

For personas where we must **infer** the voice:
- Historical figures (where did they live? what era?)
- Obscure experts (no recordings exist)
- Fictional characters without actor reference

This triggers `/interview` for collaborative voice design:

```bash
./run.sh design "Marcus Aurelius"
# Opens interview wizard for voice collaboration
```

## Quick Start

```bash
cd .pi/skills/train-voice

# Train voice from known references (fictional character)
./run.sh train "Embry" \
  --type fictional \
  --references "Hailee Steinfeld:confident,Kristen Stewart:uncertain"

# Design voice for historical figure (triggers interview)
./run.sh design "Benjamin Franklin"

# Check training status
./run.sh status "Embry"

# Test voice output
./run.sh test "Embry" --text "The authentication layer is straightforward."
```

## Voice Design Interview (for Unknown Voices)

When source material doesn't exist, `/interview` guides collaborative voice design:

### Interview Questions

1. **Geographic Origin**
   - "Where was this person born/raised?"
   - Options with regional accents mapped

2. **Lifespan**
   - "What years did they live?" (e.g., 1706-1790)
   - Enables age-correlated event mapping

3. **Formative Youth Events** (ages ~5-25)
   - "What shaped them in childhood/youth?"
   - Creates **foundational** voice texture (always subtly present)
   - Options: Loss of parent, war witnessed young, poverty, privileged education

4. **Prime Years Events** (ages ~25-50)
   - "What defined their prime years?"
   - Creates **defining** voice identity (conscious character)
   - Options: War, revolution, discovery, political power, loss of loved one

5. **Later Life Events** (ages 50+)
   - "What marked their later years?"
   - Creates **current** demeanor (most audible layer)
   - Options: Reflection, continued activism, illness, recognition, tragedy

6. **Social Class/Education**
   - "What was their background?"
   - Affects formality, vocabulary complexity

7. **Personality Traits**
   - "How would you describe their demeanor?"
   - Maps to pacing, energy, hesitation patterns

8. **Emotional Coloring**
   - "What emotional undertones should the voice carry?"
   - Derived from life experiences and events
   - Options: hopeful, stoic, urgent, wry, weathered, passionate

9. **Voice Reference** (optional)
   - "Any modern actor/speaker who might sound similar?"
   - Can paste images of reference actors

### Age-Correlated Event Impact

Events at different life stages create layered emotional texture:

| Life Stage | Voice Impact | Example |
|------------|--------------|---------|
| **Youth (5-25)** | Foundational - always subtly present | Loss of parent at 12 → underlying grief, guarded |
| **Prime (25-50)** | Defining - conscious identity | Revolution at 35 → conviction, hopeful intensity |
| **Later (50+)** | Current - most audible | Teaching at 60 → patient warmth |

Example for Benjamin Franklin:
- **Youth**: Self-educated in Boston → scrappy determination, no-nonsense
- **Prime**: Revolution, diplomacy → conviction, wit as armor
- **Later**: Reflection, mentoring → wise warmth, wry humor

This layered approach creates voices with **depth** rather than flat characterizations.

### Interview Output

```json
{
  "persona": "Benjamin Franklin",
  "voice_design": {
    "geographic_origin": "Boston, later Philadelphia",
    "time_period": "18th century colonial",
    "social_class": "Self-made polymath",
    "personality": ["witty", "avuncular", "measured"],
    "inferred_accent": "Colonial American (educated)",
    "modern_reference": "Morgan Freeman (wisdom), Sam Elliott (avuncular)",
    "register_map": {
      "default": "Freeman-inspired",
      "joking": "lighter, quicker",
      "serious": "slower, more gravitas"
    },
    "historical_context": {
      "major_events": [
        "American Revolution (shaped hopeful, revolutionary cadence)",
        "Smallpox epidemics (mortality awareness in tone)",
        "French court diplomacy (playful sophistication)"
      ],
      "voice_coloring": "Weathered optimism - seen hardship but believes in progress",
      "emotional_undertones": ["hope", "pragmatism", "wry humor"]
    }
  }
}
```

### Historical Context Shapes Voice

Events during a persona's lifetime add emotional texture:

| Persona | Key Events | Voice Impact |
|---------|-----------|--------------|
| Marcus Aurelius | Antonine Plague, Marcomannic Wars | Stoic fatigue, measured wisdom |
| Benjamin Franklin | Revolution, Enlightenment | Hopeful urgency, wit as armor |
| Ada Lovelace | Industrial Revolution | Wonder + precision |
| Frederick Douglass | Slavery, Civil War | Moral fire, controlled power |

The interview asks:
- "What major events shaped their worldview?"
- "How might these experiences color their speech?"
- "Were they hopeful, weathered, urgent, resigned?"

See [VOCAL_BIOMARKERS.md](references/VOCAL_BIOMARKERS.md) for research-backed vocal biomarkers, suppression detection, defense mechanisms, grief processing, and cultural emotional norms.

---

## Commands

### train

Train voice from known references.

```bash
./run.sh train <persona> [options]

Options:
  --type TYPE             fictional, learning, narrator (default: fictional)
  --references REFS       Comma-separated "Actor:register" pairs
  --skip-personaplex      Skip PersonaPlex embedding extraction
  --skip-qwen3            Skip Qwen3-TTS training
  --epochs N              Qwen3-TTS training epochs (default: 5)
  --background            Run training in background
```

### design

Collaborative voice design for unknown voices.

```bash
./run.sh design <persona> [options]

Options:
  --mode MODE             tui or html (default: auto)
  --output FILE           Save interview results to file
  --skip-train            Only design, don't auto-train
```

### status

Check voice training status.

```bash
./run.sh status <persona>

# Output:
# Persona: Embry
# PersonaPlex:
#   confident: embry_confident.pt (256-dim) [READY]
#   uncertain: embry_uncertain.pt (256-dim) [READY]
# Qwen3-TTS:
#   Model: embry_qwen3_1.7b
#   Epochs: 3/5
#   Status: TRAINING (PID 12345)
#   ETA: ~45 minutes
```

### test

Generate test audio from trained voice.

```bash
./run.sh test <persona> --text "Hello, world" --output test.wav

Options:
  --text TEXT             Text to synthesize
  --register REG          Voice register (confident, uncertain, etc.)
  --output FILE           Output WAV file
  --personaplex           Use PersonaPlex (real-time mode)
  --qwen3                 Use Qwen3-TTS (recorded mode, default)
```

### list

List all voices with training status.

```bash
./run.sh list

# Output:
# Persona          PersonaPlex  Qwen3-TTS    Status
# ────────────────────────────────────────────────────
# Embry            2 registers  1.7B/5ep     READY
# Horus            1 register   1.7B/10ep    READY
# Marcus Aurelius  -            -            DESIGNED (awaiting refs)
```

## Storage Layout

```
/mnt/storage12tb/media/personas/<persona>/
├── voice_refs/                    # Downloaded reference clips
│   ├── <actor_slug>/
│   │   └── clips/
│   │       ├── clip_01.wav
│   │       └── clip_02.wav
├── personaplex/                   # Real-time conversation
│   ├── voices/
│   │   ├── <persona>_confident.pt
│   │   └── <persona>_uncertain.pt
│   ├── configs/
│   │   └── emotional_mannerisms.yaml
│   └── prompts/
│       └── <persona>_prompts.yaml
├── qwen3_tts/                     # Recorded narration
│   ├── embry_manifest_qwen3.jsonl
│   ├── model/
│   │   └── checkpoint-epoch-N/
│   └── training.log
├── tts_training/                  # Raw training data
│   ├── <persona>_combined.jsonl
│   └── <persona>_<register>.jsonl
└── voice_design.json              # Interview results (if designed)
```


See [INTERVIEW_GUIDE.md](references/INTERVIEW_GUIDE.md) for interview integration, geographic accent database, workflow examples, and troubleshooting.
