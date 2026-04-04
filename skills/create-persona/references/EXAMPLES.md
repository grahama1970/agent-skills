## Examples

### Client Persona for Project

```bash

## Fictional Personas (v5)

Fictional personas are **simulated characters** (not real people). The key difference:

| Aspect | Real Persona | Fictional Persona |
|--------|--------------|-------------------|
| **Learning source** | Their talks, books, interviews | What they would consume |
| **Voice training** | Their own voice clips | Reference actor clips |
| **Simulacrum test** | "Did they really say this?" | "Is this in-character?" |
| **Discovery** | `/dogpile {name}` | `/dogpile {influences}` |

### Quick Start

```bash

### Example: Creating Embry

```bash

## Horus-Depth (v3)

Based on the Horus persona at `/home/graham/workspace/experiments/memory/persona`, this upgrade adds:

### Theory of Mind (BDI)

Each persona tracks Belief-Desire-Intention state for each user relationship:

```python
@dataclass
class BDIState:
    persona_name: str
    user_id: str

## Voice/TTS Training (v4)

Train Qwen3-TTS voice models from YouTube audio (interviews, lectures, talks) so personas can speak in their own voice.

### Quick Start

```bash

## PersonaPlex Integration (v6) - Real-Time Conversation

PersonaPlex is NVIDIA's full-duplex speech-to-speech model for real-time conversational AI. This integration enables personas to have **live conversations** with register-based voice switching.

### Key Concepts

| Concept | Description |
|---------|-------------|
| **Voice Prompts** | Speaker embeddings (.pt files) extracted from reference clips |
| **Text Prompts** | System prompts that define behavior for each register |
| **Emotional States** | State machine mapping triggers to voice/behavior |
| **Register Switching** | Dynamic voice selection (confident → uncertain) |
| **Vernacular** | Phrase libraries with emotional weight markers |

### Quick Start

```bash

## Persona Monitoring (Nightly Updates)

Expert personas need fresh content. The `monitor` command checks for new material from persona sources and triggers re-ingestion.

### Quick Start

```bash

## Model Training Expert Persona

For LoRA fine-tuning and model training guidance, create an expert persona:

### Recommended: Andrej Karpathy

Best for practical implementation guidance:

```bash

## Batch Creation

Create multiple personas at once from a YAML manifest file:

```bash
# Preview what would be created
./run.sh batch personas.yaml --dry-run

# Create all personas with auto-learning
./run.sh batch personas.yaml

# Create without triggering /ask learn (faster)
./run.sh batch personas.yaml --skip-learn

# Only create personas in a specific category
./run.sh batch personas.yaml --category coders
```

### Manifest Format

```yaml
# personas.yaml
defaults:
  scope: personas
  auto_learn: true
  depth: standard

writers:
  - name: Alan Moore
    template: expert
    domain: comics, literature, occultism
    expertise:
      - graphic novels
      - chaos magic
    goals:
      - Challenge narrative conventions
    bridges:
      Corruption: 0.7
      Precision: 0.8
    colleagues:
      - Dave Gibbons
      - Neil Gaiman

coders:
  - name: John Carmack
    template: coder
    domain: game development, VR
    expertise:
      - 3D graphics
      - engine optimization
    goals:
      - Push technical boundaries
    bridges:
      Precision: 0.95
    colleagues:
      - John Romero
```

Categories can be named anything (writers, coders, strategists, etc.). Each persona in a category gets the category name as a tag.

# Create fictional persona from character sheet
./run.sh create "Embry" --template fictional \
  --character-sheet /path/to/EMBRY_CHARACTER_SHEET.md

# Interactive creation (asks the character what they consume)
./run.sh create "Embry" --template fictional --interactive

# Set voice references
./run.sh voice-ref "Embry" \
  --actor "Hailee Steinfeld" --register confident --weight 0.6 \
  --actor "Kristen Stewart" --register uncertain --weight 0.4

# Train voice from reference actors
./run.sh voice train "Embry" --from-references
```

### Fictional-Specific Fields

Fictional personas have additional fields not present in other templates:

```yaml
# Embry - Fictional Persona Example
name: Embry
template: fictional

