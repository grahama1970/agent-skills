---
name: skill-lab
description: >
  Self-replicating skill creation via symbiogenesis. Scans the skill soup,
  identifies capability gaps, crafts missing pieces via lab skills, validates
  against best-practices, competes candidates via /battle, and promotes winners.
  Use when a task requires capabilities no existing skill provides.
triggers:
  - create skill
  - new skill
  - skill creation
  - skill gap
  - compose skills
  - symbiogenesis
metadata:
  short-description: Symbiogenic skill creation engine
provides:
  - skill-creation
  - skill-scaffolding
  - bond-prediction
  - composition-planning
  - attractor-detection
  - granularity-analysis
  - continuous-evolution
composes:
  - common
  - memory
  - plan
  - best-practices-skills
  - skills-ci
  - prompt-lab
  - gpt-lab
  - classifier-lab
  - create-gpt
  - create-classifier
  - battle
  - anvil
  - monitor-security
  - skills-broadcast
  - taxonomy
  - interview
  - task-monitor
  - scillm
  - scheduler
  - agentic-evals
taxonomy:
  - creation
  - composition
  - self-improvement
  - symbiogenesis
  - evolution
  - precision
disciplines:
  - developer-tooling
  - agentic-orchestration
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Skill Lab — Symbiogenic Skill Creation

Create new skills by **composing existing skills + crafting only the missing pieces**.

Inspired by biological symbiogenesis (Agüera y Arcas BFF, Margulis endosymbiosis):
complexity emerges from composition of existing replicators, not from scratch.

## Phase 0: Capability Overlap Check (MANDATORY — Prevents Catastrophic Forgetting)

**Before creating ANY new skill, query existing infrastructure for overlap.**

### Pre-Creation Silo Detection

```bash
# 1. Query /memory for existing solutions covering the proposed capability
memory-agent recall --q "<proposed skill description>"
memory-agent recall --q "<proposed skill capabilities>"

# 2. Scan existing skills for coverage
./run.sh scan --task "<proposed skill description>"
```

### Decision Gate

| Overlap | Action |
|---------|--------|
| Existing skills cover >60% | **WARN**: "Existing skill X covers this. Extend it instead." |
| /memory RecallSource exists | **BLOCK**: "Do NOT build new search. Register as RecallSource." |
| /taxonomy already extracts these tags | **BLOCK**: "Do NOT reimplement bridge extraction." |
| No overlap found | **PROCEED** with creation |

### Anti-Silo Rules for New Skills

New skills MUST NOT:
- Contain their own AQL queries that bypass `/memory recall`
- Implement their own taxonomy/bridge extraction (use `/taxonomy`)
- Build their own search (use RecallSources)
- Create their own ArangoDB connections (use `/memory` infrastructure)

New skills MUST:
- Compose with `/memory` for any retrieval needs
- Compose with `/taxonomy` for any tag extraction
- Register new data as RecallSource + ArangoSearch view if needed
- Document in SKILL.md frontmatter which existing skills they compose with

### Shadow-LEGO Default Architecture (MANDATORY)

**Shadow-LEGO is the DEFAULT architecture for any skill that touches the knowledge graph.**

The pattern is: Shadow classifiers produce entity seeds, LEGO-GraphRAG expands seeds
through the graph, then synthesis/assessment produces output. Skills MUST NOT reinvent
any layer of this pipeline.

```
Query → /assistant classify (Shadow layer — entity seeds)
          │
          ▼
        /memory traverse (LEGO layer — graph expansion)
          │
          ▼
        /taxonomy extract (bridge tags — cross-domain linking)
          │
          ▼
        Synthesis / Assessment (persona-driven evaluation)
```

#### Shadow-LEGO Routing Rules

| Proposed skill needs... | MUST use | MUST NOT build |
|------------------------|----------|----------------|
| Entity extraction | `/assistant classify` (Shadow classifier layer) | Custom regex, NER, or keyword matching |
| Graph traversal | `/memory traverse` (LEGO expansion layer) | Raw AQL traversal queries |
| Taxonomy / bridge tags | `/taxonomy extract` (bridge tag extraction) | Custom keyword dictionaries |
| New ArangoDB queries | Register as RecallSource in `/memory` | Standalone AQL or ArangoSearch |
| Quality assessment | Persona-driven assessment via existing personas | Ad-hoc scoring functions |

