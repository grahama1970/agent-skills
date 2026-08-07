---
name: classifier-lab-subagent
description: >
  Validate subagent reliability by running 3 concurrent classifier training loops.
  Each subagent runs /classifier-lab (deterministic code) and reports via JSON stream.
  The subagent's only job: run the skill, fix crashes, write /test-lab tests. 90% code, 10% agent.
  HP adjustment between rounds uses /scillm Gemini structured JSON, not agent judgment.

triggers:
  - classifier lab subagent
  - test subagent reliability
  - concurrent classifier training
  - subagent experiment
  - validate subagent architecture

allowed-tools: [Bash, Read, Write, Glob, Grep]

metadata:
  short-description: "3-concurrent subagent classifier training experiment"
  author: "Graham + Horus"
  version: "1.0.0"

provides:
  - subagent-reliability-validation
  - concurrent-training-orchestration

composes:
  - classifier-lab
  - scillm
  - scillm
  - test-lab

taxonomy:
  - agents
  - orchestration
  - reliability
  - classifier
disciplines:
  - ml-training
  - agentic-orchestration
  - evaluation-quality
---

# /classifier-lab-subagent

Validate whether subagents can reliably run long-running deterministic tasks.

## The Experiment

3 subagents run concurrently, each training a different text classifier model on the
same HuggingFace dataset (`ag_news`). Each subagent runs `/classifier-lab`'s existing
self-improvement loop. The orchestrator watches JSON streams, enforces timeouts, and
collects results.

**The point:** Determine if subagents can reliably perform long-running tasks when
90% of the intelligence is in the code and the subagent is just a process runner.

## Architecture

```
Project agent (interactive session)
    │
    ├── Decides: dataset, 3 models, initial HPs, gate threshold
    ├── Writes: config YAMLs for each model
    ├── Tests: preflight sanity (1 epoch each)
    │
    └── orchestrator.py (asyncio)
         ├── Subagent 1: distilbert-base-uncased
         ├── Subagent 2: bert-tiny
         └── Subagent 3: all-MiniLM-L6-v2
              │
              Each subagent:
              1. Runs classifier-lab/run.sh with config
              2. Script streams JSON to stdout
              3. If crash → debug, write /test-lab test, retry
              4. If blocked → report to orchestrator
              5. Between rounds: /scillm Gemini for structured HP suggestions
```

## What the Subagent Gets

```
Run this command:
  classifier-lab/run.sh e2e --task "ag_news" --dataset ag_news --modality text \
    --backbones {model} --gate-f1 0.95 --max-rounds 5

The script streams JSON progress. Let it run.

If it crashes: read the error, fix the obvious issue, write a /test-lab test, rerun.
If you can't fix it after 3 attempts: report "blocked" with the error.
Do not modify training logic. Do not change the self-improvement loop.
Do not add features. Just run it and report.
```

## What the Orchestrator Does

- Spawns 3 subagents via /subagent-service
- Reads JSON streams from each
- Heartbeat: no output for 120s → kill
- Wall-clock: 30min max per subagent
- Collects final metrics from all 3
- Reports: which succeeded, which failed, which blocked
- Computes subagent reliability rate

## HP Adjustment via /scillm (not agent judgment)

Between rounds, the self-improvement loop calls /scillm Gemini with structured JSON:

```json
POST http://localhost:4001/v1/chat/completions
{
  "model": "text",
  "messages": [{"role": "user", "content": "...round history..."}],
  "response_format": {"type": "json_object"}
}
```

Returns:
```json
{
  "learning_rate": 3e-5,
  "batch_size": 16,
  "epochs": 5,
  "dropout": 0.2,
  "reasoning": "Overfitting after epoch 3, reduce LR and increase dropout"
}
```

The code applies this directly. No agent interpretation needed.

## Usage

```bash
# Run the full experiment (3 concurrent subagents)
./run.sh experiment

# Preflight only (test each model for 1 epoch)
./run.sh preflight

# Single model test (no subagent, local)
./run.sh single --model distilbert-base-uncased

# Check results
./run.sh results
```

## Success Criteria

The experiment succeeds if:
1. All 3 subagents complete (not blocked/crashed)
2. At least 2/3 reach the accuracy gate (95%)
3. JSON streams were continuous (no heartbeat timeouts)
4. Total wall-clock time < 90 minutes

This tells us: subagents CAN reliably run deterministic code with monitoring.
If it fails: subagents can't even babysit a script, and we know the ceiling.
