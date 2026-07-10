"""Normalize PR3c provider-authored synthesis receipts for UX consumption."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema


NORMALIZED_SYNTHESIS_SCHEMA = "battle.normalized_synthesis_fixture.v1"
FIXTURE_KIND_PR3C = "pr3c_provider_code_author"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "battle.normalized_synthesis_fixture.v1.schema.json"
PR3C_NODES = ["lineage-summarizer", "research-scout", "method-combiner", "exploit-code-author"]
EXCLUDED_NODES = ["compile-repair", "artifact-reviewer", "battle-handoff-writer"]
PATH_LEAK_MARKERS = (
    "tau-dag-run/",
    "command-loop/",
    "command-artifacts/",
    "/home/",
    "/tmp/",
    "/mnt/",
    "pr3c-provider-workspaces",
    "provider-workspace",
    "inputs/tau-scillm-worker-work-order.json",
    "outputs/provider-worker-result.json",
    "C:\\",
    "D:\\",
)
PRIVATE_MARKERS = (
    "arena/private/",
    "hidden-ground-truth.json",
    "hidden-vulnerability-ledger.json",
    "judge/oracle/",
)
SECRET_PATTERNS = (
    re.compile(r"(?i)\b(api[_-]?key|secret|token|password)\s*=\s*['\"][^'\"]{12,}['\"]"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{20,}"),
)
MUST_NOT_CLAIM = [
    "compiled",
    "compile_passed",
    "runnable",
    "runtime_success",
    "target_contact",
    "exploit_success",
    "blue_detection",
    "blue_bypass",
    "blue_kill",
    "blue_block",
    "judge_success",
    "packet_level_behavior",
    "memory_promotion",
]
MAY_CLAIM = [
    "lineage_summary_materialized",
    "research_receipts_materialized",
    "candidate_methods_materialized",
    "exploit_genome_materialized",
    "provider_execution_attested",
    "provider_authored_specimen_materialized",
    "provider_artifact_provenance_validated",
]


def normalize_pr3c_synthesis_fixture(
    *,
    live_tau_canary: Path,
    out_dir: Path,
    public_out_dir: Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Write a PR3c-only normalized synthesis fixture and validation artifacts."""

    canary_root = _resolve_canary_root(live_tau_canary)
    receipt = _read_json(canary_root / "live-tau-child-dag-canary-receipt.json")
    tau_run = canary_root / "tau-dag-run"
    dag_receipt = _read_json(tau_run / "dag-receipt.json")
    node_receipts = _node_receipts(tau_run)
    for node_id in PR3C_NODES:
        if node_id not in node_receipts:
            raise RuntimeError(f"required PR3c node receipt missing: {node_id}")

    exploit_node = node_receipts["exploit-code-author"]
    authorship_path = _required_evidence_path(exploit_node, "provider-authorship-receipt.json")
    boundary_path = _required_evidence_path(exploit_node, "provider-code-author-boundary-receipt.json")
    validation_path = _required_evidence_path(exploit_node, "provider-artifact-validation.json")
    specimen_path = _required_evidence_path(exploit_node, "specimen.json")
    code_path = _required_evidence_path(exploit_node, "exploit_specimen.py")
    research_path = _required_evidence_path(exploit_node, "research_receipts.json")
    methods_path = _required_evidence_path(exploit_node, "candidate_methods.json")
    genome_path = _required_evidence_path(exploit_node, "exploit_genome.json")

    authorship = _read_json(authorship_path)
    boundary = _read_json(boundary_path)
    artifact_validation = _read_json(validation_path)
    specimen = _read_json(specimen_path)
    research = _read_json(research_path)
    methods = _read_json(methods_path)
    genome = _read_json(genome_path)
    code_bytes = code_path.read_bytes()
    code_text = code_bytes.decode("utf-8")
    code_sha = _sha256_bytes(code_bytes)
    _validate_source_boundary(
        authorship=authorship,
        boundary=boundary,
        artifact_validation=artifact_validation,
        specimen=specimen,
        code_sha=code_sha,
        code_text=code_text,
    )

    receipt_sources = _receipt_sources(
        receipt=receipt,
        dag_receipt=dag_receipt,
        node_receipts=node_receipts,
        authorship=authorship,
        boundary=boundary,
        artifact_validation=artifact_validation,
        specimen=specimen,
        paths={
            "live_tau_child_dag_canary": canary_root / "live-tau-child-dag-canary-receipt.json",
            "tau_dag_receipt": tau_run / "dag-receipt.json",
            **{f"{node_id}_node": _node_receipt_path(tau_run, node_id) for node_id in PR3C_NODES},
            "provider_authorship": authorship_path,
            "provider_code_author_boundary": boundary_path,
            "provider_artifact_validation": validation_path,
            "specimen": specimen_path,
        },
    )
    source_index = {
        "schema": "battle.normalized_synthesis_source_receipt_index.v1",
        "status": "PASS",
        "battle_id": receipt.get("battle_id") or authorship.get("battle_id"),
        "fixture_kind": FIXTURE_KIND_PR3C,
        "source_receipt_count": len(receipt_sources),
        "receipts": receipt_sources,
        "raw_paths_redacted": True,
    }
    fixture = _fixture(
        canary_root=canary_root,
        receipt=receipt,
        dag_receipt=dag_receipt,
        node_receipts=node_receipts,
        authorship=authorship,
        artifact_validation=artifact_validation,
        specimen=specimen,
        research=research,
        methods=methods,
        genome=genome,
        code_text=code_text,
        code_sha=code_sha,
        code_bytes=len(code_bytes),
        source_index=source_index,
        generated_at=generated_at,
    )
    report = validate_normalized_synthesis_fixture(fixture)

    out_dir.mkdir(parents=True, exist_ok=True)
    fixture_path = out_dir / "battle.normalized_synthesis_fixture.json"
    validation_path_out = out_dir / "validation.json"
    source_index_path = out_dir / "source-receipt-index.json"
    _write_json(fixture_path, fixture)
    _write_json(validation_path_out, report)
    _write_json(source_index_path, source_index)

    if public_out_dir is not None:
        public_out_dir.mkdir(parents=True, exist_ok=True)
        public_fixture = public_out_dir / "battle.normalized_synthesis_fixture.json"
        shutil.copyfile(fixture_path, public_fixture)
        if _sha256_file(public_fixture) != _sha256_file(fixture_path):
            raise RuntimeError("public synthesis fixture hash mismatch after copy")
    return fixture


