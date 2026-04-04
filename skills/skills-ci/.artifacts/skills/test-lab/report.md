# Skills CI Report: test-lab

Root: `/home/graham/workspace/experiments/pi-mono/.pi/skills`
Mode: `scan`
Timestamp: `2026-02-20T07:00:09.590643+00:00`

Best practices: best-practices-kde, best-practices-python, best-practices-react, best-practices-skills, best-practices-streamdeck

Summary: 0 errors, 4 warnings, 4 total

## Violations

| Severity | Rule | Path | Message | Fixable | Applied |
|---------|------|------|---------|---------|---------|
| warn | python.requests | /home/graham/workspace/experiments/pi-mono/.pi/skills/test-lab/generators/python_tests.py | Uses requests; prefer httpx. | true | false |
| warn | python.argparse | /home/graham/workspace/experiments/pi-mono/.pi/skills/test-lab/generators/python_tests.py | Uses argparse; prefer Typer. | false | false |
| warn | python.logging | /home/graham/workspace/experiments/pi-mono/.pi/skills/test-lab/generators/python_tests.py | Uses logging; prefer loguru. | false | false |
| warn | naming.noun_only | /home/graham/workspace/experiments/pi-mono/.pi/skills/test-lab/SKILL.md | Skill name 'test-lab' appears noun-only; consider a verb- prefix or add to _NOUN_ALLOWLIST. | false | false |
