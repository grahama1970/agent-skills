#!/usr/bin/env python3
"""Fail closed when Persona Dream current-state surfaces contradict receipts.

Persona Dream carries strong receipt-level evidence, but its prose and machine
projections drift away from it. Observed 2026-07-28: the speaker-recognition
preflight receipt read ``PASS_SPEAKER_RECOGNITION_PREFLIGHT`` with resemblyzer
available, while ``CURRENT_STATUS.json`` still listed an active blocker saying
``resemblyzer=false and speechbrain_ecapa=false`` and made "resolve the P2.4
backend blocker" the first ordered next step. An agent reading the prose would
select an already-completed stage.

The current-state hierarchy this enforces, most authoritative first:

1. named receipt files and their read-back status/hash;
2. ``CURRENT_STATUS.json`` machine projection;
3. the current summary at the top of ``PROJECT_KNOWLEDGE.md``;
4. the README current-state section;
5. historical log entries, which must be marked historical/superseded/retracted
   rather than read as current.

Lower levels may not contradict higher ones. Matching is plain substring
containment on normalized text -- deterministic and inspectable, so a mismatch
report names the exact file, JSON path, and offending string.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]

CURRENT_STATUS = ROOT / "CURRENT_STATUS.json"
PROJECT_KNOWLEDGE = ROOT / "PROJECT_KNOWLEDGE.md"
README = ROOT / "README.md"

#: Words that mark a log entry as not-current. A historical entry containing a
#: superseded claim is fine; an unmarked one is treated as a current assertion.
HISTORICAL_MARKERS = ("historical", "superseded", "retracted", "stale", "folded into")

#: How far into a document counts as "current summary". Raised from 60 after
#: #1069: the stale P2.4 section header sat at line 57 and its body beyond it,
#: so a 60-line window saw the header but not the instruction under it.
SUMMARY_LINE_LIMIT = 120


class Stage:
    """One receipted stage, plus the phrases that would contradict acceptance.

    ``contradiction_markers`` are lowercase substrings. When the stage's receipt
    is accepted, none of them may appear in an active blocker or a next step:
    each asserts the stage is still open.
    """

    def __init__(
        self,
        stage_id: str,
        receipt: str,
        accepted_prefix: str,
        contradiction_markers: tuple[str, ...],
        status_pin: str | None = None,
    ) -> None:
        self.stage_id = stage_id
        self.receipt = receipt
        self.accepted_prefix = accepted_prefix
        self.contradiction_markers = contradiction_markers
        self.status_pin = status_pin


STAGES = (
    Stage(
        stage_id="P2.4_speaker_recognition_preflight",
        receipt="reports/goal_v5/continuity/session_mood_voice_recognition_preflight/RECEIPT.json",
        accepted_prefix="PASS_",
        contradiction_markers=(
            "resemblyzer=false",
            "speechbrain_ecapa=false",
            "no real speaker-recognition backend",
            "speaker-recognition preflight is blocked",
            "resolve the p2.4 speaker-recognition backend blocker",
            "install or route to a real speaker-recognition backend",
            # Observed 2026-07-28 (#1069): PROJECT_KNOWLEDGE's stale order said
            # "Resolve the speaker-recognition backend blocker with an approved
            # real backend" -- no "p2.4" token, so every marker above missed it
            # while the checker reported PASS. Markers must match the words the
            # documents actually use, not the words the ticket used.
            "resolve the speaker-recognition backend blocker",
            "preflight blocks on missing backend",
            "blocks on missing backend",
        ),
        status_pin="continuity_state.latest_voice_recognition_preflight_receipt_sha256",
    ),
    Stage(
        stage_id="P2.1_ledger_hardening",
        receipt="reports/goal_v5/continuity/ledger_hardening/RECEIPT.json",
        accepted_prefix="PASS_",
        contradiction_markers=("harden the continuity ledger",),
        status_pin="continuity_state.latest_authority_receipt_sha256",
    ),
    Stage(
        stage_id="P2.2_session_mood_binding",
        receipt="reports/goal_v5/continuity/session_mood_binding/RECEIPT.json",
        accepted_prefix="PASS_",
        contradiction_markers=("bind a deterministic session mood before turn 1",),
        status_pin="continuity_state.latest_session_mood_binding_receipt_sha256",
    ),
    Stage(
        stage_id="P2.3_live_chatterbox_render",
        receipt="reports/goal_v5/continuity/session_mood_chatterbox_live/RECEIPT.json",
        accepted_prefix="PASS_",
        contradiction_markers=("render session mood through chatterbox",),
        status_pin="continuity_state.latest_session_mood_chatterbox_live_receipt_sha256",
    ),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def dig(obj: Any, dotted: str) -> Any:
    """Resolve ``a.b.c`` against nested dicts, returning None when absent."""
    cur = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def receipt_status(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("status")
    except ValueError:
        return None


def _mismatch(rule: str, file: str, json_path: str, detail: str, offending: str = "") -> dict[str, Any]:
    row = {"rule": rule, "file": file, "json_path": json_path, "detail": detail}
    if offending:
        row["offending"] = offending
    return row


def check_receipts(status_doc: dict[str, Any], mismatches: list[dict[str, Any]]) -> dict[str, Any]:
    """Level 1: named receipts exist, parse, and match their pinned hashes."""
    resolved: dict[str, Any] = {}
    for stage in STAGES:
        path = ROOT / stage.receipt
        got = receipt_status(path)
        accepted = bool(got and got.startswith(stage.accepted_prefix))
        resolved[stage.stage_id] = {
            "receipt": stage.receipt,
            "exists": path.is_file(),
            "status": got,
            "accepted": accepted,
        }
        if not path.is_file():
            mismatches.append(
                _mismatch(
                    "receipt_missing",
                    stage.receipt,
                    stage.stage_id,
                    "stage receipt named by the checker does not exist",
                )
            )
            continue
        resolved[stage.stage_id]["sha256"] = sha256_file(path)
        if stage.status_pin:
            pinned = dig(status_doc, stage.status_pin)
            if pinned and pinned != resolved[stage.stage_id]["sha256"]:
                mismatches.append(
                    _mismatch(
                        "receipt_hash_mismatch",
                        "CURRENT_STATUS.json",
                        stage.status_pin,
                        f"pinned {pinned} but receipt hashes to "
                        f"{resolved[stage.stage_id]['sha256']}",
                    )
                )
    return resolved


def check_blockers_and_next_steps(
    status_doc: dict[str, Any], resolved: dict[str, Any], mismatches: list[dict[str, Any]]
) -> None:
    """Level 2: no blocker or next step may reopen an accepted stage."""
    blockers = status_doc.get("active_blockers") or []
    next_step = status_doc.get("next_step") or {}
    ordered = next_step.get("ordered_steps") or []
    default_step = next_step.get("default") or ""

    for stage in STAGES:
        if not resolved.get(stage.stage_id, {}).get("accepted"):
            continue
        for idx, blocker in enumerate(blockers):
            low = str(blocker).lower()
            for marker in stage.contradiction_markers:
                if marker in low:
                    mismatches.append(
                        _mismatch(
                            "blocker_contradicts_accepted_receipt",
                            "CURRENT_STATUS.json",
                            f"active_blockers[{idx}]",
                            f"{stage.stage_id} receipt is "
                            f"{resolved[stage.stage_id]['status']} but this blocker "
                            f"asserts it is still open",
                            marker,
                        )
                    )
        for idx, step in enumerate(ordered):
            low = str(step).lower()
            for marker in stage.contradiction_markers:
                if marker in low:
                    mismatches.append(
                        _mismatch(
                            "next_step_names_accepted_stage",
                            "CURRENT_STATUS.json",
                            f"next_step.ordered_steps[{idx}]",
                            f"{stage.stage_id} is already accepted "
                            f"({resolved[stage.stage_id]['status']})",
                            marker,
                        )
                    )
        low_default = default_step.lower()
        for marker in stage.contradiction_markers:
            if marker in low_default:
                mismatches.append(
                    _mismatch(
                        "next_step_names_accepted_stage",
                        "CURRENT_STATUS.json",
                        "next_step.default",
                        f"{stage.stage_id} is already accepted "
                        f"({resolved[stage.stage_id]['status']})",
                        marker,
                    )
                )


def current_summary(path: Path, limit: int = SUMMARY_LINE_LIMIT) -> str:
    """The top-of-file current summary, which is what an agent reads first."""
    if not path.is_file():
        return ""
    lines = path.read_text(encoding="utf-8").splitlines()[:limit]
    return "\n".join(lines).lower()


def summary_paragraphs(path: Path, limit: int = SUMMARY_LINE_LIMIT) -> list[tuple[int, str]]:
    """Yield ``(first_line_number, whitespace-normalized paragraph)``.

    Paragraphs, not lines: markdown hard-wraps prose, so the README's
    "harden the continuity\\nledger first" splits a contradiction marker across
    two lines and defeats per-line substring matching. Normalizing each
    paragraph to single spaces makes wrapping irrelevant while keeping the
    historical-marker exemption scoped to a readable unit.
    """
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[:limit]
    paragraphs: list[tuple[int, str]] = []
    buf: list[str] = []
    start = 1
    for idx, line in enumerate(lines, start=1):
        if line.strip():
            if not buf:
                start = idx
            buf.append(line.strip())
        elif buf:
            paragraphs.append((start, " ".join(buf).lower()))
            buf = []
    if buf:
        paragraphs.append((start, " ".join(buf).lower()))
    return paragraphs


def check_prose_surfaces(
    status_doc: dict[str, Any], resolved: dict[str, Any], mismatches: list[dict[str, Any]]
) -> None:
    """Levels 3 and 4: prose summaries may not reopen an accepted stage.

    A line carrying a historical marker is exempt: chronology stays readable,
    it just cannot override the current projection.
    """
    for label, path in (("PROJECT_KNOWLEDGE.md", PROJECT_KNOWLEDGE), ("README.md", README)):
        if not path.is_file():
            mismatches.append(_mismatch("surface_missing", label, "-", "current-state surface absent"))
            continue
        for stage in STAGES:
            if not resolved.get(stage.stage_id, {}).get("accepted"):
                continue
            for line_no, para in summary_paragraphs(path):
                if any(mark in para for mark in HISTORICAL_MARKERS):
                    continue
                for marker in stage.contradiction_markers:
                    if marker in para:
                        mismatches.append(
                            _mismatch(
                                "current_summary_contradicts_receipt",
                                label,
                                f"line {line_no}",
                                f"{stage.stage_id} is accepted "
                                f"({resolved[stage.stage_id]['status']}) but this current "
                                f"summary line asserts it is open and is not marked historical",
                                marker,
                            )
                        )

    # Level 4 vs 2: the README and PROJECT_KNOWLEDGE must name the phase the
    # machine projection names, so agents do not select a superseded gate.
    phase = str(status_doc.get("current_phase", "")).lower()
    if phase:
        for label, path in (("PROJECT_KNOWLEDGE.md", PROJECT_KNOWLEDGE), ("README.md", README)):
            summary = current_summary(path)
            token = phase.replace("_", " ").split()[0]
            if summary and token and token not in summary and phase not in summary:
                mismatches.append(
                    _mismatch(
                        "current_summary_gate_mismatch",
                        label,
                        "current summary",
                        f"CURRENT_STATUS.current_phase is {status_doc.get('current_phase')!r} "
                        f"but the current summary never names it",
                    )
                )


def check_retracted_evidence(status_doc: dict[str, Any], mismatches: list[dict[str, Any]]) -> None:
    """Level 5: retracted results may not be presented as current positives."""
    pctom = status_doc.get("pctom_r_workstream") or {}
    status = str(pctom.get("status", ""))
    unverified = [str(item).lower() for item in pctom.get("unverified") or []]
    claims_benefit = "benefit_proven" in status.lower() or "advantage_proven" in status.lower()
    still_unproven = any("advantage" in item or "benefit" in item for item in unverified)
    if claims_benefit and still_unproven:
        mismatches.append(
            _mismatch(
                "retracted_result_presented_as_current",
                "CURRENT_STATUS.json",
                "pctom_r_workstream.status",
                f"status {status!r} claims proven benefit while unverified still lists it",
            )
        )


def run(args: argparse.Namespace) -> dict[str, Any]:
    mismatches: list[dict[str, Any]] = []
    status_path = args.current_status
    if not status_path.is_file():
        mismatches.append(
            _mismatch("current_status_missing", str(status_path), "-", "machine projection absent")
        )
        status_doc: dict[str, Any] = {}
        resolved: dict[str, Any] = {}
    else:
        status_doc = json.loads(status_path.read_text(encoding="utf-8"))
        resolved = check_receipts(status_doc, mismatches)
        check_blockers_and_next_steps(status_doc, resolved, mismatches)
        check_prose_surfaces(status_doc, resolved, mismatches)
        check_retracted_evidence(status_doc, mismatches)

    return {
        "schema": "persona_dream.current_state_consistency.v1",
        "created_at": utc_now(),
        "status": "PASS_CURRENT_STATE_CONSISTENT" if not mismatches
        else "BLOCKED_CURRENT_STATE_CONTRADICTS_RECEIPTS",
        "mocked": False,
        "live": False,
        "current_status_path": str(status_path),
        "hierarchy": [
            "named receipt status and hash",
            "CURRENT_STATUS.json machine projection",
            "PROJECT_KNOWLEDGE.md current summary",
            "README.md current state",
            "historical log entries (must be marked, never current)",
        ],
        "stages": resolved,
        "mismatches": mismatches,
        "mismatch_count": len(mismatches),
        "claims": {
            "proves": ["current-state surfaces do not contradict named receipts"]
            if not mismatches
            else [],
            "does_not_prove": [
                "receipt correctness",
                "that the described work is complete",
                "anything about surfaces not named in STAGES",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-status", type=Path, default=CURRENT_STATUS)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--json", action="store_true", help="Print the full receipt as JSON.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on any mismatch.")
    args = parser.parse_args()

    receipt = run(args)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(f"current-state consistency: {receipt['status']}")
        for row in receipt["mismatches"]:
            print(
                f"  {row['rule']}: {row['file']} :: {row['json_path']}"
                + (f" :: {row['offending']!r}" if row.get("offending") else "")
            )
            print(f"      {row['detail']}")
        if not receipt["mismatches"]:
            print(f"  {len(receipt['stages'])} stages checked, 0 mismatches")

    if receipt["mismatches"] and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
