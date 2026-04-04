# Skills CI Report: skills-ci

Root: `/home/graham/workspace/experiments/pi-mono/.pi/skills`
Mode: `scan`
Timestamp: `2026-03-05T07:00:30.302246+00:00`

Best practices: best-practices-kde, best-practices-plan, best-practices-python, best-practices-react, best-practices-skills, best-practices-streamdeck

Summary: 0 errors, 4 warnings, 4 total

## Violations

| Severity | Rule | Path | Message | Fixable | Applied |
|---------|------|------|---------|---------|---------|
| warn | python.module_docstring | /home/graham/workspace/experiments/pi-mono/.pi/skills/skills-ci/tests/fixtures/skills_root/skill-a/example.py | Missing module docstring. | true | false |
| warn | python.requests | /home/graham/workspace/experiments/pi-mono/.pi/skills/skills-ci/tests/fixtures/skills_root/skill-a/example.py | Uses requests; prefer httpx. | true | false |
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/skills-ci/integrations.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/skills-ci/runtime_scanners.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
