---
name: create-persona
description: Deliberate persona creation for client modeling, expert profiles, and stakeholder mapping. Integrates with /interview for collaborative creation and /ask for knowledge enrichment. Supports Theory of Mind (BDI), voice training, and simulacrum validation.
triggers: create persona, model client, create stakeholder, persona for, expert profile, adversary persona, fictional persona, train voice for persona, simulacrum test

provides:
  - create-persona
composes:
  - ask
  - memory
  - ingest-youtube
  - dogpile
  - task-monitor
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# /create-persona

Deliberate persona creation for client modeling, expert profiles, and stakeholder mapping. Integrates with `/interview` for collaborative creation and `/ask` for knowledge enrichment.

**New in v2:** Quality assessment, validation, and iterative improvement (like `/table-lab`).

**New in v3 (Horus-depth):** Theory of Mind (BDI), bridge traversal validation, archetype mood rules.

## When to Use

- **Client modeling**: Create personas for project stakeholders before engagement
- **Expert profiles**: Build rich profiles of domain experts (triggers `/ask learn`)
- **Threat modeling**: Create adversary personas for security analysis
- **Team dynamics**: Model stakeholders and their relationships
- **Quality audit**: Diagnose gaps, validate responses, improve personas

## Content Richness Pre-Flight

Before creating a persona, assess available source material. QRA quality depends entirely on content richness.

### Source Material Tiers

| Tier | Content Available | QRA Target | Action |
|------|-------------------|------------|--------|
| **Rich** | 3+ YouTube talks/podcasts, 1+ books, active online presence | 200-500 | Full persona with auto-learn |
| **Moderate** | 1-2 talks, some interviews, articles | 50-150 | Standard persona, supplement with `/dogpile` |
| **Thin** | Wikipedia + a few articles, no first-person content | 10-30 | Reference anchor only, `--no-learn` |
| **None** | Deceased pre-YouTube, no recordings, no books | 0 | **Don't create** — waste of Chutes quota |

### Historical Figure Warning

Pre-YouTube deceased figures (died before ~2005) typically lack:
- YouTube talks, podcasts, or interviews
- Searchable transcripts
- Sufficient first-person source material for meaningful QRAs

**Create these as reference anchors only**, not full personas:

```bash
# Reference anchor — no learning, no QRA generation
./run.sh create "Chuck Yeager" --template expert --no-learn \
  --note "Reference anchor only — thin content, no YouTube"
```

Examples of thin-content figures to avoid as full personas:
- Chuck Yeager (died 2020, no YouTube presence)
- Neil Armstrong (died 2012, famously private)
- Scott Crossfield (died 2006, X-15 era)

### Pre-Flight Checklist

Before running `batch` or `create --learn`:

1. **YouTube search**: Find 3+ talks, podcasts, or interviews
   - `yt-dlp --flat-playlist "ytsearch10:PERSON_NAME interview"` for quick check
2. **Book search**: Find 1+ authored or biographical books
3. **Set `qra_target`** proportional to content found
4. **Set `content_tier`** in personas.yaml (rich/moderate/thin/none)
5. **Skip voice training** for thin personas: `skip_voice_training: true`

### personas.yaml Content Fields

```yaml
personas:
  - name: Hasard Lee
    template: expert
    content_tier: rich        # rich | moderate | thin | none
    qra_target: 300           # Target QRA count based on content tier
    skip_voice_training: false # true for thin/none personas
    # ...
```

## Triggers

- "create a persona for..."
- "model this client..."
- "who is [Name] and what do they care about?"
- "add a stakeholder..."
- "diagnose persona quality"
- "validate persona knowledge"
- "improve persona"
- "audit personas"
- `/create-persona`

## Quick Start

```bash
# Interactive client persona (uses /interview)
./run.sh create "Jane Smith" --template client --interactive

# Expert persona with auto-learning
./run.sh create "Robert Sapolsky" --template expert --learn

# Quick stakeholder
./run.sh create "Bob Jones" --template stakeholder \
  --role "Engineering Manager" \
  --organization "Acme Corp"

# List all personas
./run.sh list

# Query persona
./run.sh show "Jane Smith" --json

# Batch create from manifest
./run.sh batch personas.yaml --dry-run
./run.sh batch personas.yaml --skip-learn
./run.sh batch personas.yaml --category writers
```

## Templates

| Template | Use Case | Auto-Learn | Default Scope |
|----------|----------|------------|---------------|
| `client` | External stakeholders, customers | No | `clients` |
| `expert` | Domain experts, researchers | Yes | `behavioral` |
| `stakeholder` | Internal team members | No | `stakeholders` |
| `adversary` | Threat actors, red-team personas | No | `threat-models` |
| `coder` | Developers, game devs, OSS maintainers | Yes | `coders` |
| `fictional` | Simulated characters, AI companions | From influences | `personas` |

