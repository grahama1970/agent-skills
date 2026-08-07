---
name: recommend-skill-chain
description: Shadow-LEGO cascade recommender for skill chain composition. Ranks chains by bond strength and elegance.
internal: true
provides:
  - skill-chain-recommendation
  - chain-ranking
  - chain-evaluation
composes:
  - skill-lab
  - assistant
  - memory
  - scillm
  - taxonomy
  - task-monitor
taxonomy:
  - composition
  - recommendation
  - routing
triggers:
  - "recommend skills"
  - "which skills"
  - "skill chain"
  - "compose skills"
  - "what skills do I need"
disciplines:
  - memory-knowledge
  - agentic-orchestration
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# /recommend-skill-chain

Shadow-LEGO cascade recommender for skill chain composition. Given a task description, recommends an optimal chain of skills to compose, ranked by bond strength and elegance.

## Usage

```bash
# Recommend a skill chain for a task
./run.sh recommend --task "ingest this PDF and learn from it" --json

# Top N recommendations
./run.sh recommend --task "..." --limit 3

# Evaluate a specific skill pair/chain
./run.sh evaluate extractor doc2qra --json

# List known chains from training data
./run.sh chains

# Shadow-LEGO agreement rate
./run.sh shadow-status

# Retrain from accumulated labels
./run.sh train

# Health check
./run.sh status
```

## Architecture

```
Task description
    ↓
[Memory] recall prior successful chains
    ↓
[Tier 0] Heuristic: transition matrix + trigger matching + gap detector
    ↓
[Tier 0.5] Classifier: assistant.classify(task="skill-chain-router")
    ↓
[Tier 2] Teacher: scillm (only if confidence < 0.7)
    ↓
[Rank] bond_predictor + energy_model → elegance score
    ↓
[Log] shadow comparison + recommendation for self-improvement
```

Gather-and-rank strategy: collects candidates from all tiers, ranks by `bond_strength * elegance`, unlike CascadeRunner which stops at first confident tier.

## Delegation

This skill is a **thin orchestrator** — every computation delegates to existing functions:

- **Graph**: `skill-lab/scripts/scan_soup.py` → `scan_soup()`
- **Chains**: `skill-lab/scripts/transition_matrix.py` → `predict_chain()`
- **Gaps**: `skill-lab/scripts/gap_detector.py` → `detect_gaps()`
- **Bonds**: `skill-lab/scripts/bond_predictor.py` → `predict_chain_success()`
- **Energy**: `skill-lab/scripts/energy_model.py` → `compute_chain_energy()`, `compute_elegance()`
- **Classifier**: `assistant/assistant.py` → `classify(task="skill-chain-router")`
- **Teacher**: `assistant/assistant.py` → `validate(task="chain-rationale")`
- **Shadow**: `common/cascade.py` → `CascadeRunner.shadow_report()`

## Self-Improvement

Logs every recommendation to `recommendations.jsonl`. Shadow-compares classifier vs teacher to `shadow.jsonl`. Run `./run.sh train` to trigger chain_miner refresh + classifier retrain.
