# lazy-report-shame-shame-shame

A serious Pi extension wearing a joke hat, for agentic engineers who have personally suffered through “committed and pushed, done” while the actual product still does not work.

When an assistant tries to turn commit-heavy or GitHub-heavy delivery prose into progress without ending in a plain status footer, the extension rejects the answer, plays one Chatterbox “shame”, and forces the next model turn to try again.

It is meant to be funny because the failure mode is otherwise exhausting. The humor is restorative; the enforcement is not optional.

> Shame.

Every agentic engineer knows the feeling: the model confidently writes a status update where a proof should be. This extension turns that moment into one short spoken word, a rejection, and another attempt.

The installed `shame.wav` policy is deliberately small: one Chatterbox-generated word, “shame”, and no bell. Replace it only with another short single-word local file.

## What it enforces

The extension is not a reminder. It is a rejection loop.

On assistant `message_end`, it:

1. extracts the assistant’s final text;
2. runs `report-check.mjs` as a deterministic checker;
3. rejects only likely delivery/status reports that are commit-heavy, GitHub-heavy, or jargon-heavy and lack a final `Status Report` footer;
4. replaces rejected output with `REJECTED_BY_SLOTH_COURT`;
5. queues one `UNLAZY_FORCED_RETRY` with `pi.sendUserMessage(..., { deliverAs: "followUp" })`;
6. refuses to queue a second automatic retry for the same originating turn.

The guard no longer auto-activates from Pi’s system prompt or loaded `AGENTS.md` files. `$unlazy`, `/unlazy`, `unlazy`, and `acceptance ledger` prompts add a one-turn reminder. `$shame` is stricter: it marks the next assistant answer as a self-correction turn and rejects any answer that does not end in the required `Status Report` footer. The `/lazy-report-shame-shame-shame` command enables session-wide reminders explicitly.

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
