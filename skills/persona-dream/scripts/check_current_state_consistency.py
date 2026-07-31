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
    Stage(
        stage_id="P2_live_chain_receipt",
        receipt="reports/goal_v5/continuity/live_chain/RECEIPT.json",
        accepted_prefix="PASS_PERSONA_DREAM_LIVE_CHAIN",
        contradiction_markers=(
            "joined live-chain receipt does not exist",
            "joined live chain missing",
            "produce the full accepted-dream to live-chain proof",
            "produce reports/goal_v5/continuity/live_chain/receipt.json",
            "write reports/goal_v5/continuity/live_chain/receipt.json",
            "the full joined live-chain receipt has not been produced",
            "current blocker: the joined live-chain receipt",
        ),
        status_pin="continuity_state.latest_live_chain_receipt_sha256",
    ),
    Stage(
        stage_id="P2_session_arc_bias",
        receipt="reports/goal_v5/continuity/session_arc_bias/RECEIPT.json",
        accepted_prefix="PASS_SESSION_ARC_BIAS_RECEIPT",
        contradiction_markers=(
            "publish the persona arc-bias artifact",
            "derive an arc bias from the continuity ledger",
            "session arc bias missing",
            "publish it under a stable schema",
            "session_arc_bias.v1 artifact missing",
        ),
        status_pin="continuity_state.latest_session_arc_bias_receipt_sha256",
    ),
    Stage(
        stage_id="P2_sparta_arc_bias_handoff",
        receipt="reports/goal_v5/continuity/sparta_arc_bias_handoff/RECEIPT.json",
        accepted_prefix="PASS_SPARTA_ARC_BIAS_HANDOFF_RECEIPT",
        contradiction_markers=(
            "write the sparta consumer contract",
            "publish a machine-checkable sparta consumer contract",
            "sparta arc-bias handoff missing",
            "sparta_arc_bias_handoff receipt missing",
        ),
        status_pin="continuity_state.latest_sparta_arc_bias_handoff_receipt_sha256",
    ),
    Stage(
        stage_id="P2_five_cycle_reliability_pilot",
        receipt="reports/goal_v5/continuity/reliability/AGGREGATE_RECEIPT.json",
        accepted_prefix="PASS_LIVE_CHAIN_RELIABILITY_PILOT",
        contradiction_markers=(
            "five-cycle repeated full dream-pipeline reliability",
            "no five-cycle campaign exists",
            "run the five-cycle engineering reliability campaign",
            "run five fresh continuity-chain cycles",
            "run five fresh continuity chain cycles",
            "repeated full dream-pipeline reliability is not proven",
            "five-cycle reliability campaign with distinct cycle ids",
        ),
        status_pin="continuity_state.latest_reliability_aggregate_receipt_sha256",
    ),
)


#: The scoped claim registry required by #1132. Every present-tense claim in
#: the surfaces must resolve to exactly one of these ids; the checker blocks
#: when a claim id is missing, under-specified, or asserts more than its scope.
CLAIM_IDS = (
    "p2_continuity_feasibility_pilot",
    "p2_continuity_reliability_soak",
    "p2_restart_recovery",
    "full_phase01_16_media_pipeline_reliability",
    "machine_speaker_identity_by_receipt_and_condition",
    "human_perceived_emotion_and_identity",
    "pctom_apparatus_integrity",
    "pctom_measurement_validity",
    "pctom_heldout_benefit",
    "previous_video_attachment_causality",
)

REQUIRED_CLAIM_FIELDS = ("status", "scope", "proves", "does_not_prove")

#: A speaker-recognition number may only appear next to its exact receipt and
#: render condition. Bare "separation 0.208427" reads as a universal score.
RECOGNITION_NUMBERS = ("0.208427", "0.159977")
CONDITION_TOKENS = (
    "live_chain", "live chain", "live-chain",
    "long_identity", "long identity", "long-identity",
    "4.68", "4.64",
)

#: A paragraph mentioning the N=5 pilot together with production/full-pipeline
#: reliability must carry one of these, or it is conflating scopes.
NEGATION_TOKENS = ("not", "unproven", "remains", "distinct", "rather than", "beyond", "instead")
PILOT_TOKENS = ("five-cycle", "five cycle", "n=5", "5/5")
OVERREACH_TOKENS = ("production reliability", "full pipeline", "phase 01-16 reliability", "full phase 01-16")


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


