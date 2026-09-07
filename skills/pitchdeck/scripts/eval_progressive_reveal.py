#!/usr/bin/env python3
"""Retained live browser build/authoring evaluation; copied approved source, real Surf and CAS API."""
import os
import argparse
import copy
import hashlib
import json
import re
import shutil
import subprocess
import time
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from eval_editing import SKILL, SURF, BASE, command, api

ROOT = Path('/mnt/storage12tb/skills/pitchdeck/outputs/progressive-reveal/browser')

def main():
    p = argparse.ArgumentParser(); p.add_argument('--out', type=Path, required=True); p.add_argument('--negative', action='store_true'); args = p.parse_args()
    os.environ.setdefault('SPARTA_PUBLIC_ROOT', '/mnt/storage12tb/skills/pitchdeck/sources/sparta-public')
    run = ROOT / str(time.time_ns()); run.mkdir(parents=True)
    result = {'live': True, 'mocked': False, 'run': str(run), 'checks': []}; tab = None
    try:
        source = run / 'document.json'
        doc = json.loads(Path('/mnt/storage12tb/skills/pitchdeck/outputs/ticket-1278/approved.document.json').read_text())
        doc['slides'] = [doc['slides'][i] for i in [0, 1, 3]]
        for i,s in enumerate(doc['slides']): s['order'] = i+1; s['reveal'] = 'none'; s['transition'] = 'none'
        cover = doc['slides'][0]
        cover['elements'].append({'id':'group','kind':'group','bbox':{'x':.15,'y':.68,'w':.7,'h':.18},'children':[{'id':'shape','kind':'shape','bbox':{'x':0,'y':0,'w':.3,'h':1},'shape':{'preset':'ellipse'}},{'id':'shape2','kind':'shape','bbox':{'x':.6,'y':0,'w':.3,'h':1},'shape':{'preset':'rect'}}]})
        def effect(id, targets, name='appear', **kw): return dict(id=id, targets=targets,effect=name,phase='entrance',direction='left',start='on-click',duration_ms=600,delay_ms=0,**kw)
        # Third row: with-previous emphasis on an already-used object proves shared clicks and multiple actions per object.
        cover['animations'] = [effect('first',['message'],'wipe'), effect('group',['group'],'zoom'), {**effect('emph',['message'],'pulse'), 'phase':'emphasis', 'start':'with-previous'}]
        last = doc['slides'][-1]; diagram = next(e['diagram'] for e in last['elements'] if e['id']=='diagram')
        rows = [effect('paragraphs',['chevron-0','chevron-1'],'fly')]
        for i,n in enumerate(diagram['nodes']):
            seen = {x['id'] for x in diagram['nodes'][:i+1]}
            edges = [e for e in diagram['edges'] if e['target'] == n['id'] and e['source'] in seen]
            rows.append(effect('node'+str(i), ['diagram/node/'+n['id']] + ['diagram/edge/'+e['id'] for e in edges], 'fade'))
        # Unordered edges join the last concept, never before either endpoint.
        assigned = {t for r in rows for t in r['targets']}
        rows[-1]['targets'] += ['diagram/edge/'+e['id'] for e in diagram['edges'] if 'diagram/edge/'+e['id'] not in assigned]
        last['animations'] = rows
        source.write_text(json.dumps(doc))
        output = SKILL / 'ui/public' / ('reveal-eval-'+run.name); url = '/'+output.name+'/deck.data.json'
        command(str(SKILL/'run.sh'),'emit-document-ui','--document',str(source),'--asset-base',str(SKILL/'examples/sparta-explorer'),'--output-dir',str(output))
        data=output/'deck.data.json'; before=source.read_bytes(); initial=json.loads(before)
        assets={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in (output/'assets').glob('*') if f.is_file()}
        def check(name, condition, evidence=None):
            result['checks'].append({'name':name,'pass':bool(condition),'evidence':evidence})
            print('CHECK', name, bool(condition), flush=True)
            (run/'progress.json').write_text(json.dumps(result,indent=2))
            assert condition,(name,evidence)
        def cas_negatives():
            c=api('/api/animations?slide_id=m-cover',url)[1]
            for name,patch in [('stale',{'revision':-1}),('unknown-target',{'animations':[effect('bad',['missing'])]}),('invalid-timing',{'animations':[{**effect('bad',['message']), 'duration_ms':-1}]}),('invalid-phase',{'animations':[{**effect('bad',['message'],'spin'),'phase':'entrance'}]})]:
                snapshot=[source.read_bytes(),data.read_bytes()]
                status,value=api('/api/animations',url,{'action':'apply','slide_id':'m-cover','hashes':c['hashes'],'revision':c['revision'],'animations':cover['animations'],**patch})
                check(name+' no-write',status==409 and snapshot==[source.read_bytes(),data.read_bytes()],value)
            check('asset bytes preserved',assets=={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in (output/'assets').glob('*') if f.is_file()})
        if args.negative:
            cas_negatives(); result['status']='PASS'; return
        created=command(str(SURF),'window.new',BASE+'/?deck='+url,'--unfocused','--width','1800','--height','1100');tab=re.search(r'\(tab (\d+)\)',created).group(1);result['tab_id']=tab
        def js(code): return json.loads(command(str(SURF),'js','return (async()=>{'+code+'})()','--tab-id',tab,'--no-activate'))
        def key(k):
            js('document.activeElement?.blur();return true')
            command(str(SURF),'key',k,'--tab-id',tab,'--no-activate');time.sleep(.12)
        def state(): return js('const e=document.querySelector(".slide-viewport [data-animation-slide]");return {id:e.dataset.animationSlide,build:Number(e.dataset.build),total:Number(e.dataset.buildTotal),targets:[...e.querySelectorAll("[data-animation-target]")].map(t=>({id:t.dataset.animationTarget,hidden:getComputedStyle(t).visibility==="hidden",inert:t.inert,opacity:getComputedStyle(t).opacity,clip:getComputedStyle(t).clipPath,transform:getComputedStyle(t).transform}))}')
        js('for(let i=0;i<100&&!document.querySelector(".slide-viewport [data-animation-slide]");i++)await new Promise(r=>setTimeout(r,100));return !!document.querySelector(".slide-viewport [data-animation-slide]")')
        command(str(SURF),'snap','--tab-id',tab,'--no-activate','--output',str(run/'initial.png'))
        s=state();m=next(t for t in s['targets'] if t['id']=='message');check('initial first-slide hidden builds',s['build']==0 and m['hidden'] and m['inert'],s)
        key('ArrowRight');s=state();check('first key reveals without crossing',s['build']==1,s)
        # Pause live WAAPI at a representative intermediate time for an inspectable frame.
        frame=js('const e=document.querySelector(".slide-viewport [data-animation-target=message]");e.getAnimations().forEach(a=>{a.pause();a.currentTime=300});return {clip:getComputedStyle(e).clipPath,opacity:getComputedStyle(e).opacity,transform:getComputedStyle(e).transform}')
        command(str(SURF),'snap','--tab-id',tab,'--no-activate','--output',str(run/'wipe-mid.png'));check('wipe intermediate clip',frame['clip']!='none' and '50%' in frame['clip'],frame)
        key('ArrowLeft');s=state();check('reverse cancels in-flight build',s['build']==0 and next(t for t in s['targets'] if t['id']=='message')['hidden'],s)
        key('ArrowRight');key('ArrowRight');s=state();check('group build',s['build']==2 and not next(t for t in s['targets'] if t['id']=='group')['hidden'],s)
        frame=js('const e=document.querySelector(".slide-viewport [data-animation-target=group]");e.getAnimations().forEach(a=>{a.pause();a.currentTime=300});return {transform:getComputedStyle(e).transform,clip:getComputedStyle(e).clipPath}')
        command(str(SURF),'snap','--tab-id',tab,'--no-activate','--output',str(run/'zoom-mid.png'));check('zoom is not wipe',frame['transform']!='none',frame)
        check('with-previous adds no click',s['total']==2 and len(cover['animations'])==3,s)
        frame=js('const e=document.querySelector(".slide-viewport [data-animation-target=message]");e.getAnimations().forEach(a=>{a.pause();a.currentTime=300});return {transform:getComputedStyle(e).transform}')
        check('with-previous emphasis pulses same object',frame['transform'].startswith('matrix(') and frame['transform']!='matrix(1, 0, 0, 1, 0, 0)',frame)
        key('ArrowRight');s=state();check('zero-build middle slide',s['id']=='m-thesis' and s['total']==0,s)
        key('ArrowLeft');s=state();check('backward revisit restores full previous slide',s['id']=='m-cover' and s['build']==2,s)
        key('Home');check('Home resets first builds',state()['build']==0)
        key('End');s=state();check('End completes last builds',s['id']==last['id'] and s['build']==s['total'],s)
        key('ArrowRight');check('last boundary stable',state()['build']==s['total'])
        for _ in range(s['total']): key('ArrowLeft')
        check('last slide reverse to zero',state()['build']==0)
        key('ArrowRight');check('last-slide keyboard build',state()['build']==1)
        command(str(SURF),'snap','--tab-id',tab,'--no-activate','--output',str(run/'diagram-first.png'))
        # Native input protection and presenter shared controller.
        key('Ctrl+Enter')
        presenter=js('return !!document.querySelector(".presenter-shell")')
        time.sleep(.2)
        if presenter:
            key('Home');key('ArrowRight');s=state();check('Presenter first build',s['id']=='m-cover' and s['build']==1,s);key('Escape')
        else: check('Presenter entry found',False)
        key('Home')
        # GUI authoring uses native controls; no hand-written JSON needed by authors.
        # wait() polls for the panel's async open (fetch + render); a fixed sleep raced and lost after reload.
        setup='const q=s=>document.querySelector(`[data-qid="deck:animations:${s}"]`);const sleep=ms=>new Promise(r=>setTimeout(r,ms));const wait=async s=>{for(let t=0;t<80;t++){const e=q(s);if(e)return e;await sleep(100)}throw new Error("missing control: "+s)};const set=(s,v)=>{const e=q(s);Object.getOwnPropertyDescriptor(e.tagName==="SELECT"?HTMLSelectElement.prototype:HTMLInputElement.prototype,"value").set.call(e,v);e.dispatchEvent(new Event(e.tagName==="SELECT"?"change":"input",{bubbles:true}))};'
        js(setup+'q("menu").click();await wait("effect");return true')
        opts=js(setup+'return [...q("effect").options].map(o=>o.value)')
        check('effect catalog enumerates 25 options',len(opts)==25 and len(set(opts))==25,opts)
        # Typing in a panel input must not advance builds or steal focus.
        js(setup+'q("duration_ms").focus();return document.activeElement===q("duration_ms")')
        command(str(SURF),'key','ArrowRight','--tab-id',tab,'--no-activate');time.sleep(.12)
        check('typing keys not hijacked',state()['build']==0 and js('return document.activeElement?.dataset.qid==="deck:animations:duration_ms"'))
        js(setup+'set("effect","fly");await sleep(100);set("direction","right");set("duration_ms","4000");await sleep(100);q("row:1").click();await sleep(100);set("start","after-previous");set("delay_ms","3000");await sleep(100);return q("start").value')
        check('preview no source write',source.read_bytes()==before)
        command(str(SURF),'snap','--tab-id',tab,'--no-activate','--output',str(run/'authoring.png'))
        js(setup+'q("apply").click();await sleep(1200);return true')
        after=json.loads(source.read_text());check('GUI persisted effect and timing',after['slides'][0]['animations'][0]['effect']=='fly' and after['slides'][0]['animations'][1]['start']=='after-previous',after['slides'][0]['animations'])
        original=copy.deepcopy(initial);edited=copy.deepcopy(after)
        for d in [original,edited]:
            for s in d['slides']: s.pop('animations',None);s.pop('reveal',None)
        check('only animation metadata changed',original==edited)
        js('location.reload();return true');time.sleep(1);key('Home');key('ArrowRight')
        s=state();check('after-previous delay real',next(t for t in s['targets'] if t['id']=='group')['hidden'],s)
        time.sleep(7.5);check('after-previous automatically runs',not next(t for t in state()['targets'] if t['id']=='group')['hidden'])
        key('ArrowLeft');time.sleep(7.5);check('reverse cancels delayed chain',next(t for t in state()['targets'] if t['id']=='group')['hidden'])
        # Real author-facing reduced-motion override; OS matchMedia branch is not emulated.
        js(setup+'q("menu").click();(await wait("reduce-motion")).click();q("cancel").click();return true')
        key('ArrowRight');check('reduced motion keeps manual step',state()['build']==1)
        reduced=js('const e=document.querySelector(".slide-viewport [data-animation-target=message]");return {transform:getComputedStyle(e).transform,durations:e.getAnimations().map(a=>a.effect.getTiming().duration)}')
        check('reduced motion immediate effect',all(d==0 for d in reduced['durations']),reduced)
        js(setup+'q("menu").click();(await wait("reduce-motion")).click();q("undo").click();await sleep(1100);return true')
        check('GUI undo source roundtrip',json.loads(source.read_text())==initial)
        export_checks(run, source, check)
        js('document.querySelector(`[data-qid="deck:export:menu"]`).click();return true')
        deadline=time.monotonic()+15
        while not js('return document.querySelector(`[data-qid="deck:export:pptx"]`)?.disabled===false'):
            if time.monotonic()>deadline: raise RuntimeError('export control did not become ready')
            time.sleep(.1)
        js('document.querySelector(`[data-qid="deck:export:pptx"]`).click();return true')
        deadline=time.monotonic()+120
        while True:
            warning=js('return document.querySelector(`[data-qid="deck:export:warnings"]`)?.innerText || ""')
            if warning: break
            if time.monotonic()>deadline: raise RuntimeError('export warnings were not shown')
            time.sleep(.2)
        check('unsupported export targets visible to author','Animation skipped:' in warning and 'diagram/node/' in warning,warning)
        # Initial and intermediate-frame Surf captures above are the per-trial
        # visual checkpoints. Export warnings are asserted through the live UI;
        # their expanded screenshot is retained separately in the delivery proof.
        cas_negatives()
        result['status']='PASS'
    except Exception as e:
        result.update(status='FAIL',error=str(e));raise
    finally:
        if tab:
            if result.get('status') == 'PASS': command(str(SURF),'tab.close',tab)
            else: result['retained_tab_id']=tab
        args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(result,indent=2));(run/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))

