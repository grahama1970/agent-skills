# Prompt Health Auditor Status

Status: contract created, supervisor dispatch proof exists, prompt-review bundle
generation proof exists, review-prompt PASS receipt not present.

Petey contract exists as a prompt-health lane worker. The executable worker at
`scripts/prompt_health_issue_worker.py` claims one `prompt_health` issue, writes
a memory-backed `subagent_decision.v1` row, updates one queue issue, and exits.

Worker proof on 2026-06-26: supervisor dispatched Petey for
`monitor-sparta:prompt-health:for-20260626T205944Z`; Petey filed
`NEEDS_REVIEW` with decision `prompt_health_worker_not_implemented` and marked
the queue issue `OPERATOR_REQUIRED`.

Worker proof on 2026-06-26: isolated queue run
`petey-prompt-health-bundle-proof-20260626T215749Z` produced a prompt-reviewer
request bundle for `qra_coverage_per_control` and filed `NEEDS_REVIEW` with
decision `prompt_review_bundle_ready`.

Artifacts:

- Receipt:
  `/mnt/storage12tb/skills/review-db/outputs/prompt-health-auditor/petey-prompt-health-bundle-proof-20260626T215749Z/receipt.json`
- Request JSON:
  `/mnt/storage12tb/skills/review-db/outputs/prompt-health-auditor/petey-prompt-health-bundle-proof-20260626T215749Z/prompt-reviewer/prompt-review-request.json`
- Request Markdown:
  `/mnt/storage12tb/skills/review-db/outputs/prompt-health-auditor/petey-prompt-health-bundle-proof-20260626T215749Z/prompt-reviewer/prompt-review-request.md`
- Required PASS receipt path:
  `/mnt/storage12tb/skills/review-db/outputs/prompt-health-auditor/petey-prompt-health-bundle-proof-20260626T215749Z/prompt-reviewer/prompt-reviewer-receipt.json`

Evidence fields: `bundle_ok=true`, `registry_status=NEEDS_REVIEW`,
`queue_status=OPERATOR_REQUIRED`, `failed_dimensions=["qra_coverage_per_control"]`,
`database_mutation=false`, `repair_cycle_invoked=false`, `health_fix_invoked=false`.

Known gap: Petey has not run the full `$review-prompt` / prompt-reviewer loop
to produce a live PASS receipt. Until that receipt exists and validates, Qbert
must not run QRA generation from that prompt category.
