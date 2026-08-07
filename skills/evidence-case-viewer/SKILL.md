---
name: evidence-case-viewer
description: >
  Live evidence case pipeline viewer with NVIS sentence markup
  and agent chat well. Shows gates firing, entity grounding,
  QRA evidence, and verdicts in real-time. Chat well connects
  to /subagent-service for human-agent course correction.
triggers:
  - evidence case viewer
  - show evidence pipeline
  - view evidence case
  - launch evidence viewer
provides:
  - evidence-visualization
  - pipeline-monitoring
  - human-agent-collaboration
composes:
  - create-evidence-case
  - scillm
  - extract-entities
  - memory
disciplines:
  - compliance-security
  - ui-design-engineering
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Evidence Case Viewer

KDE/QML app (EmbryStyle) that shows the evidence case pipeline running live,
with an agent chat well for real-time human course correction.

## Usage

```bash
# Open viewer (tail mode — watches for pipeline events)
./run.sh

# Open viewer and evaluate a question immediately
./run.sh -q "How does SV-AC-2 protect avionics bus from spoofing?"

# Connect to a specific subagent container
./run.sh --subagent-url http://localhost:8621

# Headless: run pipeline, write NDJSON events only
./run.sh --emit-only "How does X23-MUSTARD protect avionics?"
```

## Architecture

```
events.py          NDJSON event emitter (pipeline wrapper)
    ↓ writes
/tmp/evidence-case-events.jsonl
    ↑ tails
bridge.py          PySide6 QObject (signals + properties + chat client)
    ↓ binds                    ↕ SSE stream
qml/EvidenceCaseViewer.qml    /subagent-service :8620
    [Pipeline Panels]          POST /chat/stream
    [Agent Chat Well]          GET /health
```

## Panels

- **Sentence Markup** — NVIS color-coded entity chips (RED/AMBER/YELLOW/GREEN)
- **Pipeline Gates** — gates firing in sequence with pass/fail and reasons
- **Evidence QRAs** — top QRA matches from /memory recall
- **Verdict** — final verdict badge with grade and reason
- **Agent Chat Well** — talk to the evidence case agent via /subagent-service

## Chat Well

The chat well connects to a `/subagent-service` container (default `localhost:8620`).
The agent receives full pipeline context (current question, entity markup, gate
statuses, QRA results, verdict) with each message, so it can reason about the
evidence case being built.

Example interactions:
- "Reject X23-MUSTARD — it's fabricated"
- "Why did step_2_recall pass? The QRAs don't match the question."
- "Override the verdict to not_satisfied"
- "What's the closest real control to X23-MUSTARD?"

Start a subagent before launching the viewer:
```bash
/subagent-service run.sh start --port 8620
```

## NVIS Colors (MIL-STD-3009)

| Color | Hex | Meaning |
|-------|-----|---------|
| RED | #e74c3c | Fabricated entity — not in corpus |
| AMBER | #e67e22 | Fuzzy match / misspelling |
| YELLOW | #f39c12 | Not found anywhere |
| GREEN | #2ecc71 | Confirmed entity |
