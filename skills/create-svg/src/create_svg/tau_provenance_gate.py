"""Tau provenance gate for SVG variant-loop outputs.

A Tau variant candidate is not publishable merely because an SVG exists on disk.
This gate binds the SVG bytes to a Tau run, creator node receipt, judge receipt,
and screenshot-backed create_svg.visual_gate.v1 PASS receipt.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ProvenanceGateReceipt(BaseModel):
    """Machine-readable decision for a Tau-backed SVG candidate."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["create_svg.tau_variant_provenance_gate.v1"] = "create_svg.tau_variant_provenance_gate.v1"
    status: Literal["PASS", "BLOCKED"]
    failure_code: str | None = None
    errors: list[str] = Field(default_factory=list)
    launch_receipt_path: str
    run_dir: str | None = None
    tau_run_receipt_path: str | None = None
    creator_node_id: str
    creator_node_receipt_path: str | None = None
    judge_node_id: str
    judge_node_receipt_path: str | None = None
    candidate_receipt_path: str
    visual_gate_receipt_path: str
    svg_path: str
    svg_sha256: str | None = None
    screenshot_path: str | None = None
    screenshot_sha256: str | None = None
    goal: str | None = None
    target: str | None = None
    target_size: str | None = None
    mocked: bool = False
    live: bool = True
    proof_scope: str
    does_not_prove: str


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _read_json(path: Path, errors: list[str], code: str) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        errors.append(f"{code}: missing file: {path}")
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{code}: unreadable JSON: {path}: {exc}")
        return None
    if not isinstance(payload, dict):
        errors.append(f"{code}: JSON root must be object: {path}")
        return None
    return payload


def _first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists() and path.is_file():
            return path
    return None


def _resolve_run_dir(launch: dict[str, Any], launch_path: Path) -> Path | None:
    value = launch.get("run_dir") or launch.get("run_directory")
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = launch_path.parent / path
    return path.resolve()


def _receipt_ok(payload: dict[str, Any] | None) -> bool:
    if payload is None:
        return False
    return payload.get("ok") is True or payload.get("status") == "PASS"


def _candidate_svg_path(candidate: dict[str, Any]) -> str | None:
    value = candidate.get("svg_path") or candidate.get("artifact_path")
    return value if isinstance(value, str) and value.strip() else None


def _candidate_svg_sha(candidate: dict[str, Any]) -> str | None:
    value = candidate.get("svg_sha256") or candidate.get("artifact_sha256")
    return value if isinstance(value, str) and value.strip() else None


def _hash_matches(observed: str | None, expected_prefixed: str | None) -> bool:
    if not observed or not expected_prefixed:
        return False
    expected_hex = expected_prefixed.removeprefix("sha256:")
    return observed == expected_prefixed or observed == expected_hex


def _same_path(left: str | None, right: Path) -> bool:
    if not left:
        return False
    return Path(left).expanduser().resolve() == right.resolve()


