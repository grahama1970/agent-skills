---
name: a-detection
description: >
  Run the a-detection coding-assessment evidence workbench, train a Python code
  detector, inspect retained proof, or evaluate code-detection readiness. Use
  when the user asks for AI code detection, assessment evidence, or a-detection.
triggers:
  - AI code detection
  - coding assessment evidence
  - a-detection
provides:
  - coding-assessment-evidence
  - code-detection-research
composes:
  - setup-project
  - agentic-evals
complies:
  - best-practices-python
  - best-practices-skills
taxonomy:
  - validation
  - precision
  - evidence
disciplines:
  - ml-training
  - evaluation-quality
runtime_self_improvement: basic
---

# a-detection

Read `docs/PROJECT_KNOWLEDGE.md` relative to this skill first. README
explains the developer experience; this contract governs agent operation.

Use `./run.sh doctor`, `./run.sh serve`, `./run.sh analyze <source>`, and
`./sanity.sh`. `run.sh` uses this skill's own pyproject via uv, not an implicit
system Python. Consult `docs/EVALUATION.md` for full qualification, and
`docs/DATASET.md` before training.

## Boundaries

Consent precedes capture. Browser reports are untrusted observations. Never use
paste behavior, typing cadence, or a scalar score as proof of misconduct.
No model means abstain. Synthetic training never earns calibration authority.
Candidate code is parsed, never executed. No provider upload or global monitoring.
Heavy data/weights stay on configured external storage, not in this skill folder.

## Owning skill gates

`./run.sh native-setup` delegates to setup-project and `./run.sh native-evals
--release` delegates to agentic-evals through `AGENT_SKILLS_ROOT` (this
agent-skills checkout works: `export AGENT_SKILLS_ROOT=<repo root>`). A missing
native checkout is BLOCKED_EXTERNAL, not PASS. Do not implement a replacement
agentic runner, forge native receipts, disable the required client-contract gate,
or weaken fixtures to obtain READY.

Report separate facts: executed checks, assertion outcomes, core mechanisms,
browser proof, real-human efficacy, and release readiness. Retain source hashes
and failures. Real-human detection and native release evidence remain required.
