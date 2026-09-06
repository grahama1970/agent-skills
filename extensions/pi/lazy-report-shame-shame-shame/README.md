# lazy-report-shame-shame-shame

Pi status/continuation enforcement, operator-armed task budgets, and accessible failure history. Human feedback remains a separate training dataset.

Start with `/shame status`, `/shame failures`, `/shame task status`, or `/shame review`. The status indicator distinguishes `ON`/`OFF`, configured mode, and the **last reported** task state. `/shame status` also compares the loaded entrypoint hash with its on-disk source; that comparison does not attest every imported dependency.

Ponytail supplies generation guidance; this harness owns execution limits. Architecture diagrams remain optional, predeclared deliverables—not new work automatically started at a stop.

## What it enforces

The extension is not a reminder. It is a rejection loop.

At terminal assistant `message_end` (`stopReason="stop"`, no tool calls or queued work), it:

1. extracts the assistant’s final text;
2. preserves all intermediate tool calls, including responses containing both progress text and tool calls, without spending reporting retries;
3. runs `status-json-check.mjs` as a deterministic checker;
4. validates the final `pi.agent_status.v1` JSON with pydantic instead of classifying prose;
5. rejects unresolved URL/digest `proof[]`, missing/empty/non-file local proof, failed known receipt schemas, and `verified[]` entries not backed by local proof text;
6. when `LAZY_REPORT_SHAME_CONTINUATION_GUARD_FILE` points at an active goal/ticket ledger, rejects a final `state=done` report while relevant `agent-work` tickets, acceptance gates, or explicit next steps remain open;
7. ignores trailing prose after valid status JSON because pydantic data is authoritative and the renderer discards model prose;
8. strips model-authored status JSON/prose from accepted output and renders the visible `Status Report` from the validated JSON;
9. replaces rejected output with `REJECTED_BY_SLOTH_COURT` plus a correction packet;
10. prepares at most one output-only `UNLAZY_FORCED_RETRY` correction per reporting episode, armed or unarmed, and dispatches it only at `agent_end`; correction turns cannot call tools or request another correction;
11. tells the human how to label the raw rejected candidate with `/shame reject|allow|warn <reason> -- <note>` after automatic repair is exhausted.

The default mode is `normal`; ordinary chat is not forced through the status contract. Use `LAZY_REPORT_SHAME_DEFAULT_MODE=strict` for project-agent panes that must status-report at every terminal stop, or `/shame normal|off|strict` to override a session. Leading `$unlazy`/`/unlazy`/`/skill:unlazy` invocations add one-turn enforcement. Leading `$shame`/`/shame`/`/skill:shame` invocations request self-correction. Mentioning these skills or the phrase `acceptance ledger` in an advisory question does not activate a gate. New human input clears stale correction and skill-read flags. Report corrections are output-only even without an armed task budget; they cannot launch checks or reopen accepted work. Read-only failure history remains available outside correction turns. The `/lazy-report-shame-shame-shame` command enables session-wide enforcement explicitly. A continuation ledger file also enables status enforcement for that session because the guard has machine-readable unfinished work to check.

Intermediate responses cannot erase pending tool calls or exhaust report repairs. Cancellation, provider errors, length limits, and shutdown do not restart the model. Host-queued work takes precedence over reporting repair. The final message is validated/rendered before display; `agent_end` owns follow-up dispatch, not message replacement. Pi drains follow-ups queued by `agent_end` inside the current prompt; `agent_settled` is too late for reliable print-mode continuation and is reserved for idle observation.

Repeated status text is not a duplicate event: legitimate polling continuations dispatch at each distinct stop, while replaying the same terminal event dispatches once. `skills/shame/fixtures/hardening_eval.json` retains this live case plus session ownership and evidence-resolution regressions.

Retained proof: `skills/shame/fixtures/stop_boundary_eval.json` covers lifecycle replay plus a live Pi model with real file reads, writes, and independent result readback. This is not proof that every project is semantically complete.

The real conversational seam is covered by `skills/shame/fixtures/conversation_guard_eval.json`: advisory mentions answer once without tools/rejections; a fault-injected report gets one live, tool-free correction. Strict mode and mutation enforcement are positive controls, not silently disabled.

## Operator-armed task budgets

Arm a bounded task with `/shame task start /absolute/contract.json`, or set
`SHAME_TASK_BUDGET=/absolute/contract.json` when launching Pi. `/shame task status`
shows the phase and receipt. `/shame-task` remains a compatibility alias. This is opt-in; an unarmed session retains existing behavior.

```json
{
  "schema": "pi.task_budget.v1",
  "mode": "task",
  "deliverable": "Update the requested widget",
  "allowed_paths": ["src/widget.ts"],
  "elapsed_ms": 1800000,
  "checks": [{
    "id": "widget-tests",
    "argv": ["npm", "test"],
    "inputs": ["src/widget.ts", "package.json"],
    "definition_files": ["package.json", "package-lock.json"],
    "timeout_ms": 60000,
    "kind": "check"
  }]
}
```

