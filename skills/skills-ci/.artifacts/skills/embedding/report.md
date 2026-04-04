# Skills CI Report: embedding

Root: `/home/graham/workspace/experiments/pi-mono/.pi/skills`
Mode: `scan`
Timestamp: `2026-03-05T07:00:30.302246+00:00`

Best practices: best-practices-kde, best-practices-plan, best-practices-python, best-practices-react, best-practices-skills, best-practices-streamdeck

Summary: 0 errors, 1 warnings, 1 total

## Violations

| Severity | Rule | Path | Message | Fixable | Applied |
|---------|------|------|---------|---------|---------|
| warn | subprocess.raw_aql | /home/graham/workspace/experiments/pi-mono/.pi/skills/embedding/edge-verifier/verify_edges.py | Direct ArangoDB AQL execution — must use /memory skill instead. | false | false |
