---
name: monitor-personas
description: >
  Self-contained persona learning pipeline. Monitors ALL sources (YouTube, RSS, arXiv, Books, Movies, Music, Code),
  extracts QRAs, classifies into Intent/Persona streams, learns to memory with Federated Taxonomy,
  archives episodically, verifies edges, reflects on gaps, and trains persona models.
allowed-tools: Bash, Read
triggers:
  - monitor personas
  - persona monitoring
  - check persona sources
  - update personas
  - persona refresh
  - close the loop
  - persona pipeline
metadata:
  short-description: Self-contained persona learning pipeline with full automation

provides:
  - monitor-personas
composes:
  - scheduler
  - memory
  - monitor-skills
  - task-monitor
  - agentic-evals
disciplines:
  - observability-operations
  - persona-simulation
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Monitor Personas - Self-Contained Learning Pipeline

**CRUCIAL** for keeping Horus and all expert personas current with fresh knowledge.

## Continuous Operation (Non-Negotiable)

This skill is **always-on**. It:
- Runs on its configured schedule indefinitely — it NEVER stops unless explicitly halted by the user
- The agent MUST NOT stop and wait for the human to ask for status or remember to check
- If a cycle fails, diagnose the failure, attempt auto-repair, and continue
- Only escalate to the human if genuinely blocked after exhausting /dogpile research
- Gracefully handles restarts and maintains state across cycles
- Is designed for multi-day/week/month autonomous operation

**Anti-pattern**: Reporting status and waiting for the human to ask "what next?" is UNACCEPTABLE. The agent must proactively fix issues and continue the monitoring loop.

## Full Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  SELF-CONTAINED PERSONA LEARNING PIPELINE                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │               MULTI-SOURCE CHECK (2 AM Nightly)                   │      │
│  │  YouTube │ RSS │ arXiv │ Books │ Movies │ Music │ Code           │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                  │                                          │
│                                  ▼                                          │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │                    INGEST (3 AM Nightly)                          │      │
│  │  ingest-youtube │ consume-feed │ arxiv │ ingest-book │ etc       │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                  │                                          │
│                                  ▼                                          │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                     │
│  │  /extractor │───►│  /taxonomy  │───►│  /memory    │                     │
│  │  QRA pairs  │    │  bridges +  │    │  learn with │                     │
│  │  + summary  │    │  collection │    │  scope+tags │                     │
│  └─────────────┘    └─────────────┘    └─────────────┘                     │
│                                              │                              │
│                    ┌─────────────────────────┤                              │
│                    │                         │                              │
│                    ▼                         ▼                              │
│  ┌─────────────────────────────┐   ┌─────────────────────────────┐        │
│  │    INTENT STREAM            │   │    PERSONA STREAM            │        │
│  │  (Hidden Reasoning)         │   │  (Visible Reasoning)         │        │
│  │  → Query routing data       │   │  → Persona fine-tune data    │        │
│  └─────────────────────────────┘   └─────────────────────────────┘        │
│                                              │                              │
│                                              ▼                              │
│                                   ┌─────────────────────────────┐          │
│                                   │    /episodic-archiver       │          │
│                                   │  Full session context       │          │
│                                   │  Track UNRESOLVED gaps      │          │
│                                   └─────────────────────────────┘          │
│                                              │                              │
│                    ┌─────────────────────────┼─────────────────────┐       │
│                    ▼                         ▼                     ▼       │
│         ┌────────────────┐        ┌────────────────┐    ┌────────────────┐│
│         │ /edge-verifier │        │   /dogpile     │    │ /train-persona ││
│         │ Validate new   │        │ Research gaps  │    │ Generate data  ││
│         │ relationships  │        │                │    │ Train LoRA     ││
│         └────────────────┘        └────────────────┘    └────────────────┘│
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
cd .pi/skills/monitor-personas

# Check all personas for new content
./run.sh check

# Check ALL sources (YouTube, RSS, arXiv, etc.)
./run.sh check-all

# Ingest new content
./run.sh ingest --priority HIGH

# Run complete pipeline
./run.sh close-loop

# Show pipeline status
./run.sh pipeline-status

