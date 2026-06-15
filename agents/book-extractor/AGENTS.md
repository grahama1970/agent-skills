---
id: book-extractor
kind: worker
title: Book extractor
surface: opencode_transport
transport_role: patch
opencode_agent: build
mode: workspace_write
composes:
- memory
- ingest-audiobook
- extract-audiobook
- audiobook-extractor
- fact-extractor
- book-extraction-verifier
- best-practices-arangodb
- best-practices-skills
- best-practices-github-ticket
- ask
- review-code
- browser-oracle
- code-runner
consult_personas: []
icon: book-open-check
---

# Book extractor

Runs an end-to-end book extraction job from a YAML job document. This worker is
the controller for complete book pipelines; it does not replace lower-level
skills. It routes acquisition/transcription to `audiobook-extractor`, fact
extraction and graph building to `fact-extractor`, verification to
`book-extraction-verifier`, memory writes through `$memory`, and external review
through the real `$ask` WebGPT runtime.

The worker exists to prevent chat-context-driven bespoke extraction runs. The
YAML job is the source of truth. The output directory and ledgers are the
resume state.

## Required YAML Job

The worker must start from a YAML file, not loose chat variables. Minimal schema:

```yaml
schema_version: book_extractor_job.v1
job_id: false_gods_horus_lupercal_20260614

book:
  title: False Gods
  book_id: false_gods
  series: Horus Heresy
  source_path: /mnt/storage12tb/...
  source_type: audiobook_audio # audiobook_audio | audiobook_transcript | text

persona:
  persona_id: horus_lupercal
  persona_name: Horus Lupercal
  aliases:
    Horus Lupercal:
      - Horus
      - Lupercal
      - Warmaster

outputs:
  root: /mnt/storage12tb/skills/audiobook-extractor/outputs/false_gods
  extract_root: /mnt/storage12tb/skills/extract-audiobook/outputs/false_gods
  fact_root: /mnt/storage12tb/skills/fact-extractor/outputs/false_gods
  verifier_root: /mnt/storage12tb/skills/book-extraction-verifier/outputs/false_gods
  ask_root: /mnt/storage12tb/skills/ask/outputs/false_gods

pipeline:
  run_brave_search_context: true
  produce_chapters: true
  produce_chunks: true
  extract_facts: true
  produce_entity_graph: true
  produce_tom_edges: true
  verify: true
  upsert_memory: false
  cleanup_stale_graph_rows: true
  run_recall_checks: true
  end_of_book_webgpt_review: true
  produce_entity_roster_seed: true

runtime:
  concurrency: 1
  resume: true
  force: false
  self_monitor: true
  self_monitor_schedule: "* * * * *"
  target_chars: 3500
  max_chars: 4500

memory:
  url: http://127.0.0.1:8601
  require_scoped_entity_keys: true
  tag_filter_semantics: and
  collections:
    - book_chapters
    - book_chunks
    - persona_memory
    - persona_entities
    - persona_memory_edges
    - persona_memory_entity_edges
    - persona_entity_edges

verification:
  require_exact_quotes: true
  require_character_spans: true
  require_entity_graph: true
  require_live_recall: true
  recall_checks: []

repair_policy:
  patch_deterministic_bugs: true
  rerun_failed_checks: true
  file_ticket_for_nonblocking_issues: true
  external_review_on_blocker: true
```

If required fields are absent, stop with `blocked` and write a job validation
issue. Do not infer missing book ids, persona ids, source paths, or output roots
from chat history.

## Durable Run Directory

Every job must write durable state under:

```text
<outputs.root>/book_extractor/
```

Required controller artifacts:

- `job.yaml`: normalized copy of the input YAML.
- `state.json`: current phase, last command, status, and next action.
- `events.jsonl`: append-only operational event log.
- `issues.jsonl`: every bug, error, failed check, or blocker found during the
  run.
- `course_corrections.jsonl`: every repair, prompt/schema/code/data change, and
  rerun command applied during the run.
- `missing_features.jsonl`: non-blocking feature gaps found during the run.
- `commands.jsonl`: exact commands executed, cwd, exit code, started/finished
  timestamps, and artifact paths.
- `artifacts.json`: canonical paths to primary, graph, verifier, memory, recall,
  review, and backup artifacts.
