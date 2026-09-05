#!/usr/bin/env python3
"""Live Theme top-bar workflow, byte-bound refusal, source invariance and real exports.
Uses a copy of the retained approved source; no provider or browser is mocked.
"""
import argparse
import hashlib
import json
import posixpath
import re
import shutil
import time
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from eval_editing import ROOT, SKILL, SURF, BASE, command, api

import os
OUT = Path(os.environ.get('PITCHDECK_THEME_EVAL_ROOT', '/mnt/storage12tb/skills/pitchdeck/outputs/theme-picker'))

def stripped(doc):
    doc = json.loads(json.dumps(doc))
    doc['deck'].pop('theme', None); doc['deck'].pop('theme_tokens', None)
    return doc


def main():
    p = argparse.ArgumentParser(); p.add_argument('--negative', action='store_true'); p.add_argument('--out', type=Path, required=True); args = p.parse_args()
    import os
    os.environ.setdefault('SPARTA_PUBLIC_ROOT', '/mnt/storage12tb/skills/pitchdeck/sources/sparta-public')
    run = OUT / ('negative-' if args.negative else 'live-') / str(time.time_ns()); run.mkdir(parents=True)
    source = run / 'document.json'; shutil.copy2('/mnt/storage12tb/skills/pitchdeck/outputs/ticket-1278/approved.document.json', source)
    output = SKILL / 'ui/public' / ('theme-eval-' + run.name); url = '/' + output.name + '/deck.data.json'
    result = {'live': True, 'mocked': False, 'run': str(run)}; tab = None; theme_name = None
    try:
        command(str(SKILL / 'run.sh'), 'emit-document-ui', '--document', str(source), '--asset-base', str(SKILL / 'examples/sparta-explorer'), '--output-dir', str(output))
        before = source.read_bytes(); initial = json.loads(before)
        data = output / 'deck.data.json'; initial_payload = json.loads(data.read_text())
        assets = {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in (output / 'assets').glob('*') if f.is_file()}
        status, catalog = api('/api/theme', url); assert status == 200, catalog
        brand = catalog['presets'][0]
        if args.negative:
            result['refusals'] = []
            for name, patch in [('stale-revision', {'revision': -1}), ('stale-source', {'hashes': ['bad', 'bad']}), ('bad-color', {'theme': {**brand, 'tokens': {**brand['tokens'], 'accent': 'red;display:none'}}}), ('bad-opacity', {'theme': {**brand, 'tokens': {**brand['tokens'], 'header_opacity': 1.1}}}), ('bad-font', {'theme': {**brand, 'tokens': {**brand['tokens'], 'heading_font': 'url(evil)'}}}), ('unknown-token', {'theme': {**brand, 'tokens': {**brand['tokens'], 'slides': []}}})]:
                snapshot = [source.read_bytes(), data.read_bytes()]
                status, value = api('/api/theme', url, {'action': 'apply', 'revision': catalog['revision'], 'hashes': catalog['hashes'], 'theme': brand, **patch})
                assert status == 409, (name, value)
                assert snapshot == [source.read_bytes(), data.read_bytes()], name
                result['refusals'].append({'case': name, 'response': value})
        else:
            created = command(str(SURF), 'window.new', BASE + '/?deck=' + url, '--unfocused', '--width', '1600', '--height', '1050')
            tab = re.search(r'\(tab (\d+)\)', created).group(1); result['tab_id'] = tab
            def js(code): return json.loads(command(str(SURF), 'js', 'return (async()=>{' + code + '})()', '--tab-id', tab, '--no-activate'))
            setup = '''const q=s=>document.querySelector(`[data-qid="deck:theme:${s}"]`);const sleep=ms=>new Promise(r=>setTimeout(r,ms));const wait=async s=>{for(let i=0;i<100&&!q(s);i++)await sleep(100);if(!q(s))throw Error("missing "+s);return q(s)};const set=(s,v)=>{const e=q(s);Object.getOwnPropertyDescriptor(e.tagName==="SELECT"?HTMLSelectElement.prototype:HTMLInputElement.prototype,"value").set.call(e,v);e.dispatchEvent(new Event(e.tagName==="SELECT"?"change":"input",{bubbles:true}))};'''
            js(setup + '''await wait('menu');q('menu').click();await wait('preset');set('preset','grahama.co');await sleep(200);return document.documentElement.dataset.deckTheme''')
            command(str(SURF), 'snap', '--tab-id', tab, '--no-activate', '--output', str(run / 'preview.png'))
            assert source.read_bytes() == before
            result['header_image'] = js("const s=getComputedStyle(document.querySelector('.freeform-band'),'::before');const u=s.backgroundImage.match(/url\\([\"']?(.*?)[\"']?\\)/)?.[1];if(!u)throw Error('missing header image');const r=await fetch(u);if(!r.ok)throw Error('header image fetch failed');const b=await r.arrayBuffer();return {opacity:Number(s.opacity),sha256:[...new Uint8Array(await crypto.subtle.digest('SHA-256',b))].map(x=>x.toString(16).padStart(2,'0')).join('')}")
            assert result['header_image'] == {'opacity': .1, 'sha256': hashlib.sha256((ROOT / 'skills/best-practices-slide-design/assets/house-band-texture.png').read_bytes()).hexdigest()}
            js("document.querySelector('[data-qid=\"deck:nav:next\"]').click();return true");time.sleep(.3)
            command(str(SURF), 'snap', '--tab-id', tab, '--no-activate', '--output', str(run / 'preview-slide-2.png'))
            js("document.querySelector('[data-qid=\"deck:nav:prev\"]').click();return true");time.sleep(.3)
            js(setup + "q('cancel').click();await sleep(150);return document.documentElement.dataset.deckTheme")
            assert source.read_bytes() == before
            theme_name = 'Eval theme ' + run.name
            js(setup + "q('menu').click();await wait('preset');set('preset','grahama.co');await sleep(100);q('customize').click();await sleep(100);set('header_opacity','0.08');set('header_image_opacity','0.06');set('accent','#d1703c');set('heading_font','Georgia');await sleep(100);set('heading_font','Fraunces');set('name'," + json.dumps(theme_name) + ");await sleep(100);q('save').click();await sleep(1000);return q('name').value")
            assert source.read_bytes() == before
            saved = api('/api/theme', url)[1]; assert any(p['name'] == theme_name for p in saved['presets'])
            command(str(SURF), 'snap', '--tab-id', tab, '--no-activate', '--output', str(run / 'customize.png'))
            result['primary_actions_visible'] = js(setup + "const panel=document.querySelector('.theme-panel').getBoundingClientRect();return ['apply','cancel'].every(k=>{const e=q(k),r=e.getBoundingClientRect();return r.top>=panel.top&&r.bottom<=panel.bottom&&e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))})")
            assert result['primary_actions_visible'], 'Apply/Cancel must remain visible with Customize expanded'
            js(setup + "q('apply').click();await sleep(1000);return q('menu').innerText")
            after = json.loads(source.read_text()); assert stripped(after) == stripped(initial)
            assert after['deck']['theme_tokens']['header_opacity'] == .08, after['deck']
            assert after['deck']['theme_tokens']['accent'] == '#d1703c'
            assert json.loads(data.read_text())['slides'] == initial_payload['slides']
            assert assets == {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in (output / 'assets').glob('*') if f.is_file()}
            js('location.reload();return true'); time.sleep(1)
            fonts = js(setup + "await wait('menu');await document.fonts.load('600 32px Fraunces');return {loaded:[...document.fonts].filter(f=>f.family==='Fraunces').map(f=>f.status),resources:performance.getEntriesByType('resource').filter(e=>e.name.includes('fraunces')).map(e=>({name:e.name,bytes:e.transferSize})),heading:getComputedStyle(document.querySelector('.freeform-band span')).fontFamily,theme:q('menu').innerText}")
            assert fonts['loaded'] == ['loaded'], fonts
            result['font_readback'] = fonts
            rehearsal = js("document.querySelector('[data-qid=\"deck:rehearse\"]').click();await new Promise(r=>setTimeout(r,200));return {theme:document.documentElement.dataset.deckTheme,font:getComputedStyle(document.querySelector('.freeform-band span')).fontFamily}")
            assert rehearsal == {'theme':'custom', 'font':'Fraunces'}, rehearsal
            js("document.querySelector('[data-qid=\"deck:rehearse\"]').click();return true");time.sleep(.2)
            result['rehearsal_theme'] = rehearsal
            command(str(SURF), 'snap', '--tab-id', tab, '--no-activate', '--output', str(run / 'applied.png'))
            js("document.querySelector('[data-qid=\"deck:nav:next\"]').click();return true");time.sleep(.5)
            command(str(SURF), 'snap', '--tab-id', tab, '--no-activate', '--output', str(run / 'slide-2.png'))
            status, export = api('/api/export', url, {'format': 'pptx'}); assert status == 200, export
            pptx = SKILL / 'ui/public' / export['url'].lstrip('/'); shutil.copy2(pptx, run / 'deck.pptx')
            ns = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}
            with ZipFile(pptx) as z:
                parts = [n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+.xml', n)]
                slides = [ET.fromstring(z.read(n)) for n in parts]
                for part, slide in zip(parts, slides):
                    rels = {r.get('Id'): r.get('Target') for r in ET.fromstring(z.read(posixpath.join(posixpath.dirname(part), '_rels', posixpath.basename(part) + '.rels')))}
                    header_blips = [b for b in slide.findall('.//a:blip', ns) if b.find('a:alphaModFix[@amt="6000"]', ns) is not None]
                    assert any(hashlib.sha256(z.read(posixpath.normpath(posixpath.join(posixpath.dirname(part), rels[b.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed')])))).hexdigest() == result['header_image']['sha256'] for b in header_blips), 'Header image bytes/independent opacity missing from PPTX'
                    assert slide.findall('.//a:alpha[@val="8000"]', ns)
                    assert slide.findall('.//a:srgbClr[@val="211917"]', ns)
                    assert slide.findall('.//a:srgbClr[@val="0C0908"]', ns) or slide.findall('.//a:srgbClr[@val="0c0908"]', ns)
                assert any(e.attrib.get('typeface') == 'Fraunces' for s in slides for e in s.findall('.//a:latin', ns))
            status, pdf = api('/api/export', url, {'format': 'pdf'}); assert status == 200, pdf
            pdf_path = SKILL / 'ui/public' / pdf['url'].lstrip('/'); shutil.copy2(pdf_path, run / 'deck.pdf')
            result['pdf_info'] = command('pdfinfo', str(pdf_path)); result['pdf_fonts'] = command('pdffonts', str(pdf_path))
            assert re.search(r'Fraunces-\S+\s+TrueType\s+\S+\s+yes\s+yes', result['pdf_fonts']), result['pdf_fonts']
            command('pdftoppm', '-f', '1', '-singlefile', '-scale-to', '1200', '-png', str(pdf_path), str(run / 'pdf-slide-1'))
            js(setup + "q('menu').click();await wait('preset');set('preset','Legacy house');await sleep(100);set('preset'," + json.dumps(theme_name) + ");await sleep(100);return q('preset').value")
            assert source.read_bytes() == json.dumps(after, ensure_ascii=False, indent=1).encode()
            js(setup + "q('undo').click();await sleep(1000);return q('menu').innerText")
            assert json.loads(source.read_text()) == initial
            result.update(source_content_geometry_claims_animations_unchanged=True, asset_hashes=assets, pptx=str(run/'deck.pptx'), pdf=str(run/'deck.pdf'))
        result['status'] = 'PASS'
    except Exception as e:
        result.update(status='FAIL', error=str(e))
    finally:
        if tab: command(str(SURF), 'tab.close', tab)
        # Remove only the preset this isolated trial created, after readback.
        saved_path = Path('/mnt/storage12tb/skills/pitchdeck/outputs/themes/saved.json')
        if theme_name and saved_path.exists():
            saved = json.loads(saved_path.read_text())
            temp = saved_path.with_suffix('.eval-cleanup.tmp')
            temp.write_text(json.dumps([p for p in saved if p['name'] != theme_name], indent=1)); temp.replace(saved_path)
        args.out.parent.mkdir(parents=True, exist_ok=True);args.out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result));return 0 if result['status'] == 'PASS' else 1

if __name__ == '__main__': raise SystemExit(main())
