# Skills CI Report: review-code

Root: `/home/graham/workspace/experiments/pi-mono/.pi/skills`
Mode: `scan`
Timestamp: `2026-03-05T07:00:30.302246+00:00`

Best practices: best-practices-kde, best-practices-plan, best-practices-python, best-practices-react, best-practices-skills, best-practices-streamdeck

Summary: 0 errors, 2 warnings, 2 total

## Violations

| Severity | Rule | Path | Message | Fixable | Applied |
|---------|------|------|---------|---------|---------|
| warn | skills.extra_docs | /home/graham/workspace/experiments/pi-mono/.pi/skills/review-code | Extra docs in skill root: request.md. | false | false |
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/review-code/commands/review.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
