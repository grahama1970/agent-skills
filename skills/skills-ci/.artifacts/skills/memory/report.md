# Skills CI Report: memory

Root: `/home/graham/workspace/experiments/pi-mono/.pi/skills`
Mode: `scan`
Timestamp: `2026-03-05T07:00:30.302246+00:00`

Best practices: best-practices-kde, best-practices-plan, best-practices-python, best-practices-react, best-practices-skills, best-practices-streamdeck

Summary: 0 errors, 14 warnings, 14 total

## Violations

| Severity | Rule | Path | Message | Fixable | Applied |
|---------|------|------|---------|---------|---------|
| warn | subprocess.raw_aql | /home/graham/workspace/experiments/pi-mono/.pi/skills/memory/preset_storage.py | Direct ArangoDB AQL execution — must use /memory skill instead. | false | false |
| warn | subprocess.raw_aql | /home/graham/workspace/experiments/pi-mono/.pi/skills/memory/horus_lore_enrichment.py | Direct ArangoDB AQL execution — must use /memory skill instead. | false | false |
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/memory/persona_journal.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
| warn | subprocess.raw_aql | /home/graham/workspace/experiments/pi-mono/.pi/skills/memory/persona_journal.py | Direct ArangoDB AQL execution — must use /memory skill instead. | false | false |
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/memory/persona_journal_memory.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
| warn | subprocess.raw_aql | /home/graham/workspace/experiments/pi-mono/.pi/skills/memory/persona_journal_memory.py | Direct ArangoDB AQL execution — must use /memory skill instead. | false | false |
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/memory/persona_journal_db.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
| warn | subprocess.raw_aql | /home/graham/workspace/experiments/pi-mono/.pi/skills/memory/persona_journal_db.py | Direct ArangoDB AQL execution — must use /memory skill instead. | false | false |
| warn | subprocess.raw_aql | /home/graham/workspace/experiments/pi-mono/.pi/skills/memory/horus_lore_query.py | Direct ArangoDB AQL execution — must use /memory skill instead. | false | false |
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/memory/recreation_queue.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
| warn | subprocess.raw_aql | /home/graham/workspace/experiments/pi-mono/.pi/skills/memory/horus_lore_storage.py | Direct ArangoDB AQL execution — must use /memory skill instead. | false | false |
| warn | subprocess.raw_aql | /home/graham/workspace/experiments/pi-mono/.pi/skills/memory/horus_lore_cli.py | Direct ArangoDB AQL execution — must use /memory skill instead. | false | false |
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/memory/memory_quality_scorer.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
| warn | subprocess.raw_aql | /home/graham/workspace/experiments/pi-mono/.pi/skills/memory/simulacrum_retrieval.py | Direct ArangoDB AQL execution — must use /memory skill instead. | false | false |
