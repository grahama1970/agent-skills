"""Normalize specimen population receipts for UX consumption."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema


NORMALIZED_POPULATION_SCHEMA = "battle.normalized_population_fixture.v1"
FIXTURE_KIND_PR5 = "pr5_population"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "battle.normalized_population_fixture.v1.schema.json"
PATH_LEAK_MARKERS = (
    "tau-dag-run/",
    "command-loop/",
    "command-artifacts/",
    "/home/",
    "/tmp/",
    "/mnt/",
    "/workspace",
    "provider-workspace",
    "pr3c-provider-workspaces",
    "outputs/provider-worker-result.json",
    "inputs/tau-scillm-worker-work-order.json",
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
MAY_CLAIM = [
    "multiple_specimens_materialized",
    "generation_metadata_recorded",
    "parent_child_lineage_recorded",
    "method_sets_recorded",
    "provider_authorship_status_recorded",
    "compile_status_recorded",
    "runtime_status_recorded",
    "target_contact_unproven_recorded",
    "fitness_vector_recorded",
    "selection_status_recorded",
    "judge_not_run",
]
MUST_NOT_CLAIM = [
    "full_autonomous_population_engine",
    "live_tau_code_generation",
    "provider_authored_specimens",
    "exploit_success",
    "target_contact_is_exploit_success",
    "runnable_is_exploit_success",
    "blue_detection",
    "blue_bypass",
    "blue_kill",
    "blue_block",
    "judge_success",
    "packet_level_behavior",
    "memory_promotion",
]


def normalize_population_fixture(
    *,
    proof_dir: Path,
    out_dir: Path,
    public_out_dir: Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Write a normalized population fixture from a combiner-style proof directory."""

    root = _resolve_proof_root(proof_dir)
    run_receipt = _read_json(root / "run-receipt.json")
    scoreboard = _read_json(root / "scoreboard.json")
    method_menu = _read_json(root / "method-menu.json") if (root / "method-menu.json").exists() else {}
    specimens = _load_specimens(root)
    if len(specimens) < 2:
        raise RuntimeError(f"population fixture requires at least two specimens under {root / 'specimens'}")
    fixture = _fixture(
        root=root,
        run_receipt=run_receipt,
        scoreboard=scoreboard,
        method_menu=method_menu,
        specimens=specimens,
        generated_at=generated_at,
    )
    report = validate_normalized_population_fixture(fixture)
    source_index = _source_index(root=root, run_receipt=run_receipt, scoreboard=scoreboard, method_menu=method_menu, specimens=specimens)

    out_dir.mkdir(parents=True, exist_ok=True)
    fixture_path = out_dir / "battle.normalized_population_fixture.json"
    validation_path = out_dir / "validation.json"
    source_index_path = out_dir / "source-receipt-index.json"
    _write_json(fixture_path, fixture)
    _write_json(validation_path, report)
    _write_json(source_index_path, source_index)
    if public_out_dir is not None:
        public_out_dir.mkdir(parents=True, exist_ok=True)
        public_fixture = public_out_dir / "battle.normalized_population_fixture.json"
        shutil.copyfile(fixture_path, public_fixture)
        if _sha256_file(public_fixture) != _sha256_file(fixture_path):
            raise RuntimeError("public population fixture hash mismatch after copy")
    return fixture


def validate_normalized_population_fixture_path(path: Path) -> dict[str, Any]:
    return validate_normalized_population_fixture(_read_json(path))


