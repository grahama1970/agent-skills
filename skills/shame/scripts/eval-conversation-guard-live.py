#!/usr/bin/env python3
"""Live Pi advisory/format-repair regression; no repository mutations or checks."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

mode = sys.argv[1] if len(sys.argv) > 1 else 'advisory'
assert mode in {'advisory', 'repair'}
root = Path(__file__).resolve().parents[3]
out = Path('/mnt/storage12tb/skills/shame/conversation-fix')
out.mkdir(parents=True, exist_ok=True)
work = Path(tempfile.mkdtemp(prefix=mode+'-', dir=out))
index = os.environ.get('LAZY_REPORT_SHAME_INDEX', str(root / 'extensions/pi/lazy-report-shame-shame-shame/index.ts'))
env = {**os.environ, 'LAZY_REPORT_SHAME_DEFAULT_MODE': 'normal', 'LAZY_REPORT_SHAME_AUDIO_ENABLED': '0', 'LAZY_REPORT_SHAME_MEMORY_ENABLED': '0', 'LAZY_REPORT_SHAME_FAILURE_LOG': str(work/'failures.jsonl'), 'LAZY_REPORT_SHAME_PENDING_REVIEW_PACKET': str(work/'pending.json'), 'LAZY_REPORT_SHAME_CONTINUATION_GUARD_FILE': str(work/'no-ledger')}
env.pop('SHAME_TASK_BUDGET', None)
argv = ['pi','--print','--mode','json','--no-session','--no-extensions','--no-skills','--no-context-files','--no-prompt-templates','--no-themes','--tools','read','--thinking','low','--provider',os.environ['PI_PROVIDER'],'--model',os.environ['PI_MODEL']]
if mode == 'advisory':
    prompt = 'This is an advisory question about $shame, $project-watchdog and $ticket, not an execution task. Answer exactly ADVISORY_OK. Do not use tools or supply a status report.'
else:
    status = {'schema':'pi.agent_status.v1','goal':'formatting-only diagnostic example','state':'needs_human','changed':['no change: diagnostic example'],'needs_human':{'action':'Choose A or B.','reason':'This is a controlled diagnostic example.'}}
    prompt = '$shame\nReturn only this exact object in a fenced json block. Do not call tools. If transport corruption causes a correction request, return the same object again, without tools.\n'+json.dumps(status)
    fault = work/'fault.mjs'
    fault.write_text("export default function(pi){let once=false;pi.on('message_end',e=>{if(once||e.message?.role!=='assistant'||e.message.stopReason!=='stop')return;once=true;return {message:{...e.message,content:[{type:'text',text:'Transport removed the status block.'}]}};});}")
    argv += ['--extension',str(fault)]
argv += ['--extension',index,prompt]
r = subprocess.run(argv, cwd=work, env=env, text=True, capture_output=True, timeout=120)
(work/'events.jsonl').write_text(r.stdout); (work/'stderr.log').write_text(r.stderr)
assert r.returncode == 0, r.stderr[-1500:]
events = [json.loads(l) for l in r.stdout.splitlines() if l.startswith('{')]
messages = [e['message'] for e in events if e.get('type')=='message_end' and e['message'].get('role')=='assistant']
if messages and messages[-1].get('stopReason')=='error':
    print(json.dumps({'provider_error':messages[-1].get('errorMessage'),'events':str(work/'events.jsonl')})); raise SystemExit(1)
texts = ['\n'.join(p.get('text','') for p in m.get('content',[])).strip() for m in messages]
tools = [p for m in messages for p in m.get('content',[]) if p.get('type')=='toolCall']
assert not tools, f'conversation/format repair called tools: {tools}'
rows = [json.loads(l) for l in (work/'failures.jsonl').read_text().splitlines()] if (work/'failures.jsonl').exists() else []
rejected = [e for e in rows if e.get('kind')=='report_rejected']
if mode == 'advisory':
    assert texts == ['ADVISORY_OK'], texts
    assert not rejected, rejected
else:
    assert len(texts)==2 and 'REJECTED_BY_SLOTH_COURT' in texts[0] and 'State: needs_human' in texts[1], texts
    assert len(rejected)==1, rejected
report = {'mode':mode,'assistant_responses':len(texts),'rejections':len(rejected),'tool_calls':len(tools),'advisory_passed':mode=='advisory','single_repair_passed':mode=='repair','events':str(work/'events.jsonl')}
(work/'report.json').write_text(json.dumps(report,indent=2)); print(json.dumps({**report,'report':str(work/'report.json')}))