def validate_normalized_synthesis_fixture_path(path: Path) -> dict[str, Any]:
    return validate_normalized_synthesis_fixture(_read_json(path))


def validate_normalized_synthesis_fixture(fixture: dict[str, Any]) -> dict[str, Any]:
    schema = _read_json(SCHEMA_PATH)
    jsonschema.validate(fixture, schema)
    errors: list[str] = []
    if fixture.get("schema") != NORMALIZED_SYNTHESIS_SCHEMA:
        errors.append("schema must be battle.normalized_synthesis_fixture.v1")
    if fixture.get("fixture_kind") != FIXTURE_KIND_PR3C:
        errors.append("fixture_kind must be pr3c_provider_code_author")
    for key, expected in {
        "status": "PASS",
        "mocked": False,
        "agentic": True,
        "provider_live": True,
        "fixture_fallback_used": False,
    }.items():
        if fixture.get(key) != expected:
            errors.append(f"{key} must be {expected!r}")
    node_status = fixture.get("node_status") if isinstance(fixture.get("node_status"), dict) else {}
    if set(node_status) != set(PR3C_NODES):
        errors.append("node_status must contain only the four PR3c nodes")
    for node_id in PR3C_NODES:
        if node_status.get(node_id) != "PASS":
            errors.append(f"node_status.{node_id} must be PASS")
    stage = fixture.get("stage_scope") if isinstance(fixture.get("stage_scope"), dict) else {}
    if stage.get("excluded_nodes") != EXCLUDED_NODES:
        errors.append("stage_scope.excluded_nodes must exclude compile-repair, artifact-reviewer, and battle-handoff-writer")
    boundary = fixture.get("execution_boundary") if isinstance(fixture.get("execution_boundary"), dict) else {}
    for key in ["compile_status", "runtime_status", "target_contact", "judge_status", "packet_behavior", "memory_promotion"]:
        if boundary.get(key) != "NOT_RUN":
            errors.append(f"execution_boundary.{key} must be NOT_RUN")
    if boundary.get("judge_verified_exploits") != 0:
        errors.append("execution_boundary.judge_verified_exploits must be 0")
    claims = fixture.get("claim_boundary") if isinstance(fixture.get("claim_boundary"), dict) else {}
    may_claim = set(claims.get("may_claim", []))
    must_not_claim = set(claims.get("must_not_claim", []))
    for item in MAY_CLAIM:
        if item not in may_claim:
            errors.append(f"claim_boundary.may_claim missing {item}")
    for item in MUST_NOT_CLAIM:
        if item not in must_not_claim:
            errors.append(f"claim_boundary.must_not_claim missing {item}")
    forbidden_may_claim = {
        "compiled",
        "runnable",
        "target_contact",
        "exploit_success",
        "blue_detection",
        "blue_block",
        "judge_success",
        "packet_level_behavior",
        "memory_promotion",
    }
    if forbidden_may_claim & may_claim:
        errors.append(f"claim_boundary.may_claim contains forbidden values: {sorted(forbidden_may_claim & may_claim)}")
    specimen = fixture.get("specimen") if isinstance(fixture.get("specimen"), dict) else {}
    authorship = fixture.get("provider_authorship") if isinstance(fixture.get("provider_authorship"), dict) else {}
    if specimen.get("code_sha256") != authorship.get("code_sha256"):
        errors.append("specimen.code_sha256 must match provider_authorship.code_sha256")
    preview = specimen.get("code_preview") if isinstance(specimen.get("code_preview"), dict) else {}
    lines = preview.get("lines") if isinstance(preview.get("lines"), list) else []
    if len(lines) > 80:
        errors.append("code_preview.lines exceeds 80 lines")
    preview_text = "\n".join(str(line) for line in lines)
    if len(preview_text.encode("utf-8")) > 16_384:
        errors.append("code_preview exceeds 16 KiB")
    if preview.get("preview_sha256") != _sha256_text(preview_text):
        errors.append("code_preview.preview_sha256 mismatch")
    serialized = json.dumps(fixture, sort_keys=True)
    for marker in [*PATH_LEAK_MARKERS, *PRIVATE_MARKERS]:
        if marker in serialized:
            errors.append(f"normalized synthesis fixture exposes forbidden marker: {marker}")
    for pattern in SECRET_PATTERNS:
        if pattern.search(serialized):
            errors.append("normalized synthesis fixture exposes secret-like material")
    for forbidden in ("compile_receipt", "repaired_exploit_specimen", "docker", "judge-receipt"):
        if forbidden in serialized:
            errors.append(f"PR3c synthesis fixture must not expose downstream artifact marker: {forbidden}")
    if errors:
        raise ValueError("\n".join(errors))
    return {
        "schema": "battle.normalized_synthesis_fixture_validation.v1",
        "status": "PASS",
        "fixture_kind": fixture["fixture_kind"],
        "battle_id": fixture["battle_id"],
        "node_status_count": len(node_status),
        "receipt_ref_count": len(fixture.get("receipt_refs", [])),
        "raw_paths_redacted": fixture.get("provenance", {}).get("raw_paths_redacted"),
        "provider_live": fixture.get("provider_live"),
        "code_sha256": specimen.get("code_sha256"),
    }


