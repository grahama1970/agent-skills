# Skills CI Report: review-question

Root: `/home/graham/workspace/experiments/pi-mono/.pi/skills`
Mode: `scan`
Timestamp: `2026-03-05T07:00:30.302246+00:00`

Best practices: best-practices-kde, best-practices-plan, best-practices-python, best-practices-react, best-practices-skills, best-practices-streamdeck

Summary: 0 errors, 11 warnings, 11 total

## Violations

| Severity | Rule | Path | Message | Fixable | Applied |
|---------|------|------|---------|---------|---------|
| warn | python.file_length | /home/graham/workspace/experiments/pi-mono/.pi/skills/review-question/evidence_case.py | File exceeds 900 LOC (1061). | false | false |
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/review-question/evidence_case.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
| warn | subprocess.stderr_fatal | /home/graham/workspace/experiments/pi-mono/.pi/skills/review-question/evidence_case.py | Treats stderr as fatal error — uv/pip emit warnings to stderr that are not errors. Check returncode instead. | false | false |
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/review-question/conversation.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
| warn | subprocess.stderr_fatal | /home/graham/workspace/experiments/pi-mono/.pi/skills/review-question/conversation.py | Treats stderr as fatal error — uv/pip emit warnings to stderr that are not errors. Check returncode instead. | false | false |
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/review-question/validators.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
| warn | subprocess.stderr_fatal | /home/graham/workspace/experiments/pi-mono/.pi/skills/review-question/validators.py | Treats stderr as fatal error — uv/pip emit warnings to stderr that are not errors. Check returncode instead. | false | false |
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/review-question/mine_lessons.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
| warn | subprocess.stderr_fatal | /home/graham/workspace/experiments/pi-mono/.pi/skills/review-question/mine_lessons.py | Treats stderr as fatal error — uv/pip emit warnings to stderr that are not errors. Check returncode instead. | false | false |
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/review-question/review_question.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
| warn | subprocess.stderr_fatal | /home/graham/workspace/experiments/pi-mono/.pi/skills/review-question/review_question.py | Treats stderr as fatal error — uv/pip emit warnings to stderr that are not errors. Check returncode instead. | false | false |
