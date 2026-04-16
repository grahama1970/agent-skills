# Proposal: Add `consult` Command to /ask Skill

## Problem Statement

### Problem 1: No Role-Play Capability
Current `/ask` skill retrieves facts **ABOUT** personas but cannot:
1. Generate responses **AS** a persona (role-play)
2. Have a persona consult their colleagues
3. Return responses in the persona's authentic voice

### Problem 2: Persona Fragmentation (CRITICAL)
Personas are scattered across multiple locations:

| Persona | Location | In Memory? |
|---------|----------|------------|
| Embry | Memory (`personas` scope) | YES |
| Brandon Bailey | `/reality-check-sparta/BRANDON_BAILEY_PERSONA.md` | NO |
| SOC Analyst | Memory (`personas` scope) | YES |

**Result:** Embry can't consult her boss Brandon because he's not in memory.

### Problem 3: Discovery Failure
The agent had to:
1. Try `/ask` - wrong scope
2. Try `/memory recall` - wrong syntax
3. Try `/create-persona simulacrum` - wrong command
4. Try multiple scopes - still couldn't find Brandon
5. Manually grep skill directories - finally found him

**This should be ONE command.**

### Example of Current Broken Flow

```bash
# Agent tries to ask Embry for her opinion:
./run.sh ask "What does Embry think about the UI?" --scope personas

# What happens:
# 1. Memory recall finds Embry's character sheet
# 2. Returns raw QRA items about Embry
# 3. No synthesis AS Embry
# 4. Agent has to manually role-play Embry's response

# What should happen:
# 1. Load Embry's persona (BDI, voice, background)
# 2. Generate response AS Embry using scillm
# 3. Return Embry's opinion in her voice
```

## Proposed Solution: `consult` Command

### Basic Usage

```bash
# Ask a persona for their opinion
./run.sh consult "Embry" "What do you think of the new Horus UI?"

# Output:
# ── Embry's Response ──
# "That editable query with cancel? Finally. I fat-finger things all the time.
# The keyboard shortcuts are going to make Karen cry actual tears of joy.
# Ship it."
```

### With Colleague Consultation

```bash
# Ask Embry AND her colleagues
./run.sh consult "Embry" "Rate these 4 interfaces" \
  --also-ask "Brandon Bailey,SOC Analyst"

# Output:
# ── Embry's Response ──
# "The 10ft ambient is clean. Dad would approve - like a caution light..."
#
# ── Brandon Bailey's Response ──
# "Good work. The FTUE modal handles onboarding I'd otherwise have to do..."
#
# ── SOC Analyst's Response ──
# "Colorblind indicators are critical for 24/7 ops. Approved."
```

### With Relationship Awareness

Embry is protective of her boss Brandon. The system should know this:

```bash
./run.sh consult "Embry" "Is Brandon doing a good job mentoring you?"

# Should generate response aware of:
# - Embry's protective relationship with Brandon
# - Her loyalty bridge weight (0.90)
# - Her deflection style when asked uncomfortable questions
```

## Solution: Unified Persona Discovery

### Persona Registry

Create a unified persona index that searches ALL sources:

```python
PERSONA_SOURCES = [
    # 1. Memory (highest priority - already ingested)
    {"type": "memory", "scope": "personas"},

    # 2. Skill directories (PERSONA.md files)
    {"type": "glob", "pattern": ".pi/skills/**/\*_PERSONA.md"},
    {"type": "glob", "pattern": ".pi/skills/**/\*_persona.yaml"},

    # 3. Media personas directory
    {"type": "glob", "pattern": "/mnt/storage12tb/media/personas/*/docs/*.md"},
]
```

### Auto-Ingest on First Reference

```bash
./run.sh consult "Brandon Bailey" "Review this UI design"

# What happens:
# 1. Search memory for "Brandon Bailey" → NOT FOUND
# 2. Search skill dirs for "*Brandon*PERSONA.md" → FOUND
# 3. Auto-ingest BRANDON_BAILEY_PERSONA.md into memory
# 4. Generate response AS Brandon Bailey
# 5. Return response
```

### Relationship Graph Discovery

When ingesting Embry, parse her docs for relationships:

```yaml
# Extracted from EMBRY_CHARACTER_SHEET.md
relationships:
  - target: "Brandon Bailey"
    type: "reports_to"
    stance: "protective"
    source: "working with Brandon Bailey on the SPARTA project"
```

## Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                      consult "Embry" "question"                    │
└────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌────────────────────────────────────────────────────────────────────┐
│  0. UNIFIED PERSONA DISCOVERY (NEW)                                 │
│     - Search memory first                                          │
│     - Search skill directories (*_PERSONA.md, *_persona.yaml)     │
│     - Search media personas directory                              │
│     - Auto-ingest if found in files but not in memory              │
└────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌────────────────────────────────────────────────────────────────────┐
│  1. PERSONA LOADER                                                  │
│     - Load from /create-persona (BDI state, voice, background)     │
│     - Load relationships (colleagues, hierarchy)                   │
│     - Load Federated Taxonomy bridges (Loyalty: 0.90, etc.)        │
└────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌────────────────────────────────────────────────────────────────────┐
│  2. CONTEXT BUILDER                                                 │
│     - Retrieve relevant QRA from memory                            │
│     - Include relationship context if --also-ask used              │
│     - Build persona system prompt                                  │
└────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌────────────────────────────────────────────────────────────────────┐
│  3. RESPONSE GENERATOR (via scillm)                                 │
│     - System prompt: persona character sheet + voice patterns      │
│     - User prompt: the question                                    │
│     - Generate response AS the persona                             │
└────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌────────────────────────────────────────────────────────────────────┐
│  4. COLLEAGUE LOOP (if --also-ask)                                  │
│     - For each colleague, repeat steps 1-3                         │
│     - Include relationship context in prompts                      │
└────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌────────────────────────────────────────────────────────────────────┐
│  5. OUTPUT FORMATTER                                                │
│     - Format all responses with persona headers                    │
│     - Include confidence indicators                                │
│     - Optional: JSON output for programmatic use                   │
└────────────────────────────────────────────────────────────────────┘
```

## CLI Specification

```bash
./run.sh consult <persona> <question> [options]

Arguments:
  persona              Persona name (must exist in memory)
  question             The question to ask the persona

Options:
  --scope <scope>      Memory scope (default: "personas")
  --also-ask <names>   Comma-separated colleague names to also consult
  --context <text>     Additional context for the question
  --voice              Also generate TTS audio of response
  --json               Output as JSON
  --debug              Enable debug logging
```

## Implementation Notes

### Persona System Prompt Template

```
You are {persona_name}.

## Character
{character_sheet_summary}

## Voice Patterns
{voice_patterns}

## Relationships
{relationships}

## Current BDI State
- Beliefs: {beliefs}
- Desires: {desires}
- Intentions: {intentions}

Respond to the following question AS {persona_name}, in their authentic voice.
Do not break character. Do not explain that you are role-playing.
```

### Integration Points

| Component | Integration |
|-----------|-------------|
| `/create-persona` | Load persona profiles, BDI state, relationships |
| `/memory` | Retrieve relevant QRA for context |
| `/taxonomy` | Load bridge weights for response tuning |
| `scillm` | Generate responses |
| `/train-persona` | Optional fine-tuned LoRA for persona voice |

### Relationship Graph

Embry's relationships should be stored in memory:

```json
{
  "name": "Embry",
  "relationships": [
    {
      "target": "Brandon Bailey",
      "type": "reports_to",
      "stance": "protective",
      "notes": "Her boss on the SPARTA project, she's protective of him"
    },
    {
      "target": "SOC Analyst",
      "type": "colleague",
      "stance": "professional"
    }
  ]
}
```

## Migration Path

1. Add `consult` command to `/ask` skill
2. Integrate with `/create-persona` for persona loading
3. Add `--also-ask` for colleague consultation
4. Store relationship graph in memory
5. Update SKILL.md documentation

## Success Criteria

A project agent should be able to:

```bash
# One command, seamless experience
./run.sh consult "Embry" "What do you think of the new UI?" --also-ask "Brandon Bailey"
```

And get back authentic responses from both personas without any manual intervention.

## Current State (As of 2026-02-10)

After manual intervention, the following is now set up:

| Persona | In Memory | Relationships | Notes |
|---------|-----------|---------------|-------|
| Embry | YES | reports_to: Brandon Bailey | Fictitious intern |
| Brandon Bailey | YES | colleague: Embry | **REAL** - SPARTA creator at Aerospace Corp |
| Horus | - | - | Fictitious AI assistant |

**Still broken:** No `consult` command exists. Agent had to:
1. Manually create Brandon Bailey persona
2. Manually set up relationships
3. Still cannot generate responses AS either persona

## Implementation Priority

1. **P0: Add `consult` command** - Generate responses AS a persona
2. **P1: Add `--also-ask`** - Multi-persona consultation
3. **P2: Relationship-aware responses** - Brandon knows Embry reports to him
4. **P3: Auto-discovery** - Find personas across memory + skill files