# What shapes their personality (media they consume)
media_consumption:
  movies:
    formative: [Contact, Interstellar, Apollo 13, Ex Machina]
    guilty_pleasure: [rocket launch livestreams]
  books:
    nightstand: [The Right Stuff, A Fire Upon the Deep]
  youtube_channels:
    daily: [Everyday Astronaut, Scott Manley, SmarterEveryDay]
  guilty_pleasures:
    - competes with mom at Sudoku secretly
    - drinks too many Celsius

# Voice from REFERENCE ACTRESSES (not themselves)
voice_references:
  - actress: Hailee Steinfeld
    register: confident
    weight: 0.6
    clips_to_find: [Hawkeye technical scenes, True Grit conviction]
    characteristics: [youthful energy, commanding presence, natural flow]
  - actress: Kristen Stewart
    register: uncertain
    weight: 0.4
    clips_to_find: [awkward interviews, hesitant moments]
    characteristics: [hesitant pauses, vocal fry, endearing awkwardness]

voice_accent: subtle_southern  # Charleston educated

# Personality quirks
quirks:
  - competes with mom at Sudoku secretly
  - watches rocket launches while eating lunch
  - has 3-month expense report backlog
  - drinks too many Celsius

# Register switching behavior
register_switching:
  confident_triggers: [SPARTA, NIST, technical topics]
  uncertain_triggers: [being observed, Marcus from PM]
  confident_voice: Hailee Steinfeld
  uncertain_voice: Kristen Stewart

# Path to full character document
character_sheet_path: /path/to/EMBRY_CHARACTER_SHEET.md

# Simulacrum validates character consistency, not ground truth
simulacrum_mode: character_consistency
```

### The Character Speaks

Fictional personas can "speak" to express preferences about themselves. The agent embodies the character to answer questions like:

- "What do you watch on YouTube?"
- "Whose voice do you identify with when you're confident?"
- "What are your guilty pleasures?"

This is NOT the agent deciding FOR the character - it's letting the character have agency in their own creation.

### Workflow: Creating a Fictional Persona

```
1. DEFINE CHARACTER
   └── Load character sheet (if exists)
   └── Define basic attributes (age, role, domain)

2. ASK CHARACTER WHAT THEY CONSUME
   └── *Embry, what movies do you rewatch?*
   └── *What YouTube channels are you subscribed to?*
   └── *What's on your nightstand?*

3. ASK CHARACTER ABOUT THEIR VOICE
   └── *Whose voice do you sound like when confident?*
   └── *Whose voice when you're uncertain?*
   └── *What accent do you have?*

4. INGEST REFERENCE CONTENT
   └── /discover-movies for films they'd watch
   └── /ingest-youtube for channels they follow
   └── /ingest-movie for voice reference actors

5. TRAIN VOICE FROM REFERENCES
   └── Find clips of reference actors
   └── Train blended voice model
   └── 60% Steinfeld / 40% Stewart (weighted blend)

6. VALIDATE CHARACTER CONSISTENCY
   └── Simulacrum tests in-character responses
   └── Checks register switching works
   └── Verifies quirks appear naturally
```

### CLI Commands for Fictional

#### `create` with fictional template

```bash
./run.sh create NAME --template fictional [OPTIONS]

Options:
  --character-sheet PATH    Path to character document (md, yaml, json)
  --interactive, -i         Ask character about preferences
  --domain DOMAIN           Character's professional domain
  --role ROLE               Character's role/job
  --quirk QUIRK             Add a quirk (repeatable)
```

#### `media` — Manage media consumption profile

```bash
./run.sh media NAME [OPTIONS]

Options:
  --add-movie MOVIE         Add formative movie
  --add-book BOOK           Add book to nightstand
  --add-channel CHANNEL     Add YouTube channel
  --add-guilty PLEASURE     Add guilty pleasure
  --show                    Display current media profile
```

#### `voice-ref` — Manage voice references

```bash
./run.sh voice-ref NAME [OPTIONS]

Options:
  --actor NAME              Reference actor name
  --register REG            Voice register (confident, uncertain, neutral)
  --weight FLOAT            Blend weight (0.0-1.0)
  --characteristics TRAITS  Comma-separated vocal traits
  --clips DESCRIPTIONS      Comma-separated clip descriptions to find
  --show                    Display current voice references
