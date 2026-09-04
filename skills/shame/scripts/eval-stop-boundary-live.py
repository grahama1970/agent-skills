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
env = {**os.environ, 'LAZY_REPORT_SHAME_DEFAULT_MODE': 'strict',
       'LAZY_REPORT_SHAME_AUDIO_ENABLED': '0', 'LAZY_REPORT_SHAME_MEMORY_ENABLED': '0',
       'LAZY_REPORT_SHAME_PENDING_REVIEW_PACKET': str(work / 'pending.json'),
       'LAZY_REPORT_SHAME_CONTINUATION_GUARD_FILE': str(work / 'ledger.json')}
command = ['pi', '--print', '--mode', 'json', '--no-session', '--no-extensions',
           '--no-skills', '--no-context-files', '--no-prompt-templates', '--no-themes',
           '--extension', index, '--tools', 'read,write', '--thinking', 'low',
           '--provider', os.environ.get('PI_PROVIDER', 'openai-codex'),
           '--model', os.environ.get('PI_MODEL', 'gpt-6-astra'), prompt]
result = subprocess.run(command, cwd=work, env=env, capture_output=True, text=True, timeout=180)
(work / 'events.jsonl').write_text(result.stdout)
(work / 'stderr.log').write_text(result.stderr)
assert result.returncode == 0, f'CLI exit {result.returncode}: {result.stderr[-2000:]}'
events = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
messages = [e['message'] for e in events if e.get('type') == 'message_end']
assistant = [m for m in messages if m.get('role') == 'assistant']
tool_messages = [m for m in assistant if any(p.get('type') == 'toolCall' for p in m.get('content', []))]
mixed = [m for m in tool_messages if any(p.get('type') == 'text' and p.get('text', '').strip() for p in m['content'])]
assert len(tool_messages) >= 5, 'missing separate live read/write calls'
assert mixed, 'live model did not exercise mixed text/tool-call seam'
assert not (work / 'pending.json').exists(), 'intermediate or final output triggered rejection'
actual = json.loads(output.read_text())
assert actual['values'] == values and actual['sum'] == sum(values), (actual, values)
continuation_count = sum('State: continuing' in '\n'.join(p.get('text', '') for p in m.get('content', [])) for m in assistant)
if continuations:
    assert continuation_count == 6, f'expected six completed continuations, got {continuation_count}'
last_text = '\n'.join(p.get('text', '') for p in assistant[-1].get('content', []))
assert 'State: done' in last_text, last_text
assert 'REJECTED_BY_SLOTH_COURT' not in result.stdout, 'live run exhausted/used report repair'
report = {'live_model': env.get('PI_MODEL', 'gpt-6-astra'), 'tool_messages': len(tool_messages),
          'mixed_text_tool_messages': len(mixed), 'report_retries': 0, 'continuations': continuation_count,
          'sum_readback_correct': True, 'done_rendered': True,
          'events': str(work / 'events.jsonl'), 'output': str(output)}
receipt = work / 'report.json'
receipt.write_text(json.dumps(report, indent=2))
print(json.dumps({**report, 'report': str(receipt)}))
