---
name: dum-dum
description: >
  Model integrity monitor. Detects LLM quality degradation via active probes
  (NIAH, SKILL.md extraction) and passive signals (hook denials, transcript
  corrections, duplicate reads). CUSUM drift detection on quality time series.
  D3 dashboard for visualization.
triggers:
  - "model integrity"
  - "dum-dum"
  - "is the model dumb"
  - "model quality check"
  - "probe model"
allowed-tools:
  - Bash
  - Read
  - Write
metadata:
  short-description: LLM quality degradation detector
  author: Graham
  version: 0.1.0
provides:
  - dum-dum
composes:
  - scillm
  - monitor-drift-sensors
  - mine-transcripts
  - benchmark-models
  - create-figure
taxonomy:
  - Detect
  - Model
---

# dum-dum

Model integrity monitor that answers: "Is the LLM actually performing well right
now, or has quality silently degraded?"

Combines **active probes** (inject known-answer challenges) with **passive
signals** (mine session artifacts for quality indicators) and **statistical drift
detection** (CUSUM on quality time series).

## Architecture

```
Active Probes (on demand)          Passive Signals (from session data)
  NIAH ladder (1K/4K/8K/16K)        Hook denials (PreToolUse blocks)
    + adversarial distractors        Transcript corrections (user "no")
  SKILL.md extraction test           Duplicate reads (re-reading same file)
  Instruction-following test         Tool call failures / retry loops
  [latency + token telemetry]        [watermark-based dedup]
         |                                    |
         v                                    v
    probes.jsonl                      signals.jsonl
    (per-probe scores,                (watermarks.json tracks
     latency_ms, tokens)               last-scanned line)
         |                                    |
         v                                    v
    Per-channel drift detection (rolling-baseline CUSUM + Page-Hinkley + EWMA)
      probe channel ──────────┐
      signals channel ────────┤
      [EWMA entropy channel] ─┘
         |
         v
    D3 dashboard (per-channel quality, drift alerts, latency, signal breakdown)
```

## Usage

### Run active probes against the current model

```bash
./run.sh probe --model claude-sonnet-4-6
./run.sh probe --model claude-sonnet-4-6 --dry-run   # fixture data, no LLM calls
```

Runs NIAH recall + SKILL.md extraction + instruction-following probes. Stores
results in `~/.embry/dum-dum/probes.jsonl`.

### Collect passive signals from session transcripts

```bash
./run.sh collect                      # scan latest session
./run.sh collect --all                # scan all sessions
./run.sh collect --dry-run            # use fixture data
```

Mines transcripts for: hook denials, user corrections ("no", "wrong", "stop"),
duplicate file reads, tool call errors. Stores in
`~/.embry/dum-dum/signals.jsonl`.

### Run drift detection on collected data

```bash
./run.sh drift                        # CUSUM on quality time series
./run.sh drift --dry-run              # fixture data
```

Feeds probe + signal data into monitor-drift-sensors CUSUM/Page-Hinkley. Alerts
when quality degrades beyond threshold.

### Export the dashboard

```bash
./run.sh dashboard                       # export D3 dashboard to ~/.embry/dum-dum/dashboard.html
./run.sh dashboard --export report.html  # export to custom path
```

### Quick status

```bash
./run.sh status                       # last probe results + drift state
./run.sh status --json                # machine-readable
```

## Probe Types

| Probe | What it tests | How |
|-------|--------------|-----|
| **NIAH** | Context recall at depth | Inject a unique token deep in context, ask model to retrieve it |
| **SKILL.md extraction** | Instruction following | Present a SKILL.md, ask model to extract specific fields |
| **Instruction-following** | Constraint adherence | Give numbered constraints, check all are met in output |

## Passive Signal Types

| Signal | Source | Indicates |
|--------|--------|-----------|
| `hook_denial` | PreToolUse hook logs | Model tried something it shouldn't |
| `user_correction` | Transcript "no"/"wrong"/"stop" | Model got it wrong |
| `duplicate_read` | Tool call log (Read same file 2x) | Model forgot what it read |
| `tool_error` | Tool call failures | Model called tools incorrectly |
| `retry_loop` | Same tool call repeated | Model stuck in a loop |

## Grading

Each probe session produces a composite score 0-100:

| Score | Grade | Meaning |
|-------|-------|---------|
| 90-100 | A | Model performing well |
| 70-89 | B | Minor degradation |
| 50-69 | C | Noticeable quality drop |
| 0-49 | F | Significant degradation |

## Output

Results stored in `~/.embry/dum-dum/`:

```
probes.jsonl      # active probe results (scores, latency_ms, tokens per probe)
signals.jsonl     # passive signal observations (watermark-deduped)
drift.jsonl       # per-channel drift detection results
watermarks.json   # high-water marks for transcript dedup
dashboard.html    # last exported D3 dashboard (per-channel charts)
```

## Research Foundation

- **Rank-uniformity** (arXiv:2506.06975v4) - measuring attention distribution
  uniformity as a proxy for model engagement quality
- **FPEdit** (arXiv:2508.02092v2) - faithful prompt editing for detecting when
  models deviate from instruction fidelity
- **Retrieval heads as monitors** (arXiv:2604.02650v1) - retrieval head attention
  scores track quality better than NIAH alone; NIAH gives "deceptive saturation"
- **Adversarial NIAH** (arXiv:2601.20276v1) - EMB-S benchmark with collision-tested
  hard negatives; benign NIAH saturates but models degrade under semantic interference
- **Multi-faceted NIAH** (arXiv:2601.02023v1) - separating literal extraction,
  logical inference, and hallucination risk across context depths
- **EWMA entropy drift** (arXiv:2601.00554v3) - EWMA control statistic on streaming
  KL divergence; reduces retraining triggers 1-2 orders of magnitude vs fixed schedules
- **CDSeer** (arXiv:2410.09190v2) - model-agnostic concept drift detection with
  57% precision improvement using 99% fewer labels
- **CDCT compliance** (arXiv:2512.17920v1) - universal U-curve in instruction
  compliance; RLHF helpfulness is dominant cause of constraint violations
- **Positional bias at depth** (arXiv:2508.07479v1) - lost-in-the-middle effect
  strongest at <50% context window; beyond that primacy weakens

## Common Mistakes

```bash
# WRONG: Run probes without specifying model
./run.sh probe
# -> defaults to whatever scillm routes to, may not be what you want

# RIGHT: Always specify the model you're testing
./run.sh probe --model claude-sonnet-4-6

# WRONG: Only use active probes
# -> Passive signals catch real-world degradation that probes miss

# RIGHT: Combine both
./run.sh probe --model claude-sonnet-4-6
./run.sh collect
./run.sh drift
```