def _fixture(
    *,
    canary_root: Path,
    receipt: dict[str, Any],
    dag_receipt: dict[str, Any],
    node_receipts: dict[str, dict[str, Any]],
    authorship: dict[str, Any],
    artifact_validation: dict[str, Any],
    specimen: dict[str, Any],
    research: dict[str, Any],
    methods: dict[str, Any],
    genome: dict[str, Any],
    code_text: str,
    code_sha: str,
    code_bytes: int,
    source_index: dict[str, Any],
    generated_at: str | None,
) -> dict[str, Any]:
    node_status = {node_id: node_receipts[node_id].get("status") for node_id in PR3C_NODES}
    node_verdict = {node_id: node_receipts[node_id].get("verdict") for node_id in PR3C_NODES}
    run_identity = "|".join(
        value
        for value in [authorship.get("provider_run_id"), authorship.get("provider_session_id")]
        if isinstance(value, str) and value
    )
    return {
        "schema": NORMALIZED_SYNTHESIS_SCHEMA,
        "fixture_kind": FIXTURE_KIND_PR3C,
        "battle_id": str(receipt.get("battle_id") or authorship.get("battle_id") or "battle-004"),
        "run_id": "battle-004-pr3c-synthesis",
        "generated_at": generated_at or _utc_stamp(),
        "proof_mode": "live_tau_child_dag_canary",
        "status": "PASS",
        "mocked": False,
        "live": "tau_provider_artifact_authoring",
        "agentic": True,
        "provider_live": True,
        "fixture_fallback_used": False,
        "stage_scope": {
            "included_through": "exploit-code-author",
            "included_nodes": PR3C_NODES,
            "excluded_nodes": EXCLUDED_NODES,
            "downstream_receipts_ignored": True,
        },
        "source_run": {
            "proof_mode": receipt.get("proof_mode"),
            "overall_status": receipt.get("status"),
            "overall_reason": receipt.get("reason"),
            "tau_receipt_status": receipt.get("tau_receipt_status"),
            "tau_receipt_verdict": dag_receipt.get("verdict"),
        },
        "node_status": node_status,
        "node_verdict": node_verdict,
        "provider_authorship": {
            "status": "PASS",
            "provider_live": True,
            "agentic": True,
            "authored_by": "tau_provider",
            "requested_provider": authorship.get("requested_provider"),
            "requested_model": authorship.get("requested_model"),
            "observed_provider": authorship.get("observed_provider"),
            "observed_model": authorship.get("observed_model"),
            "provider_route_match": bool(authorship.get("validation", {}).get("provider_route_bound")),
            "provider_run_id_present": bool(authorship.get("provider_run_id")),
            "provider_session_id_present": bool(authorship.get("provider_session_id")),
            "provider_run_ref_sha256": _sha256_text(run_identity) if run_identity else None,
            "code_sha256": code_sha,
            "code_bytes": code_bytes,
            "goal_hash_bound": bool(authorship.get("validation", {}).get("goal_hash_bound")),
            "provider_route_bound": bool(authorship.get("validation", {}).get("provider_route_bound")),
            "output_declared_by_worker": bool(authorship.get("validation", {}).get("output_declared_by_worker")),
            "output_hash_bound": bool(authorship.get("validation", {}).get("output_hash_bound")),
            "output_inside_allowed_root": bool(authorship.get("validation", {}).get("output_inside_allowed_root")),
            "private_reference_scan_passed": bool(authorship.get("validation", {}).get("private_reference_scan_passed")),
            "claim_boundary_passed": bool(authorship.get("validation", {}).get("claim_boundary_passed")),
        },
        "specimen": {
            "schema": specimen.get("schema"),
            "specimen_id": specimen.get("specimen_id"),
            "child_lane_id": specimen.get("child_lane_id"),
            "generation": specimen.get("generation"),
            "language": specimen.get("language"),
            "code_artifact_label": "exploit_specimen.py",
            "code_sha256": code_sha,
            "code_bytes": code_bytes,
            "created_by": specimen.get("created_by"),
            "agentic": specimen.get("agentic"),
            "provider_live": specimen.get("provider_live"),
            "selected_method_ids": specimen.get("selected_method_ids", []),
            "inherited_method_ids": specimen.get("inherited_method_ids", []),
            "code_preview": _code_preview(code_text),
        },
        "research": _research_summary(research),
        "genome": _genome_summary(genome, methods),
        "execution_boundary": {
            "compile_status": "NOT_RUN",
            "runtime_status": "NOT_RUN",
            "target_contact": "NOT_RUN",
            "judge_status": "NOT_RUN",
            "judge_verified_exploits": 0,
            "packet_behavior": "NOT_RUN",
            "memory_promotion": "NOT_RUN",
        },
        "claim_boundary": {
            "may_claim": MAY_CLAIM,
            "must_not_claim": MUST_NOT_CLAIM,
        },
        "receipt_refs": source_index["receipts"],
        "provenance": {
            "source_run_label": "live_tau_child_dag_canary",
            "normalizer_schema": "battle.normalized_synthesis_fixture_builder.v1",
            "source_receipt_count": source_index["source_receipt_count"],
            "raw_paths_redacted": True,
            "tau_runtime_paths_exposed": False,
            "command_loop_paths_exposed": False,
            "provider_workspace_paths_exposed": False,
            "credentials_exposed": False,
        },
        "copy": {
            "headline": "Provider-authored specimen materialized",
            "subhead": "Tau routed a real provider/model and Battle validated the generated specimen's provenance.",
            "status_label": "Code authoring passed",
            "boundary_notice": "This PR3c fixture does not include compilation, execution, target contact, Judge replay, Blue outcomes, packet behavior, or memory promotion.",
        },
    }


