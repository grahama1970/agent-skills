#!/usr/bin/env python3
"""Agentic eval: requirement ledger + clarification amendments (#1454).

Live HTTP against a real server. The stage-1 resolver runs from a scripted
verdict fixture (one verdict per candidate), and the Ask runner appends to an
invocation ledger, so "the solver never ran" is read from an artifact the
solver path itself produces. Covers the ticket's deterministic proofs:
period-is-not-completion, blocking clarification holds Ask at zero, partial
answer keeps it held, stale-revision rejection, resolution runs Ask exactly
once, duplicate answers are idempotent, assumptions are labeled and
digest-bound, spoken non-question turns bind as speech answers, and an
invented requirement without ASSUMED provenance fails validation.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

failures: list[str] = []


def check(name: str, passed: bool, detail: str) -> None:
    print(f"{name}: {'PASS' if passed else 'FAIL'} ({detail})")
    if not passed:
        failures.append(name)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def post(base: str, path: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        base + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as exc:
        try:
            body = json.load(exc)
        except Exception:
            body = {}
        return exc.code, body


def get(base: str, path: str) -> dict:
    with urllib.request.urlopen(base + path, timeout=30) as resp:
        return json.load(resp)


BLOCKED_VERDICT = {
    "question_asked_yet": True, "question_complete": True, "ready_to_answer": True,
    "blocking_reason": "none", "question_type": "code", "actionable": True,
    "canonical_question": "Write a Python function that parses the log and returns the top entries.",
    "confidence": 0.9,
    "clarifying_questions": [
        {"id": "c1", "question": "What is the exact input format?", "blocking": True},
        {"id": "c2", "question": "In what order should results be returned?", "blocking": True},
        {"id": "c3", "question": "How large can the log get?", "blocking": False,
         "default_assumption": "Assume the log fits in memory."},
    ],
}
VERDICTS = [BLOCKED_VERDICT, BLOCKED_VERDICT]


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    from live_evidence.question_window import _has_imperative_clause
    check("given clause distinguishes request from description",
          _has_imperative_clause('given a raw log, write a python parser.')
          and not _has_imperative_clause('given a raw log, we write records to disk.'),
          'imperative accepted; description rejected')
    from live_evidence.scanner_fallback import fallback_scan
    check("default scanner preserves imperative and rejects description",
          len(fallback_scan([{'speaker': 'interviewer', 'text': 'Given the raw log, write a Python function returning counts.'}], [])) == 1
          and not fallback_scan([{'speaker': 'interviewer', 'text': 'Given the raw log, we write records to disk.'}], []),
          'deterministic default-scanner check; no provider')
    with tempfile.TemporaryDirectory(prefix="le-ledger-") as temp_name:
        temp = Path(temp_name)
        repo = temp / "repo"
        repo.mkdir()
        (repo / "parser.py").write_text("def parse_log(text):\n    return text.splitlines()\n")
        (temp / "profile.yaml").write_text(
            "name: ledger-eval\nwatch_terms:\n  - python\n  - stack\n  - log\n"
        )
        fixture = temp / "verdicts.json"
        fixture.write_text(json.dumps(VERDICTS))
        ask_ledger = temp / "ask-invocations.log"
        runner = temp / "ask.sh"
        runner.write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\n"
            f'echo invoked >> "{ask_ledger}"\n'
            'd="${LIVE_EVIDENCE_ASK_FIXTURE_RUN_DIR:?}"\n'
            'mkdir -p "$d/node-artifacts/handler-fixture"\n'
            'printf "Ask solution: parse then sort.\\n" > "$d/node-artifacts/handler-fixture/response.md"\n'
            'printf \'{"run_dir":"%s"}\\n\' "$d"\n'
        )
        runner.chmod(0o755)
        env = {
            **os.environ,
            "LIVE_EVIDENCE_REPOS": str(repo),
            "LIVE_EVIDENCE_DATA_DIR": str(temp / "data"),
            "LIVE_EVIDENCE_PROFILE": str(temp / "profile.yaml"),
            "LIVE_EVIDENCE_RESOLVER_FIXTURE": str(fixture),
            "LIVE_EVIDENCE_SCANNER_MODE": "false",
            "LIVE_EVIDENCE_ASK_RUNNER": str(runner),
            "LIVE_EVIDENCE_ASK_HANDLER": "fixture",
            "LIVE_EVIDENCE_ASK_TIMEOUT": "30",
            "LIVE_EVIDENCE_ASK_FIXTURE_RUN_DIR": str(temp / "askrun"),
            "MEMORY_SERVICE_URL": "http://127.0.0.1:9",
        }
        port = free_port()
        base = f"http://127.0.0.1:{port}"
        log = (temp / "server.log").open("w")
        proc = subprocess.Popen(
            [sys.executable, "-m", "live_evidence", "serve", "--host", "127.0.0.1",
             "--port", str(port), "--no-browser"],
            cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, text=True,
        )
        try:
            for _ in range(80):
                try:
                    get(base, "/api/health")
                    break
                except Exception:
                    time.sleep(0.1)

            def invocations() -> int:
                return len(ask_ledger.read_text().splitlines()) if ask_ledger.exists() else 0

            def speak(seq: int, text: str) -> None:
                post(base, "/api/transcript", {
                    "schema": "live_evidence.transcript_event.v1",
                    "speaker": "interviewer", "kind": "final", "source": "api",
                    "sequence": seq, "text": text,
                })

            def wait_cards(want: int, timeout_s: float = 30.0) -> list[dict]:
                deadline = time.monotonic() + timeout_s
                cards: list[dict] = []
                while time.monotonic() < deadline:
                    cards = get(base, "/api/requirements")
                    if len(cards) >= want:
                        return cards
                    time.sleep(0.4)
                return cards

            post(base, "/api/session/start", {"consent_confirmed": True, "purpose": "meeting"})

            # Proof: a grammatical period is not task completion.
            speak(1, "We rely on Python and a large log processing stack in production.")
            time.sleep(0.5)
            check("period-terminated background does not start the solver",
                  invocations() == 0, f"invocations={invocations()}")

            # Blocking clarifications hold Ask at zero.
            speak(2, "Given the raw request log, write a Python function returning the top entries by count.")
            cards = wait_cards(2)
            time.sleep(1.5)
            check("blocking requirements hold automatic Ask at zero",
                  invocations() == 0, f"invocations={invocations()}")
            blocked = next((c for c in cards if c.get("blocking") and c.get("status") == "unresolved"), None)
            journal_rows = [json.loads(line) for jf in (temp / 'data').rglob('session.jsonl')
                            for line in jf.read_text().splitlines()]
            check("held requirement binds a ledger digest",
                  any(row.get('kind') == 'requirement_ledger_opened' and row.get('payload', {}).get('ledger_digest') for row in journal_rows),
                  'ledger journal read back')
            check("assumption is labeled independently of answer cards",
                  any(c.get('status') == 'assumed' and c.get('assumption_source') for c in cards),
                  str(cards)[:100])
            check("held answers remain invisible", not get(base, '/api/state').get('cards'), 'answer rail empty')
            qid = blocked.get("question_id") if blocked else ""
            rev = blocked.get("question_revision") if blocked else 0

            # Partial answer: still held.
            code, body = post(base, f"/api/questions/{qid}/clarifications/c1/answer",
                              {"question_revision": rev, "answer": "One JSON object per line."})
            check("partial answer accepted", code == 200 and body.get("result") == "amended",
                  f"{code} {body}")
            check("partial answer leaves the solver held",
                  invocations() == 0 and body.get("blocking_remaining") == 1,
                  f"remaining={body.get('blocking_remaining')}")

            # Stale revision rejected.
            code, body = post(base, f"/api/questions/{qid}/clarifications/c2/answer",
                              {"question_revision": rev + 7, "answer": "Descending."})
            check("stale-revision answer rejected with 409", code == 409, f"{code}")

            # Completing answer: solver runs exactly once.
            code, body = post(base, f"/api/questions/{qid}/clarifications/c2/answer",
                              {"question_revision": rev, "answer": "Descending by count."})
            time.sleep(1.5)
            check("resolving the last blocking requirement runs Ask exactly once",
                  code == 200 and invocations() == 1,
                  f"invocations={invocations()} published={body.get('published')}")
            journal_rows = [json.loads(line) for jf in (temp / 'data').rglob('session.jsonl')
                            for line in jf.read_text().splitlines()]
            answered = [row for row in journal_rows if row.get('kind') == 'requirement_amendment'
                        and row.get('payload', {}).get('result') == 'amended']
            check("clarification answers are journaled independently of cards",
                  len(answered) == 2, f"answered={len(answered)}")
            check("stub solver cannot authorize publication",
                  not get(base, '/api/state').get('cards') and not body.get('published'),
                  'fixture transport is not reviewer authority')

            # Duplicate answer: idempotent, no extra solver run.
            code, body = post(base, f"/api/questions/{qid}/clarifications/c2/answer",
                              {"question_revision": rev, "answer": "Descending by count."})
            check("duplicate answer is idempotent and never re-runs the solver",
                  code == 200 and body.get("result") == "duplicate" and invocations() == 1,
                  f"{body.get('result')} invocations={invocations()}")

            # Spoken (non-question) turn binds as a speech answer on a new blocked question.
            speak(3, "Now write a Python function that groups the log entries by user id.")
            wait_cards(2)
            speak(4, "The entries arrive newline separated over standard input.")
            time.sleep(2)
            journal_kinds: dict[str, int] = {}
            speech_bound = False
            for jf in (temp / "data").rglob("session.jsonl"):
                for line in jf.read_text().splitlines():
                    rec = json.loads(line)
                    journal_kinds[rec.get("kind")] = journal_kinds.get(rec.get("kind"), 0) + 1
                    if (rec.get("kind") == "requirement_amendment"
                            and rec.get("payload", {}).get("answer_source") == "speech"):
                        speech_bound = True
            check("spoken non-question turn binds as a speech answer",
                  speech_bound, f"journal={journal_kinds}")

            # Model-invented requirement without provenance fails validation.
            from live_evidence.models import Requirement, RequirementKind, RequirementStatus
            try:
                Requirement(question_id="a" * 12, question_revision=1,
                            kind=RequirementKind.CONSTRAINT, text="invented",
                            status=RequirementStatus.STATED)
                invented_rejected = False
            except Exception:
                invented_rejected = True
            check("invented requirement without ASSUMED provenance is rejected",
                  invented_rejected, "ValidationError raised")
        finally:
            log.flush()
            Path('/tmp/live-evidence-clarification-server.log').write_text((temp / 'server.log').read_text())
            journal_text = '\n'.join(jf.read_text() for jf in (temp / 'data').rglob('session.jsonl'))
            Path('/tmp/live-evidence-clarification-session.jsonl').write_text(journal_text)
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            log.close()

    Path('/tmp/live-evidence-clarification-eval.json').write_text(json.dumps({
        'status': 'FAIL' if failures else 'PASS', 'failures': failures,
        'proof_scope': 'Real HTTP; scripted legacy resolver and stub solver. No default scanner, live provider, UI or audio proof.',
        'fixture_backed': True, 'provider_calls': 0,
    }, indent=2) + '\n')
    print()
    if failures:
        print(f"requirement ledger: FAIL ({len(failures)} failed: {', '.join(failures)})")
        return 1
    print("requirement ledger: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
