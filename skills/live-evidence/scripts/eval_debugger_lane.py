#!/usr/bin/env python3
"""Deterministic proof for the read-only debugger lane (#1450).

All ten required scenarios, exercised against the REAL sibling debugger skill
(capture_breakpoints.py + validate_debugger_proof.py run as subprocesses over
a fresh git repository created for this run). Nothing here mocks the debugger;
the deterministic part is the fixture program, not the machinery.

1.  valid breakpoint proof            -> supported outcome (real capture)
2.  unreachable breakpoint            -> no_breakpoint_hit, no supported card
3.  tampered proofValid               -> independent validator rejects
4.  stopped-frame/request mismatch    -> verified_stop_matches returns nothing
5.  repository digest mismatch        -> rejected before any capture
6.  stale question revision           -> CAS fence discards, journaled
7.  policy-blocked request            -> zero subprocess calls
8.  secret-shaped local               -> redacted end to end
9.  duplicate request digest          -> no repeated effect
10. missing capability (vscode_bridge)-> BLOCKED, never PASS
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import tempfile
from pathlib import Path

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{name}: {'PASS' if ok else 'FAIL'}{f' ({detail})' if detail else ''}")
    if not ok:
        FAILURES.append(name)


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))

    from live_evidence.debugger_lane import (
        DebuggerLane,
        repository_digest,
        verified_stop_matches,
    )
    from live_evidence.models import DebugBreakpoint, DebugRequest

    work = Path(tempfile.mkdtemp(prefix="live-evidence-debugger-eval-"))
    repo = work / "repo"
    repo.mkdir()
    program = repo / "checkout_total.py"
    program.write_text(
        "def total(prices, discount):\n"
        "    subtotal = sum(prices)\n"
        "    final = subtotal * (1 - discount)\n"
        "    return final\n"
        "\n"
        "def never_called():\n"
        "    marker = 'unreachable'\n"
        "    return marker\n"
        "\n"
        "api_key = 'sk-fixture-secret-000'\n"
        "answer = total([10, 20, 12], 0.5)\n"
        "print(answer)\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=eval@local", "-c", "user.name=eval", "commit", "-qm", "fixture"],
        cwd=repo,
        check=True,
    )
    repo_digest = repository_digest(repo)

    def request(**overrides) -> DebugRequest:
        kwargs = dict(
            session_id="debugger-eval-session",
            session_policy_digest="0" * 64,
            question_id="q-checkout-total",
            question_revision=0,
            repository_root=str(repo),
            repository_commit_or_tree_digest=repo_digest,
            technical_question="Why is the checkout total wrong at 50% discount?",
            reproduction_command=[str(program)],
            requested_breakpoints=[DebugBreakpoint(file=str(program), line=4),
                                   DebugBreakpoint(file=str(program), line=12)],
            requested_locals=["subtotal", "final", "api_key", "answer"],
        )
        kwargs.update(overrides)
        return DebugRequest(**kwargs)

    lane = DebuggerLane(work_dir=work / "artifacts")

    # 7. policy-blocked FIRST: proves zero subprocess without artifacts existing.
    blocked = lane.run(request(), debugger_invocation_allowed=False)
    check(
        "policy-blocked request runs zero subprocesses",
        blocked["result"] == "blocked_by_policy" and blocked["subprocess_calls"] == 0
        and not any((work / "artifacts").glob("proof-*.json")),
    )

    # 1 + 8. valid real capture -> supported; secret-shaped local redacted.
    ok_outcome = lane.run(request(), debugger_invocation_allowed=True)
    check(
        "valid breakpoint proof yields supported outcome",
        ok_outcome["result"] == "supported"
        and ok_outcome["stopped_line"] == 4
        and "subtotal" in ok_outcome["captured_variable_names"],
        f"result={ok_outcome['result']} stop={ok_outcome.get('stopped_file','')}:{ok_outcome.get('stopped_line')}",
    )
    check(
        "captured paused state is real (subtotal=42 from the fixture run)",
        ok_outcome.get("captured_locals", {}).get("subtotal") == "42",
        f"subtotal={ok_outcome.get('captured_locals', {}).get('subtotal')}",
    )
    secret_value = str(ok_outcome.get("captured_locals", {}).get("api_key", ""))
    blob = json.dumps(ok_outcome)
    check(
        "secret-shaped local redacted end to end",
        "sk-fixture-secret-000" not in blob and "redacted" in secret_value,
        f"api_key={secret_value[:60]}",
    )

    # 9. duplicate request digest: no second capture effect.
    proofs_before = sorted((work / "artifacts").glob("proof-*.json"))
    duplicate = lane.run(request(), debugger_invocation_allowed=True)
    proofs_after = sorted((work / "artifacts").glob("proof-*.json"))
    check(
        "duplicate request digest returns recorded outcome without re-running",
        duplicate.get("duplicate") is True
        and duplicate["result"] == "supported"
        and proofs_before == proofs_after,
    )

    # 2. unreachable breakpoint (line never executes) -> no supported card.
    unreachable = lane.run(
        request(requested_breakpoints=[DebugBreakpoint(file=str(program), line=7)],
                question_revision=1),
        debugger_invocation_allowed=True,
    )
    check(
        "unreachable breakpoint cannot produce a supported outcome",
        unreachable["result"] == "no_breakpoint_hit",
        f"result={unreachable['result']}",
    )

    # 3. tampered producer-authored proofValid=true with no real stop.
    tampered_path = work / "tampered-proof.json"
    real_proof = json.loads(Path(ok_outcome["proof_path"]).read_text())
    real_proof["hits"] = []
    real_proof["proofValid"] = True
    tampered_path.write_text(json.dumps(real_proof))
    debugger_root = Path(root).parent / "debugger"
    tampered = subprocess.run(
        [sys.executable, str(debugger_root / "scripts" / "validate_debugger_proof.py"),
         str(tampered_path), "--expect-valid"],
        capture_output=True, text=True,
    )
    check(
        "tampered proofValid without a real stop rejected by independent validator",
        tampered.returncode != 0,
        f"exit={tampered.returncode}",
    )

    # 4. stopped-frame/request mismatch, over the REAL canonical artifact.
    canonical = json.loads(Path(ok_outcome["canonical_path"]).read_text())
    mismatch_request = request(
        requested_breakpoints=[DebugBreakpoint(file=str(program), line=3)],
        question_revision=2,
    )
    check(
        "verified stop at a different location does not match the request",
        verified_stop_matches(canonical, mismatch_request) == []
        and len(verified_stop_matches(canonical, request())) >= 1,
    )

    # 5. repository digest mismatch rejected before capture.
    wrong_repo = lane.run(
        request(repository_commit_or_tree_digest="f" * 40, question_revision=3),
        debugger_invocation_allowed=True,
    )
    check(
        "wrong repository digest rejected before any capture",
        wrong_repo["result"] == "rejected_repository_mismatch"
        and wrong_repo["subprocess_calls"] == 0,
    )

    # 10. vscode_bridge capability absent -> truthful BLOCKED, no fake stop.
    gui = lane.run(request(debugger_mode="vscode_bridge", question_revision=4),
                   debugger_invocation_allowed=True)
    check(
        "missing vscode capability reports blocked, not success",
        gui["result"] == "blocked_missing_capability" and gui["subprocess_calls"] == 0,
    )

    # 6. stale question revision: the shared CAS publication fence discards a
    # debugger card for revision N once N+1 is active, and journals it.
    async def stale_fence() -> tuple[object, bool]:
        from live_evidence.config import AppSettings, InterviewProfile
        from live_evidence.models import CardStatus, EvidenceCard, EvidenceSource, RetrievalLane
        from live_evidence.state import RuntimeState

        state = RuntimeState(AppSettings.from_env(), InterviewProfile(name="debugger-eval"))
        await state.start_session(consent_confirmed=True)
        question_id, stale_revision = await state.revise_question("why is the total wrong?")
        await state.revise_question("why is the total wrong at 50% discount?")
        card = EvidenceCard(
            query="why is the total wrong?",
            thread="Debugger",
            talking_point="subtotal=42 at checkout_total.py:4",
            proof=ok_outcome["proof_path"],
            qualifier="Observed run/state only; not a semantic guarantee.",
            confidence=0.8,
            status=CardStatus.SUPPORTED,
            sources=[EvidenceSource(
                lane=RetrievalLane.DEBUGGER,
                label="debugger proof",
                path=ok_outcome["proof_path"],
                excerpt="subtotal=42",
            )],
            question_id=question_id,
            question_revision=stale_revision,
        )
        published = await state.publish_card_fenced(card)
        snapshot = await state.snapshot()
        active_cards = [c for c in snapshot.cards if c.question_id == question_id]
        return published, bool(active_cards)

    try:
        published, active = asyncio.run(stale_fence())
        check(
            "stale-revision debugger card discarded by the CAS fence",
            published is None and active is False,
        )
    except Exception as exc:  # pragma: no cover
        check("stale-revision debugger card discarded by the CAS fence", False, f"{type(exc).__name__}: {exc}")

    print()
    if FAILURES:
        print(f"debugger lane: FAIL ({len(FAILURES)} failed: {', '.join(FAILURES)})")
        return 1
    print("debugger lane: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