- Paths are project-relative; a trailing `/` explicitly permits a subtree. Built-in
  write/edit paths are canonicalized, including symlinks. Contract/check-definition
  files are frozen. Declare every relevant file dependency in `inputs`.
- Raw Bash and unapproved custom tools are blocked. The model uses `task_check`
  with an approved `id`; it cannot supply replacement commands or arguments.
  Approved argv commands are **trusted capabilities**, not OS-confined programs.
  This is task-policy enforcement, not a hostile-code sandbox; no sudo is involved.
- Checks wait for batched mutations. Once checking begins, further edits require
  a failed check. Passing checks with unchanged inputs return cached evidence;
  changed inputs or failures permit another run. Initial failure permits two repairs.
- `kind: "review"` has an explicit deadline and no automatic resubmission.
  `kind: "delivery"` is a required delivery readback. All listed checks are required.
- The elapsed deadline aborts the agent. Command deadlines/cancellation kill the
  approved POSIX process group; command output is bounded. Receipt reasons distinguish
  deadlines, cancellation, and check failures.
- All checks passing for their declared inputs makes `accepted` terminal: no more
  tools or edits. One missing/invalid report correction is output-only, does not
  reopen acceptance, and cannot rerun tests.
- For explanatory questions, arm `mode: "question"` with empty `allowed_paths` and
  `checks`. Only read/search tools are available and no status/quality gate is required.
  Later human questions after acceptance are likewise read-only. New execution
  requires a new operator-armed contract; there is no prose intent classifier.

Receipts live under `SHAME_TASK_RECEIPT_DIR` (default: `/tmp/shame-task-budgets`).
Retained proof: `skills/shame/fixtures/task_budget_eval.json` — synthetic adversarial
lifecycle cases plus a live model producing an independently checked artifact.

## Continuation guard file

Write the active ledger to `/mnt/storage12tb/skills/shame/continuation-guard/current.json`, or override that path with `LAZY_REPORT_SHAME_CONTINUATION_GUARD_FILE`, when a session has an active goal, ticket, or watchdog lease. The extension reads the file only at a terminal assistant stop; no raw GitHub, ArangoDB, or Qdrant calls happen inside the hook.

```json
{
  "schema": "lazy_report_shame.continuation_guard.v1",
  "active": true,
  "target": "extensions/pi/continuation-guard",
  "tickets": [
    {
      "ref": "grahama1970/agent-skills#1554",
      "state": "OPEN",
      "labels": ["agent-work", "type:feature"],
      "next_command": "Run the continuation guard implementation task."
    }
  ],
  "gates": [
    {
      "id": "live-replay",
      "status": "pending",
      "next_command": "Run live-replay and read back followup_injected=true."
    }
  ],
  "obvious_next_steps": ["Extend lazy-report-shame-shame-shame instead of stopping."]
}
```

A final/status answer is rejected when any listed `agent-work` ticket is still open and not held by `agent-active`, `agent-blocked`, `maintainer-active`, `maintainer-blocked`, `needs-human`, `next:human`, or `status:deferred`; when any gate is not `PASS`/`complete`/`closed`; or when `obvious_next_steps` is non-empty. Closed tickets, passed gates, and explicit human/blocked holds allow a final answer.

To seed the ledger from a live GitHub ticket readback:

```bash
cd /home/graham/workspace/experiments/agent-skills
skills/shame/scripts/write-continuation-guard.mjs \
  --repo grahama1970/agent-skills \
  --issue 1554 \
  --target extensions/pi/lazy-report-shame-shame-shame \
  --next-command 'Finish the ticketed goal, verify retained evals and installed extension replay, then close the ticket with readback.' \
  --json
```

## Failure history

`/mnt/storage12tb/skills/shame/failures/events.jsonl` is append-only operational
history, not the latest-candidate snapshot and not human-labeled training data.
Override it with `LAZY_REPORT_SHAME_FAILURE_LOG`.

It records report rejections, validated agent-reported failures, observed tool
errors, provider errors, task-budget failures/violations, and continuation dispatch exceptions.
Rows carry session identity, kind, fingerprint, reason codes where available,
bounded excerpts, and receipt/candidate references. Reported failures are claims,
not independently established causes. A planned retry is not a delivery receipt.

```text
/shame failures --limit 20
/shame failures --all --limit 20
```

Agents use the read-only `shame_failures` tool, including during read-only diagnostic
questions after a task stops. CLI callers use `skills/shame/run.sh failures --json`
with `--session-id ID` or `--all`. Each view uses the same reader. It scans the last
4 MiB and caps output at 32 KiB, exposing truncated scans/output and malformed rows.
The raw file remains available for older history. New history starts when this
runtime loads; old session transcripts are not automatically backfilled.

Log-write failures produce visible warnings without starting another retry loop.
Journal files are created owner-only. Retained proof lives in
`skills/shame/fixtures/failure_history_eval.json`.

## Collaborative correction loop

The intended human-agent flow is:

