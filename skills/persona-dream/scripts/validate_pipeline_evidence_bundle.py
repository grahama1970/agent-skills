#!/usr/bin/env python3
"""Validate the current Persona Dream pipeline evidence bundle.

This command is the operator-facing "where is the pipeline stuck?" check. It
composes existing validators and preserves `validate-run-root --direction
backward` as the authority for phase order. The Panel 01 comparison report is a
supporting reality-check surface, not a provider-readiness gate.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from validate_panel_comparison_report import validate_panel_comparison_report
from validate_pipeline_loop_run import validate_pipeline_loop_run
from validate_provider_media_public_handoff import validate_provider_media_public_handoff
from validate_provider_media_publication_preflight import validate_provider_media_publication_preflight
from validate_run_root_pipeline import validate_run_root


def _block(result: dict[str, Any], reason: str, *, phase: str = "pipeline_evidence_bundle") -> dict[str, Any]:
    result["status"] = "BLOCKED"
    result["first_blocker"] = {"phase": phase, "reason": reason}
    return result


def _validation_summary(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": result.get("status"),
        "first_blocker": result.get("first_blocker"),
        "mocked": result.get("mocked"),
        "live": result.get("live"),
        "exercised": result.get("exercised"),
        "unverified": result.get("unverified"),
    }


def _policy_from_loop(loop_result: dict[str, Any]) -> dict[str, bool | None]:
    try:
        receipt = json.loads(Path(loop_result["receipt"]).read_text(encoding="utf-8"))
    except Exception:
        return {
            "kling_call_allowed": None,
            "public_upload_allowed_without_explicit_authorization": None,
            "nano_banana_final_panel_allowed": None,
        }
    policy = receipt.get("policy") if isinstance(receipt, dict) else {}
    if not isinstance(policy, dict):
        policy = {}
    return {
        "kling_call_allowed": policy.get("kling_call_allowed"),
        "public_upload_allowed_without_explicit_authorization": policy.get(
            "public_upload_allowed_without_explicit_authorization"
        ),
        "nano_banana_final_panel_allowed": policy.get("nano_banana_final_panel_allowed"),
    }


def validate_pipeline_evidence_bundle(
    *,
    run_root: Path,
    pipeline_loop_run_receipt: Path,
    publication_work_order: Path,
    local_staging_receipt: Path,
    public_probe_receipt: Path,
    panel_report: Path,
    panel_report_status_json: Path | None = None,
    publication_preflight_receipt: Path | None = None,
    publication_authorization_receipt: Path | None = None,
) -> dict[str, Any]:
    run_root = run_root.resolve()
    pipeline_loop_run_receipt = pipeline_loop_run_receipt.resolve()
    publication_work_order = publication_work_order.resolve()
    local_staging_receipt = local_staging_receipt.resolve()
    public_probe_receipt = public_probe_receipt.resolve()
    panel_report = panel_report.resolve()
    panel_report_status_json = panel_report_status_json.resolve() if panel_report_status_json else None
    publication_preflight_receipt = publication_preflight_receipt.resolve() if publication_preflight_receipt else None
    publication_authorization_receipt = (
        publication_authorization_receipt.resolve() if publication_authorization_receipt else None
    )

    result: dict[str, Any] = {
        "schema": "persona_dream.pipeline_evidence_bundle_validation.v1",
        "status": "PASS_PIPELINE_EVIDENCE_BUNDLE",
        "first_blocker": None,
        "run_root": str(run_root),
        "inputs": {
            "pipeline_loop_run_receipt": str(pipeline_loop_run_receipt),
            "publication_work_order": str(publication_work_order),
            "local_staging_receipt": str(local_staging_receipt),
            "public_probe_receipt": str(public_probe_receipt),
            "publication_preflight_receipt": str(publication_preflight_receipt) if publication_preflight_receipt else None,
            "publication_authorization_receipt": (
                str(publication_authorization_receipt) if publication_authorization_receipt else None
            ),
            "panel_report": str(panel_report),
            "panel_report_status_json": str(panel_report_status_json) if panel_report_status_json else None,
        },
        "mocked": "yes"
        if any(
            "fixtures" in path.parts
            for path in (
                run_root,
                pipeline_loop_run_receipt,
                publication_work_order,
                local_staging_receipt,
                public_probe_receipt,
                publication_preflight_receipt or public_probe_receipt,
                publication_authorization_receipt or public_probe_receipt,
                panel_report,
            )
        )
        else "no",
        "live": "no",
        "exercised": (
            "run-root backward phase order, serial pipeline-loop receipt, provider media public handoff, "
            "Panel 01 comparison report asset/claim boundary"
        ),
        "unverified": (
            "live panel subagent generation/review, public upload authorization, paid Kling submission, "
            "visual semantic quality beyond deterministic report checks"
        ),
        "does_not_authorize": [
            "git_push",
            "public_upload",
            "direct_kling_submit",
            "paid_provider_call",
            "provider_readiness_without_passed_probe",
        ],
    }

    run_root_validation = validate_run_root(run_root, direction="backward")
    loop_validation = validate_pipeline_loop_run(pipeline_loop_run_receipt)
    handoff_validation = validate_provider_media_public_handoff(
        work_order_path=publication_work_order,
        local_staging_receipt_path=local_staging_receipt,
        public_probe_receipt_path=public_probe_receipt,
    )
    preflight_validation = (
        validate_provider_media_publication_preflight(
            work_order_path=publication_work_order,
            local_staging_receipt_path=local_staging_receipt,
        )
        if publication_preflight_receipt is None
        else _read_preflight_receipt(publication_preflight_receipt)
    )
    authorization_validation = (
        _read_authorization_receipt(publication_authorization_receipt)
        if publication_authorization_receipt is not None
        else None
    )
    report_validation = validate_panel_comparison_report(panel_report, status_path=panel_report_status_json)

    result["validations"] = {
        "run_root_backward": _validation_summary(run_root_validation),
        "pipeline_loop_run": _validation_summary(loop_validation),
        "provider_media_publication_preflight": _validation_summary(preflight_validation),
        "provider_media_public_handoff": _validation_summary(handoff_validation),
        "panel_comparison_report": _validation_summary(report_validation),
    }
    if authorization_validation is not None:
        result["validations"]["provider_media_publication_authorization"] = _validation_summary(
            authorization_validation
        )
    result["publication_preflight"] = {
        "status": preflight_validation.get("status"),
        "preflight_ready": preflight_validation.get("preflight_ready"),
        "first_blocker": preflight_validation.get("first_blocker"),
    }
    if authorization_validation is not None:
        result["publication_authorization"] = {
            "status": authorization_validation.get("status"),
            "first_blocker": authorization_validation.get("first_blocker"),
            "locked_sha256": authorization_validation.get("locked_sha256"),
            "proposed_url": authorization_validation.get("proposed_url"),
        }
    result["phase_backlog"] = [
        phase
        for phase in run_root_validation.get("phases", [])
        if isinstance(phase, dict) and phase.get("status") != "PASS"
    ]
    result["policy"] = _policy_from_loop(loop_validation)
    result["live"] = "yes" if handoff_validation.get("live") == "yes" else "no"

    if loop_validation.get("status") == "BLOCKED":
        blocker = loop_validation.get("first_blocker") or {}
        return _block(result, f"pipeline_loop_run_not_valid:{blocker.get('reason')}", phase="pipeline_loop_run_receipt")
    if report_validation.get("status") != "PASS_PANEL_COMPARISON_REPORT":
        blocker = report_validation.get("first_blocker") or {}
        return _block(result, f"panel_report_not_valid:{blocker.get('reason')}", phase="panel_comparison_report")
    if preflight_validation.get("status") != "BLOCKED_AWAITING_PUBLICATION_AUTHORIZATION":
        blocker = preflight_validation.get("first_blocker") or {}
        return _block(
            result,
            f"publication_preflight_not_ready:{preflight_validation.get('status')}:{blocker.get('reason')}",
            phase="provider_media_publication_preflight",
        )
    if preflight_validation.get("preflight_ready") is not True:
        return _block(result, "publication_preflight_ready_not_true", phase="provider_media_publication_preflight")
    if authorization_validation is not None and authorization_validation.get("status") not in {
        "BLOCKED_AWAITING_PUBLICATION_AUTHORIZATION",
        "PASS_PROVIDER_MEDIA_PUBLICATION_AUTHORIZATION",
    }:
        blocker = authorization_validation.get("first_blocker") or {}
        return _block(
            result,
            f"publication_authorization_invalid:{authorization_validation.get('status')}:{blocker.get('reason')}",
            phase="provider_media_publication_authorization",
        )

    run_root_blocker = run_root_validation.get("first_blocker")
    handoff_blocker = handoff_validation.get("first_blocker")
    if isinstance(run_root_blocker, dict):
        result["next_action"] = _next_action_for_phase(str(run_root_blocker.get("phase")))
        return _block(
            result,
            str(run_root_blocker.get("reason")),
            phase=str(run_root_blocker.get("phase")),
        )
    if isinstance(handoff_blocker, dict):
        result["next_action"] = _next_action_for_phase(str(handoff_blocker.get("phase")))
        return _block(
            result,
            str(handoff_blocker.get("reason")),
            phase=str(handoff_blocker.get("phase")),
        )

    if handoff_validation.get("status") != "PASS_PROVIDER_MEDIA_PUBLIC_HANDOFF_READY":
        return _block(result, f"public_handoff_not_ready:{handoff_validation.get('status')}", phase="provider_media_public_handoff")

    result["next_action"] = (
        "Apply the passing provider media probe to the panel repair gate, then rerun "
        "validate-run-root --direction backward before considering any Kling approval gate."
    )
    return result


def _read_preflight_receipt(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        return {
            "schema": "persona_dream.provider_media_publication_preflight_validation.v1",
            "status": "BLOCKED",
            "first_blocker": {"phase": "provider_media_publication_preflight", "reason": f"missing_file:{path}"},
            "mocked": "no",
            "live": "no",
        }
    except json.JSONDecodeError as exc:
        return {
            "schema": "persona_dream.provider_media_publication_preflight_validation.v1",
            "status": "BLOCKED",
            "first_blocker": {"phase": "provider_media_publication_preflight", "reason": f"invalid_json:{exc}"},
            "mocked": "no",
            "live": "no",
        }
    if not isinstance(loaded, dict):
        return {
            "schema": "persona_dream.provider_media_publication_preflight_validation.v1",
            "status": "BLOCKED",
            "first_blocker": {"phase": "provider_media_publication_preflight", "reason": "json_not_object"},
            "mocked": "no",
            "live": "no",
        }
    loaded.setdefault("mocked", "yes" if "fixtures" in path.parts else "no")
    loaded.setdefault("live", "no")
    return loaded


def _read_authorization_receipt(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {
            "schema": "persona_dream.provider_media_publication_authorization_validation.v1",
            "status": "BLOCKED_AWAITING_PUBLICATION_AUTHORIZATION",
            "first_blocker": {"phase": "provider_media_publication_authorization", "reason": f"missing_file:{path}"},
            "mocked": "no",
            "live": "no",
        }
    except json.JSONDecodeError as exc:
        return {
            "schema": "persona_dream.provider_media_publication_authorization_validation.v1",
            "status": "BLOCKED_AWAITING_PUBLICATION_AUTHORIZATION",
            "first_blocker": {"phase": "provider_media_publication_authorization", "reason": f"invalid_json:{exc}"},
            "mocked": "no",
            "live": "no",
        }
    if not isinstance(loaded, dict):
        return {
            "schema": "persona_dream.provider_media_publication_authorization_validation.v1",
            "status": "BLOCKED_AWAITING_PUBLICATION_AUTHORIZATION",
            "first_blocker": {"phase": "provider_media_publication_authorization", "reason": "json_not_object"},
            "mocked": "no",
            "live": "no",
        }
    loaded.setdefault("mocked", "yes" if "fixtures" in path.parts else "no")
    loaded.setdefault("live", "no")
    return loaded


def _next_action_for_phase(phase: str) -> str:
    if phase == "provider_media_publication_authorization":
        return (
            "Provide an explicit provider-media publication authorization receipt for the exact staged PNG, "
            "locked SHA-256, target repo path, and proposed public URL; then rerun validate-pipeline-evidence-bundle."
        )
    if phase == "provider_media_public_probe":
        return (
            "Publish the exact staged panel PNG to the locked public URL, rerun "
            "validate-provider-media-url, then rerun validate-pipeline-evidence-bundle."
        )
    if phase == "provider_media_local_staging":
        return "Run stage-provider-media-local-asset, then rerun validate-pipeline-evidence-bundle."
    if phase == "panel_repair_gate":
        return "Return to the panel repair subagent loop and produce a PASS_PANEL_REVIEWED provider-eligible receipt."
    return "Repair the named first blocker, then rerun validate-pipeline-evidence-bundle."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--pipeline-loop-run-receipt", type=Path, required=True)
    parser.add_argument("--publication-work-order", type=Path, required=True)
    parser.add_argument("--local-staging-receipt", type=Path, required=True)
    parser.add_argument("--public-probe-receipt", type=Path, required=True)
    parser.add_argument("--publication-preflight-receipt", type=Path)
    parser.add_argument("--publication-authorization-receipt", type=Path)
    parser.add_argument("--panel-report", type=Path, required=True)
    parser.add_argument("--panel-report-status-json", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = validate_pipeline_evidence_bundle(
            run_root=args.run_root,
            pipeline_loop_run_receipt=args.pipeline_loop_run_receipt,
            publication_work_order=args.publication_work_order,
            local_staging_receipt=args.local_staging_receipt,
            public_probe_receipt=args.public_probe_receipt,
            panel_report=args.panel_report,
            panel_report_status_json=args.panel_report_status_json,
            publication_preflight_receipt=args.publication_preflight_receipt,
            publication_authorization_receipt=args.publication_authorization_receipt,
        )
    except Exception as exc:
        result = {
            "schema": "persona_dream.pipeline_evidence_bundle_validation.v1",
            "status": "BLOCKED",
            "first_blocker": {"phase": "schema_or_parse", "reason": str(exc)},
            "live": "no",
        }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        blocker = result.get("first_blocker")
        if blocker:
            print(f"{result['status']} {blocker['phase']}: {blocker['reason']}")
        else:
            print(result["status"])
    return 0 if result["status"] == "PASS_PIPELINE_EVIDENCE_BUNDLE" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