def validate_normalized_population_fixture(fixture: dict[str, Any]) -> dict[str, Any]:
    schema = _read_json(SCHEMA_PATH)
    jsonschema.validate(fixture, schema)
    errors: list[str] = []
    if fixture.get("schema") != NORMALIZED_POPULATION_SCHEMA:
        errors.append("schema must be battle.normalized_population_fixture.v1")
    if fixture.get("fixture_kind") != FIXTURE_KIND_PR5:
        errors.append("fixture_kind must be pr5_population")
    for key, expected in {
        "status": "PASS",
        "mocked": False,
        "live": "local_docker_specimen_fixture",
        "proof_mode": "local_docker_specimen_population_fixture",
    }.items():
        if fixture.get(key) != expected:
            errors.append(f"{key} must be {expected!r}")
    campaign = fixture.get("campaign") if isinstance(fixture.get("campaign"), dict) else {}
    if campaign.get("full_population_engine_proven") is not False:
        errors.append("campaign.full_population_engine_proven must be false")
    cards = fixture.get("specimen_cards") if isinstance(fixture.get("specimen_cards"), list) else []
    if len(cards) < 2:
        errors.append("specimen_cards requires at least two specimens")
    generations = {card.get("generation") for card in cards if isinstance(card.get("generation"), int)}
    if len(generations) < 2:
        errors.append("population fixture requires at least two generations")
    if not fixture.get("lineage_edges"):
        errors.append("lineage_edges must include at least one receipt-backed edge")
    for card in cards:
        if card.get("judge_status") != "NOT_RUN":
            errors.append(f"{card.get('specimen_id')}: judge_status must be NOT_RUN")
        if card.get("judge_verified_exploits") != 0:
            errors.append(f"{card.get('specimen_id')}: judge_verified_exploits must be 0")
        if card.get("target_contact", {}).get("status") == "TARGET_CONTACT_UNPROVEN" and "exploit_success" in card.get("selection", {}).get("reason", ""):
            errors.append(f"{card.get('specimen_id')}: target contact cannot be selected as exploit success")
        provider = card.get("provider_authorship") if isinstance(card.get("provider_authorship"), dict) else {}
        if provider.get("provider_live") is True or provider.get("agentic") is True:
            errors.append(f"{card.get('specimen_id')}: combiner population fixture must not claim provider_live or agentic authorship")
    claims = fixture.get("claim_boundary") if isinstance(fixture.get("claim_boundary"), dict) else {}
    may_claim = set(claims.get("may_claim", []))
    must_not_claim = set(claims.get("must_not_claim", []))
    for item in MAY_CLAIM:
        if item not in may_claim:
            errors.append(f"claim_boundary.may_claim missing {item}")
    for item in MUST_NOT_CLAIM:
        if item not in must_not_claim:
            errors.append(f"claim_boundary.must_not_claim missing {item}")
    forbidden_may_claims = {"exploit_success", "blue_block", "judge_success", "full_autonomous_population_engine", "provider_authored_specimens"}
    if forbidden_may_claims & may_claim:
        errors.append("claim_boundary.may_claim contains forbidden outcome/population claims")
    serialized = json.dumps(fixture, sort_keys=True)
    for marker in [*PATH_LEAK_MARKERS, *PRIVATE_MARKERS]:
        if marker in serialized:
            errors.append(f"normalized population fixture exposes forbidden marker: {marker}")
    for pattern in SECRET_PATTERNS:
        if pattern.search(serialized):
            errors.append("normalized population fixture exposes secret-like material")
    if errors:
        raise ValueError("\n".join(errors))
    return {
        "schema": "battle.normalized_population_fixture_validation.v1",
        "status": "PASS",
        "fixture_kind": fixture["fixture_kind"],
        "battle_id": fixture["battle_id"],
        "specimen_count": len(cards),
        "generation_count": len(generations),
        "lineage_edge_count": len(fixture.get("lineage_edges", [])),
        "judge_verified_exploits": sum(int(card.get("judge_verified_exploits", 0)) for card in cards),
        "raw_paths_redacted": fixture.get("provenance", {}).get("raw_paths_redacted"),
    }


