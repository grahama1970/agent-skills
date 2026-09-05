#!/usr/bin/env python3
"""Live authoring/navigation/debugger gate against Vite, Surf and VS Code.

Copies actual operational documents before editing; never writes the user's source.
No mocked browser, exporter or debugger. Capture permission is a separate human gate.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[3]
SKILL = ROOT / 'skills/pitchdeck'
SURF = ROOT / 'skills/surf/run.sh'
BASE = 'http://127.0.0.1:3006'


def command(*args):
    p = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=180)
    if p.returncode:
        raise RuntimeError(p.stdout + p.stderr)
    return p.stdout


def api(route, deck, body=None, headers=None):
    request = urllib.request.Request(BASE + route, data=json.dumps(body).encode() if body is not None else None,
        headers={'X-Pitchdeck-Deck': deck, 'Content-Type': 'application/json', **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--negative', action='store_true')
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    os.environ.setdefault('SPARTA_PUBLIC_ROOT', '/mnt/storage12tb/skills/pitchdeck/sources/sparta-public')
    os.environ.setdefault('SPARTA_CANONICAL_ROOT', '/mnt/storage12tb/skills/pitchdeck/sources/sparta-canonical')
    os.environ.setdefault('SPARTA_ROOT', str(ROOT.parent / 'sparta'))
    result = {'schema': 'pitchdeck.usability_live.v1', 'live': True, 'mocked': False, 'checks': []}
    tab = None
    debug_url = None
    debug_slide = None
    source_path = SKILL / 'src/pitchdeck/document_pptx.py'
    source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    result['debuggee_source_sha256'] = source_hash
    try:
        if args.negative:
            for selected, extra in [('/../package.json', {}), ('/deck.data.json', {'Origin': 'https://untrusted.example'}), ('//outside/deck.data.json', {})]:
                status, error = api('/api/deck-context', selected, headers=extra)
                assert status == 409, (status, error)
                result['checks'].append({'deck': selected, 'status': status, 'error': error})
            status, error = api('/api/debugger', '/responsive-eval/deck.data.json', {'action': 'start', 'slide_id': 'not-a-real-slide'}, {'X-Pitchdeck-Control': '1'})
            assert status == 409, (status, error)
            result['checks'].append({'unmapped_debugger_refused': True, 'error': error})
        else:
            run = f'usability-{os.getpid()}-{time.time_ns()}'
            storage = Path('/mnt/storage12tb/skills/pitchdeck/outputs/usability-123-sync') / run
            storage.mkdir(parents=True)
            originals = [Path('/mnt/storage12tb/skills/pitchdeck/outputs/ticket-1278/approved.document.json'), SKILL / 'ui/public/deck.document.json']
            before = [p.read_bytes() for p in originals]
            decks = []
            for i, source in enumerate(originals):
                copy = storage / f'document-{i}.json'
                shutil.copy2(source, copy)
                output = SKILL / 'ui/public' / f'{run}-{i}'
                command(str(SKILL / 'run.sh'), 'emit-document-ui', '--document', str(copy), '--asset-base', str(SKILL / 'examples/sparta-explorer'), '--output-dir', str(output))
                decks.append((copy, output, f'/{output.name}/deck.data.json'))
            copied_before = [p.read_bytes() for p, _, _ in decks]
            doc = json.loads(copied_before[0])
            slide = doc['slides'][0]
            element = next(e for e in slide['elements'] if e['kind'] == 'text')
            status, edit = api('/api/slide-edit', decks[0][2], {'slide_id': slide['id'], 'field': f'element:{element["id"]}:size', 'value': '39', 'base_revision': 0})
            assert status == 200, (status, edit)
            assert decks[0][0].read_bytes() != copied_before[0]
            assert decks[1][0].read_bytes() == copied_before[1]
            status, stale = api('/api/slide-edit', decks[0][2], {'slide_id': slide['id'], 'field': f'element:{element["id"]}:size', 'value': '38', 'base_revision': 0})
            assert status == 409, (status, stale)
            result['checks'].append({'isolated_edit': True, 'stale_revision_refused': True})
            for copy, output, url in decks:
                status, exported = api('/api/export', url, {'format': 'pptx'})
                assert status == 200, (status, exported)
                artifact = SKILL / 'ui/public' / exported['url'].lstrip('/')
                assert hashlib.sha256(artifact.read_bytes()).hexdigest() == exported['sha256']
                with zipfile.ZipFile(artifact) as package:
                    slides = [n for n in package.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml', n)]
                expected = len([s for s in json.loads(copy.read_text())['slides'] if not s.get('hidden')])
                assert len(slides) == expected
                result['checks'].append({'export': exported, 'reopened_slide_count': len(slides)})
            copy, output, url = decks[0]
            # Install a real launch and explicit slide-to-source mapping, but do
            # not run a debuggee until the UI's Run button is invoked below.
            source = ROOT / 'skills/pitchdeck/src/pitchdeck/document_pptx.py'
            line = next(i for i, text in enumerate(source.read_text().splitlines(), 1) if 'band_cfg = theme.get' in text)
            command('python3', str(SKILL / 'scripts/configure_debugger.py'), '--deck-data', str(output / 'deck.data.json'), '--slide-id', slide['id'], '--file', str(source.relative_to(ROOT)), '--line', str(line), '--local', 'root', '--launch-name', 'Pitchdeck: usability live eval', '--create-export-launch')
            target = BASE + '/?deck=' + url
            created = command(str(SURF), 'window.new', target, '--unfocused', '--width', '1100', '--height', '1080')
            tab = re.search(r'\(tab (\d+)\)', created).group(1)
            def surf(*argv):
                return command(str(SURF), *argv, '--tab-id', tab, '--no-activate')
            def js(code):
                return json.loads(surf('js', 'return (async()=>{' + code + '})()'))
            def ready():
                for _ in range(100):
                    try:
                        if js('return document.readyState === "complete" && !!document.querySelector(".slide-viewport");'): return
                    except RuntimeError as e:
                        if 'context' not in str(e): raise
                    time.sleep(.1)
                raise RuntimeError('Browser app did not load')
            ready()
            payload = json.loads((output / 'deck.data.json').read_text())
            ids = [s['id'] for s in payload['slides'] if not s['hidden']]
            js('document.querySelector("[data-qid=\\"deck:nav:next\\"]").click(); return true;')
            time.sleep(.3)
            assert js('return location.hash;') == '#/slide/' + ids[1]
            surf('tab.reload'); ready()
            assert js('return document.querySelector(".slide-viewport").dataset.slideId;') == ids[1]
            js('document.querySelector("[data-qid=\\"deck:nav:next\\"]").click();return true;'); time.sleep(.3)
            js('history.back();return true;'); time.sleep(.3)
            assert js('return document.querySelector(".slide-viewport").dataset.slideId;') == ids[1]
            js('const e=document.querySelector("[data-qid=\\"deck:search\\"]");Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set.call(e,' + json.dumps(ids[0]) + ');e.dispatchEvent(new Event("input",{bubbles:true}));return true;')
            time.sleep(.3)
            js('document.querySelector(' + json.dumps(f'[data-qid="deck:search:{ids[0]}"]') + ').click();return true;'); time.sleep(.3)
            assert js('return document.querySelector(".slide-viewport").dataset.slideId;') == ids[0]
            result['checks'].append({'stable_link_reload_search_history': True})
            js('document.querySelector("[data-qid=\\"deck:rehearse\\"]").click();return true;'); time.sleep(.3)
            assert js('return !document.querySelector(".deck-header") && !document.querySelector("[data-qid=\\"deck:pane:chat\\"]") && !!document.querySelector("[data-qid=\\"deck:record:start\\"]");')
            result['checks'].append({'clean_rehearsal': True, 'recording_permission': 'not-requested-by-eval'})
            js('document.querySelector("[data-qid=\\"deck:debug:sync\\"]").click();return true;')
            for _ in range(40):
                time.sleep(.25)
                _, state = api('/api/debugger?slide=' + ids[0], url)
                if state['status'] == 'revealed': break
            assert state['status'] == 'revealed', state
            # Let polling expose the settled mapping/button, then click Run.
            js('for(let i=0;i<100;i++){const b=document.querySelector("[data-qid=\\"deck:debug:start\\"]");if(b&&!b.disabled){b.click();return true;}await new Promise(r=>setTimeout(r,100));}throw new Error("Run button unavailable");')
            debug_url, debug_slide = url, ids[0]
            for _ in range(100):
                time.sleep(.3)
                _, state = api('/api/debugger?slide=' + ids[0], url)
                if state['status'] in ['stopped', 'error']: break
            result['debugger_observation'] = state
            assert hashlib.sha256(source_path.read_bytes()).hexdigest() == source_hash, 'Debuggee source changed during eval; evidence is invalid'
            assert state['status'] == 'stopped', state
            stop = state['receipt']['stoppedState']
            assert stop['reason'] == 'breakpoint' and stop['frame']['line'] == line
            assert stop['expanded']['root']['children']['w']['value'] == '13.333'
            assert stop['expanded']['root']['children']['h']['value'] == '7.5'
            pause_path = storage / 'paused.json'; pause_path.write_text(json.dumps(state, indent=2))
            result['checks'].append({'ui_debugger_breakpoint': line, 'paused_receipt': str(pause_path), 'locals': stop['expanded']['root']['children']})
            session = state['session']
            status, stale = api('/api/debugger', url, {'action': 'continue', 'slide_id': ids[0], 'session_id': session['vscodeSessionId'], 'stop_sequence': 0}, {'X-Pitchdeck-Control':'1'})
            assert status == 409
            for action in ['inspect', 'stepOver', 'continue']:
                status, controlled = api('/api/debugger', url, {'action': action, 'slide_id': ids[0], 'session_id': session['vscodeSessionId'], 'stop_sequence': session['stopSequence']}, {'X-Pitchdeck-Control':'1'})
                assert status == 200 and controlled['status'] != 'error', controlled
                session = controlled.get('session') or session
                proof = storage / (action + '.json'); proof.write_text(json.dumps(controlled, indent=2))
                result['checks'].append({'debugger_action': action, 'status': controlled['status'], 'receipt': str(proof)})
            assert controlled['status'] == 'terminated', controlled
            shot = str(storage / 'rehearsal-debugger.png'); surf('snap', '--output', shot)
            result['screenshot'] = shot
            assert [p.read_bytes() for p in originals] == before, 'User source was changed'
            result['user_sources_unchanged'] = True
            assert hashlib.sha256(source_path.read_bytes()).hexdigest() == source_hash, 'Debuggee source changed during eval'
        result['status'] = 'PASS'
    except Exception as error:
        result.update(status='FAIL', error=str(error))
    finally:
        if debug_url:
            try:
                _, latest = api('/api/debugger?slide=' + debug_slide, debug_url)
                session = latest.get('session')
                if session and session.get('status') != 'terminated':
                    result['debugger_cleanup'] = api('/api/debugger', debug_url, {'action': 'terminate', 'slide_id': debug_slide, 'session_id': session['vscodeSessionId'], 'stop_sequence': session['stopSequence']}, {'X-Pitchdeck-Control': '1'})
            except Exception as cleanup_error:
                result['cleanup_error'] = str(cleanup_error)
        if tab and result.get('status') == 'PASS': command(str(SURF), 'tab.close', tab)
        result['tab_id'] = tab
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'receipt': str(args.out), 'error': result.get('error')}))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