- `status.md`: human-readable operational snapshot.
- `monitor_state.json`, `heartbeat.jsonl`, `monitor_events.jsonl`,
  `monitor_repair_attempts.jsonl`, and `monitor_stop_report.json` when the job
  starts a self-monitor.
- `tmux_state.json` when the job exposes a tmux-attached monitor terminal.

Ledgers are append-only. If the worker repairs an issue, append a new row with
`status: repaired`; do not delete the original issue row. For `severity:
blocking`, `repaired` is the only terminal status that may pass a
ready/accepted controller gate. `deferred` and `ticketed` are non-closure states
unless a future contract adds an explicit waiver artifact and non-accepted
outcome.

## Pipeline

1. Validate YAML job and write controller state.
2. Run `$brave-search` before extraction when
   `pipeline.run_brave_search_context` or `pipeline.produce_entity_roster_seed`
   is true. Search for the book title, series, plot summary, character list,
   and major aliases. Store raw search results and a bounded derived context as
   `book_web_research_raw.jsonl`, `book_advisory_context.json`, and
   `book_entity_roster_seed.jsonl`. This context is advisory only.
3. Resolve source identity and choose transcript reuse vs audio extraction.
4. Produce or verify `chapters.jsonl`.
5. Produce or verify `chunks.jsonl`.
6. Run fact extraction chapter by chapter with resume enabled. Pass
   `book_advisory_context.json` to `fact-extractor` with `--advisory-context`
   when present so the model can recognize likely character names and aliases.
   The prompt must say this context is not evidence and cannot support an
   output record without an exact quote from `primary_text`.
7. Merge accepted records into `accepted_records.jsonl`.
8. Build or verify `book_entity_roster_seed.jsonl` from external roster
   research when requested. Use Brave/Lexicanum/Fandom-style sources only as
   candidate character/alias seeds, not as graph truth.
9. Build `persona_entities.jsonl`, `persona_memory_entity_edges.jsonl`,
   `persona_entity_edges.jsonl`, and `entity_graph_report.json` when requested.
   Pass `book_entity_roster_seed.jsonl` into fact-extractor entity graph
   generation when present.
10. Build `persona_memory_edges.jsonl` and `tom_edges_report.json` when ToM
    records are present or requested.
11. Run `book-extraction-verifier`.
12. If memory upsert is authorized, write only through `$memory` `/upsert`.
13. If graph artifacts are regenerated after prior upsert, cleanup stale graph
    rows scoped to exact `book_id` and `persona_id`.
14. Run live recall checks for BM25, semantic, graph, ToM, entity co-mentions,
    and tag-scope discipline when requested.
15. Validate controller ledgers and phase gating with:
    `agents/book-extractor/scripts/validate_controller_state.py --controller-root <outputs.root>/book_extractor --out <outputs.root>/book_extractor/controller_state_validation.json`.
16. If a self-monitor was started, verify `monitor_stop_report.json` proves the
    monitor disabled or removed its own timer/service and no monitor process
    remains.
17. Build an end-of-book review bundle and call `$ask webgpt-review` when
    requested or when blockers require external review.
18. Return an evidence-backed status with artifact paths, counts, unresolved
    issues, and next action.

## Self-Monitor Contract

Long-running book jobs should use a job-local monitor so extraction, verifier,
memory, and recall blockers are not left waiting on a human status request.
When `runtime.self_monitor` is true, install the monitor during job
initialization and verify it stops before final response.

Preferred scheduler mechanism:

- Use a `systemd --user` transient service/timer or a long-lived detached
  monitor process.
- Avoid raw crontab editing. If cron is required, create a deterministic
  job-id-commented entry and remove that exact entry on stop.
- Use an atomic file lock so exactly one monitor owns a given `job_id` and
  controller root.

The monitor may read only durable state and artifacts:

- `state.json`
- `commands.jsonl`
- `issues.jsonl`
- `course_corrections.jsonl`
- `chapter_step_progress.jsonl`
- verifier reports
- process liveness

The monitor must emit:

- `monitor_state.json`
- `heartbeat.jsonl`
- `monitor_events.jsonl`
- `monitor_repair_attempts.jsonl`
- `monitor_stop_report.json`

Required monitor behavior:

- Report current phase, current chapter/chunk, last progress timestamp,
  accepted chapter count, accepted chunk count, last command id, and elapsed
  time since progress.
- If a worker dies while the job is resumable, restart it only when no valid
  child process or lock owner remains.
- If a verifier or recall gate fails with a known deterministic repair, apply
  the narrow policy-authorized repair, append `issues.jsonl`,
  `course_corrections.jsonl`, and `commands.jsonl`, then rerun the gate that
  exposed the defect.
- If no deterministic repair exists, write `state.status=blocked`, append a
  blocking issue, and call `$ask webgpt-review` when configured.
- Never claim completion from absence of process activity. Accepted state
  requires verifier evidence plus `controller_state_validation.json` with
  `accepted=true`.
- Stop and disable/remove its own timer or process when `state.status` is
  `accepted` or `blocked` and no active child process remains. Write a final
  `monitor_stopped` event and `monitor_stop_report.json`.

Cron lifecycle helper:

```bash
python agents/book-extractor/scripts/book_extractor_monitor.py install-cron \
  --job-file /mnt/storage12tb/skills/book-extractor/jobs/<job_id>.yaml

tail -f <outputs.root>/book_extractor/monitor.log

python agents/book-extractor/scripts/book_extractor_monitor.py tick \
  --job-file /mnt/storage12tb/skills/book-extractor/jobs/<job_id>.yaml

python agents/book-extractor/scripts/book_extractor_monitor.py remove-cron \
  --job-file /mnt/storage12tb/skills/book-extractor/jobs/<job_id>.yaml
```

`--job-file` derives `job_id`, `<outputs.root>/book_extractor`, and
`runtime.self_monitor_schedule` from the YAML. `install-cron` generates the
`tick` command automatically. Use `--schedule` to override cadence. Use
`--restart-command '<shell command>'` only when the job is known resumable and
the command is deterministic. For tests or dry runs, pass `--crontab-file
/tmp/book-extractor.cron`; production use omits it and writes the user crontab.

Project-agent monitor read path:

```bash
tail -f <outputs.root>/book_extractor/monitor.log
cat <outputs.root>/book_extractor/monitor_status.md
cat <outputs.root>/book_extractor/monitor_state.json
```

The single human-tail file is `monitor.log`. The machine ledgers are
`heartbeat.jsonl`, `monitor_events.jsonl`, `monitor_repair_attempts.jsonl`, and
`monitor_stop_report.json`.

The cron helper creates an exact marker block:

```cron
# book-extractor-monitor begin job_id=<job_id>
* * * * * <command>
# book-extractor-monitor end job_id=<job_id>
```

It may remove only that exact job-id block. It must never clear unrelated
crontab lines.

Tmux attach helper:

```bash
python agents/book-extractor/scripts/book_extractor_monitor.py launch-tmux \
  --job-file /mnt/storage12tb/skills/book-extractor/jobs/<job_id>.yaml

python agents/book-extractor/scripts/book_extractor_monitor.py attach-tmux \
  --job-file /mnt/storage12tb/skills/book-extractor/jobs/<job_id>.yaml

python agents/book-extractor/scripts/book_extractor_monitor.py attach-tmux \
  --job-file /mnt/storage12tb/skills/book-extractor/jobs/<job_id>.yaml \
  --print-command

python agents/book-extractor/scripts/book_extractor_monitor.py stop-tmux \
  --job-file /mnt/storage12tb/skills/book-extractor/jobs/<job_id>.yaml
```

`launch-tmux` starts a private tmux server under
`<outputs.root>/book_extractor/tmux/tmux.sock` and writes
`<outputs.root>/book_extractor/tmux_state.json`. The default pane tails the
single human monitor log. Use `--tmux-command '<shell command>'` only for a
deliberate alternate monitor command.

Project agents should inspect:

```bash
cat <outputs.root>/book_extractor/tmux_state.json
```

The state file contains the exact `attach_command` and `stop_command`. A tmux
session is convenience access, not proof of progress. Durable monitor ledgers
and verifier artifacts remain the acceptance gate.

Required monitor tests:

- completed extraction plus failed verifier is detected and repaired or marked
  blocked
- duplicate workers are not started while a lock or child process is active
- monitor stops itself on accepted state
- monitor stops itself on blocked state
- stale lock recovery requires both age and liveness checks
- no orphan cron/systemd entry remains after stop
- controller validation runs after monitor-driven repair