def _fixture(
    *,
    root: Path,
    run_receipt: dict[str, Any],
    scoreboard: dict[str, Any],
    method_menu: dict[str, Any],
    specimens: list[dict[str, Any]],
    generated_at: str | None,
) -> dict[str, Any]:
    method_lookup = {item.get("method_id"): item for item in method_menu.get("methods", []) if isinstance(item, dict)}
    cards = [_specimen_card(item=item, best_specimen_id=scoreboard.get("best_specimen_id"), method_lookup=method_lookup) for item in specimens]
    generation_axis = _generation_axis(cards)
    lineage_edges = _lineage_edges(cards)
    return {
        "schema": NORMALIZED_POPULATION_SCHEMA,
        "fixture_kind": FIXTURE_KIND_PR5,
        "battle_id": str(run_receipt.get("battle_id") or scoreboard.get("battle_id") or "battle-004"),
        "run_id": "battle-004-pr5-population",
        "generated_at": generated_at or _utc_stamp(),
        "status": "PASS",
        "mocked": False,
        "live": "local_docker_specimen_fixture",
        "proof_mode": "local_docker_specimen_population_fixture",
        "campaign": {
            "campaign_id": "battle-004-pr5-population",
            "source_proof": "exploit_combiner_proof",
            "generation_count": len(generation_axis),
            "specimen_count": len(cards),
            "best_specimen_id": scoreboard.get("best_specimen_id"),
            "verdict": scoreboard.get("verdict"),
            "full_population_engine_proven": False,
            "source_limitations": [
                "fixture-backed combiner population, not full autonomous genetic population engine",
                "Tau/provider code generation is not proven by this population fixture",
                "Judge replay was not run for these specimens",
            ],
        },
        "generation_axis": generation_axis,
        "specimen_cards": cards,
        "lineage_edges": lineage_edges,
        "lineage_summary": {
            "parent_child_edges": sum(1 for edge in lineage_edges if edge["edge_type"] == "parent_child"),
            "recombination_edges": sum(1 for edge in lineage_edges if edge["edge_type"] == "recombination"),
            "promoted_count": sum(1 for card in cards if card["selection"]["status"] == "selected_best_runnable_unproven"),
            "abandoned_count": sum(1 for card in cards if card["selection"]["status"] in {"retained_negative_evidence", "retained_runtime_negative_evidence"}),
        },
        "claim_boundary": {
            "may_claim": MAY_CLAIM,
            "must_not_claim": MUST_NOT_CLAIM,
            "compile_passed_is_not_runnable": True,
            "target_contact_is_not_exploit_success": True,
            "runnable_is_not_exploit_success": True,
            "population_fixture_is_not_full_engine": True,
        },
        "receipt_refs": _receipt_refs(root=root, run_receipt=run_receipt, scoreboard=scoreboard, method_menu=method_menu, specimens=specimens),
        "provenance": {
            "source_run_label": "exploit_combiner_proof",
            "normalizer_schema": "battle.normalized_population_fixture_builder.v1",
            "source_receipt_count": 3 + len(specimens) * 2,
            "raw_paths_redacted": True,
            "tau_runtime_paths_exposed": False,
            "command_loop_paths_exposed": False,
            "provider_workspace_paths_exposed": False,
            "docker_raw_paths_exposed": False,
            "raw_stdout_paths_exposed": False,
            "raw_stderr_paths_exposed": False,
            "credentials_exposed": False,
        },
        "copy": {
            "headline": "Specimen population lineage captured",
            "subhead": "Battle normalized four receipt-backed combiner specimens across generations without exposing raw runtime paths.",
            "status_label": "Population fixture; exploit success not claimed",
            "boundary_notice": "This fixture supports specimen cards, lineage, generation scrubbing, fitness, and selection only from receipts. Judge replay is required for exploit or Blue outcome claims.",
        },
        "frontend_handoff": {
            "route": "#battle/population?fixture=battle-004-pr5-population",
            "grid_field": "specimen_cards",
            "lineage_tree_field": "lineage_edges",
            "generation_scrubber_field": "generation_axis",
            "claim_boundary_field": "claim_boundary",
        },
    }