# Register full nightly pipeline with scheduler
./run.sh register-nightly
```

## Commands

### Source Monitoring

| Command | Description |
|---------|-------------|
| `check` | Check YouTube personas for new content |
| `check-all` | Check ALL sources (YouTube, RSS, arXiv, Books, Movies, Music, Code) |
| `ingest` | Ingest new YouTube content |
| `ingest-all` | Ingest from all source types |
| `status` | Show current monitoring status |
| `list-personas` | List all configured personas |

### Learning Pipeline

| Command | Description |
|---------|-------------|
| `learn` | Learn pending content to memory with taxonomy |
| `extract` | Extract content to QRAs via /extractor |
| `classify-streams` | Classify into Intent or Persona streams |

### Reflection Loop

| Command | Description |
|---------|-------------|
| `archive` | Archive sessions to episodic memory |
| `verify-edges` | Verify relationships with existing knowledge |
| `reflect` | Research knowledge gaps via /dogpile |

### Training & Status

| Command | Description |
|---------|-------------|
| `train` | Generate training data + trigger train-persona |
| `pipeline-status` | Show overall pipeline status |
| `close-loop` | Run complete pipeline (all steps) |

### Automation

| Command | Description |
|---------|-------------|
| `register-nightly` | Register full 8-step nightly pipeline |
| `register-basic` | Register basic 3-step monitoring only |

## Nightly Schedule

```
2:00 AM  - Check all sources (YouTube, RSS, arXiv, etc.)
3:00 AM  - Ingest new content
4:00 AM  - Extract to QRAs
4:30 AM  - Classify streams (Intent vs Persona)
5:00 AM  - Learn to memory with taxonomy
5:30 AM  - Archive sessions to episodic memory
6:00 AM  - Reflect on gaps (trigger /dogpile)
7:00 AM  - Train models (Sunday only)
```

## Intent vs Persona Streams

Content is classified into two streams for different purposes:

### Intent Stream (Hidden Reasoning)
- Content for training query routing models
- Accuracy is measured by output correctness
- Hidden reasoning traces are acceptable
- Examples: ml_training, programming categories

### Persona Stream (Visible Reasoning)
- Content for training persona fine-tuning
- Trace quality IS the product
- Visible reasoning must be exemplary
- Examples: video_generation, horus_lore categories

## Multi-Source Support

| Source | Check Method | Ingest Skill | Learn Scope |
|--------|-------------|--------------|-------------|
| YouTube | yt-dlp count | ingest-youtube | persona.scope |
| RSS | consume-feed headers | consume-feed | feeds |
| arXiv | arxiv API | arxiv learn | research |
| Books | ingest-book Readarr | ingest-book | books |
| Movies | ingest-movie | consume-movie | movies |
| Music | ingest-yt-history | consume-music | music |
| Code | glob scan | ingest-code | code |

## Monitored Personas

### Video Generation Experts (HIGH Priority)

| Persona | Source | Scope | Purpose |
|---------|--------|-------|---------|
| Dan Kieft | YouTube | dan-kieft | Kling AI video generation |
| AI Video School | YouTube | ai-video | General AI video |
| Nobody & Computer | YouTube | horus-filmmaking | AI filmmaking philosophy |

### ML Training Experts (HIGH Priority)

| Persona | Source | Scope | Purpose |
|---------|--------|-------|---------|
| Trelis Research | YouTube | trelis | Practical ML, fine-tuning |
| Ronan McGovern | YouTube | ronan | RAG, vector databases |
| DeepLearningAI | YouTube | andrew-ng | Enterprise ML |
| Andrej Karpathy | YouTube | karpathy | Deep learning theory |

### Programming/Education (MEDIUM Priority)

| Persona | Source | Scope | Purpose |
|---------|--------|-------|---------|
| Fireship | YouTube | fireship | Quick tech tutorials |
| 3Blue1Brown | YouTube | 3blue1brown | Math education |
| Code4AI | YouTube | code4ai | AI coding tutorials |

### Horus Lore (MEDIUM Priority)

| Persona | Source | Scope | Purpose |
|---------|--------|-------|---------|
| Luetin09 | YouTube | horus_lore | 40K deep lore |
| TheRemembrancer | YouTube | horus_lore | 40K narrations |

## Integration with Other Skills

| Skill | Integration |
|-------|-------------|
| `/taxonomy` | Bridge tags for multi-hop traversal |
| `/memory` | Knowledge storage with scope/tags |
| `/extractor` | QRA extraction from content |
| `/episodic-archiver` | Session archival for reflection |
| `/edge-verifier` | Relationship verification |
| `/dogpile` | Gap research |
| `/train-persona` | LoRA model training |
| `/scheduler` | Nightly automation |

## State Files

| File | Purpose |
|------|---------|
| `~/.pi/monitor-personas/state.json` | Persona check state |
| `~/.pi/monitor-personas/learned.json` | Learned transcript paths |
| `~/.pi/monitor-personas/extracted.json` | Extracted content paths |
| `~/.pi/monitor-personas/stream_state.json` | Intent vs Persona classifications |
| `~/.pi/monitor-personas/gap_tracker.json` | Unresolved knowledge gaps |
| `~/.pi/monitor-personas/training_state.json` | Training data + model versions |

## Adding New Personas

Edit `personas.yaml`:

```yaml
video_generation:
  - id: new-expert
    name: "New Expert Name"
    priority: HIGH
    scope: new-expert
    sources:
      - type: youtube
        handle: "https://www.youtube.com/@NewExpert"
      - type: rss
        url: "https://newexpert.com/feed.xml"
      - type: code
        repo: "github.com/newexpert/examples"
    taxonomy_hints:
      - Precision
      - Innovation
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `PERSONA_MONITOR_STATE_DIR` | State directory (default: ~/.pi/monitor-personas) |
| `PERSONA_MONITOR_PRIORITY` | Default priority filter |
| `PERSONA_MONITOR_DRY_RUN` | Enable dry-run mode globally |

## Troubleshooting

### Pipeline status check

```bash
./run.sh pipeline-status
```

### Check specific command

```bash
./run.sh check --json | jq
./run.sh learn --dry-run
```

### Reset state

```bash
rm ~/.pi/monitor-personas/learned.json
./run.sh learn  # Re-learn all
```