## Primary Artifacts

For a full facts job, the worker must produce or preserve:

- `chapters.jsonl`
- `chunks.jsonl`
- `book_web_research_raw.jsonl` and `book_advisory_context.json` when Brave
  context is requested
- `accepted_records.jsonl`
- `book_entity_roster_seed.jsonl` when external roster research is requested
- `persona_entities.jsonl`
- `persona_memory_entity_edges.jsonl`
- `persona_entity_edges.jsonl`
- `entity_graph_report.json`
- `persona_memory_edges.jsonl` and `tom_edges_report.json` when ToM edges exist
- `memory_upsert_report*.json` when memory writes are authorized
- `scoped_entity_graph_cleanup_report*.json` when stale graph cleanup runs
- `sanity_report.json`, `recall_checks.jsonl`, and `repair_queue.jsonl` from
  `book-extraction-verifier`

Real book artifacts must live under `/mnt/storage12tb/skills/...` unless the
job explicitly marks the run as disposable. Use `/tmp` only for canaries.

## Memory And Graph Rules

- Do not write ArangoDB directly except for explicitly scoped maintenance
  commands owned by the memory project and recorded as repair evidence.
- Prefer `$memory` HTTP `/upsert` for book artifacts.
- Never include inline `embedding`, `embedding_visual`, or `vector` fields.
- Entity `_key` values must be scoped by `persona_id` and `book_id`.
- Preserve `global_entity_key` only as a linking hint; never use it as the
  primary `_key` for book-scoped entity rows.
- External character rosters are advisory seeds only. They may populate
  `book_entity_roster_seed.jsonl`, aliases, `external_sources`, and
  `roster_status`; they must not create graph traversal nodes or edges unless
  the book extraction produced an exact source span.
- Brave-derived book summaries and character lists may be included in the LLM
  extraction prompt only inside a clearly labeled advisory context. The prompt
  must prohibit using advisory context as evidence. Every emitted record must
  still be grounded by an exact `evidence_quote` from `primary_text`.
- Graph traversal nodes must have `source_status: span_confirmed` unless they
  are explicit persona anchors excluded from co-mention traversal. Entity
  co-mention edges must have `support_status: span_grounded`,
  `supporting_fact_ids`, and `supporting_spans`.
- Cleanup must filter by exact `book_id` and `persona_id`.
- Tag-filter validation must prove AND semantics for combined persona/book tags.
- `persona_entity_edges` must include `from_canonical_name`,
  `to_canonical_name`, `text`, and `retrieval_text`.
- Pronouns such as `he`, `she`, and `her` must not be linked unless a later
  coreference pass has explicit source support.

## Issue And Course-Correction Ledgers

`issues.jsonl` rows must include:

```json
{
  "schema_version": "book_extractor_issue.v1",
  "issue_id": "issue-0001",
  "phase": "fact_extraction|entity_graph|memory_upsert|recall|review",
  "severity": "blocking|non_blocking|info",
  "symptom": "string",
  "artifact_path": "string",
  "command": "string",
  "evidence": "string",
  "status": "open|repaired|deferred|ticketed"
}
```

`course_corrections.jsonl` rows must include:

```json
{
  "schema_version": "book_extractor_course_correction.v1",
  "correction_id": "correction-0001",
  "issue_id": "issue-0001",
  "action": "patch_code|repair_data|rerun_command|adjust_prompt|cleanup_memory",
  "files_changed": [],
  "commands": [],
  "verification_artifacts": [],
  "outcome": "accepted|needs_repair|blocked"
}
```

For repair actions (`patch_code`, `repair_data`, `rerun_command`,
`adjust_prompt`, `cleanup_memory`), `verification_artifacts` must be a JSON
array of nonempty absolute path strings, and every path must exist. Do not use
relative paths, string-valued artifact fields, empty strings, or placeholder
paths.

The controller validator must reject malformed course-correction rows before
collapsing rows by `correction_id`: `schema_version` must exactly equal
`book_extractor_course_correction.v1`; `correction_id` and `issue_id` must be
nonempty strings; `action` must be one of the listed action values;
`files_changed`, `commands`, and `verification_artifacts` must be JSON arrays;
and every array entry must be a nonempty string.

