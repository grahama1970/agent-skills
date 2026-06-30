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

## Full Coverage Definition for SPARTA QRAs

`/monitor-sparta` must report SPARTA QRA coverage by semantic bucket, not as a
single LLM-call count. Full coverage means:

1. Canonical SPARTA QRAs exist for every in-scope/actionable SPARTA technique,
   tactic, and countermeasure.
2. Technique-context relationship QRAs exist for valid tactic→technique and
   technique→related-control prompts.
3. Technique-related control-to-control QRAs exist only for pairs that pass
   `/create-evidence-case` evidence-case adjudication inside technique `T`; raw related
   control pairs are diagnostic candidates, not coverage obligations.
4. Non-SPARTA native QRAs exist for configured source frameworks used by SPARTA
   analysis: ATT&CK, CWE, NIST, CAPEC, D3FEND, ESA, NVD, and related imported
   corpora.

Health reporting must distinguish:

- `raw_candidates`: diagnostic universe, never equivalent to missing QRAs
- `gated_runnable`: evidence-gated jobs that should be run
- `stored_qras`: schema-valid generated artifacts
- `deterministic_skips`: valid no-call or no-store outcomes such as
  `no_grounded_relationship`
- `failures`: transport/schema/runtime defects

A monitor status that reports only "remaining calls" is incomplete unless it
identifies which bucket those calls belong to and whether control-to-control jobs
were `/create-evidence-case` gated.


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
    │   ├── Repair plans: write review-required manifests for failed controls
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

## Sparta Explorer Coverage UX

`http://localhost:3002/#sparta-explorer/coverage` is the UX projection of this
skill. The page must not be a passive report. Each Coverage section is a lane
subagent under `/monitor-sparta`:

| Coverage section | Lane subagent | Safe automatic behavior | Human-gated behavior |
|------------------|---------------|--------------------------|----------------------|
| QRA Generation | `qra_generation` | observe backlog, write manifests, rerun audits, launch reviewed/runnable native + SPARTA v2 `/create-qras` backlog | launch or override blocked control-to-control comparison jobs without accepted `/create-evidence-case` responses |
| Prompt Health / Prompt Inventory | `prompt_health` | run `/best-practices-prompt`, classify prompt-unit failures, generate `/review-prompt` payloads | apply non-mechanical prompt rewrites or promote prompt changes |
| Monitor Health | `monitor_health` | run health scanners, publish heartbeat/state | change thresholds or suppress dimensions |
| UX Coverage | `ux_coverage` | scan data-qid/test-interaction coverage | edit React routes/components |
| Python Fallbacks | `python_fallbacks` | scan silent fallback patterns | remove or rewrite fallback behavior |
| Source/Text/QRA Coverage | `source_text_qra_coverage` | observe control/URL text and QRA gaps, write manifests | fetch URLs or generate QRAs |
| Source/Embedding Coverage | `source_embedding_coverage` | observe Arango/Qdrant coverage, write manifests | mutate Arango/Qdrant |

Trigger model:

- push-triggered: UI, CLI, Discord, Slack, and voice commands enqueue lane work
  immediately;
- scheduled: nightly or supervisor-managed runs catch drift when no human is
  present;
- browser: WebSocket/SSE pushes state to Sparta Explorer, with polling fallback.

Expensive health-check rule:

- Sparta Explorer may poll or subscribe continuously, but browser reads must
  return the last durable snapshot unless a cheap change signature says the
  SPARTA corpus/supervisor state changed.
- `run_all_checks()` and other full Arango health scans are allowed only for an
  explicit human/operator force refresh, a nightly/checkpoint run, or a detected
  change signature. They must not be launched by ordinary page refreshes.
- The Coverage API must expose whether a response is `change_gated`,
  `change_detected`, `force_requested`, or `snapshot_only` so agents can tell
  whether they are looking at a durable snapshot or an active audit.

Prompt Health lane rule:

1. Run the local prompt-health scanner on prompt units, not isolated user
   fragments or README files.
2. Apply `/best-practices-prompt` first.
3. Run `/review-prompt` for non-mechanical rewrites, low-confidence edits, or
   prompts that affect generation semantics.
4. Auto-apply only mechanical edits that pass the scanner and prompt canary.
5. Escalate any semantic rewrite, schema change, or production-promotion
   decision to the human with exact files, failure codes, and resume command.

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
              → Stage review-gated QRA repair candidates
            → Approved apply regenerates affected controls
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

## Data Integrity (ArangoDB Only)

`/monitor-sparta` is ArangoDB-first. Do not use DuckDB in this workflow.

Health command coverage (`monitor-sparta health`):
1. Description audit
2. Upstream version
3. Source control parity (missing controls)
4. Control description coverage (missing/empty descriptions)
5. Relationship coverage
6. Taxonomy backfill coverage
7. Embedding gaps
8. Corpus completeness
9. Description preservation
10. Requirement quality
11. Formalizability coverage
12. QRA evidence coverage (missing/empty evidence_case + version)
13. QRA reasoning coverage
14. Crosswalk edge coverage
15. Crosswalk-chain schema discipline

Read-only default:

- `monitor-sparta` must not mutate SPARTA corpus data by default.
- `monitor-sparta health --fix` is blocked unless
  `SPARTA_MONITOR_MUTATION_ENABLED=1` is explicitly set for an approved,
  rollback-backed apply.
- Regeneration requests from checkpoint/persona paths must write
  review-required manifests by default, not upsert controls, synthesize
  descriptions, create relationships, or start Stage 12.
- Missing source text is not a QRA eligibility problem to pad around. Stub text
  such as "requires QRA generation" must be treated as missing/unsupported
  evidence until authoritative text is supplied.

Former automatic remediation lanes are now review-gated:

- Backfill missing source controls into `sparta_controls`
- Backfill missing/empty control descriptions
- Backfill missing mind taxonomy tags
- Backfill embedding gaps
- Backfill QRA `evidence_case` fields (spans/glossary/version)
- Backfill missing/invalid QRA reasoning

Each mutating lane requires approved patch artifacts and rollback manifests
before `SPARTA_MONITOR_MUTATION_ENABLED=1` may be used.

## Shared Maintainer Architecture

`/monitor-sparta` follows the same reporter/fixer/reviewer split used by
`/monitor-skill-health`:

1. Monitor lanes observe live state and write normalized findings, manifests, or
   tickets.
2. Tau-backed maintainer lanes lease one work item at a time.
3. A bounded repair subagent changes only the leased target.
4. A separate verifier/reviewer attaches deterministic proof.
5. Tickets or manifests close only after proof is attached and reconciled.

The monitor must not treat a report, WebGPT review, or CI green status as
closure proof. Mutating SPARTA repairs remain review-gated and rollback-backed.