def _validate_source_boundary(
    *,
    authorship: dict[str, Any],
    boundary: dict[str, Any],
    artifact_validation: dict[str, Any],
    specimen: dict[str, Any],
    code_sha: str,
    code_text: str,
) -> None:
    errors: list[str] = []
    for label, payload in {
        "provider_authorship": authorship,
        "provider_code_author_boundary": boundary,
        "provider_artifact_validation": artifact_validation,
        "specimen": specimen,
    }.items():
        if payload.get("status") != "PASS" and label != "specimen":
            errors.append(f"{label} status must be PASS")
    if authorship.get("provider_live") is not True or authorship.get("agentic") is not True:
        errors.append("provider authorship must be live and agentic")
    if authorship.get("authored_by") != "tau_provider":
        errors.append("provider authorship authored_by must be tau_provider")
    if not authorship.get("observed_provider") or not authorship.get("observed_model"):
        errors.append("observed provider/model are required")
    if not (authorship.get("provider_run_id") or authorship.get("provider_session_id")):
        errors.append("provider run or session id is required in source receipt")
    hashes = {
        authorship.get("code_artifact_sha256"),
        artifact_validation.get("code_artifact_sha256"),
        specimen.get("code_sha256"),
        code_sha,
    }
    if len(hashes) != 1:
        errors.append("code hash mismatch across source receipts")
    for key in ["compile_status", "runtime_status", "judge_status"]:
        if authorship.get(key) != "NOT_RUN" or boundary.get(key) != "NOT_RUN":
            errors.append(f"{key} must remain NOT_RUN in PR3c source receipts")
    if authorship.get("judge_verified_exploits") != 0 or boundary.get("judge_verified_exploits") != 0:
        errors.append("judge_verified_exploits must be 0")
    for marker in PRIVATE_MARKERS:
        if marker in code_text:
            errors.append(f"code contains private marker {marker}")
    for pattern in SECRET_PATTERNS:
        if pattern.search(code_text):
            errors.append("code contains secret-like material")
    if errors:
        raise ValueError("\n".join(errors))


