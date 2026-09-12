#!/usr/bin/env python3
"""Exercise external cockpit updates in real Chrome through Surf and live HTTP.

Starts disposable API/preview processes, never a separate browser. Question data
comes from the skill's sample command and is explicitly replay, not microphone
proof. Adversarial checks delay real HTTP responses and interleave real writes;
no server replies or adapter receipts are fabricated. Own processes/tabs only.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time
from uuid import uuid4

import httpx

SKILL = Path(__file__).resolve().parents[1]
SURF = SKILL.parent / 'surf' / 'run.sh'
PANES = ['cockpit:state:root', 'cockpit:teleprompter:stage',
         'cockpit:source:panel', 'cockpit:debugger:panel', 'cockpit:diagram:stage']


def run(*args: str, cwd: Path = SKILL) -> str:
    return subprocess.run(args, cwd=cwd, check=True, text=True,
                          capture_output=True, timeout=60).stdout


def decode(text: str):
    value = json.loads(text)
    return json.loads(value) if isinstance(value, str) else value


def port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def wait_for(predicate, label: str, seconds: float = 15):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(.3)
    raise RuntimeError(f'Timed out: {label}')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--out-dir', type=Path)
    args = parser.parse_args()
    out = args.out_dir or Path(tempfile.mkdtemp(prefix='explain-browser-sync-'))
    out.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex[:12]
    api_port, ui_port = port(), port()
    while ui_port == api_port:
        ui_port = port()
    url = f'http://127.0.0.1:{ui_port}/?sync-eval={token}'
    processes, logs, tabs, checks = [], [], [], []
    report = {'schema': 'explain_project.browser_sync_eval.v1', 'status': 'FAIL',
              'url': url, 'checks': checks, 'proof_scope': 'Real Chrome, compiled React, live HTTP; replayed question and injected response ordering; no microphone, VS Code execution or board edits.'}

    def save(name, data):
        (out / f'{name}.json').write_text(json.dumps(data, indent=2) + '\n')

    def check(name, condition, detail):
        checks.append({'name': name, 'passed': bool(condition), 'detail': detail})
        if not condition:
            raise RuntimeError(name)

    def spawn(command, name, cwd=SKILL, env=None):
        log = (out / f'{name}.log').open('w')
        logs.append(log)
        processes.append(subprocess.Popen(command, cwd=cwd, env=env,
                         stdout=log, stderr=subprocess.STDOUT, start_new_session=True))

    try:
        sample = out / 'explainers.jsonl'
        run(str(SKILL / 'run.sh'), 'sample', '--output', str(sample))
        record = json.loads(sample.read_text().splitlines()[0])
        run('npm', 'run', 'build', cwd=SKILL / 'ui')
        spawn([str(SKILL / 'run.sh'), 'cockpit', '--explainers', str(sample),
               '--port', str(api_port), '--memory-url', 'http://127.0.0.1:9'], 'api')
        spawn(['npm', 'run', 'preview', '--', '--port', str(ui_port), '--strictPort'],
              'preview', SKILL / 'ui', {**os.environ, 'EXPLAIN_PROJECT_API_URL': f'http://127.0.0.1:{api_port}'})
        with httpx.Client(base_url=url.split('/?')[0], timeout=5, trust_env=False) as client:
            def ready():
                try:
                    return client.get('/api/health').status_code == 200
                except httpx.HTTPError:
                    return False
            wait_for(ready, 'API through preview')
            run(str(SURF), 'tab.new', url, '--no-activate', '--json')
            targets = [t for t in decode(run(str(SURF), 'tab.list', '--json')) if t['url'] == url]
            check('exact tab identity', len(targets) == 1, targets)
            tabs.append(targets[0]['id'])
            tab = str(tabs[0])
            report['tab_id'] = tabs[0]

            def js(source):
                return decode(run(str(SURF), 'js', source, '--tab-id', tab, '--no-activate', '--json'))

            def dom():
                return js('JSON.stringify({panes:' + json.dumps(PANES) + '.map(q=>{const e=document.querySelector(`[data-qid="${q}"]`);return {qid:q,revision:e?.dataset.revision,text:e?.innerText}}),error:document.querySelector(\'[data-qid="cockpit:state:error"]\')?.innerText,timeOrigin:performance.timeOrigin})')

            def bootstrap():
                response = client.get('/api/cockpit/bootstrap')
                response.raise_for_status()
                return response.json()

            def post(path, payload):
                response = client.post(path, json=payload)
                response.raise_for_status()
                return response.json()

            def observed(state, name):
                last = {}
                def synced():
                    nonlocal last
                    last = dom()
                    save(name + '-dom', last)
                    return last if all(p.get('revision') == str(state['revision']) for p in last['panes']) else None
                result = wait_for(synced, name)
                save(name + '-api', state)
                source = state['source']['location']
                text = result['panes'][0]['text']
                check(name, state['teleprompter']['title'] in text and source['file'] in text,
                      {'revision': state['revision'], 'panes': [p['revision'] for p in result['panes']]})
                return result

            def click(qid):
                run(str(SURF), 'click', f'[data-qid="{qid}"]', '--tab-id', tab, '--no-activate', '--json')

            def fill(qid, value):
                return js('''(() => { const e=document.querySelector(''' + json.dumps(f'[data-qid="{qid}"]') + ''');
                  const prototype=e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
                  Object.getOwnPropertyDescriptor(prototype,'value').set.call(e,''' + json.dumps(value) + ''');
                  e.dispatchEvent(new Event('input',{bubbles:true})); return JSON.stringify({value:e.value}); })()''')

            wait_for(lambda: dom()['panes'][0].get('revision') == '0', 'initial render')
            run(str(SURF), 'snap', '--tab-id', tab, '--output', str(out / 'before.png'), '--json')
            origin = dom()['timeOrigin']
            input_selector = '[data-qid="cockpit:question:manual-input"]'
            check('compiled layout utilities are effective',
                  js('JSON.stringify(getComputedStyle(document.querySelector(' + json.dumps(input_selector) + ').parentElement).display)') == 'flex', 'question row display:flex')
            fill('cockpit:question:manual-input', 'Unsubmitted draft ' + token)
            text = record['question']
            candidate = {'schema': 'live_evidence.question_candidate.v1',
                         'question_id': 'sync-question-' + token, 'normalized_question': text,
                         'speaker': 'interviewer', 'source_event_ids': ['event-' + token],
                         'source_spans': [{'event_id': 'event-' + token, 'sequence': 1,
                                          'start_offset': 0, 'end_offset': len(text)}],
                         'start_sequence': 1, 'end_sequence': 1, 'trigger_reason': 'question_mark',
                         'fingerprint': 'fingerprint-' + token}
            accepted = post('/api/intake/live-evidence', candidate)
            observed(accepted['state'], 'external-replay-updates-open-tab')
            check('replay is labelled, not microphone proof',
                  'Live Evidence (replay)' in dom()['panes'][0]['text'], accepted['state']['question']['source'])
            check('external update preserves unfinished question',
                  js('JSON.stringify(document.querySelector(' + json.dumps(input_selector) + ').value)') == 'Unsubmitted draft ' + token, 'draft retained')
            duplicate = post('/api/intake/live-evidence', candidate)
            check('duplicate does not advance revision', duplicate['status'] == 'DUPLICATE'
                  and bootstrap()['state']['revision'] == accepted['state']['revision'], duplicate['status'])

            fill('cockpit:question:manual-input', text)
            click('cockpit:question:manual-submit')
            manual = wait_for(lambda: (s if (s := bootstrap()['state'])['question']['source'] == 'manual' else None), 'manual question')
            observed(manual, 'existing-manual-question-path')
            click('cockpit:step:next')
            state = wait_for(lambda: (s if (s := bootstrap()['state'])['selection']['step_index'] == 1 else None), 'next')
            observed(state, 'existing-next-path')
            click('cockpit:step:previous')
            state = wait_for(lambda: (s if (s := bootstrap()['state'])['selection']['step_index'] == 0 else None), 'previous')
            observed(state, 'existing-previous-path')

            # Interleave another real write immediately before the UI request.
            js('''(() => { const native = window.fetch.bind(window); window.__race = null;
              window.fetch = async (input, init) => {
                if (String(input) === '/api/cockpit/event') {
                  window.fetch = native;
                  const b = await (await native('/api/cockpit/bootstrap')).json();
                  const response = await native('/api/cockpit/event', {method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({schema:'explain_project.cockpit_event.v1',event_id:crypto.randomUUID(),type:'step.next',expected_revision:b.state.revision,payload:{}})});
                  const changed = await response.json();
                  const stale = await native(input, init);
                  window.__race = {externalRevision:changed.revision,status:stale.status};
                  return stale;
                } return native(input, init);
              }; return JSON.stringify({armed:true}); })()''')
            click('cockpit:step:next')
            race = wait_for(lambda: js('JSON.stringify(window.__race)'), 'stale request 409')
            state = bootstrap()['state']
            result = observed(state, 'conflict-refresh')
            check('stale action not replayed', race['status'] == 409 and state['revision'] == race['externalRevision']
                  and state['selection']['step_index'] == 1 and 'not replayed' in (result.get('error') or ''), race)
            click('cockpit:step:next')
            state = wait_for(lambda: (s if (s := bootstrap()['state'])['selection']['step_index'] == 2 else None), 'explicit retry')
            observed(state, 'explicit-retry')
            check('successful action clears error', not dom().get('error'), dom().get('error'))

            # Hold a real older bootstrap response while a local action succeeds.
            js('''(() => { const native = window.fetch.bind(window); window.__held = false;
              window.fetch = async (input, init) => {
                const response = await native(input, init);
                if (String(input) === '/api/cockpit/bootstrap') {
                  window.fetch = native; window.__held = true;
                  await new Promise(resolve => {window.__release = resolve});
                } return response;
              }; return JSON.stringify({armed:true}); })()''')
            wait_for(lambda: js('JSON.stringify(window.__held)'), 'pending older snapshot')
            click('cockpit:step:previous')
            state = wait_for(lambda: (s if (s := bootstrap()['state'])['selection']['step_index'] == 1 else None), 'local update while poll held')
            observed(state, 'newer-action-response')
            js('(() => { window.__release(); return JSON.stringify({released:true}); })()')
            time.sleep(.4)
            observed(state, 'late-snapshot-does-not-regress')

            imported = json.loads(json.dumps(record))
            imported['feature_id'] = 'external.' + token
            imported['title'] = 'External catalog ' + token
            latest = post('/api/cockpit/explainers', {'record': imported})
            observed(latest['state'], 'external-catalog-revision')
            selector = '[data-qid="cockpit:explainer:item:' + imported['feature_id'] + '"]'
            check('external import appears without reload', js('JSON.stringify(!!document.querySelector(' + json.dumps(selector) + '))'), imported['feature_id'])
            fill('cockpit:explainer:page-input', '1')
            jumped = wait_for(lambda: (s if (s := bootstrap()['state'])['selection']['feature_id'] == imported['feature_id'] else None), 'one-based first explainer')
            observed(jumped, 'one-based-navigation')
            fill('cockpit:explainer:page-input', '2')
            wait_for(lambda: bootstrap()['state']['selection']['feature_id'] == record['feature_id'], 'second explainer')
            click('cockpit:explainer:paste-toggle')
            fill('cockpit:explainer:paste-editor', '{')
            before_invalid = bootstrap()['state']['revision']
            click('cockpit:explainer:paste-apply')
            check('invalid paste does not change backend', bootstrap()['state']['revision'] == before_invalid, before_invalid)
            imported['title'] = 'Pasted catalog ' + token
            fill('cockpit:explainer:paste-editor', json.dumps(imported))
            click('cockpit:explainer:paste-apply')
            def imported_ready():
                b = bootstrap()
                return b if any(e['title'] == imported['title'] for e in b['explainers']) else None
            updated = wait_for(imported_ready, 'pasted explainer import')
            observed(updated['state'], 'conditional-paste-editor-and-apply')
            check('successful paste closes editor', js('JSON.stringify(!document.querySelector(\'[data-qid="cockpit:explainer:paste-editor"]\'))'), 'editor closed')
            check('page was never reloaded', dom()['timeOrigin'] == origin, origin)
            check('no unintended adapter effects', not latest['state']['source']['reveal_intent']
                  and not latest['state']['debugger']['prepare_intent']
                  and latest['state']['diagram']['highlight_intent']['mutation_allowed'] is False,
                  latest['state']['integration_health'])
            run(str(SURF), 'snap', '--tab-id', tab, '--output', str(out / 'after.png'), '--json')
            report['status'] = 'PASS'
    except Exception as exc:
        report['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        for tab_id in tabs:
            try:
                run(str(SURF), 'tab.close', str(tab_id), '--json')
            except Exception as exc:
                report['cleanup_error'] = str(exc)
                report['status'] = 'FAIL'
        for process in reversed(processes):
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
        for log in logs:
            log.close()
        save('result', report)
    print(json.dumps(report, indent=2))
    print('BROWSER_SYNC_' + report['status'] + ' ' + str(out / 'result.json'))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