#### Shadow-LEGO Compliance Checklist

Before creating ANY new skill, /skill-lab MUST verify every item. A single
unchecked box is a **BLOCK** — the skill cannot proceed to Phase 1.

- [ ] **Entity extraction**: Uses `/assistant classify` (NOT custom regex/NER)
- [ ] **Graph traversal**: Uses `/memory traverse` (NOT raw AQL)
- [ ] **Taxonomy**: Uses `/taxonomy extract` (NOT custom keyword dicts)
- [ ] **Search**: Uses `/memory recall` RecallSource (NOT custom search)
- [ ] **Assessment**: Uses persona-driven assessment via existing personas (NOT ad-hoc scoring)

Items marked N/A (skill does not need that capability) count as checked.
Items where the skill builds its own implementation are a **FAIL** — extend
the existing Shadow-LEGO infrastructure instead.

### Validation (Added to Phase 5)

The validation cascade now includes silo detection:

| Check | Signal | Gate |
|-------|--------|------|
| AQL bypass | Skill contains raw AQL outside /memory | **FAIL** |
| Search bypass | Skill implements BM25/vector search | **FAIL** |
| Taxonomy bypass | Skill extracts bridges without /taxonomy | **WARN** |

## Core Principle

```
New Skill = skill_1(HAVE) + skill_2(CREATE) + skill_3(HAVE) + skill_4(CREATE)
```

Skills are chemical elements. `provides:` and `composes:` are their valence shells.
Lab skills are catalysts — they enable reactions without being consumed.
`/battle` is natural selection. `best-practices-*` are the physics.

## Quick Start

```bash
# Discover what skills exist and what gaps remain for a task
./run.sh scan --task "continuously monitor arxiv for new papers and learn them"

# Generate a composition manifest (the reaction equation)
./run.sh compose --task "continuously monitor arxiv for new papers and learn them"

# Craft missing capabilities, validate, and promote
./run.sh craft --manifest composition_manifest.yml

# Full lifecycle: scan → compose → craft → validate → compete → promote
./run.sh create --task "continuously monitor arxiv for new papers and learn them"

# Docker-isolated creation (recommended for untrusted tasks)
./run.sh create --task "..." --docker
```

## Architecture

```
Task arrives requiring new capability
    │
    ▼
┌─────────────────────────────────────┐
│  PHASE 1: SCAN SOUP                 │  scan_soup.py
│  Parse all .pi/skills/SKILL.md      │
│  Build capability graph from        │
│    provides: / composes: fields     │
│  Register in /memory for multi-hop  │
│  Output: capability_graph.json      │
└─────┬───────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────┐
│  PHASE 2: IDENTIFY GAPS             │  gap_detector.py
│  Decompose task into capability     │
│    requirements (via LLM)           │
│  Match requirements to graph        │
│  Output: composition_manifest.yml   │
│    HAVE: [existing skills]          │
│    CREATE: [missing capabilities]   │
└─────┬───────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────┐
│  PHASE 3: CRAFT (via labs)          │  crafter.py
│  For each CREATE capability:        │
│    Route to appropriate lab:        │
│      /prompt-lab → prompt tuning    │
│      /classifier-lab → classifiers  │
│      /gpt-lab → small model tuning  │
│    Self-improvement cycle:          │
│      iterate → evaluate → correct   │
│      → benchmark → promote          │
│  Output: crafted skill directory    │
└─────┬───────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────┐
│  PHASE 4: SCAFFOLD                  │  scaffolder.py
│  Generate SKILL.md with frontmatter │
│  Generate run.sh orchestrator       │
│  Wire HAVE skills via subprocess    │
│  Wire CREATE capabilities inline    │
│  Generate sanity.sh                 │
│  Output: complete skill directory   │
└─────┬───────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────┐
│  PHASE 5: VALIDATE                  │  validator.py
│  T0: /skills-ci (best-practices)   │
│  T1: /monitor-security scan        │
│  T2: /battle (if multiple cands)   │
│  T3: /anvil (no-vibes hardening)   │
│  Output: validation_report.json     │
└─────┬───────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────┐
│  PHASE 6: PROMOTE                   │
│  Install to .pi/skills/             │
│  Register in /memory graph          │
│  /skills-broadcast to all IDEs      │
│  Update capability_vocabulary.yml   │
│  Soup is now richer (niche constr.) │
└─────────────────────────────────────┘
```

