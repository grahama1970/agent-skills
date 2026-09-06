#!/usr/bin/env python3
"""Exercise the production Pi CLI + shame extension with a live model.

Only fixture inputs are local numbers; no provider response or tool result is
mocked. Independently reads output bytes and the real Pi event stream.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[3]
OUT = Path('/mnt/storage12tb/skills/shame/stop-boundary-eval')
OUT.mkdir(parents=True, exist_ok=True)
work = Path(tempfile.mkdtemp(prefix='live-', dir=OUT))
continuations = '--continuations' in sys.argv
values = [secrets.randbelow(900) + 100 for _ in range(7 if continuations else 4)]
inputs = []
for i, value in enumerate(values):
    path = work / f'number-{i}.txt'
    path.write_text(str(value))
    inputs.append(str(path))
output = work / 'sum.json'
index = os.environ.get('LAZY_REPORT_SHAME_INDEX', str(ROOT / 'extensions/pi/lazy-report-shame-shame-shame/index.ts'))
prompt = f'''Read these {len(values)} files, each in a separate read tool call: {json.dumps(inputs)}.
Include a short progress text alongside each tool-calling response. Do not emit status JSON while calling tools.
After reading all files, use write to create {output} containing JSON with keys values (all integers in order) and sum (their total).
Then stop with ONLY one fenced json block: {{"schema":"pi.agent_status.v1","goal":"live sum probe","state":"done","changed":["summed four files"],"verified":[{{"command":"sum","result":"<actual total as a string>"}}],"proof":["{output}"]}}.
Do not stop before writing the sum file. Do not modify any other file.'''
if continuations:
    prompt += '''
Lifecycle test exception to the previous no-stop sentence: after EACH of the first SIX reads, stop that model response with a continuing status before reading the next file. Pi will automatically send the next command. This is deliberate, not completion.
Use exactly this data shape, substituting the index and next path:
```json
{"schema":"pi.agent_status.v1","goal":"live sum probe","state":"continuing","changed":["read file <index>"],"not_done":[{"item":"read next file","next_command":"Read <next absolute path>, then follow the original lifecycle instructions. After the seventh read write the sum file and emit the final done status."}]}
```
Emit no status JSON in a response that also calls a tool. Only after the seventh read write the sum file and emit done. Keep all earlier values for the final sum.'''
if '--repeat-status' in sys.argv:
    assert continuations, '--repeat-status requires --continuations'
    prompt += '''
For each of the SIX continuing stops, emit this EXACT same block without edits or extra prose (the command intentionally remains identical; choose the next unread input from context):
```json
{"schema":"pi.agent_status.v1","goal":"live sum probe","state":"continuing","changed":["another input read; remaining work"],"not_done":[{"item":"finish reading inputs","next_command":"Read the next unread numbered input from the original list; after the seventh read write the sum file and emit done."}]}
```
'''
fault_kind = next((kind for flag, kind in [('--missing-footer', 'missing-footer'), ('--duplicate-key', 'duplicate-key'), ('--missing-verified', 'missing-verified'), ('--misleading-prose', 'misleading-prose'), ('--proof-repair', 'proof')] if flag in sys.argv), None)
repair_proof = fault_kind is not None and fault_kind != 'misleading-prose'
if fault_kind:
    prompt += '\nA test transport will alter your first status report. If a correction arrives, use the already observed values and output path to correct the status only. Do not call any tools during report repair. Never fabricate evidence.'
    # Corrupt exactly one real terminal message rather than asking the model
    # to fabricate a completion claim. The recovery still uses the live model.
    fault = work / 'fault.ts'
    fault.write_text('''import {writeFileSync} from 'node:fs';
export default function(pi) {
 let injected=false;
 pi.on('message_end', e=>{
  if(injected || e.message?.role!=='assistant' || e.message.stopReason!=='stop') return;
  const parts=e.message.content;
  const part=parts.find(p=>p.type==='text' && p.text.includes('```json'));
  if(!part) return;
  const start=part.text.indexOf('```json')+7, end=part.text.indexOf('```',start);
  const status=JSON.parse(part.text.slice(start,end));
  if(status.state!=='done') return;
  injected=true;
  const mode=process.env.SHAME_EVAL_FAULT;
  if(mode==='proof') status.proof=['https://shame.invalid/'+encodeURIComponent(process.cwd())];
  if(mode==='missing-verified') status.verified=[];
  let body=JSON.stringify(status);
  if(mode==='duplicate-key') body=body.replace('"schema":"pi.agent_status.v1"','"schema":"pi.agent_status.v1","schema":"pi.agent_status.v1"');
  const prefix=mode==='misleading-prose'?'Status Report\\n- Goal: unrelated\\n- State: failed\\n':'';
  writeFileSync('fault.json',JSON.stringify({injected:true,mode}));
  const text=mode==='missing-footer'?'Result ready.':prefix+'```json\\n'+body+'\\n```';
  return {message:{...e.message,content:parts.map(p=>p===part?{...p,text}:p)}};
 });
}''')
shared = Path(os.environ.get('SHAME_EVAL_SHARED_ROOT', str(work)))
shared.mkdir(parents=True, exist_ok=True)
env = {**os.environ, 'SHAME_EVAL_FAULT': fault_kind or '', 'LAZY_REPORT_SHAME_DEFAULT_MODE': 'normal' if '--normal' in sys.argv else 'strict',
       'LAZY_REPORT_SHAME_FAILURE_LOG': str(shared / 'failures.jsonl'),
       'LAZY_REPORT_SHAME_AUDIO_ENABLED': '0', 'LAZY_REPORT_SHAME_MEMORY_ENABLED': '0',
       'LAZY_REPORT_SHAME_PENDING_REVIEW_PACKET': str(shared / 'pending.json'),
       'LAZY_REPORT_SHAME_CONTINUATION_GUARD_FILE': str(work / 'ledger.json')}
command = ['pi', '--print', '--mode', 'json', '--session', str(work / 'session.jsonl'), '--no-extensions',
           '--no-skills', '--no-context-files', '--no-prompt-templates', '--no-themes',
           '--extension', index, '--tools', 'read,write', '--thinking', 'low',
           '--provider', os.environ.get('PI_PROVIDER', 'openai-codex'),
           '--model', os.environ.get('PI_MODEL', 'gpt-6-astra'), prompt]
if fault_kind:
    position=command.index('--extension')
    command[position:position]=['--extension', str(fault)]
result = subprocess.run(command, cwd=work, env=env, capture_output=True, text=True, timeout=180)
(work / 'events.jsonl').write_text(result.stdout)
(work / 'stderr.log').write_text(result.stderr)
assert result.returncode == 0, f'CLI exit {result.returncode}: {result.stderr[-2000:]}'
events = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
messages = [e['message'] for e in events if e.get('type') == 'message_end']
assistant = [m for m in messages if m.get('role') == 'assistant']
if assistant and assistant[-1].get('stopReason') == 'error':
    print(json.dumps({'provider_error': assistant[-1].get('errorMessage'), 'events': str(work / 'events.jsonl')}))
    raise SystemExit(1)
tool_messages = [m for m in assistant if any(p.get('type') == 'toolCall' for p in m.get('content', []))]
mixed = [m for m in tool_messages if any(p.get('type') == 'text' and p.get('text', '').strip() for p in m['content'])]
assert len(tool_messages) >= 5, 'missing separate live read/write calls'
assert mixed, 'live model did not exercise mixed text/tool-call seam'
session_id = json.loads((work / 'session.jsonl').read_text().splitlines()[0])['id']
packet_exists = (shared / 'pending.json').exists() or (shared / 'pending.json.sessions').exists()
assert packet_exists == repair_proof, 'unexpected pending rejection packet state'
if fault_kind:
    assert json.loads((work / 'fault.json').read_text())['injected'] is True
actual = json.loads(output.read_text())
assert actual['values'] == values and actual['sum'] == sum(values), (actual, values)
continuation_count = sum('State: continuing' in '\n'.join(p.get('text', '') for p in m.get('content', [])) for m in assistant)
if continuations:
    assert continuation_count == 6, f'expected six completed continuations, got {continuation_count}'
if '--repeat-status' in sys.argv:
    rendered = ['\n'.join(p.get('text', '') for p in m.get('content', [])) for m in assistant]
    continued = [t.strip() for t in rendered if 'State: continuing' in t]
    assert len(set(continued)) == 1, 'live run did not exercise byte-identical repeated continuation reports'
last_text = '\n'.join(p.get('text', '') for p in assistant[-1].get('content', []))
assert 'State: done' in last_text, last_text
if fault_kind == 'misleading-prose':
    assert 'State: failed' not in last_text and 'Goal: unrelated' not in last_text, last_text
rejections = sum(any('REJECTED_BY_SLOTH_COURT' in p.get('text', '') for p in m.get('content', [])) for m in assistant)
assert rejections == (1 if repair_proof else 0), f'unexpected reporting repairs: {rejections}'
if repair_proof:
    rejected_at = next(i for i, m in enumerate(assistant) if any('REJECTED_BY_SLOTH_COURT' in p.get('text', '') for p in m.get('content', [])))
    assert not any(p.get('type') == 'toolCall' for m in assistant[rejected_at + 1:] for p in m.get('content', [])), 'format correction reopened tool execution'
history_verified = False
if repair_proof:
    rows = [json.loads(line) for line in (shared / 'failures.jsonl').read_text().splitlines()]
    rejected = [row for row in rows if row['kind'] == 'report_rejected' and row['session_id'] == session_id]
    reason = {'missing-footer':'missing_agent_status_json','proof':'proof_reference_unresolved','duplicate-key':'duplicate_agent_status_key','missing-verified':'done_requires_verified'}[fault_kind]
    assert len(rejected) == 1 and reason in rejected[0]['reason_codes'], rejected
    snapshot = json.loads(Path(rejected[0]['review_packet']).read_text())
    assert snapshot['candidate_hash'] == rejected[0]['candidate_hash']
    reader = subprocess.run(['node', str(Path(index).with_name('failure-history.mjs')), '--session-id', rejected[0]['session_id'], '--json'], env=env, text=True, capture_output=True, timeout=10)
    assert reader.returncode == 0
    assert any(row['event_id'] == rejected[0]['event_id'] for row in json.loads(reader.stdout)['events'])
    history_verified = True
report = {'fault': fault_kind, 'session_id': session_id, 'session_file': str(work / 'session.jsonl'), 'failure_history_verified': history_verified, 'live_model': env.get('PI_MODEL', 'gpt-6-astra'), 'tool_messages': len(tool_messages),
          'mixed_text_tool_messages': len(mixed), 'report_retries': rejections, 'continuations': continuation_count,
          'sum_readback_correct': True, 'done_rendered': True,
          'events': str(work / 'events.jsonl'), 'output': str(output)}
receipt = work / 'report.json'
receipt.write_text(json.dumps(report, indent=2))
print(json.dumps({**report, 'report': str(receipt)}))
