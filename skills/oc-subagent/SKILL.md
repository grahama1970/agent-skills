---
name: oc-subagent
description: >
  Use OpenCode serve child sessions as persistent, inspectable subagents. Use when
  proving or operating OpenCode subagents, child-session reuse, parent/child
  session maps, concurrent subagent fan-out, DAG-like task probes, SSE/event
  capture, or persistence across multiple turns without the full scillm
  transport/orchestrator overhead.
triggers:
  - oc-subagent
  - OpenCode subagent persistence
  - persistent OpenCode child session
  - child-session reuse
  - concurrent OpenCode subagents
  - prove subagents persist between tasks
  - OpenCode parent child session map
  - simple subagent DAG probe
provides:
  - opencode-subagent-control
  - child-session-persistence-proof
  - concurrent-subagent-probe
composes:
  - agentic-evals
taxonomy:
  - validation
  - orchestration
  - persistence
  - concurrency
disciplines:
  - agentic-orchestration
---

# oc-subagent

## Overview

Use this skill when a project agent needs a simple, direct OpenCode serve MVP for subagents: one parent session, stable logical subagent ids, child sessions for executors, blocking turn completion, and proof artifacts. Prefer this skill over hand-written OpenCode endpoint logic.

This skill intentionally stays below the full `$scillm` transport/orchestrator layer. Use `$scillm` transport when the work needs durable DAG state, retries, validation gates, amendment, or UI steering. Use `$oc-subagent` when the immediate question is whether OpenCode child sessions can run concurrently and preserve state across turns.

## Core Invariants

1. Create exactly one parent OpenCode session for the test run unless explicitly recovering from failure.
2. Create one child session per logical subagent using `parentID`.
3. Track a stable logical id such as `subagent_1` separately from the physical `child_session_id`.
4. Reuse the same child session for repeated turns to the same logical subagent.
5. Serialize turns sent to the same `subagent_run_id`.
6. Dispatch independent `subagent_run_id`s concurrently only when they use different child sessions.
7. Never advance a dependent task based only on prompt dispatch or partial SSE output.
8. Advance only after the turn returns a terminal HTTP response or equivalent terminal run status and the result validates.
9. Persist session maps, request/response artifacts, raw SSE, normalized JSONL events, heartbeats, task status, child listings, message listings, and final proof JSON.
10. A persistence prompt must not leak the prior result or its ingredients (the turn-2 prompt uses no digits).
11. Prove session memory with a negative control: the same turn-2 prompt sent to a fresh child session that never ran turn 1 must not produce the persisted answer.
12. Derive proof booleans from recorded timestamps and prompt scans, never hard-code them.

## Session Model

```text
project_agent_run_id
└── parent_session_id
    ├── child_session_id for subagent_1
    ├── child_session_id for subagent_2
    └── child_session_id for subagent_3
```

The project agent should reason in logical ids:

```text
subagent_1
subagent_2
subagent_3
```

The skill user maps those to physical OpenCode ids:

```json
{
  "run_id": "oc-subagent-persistence-001",
  "parent_session_id": "ses_parent",
  "subagents": {
    "subagent_1": {"child_session_id": "ses_child_a"},
    "subagent_2": {"child_session_id": "ses_child_b"},
    "subagent_3": {"child_session_id": "ses_child_c"}
  }
}
```

## Minimal MVP Probe

Use this task list to prove persistence and concurrency without `$scillm` transport overhead:

```text
1. Project agent computes 2 + 2 = 4.

2. subagent_1 turn 1:
   "Compute 3 * 6, then add the project-agent previous result, which is 4.
    Store the resulting number as last_result."
   Expected: 22

3. In parallel:
   subagent_2: "What is the capital of France?"
   Expected: Paris

   subagent_3: "In simple everyday examples, what color is most commonly associated with an apple?"
   Expected: red

4. Wait for both subagent_2 and subagent_3 to finish.

5. subagent_1 turn 2 (same child session, value not restated):
   "Add ten to your last_result from this same session."
   Expected: 32

6. Negative control (fresh child session, no turn 1):
   Send the turn-2 prompt to a brand-new child session that never ran turn 1.
   Expected: it must NOT produce 32 (it has no last_result to recall).
```

The turn-2 `subagent_1` prompt must not contain `22`, `18`, `4`, or `32`; it uses the word "ten" and contains no digits. If it does, the test proves prompt leakage, not session persistence. If the negative-control session produces `32` anyway, the `32` from the real run is not trustworthy evidence of session memory and the proof fails.

