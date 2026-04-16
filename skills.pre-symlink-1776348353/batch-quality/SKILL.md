---
name: batch-quality
description: >
  Pre-flight validation and quality gates for batch LLM operations.
  ACTUALLY tests samples through LLM before burning tokens.
  Uses SPARTA contracts for DuckDB validation queries.
  Integrates with task-monitor for enforced quality gates.
triggers:
  - batch-quality
  - preflight
  - validate batch
  - check quality
  - before running batch

provides:
  - batch-quality
composes: [task-monitor]
---

# Batch Quality Skill

Prevent wasted LLM calls by validating quality BEFORE running full batch operations.

## What This Skill Actually Does

Unlike simple file-existence checks, this skill:

1. **Actually runs LLM on N samples** using scillm
2. **Validates JSON response structure** (excerpts, source_quality, etc.)
3. **Uses SPARTA contracts** for DuckDB validation queries
4. **Integrates with task-monitor** for enforced quality gates

## Quick Start

```bash
cd .pi/skills/batch-quality

# Preflight: Test 3 samples through actual LLM
uv run python cli.py preflight \
    --stage 05 \
    --run-id run-recovery-verify \
    --samples 3

# If preflight passes, run your batch
# ...batch operation...

# Validate: Check DuckDB against contract
uv run python cli.py validate \
    --stage 05 \
    --run-id run-recovery-verify \
    --task-name "sparta-stage-05"
```

## Commands

### preflight

Test N samples through actual LLM before running full batch.

```bash
uv run python cli.py preflight \
    --stage <stage-name> \
    --run-id <sparta-run-id> \
    --samples 3 \
    --prompt <optional-prompt-file>
```

**What it actually does:**
1. Loads SPARTA contract for the stage (if exists)
2. Checks environment variables (CHUTES_API_KEY, CHUTES_TEXT_MODEL)
3. Connects to DuckDB for the run
4. Samples N items from the input queue
5. **Runs each sample through scillm** (actual LLM call)
6. Validates JSON response structure
7. Requires 50%+ samples to pass

**Exit codes:**
- 0: PASSED - safe to proceed
- 1: FAILED - fix issues first

### validate

Validate batch output using SPARTA contracts.

```bash
uv run python cli.py validate \
    --stage <stage-name> \
    --run-id <sparta-run-id> \
    --task-name <task-monitor-name>
```

**What it actually does:**
1. Loads SPARTA contract (e.g., `05_extract_knowledge.json`)
2. Runs all `validation_queries` from contract against DuckDB
3. Checks each query result against `expected_min`
4. Notifies task-monitor of pass/fail

**Contract example (`05_extract_knowledge.json`):**
```json
{
  "validation_queries": [
    {"name": "url_knowledge_count", "query": "SELECT COUNT(*) FROM url_knowledge", "expected_min": 10},
    {"name": "urls_processed", "query": "SELECT COUNT(*) FROM url_extraction_log WHERE ok = true", "expected_min": 5}
  ]
}
```

### status

Check current preflight status (JSON output).

```bash
uv run python cli.py status
```

### clear

Clear preflight state (requires new preflight).

```bash
uv run python cli.py clear
```

## SPARTA Pipeline Integration

```bash
# 1. Register task with validation requirement
uv run python .pi/skills/task-monitor/monitor.py register \
    --name "sparta-stage-05" \
    --require-validation

# 2. Run preflight (ACTUALLY tests LLM)
uv run python .pi/skills/batch-quality/cli.py preflight \
    --stage 05 \
    --run-id run-recovery-verify \
    --samples 3

# 3. Run batch (only if preflight passed)
uv run python -m sparta.pipeline_duckdb.05_extract_knowledge \
    --run-id run-recovery-verify

# 4. Validate using contract queries
uv run python .pi/skills/batch-quality/cli.py validate \
    --stage 05 \
    --run-id run-recovery-verify \
    --task-name "sparta-stage-05"
```

## Configuration

**Environment variables:**
- `SPARTA_ROOT`: Path to SPARTA project (default: `/home/graham/workspace/experiments/sparta`)
- `CHUTES_API_KEY`: API key for LLM calls
- `CHUTES_API_BASE`: API base URL (default: `https://llm.chutes.ai/v1`)
- `CHUTES_TEXT_MODEL`: Model ID for text extraction

**Contract location:**
`$SPARTA_ROOT/tools/pipeline_gates/fixtures/D3-FEV/contracts/`

## Dependencies

- `typer` - CLI framework
- `duckdb` - Database queries
- `scillm` - LLM batch processing (for actual sample testing)

## Mandatory In-Flight Quality Gates (NON-NEGOTIABLE)

For long-running batch operations (especially QRA generation, extraction, etc.), preflight alone is insufficient. **You MUST run quality gates during execution, not just before.**

### The Pause-Assess-Diagnose-Tweak-Resume Loop

After every N batch checkpoints (e.g., every 5 KNN batches / ~1000 QRAs):

1. **PAUSE** — SIGSTOP the generation process
2. **SNAPSHOT** — Copy DuckDB for offline analysis, SIGCONT immediately
3. **SAMPLE** — Stratified random sample (high/mid/low grounding strata)
4. **ASSESS** — Check each sample: entity grounding, answer quality, reasoning
5. **DIAGNOSE** — Trend analysis: is grounding declining? Entity fails rising?
6. **TWEAK** — If degrading: adjust prompt, filter thresholds, relationship scores
7. **RESUME** — Only if quality meets thresholds
8. **STOP + NOTIFY** — If quality is below floor, halt and notify human

**This is not optional.** A batch that runs to 100k QRAs without quality gates will produce garbage that takes longer to clean than to regenerate correctly.

### QRA Quality Gate Script

```bash
# Continuous watchdog (runs alongside QRA generation)
python $SPARTA_ROOT/scripts/qra_quality_gate.py watch \
    --run-id run-recovery-verify \
    --batch-interval 5 \
    --samples 10

# One-shot assessment
python $SPARTA_ROOT/scripts/qra_quality_gate.py assess \
    --run-id run-recovery-verify \
    --samples 20

# View trend across checkpoints
python $SPARTA_ROOT/scripts/qra_quality_gate.py trend \
    --run-id run-recovery-verify
```

### Quality Thresholds

| Metric | Warning | Stop |
|--------|---------|------|
| Avg Grounding | < 0.65 | < 0.55 |
| Entity Fail % | > 5% | > 10% |
| Sample Fail Rate | > 15% | > 30% |
| Grounding Decline (per checkpoint) | > 0.05 | > 0.10 |

### Why This Matters

The QRA grounding score drifted from 0.74 to 0.62 over hours without intervention because the watchdog was passive. A proper quality gate would have caught the decline at 0.70 → 0.65 and diagnosed it (KNN exhausting easy relationships, prompt drift, etc.) instead of letting it slide to 0.62.

## Key Principle

**Preflight is cheap. Failed batches are expensive.**

Testing 3 samples costs ~$0.01 and takes 30 seconds.
Running 1000 items with a broken prompt costs ~$3 and takes hours.

**In-flight gates are cheaper than regenerating.** Pausing for 10 seconds every 1000 QRAs to verify quality costs nothing. Running 100k QRAs blind and discovering half are unusable costs everything.
