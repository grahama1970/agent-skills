# Skills CI Report: scheduler

Root: `/home/graham/workspace/experiments/pi-mono/.pi/skills`
Mode: `scan`
Timestamp: `2026-02-20T07:00:09.590643+00:00`

Best practices: best-practices-kde, best-practices-python, best-practices-react, best-practices-skills, best-practices-streamdeck

Summary: 0 errors, 2 warnings, 2 total

## Violations

| Severity | Rule | Path | Message | Fixable | Applied |
|---------|------|------|---------|---------|---------|
| warn | python.argparse | /home/graham/workspace/experiments/pi-mono/.pi/skills/scheduler/scheduler_monolith.py | Uses argparse; prefer Typer. | false | false |
| warn | python.file_length | /home/graham/workspace/experiments/pi-mono/.pi/skills/scheduler/scheduler_monolith.py | File exceeds 800 LOC (1283). | false | false |
