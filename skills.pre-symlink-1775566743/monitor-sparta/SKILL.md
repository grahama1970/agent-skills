---
name: monitor-sparta
description: >
  Continuous SPARTA quality monitor. Runs the 3-tier validation cascade
  alongside Stage 12 QRA generation — Tier 0 deterministic, Tier 1.5 trained GPT
  (via /assistant), Tier 2 Brandon (edge cases). Accumulates labels, auto-triggers
  /create-gpt training at 2000 labels, and tracks convergence.
allowed-tools:
  - Bash
  - Read
triggers:
  - monitor sparta
  - sparta quality
  - pipeline health
  - sparta convergence
  - qra quality monitor
metadata:
  short-description: Continuous 3-tier SPARTA quality monitor with auto-training

provides:
  - monitor-sparta
composes:
  - create-figure
  - task-monitor
---

# Monitor SPARTA

**Continuous quality monitor for the SPARTA QRA pipeline.** Runs alongside Stage 12
and validates at configurable checkpoints (default: every 10K QRAs).

## Architecture

```
Stage 12 (QRA generation, running)
    │
    ├── QRA count: 75K → 80K → 90K → 100K
    │
monitor-sparta (this skill)
    │
    ├── Poll QRA count every 60s
    ├── At checkpoint (every 10K):
    │   ├── Tier 0: Deterministic checks (free, instant)
    │   ├── Tier 1.5: GPT via /assistant (free, ~200ms)
    │   │   └── Low confidence → escalate to Tier 2
    │   ├── Tier 2: Brandon via /scillm (edge cases only)
    │   │   └── Labels accumulate toward training threshold
    │   ├── Training trigger: ~2000 labels → /create-gpt iterate
    │   ├── Auto-fix: regenerate failed controls
    │   └── Convergence: issue count must decrease
    │
    └── When GPT promoted (>90% agreement):
        └── Brandon only called for edge cases
        └── Monitor runs essentially for free
```

## Purpose

**Runs continuously for multiple days** until ALL QRAs and data integrity
reach A+ quality AND Margaret/Jennifer can consistently ask Brandon SPARTA
questions with 95%+ accurate results. Stops automatically when:
- 0 upstream deficiencies across all 5 dimensions
- Brandon says ACCEPTABLE with 0 FAIL and 0 WARN on QRA impact
- Persona test: 95%+ A+ accuracy (Margaret/Jennifer → Brandon → verify vs spreadsheet)
- Or: human explicitly stops the monitor

### Persona-Driven Self-Improvement Loop

The key differentiator: **Margaret Chen and Jennifer Cheung ARE the test harness.**
They ask Brandon Bailey real F-36 LEO questions. When Brandon can't answer correctly,
the failure traces back to a bad QRA. That QRA is quarantined and regenerated.
The loop runs until 95% A+ accuracy.

```
Margaret/Jennifer ask F-36 question
  → Brandon answers using QRAs from ArangoDB
    → Answer verified against SPARTA spreadsheet ground truth
      → A+: correct, grounded, complete
      → F: wrong, hallucinated, or missing
        → Trace to source QRA keys
          → Quarantine bad QRAs (quarantined=true, grounding_override=FAIL)
            → Next checkpoint regenerates for affected controls
              → Retest. Loop until 95% A+.
```

## Quick Start

```bash
cd /home/graham/workspace/experiments/memory

# Start the continuous monitor (runs for days until A+)
python scripts/validation/monitor_sparta.py start \
    --run-id run-recovery-verify

# Custom intervals (checkpoint every 5K QRAs or 30 minutes)
python scripts/validation/monitor_sparta.py start \
    --run-id run-recovery-verify \
    --checkpoint-interval 5000 --time-interval 1800

# Force a checkpoint NOW (one-shot, no daemon)
python scripts/validation/monitor_sparta.py checkpoint \
    --run-id run-recovery-verify

# Check status
python scripts/validation/monitor_sparta.py status

# Show convergence history
python scripts/validation/monitor_sparta.py convergence

# Stop the monitor
python scripts/validation/monitor_sparta.py stop
```

## Commands

| Command | Description |
|---------|-------------|
| `start` | Start continuous monitor (foreground by default) |
| `checkpoint` | Force one checkpoint now (one-shot) |
| `persona-test` | Run persona test loop (Margaret/Jennifer → Brandon → verify → backfill) |
| `status` | Show monitor status, label count, GPT readiness |
| `convergence` | Show convergence history across checkpoints |
| `stop` | Gracefully stop the running monitor |

## Three-Tier Cascade