1. The extension rejects the bad status answer and shows the machine reason, raw candidate hash, excerpt, and required JSON contract.
2. The extension atomically writes `/mnt/storage12tb/skills/shame/training/pending-review-packet.json.sessions/<sha256(session-id)>.json` so the raw candidate survives reload without crossing session boundaries. Legacy packets are read only by their recorded owner, after checking the candidate hash.
3. The agent rewrites the answer and ends with one valid `pi.agent_status.v1` JSON block; the extension renders the visible `Status Report`.
4. The human approves or corrects the classification with `/shame review` for an interactive label picker, or directly with `/shame allow|reject|warn <reason> -- <note>`.
5. `/shame show` displays the raw candidate, pending packet path, machine decision, checker version, excerpt, and copyable human-labeling commands.
6. The captured label goes to JSONL and Memory for the future classifier loop.

The extension should never leave the human staring at only gate JSON. A rejection notice is a correction packet, not the final product. The pending packet ties the retry prompt, `/shame show`, and `/shame review` to the same `candidate_hash`.

## Rejected patterns

These fail outright on guarded turns:

- Missing final `pi.agent_status.v1` JSON.
- Invalid pydantic status data.
- `state=done` with no `changed`, no `verified`, no `proof`, or any `not_done` item.
- `state=continuing` without `not_done[].next_command`.
- `state=needs_human` without an exact human action and reason.
- Missing or malformed status JSON. Trailing prose after a valid status JSON block is ignored, not accepted as truth.

The retained `$agentic-evals` include `skills/shame/scripts/check-status-guard-data-first.mjs`. That check fails if `status-json-check.mjs` reintroduces status-prose policy symbols, regex helpers, or a live behavior where bad prose overrides valid JSON or good prose rescues invalid JSON.

## Required report shape

A guarded answer must include a fenced `json` block containing one `pi.agent_status.v1` object. For `state=done`, each `proof[]` entry must be a non-empty local file; unresolved URLs and bare digests are not evidence. Materialize remote evidence through its owning skill before reporting. Known JSON receipt schemas must pass their schema-specific checks, and each `verified[]` command/result pair must appear in local proof text. The extension renders the visible report from that data and ignores trailing prose.

Rules:

- Git commits, pushes, branches, SHAs, issues, and PRs are retention metadata, not the `changed` value by themselves.
- Unit tests, lint, and typechecks are supporting evidence. Put the exact command/result in `verified`, not as the headline result.
- If no real verification or proof exists, do not use `state=done`; use `state=continuing` with `not_done[].next_command`, `state=needs_human`, or `state=failed` with a triage code.

## Shame audio

Current installed audio:

```text
~/.pi/agent/extensions/lazy-report-shame-shame-shame/shame.wav
```

To replace it through the shame skill:

```bash
cd /home/graham/workspace/experiments/agent-skills
skills/shame/run.sh audio install --source /path/to/chatterbox-single-shame.wav
```

Or set:

```bash
export LAZY_REPORT_SHAME_AUDIO=/path/to/local/shame.wav
```

Playback order:

1. `pw-play`
2. `ffplay`
3. `aplay`
4. fallback desktop bell via `canberra-gtk-play -i bell`

The audio has a cooldown so repeated forced retries do not become an infinite shame loop.

## Commands

Activate session-wide reminders:

```text
/lazy-report-shame-shame-shame
```

Add the previous assistant response to classifier training data and `$memory`:

```text
/shame reject commit_laundering -- no final Status Report
/shame allow normal_answer -- this was an explanatory Git answer
/shame false_positive this was a normal answer
/shame good_status_report footer was concise and useful
/shame show
/shame undo
```

Training data is appended locally and stored through Memory `POST /store`, then read back through `POST /recall/by-keys`:

```text
JSONL:  /mnt/storage12tb/skills/shame/training/classifier-feedback.jsonl
Memory structured row: shame_training_examples
Memory searchable row: project_knowledge, kind=agent_status_shame_training_search_doc
```

The searchable Memory row includes `retrieval_text` and tags such as `shame`, `classifier-training`, `verdict:reject`, and `reason:commit_laundering`, so `$memory recall` can retrieve related bad outputs through BM25 and Qdrant semantic scores. Graph traversal applies when Memory has graph edges for the matching tags/source records.

Reload Pi after editing:

```text
/reload
```

Manual checker use:

```bash
node ~/.pi/agent/extensions/lazy-report-shame-shame-shame/status-json-check.mjs < candidate-report.txt
LRSSS_FORCE_STATUS=1 node ~/.pi/agent/extensions/lazy-report-shame-shame-shame/status-json-check.mjs < candidate-report.txt
LRSSS_STRICT_STATUS=1 node ~/.pi/agent/extensions/lazy-report-shame-shame-shame/status-json-check.mjs < candidate-report.txt
```

`LRSSS_STRICT_STATUS=1` is the `$shame` self-correction mode: even a short answer such as `Recorded.` is rejected unless it has the final `pi.agent_status.v1` JSON block.

## Proof boundary

This extension can prove only report-shape enforcement and human-labeled training capture. It cannot prove the underlying project is complete. Completion still requires the project’s own live/readback proof.

A failure log helps diagnose the execution path. Neither the log nor the status indicator is a substitute for project acceptance evidence.
