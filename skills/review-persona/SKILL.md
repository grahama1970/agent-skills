---
name: review-persona
description: >
  Multi-provider AI persona review for character realism, voice casting, and authenticity.
  Validates fictional and real personas before production use.
triggers:
  - review persona
  - persona review
  - character review
  - validate persona
  - check character
  - review the character
  - is this persona realistic
  - voice casting review
  - character authenticity
  - persona feedback
allowed-tools:
  - Bash
  - Read
  - Glob
  - WebFetch
  - WebSearch
metadata:
  short-description: Character realism and voice casting review
  version: "1.0"

provides:
  - review-persona
composes: [task-monitor]
disciplines:
  - persona-simulation
  - evaluation-quality
---

## Standard Review Iteration Parameters

This `review-*` skill follows the shared contract in
`skills/.system/review-iteration-contract.md`.

Canonical parameters:

- `--max-rounds N`
- `--output-dir PATH`
- `--ask-gate`
- `--ask-model MODEL` (default `gpt-5.5`)
- `--ask-reasoning LEVEL` (default `high`)
- `--ask-timeout SECONDS`
- `--ask-focus LABELS`

When `--max-rounds > 1` is supplied, the skill must behave as a bounded
gate-producing controller or fail closed if that mode is not implemented. The
canonical gate artifact is `review_result.json` with verdict
`PASS`, `NEEDS_CHANGES`, `BLOCKED`, or `INSUFFICIENT_EVIDENCE`.

# review-persona

Multi-provider AI persona review skill. Validates character realism, voice casting choices, and domain authenticity using research-backed analysis.

## Triggers

- review persona
- persona review
- character review
- validate persona
- check character
- review the character
- is this persona realistic
- voice casting review
- character authenticity
- persona feedback

## When to Use

Use `/review-persona` **before** investing in:
- Voice training (expensive, time-consuming)
- Image generation (casting photos)
- Video production
- Public release of character

## Review Dimensions

| Dimension | What It Validates | Weight |
|-----------|-------------------|--------|
| **Realism** | Is this persona believable for their role/domain? | 25% |
| **Voice Casting** | Are reference actors appropriate? Do they match the character? | 25% |
| **Register Switching** | Does confident/uncertain dynamic make sense? | 15% |
| **Media Consumption** | Would they realistically consume this content? | 15% |
| **Technical Accuracy** | Is domain terminology correct? (for domain personas) | 20% |

## Quick Start

```bash
cd .pi/skills/review-persona

# Review a persona YAML file
./run.sh review /path/to/embry_persona.yaml

# Review with focus on specific dimensions
./run.sh review embry_persona.yaml --focus voice,realism

# Review using specific provider
./run.sh review embry_persona.yaml --provider claude

# Review fictional persona with character sheet
./run.sh review embry_persona.yaml --character-sheet /path/to/EMBRY_CHARACTER_SHEET.md

# Quick sanity check (no deep research)
./run.sh check embry_persona.yaml

# Deep research validation (uses /dogpile)
./run.sh deep-review embry_persona.yaml
```

## Commands

### `review` — Standard persona review

```bash
./run.sh review PERSONA_FILE [OPTIONS]

Options:
  --provider TEXT        LLM provider (claude, codex, gemini)
  --focus TEXT           Dimensions to focus on (comma-separated)
  --character-sheet PATH Character document for fictional personas
  --images PATH          Directory with casting images (vision review)
  --output PATH          Output file for review
  --json                 Output as JSON
```

### `review-visual` — Vision-based casting review

```bash
./run.sh review-visual PERSONA_FILE --images IMAGE_DIR [OPTIONS]

Options:
  --provider TEXT        Vision-capable provider (claude, gemini, openai)
  --character-sheet PATH Character document for comparison
  --output PATH          Output file

Analyzes:
- Does visual appearance match character description?
- Does the "look" match the voice references?
- Is the casting consistent across images?
- Would this face match a Steinfeld/Stewart voice blend?
```

### `deep-review` — Research-backed review (uses /dogpile)

