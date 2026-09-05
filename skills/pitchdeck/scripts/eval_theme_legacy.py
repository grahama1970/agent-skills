#!/usr/bin/env python3
"""Legacy production emit/API/export theme adapter; no source migration."""
import argparse
import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
import yaml
from eval_editing import SKILL, SURF, BASE, command, api
from eval_theme_picker import OUT, stripped

p = argparse.ArgumentParser();p.add_argument('--out', type=Path, required=True);args=p.parse_args()
os.environ.setdefault('SPARTA_CANONICAL_ROOT', '/mnt/storage12tb/skills/pitchdeck/sources/sparta-canonical')
os.environ.setdefault('SPARTA_ROOT', str(SKILL.parents[2] / 'sparta'))
os.environ.setdefault('SPARTA_PUBLIC_ROOT', '/mnt/storage12tb/skills/pitchdeck/sources/sparta-public')
run=OUT/'legacy'/str(time.time_ns());run.mkdir(parents=True)
bundle=run/'bundle';shutil.copytree(SKILL/'examples/sparta-explorer',bundle,ignore=shutil.ignore_patterns('.history','.revision','.revision.state.json'))
for manifest in ['source_manifest.yaml', 'asset_manifest.yaml']:
 f=bundle/manifest;f.write_text(os.path.expandvars(f.read_text()))
shutil.copy2(bundle/'source_manifest.yaml', bundle/'source_manifest.resolved.yaml')
output=SKILL/'ui/public'/('theme-legacy-'+run.name);url='/'+output.name+'/deck.data.json'
result={'live':True,'mocked':False,'run':str(run)};tab=None
try:
 command(str(SKILL/'run.sh'),'emit-ui','--bundle-dir',str(bundle),'--output-dir',str(output))
 source=bundle/'deck.public.yaml';before=yaml.safe_load(source.read_text());data=output/'deck.data.json';initial=json.loads(data.read_text())
 projected_before=json.loads((output/'deck.document.json').read_text())
 assets={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (output/'assets').glob('*') if p.is_file()}
 status,c=api('/api/theme',url);assert status==200,c
 body={'action':'apply','theme':c['presets'][0],'hashes':c['hashes'],'revision':c['revision']}
 created=command(str(SURF),'window.new',BASE+'/?deck='+url,'--unfocused','--width','1400','--height','1000')
 tab=re.search(r'\(tab (\d+)\)',created).group(1)
 code='''return (async()=>{const q=s=>document.querySelector(`[data-qid="deck:theme:${s}"]`);const sleep=ms=>new Promise(r=>setTimeout(r,ms));for(let i=0;i<100&&!q('menu');i++)await sleep(100);q('menu').click();for(let i=0;i<100&&!q('preset');i++)await sleep(100);const e=q('preset');Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(e,'grahama.co');e.dispatchEvent(new Event('change',{bubbles:true}));await sleep(200);q('apply').click();await sleep(1500);return {theme:q('menu').innerText,background:getComputedStyle(document.querySelector('.deck-font')).backgroundColor}})()'''
 browser=json.loads(command(str(SURF),'js',code,'--tab-id',tab,'--no-activate'));assert 'grahama.co' in browser['theme'],browser
 shot=run/'legacy-applied.png';command(str(SURF),'snap','--tab-id',tab,'--no-activate','--output',str(shot));result.update(browser=browser,screenshot=str(shot))
 assert stripped(yaml.safe_load(source.read_text()))==stripped(before)
 assert json.loads(data.read_text())['slides']==initial['slides']
 projected=json.loads((output/'deck.document.json').read_text())
 assert stripped(projected)==stripped(projected_before)
 assert projected['deck']['theme_tokens']==yaml.safe_load(source.read_text())['deck']['theme_tokens']
 snapshot=[source.read_bytes(),data.read_bytes()]
 status,r=api('/api/theme',url,body);assert status==409,r
 assert snapshot==[source.read_bytes(),data.read_bytes()]
 status,r=api('/api/export',url,{'format':'pptx'});assert status==200,r
 pptx=SKILL/'ui/public'/r['url'].lstrip('/');shutil.copy2(pptx,run/'deck.pptx')
 with ZipFile(pptx) as z:
  xml=b''.join(z.read(n) for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml'))
  assert b'Fraunces' in xml, 'Missing display font'
  ns={'a':'http://schemas.openxmlformats.org/drawingml/2006/main','p':'http://schemas.openxmlformats.org/presentationml/2006/main'}
  for part in [n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+.xml',n)]:
   slide=ET.fromstring(z.read(part))
   bands=[s for s in slide.findall('.//p:sp',ns) if s.find('p:nvSpPr/p:cNvPr[@name="chrome:band"]',ns) is not None]
   assert any(s.find('.//a:alpha[@val="100000"]',ns) is not None for s in bands), 'Header fill is not opaque'
   assert slide.findall('.//a:blip/a:alphaModFix[@amt="10000"]',ns), 'Missing independent 10% header image'
  texture=hashlib.sha256((SKILL.parent/'best-practices-slide-design/assets/house-band-texture.png').read_bytes()).hexdigest()
  assert any(hashlib.sha256(z.read(n)).hexdigest()==texture for n in z.namelist() if n.startswith('ppt/media/')), 'Supplied header image bytes missing'
 status,c=api('/api/theme',url);assert status==200,c
 status,r=api('/api/theme',url,{'action':'undo','hashes':c['hashes'],'revision':c['revision']});assert status==200,r
 assert yaml.safe_load(source.read_text())==before
 assert assets=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (output/'assets').glob('*') if p.is_file()}
 result.update(status='PASS',pptx=str(run/'deck.pptx'),unchanged_content_geometry_claims_animations_assets=True)
except Exception as e: result.update(status='FAIL',error=str(e))
finally:
 if tab: command(str(SURF),'tab.close',tab)
args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(result,indent=2));print(json.dumps(result));raise SystemExit(0 if result['status']=='PASS' else 1)
