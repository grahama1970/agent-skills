#!/usr/bin/env python3
"""#1599: real Surf UI -> Ask/Tau model -> preview -> apply/reload/undo.

Uses a copy of a real approved deck. No model/browser stubs. Negative mode also
starts the same Vite app with an invalid handler to prove fail-closed provider
configuration; that injected failure is not a successful provider call.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[3]
SKILL = ROOT / 'skills/pitchdeck'
SURF = ROOT / 'skills/surf/run.sh'
OUT = Path('/mnt/storage12tb/skills/pitchdeck/outputs/natural-language-editing')


def run(*args, **kwargs):
    p = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, timeout=240, **kwargs)
    if p.returncode:
        raise RuntimeError(p.stderr + p.stdout)
    return p.stdout


def api(port, route, url, body):
    req = urllib.request.Request(f'http://127.0.0.1:{port}/api/element-agent/{route}', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json', 'X-Pitchdeck-Deck': url})
    try:
        with urllib.request.urlopen(req, timeout=200) as response: return response.status, json.load(response)
    except urllib.error.HTTPError as e: return e.code, json.load(e)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--wording', action='store_true')
    parser.add_argument('--bound', action='store_true')
    parser.add_argument('--negative', action='store_true')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    os.environ.setdefault('SPARTA_PUBLIC_ROOT', '/mnt/storage12tb/skills/pitchdeck/sources/sparta-public')
    ident = uuid.uuid4().hex
    directory = OUT / ident
    directory.mkdir(parents=True)
    source = Path('/mnt/storage12tb/skills/pitchdeck/outputs/ticket-1278/approved.document.json')
    document = directory / 'document.json'
    shutil.copy2(source, document)
    original = document.read_bytes()
    (directory / 'original.document.json').write_bytes(original)
    output = SKILL / 'ui/public' / f'usability-nl-{ident}'
    url = f'/{output.name}/deck.data.json'
    result = {'schema': 'pitchdeck.natural_language_editing.v1', 'live': True, 'mocked': False, 'checks': []}
    tab = None
    process = None
    try:
        run(str(SKILL / 'run.sh'), 'emit-document-ui', '--document', str(document), '--asset-base', str(SKILL / 'examples/sparta-explorer'), '--output-dir', str(output))
        payload = output / 'deck.data.json'
        payload_before = payload.read_bytes()
        data = json.loads(payload_before)
        slide = next(s for s in data['slides'] if s['id'] == 'm-problem-solution') if args.bound else data['slides'][0]
        element = next(e for e in slide['elements'] if e['id'] == 'chevron-1') if args.bound else next(e for e in slide['elements'] if e.get('role') == ('message' if args.wording else 'title'))
        selected = {'client_id': str(uuid.uuid4()), 'sequence': 1, 'slide_id': slide['id'], 'element_id': element['id'], 'revision': data['revision']}
        if args.negative:
            assert api(3006, 'selection', url, {'selection': selected})[0] == 200
            newer = {**selected, 'sequence': 2, 'element_id': None}
            assert api(3006, 'selection', url, {'selection': newer})[0] == 200
            assert api(3006, 'propose', url, {'selection': selected, 'text': 'Enlarge this'})[0] == 409
            assert api(3006, 'selection', url, {'selection': {**newer, 'sequence': 3, 'element_id': 'missing'}})[0] == 409
            result['checks'].append('stale selection and missing element refused')
            # Change selection AFTER the real model request has captured its
            # context, not merely before submitting a stale envelope.
            from concurrent.futures import ThreadPoolExecutor
            selected = {**selected, 'sequence': 4}
            assert api(3006, 'selection', url, {'selection': selected})[0] == 200
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(api, 3006, 'propose', url, {'selection': selected, 'text': 'Make this heading noticeably larger without changing its words.'})
                observed = False
                for _ in range(100):
                    for context_path in Path('/mnt/storage12tb/skills/pitchdeck/outputs/element-agent').glob('*/context.json'):
                        context = json.loads(context_path.read_text())
                        if context['selection']['client_id'] == selected['client_id']:
                            observed = True; break
                    if observed: break
                    time.sleep(.1)
                assert observed, 'no captured live model context'
                assert api(3006, 'selection', url, {'selection': {**selected, 'sequence': 5, 'element_id': None}})[0] == 200
                code, rejected = future.result(timeout=180)
                assert code == 409 and 'Selection changed' in rejected['error'], rejected
                result['checks'].append({'selection_changed_during_model_call': rejected})
            assert document.read_bytes() == original and payload.read_bytes() == payload_before
            selected = {**selected, 'sequence': 6}
            assert api(3006, 'selection', url, {'selection': selected})[0] == 200
            code, candidate = api(3006, 'propose', url, {'selection': selected, 'text': 'Increase the headline font size slightly; keep the wording.'})
            assert code == 200 and candidate['status'] == 'PREVIEW', candidate
            document.write_bytes(original + b'\n')  # external edit of the test-owned copy
            code, stale_source = api(3006, 'apply', url, {'selection': selected, 'id': candidate['id']})
            assert code == 409 and document.read_bytes() == original + b'\n' and payload.read_bytes() == payload_before
            result['checks'].append({'changed_source_refused': stale_source})
            document.write_bytes(original)
            qualified = {**selected, 'sequence': 7, 'slide_id': 'm-problem-solution', 'element_id': 'qualifier'}
            assert api(3006, 'selection', url, {'selection': qualified})[0] == 200
            code, qualifier_refusal = api(3006, 'propose', url, {'selection': qualified, 'text': 'Remove this qualification entirely and say that every response is governed.'})
            assert code == 409 or qualifier_refusal.get('status') == 'QUESTION', qualifier_refusal
            assert document.read_bytes() == original and payload.read_bytes() == payload_before
            result['checks'].append({'required_qualifier_removal_refused': qualifier_refusal})
            # Same production boundary, deliberately invalid provider config.
            with (directory / 'unavailable-server.log').open('w') as log:
                process = subprocess.Popen(['pnpm', 'dev', '--host', '127.0.0.1', '--port', '3017', '--strictPort'], cwd=SKILL / 'ui', stdout=log, stderr=log, start_new_session=True, env={**os.environ, 'PITCHDECK_AGENT_HANDLER': 'missing-pitchdeck-eval-handler', 'PITCHDECK_AGENT_TIMEOUT_SECONDS': '15'})
                for _ in range(60):
                    if process.poll() is not None: raise RuntimeError('Failure-probe server exited; read unavailable-server.log')
                    try:
                        urllib.request.urlopen('http://127.0.0.1:3017/', timeout=1).close(); break
                    except OSError: time.sleep(.2)
                assert api(3017, 'selection', url, {'selection': selected})[0] == 200
                code, failed = api(3017, 'propose', url, {'selection': selected, 'text': 'Make this selected text larger.'})
                assert code == 409 and failed['status'] == 'REFUSED', failed
                result['checks'].append({'configured_handler_unavailable': failed, 'fault_injected': True})
            assert document.read_bytes() == original and payload.read_bytes() == payload_before
        else:
            created = run(str(SURF), 'window.new', f'http://127.0.0.1:3006/?deck={url}', '--unfocused', '--width', '1500', '--height', '1000')
            tab = re.search(r'\(tab (\d+)\)', created).group(1)
            def surf(*parts): return run(str(SURF), *parts, '--tab-id', tab, '--no-activate')
            def js(code): return json.loads(surf('js', 'return (async()=>{' + code + '})()'))
            def wait(code, seconds=100):
                until = time.monotonic() + seconds
                while time.monotonic() < until:
                    try:
                        value = js(code)
                        if value: return value
                    except RuntimeError as e:
                        if 'context' not in str(e): raise
                    time.sleep(.2)
                raise RuntimeError('UI condition did not settle: ' + code)
            wait('return !!document.querySelector(".slide-viewport");', 20)
            # Capture actual fetch responses without replacing their behavior.
            js('window.nlEvidence=[]; const originalFetch=window.fetch; window.fetch=async(...a)=>{const r=await originalFetch(...a);if(String(a[0]).startsWith("/api/element-agent/")){const copy=r.clone();copy.json().then(v=>window.nlEvidence.push({url:a[0],request:JSON.parse(a[1].body),status:r.status,response:v}));}return r;};return true;')
            def click(qid): js('document.querySelector(' + json.dumps(f'[data-qid="{qid}"]') + ').click();return true;')
            if args.bound:
                js('location.hash=' + json.dumps('#/slide/' + slide['id']) + '; return true;')
                wait('return document.querySelector(".slide-viewport").dataset.slideId===' + json.dumps(slide['id']) + ';')
            click('deck:mode:design')
            qid = f'deck:freeform:{slide["id"]}:{element["id"]}'
            wait('return !!document.querySelector(' + json.dumps(f'[data-qid="{qid}"]') + ');')
            click(qid)
            wait('return window.nlEvidence.some(e=>e.response.status==="SELECTED"&&e.response.selection.element_id===' + json.dumps(element['id']) + ');')
            prompt = ('Use an invitation to schedule, rather than book, an architecture walkthrough. Keep that meaning and phrase; do not add claims.' if args.wording else 'Please increase the selected text size by about twenty percent and shift it a little left. Leave every word exactly unchanged.')
            js('const e=document.querySelector("[data-qid=\\"deck:chat:claims:input\\"]");Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,"value").set.call(e,' + json.dumps(prompt) + ');e.dispatchEvent(new Event("input",{bubbles:true}));return true;')
            click('deck:chat:claims:send')
            proposal = wait('return window.nlEvidence.find(e=>e.url.endsWith("/propose")) || null;')
            assert proposal['status'] == 200 and proposal['response']['status'] == 'PREVIEW', proposal
            proposed = proposal['response']
            assert document.read_bytes() == original and payload.read_bytes() == payload_before, 'preview changed source'
            assert js('return document.querySelector(' + json.dumps(f'[data-qid="{qid}"]') + ').dataset.agentPreview;') == 'true'
            screenshot = directory / 'proposal.png'; surf('snap', '--output', str(screenshot))
            click('deck:agent:preview')
            assert js('return document.querySelector(' + json.dumps(f'[data-qid="{qid}"]') + ').dataset.agentPreview;') == 'false'
            click('deck:agent:preview')
            click('deck:agent:apply')
            applied = wait('return window.nlEvidence.find(e=>e.url.endsWith("/apply")) || null;')
            assert applied['status'] == 200, applied
            before_doc = json.loads(original); after_doc = json.loads(document.read_bytes())
            (directory / 'applied.document.json').write_bytes(document.read_bytes())
            (directory / 'applied.deck.data.json').write_bytes(payload.read_bytes())
            before_el = next(e for s in before_doc['slides'] if s['id'] == slide['id'] for e in s['elements'] if e['id'] == element['id'])
            after_el = next(e for s in after_doc['slides'] if s['id'] == slide['id'] for e in s['elements'] if e['id'] == element['id'])
            if args.bound:
                context = json.loads((Path(proposed['agent_receipt']).parents[4] / 'context.json').read_text())
                assert context['deck_id'] == data['deck_id'] and context['claims'] and context['sources'], context
                assert context['element']['bindings'], context
                result['checks'].append({'bound_context': context})
            if args.wording:
                assert after_el['text'] != before_el['text'] and 'architecture walkthrough' in after_el['text'].lower()
                assert after_doc['provenance']['preview_unapproved_renderings'] == 'true'
            else:
                assert after_el['style']['size_pt'] > before_el['style']['size_pt'] and after_el['bbox']['x'] < before_el['bbox']['x']
                assert after_el['text'] == before_el['text']
            for old, new in zip(before_doc['slides'], after_doc['slides']):
                for a, b in zip(old['elements'], new['elements']):
                    if old['id'] != slide['id'] or a['id'] != element['id']: assert a == b, 'non-target changed'
            result['checks'].append({'prompt': prompt, 'proposal': proposed, 'only_selected_element_changed': True, 'screenshot': str(screenshot)})
            # Reload must keep the committed change and offer guarded Undo after reselecting.
            surf('tab.reload'); wait('return !!document.querySelector(".slide-viewport");', 20)
            click('deck:mode:design'); time.sleep(.3); click(qid)
            wait('return !!document.querySelector("[data-qid=\\"deck:agent:undo\\"]");')
            click('deck:agent:undo')
            until = time.monotonic() + 15
            while document.read_bytes() != original and time.monotonic() < until: time.sleep(.2)
            assert document.read_bytes() == original, 'Undo failed to restore source bytes'
            result['checks'].append('reload and guarded Undo restored source bytes')
            # Replaying an already-applied proposal cannot write after Undo/revision change.
            status, stale = api(3006, 'apply', url, {'id': proposed['id'], 'selection': proposal['request']['selection']})
            assert status == 409
            result['checks'].append({'stale_apply_refused': stale})
        result['status'] = 'PASS'
    except Exception as e:
        result.update(status='FAIL', error=str(e))
    finally:
        if process:
            import signal
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=10)
        if tab and result.get('status') == 'PASS': run(str(SURF), 'tab.close', tab)
        result['tab_id'] = tab
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'receipt': str(args.out), 'error': result.get('error')}))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
