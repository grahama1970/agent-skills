"""Machine-checkable compliance for roundtables and competitions.

Purpose
    `best-practices-roundtable` and `best-practices-competition` state rules
    that decide whether a panel's output means anything: equal context for
    every seat, isolation between competitors, per-seat status, and a refusal
    to report consensus when a seat never answered. Until now those rules lived
    only in prose, so "this run complied" was an assertion nobody could check.

    This reads a finished run directory and answers it from artifacts.

The rules that carry weight
    **Equal context.** A packet tailored per seat produces a panel that agrees
    with whoever got the better brief. Only per-seat addressing may differ --
    which seat you are, and which model to select -- so compliance is measured
    on the task body with those lines removed, not on the raw bytes.

    **Isolation (competition only).** Two candidates that read each other
    converge into one candidate with extra steps. Checked by looking for a
    rival's response text inside a candidate's prompt, because that is the
    shape leakage actually takes.

    **No silent consensus.** A seat that failed, timed out, or never ran must
    appear as a named non-answer. A three-seat panel reported as agreement when
    two seats died is the single most misleading artifact this system can
    produce, so it is a violation rather than a note.

    **Quorum.** The floor is on seats that ANSWERED, never seats dispatched:
    three for a roundtable, two for a competition. Below it a run must say so.
    Without this, the previous rule is enforceable only on wording -- a panel
    that never says "the panel agrees" could still present one surviving seat
    as the panel's finding.

Non-goal
    This judges process compliance, never semantic quality. A fully compliant
    roundtable can still be wrong; that is what the proof gates are for.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

SCHEMA = "ask.panel_compliance.v1"

#: Answering seats a panel needs before its output means what it says.
#:
#: A roundtable needs three. At two, a panel that loses one seat is a single
#: opinion, and even intact there is no majority to hold and no dissent to
#: attribute -- "the panel agrees" reduces to one model talking, which is the
#: exact artifact `check_no_silent_consensus` exists to refuse, arriving through
#: the front door instead.
#:
#: A competition needs two, and two is genuinely enough: isolated candidates in
#: a head-to-head is a real bakeoff, and `best-practices-competition` already
#: refuses to pick a winner on a tie.
#:
#: Both floors count seats that ANSWERED, never seats dispatched.
ROUNDTABLE_MIN_ANSWERING = 3
COMPETITION_MIN_ANSWERING = 2

#: Lines that legitimately differ per seat: addressing and model selection.
#: Everything else in a packet is task content and must be identical.
PER_SEAT_PREFIXES = (
    "handler:",
    "browser model preference:",
    "model:",
    "seat:",
    "node_id:",
)

#: A seat that produced none of these never answered, whatever the join says.
RESPONSE_FILES = ("response.md", "response.raw.md", "response.recovered.md")


def task_body(prompt_text: str) -> str:
    """The shared task, with per-seat addressing removed."""
    kept: list[str] = []
    # A per-seat marker may carry its value inline ("Handler: webgpt") or as a
    # header whose value is on following lines ("Browser model preference:\nOpus
    # 5 High"). Both forms are addressing, not task content, so a header with no
    # inline value swallows its block up to the next blank line.
    in_block = False
    for line in str(prompt_text or "").splitlines():
        stripped = line.strip()
        lowered = stripped.casefold()
        matched = next((pre for pre in PER_SEAT_PREFIXES if lowered.startswith(pre)), None)
        if matched is not None:
            in_block = not stripped[len(matched):].strip()
            continue
        if in_block:
            if not stripped:
                in_block = False
            continue
        kept.append(line.rstrip())
    return "\n".join(kept).strip()


def packet_digest(prompt_text: str) -> str:
    return "sha256:" + hashlib.sha256(task_body(prompt_text).encode("utf-8")).hexdigest()


def _lane_dirs(run_dir: Path) -> list[Path]:
    return sorted((run_dir / "node-artifacts").glob("handler-*"))


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def seat_status(lane_dir: Path) -> dict[str, Any]:
    """One seat's outcome, from its own artifacts rather than the join's story."""
    receipt: dict[str, Any] = {}
    try:
        receipt = json.loads((lane_dir / "node-receipt.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        receipt = {}
    responded = any(
        (lane_dir / name).is_file() and (lane_dir / name).stat().st_size > 0
        for name in RESPONSE_FILES
    )
    return {
        "seat": lane_dir.name,
        "status": str(receipt.get("status") or "MISSING"),
        "failure_code": receipt.get("failure_code"),
        "responded": responded,
    }


def check_equal_context(run_dir: Path) -> dict[str, Any]:
    """Every seat must have received the same task."""
    lanes = _lane_dirs(run_dir)
    digests = {lane.name: packet_digest(_read(lane / "prompt.md")) for lane in lanes}
    distinct = sorted(set(digests.values()))
    return {
        "rule": "equal_context",
        "source": "best-practices-roundtable: every seat receives the same packet",
        "seats": len(lanes),
        "digests": digests,
        "compliant": len(distinct) <= 1 and bool(lanes),
        "detail": "one shared packet" if len(distinct) <= 1 else f"{len(distinct)} distinct packets",
    }


def check_isolation(run_dir: Path) -> dict[str, Any]:
    """No candidate may have been shown a rival's answer."""
    lanes = _lane_dirs(run_dir)
    leaks: list[dict[str, str]] = []
    responses = {
        lane.name: next(
            (_read(lane / n) for n in RESPONSE_FILES if (lane / n).is_file() and (lane / n).stat().st_size > 0),
            "",
        )
        for lane in lanes
    }
    for lane in lanes:
        prompt = _read(lane / "prompt.md")
        for other, text in responses.items():
            if other == lane.name or len(text.strip()) < 80:
                continue
            probe = text.strip()[:80]
            if probe and probe in prompt:
                leaks.append({"seat": lane.name, "saw": other})
    return {
        "rule": "isolation",
        "source": "best-practices-competition: candidates never see each other's output",
        "compliant": not leaks,
        "leaks": leaks,
    }