def _walk_unverified(obj: Any, path: str, out: list[tuple[str, str]]) -> None:
    if isinstance(obj, dict):
        for key, val in obj.items():
            sub = f"{path}.{key}" if path else key
            if key == "unverified" and isinstance(val, list):
                for idx, item in enumerate(val):
                    out.append((f"{sub}[{idx}]", str(item)))
            else:
                _walk_unverified(val, sub, out)
    elif isinstance(obj, list):
        for idx, val in enumerate(obj):
            _walk_unverified(val, f"{path}[{idx}]", out)


def check_claim_registry(status_doc: dict[str, Any], mismatches: list[dict[str, Any]]) -> None:
    """#1132: every present-tense claim carries an exact scope and receipt.

    The registry lives at ``current_claims``. Scope conflations the ticket
    names — pilot-as-production, full-pipeline-from-continuity, human-from-WER,
    PCTOM apparatus-as-benefit, unpaired previous-video benefit — each block
    with a named rule.
    """
    registry = status_doc.get("current_claims")
    if not isinstance(registry, dict):
        mismatches.append(
            _mismatch("claim_registry_missing", "CURRENT_STATUS.json", "current_claims",
                      "the scoped claim registry required by #1132 is absent")
        )
        return

    for claim_id in CLAIM_IDS:
        claim = registry.get(claim_id)
        if not isinstance(claim, dict):
            mismatches.append(
                _mismatch("claim_missing", "CURRENT_STATUS.json", f"current_claims.{claim_id}",
                          "required scoped claim object is absent")
            )
            continue
        for field in REQUIRED_CLAIM_FIELDS:
            if not claim.get(field):
                mismatches.append(
                    _mismatch("claim_field_missing", "CURRENT_STATUS.json",
                              f"current_claims.{claim_id}.{field}",
                              "scoped claim object lacks a required field")
                )

        status = str(claim.get("status", ""))
        is_pass = status.startswith("PASS")
        receipt_rel = claim.get("receipt")
        pinned_sha = claim.get("receipt_sha256")

        if receipt_rel:
            receipt_path = ROOT / str(receipt_rel)
            if not receipt_path.is_file():
                mismatches.append(
                    _mismatch("claim_receipt_missing", "CURRENT_STATUS.json",
                              f"current_claims.{claim_id}.receipt",
                              f"named receipt {receipt_rel} does not exist")
                )
            elif pinned_sha and pinned_sha != sha256_file(receipt_path):
                mismatches.append(
                    _mismatch("claim_receipt_hash_mismatch", "CURRENT_STATUS.json",
                              f"current_claims.{claim_id}.receipt_sha256",
                              f"pinned {pinned_sha} but receipt hashes to {sha256_file(receipt_path)}")
                )
        elif is_pass:
            mismatches.append(
                _mismatch("claim_pass_without_receipt", "CURRENT_STATUS.json",
                          f"current_claims.{claim_id}",
                          f"status {status!r} asserts PASS with no receipt")
            )

        if claim.get("successor_issue") and not claim.get("successor_resolved") and is_pass:
            mismatches.append(
                _mismatch("claim_pass_while_successor_open", "CURRENT_STATUS.json",
                          f"current_claims.{claim_id}.status",
                          f"status {status!r} asserts PASS while successor "
                          f"{claim.get('successor_issue')} is open")
            )

    pilot = registry.get("p2_continuity_feasibility_pilot") or {}
    pilot_text = (str(pilot.get("status", "")) + " " + str(pilot.get("scope", ""))).lower()
    if any(tok in pilot_text for tok in OVERREACH_TOKENS):
        mismatches.append(
            _mismatch("pilot_described_as_production_or_full_pipeline", "CURRENT_STATUS.json",
                      "current_claims.p2_continuity_feasibility_pilot",
                      "the N=5 engineering pilot claims production or full-pipeline scope")
        )

    full = registry.get("full_phase01_16_media_pipeline_reliability") or {}
    if str(full.get("status", "")).startswith("PASS"):
        receipt_rel = str(full.get("receipt", ""))
        if not receipt_rel or "goal_v5/continuity" in receipt_rel:
            mismatches.append(
                _mismatch("full_pipeline_reliability_inferred_from_continuity",
                          "CURRENT_STATUS.json",
                          "current_claims.full_phase01_16_media_pipeline_reliability",
                          "full Phase 01-16 reliability asserted from downstream continuity "
                          "receipts or from no receipt at all")
            )

    human = registry.get("human_perceived_emotion_and_identity") or {}
    if str(human.get("status", "")).startswith("PASS"):
        responses = str(human.get("valid_human_responses", "0/0"))
        try:
            have, need = (int(part) for part in responses.split("/", 1))
        except ValueError:
            have, need = 0, 1
        receipt_rel = str(human.get("receipt", ""))
        if have < need or "voice_recognition" in receipt_rel or "wer" in receipt_rel.lower():
            mismatches.append(
                _mismatch("human_perception_inferred_from_machine_scores",
                          "CURRENT_STATUS.json",
                          "current_claims.human_perceived_emotion_and_identity",
                          f"human perception asserted with responses {responses} and receipt "
                          f"{receipt_rel!r}; WER/embedding receipts are machine evidence")
            )

    video = registry.get("previous_video_attachment_causality") or {}
    if str(video.get("status", "")).startswith("PASS") and not video.get("paired_receipt"):
        mismatches.append(
            _mismatch("previous_video_benefit_without_paired_receipt", "CURRENT_STATUS.json",
                      "current_claims.previous_video_attachment_causality",
                      "previous-video benefit asserted without a valid #1059 paired receipt")
        )

    rows: list[tuple[str, str]] = []
    _walk_unverified(status_doc, "", rows)
    for json_path, text in rows:
        low = text.lower()
        if ("five-cycle" in low or "five cycle" in low) and "reliab" in low:
            if not any(tok in low for tok in ("phase 01-16", "full ", "media pipeline", "media-pipeline")):
                mismatches.append(
                    _mismatch("completed_pilot_listed_unverified_without_scope",
                              "CURRENT_STATUS.json", json_path,
                              "a five-cycle reliability item is listed unverified without a "
                              "distinct scope id, contradicting the completed P2 pilot",
                              text)
                )

    for claim_id in CLAIM_IDS:
        claim = registry.get(claim_id) or {}
        token = claim.get("surface_token")
        if not token:
            continue
        for label, path in (("README.md", README), ("PROJECT_KNOWLEDGE.md", PROJECT_KNOWLEDGE)):
            summary = current_summary(path)
            if summary and str(token).lower() not in summary:
                mismatches.append(
                    _mismatch("surface_missing_active_successor", label,
                              f"current_claims.{claim_id}.surface_token",
                              f"current summary never names active successor {token}")
                )


