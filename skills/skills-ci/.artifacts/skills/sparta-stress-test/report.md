# Skills CI Report: sparta-stress-test

Root: `/home/graham/workspace/experiments/pi-mono/.pi/skills`
Mode: `scan`
Timestamp: `2026-03-05T07:00:30.302246+00:00`

Best practices: best-practices-kde, best-practices-plan, best-practices-python, best-practices-react, best-practices-skills, best-practices-streamdeck

Summary: 0 errors, 23 warnings, 23 total

## Violations

| Severity | Rule | Path | Message | Fixable | Applied |
|---------|------|------|---------|---------|---------|
| warn | python.argparse | /home/graham/workspace/experiments/pi-mono/.pi/skills/sparta-stress-test/scripts/harvest_skill_chains.py | Uses argparse; prefer Typer. | false | false |
| warn | python.file_length | /home/graham/workspace/experiments/pi-mono/.pi/skills/sparta-stress-test/sparta_stress_test/semantic_grader.py | File exceeds 900 LOC (1090). | false | false |
| warn | python.file_length | /home/graham/workspace/experiments/pi-mono/.pi/skills/sparta-stress-test/sparta_stress_test/cli.py | File exceeds 900 LOC (1146). | false | false |
| warn | python.file_length | /home/graham/workspace/experiments/pi-mono/.pi/skills/sparta-stress-test/sparta_stress_test/conversation_runner.py | File exceeds 900 LOC (1043). | false | false |
| warn | subprocess.stderr_fatal | /home/graham/workspace/experiments/pi-mono/.pi/skills/sparta-stress-test/sparta_stress_test/runner.py | Treats stderr as fatal error — uv/pip emit warnings to stderr that are not errors. Check returncode instead. | false | false |
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/sparta-stress-test/sparta_stress_test/conversation_steering.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
| warn | subprocess.raw_aql | /home/graham/workspace/experiments/pi-mono/.pi/skills/sparta-stress-test/sparta_stress_test/conversation_steering.py | Direct ArangoDB AQL execution — must use /memory skill instead. | false | false |
| warn | subprocess.raw_aql | /home/graham/workspace/experiments/pi-mono/.pi/skills/sparta-stress-test/sparta_stress_test/enrich_f36_taxonomy.py | Direct ArangoDB AQL execution — must use /memory skill instead. | false | false |
| warn | subprocess.raw_aql | /home/graham/workspace/experiments/pi-mono/.pi/skills/sparta-stress-test/sparta_stress_test/retrieval.py | Direct ArangoDB AQL execution — must use /memory skill instead. | false | false |
| warn | subprocess.raw_aql | /home/graham/workspace/experiments/pi-mono/.pi/skills/sparta-stress-test/sparta_stress_test/semantic_grader.py | Direct ArangoDB AQL execution — must use /memory skill instead. | false | false |
| warn | subprocess.raw_aql | /home/graham/workspace/experiments/pi-mono/.pi/skills/sparta-stress-test/sparta_stress_test/conversation_retrieval.py | Direct ArangoDB AQL execution — must use /memory skill instead. | false | false |
| warn | subprocess.raw_aql | /home/graham/workspace/experiments/pi-mono/.pi/skills/sparta-stress-test/sparta_stress_test/question_miner.py | Direct ArangoDB AQL execution — must use /memory skill instead. | false | false |
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/sparta-stress-test/sparta_stress_test/routing.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
| warn | subprocess.raw_aql | /home/graham/workspace/experiments/pi-mono/.pi/skills/sparta-stress-test/sparta_stress_test/routing.py | Direct ArangoDB AQL execution — must use /memory skill instead. | false | false |
| warn | subprocess.raw_aql | /home/graham/workspace/experiments/pi-mono/.pi/skills/sparta-stress-test/sparta_stress_test/response_quality.py | Direct ArangoDB AQL execution — must use /memory skill instead. | false | false |
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/sparta-stress-test/sparta_stress_test/session_runner.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
| warn | subprocess.raw_aql | /home/graham/workspace/experiments/pi-mono/.pi/skills/sparta-stress-test/sparta_stress_test/question_bank.py | Direct ArangoDB AQL execution — must use /memory skill instead. | false | false |
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/sparta-stress-test/sparta_stress_test/conversation_runner.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
| warn | subprocess.venv_leak | /home/graham/workspace/experiments/pi-mono/.pi/skills/sparta-stress-test/sparta_stress_test/persona_synthesis_runner.py | Subprocess calls skill run.sh without stripping VIRTUAL_ENV — breaks in scheduler context. | false | false |
| warn | subprocess.stderr_fatal | /home/graham/workspace/experiments/pi-mono/.pi/skills/sparta-stress-test/sparta_stress_test/persona_synthesis_runner.py | Treats stderr as fatal error — uv/pip emit warnings to stderr that are not errors. Check returncode instead. | false | false |
| warn | subprocess.raw_aql | /home/graham/workspace/experiments/pi-mono/.pi/skills/sparta-stress-test/sparta_stress_test/question_quality.py | Direct ArangoDB AQL execution — must use /memory skill instead. | false | false |
| warn | subprocess.raw_aql | /home/graham/workspace/experiments/pi-mono/.pi/skills/sparta-stress-test/sparta_stress_test/entity_classifier/extractor.py | Direct ArangoDB AQL execution — must use /memory skill instead. | false | false |
| warn | subprocess.raw_aql | /home/graham/workspace/experiments/pi-mono/.pi/skills/sparta-stress-test/sparta_stress_test/entity_classifier/validator.py | Direct ArangoDB AQL execution — must use /memory skill instead. | false | false |