def check_seat_status(run_dir: Path) -> dict[str, Any]:
    """Every seat must be accounted for by name."""
    statuses = [seat_status(lane) for lane in _lane_dirs(run_dir)]
    unaccounted = [s["seat"] for s in statuses if s["status"] == "MISSING" and not s["responded"]]
    return {
        "rule": "seat_status",
        "source": "best-practices-roundtable: a missing seat is NEEDS_ATTENTION, not silence",
        "seats": statuses,
        "answered": [s["seat"] for s in statuses if s["responded"]],
        "did_not_answer": [s["seat"] for s in statuses if not s["responded"]],
        "compliant": not unaccounted,
        "unaccounted": unaccounted,
    }


def check_no_silent_consensus(run_dir: Path) -> dict[str, Any]:
    """A panel with a dead seat must not read as agreement.

    The most misleading artifact this system can produce is a three-seat
    consensus written while two seats never answered.
    """
    statuses = [seat_status(lane) for lane in _lane_dirs(run_dir)]
    silent = [s["seat"] for s in statuses if not s["responded"]]
    join_text = ""
    join_dir = run_dir / "node-artifacts" / "join"
    if join_dir.is_dir():
        for path in sorted(join_dir.glob("*.json")) + sorted(join_dir.glob("*.md")):
            join_text += _read(path)
    lowered = join_text.casefold()
    claims_agreement = bool(re.search(r"\b(the panel agrees|unanimous|all seats agree|consensus reached)\b", lowered))
    names_the_gap = all(seat.replace("handler-", "") in lowered for seat in silent) if silent else True
    return {
        "rule": "no_silent_consensus",
        "source": "best-practices-roundtable: never report consensus over a missing seat",
        "silent_seats": silent,
        "join_claims_agreement": claims_agreement,
        "compliant": not (claims_agreement and silent) and (names_the_gap or not silent),
        "detail": "every non-answering seat is named in the join" if silent else "all seats answered",
    }


