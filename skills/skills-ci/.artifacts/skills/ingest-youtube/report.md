# Skills CI Report: ingest-youtube

Root: `/home/graham/workspace/experiments/pi-mono/.pi/skills`
Mode: `scan`
Timestamp: `2026-03-05T07:00:30.302246+00:00`

Best practices: best-practices-kde, best-practices-plan, best-practices-python, best-practices-react, best-practices-skills, best-practices-streamdeck

Summary: 0 errors, 2 warnings, 2 total

## Violations

| Severity | Rule | Path | Message | Fixable | Applied |
|---------|------|------|---------|---------|---------|
| warn | routing.missing_model_flag | /home/graham/workspace/experiments/pi-mono/.pi/skills/ingest-youtube/SKILL.md | LLM-calling skill lacks --model CLI flag for `with <model>` routing. | false | false |
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/ingest-youtube/persona_monitor.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
