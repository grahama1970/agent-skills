## Persona Schema

```python
@dataclass
class Persona:

### Historical Context Fields (v7)

New fields for deep persona modeling and voice design:

#### Family Structure

```yaml
family_structure:
  birth_order: eldest  # eldest, middle, youngest, only
  siblings: 2
  parent_loss_age: 12  # if applicable
  family_size: large  # small, medium, large
  socioeconomic_class: middle  # lower, middle, upper
  family_stability: unstable  # stable, unstable, traumatic
```

#### Religion/Spirituality

```yaml
religion:
  tradition: Buddhist
  denomination: Zen  # Theravada, Mahayana, Catholic, Protestant, etc.
  religiosity: 0.7  # 0.0 = cultural only, 1.0 = devout/practicing
  religious_era: Victorian  # Era-specific religious norms
  emotional_expression_norms: suppressed  # encouraged, moderate, suppressed
```

#### Cultural Context

```yaml
cultural_context:
  birth_region: "Rome, Italy"
  era: "2nd century CE"
  cultural_tradition: Greco-Roman
  emotional_display_rules: "Stoic - controlled expression"
  grief_expression_norms: "public mourning rituals but private suffering"
```

#### Life Events (Age-Correlated)

Events at different ages create layered emotional texture in voice:

```yaml
life_events:
  formative:  # ages 5-25 - always subtly present
    - age: 12
      event: "father's death"
      voice_impact: "underlying grief, guarded"
  prime:  # ages 25-50 - defines conscious identity
    - age: 35
      event: "became emperor"
      voice_impact: "authoritative weight"
  later:  # ages 50+ - most audible layer
    - age: 58
      event: "writing Meditations"
      voice_impact: "reflective, philosophical"
```

| Life Stage | Voice Impact |
|------------|--------------|
| **Formative (5-25)** | Foundational - always subtly present |
| **Prime (25-50)** | Defining - conscious voice identity |
| **Later (50+)** | Current - most audible demeanor |

### Persona Schema Updates

Voice training adds these fields to Persona:

```python
voice_model_path: str = ""       # Path to trained Qwen3-TTS model
voice_source_urls: list[str]     # YouTube URLs used for training
voice_status: str = ""           # pending, training, ready, failed
voice_dataset_path: str = ""     # Path to training dataset
voice_trained_at: str = ""       # ISO timestamp
```

### Storage Paths

Default storage locations (12TB storage):
- Datasets: `/mnt/storage12tb/media/personas/voice-datasets/{slug}/`
- Models: `/mnt/storage12tb/media/personas/voice-models/{slug}/`

Fallback (smaller systems):
- Datasets: `~/datasets/persona-voices/{slug}/`
- Models: `~/models/persona-voices/{slug}/`

---

# Check PersonaPlex setup status
./run.sh personaplex status "Embry"

# Extract voice prompts from reference actors
./run.sh personaplex extract-prompts "Embry"

# View emotional mannerism config
./run.sh personaplex config "Embry" --states --vernacular

# Test register detection
./run.sh personaplex test-register "Embry" --text "Tell me about SPARTA controls"

# Full setup from character sheet
./run.sh personaplex setup "Embry" --character-sheet /path/to/embry.yaml
```

### CLI Commands

#### `personaplex status` — Check setup readiness

```bash
./run.sh personaplex status NAME [OPTIONS]

Options:
  --json                 Output as JSON
```

Shows:
- Config file presence
- Voice prompts by register
- Text prompts status
- Issues/gaps

#### `personaplex extract-prompts` — Extract speaker embeddings

```bash
./run.sh personaplex extract-prompts NAME [OPTIONS]

Options:
  --scope, -s SCOPE      Memory scope
  --dry-run              Preview without extracting
  --json                 Output as JSON
```

Extracts .pt files from voice reference actors for each register.

#### `personaplex config` — View emotional mannerism config

```bash
./run.sh personaplex config NAME [OPTIONS]

Options:
  --states               Show emotional states
  --vernacular           Show vernacular libraries
  --json                 Output as JSON
```

Displays the state machine, vernacular phrases, and transition behaviors.

#### `personaplex test-register` — Test register detection

```bash
./run.sh personaplex test-register NAME [OPTIONS]

Required:
  --text, -t TEXT        Text to analyze

Options:
  --time TIME            Time of day (HH:MM) for time-based triggers
  --json                 Output as JSON
```

Tests which emotional register would activate for given input.

#### `personaplex setup` — Full PersonaPlex setup

