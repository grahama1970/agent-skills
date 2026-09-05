#!/usr/bin/env python3
"""Live Pi task-budget run with an independently checked artifact; no mocked model."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
OUT = Path('/mnt/storage12tb/skills/shame/harness-budget')
OUT.mkdir(parents=True, exist_ok=True)
work = Path(tempfile.mkdtemp(prefix='live-', dir=OUT))
values = [secrets.randbelow(1000) for _ in range(4)]
(work / 'inputs.json').write_text(json.dumps(values))
oracle = work / 'oracle.py'
oracle.write_text("import json\nfrom pathlib import Path\nv=json.loads(Path('inputs.json').read_text())\na=json.loads(Path('candidate.json').read_text())\nassert a['sum']==sum(v),(a,v)\nprint('sum-verified='+str(a['sum']))\n")
contract = work / 'contract.json'
contract.write_text(json.dumps({'schema': 'pi.task_budget.v1', 'mode': 'task', 'deliverable': 'Write candidate.json with the sum of inputs.json', 'allowed_paths': ['candidate.json'], 'elapsed_ms': 150000, 'checks': [{'id': 'verify', 'argv': [sys.executable, str(oracle)], 'inputs': ['candidate.json', 'inputs.json'], 'definition_files': ['oracle.py'], 'timeout_ms': 5000}]}))
prompt = '''One deliverable: read inputs.json and write candidate.json containing {"sum": <total of the four numbers>}.
Only candidate.json may be written. Required check: call task_check with id="verify" once after writing; no Bash or other checks/reviews.
After task_check reports phase=accepted, use NO MORE TOOLS. Final answer must be a fenced JSON object with schema pi.agent_status.v1, goal "Write candidate.json with the sum of inputs.json", state done, changed ["wrote the verified sum"], verified [{"command": <the exact command returned by task_check>, "result": <the exact result returned by task_check>}], proof [<the receipt path returned by task_check>], not_done [].
Include brief progress text alongside tool-calling messages but no status JSON until final. Do not perform any further project work.'''
index = os.environ.get('LAZY_REPORT_SHAME_INDEX', str(ROOT / 'extensions/pi/lazy-report-shame-shame-shame/index.ts'))
env = {**os.environ, 'SHAME_TASK_BUDGET': str(contract), 'SHAME_TASK_RECEIPT_DIR': str(work / 'receipts'), 'LAZY_REPORT_SHAME_AUDIO_ENABLED': '0', 'LAZY_REPORT_SHAME_MEMORY_ENABLED': '0', 'LAZY_REPORT_SHAME_CONTINUATION_GUARD_FILE': str(work / 'no-ledger'), 'LAZY_REPORT_SHAME_PENDING_REVIEW_PACKET': str(work / 'pending')}
argv = ['pi', '--print', '--mode', 'json', '--no-session', '--no-extensions', '--no-skills', '--no-context-files', '--no-prompt-templates', '--no-themes', '--extension', index, '--tools', 'read,write,task_check', '--provider', os.environ['PI_PROVIDER'], '--model', os.environ['PI_MODEL'], '--thinking', 'low', prompt]
run = subprocess.run(argv, cwd=work, env=env, text=True, capture_output=True, timeout=180)
(work / 'events.jsonl').write_text(run.stdout)
(work / 'stderr.log').write_text(run.stderr)
assert run.returncode == 0, run.stderr[-3000:]
events = [json.loads(l) for l in run.stdout.splitlines() if l.startswith('{')]
messages = [e['message'] for e in events if e.get('type') == 'message_end']
checks = [m for m in messages if m.get('role') == 'toolResult' and m.get('toolName') == 'task_check']
assert len(checks) == 1, f'expected exactly one approved check, got {len(checks)}'
check = json.loads(checks[0]['content'][0]['text'])
assert check['phase'] == 'accepted' and check['passed'] is True, check
receipt = json.loads(Path(check['receipt']).read_text())
assert receipt['phase'] == 'accepted' and receipt['checks']['verify']['attempts'] == 1
actual = json.loads((work / 'candidate.json').read_text())
assert actual['sum'] == sum(values), (actual, values)
last = [m for m in messages if m.get('role') == 'assistant'][-1]
assert 'State: done' in '\n'.join(p.get('text', '') for p in last['content']), last
accepted_at = messages.index(checks[0])
assert not any(p.get('type') == 'toolCall' for m in messages[accepted_at+1:] if m.get('role') == 'assistant' for p in m.get('content', [])), 'tools called after terminal acceptance'
report = {'approved_check_runs': 1, 'accepted': True, 'output_readback_correct': True, 'post_acceptance_tool_calls': 0, 'receipt': check['receipt'], 'events': str(work / 'events.jsonl'), 'output': str(work / 'candidate.json')}
(work / 'report.json').write_text(json.dumps(report, indent=2))
print(json.dumps({**report, 'report': str(work / 'report.json')}))
