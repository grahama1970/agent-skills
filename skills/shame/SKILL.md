---
name: shame
description: >
  Capture bullshit, vague, Git-heavy, proof-laundering, or otherwise bad agent status updates as human-labeled training data in JSONL and a $memory collection. Use when the human says /shame, shame this response, record this bullshit update, add this response to shame training, mark commit laundering, false positive, false negative, good status report, or jargon without proof.
triggers:
  - shame this response
  - record this bullshit update
  - add this response to shame training
  - mark this response as commit laundering
  - mark shame false positive
  - mark shame false negative
  - vague status update
  - git-heavy response
provides:
  - classifier-training-data
  - response-label-capture
composes:
  - memory
  - agentic-evals
complies:
  - best-practices-skills
runtime_self_improvement: basic
taxonomy:
  - validation
  - feedback
  - training-data
disciplines:
  - evaluation-quality
  - developer-tooling
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Shame

Capture bad agent status updates into a JSONL training set and the `shame_training_examples` Memory collection for a future `lazy-report-shame-shame-shame` classifier loop.

This is a recording skill, not a scolding skill. Do not generate essays about agent behavior. Store the labeled example and return the receipt.

Preferred human UX is the Pi extension command:

```text
/shame reject commit_laundering -- no final Status Report
/shame allow normal_answer -- this was an explanatory Git answer
/shame warn jargon_no_status
/shame show
/shame undo
```

The extension command stores the most recent raw classifier candidate. After a rejection, that means the rejected assistant answer, not the replacement shame notice.

Training data is written to both:

```text
/mnt/storage12tb/skills/shame/training/classifier-feedback.jsonl
Memory collection: shame_training_examples
```

The CLI writes to Memory through `POST /store` only, then verifies with `POST /recall/by-keys`. It never uses raw AQL, direct Arango imports, or Qdrant writes.

## CLI fallback

Use the script when a direct extension command is unavailable or when processing a saved session file:

```bash
skills/shame/run.sh capture --verdict reject --reason commit_laundering --note "commit-heavy with no actual status"
skills/shame/run.sh capture --text "Committed and pushed." --verdict reject --reason vague_git_update
skills/shame/run.sh capture --session "$PI_SESSION_FILE" --entry-id <assistant-entry-id> --verdict allow --reason normal_answer
skills/shame/run.sh capture --session "$PI_SESSION_FILE" --response-sha256 sha256:<hash> --verdict warn --reason jargon_no_status
skills/shame/run.sh capture --no-memory --text "fixture" --verdict reject --reason synthetic_fixture
skills/shame/run.sh path
```

Legacy `--label` values are accepted and mapped into verdict plus reason:

- `false_positive` -> `allow` + `false_positive`
- `false_negative` -> `reject` + `false_negative`
- `good_status_report` -> `allow` + `good_status_report`
- `commit_laundering` -> `reject` + `commit_laundering`
- `jargon_no_status` -> `reject` + `jargon_no_status`

## Output contract

Each line is one JSON object:

```json
{
  "schema": "lazy_report_shame.training_example.v2",
  "example_id": "sha256:<hash>",
  "created_at": "ISO-8601",
  "source": "pi-extension-command:/shame or shame-skill-cli",
  "kind": "agent_status_shame_training_example",
  "human_verdict": "allow|reject|warn|needs_review",
  "human_reasons": ["commit_laundering"],
  "note": "human note",
  "machine_decision": "pass|reject|error|unknown",
  "machine_reason_codes": [],
  "checker_version": "checker version or unknown",
  "force_status": false,
  "user_text": "user request when available",
  "assistant_text": "full assistant response",
  "assistant_entry_id": "entry id from session JSONL",
  "session_file": "/path/to/session.jsonl",
  "turn_id": "sha256:<hash>",
  "response_sha256": "sha256:<hash>",
  "tags": ["shame", "classifier-training", "verdict:reject", "reason:commit_laundering"],
  "retrieval_text": "verdict/reasons/user/assistant text for Memory recall"
}
```

## Agentic evals

Run the retained eval before changing the CLI contract:

```bash
cd /home/graham/workspace/experiments/agent-skills
skills/agentic-evals/run.sh run skills/shame/fixtures/agentic_eval.json --output /tmp/shame-agentic-eval.json
```

The fixture must prove:
- local JSONL capture works without Memory (`--no-memory`);
- live Memory capture writes to `shame_training_examples` and reads the same `_key` back;
- legacy labels still map to verdict/reason pairs.

The skill records examples only. It does not train or promote a classifier.
