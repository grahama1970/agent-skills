#!/usr/bin/env python3
"""Real theme CLI with an unwritable storage destination; no mocks or pytest.
Runs after the live canonical/legacy theme cases on their isolated copies.
"""
import argparse
import hashlib
import json
import subprocess
import shutil
import os
import time
from pathlib import Path
from eval_editing import SKILL, api
from eval_theme_picker import OUT

p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);args=p.parse_args()
work=OUT/'write-failure'/str(time.time_ns());work.mkdir(parents=True)
blocked=work/'not-a-directory';blocked.write_text('deliberate storage failure')
result={'live':True,'mocked':False,'checks':[]}
try:
 for name, prefix in [('live','theme-eval-'),('legacy','theme-legacy-')]:
  receipt=json.loads((OUT/(name+'.json')).read_text());run=Path(receipt['run'])
  output=SKILL/'ui/public'/(prefix+run.name);emit=json.loads((output/'emit_ui_receipt.json').read_text())
  source=Path(emit['outputs'].get('document_path') or str(Path(emit['outputs']['bundle_dir'])/'deck.public.yaml'))
  status,catalog=api('/api/theme','/'+output.name+'/deck.data.json');assert status==200,catalog
  paths=[source,output/'deck.data.json',output/'deck.document.json',source.parent/'.revision',source.parent/'.revision.state.json']
  before=[f.read_bytes() if f.exists() else None for f in paths]
  request=work/(name+'.json');request.write_text(json.dumps({'action':'apply','theme':catalog['presets'][0],'hashes':catalog['hashes'],'revision':catalog['revision']}))
  argv=[str(SKILL/'run.sh'),'theme-edit','--source',str(source),'--output-dir',str(output),'--request-file',str(request),'--storage',str(blocked)]
  proc=subprocess.run(argv,capture_output=True,text=True,timeout=30)
  assert proc.returncode!=0,proc.stdout
  assert before==[f.read_bytes() if f.exists() else None for f in paths],'Rejected operation changed source/projection/revision'
  result['checks'].append({'source_kind':name,'command':argv,'exit':proc.returncode,'stderr':proc.stderr,'unchanged':{str(f):hashlib.sha256(b).hexdigest() if b is not None else None for f,b in zip(paths,before)}})
 # Exercise the real CLI and real os.replace rollback with a Python audit-hook
 # fault, not a mocked filesystem. Also simulate a later source writer before
 # the refusal: the transaction must leave that writer's bytes alone.
 for name, prefix in [('live','theme-eval-'),('legacy','theme-legacy-')]:
  receipt=json.loads((OUT/(name+'.json')).read_text());run=Path(receipt['run'])
  original_output=SKILL/'ui/public'/(prefix+run.name)
  emit=json.loads((original_output/'emit_ui_receipt.json').read_text())
  original_source=Path(emit['outputs'].get('document_path') or str(Path(emit['outputs']['bundle_dir'])/'deck.public.yaml'))
  for later in [False,True]:
   lane=work/(name+'-rollback-'+str(later));lane.mkdir()
   bundle=lane/'source';shutil.copytree(original_source.parent,bundle)
   output=lane/'output';shutil.copytree(original_output,output)
   source=bundle/original_source.name;storage=lane/'storage';storage.mkdir()
   catalog=api('/api/theme','/'+original_output.name+'/deck.data.json')[1]
   request=lane/'request.json';request.write_text(json.dumps({'action':'apply','theme':catalog['presets'][0],'hashes':catalog['hashes'],'revision':catalog['revision']}))
   watched=[source,output/'deck.data.json',output/'deck.document.json',bundle/'.revision',bundle/'.revision.state.json']
   before={f:f.read_bytes() if f.exists() else None for f in watched}
   history={str(f.relative_to(bundle)):f.read_bytes() for f in (bundle/'.history').rglob('*') if f.is_file()}
   stop=storage/(hashlib.sha256(str(source.resolve()).encode()).hexdigest()+'.undo.json')
   injection='''import sys,os,runpy
source,stop,later=sys.argv[1:4];sys.argv=['pitchdeck']+sys.argv[4:]
def hook(event,args):
 if event=='os.rename' and os.fspath(args[1])==stop:
  if later=='True':
   with open(source,'wb') as f:f.write(b'later writer owns these bytes\\n')
  raise OSError('retained audit-hook filesystem refusal')
sys.addaudithook(hook)
runpy.run_module('pitchdeck.cli',run_name='__main__')
'''
   argv=['/mnt/storage12tb/skills/pitchdeck/.venv/bin/python','-c',injection,str(source),str(stop),str(later),'theme-edit','--source',str(source),'--output-dir',str(output),'--request-file',str(request),'--storage',str(storage)]
   proc=subprocess.run(argv,env={**os.environ,'PYTHONPATH':str(SKILL/'src')},capture_output=True,text=True,timeout=30)
   assert proc.returncode!=0 and 'retained audit-hook filesystem refusal' in proc.stderr,proc.stderr
   actual={f:f.read_bytes() if f.exists() else None for f in watched}
   if later:
    assert actual[source]==b'later writer owns these bytes\n', 'Later writer was overwritten'
    before[source]=actual[source]
   assert actual==before,'Rollback did not restore prior file presence/bytes'
   assert history=={str(f.relative_to(bundle)):f.read_bytes() for f in (bundle/'.history').rglob('*') if f.is_file()},'History changed'
   assert not list(storage.glob('*.undo.json')),'Failed operation left a journal'
   assert not list(lane.rglob('.selected-edit-*')),'Staged files leaked'
   result['checks'].append({'source_kind':name,'fault_injected':True,'later_writer_preserved':later,'rollback_verified':True,'exit':proc.returncode,'stderr':proc.stderr,'command':argv,'readback_hashes':{str(f):hashlib.sha256(b).hexdigest() if b is not None else None for f,b in actual.items()}})
 result['status']='PASS'
except Exception as e:result.update(status='FAIL',error=str(e))
args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(result,indent=2));print(json.dumps(result));raise SystemExit(0 if result['status']=='PASS' else 1)