def _research_summary(research: dict[str, Any]) -> dict[str, Any]:
    sources = []
    for idx, source in enumerate(research.get("sources", []), start=1):
        if not isinstance(source, dict):
            continue
        url = source.get("url")
        public_url = url if isinstance(url, str) and url.startswith(("http://", "https://")) else None
        sources.append(
            {
                "source_id": source.get("source_id") or f"source-{idx:03d}",
                "source_type": source.get("source_type"),
                "title": source.get("title"),
                "public_url": public_url,
                "relevance": source.get("relevance"),
                "usable_facts": source.get("claims_supported", []),
                "used_for": source.get("used_for", []),
                "limitations": [*source.get("limitations", []), "Research is design input, not exploit proof."],
            }
        )
    query = research.get("query") if isinstance(research.get("query"), dict) else {}
    source_receipts = research.get("source_receipts") if isinstance(research.get("source_receipts"), list) else []
    return {
        "status": research.get("status"),
        "source_count": len(sources),
        "method": query.get("method"),
        "external_tool_called": query.get("external_tool_called"),
        "provider_live": research.get("provider_live"),
        "review_required": any(bool(item.get("review_required")) for item in source_receipts if isinstance(item, dict)),
        "sources": sources,
    }


def _genome_summary(genome: dict[str, Any], methods: dict[str, Any]) -> dict[str, Any]:
    selected = genome.get("selected_method_ids", []) if isinstance(genome.get("selected_method_ids"), list) else []
    rejected = genome.get("rejected_method_ids", []) if isinstance(genome.get("rejected_method_ids"), list) else []
    method_items = methods.get("methods") if isinstance(methods.get("methods"), list) else []
    inherited = [
        item.get("method_id")
        for item in method_items
        if isinstance(item, dict) and item.get("inherited") is True and item.get("method_id") in selected
    ]
    return {
        "status": genome.get("status"),
        "created_by": genome.get("created_by"),
        "agentic": genome.get("agentic"),
        "provider_live": genome.get("provider_live"),
        "selected_method_ids": selected,
        "inherited_method_ids": inherited,
        "deferred_method_ids": rejected,
        "strategy": genome.get("strategy", {}),
        "rationale_summary": _rationale_summary(genome.get("strategy", {})),
    }


