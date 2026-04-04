# Skills CI Report: extractor-quality-check

Root: `/home/graham/workspace/experiments/pi-mono/.pi/skills`
Mode: `scan`
Timestamp: `2026-03-05T07:00:30.302246+00:00`

Best practices: best-practices-kde, best-practices-plan, best-practices-python, best-practices-react, best-practices-skills, best-practices-streamdeck

Summary: 0 errors, 11 warnings, 11 total

## Violations

| Severity | Rule | Path | Message | Fixable | Applied |
|---------|------|------|---------|---------|---------|
| warn | memory.missing_has_memory_flag | /home/graham/workspace/experiments/pi-mono/.pi/skills/extractor-quality-check/memory_integration.py | memory_integration.py missing required pattern: _HAS_MEMORY | false | false |
| warn | memory.missing_recall_function | /home/graham/workspace/experiments/pi-mono/.pi/skills/extractor-quality-check/memory_integration.py | memory_integration.py missing required pattern: def recall_ | false | false |
| warn | memory.missing_learn_function | /home/graham/workspace/experiments/pi-mono/.pi/skills/extractor-quality-check/memory_integration.py | memory_integration.py missing required pattern: def learn_ | false | false |
| warn | memory.missing_extract_bridges | /home/graham/workspace/experiments/pi-mono/.pi/skills/extractor-quality-check/memory_integration.py | memory_integration.py missing required pattern: def extract_bridges | false | false |
| warn | memory.missing_bridge_keywords | /home/graham/workspace/experiments/pi-mono/.pi/skills/extractor-quality-check/memory_integration.py | memory_integration.py missing required pattern: _BRIDGE_KEYWORDS | false | false |
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/extractor-quality-check/datalake_state_collector.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
| warn | subprocess.stderr_fatal | /home/graham/workspace/experiments/pi-mono/.pi/skills/extractor-quality-check/datalake_state_collector.py | Treats stderr as fatal error — uv/pip emit warnings to stderr that are not errors. Check returncode instead. | false | false |
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/extractor-quality-check/batch_review.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/extractor-quality-check/convergence_tracker.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/extractor-quality-check/_context.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/extractor-quality-check/_teacher.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
