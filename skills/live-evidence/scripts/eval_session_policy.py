#!/usr/bin/env python3
"""Agentic eval: session capability policy is enforced in the backend (#1449).

Every check runs over live HTTP against a real server, because the ticket's
acceptance bar is explicit that hidden frontend controls are not proof: a
disabled capability must fail closed when the caller bypasses the UI entirely.
The Ask runner is a fixture that appends to an invocation ledger, so "Ask never
ran" is read from an artifact the solver path itself produces, not from a lane
label.
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
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as exc:
        try:
            body = json.load(exc)
        except Exception:
            body = {}
        return exc.code, body


def get(base: str, path: str) -> dict:
    with urllib.request.urlopen(base + path, timeout=20) as resp:
        return json.load(resp)


QUESTION = (
    "Given a string with parentheses and lowercase letters, how would you "
    "validate that the parentheses are balanced using a stack?"
)


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    with tempfile.TemporaryDirectory(prefix="le-policy-") as temp_name:
        temp = Path(temp_name)
        repo = temp / "repo"
        repo.mkdir()
        (repo / "parens.py").write_text(
            "def is_valid_parentheses(s):\n    stack = []\n    return not stack\n"
        )
        (temp / "profile.yaml").write_text(
            "name: policy-eval\nwatch_terms:\n  - parentheses\n  - stack\n"
        )
        ledger = temp / "ask-invocations.log"
        runner = temp / "ask.sh"
        runner.write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\n"
            f'echo invoked >> "{ledger}"\n'
            'd="${LIVE_EVIDENCE_ASK_FIXTURE_RUN_DIR:?}"\n'
            'mkdir -p "$d/node-artifacts/handler-fixture"\n'
            'printf "Ask solution: use a stack.\\n" > "$d/node-artifacts/handler-fixture/response.md"\n'
            'printf \'{"run_dir":"%s"}\\n\' "$d"\n'
        )
        runner.chmod(0o755)
        env = {
            **os.environ,
            "LIVE_EVIDENCE_REPOS": str(repo),
            "LIVE_EVIDENCE_DATA_DIR": str(temp / "data"),
            "LIVE_EVIDENCE_PROFILE": str(temp / "profile.yaml"),
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

            def ask_invocations() -> int:
                return len(ledger.read_text().splitlines()) if ledger.exists() else 0

            def speak(seq: int) -> None:
                post(base, "/api/transcript", {
                    "schema": "live_evidence.transcript_event.v1",
                    "speaker": "interviewer", "kind": "final", "source": "api",
                    "sequence": seq, "text": QUESTION,
                })

            def wait_cards(want: int, timeout_s: float = 45.0) -> list[dict]:
                deadline = time.monotonic() + timeout_s
                cards: list[dict] = []
                while time.monotonic() < deadline:
                    cards = get(base, "/api/state").get("cards") or []
                    if len(cards) >= want:
                        break
                    time.sleep(0.5)
                return cards

            # --- meeting baseline: ask fires, digest binds ---
            _, snap = post(base, "/api/session/start",
                           {"consent_confirmed": True, "purpose": "meeting"})
            meeting_sid = snap["session"]["session_id"]
            meeting_digest = snap["session"]["policy_digest"]
            check("meeting session carries a 64-hex policy digest",
                  len(meeting_digest) == 64, meeting_digest[:12])
            speak(1)
            cards = wait_cards(1)
            time.sleep(2)
            baseline_invocations = ask_invocations()
            check("meeting: automatic Ask ran", baseline_invocations >= 1,
                  f"invocations={baseline_invocations}")
            check("meeting: card binds the policy digest",
                  bool(cards) and cards[0].get("policy_digest") == meeting_digest,
                  str(cards[0].get("policy_digest"))[:12] if cards else "no card")

            # --- formal assessment: everything assistive fails closed ---
            _, snap = post(base, "/api/session/start",
                           {"consent_confirmed": True, "purpose": "formal_assessment",
                            "actor_role": "candidate"})
            fa_sid = snap["session"]["session_id"]
            fa_digest = snap["session"]["policy_digest"]
            check("formal_assessment allocates a NEW session id",
                  fa_sid != meeting_sid, f"{meeting_sid[:8]} -> {fa_sid[:8]}")
            check("formal_assessment digest differs from meeting",
                  fa_digest != meeting_digest, fa_digest[:12])
            speak(2)
            wait_cards(1, timeout_s=20)
            time.sleep(3)
            check("formal_assessment: automatic Ask NEVER ran",
                  ask_invocations() == baseline_invocations,
                  f"invocations still {baseline_invocations}")
            code, body = post(base, "/api/search", {"lane": "ask", "query": QUESTION})
            check("formal_assessment: manual Ask rejected 403", code == 403,
                  f"{code} {str(body.get('detail'))[:60]}")
            code, body = post(base, "/api/search", {"lane": "brave", "query": QUESTION})
            check("formal_assessment: manual external search rejected 403", code == 403,
                  f"{code} {str(body.get('detail'))[:60]}")

            # widening attempt after transcript activity -> new session, never in place
            _, snap = post(base, "/api/session/start",
                           {"consent_confirmed": True, "purpose": "meeting"})
            check("post-start widening allocates a new session id",
                  snap["session"]["session_id"] != fa_sid,
                  f"{fa_sid[:8]} -> {snap['session']['session_id'][:8]}")

            # --- rehearsal: visibly practice-only, distinct digest ---
            _, snap = post(base, "/api/session/start",
                           {"consent_confirmed": True, "purpose": "rehearsal",
                            "actor_role": "candidate"})
            check("rehearsal is machine-readably practice_only",
                  snap["session"].get("practice_only") is True, "practice_only=true")
            check("rehearsal digest differs from meeting",
                  snap["session"]["policy_digest"] not in (meeting_digest, fa_digest),
                  snap["session"]["policy_digest"][:12])

            # --- post_interview_review: consent alone must not yield LISTENING ---
            _, snap = post(base, "/api/session/start",
                           {"consent_confirmed": True, "purpose": "post_interview_review",
                            "actor_role": "reviewer"})
            check("post_interview_review never LISTENS even with consent",
                  snap["session"]["status"] == "armed", snap["session"]["status"])

            # journal digest binding, read from disk
            bound = 0
            total = 0
            for jf in (temp / "data").rglob("session.jsonl"):
                for line in jf.read_text().splitlines():
                    rec = json.loads(line)
                    total += 1
                    if len(rec.get("policy_digest") or "") == 64:
                        bound += 1
            check("every journaled record binds a policy digest",
                  total > 0 and bound == total, f"{bound}/{total}")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            log.close()

    print()
    if failures:
        print(f"session policy: FAIL ({len(failures)} failed: {', '.join(failures)})")
        return 1
    print("session policy: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
