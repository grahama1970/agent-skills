# Skills CI Report: ops-arango

Root: `/home/graham/workspace/experiments/pi-mono/.pi/skills`
Mode: `scan`
Timestamp: `2026-02-11T07:00:04.273533+00:00`

Best practices: best-practices-python, best-practices-react, best-practices-skills

Summary: 0 errors, 2 warnings, 2 total

## Violations

| Severity | Rule | Path | Message | Fixable | Applied |
|---------|------|------|---------|---------|---------|
| warn | python.requests | /home/graham/workspace/experiments/pi-mono/.pi/skills/ops-arango/scripts/maintain.py | Uses requests; prefer httpx. | true | false |
| warn | python.argparse | /home/graham/workspace/experiments/pi-mono/.pi/skills/ops-arango/scripts/maintain.py | Uses argparse; prefer Typer. | false | false |