def check_roundtable_quorum(run_dir: Path) -> dict[str, Any]:
    """Three answering seats minimum, or the run must say it fell short.

    Same shape as the competition floor and for the same reason: a seat that
    never answered is not a seat. A run honestly reporting NEEDS_ATTENTION or
    BLOCKED is not in violation -- it already says it did not get a panel. The
    violation is presenting a sub-quorum panel as a panel result.
    """
    statuses = [seat_status(lane) for lane in _lane_dirs(run_dir)]
    answered = [s["seat"] for s in statuses if s["responded"]]
    join_status = ""
    receipt_path = run_dir / "node-artifacts" / "join" / "node-receipt.json"
    try:
        join_status = str(json.loads(receipt_path.read_text(encoding="utf-8")).get("status") or "")
    except (OSError, ValueError):
        join_status = ""
    short = len(answered) < ROUNDTABLE_MIN_ANSWERING
    disclosed = join_status in {"NEEDS_ATTENTION", "BLOCKED"}
    return {
        "rule": "roundtable_quorum",
        "source": (
            f"best-practices-roundtable: >={ROUNDTABLE_MIN_ANSWERING} ANSWERING seats, "
            "or report the shortfall"
        ),
        "seats_dispatched": len(statuses),
        "seats_answered": len(answered),
        "answered": answered,
        "required": ROUNDTABLE_MIN_ANSWERING,
        "status": join_status,
        "compliant": not short or disclosed,
        "detail": (
            f"{len(answered)} of {len(statuses)} seats answered, quorum is "
            f"{ROUNDTABLE_MIN_ANSWERING}"
            if short
            else f"{len(answered)} seats answered"
        ),
    }


def check_competition_outcome(run_dir: Path) -> dict[str, Any]:
    """Two candidates minimum, and never a fabricated winner."""
    scorecard: dict[str, Any] = {}
    path = run_dir / "node-artifacts" / "join" / "compete-scorecard.json"
    try:
        scorecard = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        scorecard = {}
    candidates = scorecard.get("candidates") or []
    winner = scorecard.get("winner_handler")
    status = str(scorecard.get("status") or "")
    answered = [s for s in (seat_status(lane) for lane in _lane_dirs(run_dir)) if s["responded"]]
    fabricated = bool(winner) and not answered
    # A candidate that never answered is not a candidate. Counting dispatched
    # seats lets a one-opinion run present itself as a competition: the live
    # run on 2026-08-16 dispatched two and had one answer, while the scorecard
    # still read "candidates: 2". The floor must be measured on answers.
    single_opinion = (
        len(answered) < COMPETITION_MIN_ANSWERING
        and status not in {"NEEDS_ATTENTION", "BLOCKED"}
    )
    return {
        "rule": "competition_outcome",
        "source": (
            f"best-practices-competition: >={COMPETITION_MIN_ANSWERING} ANSWERING "
            "candidates; no winner without evidence"
        ),
        "candidates_dispatched": len(candidates),
        "candidates_answered": len(answered),
        "required": COMPETITION_MIN_ANSWERING,
        "winner": winner,
        "status": status,
        "compliant": not fabricated and not single_opinion,
        "detail": (
            "winner named with no candidate response"
            if fabricated
            else f"fewer than {COMPETITION_MIN_ANSWERING} candidates answered, "
            "so this is one opinion, not a competition"
            if single_opinion
            else "outcome consistent with receipts"
        ),
    }


def audit(run_dir: Path | str, *, mode: str = "roundtable") -> dict[str, Any]:
    """Full compliance report for one finished run."""
    root = Path(run_dir)
    checks = [
        check_equal_context(root),
        check_seat_status(root),
        check_no_silent_consensus(root),
        check_isolation(root),
    ]
    if mode == "compete":
        checks.append(check_competition_outcome(root))
    else:
        checks.append(check_roundtable_quorum(root))
    violations = [c for c in checks if not c["compliant"]]
    return {
        "schema": SCHEMA,
        "run_dir": str(root),
        "mode": mode,
        "checks": checks,
        "violations": [c["rule"] for c in violations],
        "compliant": not violations,
    }
