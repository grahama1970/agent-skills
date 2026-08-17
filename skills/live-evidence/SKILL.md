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
  - ask
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
  -> $ask code-question solver when the turn is code-related
  -> one source-bound evidence card
```

The default critical path is local. Graph Memory is the primary retrieval
boundary. Ripgrep is an exact-current-source verifier and fallback. Code-related
interviewer questions are routed through `$ask` only after bounded Memory/code
evidence has been gathered, and the Ask run directory is preserved as a source
receipt. Brave and Dogpile are manual lanes only and receive a derived query,
never the complete transcript.

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
4. `$ask tau-dag` for code-related interviewer questions, seeded only with the
   current question and top bounded Memory/code/ripgrep evidence.
5. Brave Search only from the manual search control.
6. Dogpile only from an explicit deep-research request.

## Provider boundary: two tiers, and why

`$tau` owns provider orchestration everywhere else in this repo, and its skill
contract states that a skill recommending direct SciLLM calls should be treated
as a contract bug. This skill is a human-authorized exception for one tier only,
recorded here rather than left implicit (operator, 2026-08-17).

| Tier | Transport | Cadence | Why |
| --- | --- | --- | --- |
| Stage 1 — readiness gate | direct SciLLM | ~8 calls per 43s of audio | disposable, stateless judgment |
| Stage 2 — answer | `$ask tau-dag` | ~1 call per question | run directory is the source receipt |

Measured on this machine, same readiness prompt, all producing the correct 5/5
gate verdicts:

| Path | Latency |
| --- | --- |
| `tau-dag` `claude-opus-5-high` | 56s |
| `tau-dag` `claude-opus-5-low` | 38s |
| `tau-dag` trivial "reply OK" prompt | 18s |
| direct SciLLM `claude-opus-5` default effort | 11.6s |
| direct SciLLM `claude-opus-5` `reasoning_effort: low` | 10.8s |

Tau adds roughly 27s to an 11s call. The trivial-prompt probe isolates the
cause: 18s with nothing to generate, so the floor is orchestration (DAG
compile, dispatch, run-dir creation, polling), not generation.

Reasoning effort is not the lever for this task: direct low vs default differs
by under a second. Note `claude-opus-5-low` is NOT a valid SciLLM model id;
the `-low` suffix is an Ask/Tau handler convention, and direct calls pass
`reasoning_effort` as a separate parameter.

Replaying the real 359-event capture through the readiness trigger fires 3-8
resolver calls per 43s of audio. At 10.8s per call that fits inside realtime;
at 38s per call nothing does.

SciLLM proxy note: the running container validates `SCILLM_MASTER_KEY`, which
has drifted from the `SCILLM_PROXY_KEY` exported in `~/.zshrc`. The stale key
returns 401 and trips the proxy abuse guard after 5 errors in 30s.

Stage 1 uses none of what Tau provides. It needs no goal-hash continuity, no
resume (a stale readiness verdict is discarded, not resumed), no per-call
receipt, and no attempt budget (a missed poll is superseded by the next one
seconds later). Paying 38s of compliance machinery for a verdict that is
worthless 3 seconds later makes the live loop impossible.

Stage 2 keeps `$ask tau-dag` precisely because the preserved Ask run directory
is the source receipt this contract requires, and once per question 38s is
acceptable.

Do not "simplify" stage 1 back onto `tau-dag`. That change is what makes the
skill unusable in a live interview, and the numbers above are the reason.

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
export LIVE_EVIDENCE_ASK_RUNNER=/path/to/skills/ask/run.sh  # explicit opt-in
export LIVE_EVIDENCE_ASK_HANDLER=gpt-5.5-high
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
