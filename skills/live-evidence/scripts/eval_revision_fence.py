#!/usr/bin/env python3
"""Agentic eval: slow answers cannot damage the visible card winner.

The HTTP half proves realistic STT-sized transcript events still reach a card.
The state half proves the revision fence deterministically, without depending on
scanner scheduling jitter.
"""

from __future__ import annotations

import asyncio
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

from live_evidence.config import AppSettings, InterviewProfile
from live_evidence.models import (
    CardStatus,
    EvidenceCard,
    EvidenceSource,
    Freshness,
    PublicationStatus,
    RetrievalLane,
)
from live_evidence.state import RuntimeState

failures: list[str] = []


def check(name: str, passed: bool, detail: str) -> None:
    print(f"{name}: {'PASS' if passed else 'FAIL'} ({detail})")
    if not passed:
        failures.append(name)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def supported_card(question_id: str, revision: int, nonce: str) -> EvidenceCard:
    return EvidenceCard(
        query=f"parentheses {nonce}",
        thread="parentheses",
        talking_point="Use a stack and validate bracket pairs.",
        proof="source-bound stack implementation",
        qualifier="bounded",
        confidence=0.8,
        status=CardStatus.SUPPORTED,
        sources=[
            EvidenceSource(
                lane=RetrievalLane.RIPGREP,
                label="parens.py",
                excerpt=f"# {nonce} reference\ndef validate_parentheses(s):",
                score=0.9,
                freshness=Freshness.CURRENT,
                path="/tmp/parens.py",
                repository="live-evidence-fence-eval",
            )
        ],
        lanes=[RetrievalLane.RIPGREP],
        question_id=question_id,
        question_revision=revision,
    )


async def prove_revision_fence(temp: Path, nonce: str) -> tuple[list[dict], list[int]]:
    state = RuntimeState(
        AppSettings(
            skill_root=temp,
            data_dir=temp / "state-data",
            profile_path=temp / "profile.yaml",
            repo_roots=[],
        ),
        InterviewProfile(name="fence-eval"),
    )
    await state.start_session(consent_confirmed=True)
    question_id, _ = await state.revise_question(
        f"How would you validate parentheses for case {nonce} using a stack?"
    )
    same_question_id, revision = await state.revise_question(
        f"How would you validate parentheses for case {nonce} using a stack and bracket pairs?"
    )
    await state.publish_card_fenced(supported_card(same_question_id, revision, nonce))
    await state.publish_card_fenced(supported_card(question_id, 1, nonce))
    snapshot = await state.snapshot()
    decisions = await state.card_publication_journal()
    statuses = [decision.status.value for decision in decisions]
    return [card.model_dump(mode="json") for card in snapshot.cards], statuses


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
                filler = ("so to make it clear for you let me actually walk through what "
                          "I mean by that in a bit more detail here ")
                long_question = (
                    f"Given a string s with parentheses and lowercase letters for case {nonce}, "
                    + filler * 5
                    + "how would you validate that the parentheses are balanced using a stack?"
                )
                check("realistic event length in test input", len(long_question) >= 600,
                      f"{len(long_question)} chars")
                client.post("/api/transcript", json={
                    "schema": "live_evidence.transcript_event.v1",
                    "speaker": "interviewer", "kind": "final", "source": "api",
                    "sequence": 1, "text": long_question,
                }).raise_for_status()
                deadline = time.monotonic() + 90
                cards: list[dict] = []
                while time.monotonic() < deadline:
                    time.sleep(3)
                    state = client.get("/api/state").json()
                    cards = state.get("cards") or []
                    lanes = {l["lane"]: l["state"] for l in state.get("lanes") or []}
                    if cards and lanes.get("ask") not in ("running",):
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

        fenced_cards, publication_statuses = asyncio.run(prove_revision_fence(temp, nonce))
        revisions = [card.get("question_revision") for card in fenced_cards]
        check("exactly one active card for the question", len(fenced_cards) == 1,
              f"cards={len(fenced_cards)} revisions={revisions}")
        check("active card is the corrected revision",
              bool(revisions) and revisions[0] == 2,
              f"revisions={revisions}")
        check("completed card candidates journaled for post-run audit",
              len(publication_statuses) >= 2,
              f"statuses={publication_statuses}")
        check("corrected revision is among journaled card candidates",
              "visible" in publication_statuses,
              f"statuses={publication_statuses}")
        check("publication reducer decisions journaled for post-run audit",
              "visible" in publication_statuses and "superseded" in publication_statuses,
              f"statuses={publication_statuses}")

    print()
    if failures:
        print(f"revision fence: FAIL ({len(failures)} failed: {', '.join(failures)})")
        return 1
    print("revision fence: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