## Direct OpenCode Serve Calls

Prefer a local OpenCode serve instance:

```bash
export OPENCODE_BASE="${OPENCODE_BASE:-http://127.0.0.1:4096}"
export OC_AGENT="${OC_AGENT:-build}"
export OC_MODEL="${OC_MODEL:-}"
export RUN_ID="${RUN_ID:-oc-subagent-persistence-$(date +%Y%m%dT%H%M%S)}"
export ARTIFACT_DIR="${ARTIFACT_DIR:-./artifacts/$RUN_ID}"
mkdir -p "$ARTIFACT_DIR"
```

Use OpenCode agent profiles such as `build`, `plan`, `general`, or configured local profiles. Do not put chat model ids such as `opencode-go/kimi-k2.6` in the OpenCode `agent` field.

For this MVP proof, prefer a cheap model because the questions are simple and the proof target is child-session behavior. The live runner auto-selects a model unless `OC_MODEL` is set:

1. Local/free Ollama Qwen models, preferring `ollama/qwen3:14b` when present, then available local Qwen variants such as `ollama/qwen3:8b-nothink`, `ollama/qwen3:8b`, or `ollama/qwen2.5:14b`.
2. Cheap OpenCode Go fallback, currently `opencode-go/kimi-k2.6`.
3. Paid/high-confidence fallback, currently `openai/gpt-5.5`.

`OC_MODEL` is sent as the message `model` object; it is not the `agent` profile. Set `OC_MODEL_CANDIDATES` to a comma-separated list to override the auto-selection order. Set `OC_OLLAMA_MODEL` to prefer a specific local Ollama tag. The selected model and rejected candidates are written to `model-selection.json`.

Use different models for different work:

| Work type | Default model policy |
|-----------|----------------------|
| Cheap MVP persistence/concurrency proof | Local Ollama Qwen first, then OpenCode Go |
| Design critique, information architecture, broad synthesis | Moonshot AI Kimi K2.6 when configured, or OpenCode Go Kimi K2.6 |
| Coding, debugging, patch planning, hard correctness gates | GPT-5.5 high reasoning via OAuth/profile only when the task needs it |

Do not spend GPT-5.5 high reasoning on this MVP sanity unless cheaper candidates fail or the runner is diagnosing a real substrate bug.

## Live Sanity

Run the real MVP task list against a local OpenCode serve sidecar:

```bash
OPENCODE_BASE=http://127.0.0.1:4098 \
ARTIFACT_DIR=/tmp/oc-subagent/live-proof-$(date +%Y%m%dT%H%M%S) \
./sanity-live.sh
```

Expected success output:

```json
{
  "verdict": "PASS",
  "artifact_dir": "/tmp/oc-subagent/live-proof-..."
}
```

If OpenCode is unreachable, the script writes `proof.json` with `verdict: BLOCKED`. If a task answer, session id, concurrency, or prompt-leak invariant fails, it writes `verdict: FAIL`.

Minimal helpers:

```bash
oc_json_id() {
  jq -r '.id // .ID // .sessionID // .session_id // empty'
}

oc_message_body() {
  local text="$1"
  jq -n --arg agent "$OC_AGENT" --arg text "$text" \
    '{agent: $agent, parts: [{type: "text", text: $text}]}'
}

oc_create_parent() {
  local title="$1"
  curl -sS -X POST "$OPENCODE_BASE/session" \
    -H 'Content-Type: application/json' \
    -d "$(jq -n --arg title "$title" '{title: $title}')"
}

oc_create_child() {
  local parent_id="$1"
  local title="$2"
  curl -sS -X POST "$OPENCODE_BASE/session" \
    -H 'Content-Type: application/json' \
    -d "$(jq -n --arg parentID "$parent_id" --arg title "$title" '{parentID: $parentID, title: $title}')"
}

oc_send_turn_and_wait() {
  local child_session_id="$1"
  local text="$2"
  curl -sS -X POST "$OPENCODE_BASE/session/$child_session_id/message" \
    -H 'Content-Type: application/json' \
    -d "$(oc_message_body "$text")"
}
```

## Evidence Contract

Write artifacts under one run directory:

