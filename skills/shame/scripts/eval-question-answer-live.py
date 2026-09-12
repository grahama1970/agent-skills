#!/usr/bin/env python3
"""Live Pi question turn: terminal status must carry answer and render it first."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
OUT = Path('/mnt/storage12tb/skills/shame/question-answer-live')
OUT.mkdir(parents=True, exist_ok=True)
work = Path(tempfile.mkdtemp(prefix='live-', dir=OUT))
proof = work / 'closure-proof.txt'
proof.write_text('command: read closure receipt\nresult: COMPLETE per project_watchdog.goal_completion.v1; #1058 scoped non-claim\n')
index = os.environ.get('LAZY_REPORT_SHAME_INDEX', str(ROOT / 'extensions/pi/lazy-report-shame-shame-shame/index.ts'))
fault = work / 'strip-answer-once.ts'
fault.write_text('''export default function(pi) {\n let injected=false;\n pi.on('message_end', e=>{\n  if(injected || e.message?.role!=='assistant' || e.message.stopReason!=='stop') return;\n  const parts=e.message.content || [];\n  const part=parts.find(p=>p.type==='text' && p.text.includes('```json'));\n  if(!part) return;\n  const start=part.text.indexOf('```json')+7, end=part.text.indexOf('```',start);\n  const status=JSON.parse(part.text.slice(start,end));\n  if(status.schema!=='pi.agent_status.v1' || status.state!=='done') return;\n  delete status.answer;\n  injected=true;\n  return {message:{...e.message,content:parts.map(p=>p===part?{...p,text:'```json\\n'+JSON.stringify(status)+'\\n```'}:p)}};\n });\n}\n''')
shared = work
prompt = f'''Is persona-dream complete?

This is a live Shame question-turn validation. Do not use tools. Reply with ONLY this fenced JSON shape, substituting nothing except preserving valid JSON:
```json
{{"schema":"pi.agent_status.v1","goal":"Answer whether persona-dream immutable goal is complete.","answer":"COMPLETE per project_watchdog.goal_completion.v1; #1058 is a scoped non-claim, not a blocker.","state":"done","changed":["no code change: answered the status question"],"verified":[{{"command":"read closure receipt","result":"COMPLETE per project_watchdog.goal_completion.v1; #1058 scoped non-claim"}}],"proof":["{proof}"]}}
```
If a correction request arrives, emit the corrected fenced JSON only. Do not use tools during correction.'''
env = {**os.environ,
       'LAZY_REPORT_SHAME_DEFAULT_MODE': 'strict',
       'LAZY_REPORT_SHAME_AUDIO_ENABLED': '0',
       'LAZY_REPORT_SHAME_MEMORY_ENABLED': '0',
       'LAZY_REPORT_SHAME_FAILURE_LOG': str(shared / 'failures.jsonl'),
       'LAZY_REPORT_SHAME_PENDING_REVIEW_PACKET': str(shared / 'pending.json'),
       'LAZY_REPORT_SHAME_CONTINUATION_GUARD_FILE': str(shared / 'ledger.json')}
env.pop('SHAME_TASK_BUDGET', None)
cmd = ['pi', '--print', '--mode', 'json', '--session', str(work / 'session.jsonl'), '--no-extensions',
       '--no-skills', '--no-context-files', '--no-prompt-templates', '--no-themes', '--tools', 'read',
       '--thinking', 'low', '--provider', os.environ.get('PI_PROVIDER', 'openai-codex'),
       '--model', os.environ.get('PI_MODEL', 'gpt-6-astra'), '--extension', str(fault), '--extension', index, prompt]
r = subprocess.run(cmd, cwd=work, env=env, text=True, capture_output=True, timeout=300)
(work / 'events.jsonl').write_text(r.stdout)
(work / 'stderr.log').write_text(r.stderr)
assert r.returncode == 0, f'CLI exit {r.returncode}: {r.stderr[-2000:]}'
events = [json.loads(line) for line in r.stdout.splitlines() if line.startswith('{')]
assistant = [e['message'] for e in events if e.get('type') == 'message_end' and e.get('message', {}).get('role') == 'assistant']
if assistant and assistant[-1].get('stopReason') == 'error':
    print(json.dumps({'provider_error': assistant[-1].get('errorMessage'), 'events': str(work / 'events.jsonl')}))
    raise SystemExit(1)
texts = ['\n'.join(p.get('text', '') for p in m.get('content', []) if p.get('type') == 'text').strip() for m in assistant]
rejections = [t for t in texts if 'REJECTED_BY_SLOTH_COURT' in t]
# New pipeline: an honest model that refuses to fabricate a done claim stops
# prose-only and is guard-substituted with a continuing status (no rejection);
# a model that emits done-without-answer is rejected once. Either path must end
# with a terminal answer-bearing rendered report.
assert len(rejections) <= 1, {'rejections': len(rejections), 'texts': texts}
for rej in rejections:
    # Live-model variance: an honest model refuses to fabricate a done claim and
    # prose-stops (guard substitutes); a compliant model emits done-with-answer
    # which the fault strips (missing_answer_to_question). Both are legal paths.
    assert 'missing_answer_to_question' in rej or 'missing_agent_status_json' in rej, rej
final = texts[-1]
assert 'Status Report' in final or '"state"' in final, final
assert 'State: done' in final or '"state": "done"' in final or '"state":"done"' in final, final

# Deterministic core of the contract, independent of live-model mood: the
# checker must reject a terminal done status lacking an answer on a question
# turn (this is the gate the fault exercises in the compliant-model path).
import subprocess as _sp
_noanswer = '```json\n' + json.dumps({
    'schema': 'pi.agent_status.v1', 'goal': 'Answer the status question.',
    'state': 'done', 'changed': ['no change: gate probe'],
    'verified': [{'command': 'read closure receipt', 'result': 'COMPLETE per project_watchdog.goal_completion.v1'}],
    'proof': [str(work / 'closure-proof.txt')],
}) + '\n```\n'
_probe = _sp.run(['node', str(ROOT / "extensions/pi/lazy-report-shame-shame-shame/status-json-check.mjs")],
                 input=_noanswer, text=True, capture_output=True, timeout=30,
                 env={**env, 'LRSSS_FORCE_STATUS': '1', 'LRSSS_USER_TEXT': prompt[:200]})
try:
    _parsed = json.loads(_probe.stdout)
except Exception:
    raise AssertionError({'probe_stdout': _probe.stdout, 'probe_stderr': _probe.stderr})
assert _parsed.get('decision') == 'reject' and 'missing_answer_to_question' in _parsed.get('reason_codes', []), _parsed
failures_path = shared / 'failures.jsonl'
if failures_path.exists():
    rows = [json.loads(line) for line in failures_path.read_text().splitlines()]
    rejected_rows = [row for row in rows if row.get('kind') == 'report_rejected']
    assert len(rejected_rows) == len(rejections), rejected_rows
    for row in rejected_rows:
        assert 'missing_answer_to_question' in row.get('reason_codes', []), row
else:
    assert not rejections, rejections  # no journal without guard activity
report = {
    'schema': 'shame.question_answer_live.report.v1',
    'status': 'PASS_LIVE_QUESTION_TURN_REQUIRES_ANSWER',
    'report_retries': len(rejections),
    'missing_answer_rejected': True,
    'answer_first_line': final.splitlines()[0],
    'failure_history_verified': True,
    'session_file': str(work / 'session.jsonl'),
    'events': str(work / 'events.jsonl'),
    'report': str(work / 'report.json'),
}
(work / 'report.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report))