```bash
./run.sh personaplex setup NAME [OPTIONS]

Options:
  --character-sheet, -c PATH   Path to character sheet
  --dry-run                    Preview without changes
  --json                       Output as JSON
```

Orchestrates complete PersonaPlex setup including voice prompt extraction.

### Emotional Mannerism Configuration

PersonaPlex uses a YAML config for emotional state machines:

```yaml
# emotional_mannerisms.yaml
name: Embry
version: "1.0"

voice_prompts:
  confident:
    file: embry_confident.pt
    source: Hailee Steinfeld reference clips
    characteristics:
      - forward momentum
      - clear articulation
      - youthful energy

  uncertain:
    file: embry_uncertain.pt
    source: Kristen Stewart reference clips
    characteristics:
      - hesitant pauses
      - vocal fry
      - trailing sentences

states:
  technical_flow:
    voice: confident
    triggers:
      keywords: [SPARTA, NIST, AC-17, satellite, authentication]
      context: [presenting, explaining, debugging]
    behavior:
      speech_rate: normal_to_fast
      pauses: minimal
    example: "The AC-17 control requires multi-factor authentication."

  uncertain_deflecting:
    voice: uncertain
    triggers:
      keywords: [Hawaii, surfing, Kai, relationship]
      context: [personal_questions, being_observed]
    behavior:
      speech_rate: slower
      pauses: frequent_mid_sentence
      filler_words: [um, I mean, like, anyway]
    example: "Hawaii? I... it's been a while. Anyway, what were we—"

  tired_charleston:
    voice: confident  # Voice stays strong, accent slips
    triggers:
      time: after_2300
      context: [third_failure, long_session]
    behavior:
      accent: charleston_emerges
      vernacular_unlocked:
        - "y'all"
        - "fixing to"
        - "we're in the short rows"
    example: "We're in the short rows. I'm fixing to run it one more time."

vernacular:
  charleston:
    safe:
      - phrase: "We're in the short rows"
        meaning: almost done
        usage: wrap-up, end of session
      - phrase: "fixing to"
        meaning: about to
      - phrase: "might could"
        meaning: might be able to

  hawaiian:
    safe:
      - phrase: "hamajang"
        meaning: all messed up
        emotional_weight: none
      - phrase: "da kine stay hamajang"
        meaning: that thing is completely broken
    loaded:
      - phrase: "talk story"
        meaning: casual conversation
        emotional_weight: high_hurts
    forbidden:
      - phrase: "ku'uipo"
        meaning: my sweetheart
        emotional_weight: critical_never_say

personaplex:
  model: nvidia/personaplex-7b-v1
  voice_switching:
    enabled: true
    method: register_based
    default_voice: confident
  inference_settings:
    seed: 42424242
```

### Workflow: Setting Up PersonaPlex for a Fictional Persona

```
1. CREATE PERSONA (if not exists)
   ./run.sh create "Embry" --template fictional \
     --character-sheet /path/to/embry.yaml

2. ADD VOICE REFERENCES
   ./run.sh voice-ref "Embry" \
     --actor "Hailee Steinfeld" --register confident --weight 0.6
   ./run.sh voice-ref "Embry" \
     --actor "Kristen Stewart" --register uncertain --weight 0.4

3. CREATE PERSONAPLEX DIRECTORY
   mkdir -p /mnt/storage12tb/media/personas/embry/personaplex/{configs,voices,prompts}

4. CREATE EMOTIONAL MANNERISMS CONFIG
   # Write emotional_mannerisms.yaml with states, triggers, vernacular

5. CREATE TEXT PROMPTS
   # Write embry_prompts.yaml with register-specific system prompts

6. EXTRACT VOICE PROMPTS
   ./run.sh personaplex extract-prompts "Embry"

7. TEST REGISTER DETECTION
   ./run.sh personaplex test-register "Embry" --text "Tell me about SPARTA"

8. VERIFY SETUP
   ./run.sh personaplex status "Embry"
```

### Storage Layout

```
/mnt/storage12tb/media/personas/{slug}/
├── embry_persona.yaml          # Main persona definition
├── docs/
│   ├── EMBRY_CHARACTER_SHEET.md
│   └── EMBRY_BDI_MEMORIES.md
├── personaplex/
│   ├── configs/
│   │   └── emotional_mannerisms.yaml
│   ├── prompts/
│   │   └── embry_prompts.yaml
│   └── voices/
│       ├── embry_confident.pt
│       └── embry_uncertain.pt
└── qwen3_tts/
    ├── datasets/
    └── models/
```

### Integration with Qwen3-TTS

PersonaPlex handles **live conversation** while Qwen3-TTS handles **recorded narration**:

