#!/usr/bin/env python3
"""Prove cockpit intents drive the real debugger bridge and native readback.

Runs the production API, UI events, the bridge command, and the actual VS Code
extension-owned artifacts. The debuggee is the skill-generated sample workspace,
never an imported command. Requires an open, trusted VS Code window for the
generated workspace; without it the reveal case reports BLOCKED honestly.
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


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--out-dir', type=Path)
    parser.add_argument('--live-vscode', action='store_true',
                        help='Require the trusted VS Code bridge for a real reveal readback.')
    args = parser.parse_args()
    out = args.out_dir or Path(tempfile.mkdtemp(prefix='explain-bridge-eval-'))
    out.mkdir(parents=True, exist_ok=True)
    checks: list[dict] = []
    report = {'schema': 'explain_project.bridge_execution_eval.v1', 'status': 'FAIL',
              'checks': checks,
              'proof_scope': 'Production API + bridge worker + owning debugger artifacts on a generated workspace. Reveal/native readback requires a trusted open VS Code window; no imported command execution, microphone, or board mutation.'}

    def check(name: str, passed: bool, detail) -> None:
        checks.append({'name': name, 'passed': bool(passed), 'detail': detail})
        if not passed:
            raise RuntimeError(name)

    port = free_port()
    repo = out / 'workspace'
    (repo / 'docs' / 'explain').mkdir(parents=True)
    api_log = (out / 'api.log').open('w')
    api = None
    try:
        explainers = repo / 'docs/explain/explainers.jsonl'
        subprocess.run([str(SKILL / 'run.sh'), 'sample', '--output', str(explainers)],
                       check=True, capture_output=True, text=True, timeout=120)
        record = json.loads(explainers.read_text().splitlines()[0])
        source = repo / record['source_ranges'][0]['file']
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text('\n'.join(f'line_{i} = {i}' for i in range(1, 260)) + '\n')
        api = subprocess.Popen([str(SKILL / 'run.sh'), 'cockpit', '--explainers', str(explainers),
                                '--repo', str(repo), '--port', str(port),
                                '--memory-url', 'http://127.0.0.1:9'],
                               stdout=api_log, stderr=subprocess.STDOUT, start_new_session=True)
        client = httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=5, trust_env=False)

        def ready() -> bool:
            try:
                return client.get('/api/health').status_code == 200
            except httpx.HTTPError:
                return False
        deadline = time.monotonic() + 60
        while not ready():
            if time.monotonic() >= deadline:
                raise RuntimeError('cockpit API did not start')
            time.sleep(.3)

        def dispatch(event_type: str, payload: dict | None = None) -> dict:
            state = client.get('/api/cockpit/bootstrap').json()['state']
            response = client.post('/api/cockpit/event', json={
                'schema': 'explain_project.cockpit_event.v1', 'event_id': 'evt-' + uuid4().hex,
                'type': event_type, 'expected_revision': state['revision'],
                'payload': payload or {}})
            response.raise_for_status()
            return response.json()

        def bridge(*extra: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run([str(SKILL / 'run.sh'), 'bridge', '--repo', str(repo),
                                   '--base-url', f'http://127.0.0.1:{port}',
                                   '--out-dir', str(out / 'bridge'), *extra],
                                  capture_output=True, text=True, timeout=120)

        foreign = client.post('/api/cockpit/event', headers={'origin': 'http://evil.example'},
                              json={'schema': 'explain_project.cockpit_event.v1',
                                    'event_id': 'evt-foreign', 'type': 'step.next',
                                    'expected_revision': 0, 'payload': {}})
        check('cross-origin mutation refused', foreign.status_code == 403
              and foreign.json()['failure_code'] == 'ORIGIN_REFUSED', foreign.status_code)

        idle = bridge()
        check('no intent yields IDLE without side effects', idle.returncode == 0
              and json.loads(idle.stdout)['status'] == 'IDLE', idle.stdout.strip())

        dispatch('explainer.select', {'feature_id': record['feature_id']})

        rendered = record['diagram']['rendered_svg_path']
        absent = client.get('/api/cockpit/diagram')
        check('missing diagram artifact is an honest 404', absent.status_code == 404
              and absent.json()['failure_code'] == 'DIAGRAM_ARTIFACT_MISSING', rendered)
        svg_path = repo / rendered
        svg_path.parent.mkdir(parents=True, exist_ok=True)
        svg_path.write_text('<svg xmlns="http://www.w3.org/2000/svg"><g id="probe"/></svg>')
        served = client.get('/api/cockpit/diagram')
        check('bound diagram artifact is served as svg bytes',
              served.status_code == 200
              and served.headers['content-type'] == 'image/svg+xml'
              and served.content == svg_path.read_bytes(),
              {'bytes': len(served.content)})

        dispatch('source.reveal.request')
        dry = bridge()
        payload = json.loads(dry.stdout)
        check('reveal intent defaults to a typed dry-run command', dry.returncode == 0
              and payload['status'] == 'DRY_RUN' and '--action' in payload['command']
              and 'reveal' in payload['command'], payload['command'][:8])

        executed = bridge('--execute')
        result = json.loads(executed.stdout)
        if args.live_vscode:
            state = client.get('/api/cockpit/bootstrap').json()['state']
            native = json.loads(Path(result['status_path']).read_text())
            receipt = result['receipt']
            check('live reveal applied through owning bridge', executed.returncode == 0
                  and result['status'] == 'APPLIED' and receipt['status'] == 'REVEALED'
                  and native['status'] == 'revealed' and native['reveal']['selected'] is True
                  and native['reveal']['file'] == str(source)
                  and state['integration_health']['source_reveal'] == 'READY'
                  and state['adapter_receipts'][-1]['receipt_id'] == receipt['receipt_id'],
                  {'status_path': result['status_path'], 'native': native['reveal']})
        else:
            check('without a trusted bridge the executor blocks honestly', executed.returncode == 1
                  and result['status'] == 'BLOCKED' and result['receipt']['status'] == 'BLOCKED'
                  and 'native readback' not in (result['receipt']['detail'] or ''),
                  result.get('detail'))

        dispatch('debugger.prepare.request')
        stale_probe = subprocess.Popen(
            [str(SKILL / 'run.sh'), 'bridge', '--repo', str(repo),
             '--base-url', f'http://127.0.0.1:{port}', '--out-dir', str(out / 'bridge'),
             '--execute'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        dispatch('step.next')
        stale_out, _ = stale_probe.communicate(timeout=120)
        stale = json.loads(stale_out)
        # IDLE means the supersede landed before the bridge even read an
        # intent; STALE means it landed between read and dispatch. Both are
        # safe: no receipt may be applied against the newer revision.
        check('superseded intent is never dispatched as current',
              stale['status'] in {'IDLE', 'STALE', 'BLOCKED'}
              and (stale['status'] != 'STALE' or stale['receipt'] is None or stale['status_path'] is None),
              stale['status'])

        report['status'] = 'PASS'
    except Exception as error:  # noqa: BLE001 - single eval boundary
        report['error'] = f'{type(error).__name__}: {error}'
    finally:
        if api is not None and api.poll() is None:
            os.killpg(api.pid, signal.SIGTERM)
            try:
                api.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(api.pid, signal.SIGKILL)
        api_log.close()
        (out / 'result.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print('BRIDGE_EXECUTION_' + report['status'] + ' ' + str(out / 'result.json'))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
