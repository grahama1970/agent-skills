# Skills CI Report: hack

Root: `/home/graham/workspace/experiments/pi-mono/.pi/skills`
Mode: `scan`
Timestamp: `2026-03-05T07:00:30.302246+00:00`

Best practices: best-practices-kde, best-practices-plan, best-practices-python, best-practices-react, best-practices-skills, best-practices-streamdeck

Summary: 0 errors, 10 warnings, 10 total

## Violations

| Severity | Rule | Path | Message | Fixable | Applied |
|---------|------|------|---------|---------|---------|
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/hack/cascade_integration.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/hack/utils.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
| warn | subprocess.stderr_fatal | /home/graham/workspace/experiments/pi-mono/.pi/skills/hack/utils.py | Treats stderr as fatal error — uv/pip emit warnings to stderr that are not errors. Check returncode instead. | false | false |
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/hack/commands.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/hack/remediation.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/hack/chaos.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
| warn | subprocess.stderr_fatal | /home/graham/workspace/experiments/pi-mono/.pi/skills/hack/tools/nuclei.py | Treats stderr as fatal error — uv/pip emit warnings to stderr that are not errors. Check returncode instead. | false | false |
| warn | subprocess.stderr_fatal | /home/graham/workspace/experiments/pi-mono/.pi/skills/hack/tools/semgrep.py | Treats stderr as fatal error — uv/pip emit warnings to stderr that are not errors. Check returncode instead. | false | false |
| warn | subprocess.stderr_fatal | /home/graham/workspace/experiments/pi-mono/.pi/skills/hack/tools/nmap.py | Treats stderr as fatal error — uv/pip emit warnings to stderr that are not errors. Check returncode instead. | false | false |
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/hack/tests/test_integration.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
