#!/usr/bin/env python3
"""Write source-derived status data for the Panel 01 comparison report."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from pipeline_loop_status import build_pipeline_loop_status
from validate_pipeline_loop_run import validate_pipeline_loop_run
from validate_provider_media_public_handoff import validate_provider_media_public_handoff
from validate_run_root_pipeline import validate_run_root


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _read_json_if_exists(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"expected JSON object: {path}")
    return loaded


def _receipt_status(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"path": None, "status": "MISSING", "exists": False}
    doc = _read_json_if_exists(path)
    if doc is None:
        return {"path": str(path), "status": "MISSING", "exists": False}
    return {
        "path": str(path),
        "status": doc.get("status"),
        "first_blocker": doc.get("first_blocker"),
        "exists": True,
        "url": doc.get("url"),
        "blockers": doc.get("blockers", []),
        "provider_eligibility": doc.get("provider_eligibility"),
        "provider_media_status": doc.get("provider_media_status"),
        "provider_packet_status": doc.get("provider_packet_status"),
        "sha256": doc.get("staged_sha256") or doc.get("expected_sha256") or doc.get("locked_sha256"),
        "authorized_sha256": doc.get("authorized_sha256"),
        "authorized_url": doc.get("authorized_url"),
        "preflight_ready": doc.get("preflight_ready"),
        "live": doc.get("live"),
        "mocked": doc.get("mocked"),
    }


def _loop_run_status(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "path": None,
            "exists": False,
            "validation_status": "MISSING",
            "status": "MISSING",
        }
    doc = _read_json_if_exists(path)
    if doc is None:
        return {
            "path": str(path),
            "exists": False,
            "validation_status": "MISSING",
            "status": "MISSING",
        }
    validation = validate_pipeline_loop_run(path)
    active_loop = doc.get("active_loop") if isinstance(doc.get("active_loop"), dict) else {}
    iterations = doc.get("iterations") if isinstance(doc.get("iterations"), list) else []
    return {
        "path": str(path),
        "exists": True,
        "validation_status": validation.get("status"),
        "status": doc.get("status"),
        "stop_reason": doc.get("stop_reason"),
        "iteration_count": len(iterations),
        "active_loop": {
            "loop": active_loop.get("loop"),
            "phase": active_loop.get("phase"),
            "external_action_required": active_loop.get("external_action_required"),
        },
        "policy": doc.get("policy"),
        "mocked": doc.get("mocked"),
        "live": doc.get("live"),
        "exercised": validation.get("exercised"),
        "unverified": validation.get("unverified"),
    }


def _pipeline_evidence_bundle_status(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "path": None,
            "exists": False,
            "status": "MISSING",
            "first_blocker": {
                "phase": "pipeline_evidence_bundle",
                "reason": "missing_pipeline_evidence_bundle_receipt",
            },
        }
    doc = _read_json_if_exists(path)
    if doc is None:
        return {
            "path": str(path),
            "exists": False,
            "status": "MISSING",
            "first_blocker": {
                "phase": "pipeline_evidence_bundle",
                "reason": "missing_pipeline_evidence_bundle_receipt",
            },
        }
    validations = doc.get("validations") if isinstance(doc.get("validations"), dict) else {}
    return {
        "path": str(path),
        "exists": True,
        "status": doc.get("status"),
        "first_blocker": doc.get("first_blocker"),
        "live": doc.get("live"),
        "mocked": doc.get("mocked"),
        "next_action": doc.get("next_action"),
        "phase_backlog_count": len(doc.get("phase_backlog", [])) if isinstance(doc.get("phase_backlog"), list) else None,
        "validation_statuses": {
            key: value.get("status") if isinstance(value, dict) else None
            for key, value in validations.items()
        },
    }


def _public_handoff_status(
    *,
    publication_work_order: Path | None,
    local_staging_receipt: Path | None,
    public_probe_receipt: Path | None,
) -> dict[str, Any]:
    if publication_work_order is None or local_staging_receipt is None or public_probe_receipt is None:
        return {
            "status": "MISSING",
            "first_blocker": {
                "phase": "provider_media_public_handoff",
                "reason": "missing_required_handoff_input",
            },
            "exists": False,
        }
    if not publication_work_order.exists() or not local_staging_receipt.exists() or not public_probe_receipt.exists():
        return {
            "status": "MISSING",
            "first_blocker": {
                "phase": "provider_media_public_handoff",
                "reason": "missing_required_handoff_file",
            },
            "exists": False,
            "work_order": str(publication_work_order),
            "local_staging_receipt": str(local_staging_receipt),
            "public_probe_receipt": str(public_probe_receipt),
        }
    result = validate_provider_media_public_handoff(
        work_order_path=publication_work_order,
        local_staging_receipt_path=local_staging_receipt,
        public_probe_receipt_path=public_probe_receipt,
    )
    result["exists"] = True
    return result


def _next_action(
    *,
    local_staging: dict[str, Any],
    publication_authorization: dict[str, Any],
    public_probe: dict[str, Any],
    panel_gate: dict[str, Any],
) -> str:
    if local_staging["status"] != "PASS_PROVIDER_MEDIA_LOCAL_STAGING":
        return "Stage the locked Panel 01 media bytes locally, then validate provider-media local staging."
    if publication_authorization["status"] != "PASS_PROVIDER_MEDIA_PUBLICATION_AUTHORIZATION":
        return "Provide an explicit publication authorization receipt for the exact staged Panel 01 PNG, locked SHA-256, target repo path, and proposed public URL."
    if public_probe["status"] != "PASS_PROVIDER_MEDIA_URL_PROBE":
        return "Publish the staged Panel 01 PNG to a stable public URL, rerun validate-provider-media-url, then apply the passing probe."
    if panel_gate.get("provider_eligibility") is not True:
        return "Apply the passing provider media probe to the panel repair gate, then rerun validate-panel-repair-gate --require-provider-eligible."
    return "Rerun panel source and backward run-root validation before considering any provider packet handoff."


def build_panel_comparison_status(
    *,
    run_root: Path,
    panel_id: str,
    panel_repair_gate_receipt: Path | None,
    local_staging_receipt: Path | None,
    public_probe_receipt: Path | None,
    publication_work_order: Path | None,
    pipeline_loop_run_receipt: Path | None = None,
    pipeline_evidence_bundle_receipt: Path | None = None,
    provider_media_publication_preflight_receipt: Path | None = None,
    provider_media_publication_authorization_receipt: Path | None = None,
    provider_media_publication_authorization_template: Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    timestamp = generated_at or _now_iso()
    backward = validate_run_root(run_root, direction="backward")
    loop_status = build_pipeline_loop_status(run_root=run_root, direction="backward", generated_at=timestamp)
    phases = backward.get("phases", [])
    phase_summary = [
        {"phase": phase.get("phase"), "status": phase.get("status"), "blocker": phase.get("blocker")}
        for phase in phases
        if isinstance(phase, dict)
    ]
    panel_gate = _receipt_status(panel_repair_gate_receipt)
    local_staging = _receipt_status(local_staging_receipt)
    public_probe = _receipt_status(public_probe_receipt)
    publication = _receipt_status(publication_work_order)
    publication_preflight = _receipt_status(provider_media_publication_preflight_receipt)
    publication_authorization = _receipt_status(provider_media_publication_authorization_receipt)
    publication_authorization_template = _receipt_status(provider_media_publication_authorization_template)
    loop_run = _loop_run_status(pipeline_loop_run_receipt)
    evidence_bundle = _pipeline_evidence_bundle_status(pipeline_evidence_bundle_receipt)
    public_handoff = _public_handoff_status(
        publication_work_order=publication_work_order,
        local_staging_receipt=local_staging_receipt,
        public_probe_receipt=public_probe_receipt,
    )
    first_blocker = backward.get("first_blocker")

    return {
        "schema": "persona_dream.panel_comparison_status.v1",
        "generated_at": timestamp,
        "updated_at": timestamp,
        "run_root": str(run_root),
        "panel_id": panel_id,
        "status": "BLOCKED" if first_blocker else "READY_FOR_NEXT_VALIDATION",
        "first_blocker": first_blocker,
        "acceptance_state": "Not asserted by this report.",
        "backward_validator": {
            "status": backward.get("status"),
            "first_blocker": first_blocker,
            "phase_summary": phase_summary,
            "mocked": backward.get("mocked"),
            "live": backward.get("live"),
        },
        "active_loop": loop_status.get("active_loop"),
        "loop_backlog": loop_status.get("loop_backlog", []),
        "loop_model": loop_status.get("loop_model"),
        "loop_stop_condition": loop_status.get("stop_condition"),
        "loop_run": loop_run,
        "receipts": {
            "panel_repair_gate": panel_gate,
            "provider_media_local_staging": local_staging,
            "provider_media_public_probe": public_probe,
            "provider_media_publication_work_order": publication,
            "provider_media_publication_preflight": publication_preflight,
            "provider_media_publication_authorization": publication_authorization,
            "provider_media_publication_authorization_template": publication_authorization_template,
            "provider_media_public_handoff": public_handoff,
            "pipeline_evidence_bundle": evidence_bundle,
        },
        "policy": {
            "kling_call_allowed": False,
            "nano_banana_final_panel_allowed": False,
            "requires_public_provider_media_url": True,
        },
        "next_action": _next_action(
            local_staging=local_staging,
            publication_authorization=publication_authorization,
            public_probe=public_probe,
            panel_gate=panel_gate,
        ),
        "mocked": "no",
        "live": "no",
        "exercised": "local receipts, run-root backward validator, publication/staging/probe status extraction",
        "unverified": "public URL reachability if current probe is blocked, Kling provider fetch behavior, paid-call authorization, Kling submission",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--panel-id", default="panel_01")
    parser.add_argument("--panel-repair-gate-receipt", type=Path)
    parser.add_argument("--local-staging-receipt", type=Path)
    parser.add_argument("--public-probe-receipt", type=Path)
    parser.add_argument("--publication-work-order", type=Path)
    parser.add_argument("--pipeline-loop-run-receipt", type=Path)
    parser.add_argument("--pipeline-evidence-bundle-receipt", type=Path)
    parser.add_argument("--provider-media-publication-preflight-receipt", type=Path)
    parser.add_argument("--provider-media-publication-authorization-receipt", type=Path)
    parser.add_argument("--provider-media-publication-authorization-template", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--generated-at")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        status = build_panel_comparison_status(
            run_root=args.run_root,
            panel_id=args.panel_id,
            panel_repair_gate_receipt=args.panel_repair_gate_receipt,
            local_staging_receipt=args.local_staging_receipt,
            public_probe_receipt=args.public_probe_receipt,
            publication_work_order=args.publication_work_order,
            pipeline_loop_run_receipt=args.pipeline_loop_run_receipt,
            pipeline_evidence_bundle_receipt=args.pipeline_evidence_bundle_receipt,
            provider_media_publication_preflight_receipt=args.provider_media_publication_preflight_receipt,
            provider_media_publication_authorization_receipt=args.provider_media_publication_authorization_receipt,
            provider_media_publication_authorization_template=args.provider_media_publication_authorization_template,
            generated_at=args.generated_at,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        result = {"status": "WROTE", "output": str(args.output), "panel_comparison_status": status}
    except Exception as exc:
        result = {
            "schema": "persona_dream.panel_comparison_status.v1",
            "status": "BLOCKED",
            "first_blocker": {"phase": "panel_comparison_status", "reason": str(exc)},
        }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{result['status']} {result.get('output', '')}".strip())
    return 0 if result["status"] != "BLOCKED" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
