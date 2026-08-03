"""Deterministic positive and adversarial verification for the Stage 0 kernel."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from .contracts import ContractError, IMMUTABLE_GOAL, validate_manifest
from .report import render_report


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def source_version(skill_dir: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=skill_dir,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip() or None


from .fixture import built_in_fixture


def _expect_rejection(
    name: str,
    raw: dict[str, Any],
    expected_code: str,
) -> dict[str, Any]:
    try:
        validate_manifest(raw)
    except ContractError as exc:
        return {
            "name": name,
            "status": "PASS" if exc.code == expected_code else "FAIL",
            "expected_error": expected_code,
            "observed_error": exc.code,
            "detail": exc.message,
        }
    return {
        "name": name,
        "status": "FAIL",
        "expected_error": expected_code,
        "observed_error": None,
        "detail": "Mutation was incorrectly accepted",
    }


def run_verification(out_dir: Path, fixture_path: Path | None = None) -> dict[str, Any]:
    started = utc_now()
    out_dir.mkdir(parents=True, exist_ok=True)
    if fixture_path is not None and fixture_path.exists():
        raw = json.loads(fixture_path.read_text(encoding="utf-8"))
        fixture_source = str(fixture_path)
    else:
        raw = built_in_fixture()
        fixture_source = "built-in"

    fixture_bytes = (json.dumps(raw, sort_keys=True, separators=(",", ":")) + "\n").encode()
    cases: list[dict[str, Any]] = []

    try:
        manifest = validate_manifest(copy.deepcopy(raw))
        artifacts = render_report(manifest, out_dir / "positive-report")
        cases.append(
            {
                "name": "valid_stage0_report",
                "status": "PASS",
                "detail": artifacts,
            }
        )
    except ContractError as exc:
        cases.append(
            {
                "name": "valid_stage0_report",
                "status": "FAIL",
                "detail": exc.as_dict(),
            }
        )

    mutations: list[tuple[str, Callable[[dict[str, Any]], None], str]] = []

    def hidden(value: dict[str, Any]) -> None:
        value["outreach_packets"][0]["visible_in_report"] = False

    mutations.append(("hidden_action_artifact", hidden, "HIDDEN_ACTION_ARTIFACT"))

    def feed_mislabeled(value: dict[str, Any]) -> None:
        value["lane_coverage"][1]["result_status"] = "NO_MATCHES"

    mutations.append(("feed_down_as_no_matches", feed_mislabeled, "FEED_FAILURE_MISLABELED"))

    def relocation(value: dict[str, Any]) -> None:
        value["opportunities"][0]["location"]["relocation_required"] = True

    mutations.append(("relocation_shortlisted", relocation, "RELOCATION_SHORTLISTED"))

    def sendable(value: dict[str, Any]) -> None:
        value["outreach_packets"][0]["sendable"] = True

    mutations.append(("sendable_outreach", sendable, "OUTREACH_SENDABLE_STAGE0"))

    def ats_authorized(value: dict[str, Any]) -> None:
        value["applications"][0]["authorized"] = True

    mutations.append(("ats_authorized", ats_authorized, "ATS_AUTHORIZED_STAGE0"))

    def free_text(value: dict[str, Any]) -> None:
        field = value["applications"][0]["fields"][0]
        field["disposition"] = "exact_approved_answer"
        field["automated_answer"] = "Generated response"

    mutations.append(
        ("free_text_autofilled", free_text, "HUMAN_REQUIRED_FIELD_AUTOFILLED")
    )

    def nine(value: dict[str, Any]) -> None:
        seed = copy.deepcopy(value["opportunities"][0])
        while len(value["opportunities"]) < 9:
            item = copy.deepcopy(seed)
            item["opportunity_id"] = f"opp:extra:{len(value['opportunities'])}"
            value["opportunities"].append(item)

    mutations.append(("nine_shortlisted", nine, "SHORTLIST_LIMIT_EXCEEDED"))

    def unknown_status(value: dict[str, Any]) -> None:
        value["lane_coverage"][0]["result_status"] = "MAYBE"

    mutations.append(("unknown_source_status", unknown_status, "UNKNOWN_SOURCE_STATUS"))

    for name, mutate, expected in mutations:
        candidate = copy.deepcopy(raw)
        mutate(candidate)
        cases.append(_expect_rejection(name, candidate, expected))

    overall = "PASS" if all(case["status"] == "PASS" for case in cases) else "FAIL"
    skill_dir = Path(__file__).resolve().parents[2]
    receipt = {
        "schema": "monitor_opportunities.verify.v1",
        "command": "verify",
        "started_at": started,
        "completed_at": utc_now(),
        "source_version": source_version(skill_dir),
        "contract_version": "0.2.0",
        "fixture": {
            "source": fixture_source,
            "sha256": hashlib.sha256(fixture_bytes).hexdigest(),
        },
        "mocked": False,
        "live": True,
        "network_used": False,
        "external_effects": False,
        "cases": cases,
        "overall": overall,
        "non_claims": [
            "Verification proves only the local Stage 0 report kernel.",
            "It does not prove live discovery, ranking, resume generation, scheduling, or external effects.",
        ],
    }
    receipt_path = out_dir / "verification-receipt.json"
    receipt_text = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    receipt_path.write_text(receipt_text, encoding="utf-8")
    if receipt_path.read_text(encoding="utf-8") != receipt_text:
        raise ContractError("VERIFY_READBACK_FAILED", "Verification receipt did not read back")
    return receipt
