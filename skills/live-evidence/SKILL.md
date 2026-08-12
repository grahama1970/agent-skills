---
name: live-evidence
description: >
  Local-first, always-on interview and meeting copilot that transcribes speech with
  RealtimeSTT/faster-whisper and surfaces source-bound evidence from Graph Memory,
  indexed code, and current repositories. Use when the user says "live interview
  evidence", "listen during my interview", "surface repo proof while I talk",
  "meeting copilot", or "find supporting code while someone is speaking".
triggers:
  - live interview evidence
  - listen during my interview
  - meeting evidence copilot
  - surface repo proof while I talk
  - find supporting code during a meeting
  - realtime transcription with memory
  - interview talking points from my repos
provides:
  - live-transcription
  - live-evidence-retrieval
  - source-bound-talking-points
  - interview-copilot-ui
composes:
  - agentic-evals
  - memory
  - ingest-code
  - brave-search
  - dogpile
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-react
  - best-practices-security
runtime_self_improvement: basic
taxonomy:
  - retrieval
  - human-in-the-loop
  - observability
  - precision
  - privacy
disciplines:
  - human-collaboration
  - research-retrieval
  - ui-design-engineering
  - memory-knowledge
---

# Live Evidence

Live Evidence lets the human stay in the conversation. It listens locally,
assembles stable speaker turns, and retrieves compact evidence cards instead of
generating a second conversation to read.

## Operating contract

```text
consented audio
  -> RealtimeSTT/faster-whisper
  -> stabilized/final speaker turns
  -> bounded trigger decision
  -> Memory/GMO recall + code navigation
  -> current-checkout ripgrep verification
  -> one source-bound evidence card
```

The default critical path is local. Graph Memory is the primary retrieval
boundary. Ripgrep is an exact-current-source verifier and fallback. Brave and
Dogpile are manual lanes only and receive a derived query, never the complete
transcript.

## Start

```bash
./run.sh setup
./run.sh ui-build
./run.sh serve --open-browser
```

In another terminal, after obtaining any required recording consent:

```bash
# Default microphone
./run.sh listen --mode microphone --consent-confirmed

# Meeting/system audio from a PipeWire source
./run.sh listen --mode pipewire \
  --pipewire-source '<source-name>' \
  --speaker interviewer \
  --consent-confirmed

# Browser/video audio from a PipeWire output sink
./run.sh listen --mode pipewire \
  --pipewire-source 'sink:<sink-node-name>' \
  --speaker interviewer \
  --consent-confirmed

# Two channels: default microphone + a PipeWire meeting source
./run.sh listen --mode dual \
  --pipewire-source '<source-name>' \
  --consent-confirmed
```

Use `pw-cli list-objects Node` or `pactl list short sources` to identify a
meeting/system source. Live Evidence stores transcript and evidence JSONL, not
raw audio, unless a future explicitly authorized extension changes that policy.

## Retrieval precedence

1. `memory /intent` and `/recall` using supported HTTP boundaries.
2. `memory/run.sh code-search` and `code-node` for indexed source with freshness.
3. `rg --fixed-strings` over explicitly configured repository roots.
4. Brave Search only from the manual search control.
5. Dogpile only from an explicit deep-research request.

Never import ArangoDB or Qdrant clients here. `/memory` owns ArangoDB, BM25,
Qdrant/Jina semantic retrieval, graph traversal, code-index lifecycle, and
freshness policy.

## Configuration

Copy `config/g2i.example.yaml` and set:

```bash
export LIVE_EVIDENCE_PROFILE=/absolute/path/to/profile.yaml
export LIVE_EVIDENCE_REPOS="$HOME/workspace/experiments/tau:$HOME/workspace/experiments/agent-skills:$HOME/workspace/experiments/sparta"
export MEMORY_SERVICE_URL=http://127.0.0.1:8601
```

Runner paths are autodetected from sibling skills and can be overridden with:

```bash
export LIVE_EVIDENCE_MEMORY_RUNNER=/path/to/skills/memory/run.sh
export LIVE_EVIDENCE_BRAVE_RUNNER=/path/to/skills/brave-search/run.sh
export LIVE_EVIDENCE_DOGPILE_RUNNER=/path/to/skills/dogpile/run.sh
```

## Proof

```bash
./sanity.sh
```

The sanity path starts a real local FastAPI server, submits a final interviewer
turn over HTTP, runs real ripgrep against a temporary repository, waits for a
source-bound card, validates the UI instrumentation contract, and writes a JSON
receipt. It does not claim live microphone, PipeWire, GPU inference, Graph
Memory, Brave, or Dogpile health unless those lanes were actually exercised.

## Boundaries

- Recording/transcription must comply with applicable law, employer policy, and
  meeting consent requirements.
- Evidence cards are prompts for the human, not permission to quote uncertain
  numbers or disclose private/ITAR material.
- A retrieved source is relevant evidence, not proof that a spoken claim is
  correct in the current context.
- Missing or stale evidence produces an explicit insufficient/degraded card;
  it never produces invented support.
