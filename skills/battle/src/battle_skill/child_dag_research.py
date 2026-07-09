"""Source-bearing research adapter for Battle child Tau DAG nodes."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


BATTLE_CHILD_RESEARCH_SCHEMA = "battle.child_research_receipts.v1"
CANDIDATE_METHODS_SCHEMA = "battle.child_candidate_methods.v1"
DEFAULT_TAU_ROOT = Path("/home/graham/workspace/experiments/tau")


def run_research_scout(
    *,
    artifact_dir: Path,
    lineage_summary_path: Path,
    tau_root: Path = DEFAULT_TAU_ROOT,
) -> dict[str, Any]:
    """Build a source packet, validate it through Tau, and write Battle research artifacts."""

    lineage = _read_json(lineage_summary_path)
    query = _research_query(lineage)
    source_packet = _source_packet(query=query, lineage=lineage)
    source_packet_path = artifact_dir / "research-source-packet.json"
    source_receipt_path = artifact_dir / "research-source-receipt.json"
    _write_json(source_packet_path, source_packet)

    tau_stdout = artifact_dir / "tau-research-source-receipt-stdout.txt"
    tau_stderr = artifact_dir / "tau-research-source-receipt-stderr.txt"
    command = [
        "uv",
        "run",
        "tau",
        "research-source-receipt",
        "--source",
        str(source_packet_path),
        "--receipt",
        str(source_receipt_path),
    ]
    result = subprocess.run(
        command,
        cwd=tau_root,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    tau_stdout.write_text(result.stdout, encoding="utf-8")
    tau_stderr.write_text(result.stderr, encoding="utf-8")
    source_receipt = _read_json(source_receipt_path) if source_receipt_path.exists() else _parse_json(result.stdout)
    if not isinstance(source_receipt, dict):
        source_receipt = {
            "schema": "tau.research_source_receipt.v1",
            "status": "BLOCKED",
            "ok": False,
            "errors": ["Tau research-source-receipt did not emit JSON receipt."],
        }

    candidate_methods = _candidate_methods(lineage=lineage, source_receipt=source_receipt)
    candidate_methods_path = artifact_dir / "candidate_methods.json"
    _write_json(candidate_methods_path, candidate_methods)

    status = "PASS" if result.returncode == 0 and source_receipt.get("status") == "PASS" else "BLOCKED"
    research_receipts = {
        "schema": BATTLE_CHILD_RESEARCH_SCHEMA,
        "battle_id": lineage.get("battle_id"),
        "child_lane_id": lineage.get("child_lane_id"),
        "status": status,
        "mocked": False,
        "live": "tau_command_spec_node",
        "research_scout_live": True,
        "provider_live": False,
        "fixture_fallback_used": False,
        "query": {
            "value": query,
            "method": "manual",
            "safety_receipt": None,
            "external_tool_called": False,
        },
        "tau_command": command,
        "tau_exit_code": result.returncode,
        "source_receipts": [
            {
                "schema": source_receipt.get("schema"),
                "path": str(source_receipt_path),
                "status": source_receipt.get("status"),
                "source_type": source_receipt.get("source_type"),
                "method": source_receipt.get("method"),
                "source_count": source_receipt.get("source_count"),
                "review_required": source_receipt.get("review_required"),
            }
        ],
        "sources": [
            {
                "source_id": f"source-{index + 1:03d}",
                "source_type": source_receipt.get("source_type"),
                "method": source_receipt.get("method"),
                "title": source.get("title"),
                "url": source.get("url"),
                "retrieved_at": source_receipt.get("retrieved_at"),
                "relevance": source.get("relevance"),
                "classification": source_receipt.get("classification"),
                "claims_supported": source.get("claims_supported", []),
                "used_for": _used_for_source(index),
                "limitations": [
                    "Research is not proof of exploitability.",
                    "Research does not prove the method applies to this target.",
                ],
            }
            for index, source in enumerate(source_receipt.get("sources", []) if isinstance(source_receipt.get("sources"), list) else [])
            if isinstance(source, dict)
        ],
        "candidate_method_refs": ["candidate_methods.json"] if status == "PASS" else [],
        "errors": source_receipt.get("errors", []),
        "claims": {
            "proves": [
                "Research Scout executed through the live Tau command-spec DAG path.",
                "Research Scout produced source-bearing design-input receipts.",
                "Research Scout preserved Tau research-source receipt validation.",
            ]
            if status == "PASS"
            else ["Research Scout reached Tau research-source receipt validation."],
            "does_not_prove": [
                "The cited sources are true.",
                "The researched technique applies to BATTLE-004.",
                "Any child exploit code was generated.",
                "Any child exploit code compiles.",
                "Any child exploit code runs.",
                "Any exploit succeeded.",
                "Any Blue detection, bypass, stealth, kill, or block occurred.",
                "Any packet-level behavior was captured.",
            ],
        },
    }
    research_receipts_path = artifact_dir / "research_receipts.json"
    _write_json(research_receipts_path, research_receipts)
    return {
        "status": status,
        "research_receipts": research_receipts,
        "research_receipts_path": research_receipts_path,
        "candidate_methods": candidate_methods,
        "candidate_methods_path": candidate_methods_path,
        "source_packet_path": source_packet_path,
        "source_receipt_path": source_receipt_path,
        "tau_stdout": tau_stdout,
        "tau_stderr": tau_stderr,
    }


def _source_packet(*, query: str, lineage: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "tau.research_source_packet.v1",
        "source_type": "web",
        "method": "manual",
        "query": query,
        "retrieved_at": _utc_stamp(),
        "classification": "design_input",
        "sources": [
            {
                "title": "Zip Slip Vulnerability - Snyk Security Database",
                "url": "https://security.snyk.io/research/zip-slip-vulnerability",
                "relevance": "HIGH",
                "claims_supported": [
                    "Zip Slip is an archive extraction directory traversal pattern.",
                    "Traversal filenames can write outside the intended extraction directory.",
                ],
            },
            {
                "title": "zipfile - Work with ZIP archives - Python documentation",
                "url": "https://docs.python.org/3/library/zipfile.html",
                "relevance": "HIGH",
                "claims_supported": [
                    "Python archive path handling requires filename validation for unsafe member paths in some APIs.",
                    "Absolute paths and parent-directory components are relevant archive path risks.",
                ],
            },
            {
                "title": "snyk/zip-slip-vulnerability examples",
                "url": "https://github.com/snyk/zip-slip-vulnerability",
                "relevance": "MEDIUM",
                "claims_supported": [
                    "Public examples classify traversal filenames as the essential Zip Slip payload shape.",
                    "Archive formats and language APIs vary, so implementation-specific validation remains required.",
                ],
            },
        ],
        "summary": (
            "Manual source packet for BATTLE-004 child research. Sources inform candidate "
            "archive path traversal methods only; parent lineage remains the local evidence."
        ),
        "limitations": [
            "Manual source packet was not fetched by a live external search tool in this PR3b node.",
            "Research is design input only.",
            "Judge replay remains required for exploit success.",
            f"Lineage child lane: {lineage.get('child_lane_id')}",
        ],
    }


def _candidate_methods(*, lineage: dict[str, Any], source_receipt: dict[str, Any]) -> dict[str, Any]:
    source_refs = ["research-source-receipt.json"]
    inherited = [item for item in lineage.get("inherited_methods", []) if isinstance(item, str)]
    return {
        "schema": CANDIDATE_METHODS_SCHEMA,
        "battle_id": lineage.get("battle_id"),
        "child_lane_id": lineage.get("child_lane_id"),
        "status": "PASS" if source_receipt.get("status") == "PASS" else "BLOCKED",
        "mocked": False,
        "live": "tau_command_spec_node",
        "provider_live": False,
        "fixture_fallback_used": False,
        "source_receipts": source_refs,
        "methods": [
            {
                "method_id": "child_archive_traversal_baseline",
                "name": "Child archive traversal baseline",
                "source": "manual_source_receipt",
                "inherited": "zip_slip_basic" in inherited,
                "complexity": "low",
                "access_mode": "black_box",
                "technique_class": "filesystem_path",
                "expected_usefulness": "high",
                "evidence_refs": source_refs + ["lineage_summary.json"],
                "rationale": "Start child synthesis from the simplest archive path traversal family before adding unrelated staging ideas.",
                "known_risks": ["Target API specifics are not proven by research."],
            },
            {
                "method_id": "child_archive_path_normalization_variants",
                "name": "Archive path normalization variants",
                "source": "manual_source_receipt",
                "inherited": "archive_encoding_variant" in inherited,
                "complexity": "medium",
                "access_mode": "grey_box",
                "technique_class": "encoding_variant",
                "expected_usefulness": "medium",
                "evidence_refs": source_refs + ["lineage_summary.json"],
                "rationale": "Try filename normalization and separator variants only after baseline contact is understood.",
                "known_risks": ["Could generate malformed archives or non-portable filenames."],
            },
            {
                "method_id": "child_drop_mitm_and_assembly",
                "name": "Drop MITM and assembly ideas for first child",
                "source": "negative_parent_evidence",
                "inherited": False,
                "complexity": "low",
                "access_mode": "black_box",
                "technique_class": "negative_filter",
                "expected_usefulness": "high",
                "evidence_refs": source_refs + ["lineage_summary.json"],
                "rationale": "Parent evidence labels protocol staging and assembly payload probes as likely irrelevant to local archive import.",
                "known_risks": ["May miss a creative but unsupported branch."],
            },
        ],
        "claims": {
            "proves": ["Battle derived candidate methods from source-bearing research and parent lineage evidence."],
            "does_not_prove": ["Any candidate method works.", "Any exploit code was generated.", "Exploit success."],
        },
    }


def _research_query(lineage: dict[str, Any]) -> str:
    questions = [item for item in lineage.get("next_research_questions", []) if isinstance(item, str)]
    if questions:
        return f"BATTLE-004 public archive import child research: {questions[0]}"
    return "BATTLE-004 public archive import Zip Slip child research"


def _used_for_source(index: int) -> list[str]:
    if index == 0:
        return ["candidate_method", "negative_evidence"]
    if index == 1:
        return ["candidate_method", "compile_repair_policy"]
    return ["negative_evidence"]


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _utc_stamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
