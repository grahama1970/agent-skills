# Ryan Research Auditor Status

Status: contract created, supervisor dispatch proof exists, source-fetch
primitive implementation not promoted.

Ryan is registered as the research/source-fetch lane subagent for monitor-sparta
handoffs. The executable worker at `scripts/research_issue_worker.py` claims one
source/research issue, writes a memory-backed `subagent_decision.v1` row,
updates one queue issue, and exits.

Worker proof on 2026-06-26: supervisor materialized a Qbert
`NEEDS_AGENT -> research-auditor` decision into
`monitor-sparta:source-fetch:20260626T205944Z`; Ryan filed `NEEDS_HUMAN` with
decision `source_fetch_worker_not_implemented` and marked the queue issue
`OPERATOR_REQUIRED`.

Worker proof on 2026-06-26: Ryan consumed a Qbert
`source_text_qra_manifest`, wrote
`source_evidence_manifest.json`, identified three exact source text targets
(`ctrl__T1454`, `ctrl__10`, and `url__2651`), filed `NEEDS_HUMAN`, and marked
the source-fetch issue `OPERATOR_REQUIRED`. Isolated supervisor proof:
`/mnt/storage12tb/skills/review-db/outputs/research-auditor/monitor-sparta-manifest-flow2-20260626T211919Z-ryan-source_fetch/receipt.json`.

Worker proof on 2026-06-26: Ryan enriched the three exact source targets with
source-resolution evidence:

- `ctrl__T1454`: official MITRE Mobile ATT&CK CTI confirms `revoked=true` and
  description `Test`; recommended next owner is Dewey for rollback-backed
  deprecated/excluded metadata repair.
- `ctrl__10`: `SPARTA-Data.xlsx` / `worksheets.yaml` source row is heading-only
  (`ID=10`, `Name=Improvement`, `Type=Requirement`) with no narrative; recommended
  next owner is Dewey for rollback-backed heading-only non-generation/exclusion
  metadata repair.
- `url__2651`: no `sparta_url_knowledge` rows exist; Ryan remains the owner for
  external URL fetch/extract evidence.

Evidence receipt:
`/mnt/storage12tb/skills/review-db/outputs/research-auditor/ryan-source-resolution-proof-20260626T212828Z/receipt.json`.

Worker proof on 2026-06-26: Ryan now files a `NEEDS_AGENT` handoff to Dewey
when a source evidence manifest contains deterministic control-status repairs.
Isolated supervisor flow
`monitor-sparta-dewey-source-status-flow-20260626T214037Z` produced a Dewey
`source_text_status_repair` issue for two control targets and left the unresolved
URL fetch target with Ryan. Ryan receipt:
`/mnt/storage12tb/skills/review-db/outputs/research-auditor/monitor-sparta-dewey-source-status-flow-20260626T214037Z-tick2-source_fetch/receipt.json`.

URL fetch proof on 2026-06-26: Ryan/fetcher retrieved `url_id=2651` from the
authoritative Technet/Microsoft Learn redirect path. Fetcher receipt:
`/mnt/storage12tb/skills/review-db/outputs/research-auditor/url-2651-fetch-20260626T214720Z/consumer_summary.json`.
That artifact was consumed by Dewey's `dewey_url_text_backfill.py` primitive.

Known gap: Ryan can now produce exact source evidence manifests and has a
future worker path to run fetcher for URL targets and hand usable fetch artifacts
to Dewey. The current live queue still contains older blocked/operator source
handoff rows from before this patch; the latest source coverage rescan reports
no `control_text` or `url_text` source targets.
