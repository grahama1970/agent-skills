# Skills CI Report: agents-registry

Root: `/home/graham/workspace/experiments/pi-mono/.pi/skills`
Mode: `scan`
Timestamp: `2026-03-05T07:00:30.302246+00:00`

Best practices: best-practices-kde, best-practices-plan, best-practices-python, best-practices-react, best-practices-skills, best-practices-streamdeck

Summary: 0 errors, 3 warnings, 3 total

## Violations

| Severity | Rule | Path | Message | Fixable | Applied |
|---------|------|------|---------|---------|---------|
| warn | python.module_docstring | /home/graham/workspace/experiments/pi-mono/.pi/skills/agents-registry/agents_registry/__init__.py | Missing module docstring. | true | false |
| warn | naming.noun_only | /home/graham/workspace/experiments/pi-mono/.pi/skills/agents-registry/SKILL.md | Skill name 'agents-registry' appears noun-only; consider a verb- prefix or add to _NOUN_ALLOWLIST. | false | false |
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/agents-registry/agents_registry/cli.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
