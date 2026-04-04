# review-pdf aggregate report

- run_id: `review_pdf_batch_1771950254`
- documents_total: `50`
- documents_analyzed: `50`
- documents_missing: `0`
- overall_average_score: `0.8243`
- extraction_events_count: `0`
- extraction_failed_count: `0`
- extraction_succeeded_count: `0`

## verdict counts
- PASS: `45`
- WARN: `0`
- FAIL: `5`

## domain summary
- unknown: count=50 pass=45 warn=0 fail=5

## top issue codes
- section_alignment_low: `35`
- content_overextract_medium: `3`
- content_overextract_high: `2`
- table_recall_low: `1`

## recommended helper skills
- classifier-lab
- create-classifier
- debug-pdf
- normalize
- quality-audit
- create-table-classifier
- table-lab

## aggregate helper jobs
- [quality-audit] `cd /home/graham/workspace/experiments/pi-mono/.pi/skills/quality-audit && ./run.sh report --input reports/review_pdf_batch_1771950254/per_doc --output reports/review_pdf_batch_1771950254/quality_audit.md`
  reason: validate stratified quality distribution across reviewed PDFs
- [batch-quality] `cd /home/graham/workspace/experiments/pi-mono/.pi/skills/batch-quality && ./run.sh preflight --stage 11 --samples 5`
  reason: run preflight quality gate before large reruns
- [corpus-report] `cd /home/graham/workspace/experiments/pi-mono/.pi/skills/corpus-report && ./run.sh quality --json`
  reason: measure corpus-level extraction trends and bottlenecks
- [analytics] `cd /home/graham/workspace/experiments/pi-mono/.pi/skills/analytics && ./run.sh describe reports/review_pdf_batch_1771950254/aggregate.json`
  reason: profile aggregate metrics for dashboard and change tracking
- [monitor-pdfs] `cd /home/graham/workspace/experiments/pi-mono/.pi/skills/monitor-pdfs && ./run.sh status`
  reason: track extraction throughput and status while remediation runs
- [data-audit] `cd /home/graham/workspace/experiments/pi-mono/.pi/skills/data-audit && uv run python audit.py --help`
  reason: verify coverage completeness in downstream data products
- [task-monitor] `cd /home/graham/workspace/experiments/pi-mono/.pi/skills/task-monitor && ./run.sh --help`
  reason: observe long-running classifier/prompt improvement tasks