def evaluate_tau_variant_provenance(
    *,
    launch_receipt: Path,
    svg: Path,
    candidate_receipt: Path,
    visual_gate_receipt: Path,
    creator_node_id: str,
    judge_node_id: str,
) -> ProvenanceGateReceipt:
    """Fail closed unless one SVG candidate is bound to complete Tau evidence."""

    errors: list[str] = []
    launch_receipt = launch_receipt.expanduser().resolve()
    svg = svg.expanduser().resolve()
    candidate_receipt = candidate_receipt.expanduser().resolve()
    visual_gate_receipt = visual_gate_receipt.expanduser().resolve()

    launch = _read_json(launch_receipt, errors, "create_svg_tau_provenance_missing_launch_receipt")
    if not svg.exists() or not svg.is_file():
        errors.append(f"create_svg_tau_provenance_hash_mismatch: missing svg file: {svg}")
        svg_sha: str | None = None
    else:
        svg_sha = _sha256(svg)

    run_dir = _resolve_run_dir(launch, launch_receipt) if launch else None
    if run_dir is None or not run_dir.exists() or not run_dir.is_dir():
        errors.append(f"create_svg_tau_provenance_missing_tau_receipt: launch receipt does not name a readable run_dir: {run_dir}")
        run_dir = None
    tau_receipt_path = (
        _first_existing([run_dir / "tau-receipts" / "dag-receipt.json", run_dir / "tau-receipts" / "dag-progress.json"])
        if run_dir
        else None
    )
    tau_receipt = _read_json(tau_receipt_path, errors, "create_svg_tau_provenance_missing_tau_receipt") if tau_receipt_path else None
    if run_dir and tau_receipt_path is None:
        errors.append("create_svg_tau_provenance_missing_tau_receipt: no dag-receipt.json or dag-progress.json under run_dir/tau-receipts")
    if tau_receipt is not None and not _receipt_ok(tau_receipt):
        errors.append("create_svg_tau_provenance_missing_tau_receipt: Tau run receipt is not PASS/ok")

    creator_receipt_path = run_dir / "node-artifacts" / creator_node_id / "node-receipt.json" if run_dir else None
    creator_receipt = _read_json(creator_receipt_path, errors, "create_svg_tau_provenance_missing_node_receipt") if creator_receipt_path else None
    if creator_receipt is not None and not _receipt_ok(creator_receipt):
        errors.append("create_svg_tau_provenance_missing_node_receipt: creator node receipt is not PASS/ok")
    if creator_receipt is not None and str(creator_receipt.get("node_id") or creator_node_id) != creator_node_id:
        errors.append("create_svg_tau_provenance_binding_mismatch: creator node receipt node_id mismatch")

    judge_receipt_path = run_dir / "node-artifacts" / judge_node_id / "node-receipt.json" if run_dir else None
    judge_receipt = _read_json(judge_receipt_path, errors, "create_svg_tau_provenance_missing_judge_receipt") if judge_receipt_path else None
    if judge_receipt is not None and not _receipt_ok(judge_receipt):
        errors.append("create_svg_tau_provenance_missing_judge_receipt: judge node receipt is not PASS/ok")
    if judge_receipt is not None and str(judge_receipt.get("node_id") or judge_node_id) != judge_node_id:
        errors.append("create_svg_tau_provenance_binding_mismatch: judge node receipt node_id mismatch")

    candidate = _read_json(candidate_receipt, errors, "create_svg_tau_provenance_missing_candidate_receipt")
    if candidate is not None:
        if candidate.get("schema") != "create_svg.variant_candidate.v1":
            errors.append("create_svg_tau_provenance_binding_mismatch: candidate receipt schema mismatch")
        if candidate.get("mocked") is not False or candidate.get("live") is not True:
            errors.append("create_svg_tau_provenance_binding_mismatch: candidate receipt must declare mocked=false and live=true")
        if not _same_path(_candidate_svg_path(candidate), svg):
            errors.append("create_svg_tau_provenance_binding_mismatch: candidate svg_path does not match requested svg")
        candidate_sha = _candidate_svg_sha(candidate)
        if svg_sha and not _hash_matches(candidate_sha, svg_sha):
            errors.append("create_svg_tau_provenance_hash_mismatch: candidate svg sha256 does not match bytes on disk")
        if str(candidate.get("creator_node_id") or candidate.get("node_id") or "") != creator_node_id:
            errors.append("create_svg_tau_provenance_binding_mismatch: candidate creator_node_id does not match")
        if run_dir and str(Path(str(candidate.get("tau_run_dir") or run_dir)).expanduser().resolve()) != str(run_dir):
            errors.append("create_svg_tau_provenance_binding_mismatch: candidate tau_run_dir does not match launch run_dir")

    visual = _read_json(visual_gate_receipt, errors, "create_svg_tau_provenance_visual_gate_missing")
    screenshot_path: str | None = None
    screenshot_sha: str | None = None
    if visual is not None:
        if visual.get("kind") != "create_svg.visual_gate.v1":
            errors.append("create_svg_tau_provenance_visual_gate_missing: visual gate receipt kind mismatch")
        if visual.get("status") != "PASS" or visual.get("represents_goal") is not True or visual.get("attractive") is not True:
            errors.append("create_svg_tau_provenance_visual_gate_not_pass: visual gate receipt is not PASS")
        if svg_sha and (not _hash_matches(str(visual.get("svg_sha256") or ""), svg_sha) or not _same_path(str(visual.get("svg_path") or ""), svg)):
            errors.append("create_svg_tau_provenance_hash_mismatch: visual gate svg binding does not match requested svg")
        screenshot_path = visual.get("screenshot_path") if isinstance(visual.get("screenshot_path"), str) else None
        screenshot_sha = visual.get("screenshot_sha256") if isinstance(visual.get("screenshot_sha256"), str) else None
        if not screenshot_path or not screenshot_sha:
            errors.append("create_svg_tau_provenance_visual_gate_missing: visual gate omitted screenshot path/hash")
        else:
            screenshot = Path(screenshot_path).expanduser().resolve()
            if not screenshot.exists() or not screenshot.is_file():
                errors.append("create_svg_tau_provenance_visual_gate_missing: screenshot path is unreadable")
            elif not _hash_matches(screenshot_sha, _sha256(screenshot)):
                errors.append("create_svg_tau_provenance_hash_mismatch: visual gate screenshot sha256 does not match bytes on disk")
        if launch is not None:
            for field in ("goal", "target", "target_size"):
                launch_value = launch.get(field)
                visual_value = visual.get(field)
                if isinstance(launch_value, str) and launch_value and visual_value != launch_value:
                    errors.append(f"create_svg_tau_provenance_binding_mismatch: visual gate {field} does not match launch receipt")

    failure_code = None
    if errors:
        for candidate_code in (
            "create_svg_tau_provenance_missing_candidate_receipt",
            "create_svg_tau_provenance_missing_node_receipt",
            "create_svg_tau_provenance_missing_judge_receipt",
            "create_svg_tau_provenance_visual_gate_missing",
            "create_svg_tau_provenance_visual_gate_not_pass",
            "create_svg_tau_provenance_hash_mismatch",
            "create_svg_tau_provenance_binding_mismatch",
            "create_svg_tau_provenance_missing_tau_receipt",
            "create_svg_tau_provenance_missing_launch_receipt",
        ):
            if any(error.startswith(candidate_code) for error in errors):
                failure_code = candidate_code
                break
        failure_code = failure_code or "create_svg_tau_provenance_binding_mismatch"

    return ProvenanceGateReceipt(
        status="BLOCKED" if errors else "PASS",
        failure_code=failure_code,
        errors=errors,
        launch_receipt_path=str(launch_receipt),
        run_dir=str(run_dir) if run_dir else None,
        tau_run_receipt_path=str(tau_receipt_path) if tau_receipt_path else None,
        creator_node_id=creator_node_id,
        creator_node_receipt_path=str(creator_receipt_path) if creator_receipt_path else None,
        judge_node_id=judge_node_id,
        judge_node_receipt_path=str(judge_receipt_path) if judge_receipt_path else None,
        candidate_receipt_path=str(candidate_receipt),
        visual_gate_receipt_path=str(visual_gate_receipt),
        svg_path=str(svg),
        svg_sha256=svg_sha,
        screenshot_path=screenshot_path,
        screenshot_sha256=screenshot_sha,
        goal=str(launch.get("goal")) if isinstance(launch, dict) and launch.get("goal") is not None else None,
        target=str(launch.get("target")) if isinstance(launch, dict) and launch.get("target") is not None else None,
        target_size=str(launch.get("target_size")) if isinstance(launch, dict) and launch.get("target_size") is not None else None,
        proof_scope=(
            "This receipt proves one SVG path is bound to a PASS Tau run receipt, PASS creator node receipt, "
            "PASS judge node receipt, create_svg.variant_candidate.v1 receipt, and screenshot-bound "
            "create_svg.visual_gate.v1 PASS receipt."
        ),
        does_not_prove="Deployment, README wiring, universal aesthetic approval, or provider semantic quality outside the cited receipts.",
    )
