#!/usr/bin/env python3
"""No-hardware lifecycle regression: real supervisor/HTTP, substitute recorder.

The substitute opens a heartbeat-writing subprocess, never an audio device.
Counts and surviving worker PIDs are read independently before fixture cleanup.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from live_evidence import listener
from live_evidence.config import InterviewProfile

CASES = ('pause_resume', 'new_session', 'consent_loss', 'backend_failure', 'normal_stop')


def run_case(case: str) -> dict:
    with tempfile.TemporaryDirectory(prefix='le-lifecycle-') as directory:
        root = Path(directory)
        capture = root / 'capture.jsonl'
        transcribe = root / 'stt.jsonl'
        session = {'session_id': 'fixture-session-one', 'status': 'listening', 'consent_confirmed': True}
        unavailable = threading.Event()
        recorders = []
        checks = {}
        worker_code = "import os,time,sys\nf=open(sys.argv[1],'a',buffering=1)\nwhile True:\n f.write(str(os.getpid())+'\\n'); time.sleep(.05)\n"

        class Recorder:
            def __init__(self, **kwargs):
                self.closed = threading.Event()
                self.worker = subprocess.Popen([sys.executable, '-c', worker_code, str(capture)])
                recorders.append(self)
            def text(self, callback):
                if not self.closed.wait(.05):
                    with transcribe.open('a') as f:
                        f.write('tick\n')
            def shutdown(self):
                self.closed.set()
                if self.worker.poll() is None:
                    self.worker.terminate()
                    self.worker.wait(timeout=3)

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                self.rfile.read(int(self.headers.get('Content-Length', '0')))
                self.reply()
            def do_GET(self):
                self.reply()
            def reply(self):
                self.send_response(503 if unavailable.is_set() else 200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'session': dict(session)}).encode())

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        serving = threading.Thread(target=server.serve_forever, daemon=True)
        serving.start()
        instance = listener.LiveListener(listener.ListenerOptions(
            backend_url=f'http://127.0.0.1:{server.server_port}',
            mode=listener.ListenMode.MICROPHONE, consent_confirmed=True,
        ), InterviewProfile(name='lifecycle-fixture'))
        def counts():
            return tuple(len(p.read_text().splitlines()) if p.exists() else 0 for p in (capture, transcribe))
        def alive():
            return [r.worker.pid for r in recorders if r.worker.poll() is None]
        errors = []
        def supervise():
            try:
                instance.run()
            except Exception as exc:
                errors.append(f'{type(exc).__name__}: {exc}')
        with patch.object(listener, '_load_recorder', return_value=Recorder), patch.object(listener, '_install_signal_handlers'):
            supervisor = threading.Thread(target=supervise, daemon=True)
            supervisor.start()
            try:
                for _ in range(100):
                    if counts()[0] >= 3: break
                    time.sleep(.05)
                checks['capture_started'] = counts()[0] >= 3
                if case == 'pause_resume':
                    session['status'] = 'paused'
                    time.sleep(1.5)
                    before = counts(); time.sleep(.4)
                    checks['pause_stops_capture_and_stt'] = counts() == before and not alive()
                    session['status'] = 'listening'
                    time.sleep(1.5)
                    before = counts(); time.sleep(.4)
                    checks['same_session_resume_restarts_capture'] = counts()[0] > before[0]
                elif case == 'new_session':
                    session['session_id'] = 'fixture-session-two'
                    time.sleep(1.5)
                    before = counts(); time.sleep(.4)
                    checks['new_session_stops_old_capture'] = counts() == before and not alive()
                elif case == 'consent_loss':
                    session.update(status='armed', consent_confirmed=False)
                    time.sleep(1.5)
                    before = counts(); time.sleep(.4)
                    checks['consent_loss_stops_capture'] = counts() == before and not alive()
                elif case == 'backend_failure':
                    unavailable.set()
                    supervisor.join(timeout=12)
                    checks['backend_failure_terminates_supervisor'] = not supervisor.is_alive()
                    checks['backend_failure_closes_workers'] = not alive()
                session['status'] = 'stopped'
                unavailable.clear()
                supervisor.join(timeout=3)
                checks['terminal_cleanup'] = not supervisor.is_alive() and not alive()
                observed_workers = alive()
            finally:
                # Fixture cleanup is not counted as production cleanup proof.
                instance._stop.set()
                for recorder in recorders: recorder.shutdown()
                supervisor.join(timeout=3)
                server.shutdown(); server.server_close(); serving.join(timeout=3)
        return {'case': case, 'checks': checks, 'errors': errors,
                'worker_pids_before_fixture_cleanup': observed_workers,
                'passed': all(checks.values())}


def main() -> int:
    results = [run_case(case) for case in CASES]
    receipt = {'schema': 'live_evidence.listener_lifecycle_eval.v1',
               'status': 'PASS' if all(r['passed'] for r in results) else 'FAIL',
               'proof_scope': 'Fault-injected recorder subprocesses and controlled HTTP; production listener supervisor. No hardware, audio, Meet or provider calls.',
               'hardware_capture_opened': False, 'fixture_backed': True, 'cases': results}
    path = Path('/tmp/live-evidence-listener-lifecycle.json')
    path.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))
    return 0 if receipt['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
