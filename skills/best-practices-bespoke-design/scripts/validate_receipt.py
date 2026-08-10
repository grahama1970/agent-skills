#!/usr/bin/env python3
"""Validate a bespoke-design proof receipt.

The validator is intentionally fail-closed and uses the Python standard library.
If the optional ``jsonschema`` package is installed, it also validates against the
bundled JSON Schema before running cross-field truth checks.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

ALLOWED_STATUSES = {"PASS", "FAIL", "NOT_TESTED", "BLOCKED"}
REQUIRED_GATES = {f"G{i}" for i in range(21)}
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
PLACEHOLDER_RE = re.compile(r"\b(?:tbd|todo|placeholder|lorem ipsum|fill me|unknown)\b", re.I)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a bespoke-design-receipt.v1 JSON document."
    )
    parser.add_argument("receipt", type=Path, help="Path to the receipt JSON")
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "schemas"
        / "bespoke-design-receipt.schema.json",
        help="Path to the JSON Schema",
    )
    parser.add_argument(
        "--skip-optional-jsonschema",
        action="store_true",
        help="Skip validation with the optional jsonschema package.",
    )
    return parser.parse_args()


def read_json(path: Path, errors: list[str], label: str) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        errors.append(f"{label}: file not found: {path}")
    except json.JSONDecodeError as exc:
        errors.append(f"{label}: invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}")
    except OSError as exc:
        errors.append(f"{label}: could not read {path}: {exc}")
    return None


def as_dict(value: Any, path: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{path}: expected object")
        return {}
    return value


def as_list(value: Any, path: str, errors: list[str]) -> list[Any]:
    if not isinstance(value, list):
        errors.append(f"{path}: expected array")
        return []
    return value


def nonempty_text(value: Any, path: str, errors: list[str], minimum: int = 1) -> str:
    if not isinstance(value, str) or len(value.strip()) < minimum:
        errors.append(f"{path}: expected non-empty string with at least {minimum} character(s)")
        return ""
    return value.strip()


def valid_sha(value: Any, path: str, errors: list[str]) -> str:
    text = nonempty_text(value, path, errors)
    if text and not SHA256_RE.fullmatch(text):
        errors.append(f"{path}: expected lowercase 64-character SHA-256")
    return text


def unique_nonempty_strings(
    value: Any,
    path: str,
    errors: list[str],
    minimum_count: int = 0,
    minimum_length: int = 1,
) -> list[str]:
    raw = as_list(value, path, errors)
    result: list[str] = []
    for index, item in enumerate(raw):
        text = nonempty_text(item, f"{path}[{index}]", errors, minimum_length)
        if text:
            result.append(text)
    normalized = [item.casefold() for item in result]
    if len(set(normalized)) != len(normalized):
        errors.append(f"{path}: values must be unique")
    if len(result) < minimum_count:
        errors.append(f"{path}: expected at least {minimum_count} item(s)")
    return result


def check_placeholder_strings(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, str):
        if PLACEHOLDER_RE.search(value):
            errors.append(f"{path}: contains placeholder language")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            check_placeholder_strings(item, f"{path}[{index}]", errors)
    elif isinstance(value, dict):
        for key, item in value.items():
            check_placeholder_strings(item, f"{path}.{key}", errors)


def validate_optional_schema(
    receipt: Any, schema_path: Path, errors: list[str], skip: bool
) -> bool:
    if skip:
        return False
    try:
        import jsonschema  # type: ignore
    except ImportError:
        return False

    schema_errors: list[str] = []
    schema = read_json(schema_path, schema_errors, "schema")
    if schema_errors:
        errors.extend(schema_errors)
        return True
    try:
        validator = jsonschema.Draft202012Validator(schema)
        for issue in sorted(validator.iter_errors(receipt), key=lambda item: list(item.path)):
            location = "$"
            if issue.path:
                location += "".join(
                    f"[{part}]" if isinstance(part, int) else f".{part}" for part in issue.path
                )
            errors.append(f"schema {location}: {issue.message}")
    except Exception as exc:  # defensive: schema tooling itself must not hide failure
        errors.append(f"schema validation failed unexpectedly: {exc}")
    return True


def artifact_references_exist(
    ids: Iterable[Any],
    path: str,
    artifact_ids: set[str],
    errors: list[str],
    require_nonempty: bool = False,
) -> list[str]:
    refs = unique_nonempty_strings(list(ids) if not isinstance(ids, list) else ids, path, errors)
    if require_nonempty and not refs:
        errors.append(f"{path}: at least one evidence artifact is required")
    for ref in refs:
        if ref not in artifact_ids:
            errors.append(f"{path}: unknown artifact id {ref!r}")
    return refs


def validate_receipt(receipt: Any, schema_path: Path, skip_schema: bool) -> tuple[list[str], bool]:
    errors: list[str] = []
    schema_used = validate_optional_schema(receipt, schema_path, errors, skip_schema)

    root = as_dict(receipt, "$", errors)
    if not root:
        return errors, schema_used

    if root.get("schema_version") != "bespoke-design-receipt.v1":
        errors.append("$.schema_version: expected 'bespoke-design-receipt.v1'")

    project = as_dict(root.get("project"), "$.project", errors)
    nonempty_text(project.get("name"), "$.project.name", errors)
    nonempty_text(project.get("surface"), "$.project.surface", errors)
    nonempty_text(project.get("source_revision"), "$.project.source_revision", errors)
    nonempty_text(
        project.get("implementation_revision"),
        "$.project.implementation_revision",
        errors,
    )
    nonempty_text(project.get("generated_at"), "$.project.generated_at", errors)
    fixture = project.get("fixture", False)
    if not isinstance(fixture, bool):
        errors.append("$.project.fixture: expected boolean")
        fixture = False

    provenance = as_dict(root.get("source_provenance"), "$.source_provenance", errors)
    valid_sha(
        provenance.get("source_bundle_sha256"),
        "$.source_provenance.source_bundle_sha256",
        errors,
    )
    source_count = provenance.get("authoritative_source_count")
    if not isinstance(source_count, int) or isinstance(source_count, bool) or source_count < 1:
        errors.append("$.source_provenance.authoritative_source_count: expected integer >= 1")

    territories = as_list(root.get("concept_territories"), "$.concept_territories", errors)
    if len(territories) < 3:
        errors.append("$.concept_territories: at least three territories are required")

    territory_ids: list[str] = []
    premises: list[str] = []
    compositions: list[str] = []
    typography_strategies: list[str] = []
    image_logics: list[str] = []
    motifs: list[str] = []

    for index, territory_value in enumerate(territories):
        path = f"$.concept_territories[{index}]"
        territory = as_dict(territory_value, path, errors)
        territory_ids.append(nonempty_text(territory.get("id"), f"{path}.id", errors))
        nonempty_text(territory.get("name"), f"{path}.name", errors)
        premises.append(
            nonempty_text(territory.get("semantic_premise"), f"{path}.semantic_premise", errors, 20)
        )
        nonempty_text(territory.get("emotional_posture"), f"{path}.emotional_posture", errors, 3)
        typography_strategies.append(
            nonempty_text(
                territory.get("typography_strategy"),
                f"{path}.typography_strategy",
                errors,
                10,
            )
        )
        compositions.append(
            nonempty_text(
                territory.get("composition_model"),
                f"{path}.composition_model",
                errors,
                10,
            )
        )
        image_logics.append(
            nonempty_text(territory.get("image_logic"), f"{path}.image_logic", errors, 10)
        )
        motifs.append(
            nonempty_text(territory.get("primary_motif"), f"{path}.primary_motif", errors, 3)
        )
        unique_nonempty_strings(
            territory.get("evidence_claim_ids"),
            f"{path}.evidence_claim_ids",
            errors,
            minimum_count=1,
        )

    for label, values in (
        ("ids", territory_ids),
        ("semantic premises", premises),
        ("composition models", compositions),
        ("typography strategies", typography_strategies),
        ("image logics", image_logics),
        ("primary motifs", motifs),
    ):
        cleaned = [value.casefold() for value in values if value]
        if len(set(cleaned)) != len(cleaned):
            errors.append(f"$.concept_territories: {label} must be unique across territories")

    selected = nonempty_text(root.get("selected_territory_id"), "$.selected_territory_id", errors)
    if selected and selected not in set(territory_ids):
        errors.append("$.selected_territory_id: must reference an existing territory id")

    grammar = as_dict(root.get("visual_grammar"), "$.visual_grammar", errors)
    nonempty_text(grammar.get("narrative_premise"), "$.visual_grammar.narrative_premise", errors, 20)
    unique_nonempty_strings(
        grammar.get("non_color_invariants"),
        "$.visual_grammar.non_color_invariants",
        errors,
        minimum_count=3,
        minimum_length=8,
    )
    motif_mappings = as_list(grammar.get("motif_mappings"), "$.visual_grammar.motif_mappings", errors)
    if not motif_mappings:
        errors.append("$.visual_grammar.motif_mappings: at least one mapping is required")
    for index, mapping_value in enumerate(motif_mappings):
        path = f"$.visual_grammar.motif_mappings[{index}]"
        mapping = as_dict(mapping_value, path, errors)
        nonempty_text(mapping.get("motif"), f"{path}.motif", errors, 2)
        nonempty_text(mapping.get("meaning_or_job"), f"{path}.meaning_or_job", errors, 8)
        unique_nonempty_strings(
            mapping.get("source_claim_ids"),
            f"{path}.source_claim_ids",
            errors,
            minimum_count=1,
        )
    unique_nonempty_strings(
        grammar.get("responsive_transformations"),
        "$.visual_grammar.responsive_transformations",
        errors,
        minimum_count=3,
        minimum_length=8,
    )
    abundance = as_dict(
        grammar.get("controlled_abundance"),
        "$.visual_grammar.controlled_abundance",
        errors,
    )
    for key in ("expressive_zones", "calm_reading_zones", "calm_task_zones"):
        unique_nonempty_strings(
            abundance.get(key),
            f"$.visual_grammar.controlled_abundance.{key}",
            errors,
            minimum_count=1,
        )

    artifacts = as_list(root.get("artifacts"), "$.artifacts", errors)
    if not artifacts:
        errors.append("$.artifacts: at least one artifact is required")
    artifact_ids_list: list[str] = []
    for index, artifact_value in enumerate(artifacts):
        path = f"$.artifacts[{index}]"
        artifact = as_dict(artifact_value, path, errors)
        artifact_ids_list.append(
            nonempty_text(artifact.get("artifact_id"), f"{path}.artifact_id", errors)
        )
        nonempty_text(artifact.get("kind"), f"{path}.kind", errors)
        nonempty_text(artifact.get("path"), f"{path}.path", errors)
        valid_sha(artifact.get("sha256"), f"{path}.sha256", errors)
    artifact_ids = {item for item in artifact_ids_list if item}
    if len(artifact_ids) != len([item for item in artifact_ids_list if item]):
        errors.append("$.artifacts: artifact_id values must be unique")

    blind = as_dict(root.get("blind_tests"), "$.blind_tests", errors)

    logo = as_dict(blind.get("logo_off"), "$.blind_tests.logo_off", errors)
    logo_status = logo.get("status")
    if logo_status not in ALLOWED_STATUSES:
        errors.append("$.blind_tests.logo_off.status: invalid status")
    logo_correct = logo.get("correct_assignments")
    logo_total = logo.get("total_assignments")
    if not isinstance(logo_correct, int) or isinstance(logo_correct, bool) or logo_correct < 0:
        errors.append("$.blind_tests.logo_off.correct_assignments: expected integer >= 0")
        logo_correct = 0
    if not isinstance(logo_total, int) or isinstance(logo_total, bool) or logo_total < 0:
        errors.append("$.blind_tests.logo_off.total_assignments: expected integer >= 0")
        logo_total = 0
    artifact_references_exist(
        logo.get("raw_output_artifact_ids", []),
        "$.blind_tests.logo_off.raw_output_artifact_ids",
        artifact_ids,
        errors,
        require_nonempty=logo_status == "PASS",
    )
    if logo_correct > logo_total:
        errors.append("$.blind_tests.logo_off: correct_assignments cannot exceed total_assignments")
    if logo_status == "PASS":
        if logo_total < 15:
            errors.append("$.blind_tests.logo_off: PASS requires at least 15 assignments")
        elif logo_correct / logo_total < 0.80:
            errors.append("$.blind_tests.logo_off: PASS requires at least 80% correct")

    swap = as_dict(blind.get("competitor_swap"), "$.blind_tests.competitor_swap", errors)
    swap_status = swap.get("status")
    if swap_status not in ALLOWED_STATUSES:
        errors.append("$.blind_tests.competitor_swap.status: invalid status")
    channels = unique_nonempty_strings(
        swap.get("conflict_channels"),
        "$.blind_tests.competitor_swap.conflict_channels",
        errors,
    )
    artifact_references_exist(
        swap.get("raw_output_artifact_ids", []),
        "$.blind_tests.competitor_swap.raw_output_artifact_ids",
        artifact_ids,
        errors,
        require_nonempty=swap_status == "PASS",
    )
    if swap_status == "PASS" and len(channels) < 3:
        errors.append("$.blind_tests.competitor_swap: PASS requires at least three conflict channels")

    family = as_dict(
        blind.get("cross_screen_family"),
        "$.blind_tests.cross_screen_family",
        errors,
    )
    family_status = family.get("status")
    if family_status not in ALLOWED_STATUSES:
        errors.append("$.blind_tests.cross_screen_family.status: invalid status")
    family_correct = family.get("correct_groupings")
    family_total = family.get("total_groupings")
    if not isinstance(family_correct, int) or isinstance(family_correct, bool) or family_correct < 0:
        errors.append("$.blind_tests.cross_screen_family.correct_groupings: expected integer >= 0")
        family_correct = 0
    if not isinstance(family_total, int) or isinstance(family_total, bool) or family_total < 0:
        errors.append("$.blind_tests.cross_screen_family.total_groupings: expected integer >= 0")
        family_total = 0
    observed_invariants = unique_nonempty_strings(
        family.get("observed_non_color_invariants"),
        "$.blind_tests.cross_screen_family.observed_non_color_invariants",
        errors,
    )
    artifact_references_exist(
        family.get("raw_output_artifact_ids", []),
        "$.blind_tests.cross_screen_family.raw_output_artifact_ids",
        artifact_ids,
        errors,
        require_nonempty=family_status == "PASS",
    )
    if family_correct > family_total:
        errors.append("$.blind_tests.cross_screen_family: correct_groupings cannot exceed total_groupings")
    if family_status == "PASS":
        if family_total < 5:
            errors.append("$.blind_tests.cross_screen_family: PASS requires at least five groupings")
        elif family_correct / family_total < 0.80:
            errors.append("$.blind_tests.cross_screen_family: PASS requires at least 80% correct")
        if len(observed_invariants) < 3:
            errors.append(
                "$.blind_tests.cross_screen_family: PASS requires at least three observed non-color invariants"
            )

    leakage = as_dict(
        blind.get("reference_leakage"),
        "$.blind_tests.reference_leakage",
        errors,
    )
    leakage_status = leakage.get("status")
    if leakage_status not in ALLOWED_STATUSES:
        errors.append("$.blind_tests.reference_leakage.status: invalid status")
    artifact_references_exist(
        leakage.get("reference_corpus_artifact_ids", []),
        "$.blind_tests.reference_leakage.reference_corpus_artifact_ids",
        artifact_ids,
        errors,
        require_nonempty=True,
    )
    copied = leakage.get("distinctive_combination_copied")
    if not isinstance(copied, bool):
        errors.append("$.blind_tests.reference_leakage.distinctive_combination_copied: expected boolean")
    artifact_references_exist(
        leakage.get("raw_output_artifact_ids", []),
        "$.blind_tests.reference_leakage.raw_output_artifact_ids",
        artifact_ids,
        errors,
        require_nonempty=leakage_status == "PASS",
    )
    if leakage_status == "PASS" and copied is not False:
        errors.append("$.blind_tests.reference_leakage: PASS requires copied=false")

    gates = as_dict(root.get("gates"), "$.gates", errors)
    actual_gate_ids = set(gates)
    missing = REQUIRED_GATES - actual_gate_ids
    extra = actual_gate_ids - REQUIRED_GATES
    if missing:
        errors.append(f"$.gates: missing required gates {sorted(missing)}")
    if extra:
        errors.append(f"$.gates: unknown gates {sorted(extra)}")

    statuses: dict[str, str] = {}
    for gate_id in sorted(REQUIRED_GATES, key=lambda item: int(item[1:])):
        gate = as_dict(gates.get(gate_id), f"$.gates.{gate_id}", errors)
        status = gate.get("status")
        if status not in ALLOWED_STATUSES:
            errors.append(f"$.gates.{gate_id}.status: invalid status")
            status = ""
        statuses[gate_id] = status
        nonempty_text(gate.get("summary"), f"$.gates.{gate_id}.summary", errors, 4)
        artifact_references_exist(
            gate.get("evidence_artifact_ids", []),
            f"$.gates.{gate_id}.evidence_artifact_ids",
            artifact_ids,
            errors,
            require_nonempty=status == "PASS",
        )

    final_status = root.get("final_status")
    if final_status not in {"READY", "NOT_READY", "BLOCKED"}:
        errors.append("$.final_status: expected READY, NOT_READY, or BLOCKED")
    all_pass = bool(statuses) and all(status == "PASS" for status in statuses.values())
    any_blocked = any(status == "BLOCKED" for status in statuses.values())
    if final_status == "READY" and not all_pass:
        errors.append("$.final_status: READY is illegal unless every required gate is PASS")
    if all_pass and final_status != "READY":
        errors.append("$.final_status: all gates are PASS, so final_status must be READY")
    if final_status == "BLOCKED" and not any_blocked:
        errors.append("$.final_status: BLOCKED requires at least one BLOCKED gate")
    if final_status == "NOT_READY" and any_blocked:
        errors.append("$.final_status: use BLOCKED when any required gate is BLOCKED")

    if not fixture:
        check_placeholder_strings(root, "$", errors)

    return errors, schema_used


def main() -> int:
    args = parse_args()
    read_errors: list[str] = []
    receipt = read_json(args.receipt, read_errors, "receipt")
    if read_errors:
        print(json.dumps({"status": "FAIL", "errors": read_errors}, indent=2))
        return 1

    errors, schema_used = validate_receipt(
        receipt,
        schema_path=args.schema,
        skip_schema=args.skip_optional_jsonschema,
    )
    if errors:
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "schema_validation_used": schema_used,
                    "error_count": len(errors),
                    "errors": errors,
                },
                indent=2,
            )
        )
        return 1

    print(
        json.dumps(
            {
                "status": "PASS",
                "schema_validation_used": schema_used,
                "receipt": str(args.receipt),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
