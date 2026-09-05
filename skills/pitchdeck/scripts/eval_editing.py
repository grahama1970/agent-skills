#!/usr/bin/env python3
"""Live editing gate: insert/paste/crop/delete/slide ops on a canonical document
through the real Vite API and the real browser UI (Surf), with $create-figure
and $create-svg generating the images. Works on a COPY of the approved
document; the user's source is never written. PPTX is re-emitted and reopened
so the crop and generated images are proven in the delivered artifact.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SKILL = ROOT / 'skills/pitchdeck'
SURF = ROOT / 'skills/surf/run.sh'
BASE = 'http://127.0.0.1:3006'


def command(*args, timeout=240):
    p = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError(p.stdout + p.stderr)
    return p.stdout


def api(route, deck, body=None, headers=None):
    request = urllib.request.Request(BASE + route, data=json.dumps(body).encode() if body is not None else None,
        headers={'X-Pitchdeck-Deck': deck, 'Content-Type': 'application/json', **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=240) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


PASTE_JS = '''return (async()=>{const q=s=>document.querySelector(s);const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const c=document.createElement("canvas");c.width=64;c.height=48;const g=c.getContext("2d");g.fillStyle="#d39500";g.fillRect(0,0,64,48);
const blob=await new Promise(r=>c.toBlob(r,"image/png"));const dt=new DataTransfer();dt.items.add(new File([blob],"pasted.png",{type:"image/png"}));
document.body.dispatchEvent(new ClipboardEvent("paste",{clipboardData:dt,bubbles:true}));await sleep(300);
const alt=q("[data-qid=\\"deck:asset-drop:alt\\"]");if(!alt)throw new Error("paste dialog missing");
Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set.call(alt,"Pasted gold swatch");alt.dispatchEvent(new Event("input",{bubbles:true}));
q("[data-qid=\\"deck:asset-drop:attach\\"]").click();for(let i=0;i<100&&q("[data-qid=\\"deck:asset-drop:attach\\"]");i++)await sleep(200);
for(let i=0;i<50&&!q("[data-qid^=\\"deck:freeform:SLIDE:img-pasted\\"]");i++)await sleep(200);
const el=q("[data-qid^=\\"deck:freeform:SLIDE:img-pasted\\"]");if(!el)throw new Error("pasted element missing");const id=el.dataset.qid.split(":").pop();
for(let i=0;i<20&&!q(`[data-qid="freeform:toolbar:crop-h:${id}"]`);i++){el.click();await sleep(200);}
const setc=(k,v)=>{q(`[data-qid="freeform:toolbar:crop-${k}:${id}"]`).value=String(v)};setc("x",0.25);setc("y",0.25);setc("w",0.5);setc("h",0.5);
q(`[data-qid="freeform:toolbar:crop-h:${id}"]`).dispatchEvent(new FocusEvent("focusout",{bubbles:true}));
for(let i=0;i<50;i++){await sleep(200);const img=[...document.querySelectorAll(".slide-viewport img")].find(i=>i.currentSrc.includes("pasted"));if(img&&img.style.width==="200%")return {id,cropStyle:img.style.width+" "+img.style.marginLeft};}
throw new Error("crop not reflected: "+(q("[role=alert]")?.innerText||""))})()'''

CHART_JS = '''return (async()=>{const q=s=>document.querySelector(s);const sleep=ms=>new Promise(r=>setTimeout(r,ms));
for(let i=0;i<50&&!q(".slide-viewport");i++)await sleep(100);q("[data-qid=\\"deck:mode:design\\"]").click();await sleep(300);
q("[data-qid=\\"deck:insert:menu\\"]").click();await sleep(200);q("[data-qid=\\"deck:insert:chart\\"]").click();await sleep(200);
const set=(sel,v)=>{const e=q(sel);Object.getOwnPropertyDescriptor(e.tagName==="TEXTAREA"?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,"value").set.call(e,v);e.dispatchEvent(new Event("input",{bubbles:true}))};
set("[data-qid=\\"deck:insert:spec\\"]",JSON.stringify({Detect:12,Harden:30,Restore:8}));set("[data-qid=\\"deck:insert:alt\\"]","Bar chart of tactic counts");
q("[data-qid=\\"deck:insert:generate\\"]").click();for(let i=0;i<400&&q("[data-qid=\\"deck:insert:generate\\"]");i++)await sleep(200);
for(let i=0;i<50;i++){await sleep(200);const imgs=[...document.querySelectorAll(".slide-viewport img")].map(i=>i.currentSrc.split("/").pop());if(imgs.some(n=>n.startsWith("chart")))return {imgs};}
throw new Error("chart not rendered: "+(q("[role=alert]")?.innerText||""))})()'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--negative', action='store_true')
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    os.environ.setdefault('UV_PROJECT_ENVIRONMENT', '/mnt/storage12tb/skills/pitchdeck/.venv')
    os.environ.setdefault('SPARTA_PUBLIC_ROOT', '/mnt/storage12tb/skills/pitchdeck/sources/sparta-public')
    result = {'schema': 'pitchdeck.editing_live.v1', 'live': True, 'mocked': False, 'checks': []}
    tab = None
    original = Path('/mnt/storage12tb/skills/pitchdeck/outputs/ticket-1278/approved.document.json')
    before = original.read_bytes()
    run = f'editing-{os.getpid()}-{time.time_ns()}'
    storage = Path('/mnt/storage12tb/skills/pitchdeck/outputs/usability-123-sync') / run
    storage.mkdir(parents=True)
    doc = storage / 'doc.json'
    shutil.copy2(original, doc)
    output = SKILL / 'ui/public' / f'usability-{run}'
    url = f'/{output.name}/deck.data.json'
    try:
        command(str(SKILL / 'run.sh'), 'emit-document-ui', '--document', str(doc), '--asset-base', str(SKILL / 'examples/sparta-explorer'), '--output-dir', str(output))
        deck = json.loads((output / 'deck.data.json').read_text())
        first = deck['slides'][0]['id']
        op = ['--document', str(doc), '--output-dir', str(output), '--asset-base', str(SKILL / 'examples/sparta-explorer')]
        if args.negative:
            fake = storage / 'fake.png'
            fake.write_bytes(b'#!/bin/sh\necho not an image\n')
            for label, argv in [
                ('script renamed png', ['--op', 'add-image', '--slide-id', first, '--file', str(fake), '--alt', 'x']),
                ('crop out of bounds', ['--op', 'crop', '--slide-id', first, '--element-id', 'title', '--bbox', '0.5,0.5,0.8,0.8']),
                ('delete unknown element', ['--op', 'delete-element', '--slide-id', first, '--element-id', 'nope']),
                ('missing alt', ['--op', 'add-image', '--slide-id', first, '--file', str(SKILL / 'examples/sparta-explorer/assets/sparta-front-helmet-cyan.svg'), '--alt', ' ']),
            ]:
                p = subprocess.run([str(SKILL / 'run.sh'), 'document-op', *op, *argv], cwd=ROOT, capture_output=True, text=True, timeout=120)
                assert p.returncode != 0, label
                result['checks'].append({'refused': label, 'stderr': p.stderr.strip()[-200:]})
            assert hashlib.sha256(doc.read_bytes()).hexdigest() == hashlib.sha256(before).hexdigest(), 'rejected ops must not write'
            status, err = api('/api/insert', url, {'kind': 'chart', 'slide_id': first, 'spec': 'not json', 'alt': 'x'})
            assert status == 422, (status, err)
            result['checks'].append({'refused': 'insert with invalid metrics JSON', 'status': status})
        else:
            # CLI path (what an agent runs): chart via create-figure, diagram via create-svg, slide ops.
            (storage / 'metrics.json').write_text('{"Search": 42, "Review": 17, "Approve": 9}')
            command(str(ROOT / 'skills/create-svg/run.sh'), 'new', 'positive-negative', str(storage / 'scene.yml'))
            r1 = json.loads(command(str(SKILL / 'run.sh'), 'document-op', *op, '--op', 'add-chart', '--slide-id', first, '--spec', str(storage / 'metrics.json'), '--chart-type', 'pie', '--title', 'Corpus', '--alt', 'Pie of corpus counts', '--bbox', '0.55,0.3,0.4,0.4'))
            r2 = json.loads(command(str(SKILL / 'run.sh'), 'document-op', *op, '--op', 'add-diagram', '--slide-id', first, '--spec', str(storage / 'scene.yml'), '--alt', 'Validation diagram', '--bbox', '0.05,0.3,0.45,0.4'))
            r3 = json.loads(command(str(SKILL / 'run.sh'), 'document-op', *op, '--op', 'slide-duplicate', '--slide-id', first))
            json.loads(command(str(SKILL / 'run.sh'), 'document-op', *op, '--op', 'slide-delete', '--slide-id', r3['slide']))
            result['checks'].append({'cli': [r1, r2, r3]})
            # UI path: Insert menu chart (create-figure), clipboard paste, crop, delete element.
            created = command(str(SURF), 'window.new', BASE + '/?deck=' + url, '--unfocused', '--width', '1400', '--height', '1000')
            tab = re.search(r'\(tab (\d+)\)', created).group(1)
            def js(code):
                return json.loads(command(str(SURF), 'js', code, '--tab-id', tab, '--no-activate'))
            result['checks'].append({'ui_chart': js(CHART_JS)})
            result['checks'].append({'ui_paste_crop': js(PASTE_JS.replace('SLIDE', first))})
            shot = str(storage / 'editing.png'); command(str(SURF), 'snap', '--output', shot, '--tab-id', tab, '--no-activate'); result['screenshot'] = shot
            status, deleted = api('/api/slide-edit', url, {'slide_id': first, 'field': f'element:del:{r1["element"]}', 'value': ''})
            assert status == 200, (status, deleted)
            document = json.loads(doc.read_text())
            slide = next(s for s in document['slides'] if s['id'] == first)
            ids = {e['id']: e for e in slide['elements']}
            assert r1['element'] not in ids and r2['element'] in ids and 'img-pasted' in ids
            assert ids['img-pasted']['crop'] == {'x': 0.25, 'y': 0.25, 'w': 0.5, 'h': 0.5}
            # Delivered artifact: reopen PPTX, find the cropped picture and the generated images.
            pptx = storage / 'out.pptx'
            command(str(SKILL / 'run.sh'), 'emit-document-pptx', '--document', str(doc), '--asset-base', str(SKILL / 'examples/sparta-explorer'), '--output', str(pptx))
            probe = "import json,sys;from pptx import Presentation;print(json.dumps({sh.name:[getattr(sh,'crop_left',None),getattr(sh,'crop_right',None)] for sh in Presentation(sys.argv[1]).slides[0].shapes if sh.name.startswith('el:img')}))"
            names = json.loads(command('uv', 'run', '--project', str(SKILL), 'python', '-c', probe, str(pptx)))
            assert abs(names['el:img-pasted'][0] - 0.25) < 1e-6 and abs(names['el:img-pasted'][1] - 0.25) < 1e-6, names
            assert f'el:{r2["element"]}' in names and any(n.startswith('el:img-chart') for n in names)
            result['checks'].append({'pptx': str(pptx), 'shapes': sorted(names)})
        assert original.read_bytes() == before, 'user source changed'
        result['status'] = 'PASS'
    except Exception as e:
        result.update(status='FAIL', error=str(e))
    finally:
        if tab and result.get('status') == 'PASS':
            command(str(SURF), 'tab.close', tab)
        result['tab_id'] = tab
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'receipt': str(args.out), 'error': result.get('error')}))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