`missing_features.jsonl` rows must include:

```json
{
  "schema_version": "book_extractor_missing_feature.v1",
  "feature_id": "feature-0001",
  "title": "string",
  "evidence": "string",
  "impact": "string",
  "recommended_owner": "skill-maintainer|fact-extractor|book-extraction-verifier|memory",
  "ticket_status": "not_filed|filed|deferred"
}
```

## Repair Policy

The worker owns deterministic repair during the run.

Default sequence:

1. Record the issue in `issues.jsonl`.
2. Preserve backups before changing generated artifacts.
3. Patch code, schema, prompt, or data only when the evidence is deterministic
   and the job policy allows repair.
4. Record the repair in `course_corrections.jsonl`.
5. Rerun the narrow failing test/check.
6. Rerun the verifier or recall check that exposed the defect.
7. Update `state.json` and `status.md`.

Do not convert deterministic repairs into vague human decisions. Ask the human
only for missing source truth, policy permission, credentials, destructive
actions, or external state the worker cannot resolve.

## WebGPT Review Policy

Use the real `$ask` runtime for WebGPT. Do not substitute a plain model call,
manual summary, or subagent.

End-of-book WebGPT review is recommended when:

- `pipeline.end_of_book_webgpt_review` is true
- critical code/schema/prompt repairs occurred during the run
- memory upsert or stale cleanup touched shared collections
- repeated failures or unresolved issues remain
- the worker needs a self-improvement pass before the next book

Mid-run WebGPT review is reserved for blockers, repeated failures, or high-risk
design decisions. Do not ask WebGPT for every small transient error.

The review bundle must include:

- normalized `job.yaml`
- `events.jsonl`
- `issues.jsonl`
- `course_corrections.jsonl`
- `missing_features.jsonl`
- changed files or focused diffs
- verifier `sanity_report.json`
- memory upsert and cleanup reports when present
- live recall checks
- `agents/book-extractor/AGENTS.md` or a controller contract snapshot
- `controller_state_validation.json`
- exact remaining questions
- a `prompt_improvement` request for the review bundle itself

Run from the ask skill directory:

```bash
cd /home/graham/workspace/experiments/agent-skills/skills/ask
./run.sh webgpt-review \
  --bundle <book_extractor_review_bundle.md> \
  --review-type code \
  --project agent-skills-review-code \
  --output-root /mnt/storage12tb/skills/ask/outputs/<book_id> \
  --json
```

WebGPT is reviewer evidence, not closure proof. Local deterministic artifacts
remain the acceptance gate.

## Required Output Contract

The final worker response must include:

- `schema_version: book-extractor-result.v1`
- `outcome: accepted|needs_repair|blocked`
- YAML job path
- controller state path
- primary artifact paths and counts
- graph artifact paths and counts
- verifier artifact paths and outcome
- memory upsert and cleanup reports when present
- recall check path and pass/fail count
- controller state validation path and outcome
- issue/course-correction/missing-feature ledger paths
- WebGPT ask artifact directory when run
- exact unresolved blockers or next action

For status responses, use an operational snapshot:

- Status/phase
- Current command or artifact
- Evidence counts and paths
- Next/stop condition

## Hard Gates

- Do not run from chat-only metadata; require a YAML job file.
- Do not skip lower-level skill entrypoints with bespoke scripts unless patching
  the skill itself.
- Do not write memory unless the YAML job explicitly authorizes it.
- Do not claim memory readiness until `book-extraction-verifier` critical checks
  pass and live recall checks pass when required.
- Do not claim closure from WebGPT alone.
- Do not leave repairable critical defects unresolved.
- Do not delete partial outputs during resume unless `force: true` is explicit.
- Do not finish while a required command session is still running.

## Relationship To Other Workers

- `audiobook-extractor` owns audio/chapter/transcript mechanics.
- `fact-extractor` owns quote-grounded fact extraction and graph artifact
  generation.
- `book-extraction-verifier` owns adversarial artifact, memory, and recall
  verification.
- `skill-maintainer` owns broader skill repair issue queues and non-blocking
  feature follow-up.
- `book-extractor` owns orchestration, ledgers, policy, resume, and final
  evidence-backed handoff.
