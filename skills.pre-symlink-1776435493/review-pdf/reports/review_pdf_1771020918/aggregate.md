# review-pdf aggregate report

- run_id: `review_pdf_1771020918`
- documents_total: `1`
- documents_analyzed: `1`
- documents_missing: `0`
- overall_average_score: `0.6714`
- extraction_events_count: `0`
- extraction_failed_count: `0`
- extraction_succeeded_count: `0`

## verdict counts
- PASS: `0`
- WARN: `1`
- FAIL: `0`

## domain summary
- unknown: count=1 pass=0 warn=1 fail=0

## top issue codes
- duplicate_content_high: `1`
- section_alignment_low: `1`

## recommended helper skills
- create-classifier
- classifier-lab
- normalize
- quality-audit

## aggregate helper jobs
- [quality-audit] `cd /home/graham/workspace/experiments/pi-mono/.pi/skills/quality-audit && ./run.sh report --input reports/review_pdf_1771020918/per_doc --output reports/review_pdf_1771020918/quality_audit.md`
  reason: validate stratified quality distribution across reviewed PDFs
- [batch-quality] `cd /home/graham/workspace/experiments/pi-mono/.pi/skills/batch-quality && ./run.sh preflight --stage 11 --samples 5`
  reason: run preflight quality gate before large reruns
- [corpus-report] `cd /home/graham/workspace/experiments/pi-mono/.pi/skills/corpus-report && ./run.sh quality --json`
  reason: measure corpus-level extraction trends and bottlenecks
- [analytics] `cd /home/graham/workspace/experiments/pi-mono/.pi/skills/analytics && ./run.sh describe reports/review_pdf_1771020918/aggregate.json`
  reason: profile aggregate metrics for dashboard and change tracking
- [monitor-pdfs] `cd /home/graham/workspace/experiments/pi-mono/.pi/skills/monitor-pdfs && ./run.sh status`
  reason: track extraction throughput and status while remediation runs
- [data-audit] `cd /home/graham/workspace/experiments/pi-mono/.pi/skills/data-audit && uv run python audit.py --help`
  reason: verify coverage completeness in downstream data products
- [task-monitor] `cd /home/graham/workspace/experiments/pi-mono/.pi/skills/task-monitor && ./run.sh --help`
  reason: observe long-running classifier/prompt improvement tasks
