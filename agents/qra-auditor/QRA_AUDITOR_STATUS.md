# QRA Auditor Status

Status: contract created, supervisor dispatch proof exists, runtime not promoted
for QRA generation.

Current scope:

- QRA coverage and quality repair only.
- Bounded/gated generation repair, not DBA repair.
- No cron target.
- No live QRA generation proof yet.
- Executable worker exists at `scripts/qra_issue_worker.py`.
- Worker proof on 2026-06-26: claimed one `source_text_qra_coverage` issue,
  filed `NEEDS_AGENT -> research-auditor`, and updated the issue to
  `BLOCKED_WAITING_ON_RESEARCH`.
- Worker proof on 2026-06-26: carried a concrete
  `source_text_qra_manifest` path from monitor-sparta into the Ryan handoff.
  Isolated supervisor proof:
  `/mnt/storage12tb/skills/review-db/outputs/monitor-sparta-supervisor/monitor-sparta-manifest-flow2-20260626T211919Z-qbert/receipt.json`.
- Worker proof on 2026-06-26: in isolated supervisor flow
  `monitor-sparta-dewey-source-status-flow-20260626T214037Z`, Qbert again
  claimed one `source_text_qra_coverage` issue and handed the concrete manifest
  to Ryan. The downstream Ryan->Dewey source-status handoff then repaired two
  control-status targets. Qbert dispatch receipt is in
  `/mnt/storage12tb/skills/review-db/outputs/monitor-sparta-supervisor/monitor-sparta-dewey-source-status-flow-20260626T214037Z-tick1/receipt.json`.
- Worker proof on 2026-06-26: claimed one `qra_coverage_per_control` issue,
  filed `NEEDS_AGENT -> prompt-health-auditor`, and updated the issue to
  `BLOCKED_WAITING_ON_PROMPT_HEALTH`.

Known gaps:

- A `qra_repair.py` or equivalent reviewed wrapper may be added under
  `agents/qra-auditor/scripts/` when runtime automation is needed. It should be
  a control wrapper over `review-prompt`, Scillm/Chutes preflight, and
  `/create-qras`, not a Dewey primitive.
- Current worker intentionally does not call `/create-qras`; it gates on Petey
  and Ryan until those prerequisite receipts exist.
- Memory QRA ledger-audit contract is now documented in `persona.yaml` and
  `AGENTS.md`, with prompt, review payload, output schema, and 30-call
  llm-eval-lab plan under `agents/qra-auditor/`. Tau course-correcting eval r8
  completed 30/30 with strict JSON/schema validation before reviewer,
  max 2 creator attempts, and zero invalid-output-to-reviewer violations:
  `/mnt/storage12tb/skills/ask/outputs/eval-reports/qra-ledger-auditor-v4-course-correcting-jsonmode-r8-20260830T1631Z/results.course_correcting.json`.
  This proves the seeded agent-plausibility ledger-audit lane, not Graham
  signoff, cybersecurity expert verification, or answer authority.
- First live proof must be a small reviewed `/create-qras` manifest canary with
  prompt-review, Scillm/Chutes preflight, dry-run, write receipt, and QRA gap
  delta evidence.