```bash
./run.sh deep-review PERSONA_FILE [OPTIONS]

Options:
  --research-focus TEXT  What to research (role, voice, domain)
  --provider TEXT        LLM provider
  --output PATH          Output file
```

Deep review researches:
1. What do real people in this role sound like?
2. Are reference actors appropriate for this character age/type?
3. Is the media consumption realistic for this demographic?
4. Is domain terminology accurate?

### `check` — Quick sanity check

```bash
./run.sh check PERSONA_FILE

Checks:
- Required fields present
- Voice references have weights that sum to ~1.0
- Bridge weights are valid (0.0-1.0)
- Character sheet exists (if specified)
```

### `compare-voice` — Validate voice casting

```bash
./run.sh compare-voice PERSONA_FILE [OPTIONS]

Options:
  --find-alternatives    Search for alternative voice references
  --validate-blend       Check if voice blend makes sense
```

## Output Format

### Review Report

```markdown
# Persona Review: Embry

## Overall Score: B+ (82/100)

### Realism (23/25)
✓ Entry-level cybersecurity role is well-defined
✓ Age-appropriate concerns (boxes unpacked, recent breakup)
⚠ Military brat background adds depth but verify terminology

### Voice Casting (22/25)
✓ Hailee Steinfeld matches confident young professional
✓ Kristen Stewart matches uncertain/gawky moments
⚠ Consider: Steinfeld may skew too "Hollywood confident"
  Alternative: Thomasin McKenzie for more grounded energy

### Register Switching (14/15)
✓ Confident on SPARTA controls → makes sense for trained area
✓ Uncertain when observed → realistic for entry-level
✓ Switch triggers are specific and believable

### Media Consumption (13/15)
✓ Everyday Astronaut, Scott Manley → perfect for aerospace
✓ Contact, Interstellar → genre-appropriate favorites
⚠ Consider adding: CyberWire podcast for cybersecurity immersion

### Technical Accuracy (19/20)
✓ AC-17, IA-5 are real NIST controls
✓ SPARTA is a real framework (mentioned correctly)
✓ D3FEND countermeasures used correctly
⚠ Minor: "Telemetry specs" is slightly vague - specify protocol

## Recommendations
1. Add a cybersecurity podcast to media consumption
2. Consider Thomasin McKenzie as alternative confident voice
3. Specify telemetry protocols (CCSDS? TMTC?)

## Ready for Production: YES (with minor adjustments)
```

### JSON Output

```json
{
  "persona": "Embry",
  "template": "fictional",
  "overall_score": 82,
  "grade": "B+",
  "dimensions": {
    "realism": {"score": 23, "max": 25, "issues": [], "praise": [...]},
    "voice_casting": {"score": 22, "max": 25, "issues": [...], "alternatives": [...]},
    "register_switching": {"score": 14, "max": 15, "issues": []},
    "media_consumption": {"score": 13, "max": 15, "suggestions": [...]},
    "technical_accuracy": {"score": 19, "max": 20, "issues": [...]}
  },
  "recommendations": [...],
  "ready_for_production": true,
  "blockers": []
}
```

## Visual Review (Casting Images)

For fictional personas with casting images, vision-capable LLMs analyze:

### What Visual Review Checks

| Check | Question |
|-------|----------|
| **Character Sheet Match** | Does the face match "shoulder-length brown hair, sharp features"? |
| **Voice-Face Congruence** | Would this person sound like Steinfeld/Stewart? |
| **Role Authenticity** | Does she look like an entry-level engineer, not a model? |
| **Consistency** | Are all casting images the same person? |
| **Age Match** | Does she look 23? Not too young/old? |
| **Wardrobe** | Practical clothes? No glamour shots? |

### Visual Review Output

