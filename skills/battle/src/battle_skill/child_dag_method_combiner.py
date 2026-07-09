"""Deterministic method-combiner adapter for Battle child Tau DAG nodes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


EXPLOIT_GENOME_SCHEMA = "battle.child_exploit_genome.v1"


def run_method_combiner(
    *,
    artifact_dir: Path,
    research_receipts_path: Path,
    candidate_methods_path: Path,
) -> dict[str, Any]:
    """Combine source-backed child candidate methods without authoring exploit code."""

    research = _read_json(research_receipts_path)
    candidates = _read_json(candidate_methods_path)
    errors = _validate_inputs(research=research, candidates=candidates)
    selected = _select_methods(candidates) if not errors else []
    genome = {
        "schema": EXPLOIT_GENOME_SCHEMA,
        "battle_id": research.get("battle_id") or candidates.get("battle_id"),
        "child_lane_id": research.get("child_lane_id") or candidates.get("child_lane_id"),
        "status": "PASS" if not errors else "BLOCKED",
        "mocked": False,
        "live": "tau_command_spec_node",
        "provider_live": False,
        "fixture_fallback_used": False,
        "created_by": "battle_deterministic_method_combiner",
        "agentic": False,
        "selected_method_ids": [method["method_id"] for method in selected],
        "rejected_method_ids": _rejected_method_ids(candidates, selected),
        "source_receipts": ["research_receipts.json", "candidate_methods.json"],
        "strategy": {
            "primary": "Prefer low-complexity archive traversal baseline before high-complexity inherited branches.",
            "repair_bias": "Use source-backed path normalization variants only after baseline target contact.",
            "negative_filter": "Defer MITM staging and assembly payload probes until evidence supports them.",
        },
        "errors": errors,
        "claims": {
            "proves": [
                "Battle deterministically combined source-backed child methods into an exploit genome candidate."
            ]
            if not errors
            else [],
            "does_not_prove": [
                "Tau authored exploit code.",
                "Any exploit code was generated.",
                "Any exploit code compiles.",
                "Any exploit code runs.",
                "Any exploit succeeded.",
            ],
        },
    }
    rationale = _rationale(genome=genome, selected=selected)
    genome_path = artifact_dir / "exploit_genome.json"
    rationale_path = artifact_dir / "combination_rationale.md"
    _write_json(genome_path, genome)
    rationale_path.write_text(rationale, encoding="utf-8")
    return {
        "status": genome["status"],
        "genome": genome,
        "genome_path": genome_path,
        "rationale_path": rationale_path,
        "errors": errors,
    }


def _validate_inputs(*, research: dict[str, Any], candidates: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if research.get("schema") != "battle.child_research_receipts.v1":
        errors.append("research_receipts schema must be battle.child_research_receipts.v1")
    if research.get("status") != "PASS":
        errors.append("research_receipts status must be PASS")
    if candidates.get("schema") != "battle.child_candidate_methods.v1":
        errors.append("candidate_methods schema must be battle.child_candidate_methods.v1")
    if candidates.get("status") != "PASS":
        errors.append("candidate_methods status must be PASS")
    methods = candidates.get("methods")
    if not isinstance(methods, list) or not methods:
        errors.append("candidate_methods must contain non-empty methods")
    proves = " ".join(research.get("claims", {}).get("proves", []) if isinstance(research.get("claims"), dict) else []).lower()
    if "exploit success" in proves or "exploited" in proves:
        errors.append("research_receipts must not claim exploit success")
    return errors


def _select_methods(candidates: dict[str, Any]) -> list[dict[str, Any]]:
    methods = [method for method in candidates.get("methods", []) if isinstance(method, dict)]
    selected: list[dict[str, Any]] = []
    for method in methods:
        method_id = method.get("method_id")
        if method_id in {"child_archive_traversal_baseline", "child_archive_path_normalization_variants"}:
            selected.append(method)
    return selected


def _rejected_method_ids(candidates: dict[str, Any], selected: list[dict[str, Any]]) -> list[str]:
    selected_ids = {method.get("method_id") for method in selected}
    return [
        str(method.get("method_id"))
        for method in candidates.get("methods", [])
        if isinstance(method, dict) and method.get("method_id") not in selected_ids
    ]


def _rationale(*, genome: dict[str, Any], selected: list[dict[str, Any]]) -> str:
    lines = [
        "# Battle Child Method Combination Rationale",
        "",
        f"Status: {genome['status']}",
        "",
        "Selected methods:",
    ]
    lines.extend(f"- `{method['method_id']}`: {method.get('rationale', '')}" for method in selected)
    lines.extend(
        [
            "",
            "Claim boundary:",
            "- This genome is not exploit code.",
            "- This genome does not prove exploit success.",
            "- Code authoring remains blocked until a real Tau/provider code-authoring adapter exists.",
            "",
        ]
    )
    return "\n".join(lines)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
