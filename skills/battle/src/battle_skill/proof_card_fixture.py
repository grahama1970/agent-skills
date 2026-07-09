"""Normalize Battle proof-card fixtures from backend proof receipts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema


NORMALIZED_PROOF_CARD_SCHEMA = "battle.normalized_proof_card_fixture.v1"
PROOF_CARD_KIND_PR3B = "pr3b_tau_research_combiner"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "battle.normalized_proof_card_fixture.v1.schema.json"
REQUIRED_PR3B_ARTIFACTS = {
    "child_research_receipts": "battle.child_research_receipts.v1",
    "child_candidate_methods": "battle.child_candidate_methods.v1",
    "child_exploit_genome": "battle.child_exploit_genome.v1",
}
EXPECTED_NODE_ORDER = [
    "lineage-summarizer",
    "research-scout",
    "method-combiner",
    "exploit-code-author",
]


def normalize_pr3b_proof_card_fixture(*, live_tau_canary: Path, out: Path) -> dict[str, Any]:
    """Write a normalized proof-card fixture from a PR3b live Tau canary run."""

    canary_root = _resolve_canary_root(live_tau_canary)
    receipt = _read_json(canary_root / "live-tau-child-dag-canary-receipt.json")
    tau_run = canary_root / "tau-dag-run"
    dag_receipt = _read_json(tau_run / "dag-receipt.json")
    node_receipts = _node_receipts(tau_run)
    artifacts = _public_artifacts(
        research=_read_json(_required_artifact(tau_run, "research_receipts.json")),
        methods=_read_json(_required_artifact(tau_run, "candidate_methods.json")),
        genome=_read_json(_required_artifact(tau_run, "exploit_genome.json")),
    )
    fixture = _fixture(
        canary_root=canary_root,
        receipt=receipt,
        dag_receipt=dag_receipt,
        node_receipts=node_receipts,
        artifacts=artifacts,
    )
    validate_normalized_proof_card_fixture(fixture)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fixture, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return fixture


def validate_normalized_proof_card_fixture_path(path: Path) -> dict[str, Any]:
    return validate_normalized_proof_card_fixture(_read_json(path))


def validate_normalized_proof_card_fixture(fixture: dict[str, Any]) -> dict[str, Any]:
    schema = _read_json(SCHEMA_PATH)
    jsonschema.validate(fixture, schema)
    errors: list[str] = []
    if fixture.get("schema") != NORMALIZED_PROOF_CARD_SCHEMA:
        errors.append("schema must be battle.normalized_proof_card_fixture.v1")
    if fixture.get("proof_card_kind") != PROOF_CARD_KIND_PR3B:
        errors.append("proof_card_kind must be pr3b_tau_research_combiner")
    claim_boundary = fixture.get("claim_boundary") if isinstance(fixture.get("claim_boundary"), dict) else {}
    must_not_claim = set(claim_boundary.get("must_not_claim", []))
    for forbidden in ["child_exploit_generated", "child_exploit_compiled", "child_exploit_runnable", "exploit_success"]:
        if forbidden not in must_not_claim:
            errors.append(f"claim_boundary.must_not_claim missing {forbidden}")
    node_status = fixture.get("node_status") if isinstance(fixture.get("node_status"), dict) else {}
    expected = {
        "lineage-summarizer": "PASS",
        "research-scout": "PASS",
        "method-combiner": "PASS",
        "exploit-code-author": "BLOCKED",
    }
    for node_id, status in expected.items():
        if node_status.get(node_id) != status:
            errors.append(f"node_status.{node_id} must be {status}")
    artifacts = fixture.get("artifacts") if isinstance(fixture.get("artifacts"), dict) else {}
    for key, schema_id in REQUIRED_PR3B_ARTIFACTS.items():
        artifact = artifacts.get(key) if isinstance(artifacts.get(key), dict) else {}
        if artifact.get("schema") != schema_id:
            errors.append(f"artifacts.{key}.schema must be {schema_id}")
    serialized = json.dumps(fixture, sort_keys=True)
    for forbidden in ("exploit_success", "child_exploit_generated"):
        if forbidden in " ".join(fixture.get("claim_boundary", {}).get("may_claim", [])):
            errors.append(f"claim_boundary.may_claim must not contain {forbidden}")
    if "command-loop/command-artifacts" in serialized:
        errors.append("normalized proof-card fixture must not expose Tau command-loop artifact paths")
    if errors:
        raise ValueError("\n".join(errors))
    return {
        "schema": "battle.normalized_proof_card_fixture_validation.v1",
        "status": "PASS",
        "proof_card_kind": fixture["proof_card_kind"],
        "battle_id": fixture["battle_id"],
        "node_status_count": len(node_status),
        "embedded_artifact_count": len(artifacts),
        "claim_boundary": fixture["claim_boundary"],
    }


def _fixture(
    *,
    canary_root: Path,
    receipt: dict[str, Any],
    dag_receipt: dict[str, Any],
    node_receipts: dict[str, dict[str, Any]],
    artifacts: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    node_status = {node_id: node_receipts.get(node_id, {}).get("status", "MISSING") for node_id in EXPECTED_NODE_ORDER}
    node_verdict = {node_id: node_receipts.get(node_id, {}).get("verdict", "MISSING") for node_id in EXPECTED_NODE_ORDER}
    return {
        "schema": NORMALIZED_PROOF_CARD_SCHEMA,
        "proof_card_kind": PROOF_CARD_KIND_PR3B,
        "battle_id": str(receipt.get("battle_id") or "battle-004"),
        "run_id": canary_root.name,
        "generated_at": _utc_stamp(),
        "proof_mode": receipt.get("proof_mode"),
        "status": receipt.get("status"),
        "reason": receipt.get("reason"),
        "mocked": False,
        "live": receipt.get("live"),
        "agentic": receipt.get("agentic"),
        "fixture_fallback_used": receipt.get("fixture_fallback_used"),
        "tau_execution": receipt.get("tau_execution"),
        "tau_receipt_status": receipt.get("tau_receipt_status"),
        "tau_receipt_verdict": receipt.get("tau_receipt_verdict"),
        "claim_boundary": {
            "may_claim": [
                "research_receipts_materialized",
                "candidate_methods_materialized",
                "exploit_genome_materialized",
            ],
            "must_not_claim": [
                "child_exploit_generated",
                "child_exploit_compiled",
                "child_exploit_runnable",
                "exploit_success",
                "blue_detection",
                "blue_bypass",
                "packet_level_behavior",
            ],
        },
        "node_status": node_status,
        "node_verdict": node_verdict,
        "artifacts": artifacts,
        "receipt_refs": [
            {
                "id": "live_tau_child_dag_canary",
                "schema": receipt.get("schema"),
                "status": receipt.get("status"),
                "verdict": receipt.get("reason"),
            },
            {
                "id": "tau_dag_receipt",
                "schema": dag_receipt.get("schema"),
                "status": dag_receipt.get("status"),
                "verdict": dag_receipt.get("verdict"),
            },
            *[
                {
                    "id": node_id,
                    "schema": node_receipts[node_id].get("schema"),
                    "status": node_receipts[node_id].get("status"),
                    "verdict": node_receipts[node_id].get("verdict"),
                }
                for node_id in EXPECTED_NODE_ORDER
                if node_id in node_receipts
            ],
        ],
        "scoreboard": receipt.get("scoreboard", {}),
        "copy": {
            "headline": "Research and method genome produced",
            "subhead": "Exploit code authoring is blocked until a real Tau/provider code-authoring adapter exists.",
            "status_label": "Blocked at exploit-code-author",
        },
    }


def _public_artifacts(*, research: dict[str, Any], methods: dict[str, Any], genome: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return UX-safe artifact summaries without Tau runtime paths."""

    return {
        "child_research_receipts": {
            "schema": research.get("schema"),
            "battle_id": research.get("battle_id"),
            "child_lane_id": research.get("child_lane_id"),
            "status": research.get("status"),
            "mocked": research.get("mocked"),
            "live": research.get("live"),
            "provider_live": research.get("provider_live"),
            "fixture_fallback_used": research.get("fixture_fallback_used"),
            "query": research.get("query"),
            "source_receipts": [
                {
                    "schema": item.get("schema"),
                    "status": item.get("status"),
                    "source_type": item.get("source_type"),
                    "method": item.get("method"),
                    "source_count": item.get("source_count"),
                    "review_required": item.get("review_required"),
                }
                for item in research.get("source_receipts", [])
                if isinstance(item, dict)
            ],
            "sources": research.get("sources", []),
            "claims": research.get("claims", {}),
        },
        "child_candidate_methods": {
            "schema": methods.get("schema"),
            "battle_id": methods.get("battle_id"),
            "child_lane_id": methods.get("child_lane_id"),
            "status": methods.get("status"),
            "mocked": methods.get("mocked"),
            "live": methods.get("live"),
            "provider_live": methods.get("provider_live"),
            "fixture_fallback_used": methods.get("fixture_fallback_used"),
            "methods": methods.get("methods", []),
            "claims": methods.get("claims", {}),
        },
        "child_exploit_genome": {
            "schema": genome.get("schema"),
            "battle_id": genome.get("battle_id"),
            "child_lane_id": genome.get("child_lane_id"),
            "status": genome.get("status"),
            "mocked": genome.get("mocked"),
            "live": genome.get("live"),
            "provider_live": genome.get("provider_live"),
            "fixture_fallback_used": genome.get("fixture_fallback_used"),
            "created_by": genome.get("created_by"),
            "agentic": genome.get("agentic"),
            "selected_method_ids": genome.get("selected_method_ids", []),
            "rejected_method_ids": genome.get("rejected_method_ids", []),
            "strategy": genome.get("strategy", {}),
            "claims": genome.get("claims", {}),
        },
    }


def _resolve_canary_root(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.is_dir():
        return resolved
    if resolved.name == "live-tau-child-dag-canary-receipt.json":
        return resolved.parent
    raise RuntimeError(f"live Tau canary must be a directory or receipt file: {path}")


def _node_receipts(tau_run: Path) -> dict[str, dict[str, Any]]:
    receipts: dict[str, dict[str, Any]] = {}
    for path in sorted(tau_run.rglob("*node-receipt.json")):
        payload = _read_json(path)
        node_id = payload.get("node_id")
        if isinstance(node_id, str):
            receipts[node_id] = payload
    return receipts


def _required_artifact(root: Path, name: str) -> Path:
    matches = sorted(root.rglob(name))
    if not matches:
        raise RuntimeError(f"required PR3b artifact missing: {name}")
    return matches[0]


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return payload


def _utc_stamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
