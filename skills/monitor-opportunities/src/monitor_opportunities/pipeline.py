"""Single local Stage 0 run transaction composed from read-only phase artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import IMMUTABLE_GOAL
from .discovery import sweep
from .fixture import built_in_fixture
from .ranking import rank
from .report import load_manifest, render_report
from .tailoring import tailor
from .util import read_json, sha256_json, stable_id, utc_now, write_json


def _report_from_fixture(run_id: str) -> dict[str, Any]:
    report = built_in_fixture()
    report["run_id"] = run_id
    report["generated_at"] = utc_now()
    report["operational_readiness"] = "STAGE_0_LOCAL_READY"
    return report


def run_stage0(skill_dir: Path, out_dir: Path, fixture_dir: Path | None = None) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = stable_id("run", {"out": str(out_dir), "started": utc_now()})
    phases = []
    discovery_dir = out_dir / "discovery"
    ranking_dir = out_dir / "ranking"
    tailoring_dir = out_dir / "tailoring"
    report_dir = out_dir / "report"

    discovery_receipt = sweep(
        skill_dir=skill_dir,
        lanes={"A", "B", "C"},
        out_dir=discovery_dir,
        fixture_dir=fixture_dir,
    )
    phases.append({"phase": "DISCOVERY_COMPLETE", "artifact": str(discovery_dir / "run-manifest.json")})
    ranking_receipt = rank(discovery_dir, 8, ranking_dir)
    phases.append({"phase": "RANKING_COMPLETE", "artifact": str(ranking_dir / "ranking-receipt.json")})
    claims_path = skill_dir / "tests" / "fixtures" / "claims" / "approved-claims.json"
    tailoring_receipt = None
    if claims_path.exists():
        tailoring_receipt = tailor("fixture:eligible-ai-architect", claims_path, tailoring_dir)
        phases.append({"phase": "TAILORING_COMPLETE", "artifact": str(tailoring_dir / "tailoring-receipt.json")})

    manifest_path = out_dir / "report-manifest.json"
    report_manifest = _report_from_fixture(run_id)
    write_json(manifest_path, report_manifest)
    manifest = load_manifest(manifest_path)
    render_artifacts = render_report(manifest, report_dir)
    phases.append({"phase": "REPORT_READY", "artifact": render_artifacts["report_html"]})
    receipt = {
        "schema": "monitor_opportunities.run_receipt.v1",
        "run_id": run_id,
        "started_at": report_manifest["generated_at"],
        "completed_at": utc_now(),
        "terminal_state": "AWAITING_HUMAN",
        "mocked": False,
        "live": fixture_dir is None,
        "external_effects": False,
        "immutable_goal": IMMUTABLE_GOAL,
        "budget": {"currency": "USD", "max": 10.0, "estimated": 0.0, "actual": 0.0},
        "phase_artifacts": phases,
        "discovery_receipt": discovery_receipt,
        "ranking_receipt": ranking_receipt,
        "tailoring_receipt": tailoring_receipt,
        "report_manifest_sha256": sha256_json(report_manifest),
        "report_html": render_artifacts["report_html"],
        "report_json": render_artifacts["report_json"],
    }
    write_json(out_dir / "run-receipt.json", receipt)
    return receipt


def status_for_run(run_dir: Path) -> dict[str, Any]:
    receipt_path = run_dir / "run-receipt.json"
    if not receipt_path.exists():
        return {"schema": "monitor_opportunities.run_status.v1", "run_dir": str(run_dir), "state": "NOT_FOUND"}
    receipt = read_json(receipt_path)
    return {
        "schema": "monitor_opportunities.run_status.v1",
        "run_dir": str(run_dir),
        "run_id": receipt["run_id"],
        "state": receipt["terminal_state"],
        "report_html": receipt["report_html"],
        "external_effects": receipt["external_effects"],
    }