## Commands

### Skill Creation

| Command | Description |
|---------|-------------|
| `./run.sh scan` | Scan skill soup and build capability graph |
| `./run.sh scan --task "..."` | Scan + show which skills match a task |
| `./run.sh compose --task "..."` | Generate composition manifest for a task |
| `./run.sh craft --manifest FILE` | Craft missing capabilities from manifest |
| `./run.sh create --task "..."` | Full lifecycle: scan → compose → craft → validate → promote |
| `./run.sh create --task "..." --docker` | Same but Docker-isolated (like /battle) |
| `./run.sh validate SKILL_DIR` | Run validation cascade on a skill |
| `./run.sh graph` | Visualize the capability graph |
| `./run.sh graph --json` | Export capability graph as JSON |

### Runtime Composition (Run Mode)

| Command | Description |
|---------|-------------|
| `./run.sh run --task "..."` | Compose and show a skill pipeline |
| `./run.sh run --task "..." --execute` | Compose and execute the pipeline |
| `./run.sh run --task "..." --dry-run` | Preview execution without running |
| `./run.sh run --task "..." --json` | Output pipeline as JSON |
| `./run.sh run --task "..." --optimize` | Find shorter equivalent chain |

### Bond Prediction (3-Tier Cascade)

| Command | Description |
|---------|-------------|
| `./run.sh predict --skill-a X --skill-b Y` | Predict bond between two skills |
| `./run.sh chain --skills "a,b,c"` | Predict chain success probability |
| `./run.sh train bootstrap` | Bootstrap labels from /scillm teacher |
| `./run.sh train loop` | Full training loop (bootstrap→train→gate) |
| `./run.sh warm-pond --iterations 200` | Docker-isolated batch simulations |
| `./run.sh harvest` | Nightly harvest (traces + battle + warm pond) |
| `./run.sh bond-stats` | Show training data statistics |
| `./run.sh attractors` | Detect attractor compositions from warm pond |
| `./run.sh granularity` | Check skill granularity (SUBLEQ lesson) |
| `./run.sh evolve` | Register nightly evolution with /scheduler |
| `./run.sh evolve --status` | Show evolution health report |

## Composition Manifest Schema

See `references/manifest_schema.yml` for full schema. Example:

```yaml
name: learn-arxiv
task: "Monitor arxiv, extract papers, store to memory"
composition:
  have:
    - skill: arxiv
      role: "Search papers"
      bond: "run.sh search"
    - skill: extractor
      role: "Extract content and learn to memory"
      bond: "run.sh <file> --learn"
    - skill: memory
      role: "Store knowledge"
      bond: "run.sh learn"
  create:
    - capability: topic-relevance-filter
      lab: prompt-lab
      description: "Score paper relevance to user interests"
    - capability: dedup-checker
      lab: null  # simple code, no lab needed
      description: "Check if already ingested via memory recall"
```

## Lab Routing

| Capability Type | Lab | Method |
|----------------|-----|--------|
| Prompt/instruction | `/prompt-lab` | Iterate prompt, evaluate, self-correct |
| Classification model | `/classifier-lab` | Train vision/text classifier |
| Small inference model | `/gpt-lab` | Fine-tune, benchmark, compare |
| Simple code logic | None | Direct implementation by LLM |
| Complex orchestration | `/plan` + `/orchestrate` | Task file with quality gates |

## Validation Cascade

Inspired by `/monitor-security` four-tier probe cascade:

