# Skills CI Report: ops-runpod

Root: `/home/graham/workspace/experiments/pi-mono/.pi/skills`
Mode: `scan`
Timestamp: `2026-02-20T07:00:09.590643+00:00`

Best practices: best-practices-kde, best-practices-python, best-practices-react, best-practices-skills, best-practices-streamdeck

Summary: 0 errors, 4 warnings, 4 total

## Violations

| Severity | Rule | Path | Message | Fixable | Applied |
|---------|------|------|---------|---------|---------|
| warn | python.requests | /home/graham/workspace/experiments/pi-mono/.pi/skills/ops-runpod/src/runpod_ops_fixed/core/training_orchestrator.py | Uses requests; prefer httpx. | true | false |
| warn | python.file_length | /home/graham/workspace/experiments/pi-mono/.pi/skills/ops-runpod/src/runpod_ops_fixed/core/training_orchestrator.py | File exceeds 800 LOC (817). | false | false |
| warn | python.file_length | /home/graham/workspace/experiments/pi-mono/.pi/skills/ops-runpod/src/runpod_ops_fixed/core/inference_server.py | File exceeds 800 LOC (823). | false | false |
| warn | python.file_length | /home/graham/workspace/experiments/pi-mono/.pi/skills/ops-runpod/src/runpod_ops_fixed/core/instance_monitor.py | File exceeds 800 LOC (819). | false | false |