```

#### `validate-character` — Test character consistency

```bash
./run.sh validate-character NAME [OPTIONS]

Options:
  --prompts PATH            Custom test prompts (yaml)
  --check-register          Test register switching
  --check-quirks            Verify quirks appear
  --json                    Output as JSON
```

# 1. Create from character sheet
./run.sh create "Embry" --template fictional \
  --character-sheet /mnt/storage12tb/media/personas/embry/docs/EMBRY_CHARACTER_SHEET_V2.md \
  --domain "aerospace cybersecurity" \
  --role "SPARTA Intern"

# 2. Add media consumption (from character interview)
./run.sh media "Embry" \
  --add-movie "Contact" \
  --add-movie "Interstellar" \
  --add-movie "Apollo 13" \
  --add-channel "Everyday Astronaut" \
  --add-channel "Scott Manley" \
  --add-guilty "competes with mom at Sudoku"

# 3. Add voice references
./run.sh voice-ref "Embry" \
  --actor "Hailee Steinfeld" \
  --register confident \
  --weight 0.6 \
  --characteristics "youthful energy,commanding presence,natural flow" \
  --clips "Hawkeye technical scenes,True Grit conviction"

./run.sh voice-ref "Embry" \
  --actor "Kristen Stewart" \
  --register uncertain \
  --weight 0.4 \
  --characteristics "hesitant pauses,vocal fry,endearing awkwardness" \
  --clips "awkward interviews,Personal Shopper"

# 4. Train voice from references
./run.sh voice train "Embry" --from-references --model-size 1.7B

# 5. Validate character
./run.sh validate-character "Embry" --check-register --check-quirks
```

    # Core BDI
    beliefs: dict[str, float]     # e.g., {"is_curious": 0.7, "is_expert": 0.4}
    desires: list[str]            # e.g., ["learn", "solve_problem"]
    intentions: list[str]         # e.g., ["request_assistance"]

    # Relationship metrics
    respect_level: float = 0.5
    trust_level: float = 0.5
    interaction_count: int = 0

    # Mood (computed from beliefs + context)
    current_mood: str = "neutral"
    mood_history: list[str] = []
```

#### CLI Commands

```bash
# View BDI state for persona-user relationship
./run.sh bdi "Hayao Miyazaki" --user graham

# Show mood history
./run.sh bdi "Hayao Miyazaki" --history

# Reset BDI state
./run.sh bdi "Hayao Miyazaki" --reset
```

#### Mood Computation

Moods are computed from beliefs and context:

| Condition | Mood |
|-----------|------|
| User is frustrated + low respect | `dismissive` |
| User is frustrated + high respect | `amused` |
| User is curious | `engaged` |
| User is confused | `supportive` |
| High topic relevance | `intense` |
| Trauma trigger | `defensive` |

Each template has archetype-specific mood rules:

- **expert**: Default `contemplative`, triggers on research/discovery
- **coder**: Default `engaged`, triggers on code/optimization
- **adversary**: Default `critical`, triggers on vulnerabilities
- **client**: Default `engaged`, triggers on budget/deadlines

### Bridge Traversal Validation

Simulacrum probes now include `bridge_traversal` tests that verify cross-domain reasoning:

```bash
# Run simulacrum with bridge traversal
./run.sh simulacrum "Hayao Miyazaki" --probes "philosophy,technique,bridge_traversal"
```

Bridge traversal probes test connections like:
- **Precision**: "How does attention to detail influence broader philosophy?"
- **Resilience**: "What do experiences with failure teach about endurance?"
- **Fragility**: "How do you use awareness of fragility to create stronger work?"

### Bridges CLI

```bash
# Show all bridge definitions
./run.sh bridges

# Show persona's bridges with weights
./run.sh bridges "Hayao Miyazaki"

# Add a bridge
./run.sh bridges "Hayao Miyazaki" --add Fragility:0.8

# Extract bridges from text
./run.sh bridges --extract-from "His work endures through careful attention to detail"
# → ["Precision", "Resilience"]
```

### Upgrade Existing Personas

To apply Horus-depth to all existing personas:

```bash
# Preview what would be upgraded
python upgrade_to_horus_depth.py --scope personas --dry-run

