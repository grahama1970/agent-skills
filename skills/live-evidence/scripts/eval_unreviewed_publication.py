#!/usr/bin/env python3
"""Exercise the live HTTP path: source retrieval is not answer-review approval."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

from eval_interview_loop import free_port, post_turn, write_profile
from eval_ui_surf_controls import surf, surf_click, surf_new_tab, surf_js


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    reviewed = '--reviewed' in sys.argv
    manual_mode = '--manual' in sys.argv
    ui_mode = '--ui' in sys.argv
    receipt_path = Path('/tmp/live-evidence-reviewed-publication.json' if reviewed else '/tmp/live-evidence-unreviewed-publication.json')
    with tempfile.TemporaryDirectory(prefix='le-unreviewed-') as temporary:
        temp = Path(temporary)
        repo = temp / 'evalrepo'
        repo.mkdir()
        (repo / 'evidence_loop.py').write_text(
            "def evidence_loop():\n    return 'evidence-loop routes interviewer questions into ambient hud cards'\n"
        )
        profile = temp / 'profile.yaml'
        write_profile(profile)
        port = free_port()
        env = {**os.environ, 'LIVE_EVIDENCE_REPOS': str(repo),
               'LIVE_EVIDENCE_DATA_DIR': str(temp / 'data'),
               'LIVE_EVIDENCE_PROFILE': str(profile),
               'LIVE_EVIDENCE_ASK_RUNNER': '',
               'MEMORY_SERVICE_URL': 'http://127.0.0.1:9',
               'LIVE_EVIDENCE_HTTP_TIMEOUT': '0.3'}
        if reviewed:
            env.update(LIVE_EVIDENCE_ASK_RUNNER=str(root.parent / 'ask/run.sh'),
                       LIVE_EVIDENCE_ASK_ALLOW_PROVIDER_CALLS='1', LIVE_EVIDENCE_ASK_TIMEOUT='240')
        with (temp / 'server.log').open('w') as log:
            process = subprocess.Popen(
                [sys.executable, '-m', 'live_evidence', 'serve', '--host', '127.0.0.1',
                 '--port', str(port), '--no-browser'], cwd=root, env=env,
                stdout=log, stderr=subprocess.STDOUT)
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=3) as client:
                for _ in range(80):
                    try:
                        if client.get('/api/health').is_success:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.1)
                else:
                    raise RuntimeError((temp / 'server.log').read_text())
                client.post('/api/session/start', json={'consent_confirmed': True}).raise_for_status()
                query = ('How does evidence_loop return the evidence-loop text? Show its Python implementation, not a real routing system.'
                         if reviewed else 'How does the evidence-loop put interviewer questions into ambient hud cards?')
                if manual_mode:
                    manual_response = client.post('/api/search', json={'lane': 'ask', 'query': query}, timeout=260)
                    manual_response.raise_for_status()
                else:
                    post_turn(client, speaker='interviewer', sequence=1, text=query)
                decisions = []
                for _ in range(2400 if reviewed else 150):
                    response = client.get('/api/cards/publications')
                    response.raise_for_status()
                    decisions = response.json()
                    if decisions:
                        break
                    time.sleep(0.1)
                response = client.get('/api/state')
                response.raise_for_status()
                cards = response.json()['cards']
                passed = (bool(decisions) and not cards and
                          all(d['status'] == 'held' and
                              'answer_review_required' in d['reason_codes'] for d in decisions))
                checks = {}
                if not reviewed:
                    manual = client.post('/api/search', json={'lane': 'ripgrep',
                        'query': 'How does evidence_loop return evidence-loop text?'})
                    checks['manual_held_http_409'] = manual.status_code == 409
                    checks['manual_held_no_visible_card'] = not client.get('/api/state').json()['cards']
                    passed = passed and all(checks.values())
                if reviewed:
                    passed = False
                    if len(cards) == 1 and cards[0].get('answer_review'):
                        card = cards[0]
                        approval = card['answer_review']
                        run = Path(approval['run_dir'])
                        creator_dir = run / 'node-artifacts' / approval['creator_node']
                        reviewer_dir = run / 'node-artifacts' / approval['reviewer_node']
                        creator = json.loads((creator_dir / 'node-receipt.json').read_text())
                        reviewer = json.loads((reviewer_dir / 'node-receipt.json').read_text())
                        answer = (creator_dir / 'response.md').read_text().strip()
                        headings = ['### APPROACH', '### PSEUDOCODE', '### CODE',
                                    '### COMPLEXITY', '### OPTIMIZATIONS']
                        checks = {
                            'creator_live': creator.get('live') is True and creator.get('mocked') is False,
                            'reviewer_live': reviewer.get('live') is True and reviewer.get('mocked') is False,
                            'reviewer_approved': reviewer.get('ok') is True and reviewer.get('verdict') == 'PASS',
                            'card_reviewed': card.get('review_verdict') == 'ok',
                            'exact_creator_answer': card.get('answer') == answer,
                            'answer_digest_matches': hashlib.sha256(answer.encode()).hexdigest() == approval['answer_sha256'],
                            'required_sections': all(heading in answer.splitlines() for heading in headings),
                        }
                        passed = all(checks.values())
                screenshots = []
                session_control_readback = {}
                if ui_mode and passed:
                    tab = surf_new_tab(root, f'http://127.0.0.1:{port}/')
                    try:
                        time.sleep(1)
                        shot = f'/tmp/live-evidence-approved-{temp.name}.png'
                        surf(root, ['snap', '--tab-id', str(tab), '--no-activate', '--output', shot])
                        screenshots.append(shot)
                        if reviewed:
                            geometry = surf_js(root, tab, """return JSON.stringify((() => {
                              const pane = document.querySelector('[data-qid="flashcard-answer-pane"]');
                              const code = pane?.querySelector('pre');
                              const rect = code?.getBoundingClientRect();
                              return {noScroll: !!pane && pane.scrollHeight <= pane.clientHeight + 1 && pane.scrollWidth <= pane.clientWidth + 1,
                                      codeVisible: !!rect && rect.top >= 0 && rect.bottom <= innerHeight,
                                      nestedHeadingLeak: !!pane && pane.innerText.includes('###')};
                            })());""")
                            checks['primary_answer_no_scroll'] = geometry['noScroll']
                            checks['implementation_above_fold'] = geometry['codeVisible']
                            checks['no_raw_nested_headings'] = not geometry['nestedHeadingLeak']
                        initial = client.get('/api/state').json()['session']
                        for label, selector, expected in [
                            ('pause', 'status-pause-session', 'paused'),
                            ('play', 'status-start-session', 'listening'),
                        ]:
                            surf_click(root, tab, f'[data-qid="{selector}"]')
                            for _ in range(40):
                                observed = client.get('/api/state').json()['session']
                                if observed['status'] == expected:
                                    break
                                time.sleep(0.1)
                            checks[f'{label}_same_session'] = (observed['status'] == expected and observed['session_id'] == initial['session_id'])
                        surf_click(root, tab, '[data-qid="status-new-session"]')
                        for _ in range(200):
                            observed = client.get('/api/state').json()['session']
                            if observed['session_id'] != initial['session_id']:
                                break
                            time.sleep(0.1)
                        checks['new_session_identity'] = observed['session_id'] != initial['session_id']
                        checks['new_session_empty'] = not client.get('/api/state').json()['cards']
                        checks['new_session_requires_consent'] = (observed['consent_confirmed'] is False and observed['status'] != 'listening')
                        session_control_readback = {'before': initial, 'after_new': observed}
                        passed = passed and all(checks.values())
                    finally:
                        surf(root, ['tab.close', str(tab)])
                receipt = {'schema': 'live_evidence.unreviewed_publication_eval.v1',
                           'status': 'PASS' if passed else 'FAIL',
                           'proof_scope': ('Live local HTTP and Ask/Tau providers with synthetic source/question; no microphone or UI proof'
                                           if reviewed else 'Live local HTTP with synthetic source/question; no provider or microphone proof'),
                           'synthetic_inputs': True, 'provider_live': reviewed and bool(checks) and checks.get('creator_live', False) and checks.get('reviewer_live', False),
                           'checks': checks, 'manual_mode': manual_mode, 'screenshots': screenshots,
                           'session_control_readback': session_control_readback,
                           'cards': cards, 'decisions': decisions,
                           'lanes': response.json().get('lanes'), 'reviewed_run': reviewed}
                receipt_text = json.dumps(receipt, indent=2) + '\n'
                receipt_path.write_text(receipt_text)
                archive_path = receipt_path.with_name(f'{receipt_path.stem}-{temp.name}.json')
                archive_path.write_text(receipt_text)
                print(json.dumps({'status': receipt['status'], 'receipt': str(receipt_path), 'archive': str(archive_path)}))
                return 0 if passed else 1
        finally:
            receipt_path.with_suffix('.server.log').write_text((temp / 'server.log').read_text())
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == '__main__':
    raise SystemExit(main())
