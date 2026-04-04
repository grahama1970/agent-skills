# Skills CI Report: episodic-archiver

Root: `/home/graham/workspace/experiments/pi-mono/.pi/skills`
Mode: `scan`
Timestamp: `2026-03-05T07:00:30.302246+00:00`

Best practices: best-practices-kde, best-practices-plan, best-practices-python, best-practices-react, best-practices-skills, best-practices-streamdeck

Summary: 0 errors, 4 warnings, 4 total

## Violations

| Severity | Rule | Path | Message | Fixable | Applied |
|---------|------|------|---------|---------|---------|
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/episodic-archiver/analysis_integrations.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/episodic-archiver/session_analysis.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
| warn | subprocess.stderr_fatal | /home/graham/workspace/experiments/pi-mono/.pi/skills/episodic-archiver/session_analysis.py | Treats stderr as fatal error — uv/pip emit warnings to stderr that are not errors. Check returncode instead. | false | false |
| warn | subprocess.raw_aql | /home/graham/workspace/experiments/pi-mono/.pi/skills/episodic-archiver/analysis_edges.py | Direct ArangoDB AQL execution — must use /memory skill instead. | false | false |