def _load_specimens(root: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for specimen_path in sorted((root / "specimens").glob("*/specimen.json")):
        specimen = _read_json(specimen_path)
        run_receipt = _read_json(specimen_path.with_name("run-receipt.json"))
        _validate_source_pair(specimen, run_receipt)
        items.append({"specimen": specimen, "run_receipt": run_receipt})
    return sorted(items, key=lambda item: (int(item["specimen"].get("generation", 0)), str(item["specimen"].get("specimen_id"))))


def _specimen_card(*, item: dict[str, Any], best_specimen_id: str | None, method_lookup: dict[str, dict[str, Any]]) -> dict[str, Any]:
    specimen = item["specimen"]
    receipt = item["run_receipt"]
    specimen_id = str(specimen.get("specimen_id"))
    target_observed = bool(receipt.get("target_contact", {}).get("observed"))
    runtime_status = "TARGET_CONTACT_UNPROVEN" if target_observed else _runtime_status(receipt)
    compile_status = "COMPILE_PASSED" if receipt.get("compile_ok") else "COMPILE_FAILED"
    chosen_methods = [str(method) for method in specimen.get("chosen_method_ids", [])]
    inherited_methods = [str(method) for method in specimen.get("inherited_method_ids", [])]
    return {
        "specimen_id": specimen_id,
        "generation": int(specimen.get("generation", 0)),
        "parent_specimen_id": specimen.get("parent_specimen_id"),
        "selected_methods": [_method_summary(method_id, method_lookup) for method_id in chosen_methods],
        "selected_method_ids": chosen_methods,
        "inherited_methods": inherited_methods,
        "provider_authorship": {
            "authored_by": str(specimen.get("created_by") or "unknown"),
            "agentic": False,
            "provider_live": False,
            "does_not_prove": ["Tau/provider authored this specimen", "live model generation"],
        },
        "compile_status": compile_status,
        "runtime_status": runtime_status,
        "target_contact": {
            "observed": target_observed,
            "status": "TARGET_CONTACT_UNPROVEN" if target_observed else "NOT_OBSERVED",
            "entrypoint": receipt.get("target_contact", {}).get("entrypoint"),
            "does_not_prove": ["exploit success", "path traversal", "Blue bypass"],
        },
        "judge_status": "NOT_RUN",
        "judge_verified_exploits": 0,
        "fitness": _fitness(receipt=receipt, target_observed=target_observed, method_ids=chosen_methods),
        "novelty": {
            "method_combo_hash": _sha256_text("|".join(sorted(chosen_methods))),
            "method_count": len(chosen_methods),
            "inherited_method_count": len(inherited_methods),
        },
        "selection": _selection(specimen_id=specimen_id, receipt=receipt, best_specimen_id=best_specimen_id, target_observed=target_observed),
    }


def _method_summary(method_id: str, method_lookup: dict[str, dict[str, Any]]) -> dict[str, Any]:
    source = method_lookup.get(method_id, {})
    return {
        "method_id": method_id,
        "name": source.get("name") or method_id,
        "technique_class": source.get("technique_class") or "unknown",
        "source": source.get("source") or "unknown",
        "complexity": source.get("complexity") or "unknown",
    }


def _fitness(*, receipt: dict[str, Any], target_observed: bool, method_ids: list[str]) -> dict[str, Any]:
    compile_ok = bool(receipt.get("compile_ok"))
    runtime_ok = bool(receipt.get("runtime_ok"))
    if runtime_ok and target_observed:
        tier = 3
        label = "target_contact_unproven"
    elif runtime_ok:
        tier = 2
        label = "runs_unproven"
    elif compile_ok:
        tier = 1
        label = "compiles_runtime_failed"
    else:
        tier = 0
        label = "compile_failed"
    return {
        "tier": tier,
        "tier_label": label,
        "compile_ok": compile_ok,
        "runtime_ok": runtime_ok,
        "target_contact_unproven": target_observed,
        "judge_confirmed_exploit": False,
        "novel_method_combination": True,
        "method_count": len(method_ids),
    }


def _selection(*, specimen_id: str, receipt: dict[str, Any], best_specimen_id: str | None, target_observed: bool) -> dict[str, Any]:
    if specimen_id == best_specimen_id:
        return {
            "status": "selected_best_runnable_unproven",
            "reason": "Scoreboard selected this specimen as best because it became runnable or contacted the target, not because it exploited the target.",
            "promoted": False,
        }
    if not receipt.get("compile_ok"):
        return {"status": "retained_negative_evidence", "reason": "Compile failure retained for population history.", "promoted": False}
    if not receipt.get("runtime_ok"):
        return {"status": "retained_runtime_negative_evidence", "reason": "Runtime failure retained for population history.", "promoted": False}
    if target_observed:
        return {"status": "retained_target_contact_unproven", "reason": "Target contact retained as unproven progress.", "promoted": False}
    return {"status": "retained_unproven", "reason": "Specimen retained without Judge proof.", "promoted": False}


def _generation_axis(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, list[str]] = defaultdict(list)
    for card in cards:
        grouped[int(card["generation"])].append(str(card["specimen_id"]))
    return [
        {
            "generation": generation,
            "specimen_ids": sorted(specimen_ids),
            "specimen_count": len(specimen_ids),
            "selected_count": sum(1 for card in cards if card["generation"] == generation and card["selection"]["status"] == "selected_best_runnable_unproven"),
        }
        for generation, specimen_ids in sorted(grouped.items())
    ]


def _lineage_edges(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    card_ids = {card["specimen_id"] for card in cards}
    edges: list[dict[str, Any]] = []
    for card in cards:
        parent = card.get("parent_specimen_id")
        if parent and parent in card_ids:
            edges.append(
                {
                    "edge_id": f"{parent}->{card['specimen_id']}",
                    "edge_type": "parent_child",
                    "from_specimen_id": parent,
                    "to_specimen_id": card["specimen_id"],
                    "spawn_cause": "combiner_iteration_after_prior_specimen_receipt",
                    "inherited_methods": card.get("inherited_methods", []),
                    "promoted": False,
                    "abandoned": card["selection"]["status"] in {"retained_negative_evidence", "retained_runtime_negative_evidence"},
                }
            )
    return edges


def _runtime_status(receipt: dict[str, Any]) -> str:
    value = receipt.get("status")
    if value == "SPECIMEN_COMPILE_FAILED":
        return "COMPILE_FAILED"
    if value == "SPECIMEN_RUNTIME_FAILED":
        return "RUNTIME_FAILED"
    if value == "SPECIMEN_RUNNABLE_UNPROVEN":
        return "RUNNABLE_UNPROVEN"
    return "POLICY_BLOCKED"


def _validate_source_pair(specimen: dict[str, Any], receipt: dict[str, Any]) -> None:
    if specimen.get("schema") != "battle.exploit_specimen.v1":
        raise ValueError("source specimen schema must be battle.exploit_specimen.v1")
    if receipt.get("schema") != "battle.exploit_specimen_run.v1":
        raise ValueError("source run receipt schema must be battle.exploit_specimen_run.v1")
    if specimen.get("specimen_id") != receipt.get("specimen_id"):
        raise ValueError("source specimen/run receipt specimen_id mismatch")
    claims = " ".join([*receipt.get("proves", []), *specimen.get("proves", [])])
    if "exploit success" in claims.lower() or "exploited the target" in claims.lower():
        raise ValueError("population source receipts must not claim exploit success")


def _source_index(*, root: Path, run_receipt: dict[str, Any], scoreboard: dict[str, Any], method_menu: dict[str, Any], specimens: list[dict[str, Any]]) -> dict[str, Any]:
    refs = _receipt_refs(root=root, run_receipt=run_receipt, scoreboard=scoreboard, method_menu=method_menu, specimens=specimens)
    return {
        "schema": "battle.normalized_population_source_receipt_index.v1",
        "status": "PASS",
        "battle_id": run_receipt.get("battle_id") or scoreboard.get("battle_id"),
        "fixture_kind": FIXTURE_KIND_PR5,
        "source_receipt_count": len(refs),
        "receipts": refs,
        "raw_paths_redacted": True,
    }


def _receipt_refs(*, root: Path, run_receipt: dict[str, Any], scoreboard: dict[str, Any], method_menu: dict[str, Any], specimens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[tuple[str, Path, dict[str, Any]]] = [
        ("combiner_run_receipt", root / "run-receipt.json", run_receipt),
        ("combiner_scoreboard", root / "scoreboard.json", scoreboard),
    ]
    if method_menu:
        items.append(("method_menu", root / "method-menu.json", method_menu))
    for item in specimens:
        specimen = item["specimen"]
        receipt = item["run_receipt"]
        specimen_id = str(specimen.get("specimen_id"))
        items.append((f"specimen_{specimen_id}", root / "specimens" / specimen_id / "specimen.json", specimen))
        items.append((f"specimen_run_{specimen_id}", root / "specimens" / specimen_id / "run-receipt.json", receipt))
    return [
        {"id": item_id, "schema": payload.get("schema"), "status": payload.get("status") or payload.get("verdict"), "label": path.name, "sha256": _sha256_file(path)}
        for item_id, path, payload in items
    ]


def _resolve_proof_root(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.is_dir():
        return resolved
    if resolved.name == "run-receipt.json":
        return resolved.parent
    raise RuntimeError(f"population proof source must be a directory or run-receipt.json: {path}")


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


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _utc_stamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
