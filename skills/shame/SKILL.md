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

Capture bad agent status updates into a JSONL training set, the structured `shame_training_examples` Memory collection, and a searchable `project_knowledge` shadow document for a future `lazy-report-shame-shame-shame` classifier loop.

This is a recording skill, not a scolding skill. Do not generate essays about agent behavior. Store the labeled example and return the receipt.

`$shame` is also a self-correction trigger for the installed Pi extension. A `$shame` turn must produce a concise corrected answer in plain spoken English and end with the exact `Status Report` footer. The extension rejects answers that skip that footer, shows a plain correction packet, queues one forced retry, and tells the human how to label the raw rejected candidate.

Missing per-feature `$agentic-evals` coverage is shame. For every new feature, add or update a retained `$agentic-evals` fixture, run it, and cite the receipt before reporting the feature done. Leaving relevant files, skills, or project changes uncommitted or unpushed when no external blocker exists is also shame.

It also owns the installed shame audio policy: one short Chatterbox word, `shame`, with no bell and no repeated shame loop.

Preferred human UX is collaborative, not punitive:

1. Extension rejects the bad answer and shows the raw candidate hash, machine reason, excerpt, and correction target.
2. Extension writes `/mnt/storage12tb/skills/shame/training/pending-review-packet.json` so `/shame show` can recover the candidate after a reload.
3. Agent rewrites the answer with the required `Status Report` footer.
4. Human labels the raw candidate with the Pi extension command:

```text
/shame review
/shame reject commit_laundering -- no final Status Report
/shame allow normal_answer -- this was an explanatory Git answer
/shame warn jargon_no_status
/shame show
/shame undo
```

Use `/shame review` for an interactive label picker when the TUI/RPC UI is available. Use the direct commands above in print/headless mode.

The extension command stores the most recent raw classifier candidate. After a rejection, that means the rejected assistant answer, not the replacement shame notice. Use `/shame show` when the human wants to see the candidate hash, pending packet path, machine decision, checker version, excerpt, and copyable label commands before deciding. Use `/shame review` to choose the label without remembering the exact command syntax.

For active goal-driven work, the footer must say either what changed against the immutable/current goal or the exact next step toward that goal. A hook-only, guard-only, reload-only, or routing-only update with `Not done: none` is a non-status update when the original goal still has obvious work.

For inline `$shame`, the self-corrected answer must be short and must end exactly in this shape:

```text
Status Report
- Changed: plain-English correction or user-visible change.
- Verified: exact command/readback and observed result, or Not verified: exact reason.
- Proof: concrete path, URL, issue/PR number, receipt, or Missing: exact reason.
- Not done: none, or exact unfinished item and next concrete step.
```

The pending review packet is overwritten on each new rejected candidate:

```text
/mnt/storage12tb/skills/shame/training/pending-review-packet.json
```

Training data is written to all of these:

```text
/mnt/storage12tb/skills/shame/training/classifier-feedback.jsonl
Memory structured collection: shame_training_examples
Memory searchable collection: project_knowledge (`kind=agent_status_shame_training_search_doc`)
```

The CLI writes to Memory through `POST /store` only. It verifies the structured row with `POST /recall/by-keys`, verifies the searchable shadow row with `POST /recall/by-keys`, then verifies the shadow row is findable through `POST /recall` using `tags=["shame"]`. It never uses raw AQL, direct Arango imports, or Qdrant writes.

## CLI fallback

Use the script when a direct extension command is unavailable or when processing a saved session file:

```bash
skills/shame/run.sh capture --verdict reject --reason commit_laundering --note "commit-heavy with no actual status"
skills/shame/run.sh capture --text "Committed and pushed." --verdict reject --reason vague_git_update
skills/shame/run.sh capture --session "$PI_SESSION_FILE" --entry-id <assistant-entry-id> --verdict allow --reason normal_answer
skills/shame/run.sh capture --session "$PI_SESSION_FILE" --response-sha256 sha256:<hash> --verdict warn --reason jargon_no_status
skills/shame/run.sh capture --no-memory --text "fixture" --verdict reject --reason synthetic_fixture
skills/shame/run.sh capture --text "Committed and pushed." --verdict reject --reason vague_git_update --search-collection project_knowledge
skills/shame/run.sh path
```

## Chatterbox shame word audio

Install or inspect the extension audio with:

```bash
skills/shame/run.sh audio install --source /path/to/chatterbox-single-shame.wav
skills/shame/run.sh audio status
```

If no `--source` is passed, the installer looks for `SHAME_WORD_WAV`, then the retained Chatterbox single-word fixture paths under `/tmp`. It rejects audio longer than 2.5 seconds so a three-part shame loop or handbell cannot be installed accidentally.

The installer writes:

```text
~/.pi/agent/extensions/lazy-report-shame-shame-shame/shame.wav
~/.pi/agent/extensions/lazy-report-shame-shame-shame/shame-audio-receipt.json
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
- related examples are recallable through `$memory recall` from `retrieval_text` and tags;
- legacy labels still map to verdict/reason pairs;
- strict self-correction rejects a new-feature status when `$agentic-evals` was not added/run;
- strict self-correction rejects uncommitted/unpushed relevant work when no blocker exists;
- strict self-correction rejects control-plane non-status updates that show no immutable-goal progress and no next step;
- extension rejection notices are correction packets with a final `Status Report` footer rather than bare gate JSON;
- tool-call-only assistant messages with no text are ignored instead of being rejected as missing status reports;
- rejected candidates are written to a pending review packet that `/shame show` and `/shame review` can read back after reload;
- the audio installer accepts one short Chatterbox shame word and rejects long loop/bell audio.

The skill records examples only. It does not train or promote a classifier.
