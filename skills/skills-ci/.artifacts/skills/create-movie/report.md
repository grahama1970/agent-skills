# Skills CI Report: create-movie

Root: `/home/graham/workspace/experiments/pi-mono/.pi/skills`
Mode: `scan`
Timestamp: `2026-03-05T07:00:30.302246+00:00`

Best practices: best-practices-kde, best-practices-plan, best-practices-python, best-practices-react, best-practices-skills, best-practices-streamdeck

Summary: 0 errors, 4 warnings, 4 total

## Violations

| Severity | Rule | Path | Message | Fixable | Applied |
|---------|------|------|---------|---------|---------|
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/create-movie/persona_integration_core.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/create-movie/persona_integration_experts.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/create-movie/sanity/e2e_60s_dream.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
| warn | subprocess.stderr_fatal | /home/graham/workspace/experiments/pi-mono/.pi/skills/create-movie/sanity/dream_30s_e2e.py | Treats stderr as fatal error — uv/pip emit warnings to stderr that are not errors. Check returncode instead. | false | false |
