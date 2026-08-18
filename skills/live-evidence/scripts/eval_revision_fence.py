#!/usr/bin/env python3
"""Agentic eval: a slow answer for a corrected question is discarded, not shown.

Retrieval plus the solver runs for tens of seconds, long enough for the speaker
to correct the question underneath it. This proves the compare-and-swap fence:
revision 1's completed result must land in the journal as
evidence_card_discarded_stale_revision and never reach the active card, while
revision 2 publishes exactly one card.

Determinism comes from a fixture Ask runner that sleeps before responding, so
revision 1 is guaranteed to finish after the correction arrives. The nonce is
generated at run time, so no compiled-in string can satisfy the assertions.

Also asserts on a REALISTIC-length transcript event (~640 chars, the measured
mean of live STT payloads). The window-annihilation regression (a 512-char cap
silently destroying every real event) passed the entire suite because fixture
questions are ~115 chars; this check exists so that class cannot return.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import httpx

failures: list[str] = []


def check(name: str, passed: bool, detail: str) -> None:
    print(f"{name}: {'PASS' if passed else 'FAIL'} ({detail})")
    if not passed:
        failures.append(name)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    nonce = uuid.uuid4().hex[:10]
    with tempfile.TemporaryDirectory(prefix="live-evidence-fence-") as temp_name:
        temp = Path(temp_name)
        repo = temp / "repo"
        repo.mkdir()
        (repo / "parens.py").write_text(
            f"# {nonce} reference\ndef validate_parentheses(s):\n    stack = []\n    return not stack\n",
            encoding="utf-8",
        )
        profile = temp / "profile.yaml"
        profile.write_text(
            "name: fence-eval\nwatch_terms:\n  - parentheses\n  - stack\n", encoding="utf-8"
        )
        # Fixture Ask runner: sleeps so revision 1 finishes AFTER the correction.
        runner = temp / "ask.sh"
        runner.write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\n"
            'd="${LIVE_EVIDENCE_ASK_FIXTURE_RUN_DIR:?}"\n'
            "sleep 12\n"
            'mkdir -p "$d/node-artifacts/handler-fixture"\n'
            'printf "Ask solution: use a stack.\\n" > "$d/node-artifacts/handler-fixture/response.md"\n'
            'printf \'{"run_dir":"%s"}\\n\' "$d"\n',
            encoding="utf-8",
        )
        runner.chmod(0o755)
        data_dir = temp / "data"
        port = free_port()
        env = {
            **os.environ,
            "LIVE_EVIDENCE_REPOS": str(repo),
            "LIVE_EVIDENCE_DATA_DIR": str(data_dir),
            "LIVE_EVIDENCE_PROFILE": str(profile),
            "LIVE_EVIDENCE_ASK_RUNNER": str(runner),
            "LIVE_EVIDENCE_ASK_HANDLER": "fixture",
            "LIVE_EVIDENCE_ASK_TIMEOUT": "60",
            "LIVE_EVIDENCE_ASK_FIXTURE_RUN_DIR": str(temp / "askrun"),
            "MEMORY_SERVICE_URL": "http://127.0.0.1:9",
        }
        env.pop("LIVE_EVIDENCE_SCILLM_KEY", None)  # resolver absent -> legacy fallback path
        log = (temp / "server.log").open("w", encoding="utf-8")
        process = subprocess.Popen(
            [sys.executable, "-m", "live_evidence", "serve", "--host", "127.0.0.1",
             "--port", str(port), "--no-browser"],
            cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, text=True,
        )
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=5.0) as client:
                for _ in range(80):
                    try:
                        if client.get("/api/health").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.1)
                client.post("/api/session/start", json={"consent_confirmed": True}).raise_for_status()

                def turn(seq: int, text: str) -> None:
                    client.post("/api/transcript", json={
                        "schema": "live_evidence.transcript_event.v1",
                        "speaker": "interviewer", "kind": "final", "source": "api",
                        "sequence": seq, "text": text,
                    }).raise_for_status()

                # Realistic-length event: ~640 chars, the measured live mean.
                filler = ("so to make it clear for you let me actually walk through what "
                          "I mean by that in a bit more detail here ")
                long_question = (
                    f"Given a string s with parentheses and lowercase letters for case {nonce}, "
                    + filler * 5
                    + "how would you validate that the parentheses are balanced using a stack?"
                )
                check("realistic event length in test input", len(long_question) >= 600,
                      f"{len(long_question)} chars")
                turn(1, long_question)
                time.sleep(3)
                # Correction while revision 1's slow solver is still running.
                turn(2, f"Actually for case {nonce} also handle square and curly brackets "
                        "and ignore any letters, still using a stack of open parentheses.")

                deadline = time.monotonic() + 90
                cards: list[dict] = []
                while time.monotonic() < deadline:
                    time.sleep(3)
                    state = client.get("/api/state").json()
                    cards = state.get("cards") or []
                    lanes = {l["lane"]: l["state"] for l in state.get("lanes") or []}
                    if cards and lanes.get("ask") not in ("running",):
                        time.sleep(10)  # let the stale revision-1 task land too
                        cards = client.get("/api/state").json().get("cards") or []
                        break

        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            log.close()

        check("realistic-length event produced a card (window not annihilated)",
              len(cards) >= 1, f"cards={len(cards)}")
        qids = {c.get("question_id") for c in cards}
        revisions = [c.get("question_revision") for c in cards]
        check("exactly one active card for the question", len(cards) == 1,
              f"cards={len(cards)} qids={len(qids)}")
        check("active card is the corrected revision",
              bool(revisions) and max(r or 0 for r in revisions) >= 2,
              f"revisions={revisions}")

        kinds: dict[str, int] = {}
        for session_file in data_dir.rglob("session.jsonl"):
            for line in session_file.read_text(encoding="utf-8").splitlines():
                try:
                    kind = json.loads(line).get("kind")
                except json.JSONDecodeError:
                    continue
                kinds[kind] = kinds.get(kind, 0) + 1
        check("stale revision-1 result journaled as discarded, not lost",
              kinds.get("evidence_card_discarded_stale_revision", 0) >= 1,
              f"journal kinds={kinds}")
        check("exactly one published card in journal",
              kinds.get("evidence_card", 0) == 1, f"journal kinds={kinds}")

    print()
    if failures:
        print(f"revision fence: FAIL ({len(failures)} failed: {', '.join(failures)})")
        return 1
    print("revision fence: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