## Skill Access by Template

Different personas have access to different skills for research and answering questions:

| Template | Available Skills |
|----------|-----------------|
| `coder` | `/hack`, `/battle`, `/context7`, `/github-search`, `/treesitter`, `/create-story`, `/dogpile` |
| `expert` | `/dogpile`, `/arxiv`, `/context7`, `/memory` |
| `adversary` | `/hack`, `/battle`, `/security-scan` |
| `client` | `/dogpile`, `/memory` |
| `stakeholder` | `/dogpile`, `/memory` |
| `fictional` | `/dogpile`, `/discover-movies`, `/discover-books`, `/ingest-youtube`, `/ingest-movie`, `/create-story`, `/tts-train` |

This enables rich persona interactions like:
- Ask a game developer persona how to implement inverse square algorithms
- Ask a security expert persona to review architecture for vulnerabilities
- Ask a domain expert to cite colleagues' papers on a topic

## CLI Commands

### `create` — Create a new persona

```bash
./run.sh create NAME [OPTIONS]

Options:
  --template {client,expert,stakeholder,adversary}  Persona template
  --interactive, -i    Use /interview for collaborative creation
  --learn              Trigger /ask learn for knowledge enrichment
  --scope SCOPE        Memory scope (default: template-based)
  --role ROLE          Job title or role
  --organization ORG   Company or institution
  --domain DOMAIN      Area of expertise
  --goal GOAL          Add a goal (repeatable)
  --concern CONCERN    Add a concern (repeatable)
  --colleague NAME     Add colleague relationship (repeatable)
  --bridge BRIDGE      Add Federated Taxonomy bridge (repeatable)
```

### `list` — List personas

```bash
./run.sh list [OPTIONS]

Options:
  --scope SCOPE        Filter by scope
  --template TEMPLATE  Filter by template type
  --tag TAG            Filter by tag
  --json               Output as JSON
```

### `show` — Display persona details

```bash
./run.sh show NAME [OPTIONS]

Options:
  --scope SCOPE        Memory scope to search
  --json               Output as JSON
  --with-colleagues    Include colleague details
```

### `update` — Modify existing persona

```bash
./run.sh update NAME [OPTIONS]

Options:
  --add-goal GOAL      Add a goal
  --add-concern CONCERN  Add a concern
  --add-colleague NAME   Add colleague relationship
  --set-role ROLE      Update role
  --remove-goal GOAL   Remove a goal
```

### `relate` — Create relationship between personas

```bash
./run.sh relate NAME [OPTIONS]

Options:
  --colleague NAME     Peer relationship
  --reports-to NAME    Hierarchical (reports to)
  --manages NAME       Hierarchical (manages)
  --mentors NAME       Mentorship relationship
  --bridges BRIDGE     Shared taxonomy bridges (comma-separated)
  --context TEXT       Relationship context/notes
```

### `batch` — Create multiple personas from YAML manifest

```bash
./run.sh batch MANIFEST [OPTIONS]

Options:
  --category, -c CATEGORY  Only process specific category
  --skip-learn             Skip auto-learning
  --dry-run                Preview without creating
```

## Simulacrum Validation (REQUIRED)

**A persona is NOT complete until it passes simulacrum tests.**

Simulacrum tests probe whether the persona can *reason* like the real person, not just regurgitate Wikipedia facts.

### The Simulacrum Standard

| Bad (Trivia) | Good (Simulacrum) |
|--------------|-------------------|
| "What year was Miyazaki born?" | "How would you convey emotion without dialogue?" |
| "What studio did he co-found?" | "What's wrong with fully digital animation?" |
| "Name three films he directed" | "Why does Chihiro initially refuse to eat?" |

### `simulacrum` — Deep validation

```bash
./run.sh simulacrum NAME [OPTIONS]

Options:
  --probes, -p TEXT        Probe types (default: philosophy,technique,motivation)
  --scope, -s SCOPE        Memory scope
  --json                   Output as JSON
```

Probe types:
- `philosophy` — Core worldview, beliefs, "what is art for?"
- `technique` — Craft methods, unique approaches
- `motivation` — Why they make choices, what drives them
- `criticism` — What they oppose, what's wrong with the mainstream
- `hypothetical` — How they'd handle new scenarios

Example:
```bash
./run.sh simulacrum "Hayao Miyazaki" --probes "philosophy,technique,criticism"

# Output:
Simulacrum Validation: Hayao Miyazaki
  Grade: B (Accuracy: 0.80)

Simulacrum Probes:
  ✓ What is Hayao Miyazaki's core philosophy or approach to their work?
      Good reasoning indicators (4 found)
      Persona speaking in first person (good simulacrum)
  ✓ How would Hayao Miyazaki approach a scene that needs to convey deep emotion...
      Substantive answer (127 words)
  ✗ What does Hayao Miyazaki criticize about the mainstream in their field?
      Knowledge gap indicator: 'no specific information'
```