```markdown
## Visual Review: Embry Casting Images

Analyzed 22 images from /mnt/storage12tb/media/personas/embry/assets/casting_v2/

### Character Sheet Alignment (90%)
✓ Brown shoulder-length hair (matches)
✓ Athletic build, surfer physique (matches)
✓ Practical clothing - polos, flannels (matches)
✓ Nose scar visible in some images (good continuity)
⚠ Some images show slightly glamorized lighting

### Voice-Face Congruence (85%)
✓ Natural, approachable appearance suits Steinfeld energy
✓ Slight awkwardness in candid shots matches Stewart quality
⚠ Some "confident" poses may be too polished

### Role Authenticity (88%)
✓ Looks like someone who works, not poses
✓ Hands show some texture (matches "garage hands" description)
⚠ Suggest adding images with grease/work context

### Consistency (95%)
✓ All images appear to be same character
✓ Consistent facial structure across angles
✓ Scar detail maintained
```

### Example: Visual + Voice Review

```bash
# Full review with both persona YAML and images
./run.sh review embry_persona.yaml \
  --images /mnt/storage12tb/media/personas/embry/assets/casting_v2/ \
  --character-sheet /mnt/storage12tb/media/personas/embry/docs/EMBRY_CHARACTER_SHEET_V2.md \
  --provider claude
```

## Voice Casting Validation

For fictional personas, validates voice references against:

### Age Appropriateness
| Character Age | Appropriate References |
|---------------|----------------------|
| Teens (13-19) | Hailee Steinfeld, Thomasin McKenzie, Millie Bobby Brown |
| 20s | Florence Pugh, Zendaya, Sydney Sweeney |
| 30s | Brie Larson, Daisy Ridley, Elizabeth Olsen |
| 40s+ | Cate Blanchett, Nicole Kidman, Viola Davis |

### Register Matching
| Register | Voice Qualities | Good References |
|----------|-----------------|-----------------|
| Confident | Forward momentum, clear, commanding | Steinfeld, Larson, Pugh |
| Uncertain | Hesitant, vocal fry, trailing | Stewart, McKenzie, Ronan |
| Technical | Precise, measured, calm | Foster (Contact), Portman |
| Casual | Natural, relaxed, warm | Chalamet, Zendaya |

### Domain Matching
| Domain | Voice Qualities | Research Sources |
|--------|-----------------|------------------|
| Engineering | Technical precision, clarity | Real engineers on YouTube |
| Military | Clipped, confident, jargon | Military briefings |
| Academic | Measured, detailed, curious | TED talks, lectures |
| Creative | Expressive, dynamic range | Artist interviews |

## Integration with Other Skills

### With /dogpile
Deep review uses `/dogpile` to research:
- Real voices in the character's domain
- Actor filmography for voice sample quality
- Domain terminology accuracy

### With /create-persona
Review integrates with `/create-persona` for:
- Pre-training validation
- Iterative improvement loop
- Voice reference discovery

### With /tts-train
Review validates voice casting before expensive training:
- Are clip sources available?
- Do reference actors have enough content?
- Is the blend ratio realistic?

## Workflow: Persona Creation → Review → Production

```
1. CREATE PERSONA
   └── /create-persona create "Embry" --template fictional

2. REVIEW BEFORE INVESTMENT
   └── /review-persona deep-review embry_persona.yaml
   └── Address issues, iterate

3. VALIDATE VOICE CASTING
   └── /review-persona compare-voice embry_persona.yaml
   └── Confirm reference actors are appropriate

4. TRAIN VOICE (expensive)
   └── /create-persona voice train "Embry" --from-references

5. GENERATE CONTENT
   └── Only after review passes
```

## Example: Reviewing Embry

```bash
# Full review with research
./run.sh deep-review /mnt/storage12tb/media/personas/embry/embry_persona.yaml \
  --character-sheet /mnt/storage12tb/media/personas/embry/docs/EMBRY_CHARACTER_SHEET_V2.md \
  --research-focus "voice,domain" \
  --output embry_review.md

# Quick check before voice training
./run.sh check /mnt/storage12tb/media/personas/embry/embry_persona.yaml
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `REVIEW_PERSONA_PROVIDER` | Default LLM provider | `claude` |
| `REVIEW_PERSONA_OUTPUT_DIR` | Output directory | `./review_output` |

## Dependencies

- `/dogpile` - Deep research for validation
- `/create-persona` - Persona loading and updates
- `/discover-movies` - Actor filmography research
- `/ingest-youtube` - Voice sample discovery