def full_paragraphs(path: Path) -> list[tuple[int, str]]:
    """Whole-file paragraphs; the number/scope rules apply beyond the summary."""
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
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


def check_scope_conflation_prose(mismatches: list[dict[str, Any]]) -> None:
    """#1132 text rules over README and PROJECT_KNOWLEDGE.

    A recognition number must sit next to its receipt and render condition; a
    pilot mention must not share a paragraph with production/full-pipeline
    reliability unless the paragraph itself draws the distinction. Historical
    paragraphs are exempt, as everywhere else in this checker.
    """
    for label, path in (("README.md", README), ("PROJECT_KNOWLEDGE.md", PROJECT_KNOWLEDGE)):
        for line_no, para in full_paragraphs(path):
            if any(mark in para for mark in HISTORICAL_MARKERS):
                continue
            for number in RECOGNITION_NUMBERS:
                if number in para:
                    if "receipt" not in para or not any(tok in para for tok in CONDITION_TOKENS):
                        mismatches.append(
                            _mismatch("unqualified_recognition_number", label,
                                      f"line {line_no}",
                                      f"separation {number} appears without its exact receipt "
                                      f"and render condition; a single observed separation is "
                                      f"not a universal identity result",
                                      number)
                        )
            if any(tok in para for tok in PILOT_TOKENS) and any(tok in para for tok in OVERREACH_TOKENS):
                if not any(tok in para for tok in NEGATION_TOKENS):
                    mismatches.append(
                        _mismatch("pilot_conflated_with_production_or_full_pipeline", label,
                                  f"line {line_no}",
                                  "the N=5 pilot and production/full-pipeline reliability share "
                                  "a paragraph with no distinguishing language")
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
        check_claim_registry(status_doc, mismatches)
        check_scope_conflation_prose(mismatches)

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
