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
  - debugger
  - surf
  - tau
  - ops-google-calendar
  - analytics
  - create-figure
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
---

# Live Evidence

Live Evidence lets the human stay in the conversation. It listens locally,
assembles stable speaker turns, and retrieves compact evidence cards instead of
generating a second conversation to read.

## Capability map (receipt-backed, 31-case suite)

Every row below is guarded by at least one live agentic-eval case; the full
suite last ran READY with all cases passing twice.

| Capability | Mechanism |
| --- | --- |
| Live audio -> card | PipeWire -> Docker RealtimeSTT (CUDA, CPU fallback on OOM) -> stage-1 resolver -> retrieval -> revision-fenced card |
| Stage-1 readiness | local deterministic scanner/readiness gate; canonical question authors the card without direct provider access |
| Stage-2 fast answer | streaming solver into the published card: p50 0.9s / p95 2.2s to first content, receipt journaled per answer; `$ask tau-dag` is the escalation path |
| Requirement ledger (#1454) | blocking clarifications hold the solver at zero; exactly-once per revision; amendable |
| Session purposes (#1449) | frozen backend-enforced capability policies; digest bound to every artifact |
| Briefing packs | pre-call talking points stem-matched live against the transcript; surfaced openings cite their trigger events; refused in formal_assessment |
| Action lane (#1475) | resolver-proposed fact_check / remember_fact / open_artifact; human-approved, destination-readback receipts |
| Clause provenance (#1476) | clause -> source mapping with digests recomputed per call; mutated sources render invalidated |
| Rubric coverage (#1452/#1474) | model authors coverage over live transcripts; deterministic floor verifies every binding; no scores ever |
| Debugger lane (#1450) | read-only breakpoint proofs via the sibling debugger skill, independently validated, CAS-fenced cards |
| Review dossier (#1451) | evidence-linked post-interview claims with click-to-seek media |
| Rehearsal (#1453) | practice-only chatterbox voice loop with hash-bound receipts and echo redaction |
| Speaker turns (#1477) | deterministic turn ids + anonymous slots + journaled manual correction; diarization deliberately deferred |

## Briefing packs

Load a `live_evidence.briefing_pack.v1` before a call
(`POST /api/briefing/load`): each point carries opening-trigger groups
(word-start stem matching), the hook to say, the story behind it, and
optionally the question to ask. During the call every final transcript event
is matched zero-latency over a rolling window; a hit surfaces the point in
the HUD's Openings panel WITH the heard terms and the exact trigger events,
then cools down for two minutes. A recognition assist, never a script.
`fixtures/briefing_straive.json` is the shipped example pack.

## Client/employer/topic prep packs

For a researched interview, meeting, client, employer, or topic, build one
self-contained `live_evidence.prep_pack.v1` before the live run. The pack is
the durable boundary between deep research and the live copilot. It bundles:

- source context from `$brave-search`, `$dogpile`, selected docs, repos, and
  local briefs;
- the `live_evidence.briefing_pack.v1` to load into `/api/briefing/load`;
- expected question oracles with time/category anchors when available;
- reviewed answers, required skill chains, quality bars, publication gates, and
  fail-closed conditions;
- Memory export instructions for `/live-evidence/oracle-pack` and `/recall`;
- post-run grading instructions for missed questions, weak answers, and wrong
  skill-chain choices.

The normal front door is `$curate-client`. It owns the client KB curation and
live-evidence wiring. Its internal prep chain is:

```text
$curate-client client/employer/topic KB build
  -> $brave-search for current public discovery
  -> $dogpile for deeper multi-source research
  -> $ingest-website for durable selected docs when needed
  -> $ask for question/answer/skill-chain generation and review
  -> $memory for live retrieval by known or similar question
  -> $live-evidence loads the briefing pack and recalls the oracle graph
```

`fixtures/prep_pack_drivewealth.json` is the shipped DriveWealth example. Validate
the shape with `./run.sh eval-prep-pack`, then load it into a running HUD with:

```bash
./run.sh load-prep-pack \
  --pack fixtures/prep_pack_drivewealth.json \
  --backend-url http://127.0.0.1:8799
```

`load-prep-pack` loads the embedded briefing pack through `/api/briefing/load`
and verifies each question oracle's `memory_keys` through `/recall`. A retrieved
prep-pack or oracle answer is a prior for live ranking and answer shaping, not
publication authority; the live transcript revision, source provenance, and card
publication gates still decide visibility.

## Precomputed interview oracles

Before live testing a known interview scenario, every transcript should have a
finished oracle set: canonical questions, reviewed answers, required skill
chains, source references, and expected disposition by timecode. For
DriveWealth-style prep, the target frontier is 100-200 questions across
5-10 minute mock interviews. Known or similar question retrieval should help the
live loop choose the right skill chain and answer shape, but it must never make
the card bypass review.

For synthetic meeting demos, do not hand-author a simplified fallback transcript.
Use `$ask webgpt` or another approved browser-model authoring route with the full
frozen context bundle, then run `$best-practices-fake-meeting` in
`production-demo` mode before Chatterbox synthesis. The accepted transcript must
carry an authoring receipt, context-bundle hash, source question IDs, per-turn
`kind` labels, and `source_question_id` mappings on substantive sourced
questions. A structural `PASS` is not proof of company accuracy, meeting quality,
live STT, playback, or Live Evidence card quality; those require independent
content review plus live-path receipts.

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
./run.sh serve --port 8799 --open-browser
# If 8799 is already occupied, fail closed or explicitly scan upward:
./run.sh serve --port 8799 --auto-port --open-browser
```

`serve --auto-port` writes the selected URL to `local/server.json`; copy that
`backend_url` into `listen`, `replay`, or `status` when the server could not use
8799.

In another terminal, after obtaining any required recording consent:

```bash
# Default microphone
./run.sh listen --mode microphone \
  --backend-url http://127.0.0.1:8799 \
  --device cpu \
  --consent-confirmed

# Meeting/system audio from a PipeWire source
./run.sh listen --mode pipewire \
  --backend-url http://127.0.0.1:8799 \
  --pipewire-source '<source-name>' \
  --speaker interviewer \
  --device cpu \
  --consent-confirmed

# Browser/video audio from a PipeWire output sink
./run.sh listen --mode pipewire \
  --backend-url http://127.0.0.1:8799 \
  --pipewire-source 'sink:<sink-node-name>' \
  --speaker interviewer \
  --device cpu \
  --consent-confirmed

# Two channels: default microphone + a PipeWire meeting source
./run.sh listen --mode dual \
  --backend-url http://127.0.0.1:8799 \
  --pipewire-source '<source-name>' \
  --device cpu \
  --consent-confirmed
```

Use `pw-cli list-objects Node` or `pactl list short sources` to identify a
meeting/system source. Live Evidence stores transcript and evidence JSONL, not
raw audio, unless a future explicitly authorized extension changes that policy.

## Session purposes and capability policy (#1449)

A session is started FOR something, and that purpose is authority, not a UI
label. `POST /api/session/start` accepts `purpose`, `actor_role`, and an
optional explicit `policy`; the resolved capability set is frozen at start and
bound into a SHA-256 `policy_digest` that every card and journal record
carries. Changing purpose, role, or policy after activity begins allocates a
NEW session id -- a toggle can never silently widen a running session.

| purpose | default stance |
| --- | --- |
| `meeting` | evidence + decision capture; external search permitted (manual lanes) |
| `rehearsal` | coaching + voice permitted; session is machine-readably `practice_only` |
| `formal_assessment` | FAILS CLOSED: no candidate answers, no manual/automatic Ask, no external search, no debugger, no voice, no repository mutation |
| `interviewer_assist` | follow-up suggestions permitted; candidate answer generation disabled |
| `post_interview_review` | post-hoc only; `capture_audio` disabled, so the session can never reach LISTENING |

Enforcement lives in the backend choke points (coordinator gates, manual-route
403s), never only in hidden React controls; `eval-session-policy` proves the
fail-closed matrix over live HTTP, including UI-bypass calls. Consent remains a
separate, prior gate that policy supplements and never replaces.

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
contract states that a skill recommending Tau-owned provider calls should be treated
as a contract bug. This skill is a human-authorized exception for one tier only,
recorded here rather than left implicit (operator, 2026-08-17).

| Tier | Transport | Cadence | Why |
| --- | --- | --- | --- |
| Stage 1 — readiness gate | Tau-owned provider | ~8 calls per 43s of audio | disposable, stateless judgment |
| Stage 2 — answer | `$ask tau-dag` | ~1 call per question | run directory is the source receipt |

Measured on this machine, same readiness prompt, all producing the correct 5/5
gate verdicts:

| Path | Latency |
| --- | --- |
| `tau-dag` `Codex-opus-5-high` | 56s |
| `tau-dag` `Codex-opus-5-low` | 38s |
| `tau-dag` trivial "reply OK" prompt | 18s |
| Tau-owned provider `Codex-opus-5` default effort | 11.6s |
| Tau-owned provider `Codex-opus-5` `reasoning_effort: low` | 10.8s |

Tau adds roughly 27s to an 11s call. The trivial-prompt probe isolates the
cause: 18s with nothing to generate, so the floor is orchestration (DAG
compile, dispatch, run-dir creation, polling), not generation.

Reasoning effort is not the lever for this task: direct low vs default differs
by under a second. Note `Codex-opus-5-low` is a Tau/Ask handler convention;
the `-low` suffix is an Ask/Tau handler convention, and direct calls pass
provider effort stays behind Tau/Ask.

Replaying the real 359-event capture through the readiness trigger fires 3-8
resolver calls per 43s of audio. At 10.8s per call that fits inside realtime;
at 38s per call nothing does.

Provider boundary note: model/provider calls are owned by Tau. Live Evidence
must not fetch or export provider keys directly; local detection falls back to
deterministic scanners, and provider-backed solving routes through Ask/Tau receipts.

Stage 1 uses none of what Tau provides. It needs no goal-hash continuity, no
resume (a stale readiness verdict is discarded, not resumed), no per-call
receipt, and no attempt budget (a missed poll is superseded by the next one
seconds later). Paying 38s of compliance machinery for a verdict that is
worthless 3 seconds later makes the live loop impossible.

Stage 2 (#1473) has a fast path and an escalation path. The fast path is a
Tau/Ask-backed streaming path (claude-sonnet-5, medium effort) that publishes
the answer into the already-fenced card as it streams: measured live over 30
heterogeneous questions, p50 1.96s / p95 5.35s from canonical-question-ready
to first answer content, with a fast_solver_receipt (model, effort, latency
segments, response sha256) journaled per answer and blinded quality parity
gated against the `$ask` path. `$ask tau-dag` remains the escalation route
because its run directory is the source receipt this contract requires --
and after agent-skills#1472 a single call costs ~5s of orchestration plus
generation, not ~40s. A live-answer capability claim requires the fast path's
live receipts; the keyless ask fixture runner is a regression floor only.

Do not "simplify" stage 1 back onto `tau-dag`. That change is what makes the
skill unusable in a live interview, and the numbers above are the reason.

## Debugger composition (#1450)

Live Evidence composes the sibling `skills/debugger` through a bounded,
read-only proof lane (`src/live_evidence/debugger_lane.py`): a
`live_evidence.debug_request.v1` binds repository identity, question revision,
and the frozen session policy; capture runs through the debugger skill's
front door (`skills/debugger/run.sh break`, which owns the venv/env plumbing);
the proof becomes evidence only after
`skills/debugger/run.sh validate --expect-valid` passes AND the adapter's own
readback confirms a verified stop at a requested location. Dispatch success,
exit 0, or a producer-authored `proofValid` never satisfies the card gate.
Secret redaction is debugger-side and preserved end to end. `vscode_bridge`
mode reports a truthful BLOCKED state until the GUI capability is provisioned.

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