| Tier | Tool | What it checks | Gate |
|------|------|---------------|------|
| T0 | `/skills-ci` | Frontmatter, structure, best-practices | MUST PASS |
| T1 | `/monitor-security` | OWASP scan, dependency audit, secrets | MUST PASS |
| T2 | `/battle` | Multiple candidates compete (if >1) | BEST WINS |
| T3 | `/anvil` | No-vibes hardening, evidence-based judge | RECOMMENDED |

Skills with executable scripts are **2.12x more likely** to contain vulnerabilities
(Agent Skills Survey, arxiv:2602.12430). T1 is non-negotiable.

## Docker Isolation

When `--docker` is specified, crafting and validation run inside isolated containers
using the same security profile as `/battle`:

- `--cap-drop ALL` — remove all Linux capabilities
- `--security-opt no-new-privileges`
- `--memory 512m` — memory cap
- `--read-only` — read-only root filesystem
- Seccomp profile blocking dangerous syscalls

## Graph Registration

Every skill is registered in `/memory` as a node in the knowledge graph,
enabling multi-hop traversal for capability discovery:

```
skill:extractor ──provides──► capability:pdf-extraction
skill:extractor ──composes──► skill:memory
skill:extractor ──composes──► skill:scillm
skill:learn-arxiv ──composes──► skill:arxiv
skill:learn-arxiv ──composes──► skill:extractor
```

`/taxonomy` bridge tags enable cross-domain discovery — a security skill
and an extraction skill might share `taxonomy:validation` tags.

## Self-Improvement Cycle

Like `/prompt-lab` and `/gpt-lab`, `/skill-lab` follows the iterate-evaluate-correct
loop for each crafted capability:

```
1. Draft capability (via appropriate lab)
2. Evaluate against task requirements
3. Self-correct based on evaluation
4. Benchmark against alternatives
5. Promote best candidate
```

For competitive selection (multiple candidates), `/battle` runs them in
Docker isolation with AIxCC-style scoring. Best survives.

See [BOND_PREDICTION.md](references/BOND_PREDICTION.md) for the 3-tier bond prediction cascade, training data sources, teacher-student loop, warm pond simulations, and BFF alignment.

---

# Run 200 simulations in Docker isolation (overnight)
./run.sh warm-pond --iterations 200

# Without Docker (quick local test)
./run.sh warm-pond --iterations 50 --no-docker

# Full nightly harvest (traces + battle + warm pond + retrain)
./run.sh harvest
```

The warm pond:
1. Spins up a Docker container (same security as `/battle`)
2. Randomly composes 2-4 skills into chains
3. Executes each chain and records success/failure
4. Harvests results as training labels for bond models
5. After 100s of iterations, bond affinities emerge from data

This is a **long-running overnight process** — designed for `/scheduler`
to run nightly alongside other harvest jobs.

### Evolutionary Lifecycle

```
         CREATION                    SELECTION                    EXTINCTION
  ┌──────────────────┐      ┌──────────────────────┐      ┌────────────────┐
  │ /skill-lab create │  →  │ /battle competition   │  →  │ Deprecation    │
  │ /create-gpt       │      │ Warm pond simulation  │      │ Low bond score │
  │ /create-classifier │      │ Execution trace data  │      │ No co-occurrence│
  │ /prompt-lab        │      │ Shadow mode validation│      │ Failed gates   │
  └──────────────────┘      └──────────────────────┘      └────────────────┘
           │                          │                          │
           ▼                          ▼                          ▼
     Skills created          Winners strengthened          Skills archived
     with valence            Losers weakened               Bonds removed
     shells defined          Models retrained              Soup simplifies
```

- **Winners**: Bond affinities increase, models trained on success patterns,
  skill gets its own `/create-classifier` and `/create-gpt` if it develops
  enough domain-specific inference needs
- **Losers**: Bond affinities decrease, skill composition deprioritized,
  eventually deprecated if consistently losing
- **Extinct**: Skills with zero co-occurrence across warm pond + production
  traces are candidates for deprecation — like species that can't find mates
