#!/usr/bin/env python3
"""Real Pi advisory question: one answer, no tools, no report-repair loop."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

if len(sys.argv)>1 and sys.argv[1]!='advisory':
    raise SystemExit('Use the canonical agentic_eval.json --case single-format-correction for repair coverage.')
root=Path(__file__).resolve().parents[3]
out=Path('/mnt/storage12tb/skills/shame/conversation-fix');out.mkdir(parents=True,exist_ok=True)
work=Path(tempfile.mkdtemp(prefix='advisory-',dir=out))
index=os.environ.get('LAZY_REPORT_SHAME_INDEX',str(root/'extensions/pi/lazy-report-shame-shame-shame/index.ts'))
env={**os.environ,'LAZY_REPORT_SHAME_DEFAULT_MODE':'normal','LAZY_REPORT_SHAME_AUDIO_ENABLED':'0','LAZY_REPORT_SHAME_MEMORY_ENABLED':'0','LAZY_REPORT_SHAME_FAILURE_LOG':str(work/'failures.jsonl'),'LAZY_REPORT_SHAME_PENDING_REVIEW_PACKET':str(work/'pending.json'),'LAZY_REPORT_SHAME_CONTINUATION_GUARD_FILE':str(work/'no-ledger')}
env.pop('SHAME_TASK_BUDGET',None)
prompt='This is an advisory question about $shame, $project-watchdog and $ticket, not an execution task. Answer exactly ADVISORY_OK. Do not use tools or supply a status report.'
argv=['pi','--print','--mode','json','--no-session','--no-extensions','--no-skills','--no-context-files','--no-prompt-templates','--no-themes','--tools','read','--thinking','low','--provider',os.environ['PI_PROVIDER'],'--model',os.environ['PI_MODEL'],'--extension',index,prompt]
r=subprocess.run(argv,cwd=work,env=env,text=True,capture_output=True,timeout=120)
(work/'events.jsonl').write_text(r.stdout);(work/'stderr.log').write_text(r.stderr)
assert r.returncode==0,r.stderr[-1500:]
events=[json.loads(l) for l in r.stdout.splitlines() if l.startswith('{')]
messages=[e['message'] for e in events if e.get('type')=='message_end' and e['message'].get('role')=='assistant']
if messages and messages[-1].get('stopReason')=='error':
    print(json.dumps({'provider_error':messages[-1].get('errorMessage'),'events':str(work/'events.jsonl')}));raise SystemExit(1)
texts=['\n'.join(p.get('text','') for p in m.get('content',[])).strip() for m in messages]
tools=[p for m in messages for p in m.get('content',[]) if p.get('type')=='toolCall']
assert texts==['ADVISORY_OK'] and not tools,(texts,tools)
rows=[json.loads(l) for l in (work/'failures.jsonl').read_text().splitlines()] if (work/'failures.jsonl').exists() else []
assert not rows,rows
report={'assistant_responses':1,'rejections':0,'tool_calls':0,'events':str(work/'events.jsonl')}
(work/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps({**report,'report':str(work/'report.json')}))
