#!/usr/bin/env python3
"""Installed audio -> real installer -> byte readback -> bad-loop refusal."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import wave

ROOT=Path(__file__).resolve().parents[3]
OUT=Path('/mnt/storage12tb/skills/shame/eval-cleanup');OUT.mkdir(parents=True,exist_ok=True)
work=Path(tempfile.mkdtemp(prefix='audio-',dir=OUT))
source=Path.home()/'.pi/agent/extensions/lazy-report-shame-shame-shame/shame.wav'
target=work/'installed'
argv=[str(ROOT/'skills/shame/run.sh'),'audio','install','--source',str(source),'--extension-dir',str(target)]
r=subprocess.run(argv,cwd=ROOT,text=True,capture_output=True,timeout=30)
assert r.returncode==0,r.stderr
receipt=json.loads(r.stdout);(work/'install-receipt.json').write_text(r.stdout)
installed=target/'shame.wav'
assert installed.read_bytes()==source.read_bytes()
assert 0.9<=receipt['installed']['duration_sec']<=2.5 and receipt['installed']['active_duration_sec']>=0.45
before=hashlib.sha256(installed.read_bytes()).hexdigest()
with wave.open(str(source),'rb') as audio: params=audio.getparams();pcm=audio.readframes(audio.getnframes())
bad=work/'repeated-loop.wav'
with wave.open(str(bad),'wb') as audio:audio.setparams(params);audio.writeframes(pcm*4)
r=subprocess.run([str(ROOT/'skills/shame/run.sh'),'audio','install','--source',str(bad),'--extension-dir',str(target)],cwd=ROOT,text=True,capture_output=True,timeout=30)
(work/'refusal.log').write_text(r.stdout+r.stderr)
assert r.returncode!=0 and hashlib.sha256(installed.read_bytes()).hexdigest()==before
result={'installed_bytes_verified':True,'loop_rejected':True,'good_install_preserved':True,'proof_boundary':'Real installed reference and installer/file operations; no new TTS generation or human listening judgment.','receipt':str(work/'install-receipt.json'),'refusal':str(work/'refusal.log')}
(work/'report.json').write_text(json.dumps(result,indent=2));print(json.dumps({**result,'report':str(work/'report.json')}))
