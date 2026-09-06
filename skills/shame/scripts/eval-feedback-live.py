#!/usr/bin/env python3
"""Real Pi sessions -> isolated history -> capture CLI -> independent Memory readback."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import httpx

ROOT=Path(__file__).resolve().parents[3]
OUT=Path('/mnt/storage12tb/skills/shame/eval-cleanup');OUT.mkdir(parents=True,exist_ok=True)
work=Path(tempfile.mkdtemp(prefix='feedback-',dir=OUT))
env={**os.environ,'SHAME_EVAL_SHARED_ROOT':str(work),'LAZY_REPORT_SHAME_FAILURE_LOG':str(work/'failures.jsonl')}
def run(argv):
    r=subprocess.run(argv,cwd=ROOT,env=env,text=True,capture_output=True,timeout=190)
    if r.returncode:
        failure=work/'command-failure.json';failure.write_text(json.dumps({'argv':argv,'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr},indent=2))
        raise RuntimeError(f'{argv[0]} failed; receipt={failure}: {r.stderr[-1500:]}')
    return json.loads(r.stdout)
# Two independent real Pi processes deliberately share the journal/snapshot base.
sessions=[run([sys.executable,str(ROOT/'skills/shame/scripts/eval-stop-boundary-live.py'),'--proof-repair']) for _ in range(2)]
assert sessions[0]['session_id']!=sessions[1]['session_id']
for s in sessions:
    r=subprocess.run([str(ROOT/'skills/shame/run.sh'),'failures','--session-id',s['session_id'],'--json'],cwd=ROOT,env=env,text=True,capture_output=True,timeout=20)
    assert r.returncode==0,r.stderr
    history=json.loads(r.stdout)
    assert history['events'] and all(e['session_id']==s['session_id'] for e in history['events'])
    rejected=[e for e in history['events'] if e['kind']=='report_rejected'];assert len(rejected)==1
    candidate=json.loads(Path(rejected[0]['review_packet']).read_text())['candidate']
    assert candidate['session_id']==s['session_id']
    assert candidate['response_sha256']==rejected[0]['candidate_hash']
# Capture an actual completed assistant turn, not a hand-written transcript.
local=work/'labels.jsonl'
argv=[str(ROOT/'skills/shame/run.sh'),'capture','--session',sessions[0]['session_file'],'--label','good_status_report','--synthetic','--note',work.name,'--out',str(local),'--memory-collection','shame_training_examples','--search-collection','project_knowledge']
receipt=run(argv);(work/'capture.json').write_text(json.dumps(receipt,indent=2))
row=json.loads(local.read_text().strip())
assert row['assistant_entry_id']!='explicit-text' and row['user_text']
assert row['human_verdict']=='allow' and 'good_status_report' in row['human_reasons']
assert row['response_sha256']=='sha256:'+hashlib.sha256(row['assistant_text'].encode()).hexdigest()
base=os.environ.get('MEMORY_SERVICE_URL') or os.environ.get('MEMORY_API_URL') or 'http://127.0.0.1:8601'
if base.startswith('unix://'):base='http://127.0.0.1:8601'
with httpx.Client(base_url=base.rstrip('/'),timeout=httpx.Timeout(15,connect=2),headers={'x-caller-skill':'shame'}) as client:
    def fetch(collection,key):
        r=client.post('/recall/by-keys',json={'collection':collection,'keys':[key],'key_field':'_key','return_fields':['_key','response_sha256','example_ref','retrieval_text']});r.raise_for_status();return r.json()['documents']
    memory=receipt['memory'];docs=fetch(memory['collection'],memory['key'])
    assert len(docs)==1 and docs[0]['response_sha256']==row['response_sha256']
    shadow=fetch(memory['search']['collection'],memory['search']['key'])
    assert len(shadow)==1 and shadow[0]['example_ref']==memory['collection']+'/'+memory['key']
    recalled=client.post('/recall',json={'q':work.name,'collections':['project_knowledge'],'tags':['shame'],'k':10,'threshold':0.0});recalled.raise_for_status()
    readback=work/'memory-readback.json'
    returned=[e.get('_key') for e in recalled.json()['items']]
    readback.write_text(json.dumps({'structured_keys':[e['_key'] for e in docs],'shadow_keys':[e['_key'] for e in shadow],'expected_recall_key':memory['search']['key'],'recall_keys':returned,'recall_response':recalled.json()},indent=2))
    assert memory['search']['key'] in returned, f'stored shadow not recalled; receipt={readback}'
# Invalid collection names must fail before a local training row is written.
bad=work/'forbidden.jsonl'
r=subprocess.run([str(ROOT/'skills/shame/run.sh'),'capture','--text','invalid collection control','--verdict','reject','--reason','synthetic_fixture','--memory-collection','_system','--out',str(bad)],cwd=ROOT,env=env,text=True,capture_output=True,timeout=20)
assert r.returncode!=0 and 'must not be a system collection' in r.stderr and not bad.exists()
result={'sessions_isolated':True,'real_session_capture':True,'memory_independently_read_back':True,'unsafe_collection_refused':True,'sessions':[s['session_file'] for s in sessions],'capture':str(work/'capture.json'),'memory_readback':str(work/'memory-readback.json')}
(work/'report.json').write_text(json.dumps(result,indent=2));print(json.dumps({**result,'report':str(work/'report.json')}))
