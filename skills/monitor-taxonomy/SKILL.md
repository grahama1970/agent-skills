---
name: monitor-taxonomy
description: >
  Three-tier cascade taxonomy quality monitor. Assesses whether Heart/Mind
  taxonomy tags and collection_tags on memory documents are CORRECT (not just
  present). Uses T0 heuristic → T1.5 classifier/GPT → T2 Brandon teacher cascade.
  Accumulates training labels for autonomous quality assessment.

  Heart/Mind field conventions:
  - `mind` (8 SPARTA tactical tags: Detect/Evade/Exploit/Harden/Isolate/Model/Persist/Restore)
    lives on `sparta_qra` documents.
  - `heart` (6 emotional tags: anger/fear/joy/neutral/sadness/trust)
    lives on `lessons` documents.
triggers:
  - monitor taxonomy
  - taxonomy quality
  - check taxonomy quality
  - taxonomy cascade
  - mind tag quality
  - heart tag quality
  - run taxonomy monitor
allowed-tools: Bash
metadata:
  short-description: Three-tier cascade taxonomy quality monitor (Heart/Mind)

provides:
  - monitor-taxonomy
composes:
  - task-monitor
  - agentic-evals
disciplines:
  - observability-operations
  - memory-knowledge
---

# Monitor Taxonomy

Taxonomy quality monitor that assesses correctness of Heart/Mind tags and
collection_tags on memory documents via a three-tier cascade.

**Key distinction from monitor-memory**: monitor-memory checks coverage/method/drift.
monitor-taxonomy checks **correctness** via cascade validation.

## Heart/Mind Fields

| Field   | Collection   | Valid vocabulary (13 total)                                          |
|---------|--------------|----------------------------------------------------------------------|
| `mind`  | `sparta_qra` | Detect, Evade, Exploit, Harden, Isolate, Model, Persist, Restore   |
| `heart` | `lessons`    | anger, fear, joy, sadness, trust                                     |

The cascade reads whichever field (`mind` or `heart`) is present in the input
document. The legacy key `bridge_attributes` is accepted as a fallback but
should not appear on new documents.

## Continuous Operation (Non-Negotiable)

This skill is **always-on**. It:
- Runs on its configured schedule indefinitely — it NEVER stops unless explicitly halted by the user
- The agent MUST NOT stop and wait for the human to ask for status or remember to check
- If a cycle fails, diagnose the failure, attempt auto-repair, and continue
- Only escalate to the human if genuinely blocked after exhausting /dogpile research
- Gracefully handles restarts and maintains state across cycles
- Is designed for multi-day/week/month autonomous operation

**Anti-pattern**: Reporting status and waiting for the human to ask "what next?" is UNACCEPTABLE. The agent must proactively fix issues and continue the monitoring loop.

## Architecture

```
Document with `mind` (QRA) or `heart` (lessons) tags
         │
    ┌────▼────┐
    │  Tier 0  │  Heuristic: vocabulary validation, null check,
    │ (instant) │  text-tag coherence (keyword overlap score)
    └────┬────┘
         │ confidence < 0.80
    ┌────▼─────┐
    │ Tier 1.5  │  Trained classifier (after 50+ labels)
    │ (~200ms)  │  OR small GPT (after /create-gpt training)
    └────┬─────┘
         │ confidence < 0.85 ("maybe" zone)
    ┌────▼────┐
    │  Tier 2  │  Brandon (scillm persona) — authoritative teacher
    │ (~3s)    │  Full semantic assessment → training_labels.jsonl
    └────┬────┘
         │
    Grade: CORRECT / MISTAGGED / MISSING / HALLUCINATED
    Action: keep / re-extract / remove / flag
```

## Commands

```bash
# Run all probes
./run.sh check --json

# Run a specific tier
./run.sh check --tier 0 --autofix --json

# Run a single probe
./run.sh check --probe null-bridge-gc --json

# Dashboard
./run.sh dashboard

# Status (labels, shadow, classifier)
./run.sh status

# Register nightly schedule
./run.sh register-nightly

# Help
./run.sh help
```

## Probes

### Tier 0 — Heuristic Quality (instant, deterministic)

| ID  | Probe                        | Collections checked        | Auto-Fix |
|-----|------------------------------|---------------------------|----------|
| P01 | null-tag-gc                  | sparta_qra (mind), lessons (heart) | Yes |
| P02 | vocabulary-violation         | sparta_qra (mind), lessons (heart) | Yes |
| P03 | text-tag-coherence           | sparta_qra (mind), lessons (heart) | No  |
| P04 | collection-tag-violation     | lessons                   | Yes      |
| P05 | stale-taxonomy               | sparta_qra, lessons       | No       |

### Tier 1.5 — Classifier/GPT Quality (after training)

| ID  | Probe                     | Auto-Fix |
|-----|---------------------------|----------|
| P10 | classifier-quality-check  | No       |
| P11 | shadow-agreement          | No       |
| P12 | confidence-distribution   | No       |

### Tier 2 — Brandon Teacher + Training

| ID  | Probe              | Auto-Fix |
|-----|--------------------|----------|
| P20 | teacher-validate   | No       |
| P21 | label-accumulation | No       |
| P22 | shadow-tracking    | No       |
| P23 | retrain-trigger    | Yes      |

## Nightly Schedule

```
03:00  monitor-taxonomy T0: Heuristic quality (P01-P05) + auto-fix
03:15  monitor-taxonomy T1.5: Classifier quality (P10-P12) — skips if no model
03:30  monitor-taxonomy T2: Brandon teacher (P20-P23) — validates flagged docs
```

Runs BEFORE monitor-memory at 05:00. Taxonomy fixes applied before coverage measured.

## Environment Variables

| Variable                       | Default                        | Description              |
|-------------------------------|--------------------------------|--------------------------|
| `ARANGO_URL`                   | `http://127.0.0.1:8529`      | ArangoDB endpoint        |
| `ARANGO_DB`                    | `memory`                       | Database name            |
| `MONITOR_TAXONOMY_STATE_DIR`   | `~/.pi/monitor-taxonomy`      | State directory          |
| `TAXONOMY_RETRAIN_THRESHOLD`   | `50`                           | Labels to trigger retrain|
| `TAXONOMY_SAMPLE_SIZE`         | `100`                          | Nightly sample size      |
| `TAXONOMY_COHERENCE_THRESHOLD` | `0.20`                         | Min keyword overlap      |
| `TAXONOMY_STALE_DAYS`          | `90`                           | Days before stale        |