# Upgrade with simulacrum validation
python upgrade_to_horus_depth.py --scope personas --threshold 0.7

# Resume from checkpoint (for long runs)
python upgrade_to_horus_depth.py --scope personas --resume
```

The upgrade script:
1. Infers bridge weights from domain/expertise
2. Initializes BDI state
3. Runs simulacrum validation
4. Improves failing personas

### BDI Edges

Theory of Mind creates graph edges:

```python
ALLOWED_EDGE_TYPES = {
    # Standard
    "solves", "mitigates", "related", "verifies",

    # Theory of Mind
    "observes",       # Persona observes user behavior
    "revises",        # Persona revises a belief
    "trusts",         # Trust relationship
    "respects",       # Respect relationship
    "distrusts",      # Distrust relationship
    "triggers",       # Triggers mood/behavior
    "satisfies",      # Satisfies a desire
    "frustrates",     # Frustrates a desire
    "lesson_informs_belief",  # Lesson influences belief
}
```

# Train voice with auto-discovered URLs from memory
./run.sh voice train "Robert Sapolsky" --discover

# Train with specific YouTube URLs
./run.sh voice train "Robert Sapolsky" \
  --url "https://youtube.com/watch?v=abc123" \
  --url "https://youtube.com/watch?v=def456"

# Check training status
./run.sh voice status "Robert Sapolsky"

# Synthesize speech
./run.sh voice synthesize "Robert Sapolsky" \
  --text "Stress affects every system in the body" \
  --output sapolsky_speech.wav

# List personas with trained voices
./run.sh voice list
```

### Voice CLI Commands

#### `voice train` — Train a voice model

```bash
./run.sh voice train NAME [OPTIONS]

Options:
  --url, -u URL          YouTube URL (repeatable)
  --discover, -d         Auto-discover URLs from persona's learning history
  --model-size, -m SIZE  "0.6B" (faster) or "1.7B" (higher quality)
  --epochs, -e INT       Training epochs (default: 5)
  --scope, -s SCOPE      Memory scope
  --dry-run              Preview without training
```

#### `voice status` — Check training status

```bash
./run.sh voice status NAME [OPTIONS]

Options:
  --scope, -s SCOPE      Memory scope
  --json                 Output as JSON
```

Status values: `pending`, `collecting`, `building_dataset`, `training`, `ready`, `failed`

#### `voice synthesize` — Generate speech

```bash
./run.sh voice synthesize NAME [OPTIONS]

Required:
  --text, -t TEXT        Text to synthesize

Options:
  --output, -o PATH      Output WAV file (default: {name}_speech.wav)
  --scope, -s SCOPE      Memory scope
```

#### `voice list` — List personas with voices

```bash
./run.sh voice list [OPTIONS]

Options:
  --scope, -s SCOPE      Memory scope
  --json                 Output as JSON
```

### Voice Training Pipeline

1. **Collect audio**: Download audio from YouTube interviews/lectures using yt-dlp
2. **Build dataset**: Transcribe with WhisperX, segment into training clips
3. **Train model**: Fine-tune Qwen3-TTS on the persona's voice
4. **Register**: Store model path in persona record

### Model Sizes

| Model | VRAM | Training Time | Quality |
|-------|------|---------------|---------|
| 0.6B | ~8GB | ~30 min | Good |
| 1.7B | ~18GB | ~2 hours | Excellent |

For personas with distinctive voices (Sapolsky, Miyazaki), use 1.7B.

### Best Audio Sources

For best voice training results, collect:
- Long-form interviews (20+ minutes)
- Lectures/talks (clear audio)
- Audiobook narration (if available)

Avoid:
- Music/singing (use `/learn-artist` for that)
- Group conversations
- Noisy/low-quality recordings

### Integration with /ask learn

When learning about a persona, YouTube URLs are saved. Voice training can discover these:

```bash
# Learn about persona (collects YouTube URLs)
./run.sh create "Robert Sapolsky" --template expert --learn

# Later, train voice using discovered URLs
./run.sh voice train "Robert Sapolsky" --discover
```


See [SCHEMA.md](SCHEMA.md) for the full persona data schema, historical context fields, and voice profile fields.