### `simulacrum-improve` — Iterative improvement loop

```bash
./run.sh simulacrum-improve [NAME] [OPTIONS]

Options:
  --threshold, -t FLOAT    Pass threshold (default: 0.7)
  --max-iterations, -m INT Max iterations per persona (default: 3)
  --probes, -p TEXT        Probe types
  --limit, -l INT          Max personas to process
  --dry-run                Preview without changes
  --resume                 Resume from checkpoint
  --scope, -s SCOPE        Memory scope
  --json                   Output as JSON
```

Examples:
```bash
# Improve single persona until it passes
./run.sh simulacrum-improve "Hayao Miyazaki" --threshold 0.8

# Improve ALL personas in batch (overnight run)
./run.sh simulacrum-improve --scope personas --threshold 0.7 --resume

# Dry run to see what would happen
./run.sh simulacrum-improve --scope personas --dry-run --limit 10
```

The improvement loop:
1. **Validate** with simulacrum probes
2. **Identify** what's missing (philosophy? technique? first-person content?)
3. **Improve** with targeted actions:
   - Deep /dogpile for philosophy and reasoning
   - YouTube lectures/interviews for first-person perspective
   - Books for deeper knowledge
4. **Re-validate** until passing

### Workflow: Persona Creation → Simulacrum Pass

```
1. ./run.sh batch personas.yaml           # Create personas
2. ./run.sh simulacrum-improve --scope personas --resume  # Improve until valid
3. ./run.sh audit --scope personas        # Final quality report
```

A persona is ready for use ONLY when `simulacrum` shows Grade B or better.

---

## Quality Commands (v2)

### `diagnose` — Identify gaps and issues

```bash
./run.sh diagnose NAME [OPTIONS]

Options:
  --scope, -s SCOPE        Memory scope
  --json                   Output as JSON
```

Checks: Completeness, Connectivity, Freshness, Bridges (Federated Taxonomy coverage).

### `validate` — Test persona responses

```bash
./run.sh validate NAME [OPTIONS]

Options:
  --question, -q TEXT      Test question
  --expected, -e TEXT      Expected content (comma-separated)
  --ground-truth, -g PATH  YAML/JSON file with tests
  --scope, -s SCOPE        Memory scope
  --json                   Output as JSON
```

Supports single-question and batch ground-truth file testing.

### `improve` — Iterative enhancement

```bash
./run.sh improve NAME [OPTIONS]

Options:
  --threshold, -t FLOAT    Quality threshold (default: 0.7)
  --max-iterations, -m INT Max iterations (default: 3)
  --dry-run                Preview actions without executing
  --scope, -s SCOPE        Memory scope
  --json                   Output as JSON
```

Convergence loop: /dogpile for missing sources, discover books, ingest YouTube, enrich colleague graph, extract QRA pairs.

### `audit` — Batch quality assessment

```bash
./run.sh audit [OPTIONS]

Options:
  --scope, -s SCOPE        Scope to audit
  --min-quality FLOAT      Only show below threshold
  --limit, -l INT          Max personas to audit
  --report                 Generate markdown report
  --json                   Output as JSON
```

Shows grade distribution (A-F), common gaps, and failing personas.

### `export` / `import` — Backup and restore

```bash
./run.sh export NAME --format json > persona.json
./run.sh import persona.json --scope new-project
```

See [SCHEMA.md](references/SCHEMA.md) for the full persona data schema, historical context fields, and voice profile fields.

See [ARCHITECTURE.md](references/ARCHITECTURE.md) for taxonomy integration, relationship edges, BDI Theory of Mind, voice/TTS training, PersonaPlex, and persona monitoring.

See [EXAMPLES.md](references/EXAMPLES.md) for detailed usage examples including client, expert, adversary, coder, batch creation, and fictional persona workflows.

## Dependencies

- `/memory` -- Storage and recall
- `/interview` -- Interactive creation
- `/ask` -- Knowledge enrichment (learn)
- `common/taxonomy` -- Federated Taxonomy bridges
- `/tts-train` -- Voice model training (Qwen3-TTS)
- `/ingest-youtube` -- YouTube audio download
- Theory of Mind: Based on Horus persona architecture
- PersonaPlex: NVIDIA's full-duplex speech-to-speech model
- resemblyzer/speechbrain: Speaker embedding extraction

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PERSONA_DEFAULT_SCOPE` | Default memory scope | `personas` |
| `PERSONA_AUTO_LEARN` | Auto-learn for experts | `true` |
| `PERSONA_MONITOR_FREQUENCY` | Default check frequency | `weekly` |