def _rationale_summary(strategy: Any) -> str:
    if not isinstance(strategy, dict):
        return ""
    parts = [value for key in ["primary", "repair_bias", "negative_filter"] if isinstance((value := strategy.get(key)), str) and value]
    return " ".join(parts)


def _code_preview(code_text: str) -> dict[str, Any]:
    lines = code_text.splitlines()
    preview_lines, redaction_reasons = _redacted_preview_lines(lines[:80])
    preview_text = "\n".join(preview_lines)
    while len(preview_text.encode("utf-8")) > 16_384 and preview_lines:
        preview_lines = preview_lines[:-1]
        preview_text = "\n".join(preview_lines)
    return {
        "available": True,
        "redacted": bool(redaction_reasons),
        "truncated": len(preview_lines) < len(lines),
        "max_lines": 80,
        "max_bytes": 16_384,
        "line_count_total": len(lines),
        "preview_sha256": _sha256_text(preview_text),
        "lines": preview_lines,
        "redaction_reasons": sorted(redaction_reasons),
    }


def _redacted_preview_lines(lines: list[str]) -> tuple[list[str], set[str]]:
    reasons: set[str] = set()
    redacted: list[str] = []
    for line in lines:
        value = line
        for marker in PATH_LEAK_MARKERS:
            if marker in value:
                value = value.replace(marker, "[redacted-path-marker]")
                reasons.add("path_marker")
        for marker in PRIVATE_MARKERS:
            if marker in value:
                value = value.replace(marker, "[redacted-private-marker]")
                reasons.add("private_marker")
        for pattern in SECRET_PATTERNS:
            if pattern.search(value):
                value = pattern.sub("[redacted-secret]", value)
                reasons.add("secret_pattern")
        redacted.append(value)
    return redacted, reasons


def _receipt_sources(
    *,
    receipt: dict[str, Any],
    dag_receipt: dict[str, Any],
    node_receipts: dict[str, dict[str, Any]],
    authorship: dict[str, Any],
    boundary: dict[str, Any],
    artifact_validation: dict[str, Any],
    specimen: dict[str, Any],
    paths: dict[str, Path],
) -> list[dict[str, Any]]:
    values: list[tuple[str, dict[str, Any]]] = [
        ("live_tau_child_dag_canary", receipt),
        ("tau_dag_receipt", dag_receipt),
        *[(f"{node_id}_node", node_receipts[node_id]) for node_id in PR3C_NODES],
        ("provider_authorship", authorship),
        ("provider_code_author_boundary", boundary),
        ("provider_artifact_validation", artifact_validation),
        ("specimen", specimen),
    ]
    result = []
    for source_id, payload in values:
        path = paths[source_id]
        result.append(
            {
                "id": source_id,
                "schema": payload.get("schema"),
                "status": payload.get("status"),
                "verdict": payload.get("verdict") or payload.get("reason"),
                "label": path.name,
                "sha256": _sha256_file(path),
            }
        )
    return result


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


def _node_receipt_path(tau_run: Path, node_id: str) -> Path:
    for path in sorted(tau_run.rglob("*node-receipt.json")):
        try:
            payload = _read_json(path)
        except (OSError, json.JSONDecodeError, RuntimeError):
            continue
        if payload.get("node_id") == node_id:
            return path
    raise RuntimeError(f"node receipt path missing: {node_id}")


def _required_evidence_path(receipt: dict[str, Any], kind: str) -> Path:
    for item in receipt.get("evidence", []):
        if not isinstance(item, dict) or item.get("kind") != kind:
            continue
        value = item.get("path")
        if isinstance(value, str) and value:
            path = Path(value)
            if path.exists():
                return path
    raise RuntimeError(f"required evidence missing from {receipt.get('node_id')}: {kind}")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _utc_stamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
