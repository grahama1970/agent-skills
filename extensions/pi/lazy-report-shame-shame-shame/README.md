# lazy-report-shame-shame-shame

A serious Pi extension wearing a joke hat, for agentic engineers who have personally suffered through “committed and pushed, done” while the actual product still does not work.

When an assistant tries to turn commit-heavy or GitHub-heavy delivery prose into progress without ending in a plain status footer, the extension rejects the answer, plays one Chatterbox “shame”, and starts a short correction workflow: the agent rewrites the status report, then the human labels the raw rejected candidate for training.

It is meant to be funny because the failure mode is otherwise exhausting. The humor is restorative; the enforcement is not optional.

> Shame.

Every agentic engineer knows the feeling: the model confidently writes a status update where a proof should be. This extension turns that moment into one short spoken word, a plain correction packet, and a human-labeling step.

The installed `shame.wav` policy is deliberately small: one Chatterbox-generated word, “shame”, and no bell. Replace it only with another short single-word local file.

## What it enforces

The extension is not a reminder. It is a rejection loop.

On assistant `message_end`, it:

1. extracts the assistant’s final text;
2. ignores tool-call-only assistant messages with no text, so intermediate tool use is not rejected as a missing report;
3. runs `report-check.mjs` as a deterministic checker;
4. rejects only likely delivery/status reports that are commit-heavy, GitHub-heavy, or jargon-heavy and lack a final `Status Report` footer;
5. when `LAZY_REPORT_SHAME_CONTINUATION_GUARD_FILE` points at an active goal/ticket ledger, rejects a final report that claims completion while relevant `agent-work` tickets, acceptance gates, or explicit next steps remain open;
6. replaces rejected output with `REJECTED_BY_SLOTH_COURT` plus a final `Status Report` footer so the replacement itself is plain-spoken;
7. queues one `UNLAZY_FORCED_RETRY` with `pi.sendUserMessage(..., { deliverAs: "followUp" })`;
8. tells the human how to label the raw rejected candidate with `/shame reject|allow|warn <reason> -- <note>`;
9. refuses to queue a second automatic retry for the same originating turn.

The guard no longer auto-activates from Pi’s system prompt or loaded `AGENTS.md` files. `$unlazy`, `/unlazy`, `unlazy`, and `acceptance ledger` prompts add a one-turn reminder. `$shame` is stricter: it marks the next assistant answer as a self-correction turn and rejects any answer that does not end in the required `Status Report` footer. The `/lazy-report-shame-shame-shame` command enables session-wide reminders explicitly. A continuation ledger file also enables status enforcement for that session because the guard has machine-readable unfinished work to check.

## Continuation guard file

Write the active ledger to `/mnt/storage12tb/skills/shame/continuation-guard/current.json`, or override that path with `LAZY_REPORT_SHAME_CONTINUATION_GUARD_FILE`, when a session has an active goal, ticket, or watchdog lease. The extension reads the file on each assistant `message_end`; no raw GitHub, ArangoDB, or Qdrant calls happen inside the hook.

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

## Collaborative correction loop

The intended human-agent flow is:

1. The extension rejects the bad status answer and shows the machine reason, raw candidate hash, excerpt, and required footer.
2. The extension writes a pending review packet to `/mnt/storage12tb/skills/shame/training/pending-review-packet.json` so the raw candidate survives an extension reload.
3. The agent rewrites the answer in plain English with `Status Report` bullets.
4. The human approves or corrects the classification with `/shame review` for an interactive label picker, or directly with `/shame allow|reject|warn <reason> -- <note>`.
5. `/shame show` displays the raw candidate, pending packet path, machine decision, checker version, excerpt, and copyable human-labeling commands.
6. The captured label goes to JSONL and Memory for the future classifier loop.

The extension should never leave the human staring at only gate JSON. A rejection notice is a correction packet, not the final product. The pending packet ties the retry prompt, `/shame show`, and `/shame review` to the same `candidate_hash`.

## Rejected patterns

These fail outright when they look like a delivery/status report and do not end with the required footer:

- Git metadata presented as progress: “Committed and pushed. Done.”
- GitHub/issue/PR-heavy closure reports with no user-visible change.
- Jargon-heavy completion prose with no proof line.
- Vague unresolved work inside a delivery report: “remaining gates are open.”

## Required report shape

A delivery/status answer must end with this exact footer shape:

```text
Status Report
- Changed: plain-English user-visible/project-visible change.
- Verified: `exact command` -> exact result, or say not verified.
- Proof: path, URL, issue, receipt, artifact, or explicit missing proof.
- Not done: none, or exact unfinished item plus next command.
```

Rules:

- Git commits, pushes, branches, SHAs, issues, and PRs are retention metadata, not the `Changed` value by themselves.
- Unit tests, lint, and typechecks are supporting evidence. Put the exact command/result in `Verified`, not as the headline result.
- If no real verification or proof exists, say that plainly and put the next command in `Not done`.

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
node ~/.pi/agent/extensions/lazy-report-shame-shame-shame/report-check.mjs < candidate-report.txt
LRSSS_FORCE_STATUS=1 node ~/.pi/agent/extensions/lazy-report-shame-shame-shame/report-check.mjs < candidate-report.txt
LRSSS_STRICT_STATUS=1 node ~/.pi/agent/extensions/lazy-report-shame-shame-shame/report-check.mjs < candidate-report.txt
```

`LRSSS_STRICT_STATUS=1` is the `$shame` self-correction mode: even a short answer such as `Recorded.` is rejected unless it has the final `Status Report` footer.

## Proof boundary

This extension can prove only report-shape enforcement and human-labeled training capture. It cannot prove the underlying project is complete. Completion still requires the project’s own live/readback proof.

The spoken “shame” is the joke. The rejection loop is not.

If this makes another agentic engineer laugh after the fifth fake “done” report of the day, it is working as designed.