| Tier | Source | Cost | When Used |
|------|--------|------|-----------|
| **0** | Deterministic checks | Free | Always — every checkpoint |
| **1.5** | Trained GPT via /assistant | Free | After training + deployment |
| **2** | Brandon via /scillm (DeepSeek-V3) | ~$0.12/1K | Edge cases + label accumulation |

### Lifecycle

1. **Pre-GPT** (~0-2000 labels): Tier 0 + Tier 2 Brandon at every checkpoint
2. **Training** (2000+ labels): `/create-gpt iterate` auto-triggered
3. **Shadow** (GPT deployed, <90% agreement): Tier 1.5 runs alongside Tier 2, logs disagreements
4. **Production** (>90% agreement): Tier 1.5 handles bulk, Brandon only for low-confidence escalations

## Training Pipeline

```
Brandon labels (25 per dim per checkpoint)
    │
    ├── Accumulate in STATE_DIR/*/bootstrap_labels.jsonl
    │   (currently: 735 labels)
    │
    ├── At 2000 labels:
    │   ├── Export to pipeline-validator.jsonl
    │   └── /create-gpt iterate --task sparta-pipeline-validator
    │
    └── Deploy trained model:
        ├── ./run.sh register --task sparta-pipeline-validator \
        │     --model-path <path> --type gpt --threshold 0.85
        ├── Shadow mode: always escalates to Tier 2, logs both
        └── Promote when agreement > 90%
```

## Convergence Tracking

The monitor tracks quality metrics across checkpoints:

```
  CP    QRAs   Defic       Verdict   Labels    GPT  Agree
  ---   -----  -----       -------   ------    ---  -----
    1  75,724  5,169    ACCEPTABLE      735      N     0%
    2  85,000  4,800    ACCEPTABLE    1,035      N     0%
    3  90,000  4,200    ACCEPTABLE    1,335      N     0%
    4  95,000  3,900    ACCEPTABLE    1,635      N     0%
    5 100,000  3,500    ACCEPTABLE    1,935      N     0%
    6 105,000  3,200    ACCEPTABLE    2,235      Y    72%
    7 110,000  2,800    ACCEPTABLE    2,535      Y    85%
    8 120,000  2,400    ACCEPTABLE    2,835      Y    92%  ← promote
```

**Rules:**
- Issue count MUST decrease cycle over cycle
- 3 consecutive regressions → STALLED alert, manual intervention
- NEVER lower thresholds to game the curve

### Agent Behavior Rule (Non-Negotiable)

- The agent MUST NOT stop and wait for the human to ask for status or remember to check
- If a cycle fails, diagnose the failure, attempt auto-repair, and continue
- Only escalate to the human if genuinely blocked after exhausting /dogpile research

**Anti-pattern**: Reporting status and waiting for the human to ask "what next?" is UNACCEPTABLE. The agent must proactively fix issues and continue the monitoring loop.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MONITOR_SPARTA_STATE_DIR` | `/mnt/storage12tb/.../monitor-sparta` | State directory |
| `TEACHER_MODEL` | `deepseek-ai/DeepSeek-V3` | Brandon's LLM |
| Checkpoint interval | 10,000 QRAs | `--checkpoint-interval` |
| Poll interval | 60s | `--poll-interval` |
| Training threshold | 2,000 labels | Hardcoded in script |
| Shadow agreement target | 90% | Hardcoded in script |
| Brandon samples per checkpoint | 25 per dim | Hardcoded in script |
| Brandon impact samples | 50 | Hardcoded in script |

## State Files

```
/mnt/storage12tb/media/agents/shared/monitor-sparta/
├── state.json           # Current monitor state
├── convergence.jsonl    # One entry per checkpoint
├── monitor.pid          # PID file for stop command
├── task_state.json      # For /task-monitor integration
├── training.log         # /create-gpt output when triggered
└── checkpoint_N.json    # Validation report per checkpoint
```

## Integration

| Skill | How It's Used |
|-------|---------------|
| `/sparta-pipeline-validator` | Tier 0 + Tier 2 validation |
| `/assistant` | Tier 1.5 GPT inference + shadow mode |
| `/create-gpt` | Train Tier 1.5 GPT when threshold reached |
| `/scillm` | All Brandon LLM calls |
| `/task-monitor` | Progress reporting |
| `/memory` | Store convergence findings as lessons |

## Relationship to Other Skills

| Skill | Role |
|-------|------|
| `/sparta-review` | One-shot quality assessment (used ad-hoc by humans) |
| `/monitor-sparta` | **Continuous autonomous monitoring** (this skill) |
| `regenerate_failed.py` | Regeneration action triggered by this monitor |
| `backfill_parent_context.py` | Upstream fix triggered by this monitor |