| System | Use Case | Voice Source |
|--------|----------|--------------|
| PersonaPlex | Real-time dialog | Speaker embeddings (.pt) |
| Qwen3-TTS | Narration, voiceover | Fine-tuned model (LoRA) |

Both can use the same voice references but with different training approaches.

---

# Monitor single persona for new content
./run.sh monitor "Dan Kieft" --check-new

# Monitor all expert personas
./run.sh monitor --scope experts --all

# Nightly monitoring (register with /scheduler)
./run.sh monitor --register-nightly

# Show monitoring status
./run.sh monitor --status
```

### CLI Commands

#### `monitor` — Check and ingest new content

```bash
./run.sh monitor [NAME] [OPTIONS]

Options:
  --scope, -s SCOPE      Scope to monitor (default: experts)
  --all, -a              Monitor all personas in scope
  --check-new            Only check for new content, don't ingest
  --ingest               Ingest new content found
  --register-nightly     Register with /scheduler for nightly runs
  --status               Show monitoring status
  --since DAYS           Only check content newer than N days (default: 7)
  --dry-run              Preview without changes
```

### Monitoring Sources by Template

| Template | Monitored Sources | Check Frequency |
|----------|-------------------|-----------------|
| `expert` | YouTube channels, ArXiv, Books | Weekly |
| `coder` | GitHub repos, YouTube, Blogs | Weekly |
| `fictional` | Reference actor content | Monthly |
| `adversary` | Threat feeds, CVE databases | Daily |

### Source Configuration

Personas store their monitoring sources:

```yaml
# In persona record
monitoring:
  youtube_channels:
    - "@DanKieftAI"
    - "@Lightricks"
  github_repos:
    - "Lightricks/LTX-Video"
  arxiv_queries:
    - "video generation diffusion"
  check_frequency: weekly
  last_checked: "2025-02-01T00:00:00Z"
  new_content_count: 3
```

### Integration with /scheduler

```bash
# Register persona monitoring as nightly task
./run.sh monitor --register-nightly

# Creates entry in /scheduler:
# - Runs at 2 AM
# - Checks all expert personas
# - Ingests new YouTube content
# - Updates knowledge via /doc2qra
```

### Example: Keeping Dan Kieft Updated

```bash
# Check for new videos
./run.sh monitor "Dan Kieft" --check-new

# Output:
# Dan Kieft (@DanKieftAI)
#   Last checked: 2025-02-01
#   New videos found: 2
#     - "Kling 3.1 First Look" (2025-02-05)
#     - "Character Consistency Deep Dive" (2025-02-03)
#
# Run with --ingest to add to memory

# Ingest new content
./run.sh monitor "Dan Kieft" --ingest
```

---

# Create expert persona
./run.sh create "Andrej Karpathy" --template expert \
  --domain "deep learning, language models" \
  --expertise "LoRA fine-tuning, transformer training, optimization" \
  --learn

# Add YouTube sources for monitoring
./run.sh update "Andrej Karpathy" \
  --add-youtube "@AndrejKarpathy" \
  --add-youtube "Let's build GPT" \
  --add-youtube "Let's reproduce GPT-2"

# Add to monitoring
./run.sh monitor "Andrej Karpathy" --register-nightly
```

### Platform Expert Registry (for create-movie)

Expert personas integrate with video generation platforms:

| Platform | Expert Persona | Memory Scope |
|----------|---------------|--------------|
| Kling | Dan Kieft | `dan-kieft` |
| Veo | (TBD) | `veo-expert` |
| LTX-2 | (TBD) | `ltx2-expert` |
| **Model Training** | Andrej Karpathy | `karpathy` |

```bash
# Query model training expert before fine-tuning
./run.sh show "Andrej Karpathy" --query "LoRA rank selection for 7B model"
```

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PERSONA_DEFAULT_SCOPE` | Default memory scope | `personas` |
| `PERSONA_AUTO_LEARN` | Auto-learn for experts | `true` |
| `PERSONA_MONITOR_FREQUENCY` | Default check frequency | `weekly` |

## Dependencies

- `/memory` — Storage and recall
- `/interview` — Interactive creation
- `/ask` — Knowledge enrichment (learn)
- `common/taxonomy` — Federated Taxonomy bridges
- `/tts-train` — Voice model training (Qwen3-TTS)
- `/ingest-youtube` — YouTube audio download
- Theory of Mind: Based on Horus persona architecture
- PersonaPlex: NVIDIA's full-duplex speech-to-speech model
- resemblyzer/speechbrain: Speaker embedding extraction