_P='{http://schemas.openxmlformats.org/presentationml/2006/main}'

def export_checks(run, source, check):
    """Structural p:timing + static-completeness proof. XML/ZIP inspection and a
    LibreOffice PDF are NOT native playback evidence; docs/ANIMATIONS.md keeps
    the per-effect matrix and the playback proof boundary."""
    pptx=run/'export.pptx'
    command(str(SKILL/'run.sh'),'emit-document-pptx','--document',str(source),'--asset-base',str(SKILL/'examples/sparta-explorer'),'--output',str(pptx))
    z=zipfile.ZipFile(pptx)
    def slide(n):
        root=ET.fromstring(z.read(f'ppt/slides/slide{n}.xml'))
        names={c.get('id'):c.get('name') for c in root.iter() if c.tag.endswith('}cNvPr')}
        return root.find(f'{_P}timing'), names
    t1,names=slide(1)
    rows=[]
    for group_i,par in enumerate(t1.find(f'.//{_P}cTn[@nodeType="mainSeq"]/{_P}childTnLst')):
        for c in par.findall(f'.//{_P}cTn[@presetClass]'):
            rows.append({'group':group_i,'class':c.get('presetClass'),'preset':c.get('presetID'),
                         'node':c.get('nodeType'),'delay':c.find(f'{_P}stCondLst/{_P}cond').get('delay'),
                         'target':names.get(c.find(f'.//{_P}spTgt').get('spid')),
                         'durs':sorted({x.get('dur') for x in c.findall(f'.//{_P}cTn') if x.get('dur') not in (None,'1')})})
    check('export timing targets and click order',
          [(r['group'],r['class'],r['node'],r['target'],r['durs']) for r in rows]==
          [(0,'entr','clickEffect','el:message',['600']),(1,'entr','clickEffect','el:group',['600']),
           (1,'emph','withEffect','el:message',['300'])],rows)
    check('export zero-build slide has no timing',slide(2)[0] is None)
    t3,names3=slide(3)
    spids3={c.get('spid') for c in t3.iter(f'{_P}spTgt')}
    check('export diagram nested targets skipped not silently retargeted',
          {names3.get(s) for s in spids3}=={'el:chevron-0','el:chevron-1'},sorted(names3.get(s) or s for s in spids3))
    # Same document minus animations: every slide XML must match except p:timing.
    plain_doc=json.loads(source.read_text())
    for s in plain_doc['slides']: s.pop('animations',None)
    plain_src=run/'document-plain.json'; plain_src.write_text(json.dumps(plain_doc))
    plain=run/'export-plain.pptx'
    command(str(SKILL/'run.sh'),'emit-document-pptx','--document',str(plain_src),'--asset-base',str(SKILL/'examples/sparta-explorer'),'--output',str(plain))
    zp=zipfile.ZipFile(plain)
    def stripped(zf,n):
        root=ET.fromstring(zf.read(f'ppt/slides/slide{n}.xml'))
        for el in root.findall(f'{_P}timing'): root.remove(el)
        return ET.tostring(root)
    check('export only p:timing differs from animation-free emission',
          all(stripped(z,n)==stripped(zp,n) for n in (1,2,3)))
    command(str(SKILL/'run.sh'),'render','--pptx',str(pptx),'--output-dir',str(run/'render'),'--dpi','72')
    text=subprocess.run(['pdftotext',str(run/'render/export.pdf'),'-'],capture_output=True,text=True,check=True,timeout=60).stdout
    doc=json.loads(source.read_text())
    message=next(e['text'] for e in doc['slides'][0]['elements'] if e['id']=='message')
    check('static PDF shows full content not hidden first build',message.split()[0] in text and message.split()[-1] in text,
          {'probe':message,'pdf_chars':len(text)})

if __name__=='__main__': main()