```text
artifacts/<run_id>/
  project-agent-state.json
  parent-session.json
  session-map.json
  events.sse
  subagent_1-session.json
  subagent_1-turn-1-request.txt
  subagent_1-turn-1-response.json
  subagent_1-turn-2-request.txt
  subagent_1-turn-2-response.json
  subagent_2-session.json
  subagent_2-concurrent-request.txt
  subagent_2-concurrent-response.json
  subagent_3-session.json
  subagent_3-concurrent-request.txt
  subagent_3-concurrent-response.json
  subagent_1_negative-session.json
  subagent_1_negative-request.txt
  subagent_1_negative-response.json
  children-after.json
  messages-subagent_1-after.json
  model-selection.json
  events.jsonl
  heartbeats.jsonl
  timeline.jsonl
  task-status.json
  proof.json
```

Final proof shape:

```json
{
  "verdict": "PASS",
  "run_id": "oc-subagent-persistence-001",
  "parent_session_id": "ses_parent",
  "model_selection": {
    "selected_model": "ollama/qwen3:8b-nothink",
    "artifact": "model-selection.json"
  },
  "project_agent_persistence": {
    "step_1_result": 4,
    "state_survived_unrelated_tasks": true
  },
  "sequential_subagent_persistence": {
    "subagent_run_id": "subagent_1",
    "child_session_id_turn_1": "ses_child_a",
    "child_session_id_turn_2": "ses_child_a",
    "same_child_session": true,
    "turn_1_answer": 22,
    "turn_2_answer": 32,
    "turn_2_prompt_did_not_leak_prior_value": true,
    "turn_2_waited_for_turn_1": true,
    "passed": true
  },
  "concurrent_subagents": {
    "subagent_2_child_session_id": "ses_child_b",
    "subagent_3_child_session_id": "ses_child_c",
    "subagent_2_answer": "Paris",
    "subagent_3_answer": "red",
    "both_dispatched_before_first_result_consumed": true,
    "passed": true
  },
  "negative_control": {
    "subagent_run_id": "subagent_1_negative",
    "child_session_id": "ses_child_neg",
    "prompt_is_turn_2_without_turn_1": true,
    "answer": null,
    "produced_32": false,
    "passed": true
  },
  "failure_reasons": [],
  "artifacts": {
    "model_selection": "model-selection.json",
    "session_map": "session-map.json",
    "events": "events.sse",
    "events_jsonl": "events.jsonl",
    "heartbeats": "heartbeats.jsonl",
    "timeline": "timeline.jsonl",
    "task_status": "task-status.json",
    "children_after": "children-after.json",
    "messages_subagent_1_after": "messages-subagent_1-after.json",
    "negative_control_session": "subagent_1_negative-session.json",
    "negative_control_response": "subagent_1_negative-response.json"
  }
}
```

## Observability Contract

The live runner follows the scillm transport convention: raw SSE is preserved for forensics, normalized JSONL is written for machines, and task state is snapshotted for operators.

```text
events.sse        raw OpenCode event stream
events.jsonl      normalized SSE rows keyed by session/subagent when known
timeline.jsonl    project-agent lifecycle rows such as run_started, task_started, task_completed
heartbeats.jsonl  periodic liveness rows for active DAG nodes/subagent calls
task-status.json  latest per-node state snapshot
```

Completion still gates on a terminal message response plus result validation. Heartbeats and streamed deltas prove liveness and diagnosability; they are not sufficient by themselves to advance a dependent DAG node.

## Failure Conditions

Fail the proof if any of these occur:

- `subagent_1` turn 2 uses a different child session without an explicit fork/recovery receipt.
- Turn 2 dispatches before turn 1 returned and validated.
- Two simultaneous turns are sent to the same child session.
- Concurrent distractor results are consumed before both independent calls were dispatched.
- The turn-2 `subagent_1` prompt includes `22`, `18`, `4`, or `32`.
- The negative-control session (turn-2 prompt, no turn 1) produces `32`, which would mean `32` is not proof of session memory.
- A measured invariant (`turn_2_prompt_did_not_leak_prior_value`, `turn_2_waited_for_turn_1`, `both_dispatched_before_first_result_consumed`) is false rather than asserted true.
- The proof is based only on natural-language claims rather than saved artifacts.
- A chat model id is used as the OpenCode `agent` field.
- `events.jsonl`, `heartbeats.jsonl`, `timeline.jsonl`, or `task-status.json` is missing from a live run.

## Output Summary

Return a concise final summary:

```text
VERDICT: PASS | FAIL

Project-agent state: PASS | FAIL
Sequential subagent persistence: PASS | FAIL
Concurrent subagents: PASS | FAIL

Final values:
project_agent_step_1 = 4
subagent_1_final = 32
subagent_2 = Paris
subagent_3 = red

Artifact directory: artifacts/<run_id>
```
