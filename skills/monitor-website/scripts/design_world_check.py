#!/usr/bin/env python3
"""design-world-check (#1337): validate grahama.co's visual-world contract and
scan for deterministically-checkable AI-template residue. Rendered/blind gates
read receipt files when present and return NOT_TESTED only when evidence is
absent — prose is not proof.
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SITE = REPO / "site"
DESIGN_ROUNDTABLE = SITE / "design-roundtable"


def _load_yaml(p: Path):
    import yaml
    return yaml.safe_load(p.read_text())


def validate_contract(c: dict) -> list[str]:
    errs = []
    if c.get("schema") != "grahama.design_world.v1":
        errs.append("contract: schema must be grahama.design_world.v1")
    if not str(c.get("premise", "")).strip():
        errs.append("contract: premise missing")
    inv = c.get("invariants") or []
    if len(inv) < 3:
        errs.append("contract: at least 3 non-color invariants required")
    for k in ("role_grammar", "exclusions", "machine_output_selectors"):
        if not c.get(k):
            errs.append(f"contract: {k} missing")
    return errs


def scan_mono_on_human_labels(css_files, allow: list[str]) -> list[dict]:
    """Flag any CSS rule that sets font-family: var(--mono) whose selector is not
    an approved machine-output selector. This is the deterministic form of the
    'monospace on human-written labels' exclusion."""
    allow_set = {a.strip() for a in allow}
    violations = []
    comment_re = re.compile(r"/\*.*?\*/", re.S)
    rule_re = re.compile(r"([^{}]+)\{([^{}]*)\}", re.S)
    for f in css_files:
        text = comment_re.sub(" ", f.read_text())  # strip CSS comments (no false selectors)
        for m in rule_re.finditer(text):
            sel, body = " ".join(m.group(1).split()), m.group(2)
            if "font-family: var(--mono)" in body or "font-family:var(--mono)" in body:
                # allowed if any approved machine-output selector is present in the
                # (possibly grouped/pseudo) selector — covers grouped rules.
                if any(a and a in sel for a in allow_set):
                    continue
                violations.append({"file": f.name, "selector": sel[:80]})
    return violations


def _load_json(path: Path) -> tuple[dict | None, str | None]:
    if not path.is_file():
        return None, "missing"
    try:
        return json.loads(path.read_text()), None
    except json.JSONDecodeError as exc:
        return None, f"invalid_json: {exc}"


def _resolve_artifact(path_value: str) -> Path:
    path = Path(path_value)
    if not path.is_absolute():
        path = REPO / path
    return path


def _artifact_exists(path_value: str) -> bool:
    return _resolve_artifact(path_value).is_file()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _lookup_field(root: dict, field: str) -> tuple[object | None, dict | None]:
    value: object | None = root
    parent: dict | None = None
    for part in field.split("."):
        if not isinstance(value, dict):
            return None, None
        parent = value
        value = value.get(part)
    return value, parent


def _hash_mismatch(path_value: str, expected_sha256: object) -> dict | None:
    if not isinstance(expected_sha256, str) or not expected_sha256:
        return None
    path = _resolve_artifact(path_value)
    if not path.is_file():
        return None
    actual = _sha256_file(path)
    if actual != expected_sha256:
        return {
            "path": path_value,
            "expected_sha256": expected_sha256,
            "actual_sha256": actual,
        }
    return None


def _receipt_gate(
    *,
    receipt_path: Path,
    expected_schema: str,
    needs: str,
    evidence_fields: list[str],
    required_artifacts: list[str] | None = None,
) -> dict:
    receipt, err = _load_json(receipt_path)
    if err == "missing":
        return {"status": "NOT_TESTED", "needs": needs, "receipt": str(receipt_path)}
    if err:
        return {"status": "FAIL", "receipt": str(receipt_path), "errors": [err]}

    errors = []
    if receipt.get("schema") != expected_schema:
        errors.append(f"schema must be {expected_schema}")

    status = receipt.get("status")
    if status not in {"PASS", "FAIL", "NOT_TESTED", "BLOCKED"}:
        errors.append("status must be one of PASS, FAIL, NOT_TESTED, BLOCKED")

    missing_artifacts = []
    hash_mismatches = []
    for field in required_artifacts or []:
        value, parent = _lookup_field(receipt, field)
        if not value or not _artifact_exists(str(value)):
            missing_artifacts.append(field)
            continue
        if parent:
            mismatch = _hash_mismatch(str(value), parent.get("sha256"))
            if mismatch:
                mismatch["field"] = field
                hash_mismatches.append(mismatch)

    if missing_artifacts:
        errors.append(f"missing referenced artifacts: {', '.join(missing_artifacts)}")
    if hash_mismatches:
        errors.append("referenced artifact hash mismatch")

    gate = {
        "status": "FAIL" if errors else status,
        "receipt": str(receipt_path),
        "source_commit": receipt.get("source_commit"),
    }
    if "source_state" in receipt:
        gate["source_state"] = receipt["source_state"]
    if errors:
        gate["errors"] = errors
    for field in evidence_fields:
        if field in receipt:
            gate[field] = receipt[field]
    if missing_artifacts:
        gate["missing_artifacts"] = missing_artifacts
    if hash_mismatches:
        gate["hash_mismatches"] = hash_mismatches
    return gate


def _missing_paths(paths: list[str]) -> list[str]:
    missing = []
    for path in paths:
        if not path or not _artifact_exists(path):
            missing.append(path)
    return missing


def _subgate(status: str, **fields) -> dict:
    return {"status": status, **fields}


def _corpus_subgates(receipt: dict) -> dict:
    section_corpus = receipt.get("section_corpus_manifest") or {}
    contact_sheet = receipt.get("contact_sheet") or {}
    subgates: dict[str, dict] = {}

    corpus_path_value = str(section_corpus.get("path") or "")
    if not corpus_path_value:
        subgates["corpus_current"] = _subgate(
            "NOT_TESTED",
            reason="section_corpus_manifest.path is missing",
        )
        subgates["section_crop_review_units"] = _subgate(
            "NOT_TESTED",
            reason="no segmented screenshot manifest is available",
        )
    else:
        corpus_path = _resolve_artifact(corpus_path_value)
        manifest, manifest_err = _load_json(corpus_path)
        corpus_errors = []
        if manifest_err:
            corpus_errors.append(manifest_err)
        else:
            if manifest.get("schema") != "grahama.responsive_section_corpus.v1":
                corpus_errors.append("manifest schema must be grahama.responsive_section_corpus.v1")
            mismatch = _hash_mismatch(corpus_path_value, section_corpus.get("sha256"))
            if mismatch:
                corpus_errors.append("manifest sha256 does not match receipt")
            counts = manifest.get("counts") or {}
            if int(counts.get("screenshots") or 0) <= 0:
                corpus_errors.append("manifest has no screenshots")
            if int(counts.get("sections") or 0) <= 0:
                corpus_errors.append("manifest has no sections")
            if int(counts.get("viewports") or 0) <= 0:
                corpus_errors.append("manifest has no viewports")
            if int(counts.get("failures") or 0) != 0:
                corpus_errors.append("manifest contains capture failures")
        if manifest_err:
            counts = {}
        else:
            counts = (manifest or {}).get("counts") or {}
        subgates["corpus_current"] = _subgate(
            "FAIL" if corpus_errors else "PASS",
            path=corpus_path_value,
            corpus_sha256=section_corpus.get("sha256"),
            counts=counts,
            errors=corpus_errors,
        )

        crop_errors = []
        if not manifest_err and manifest:
            note = " ".join(
                str(v or "")
                for v in (
                    manifest.get("review_note"),
                    section_corpus.get("review_note"),
                    section_corpus.get("segmentation"),
                )
            ).lower()
            if "section" not in note or "full-page" not in note:
                crop_errors.append("manifest must state that review units are section/page-state crops, not full-page primary evidence")
            screenshots = manifest.get("screenshots") or []
            for index, shot in enumerate(screenshots):
                if not isinstance(shot, dict):
                    crop_errors.append(f"screenshot {index + 1} is not an object")
                    continue
                for field in ("route", "viewport_id", "path", "dimensions", "intended_proof"):
                    if field not in shot:
                        crop_errors.append(f"screenshot {index + 1} missing {field}")
                intended = str(shot.get("intended_proof") or "").lower()
                if "full-page" not in intended and "whole-site" not in intended:
                    crop_errors.append(f"screenshot {index + 1} does not declare it is not a whole-page primary unit")
                path = str(shot.get("path") or "")
                if path and not _artifact_exists(path):
                    crop_errors.append(f"screenshot {index + 1} artifact missing: {path}")
        subgates["section_crop_review_units"] = _subgate(
            "FAIL" if crop_errors else ("NOT_TESTED" if manifest_err else "PASS"),
            screenshot_count=int(counts.get("screenshots") or 0),
            errors=crop_errors,
        )

    contact_path_value = str(contact_sheet.get("path") or "")
    contact_errors = []
    if not contact_path_value:
        subgates["contact_sheet_current"] = _subgate(
            "NOT_TESTED",
            reason="contact_sheet.path is missing",
        )
    else:
        if not _artifact_exists(contact_path_value):
            contact_errors.append("contact sheet artifact is missing")
        else:
            mismatch = _hash_mismatch(contact_path_value, contact_sheet.get("sha256"))
            if mismatch:
                contact_errors.append("contact sheet sha256 does not match receipt")
        subgates["contact_sheet_current"] = _subgate(
            "FAIL" if contact_errors else "PASS",
            path=contact_path_value,
            crop_count=contact_sheet.get("crop_count"),
            errors=contact_errors,
        )
    return subgates


def _rater_subgates(receipt: dict) -> tuple[dict, list[str]]:
    thresholds = receipt.get("thresholds") or {}
    aggregate = receipt.get("aggregate") or {}
    raters = receipt.get("raters") or []
    min_raters = int(thresholds.get("min_raters") or 5)
    usable_raters = [r for r in raters if isinstance(r, dict) and r.get("usable")]
    usable = int(aggregate.get("usable") or len(usable_raters))
    completed = usable >= min_raters and len(usable_raters) >= min_raters
    subgates: dict[str, dict] = {}
    parent_errors: list[str] = []

    subgates["rater_transport_ready"] = _subgate(
        "NOT_TESTED" if not usable_raters else "PASS",
        usable=usable,
        counted_raters=len(usable_raters),
        excluded_transport_blockers=len(receipt.get("excluded_transport_blockers") or []),
        reason="no current-corpus rater submissions are counted" if not usable_raters else None,
    )
    subgates["fresh_rater_set_complete"] = _subgate(
        "PASS" if completed else "NOT_TESTED",
        usable=usable,
        usable_records=len(usable_raters),
        required=min_raters,
        reason="fresh blind-rater set has not been run for the current segmented corpus" if not completed else None,
    )

    raw_errors = []
    for index, rater in enumerate(usable_raters):
        for field in ("output_path", "raw_output_path"):
            value = rater.get(field)
            if not value or not _artifact_exists(str(value)):
                raw_errors.append(f"usable rater {index + 1} missing {field}")
    raw_status = "FAIL" if raw_errors else ("PASS" if usable_raters else "NOT_TESTED")
    if raw_errors:
        parent_errors.extend(raw_errors)
    subgates["raw_outputs_preserved"] = _subgate(
        raw_status,
        usable_records=len(usable_raters),
        errors=raw_errors,
    )

    aggregate_keys = (
        "positive_classification",
        "competitor_swap_tension",
        "cross_screen_family",
        "generic_ai_template_primary",
    )
    aggregate_missing = [k for k in aggregate_keys if k not in aggregate]
    aggregate_status = "FAIL" if aggregate_missing and usable_raters else ("PASS" if usable_raters else "NOT_TESTED")
    subgates["aggregate_replay_ready"] = _subgate(
        aggregate_status,
        aggregate=aggregate,
        missing=aggregate_missing,
    )
    if aggregate_status == "FAIL":
        parent_errors.append(f"aggregate missing keys: {', '.join(aggregate_missing)}")

    threshold_errors = []
    checks = [
        (
            "positive_classification",
            int(aggregate.get("positive_classification") or 0),
            ">=",
            int(thresholds.get("min_positive_classification") or 0),
        ),
        (
            "competitor_swap_tension",
            int(aggregate.get("competitor_swap_tension") or 0),
            ">=",
            int(thresholds.get("min_competitor_swap_tension") or 0),
        ),
        (
            "cross_screen_family",
            int(aggregate.get("cross_screen_family") or 0),
            ">=",
            int(thresholds.get("min_cross_screen_family") or 0),
        ),
        (
            "generic_ai_template_primary",
            int(aggregate.get("generic_ai_template_primary") or 0),
            "<=",
            int(thresholds.get("max_generic_ai_template_primary") or 0),
        ),
    ]
    if completed:
        for name, actual, op, expected in checks:
            failed = actual < expected if op == ">=" else actual > expected
            if failed:
                threshold_errors.append(f"{name} {actual} does not satisfy {op} {expected}")
        if threshold_errors:
            parent_errors.extend(threshold_errors)
    subgates["thresholds_met"] = _subgate(
        "FAIL" if threshold_errors else ("PASS" if completed else "NOT_TESTED"),
        checks=[
            {"name": name, "actual": actual, "operator": op, "expected": expected}
            for name, actual, op, expected in checks
        ],
        errors=threshold_errors,
    )
    return subgates, parent_errors


def _g11_reason_and_next(gate: dict) -> tuple[str | None, dict | None]:
    subgates = gate.get("subgates") or {}
    failed = [name for name, subgate in subgates.items() if subgate.get("status") == "FAIL"]
    if failed:
        if "thresholds_met" in failed:
            return "blind_distinctiveness_thresholds_not_met", {
                "lane": "design_repair_or_rater_packet_audit",
                "command": "inspect raw rater outputs, then repair only the failed design invariant or receipt aggregate",
            }
        if "raw_outputs_preserved" in failed or "aggregate_replay_ready" in failed:
            return "blind_rater_output_integrity_failed", {
                "lane": "rater_receipt_repair",
                "command": "repair or quarantine the affected rater receipt records before counting them",
            }
        return "g11_input_artifacts_invalid", {
            "lane": "corpus_repair",
            "command": "regenerate section-crop corpus and contact sheet before rater submission",
        }
    fresh = subgates.get("fresh_rater_set_complete") or {}
    if fresh.get("status") != "PASS":
        return "fresh_blind_raters_not_run_for_current_segmented_corpus", {
            "lane": "rater_submission",
            "command": "submit current section-crop corpus to at least five fresh raters and preserve raw outputs",
            "required_usable_raters": fresh.get("required", 5),
            "current_usable_raters": fresh.get("usable", 0),
        }
    thresholds = subgates.get("thresholds_met") or {}
    if thresholds.get("status") != "PASS":
        return "blind_distinctiveness_thresholds_not_met", {
            "lane": "design_repair_or_rater_packet_audit",
            "command": "inspect threshold failures against raw rater outputs",
        }
    return None, None


def responsive_choreography_gate() -> dict:
    return _receipt_gate(
        receipt_path=DESIGN_ROUNDTABLE / "responsive-geometry.r1.json",
        expected_schema="monitor_website.responsive_geometry_check.v1",
        needs=(
            "site/design-roundtable/responsive-geometry.r1.json with rendered "
            "viewport checks and section_corpus_manifest.path"
        ),
        evidence_fields=["counts", "failures"],
        required_artifacts=["section_corpus_manifest.path"],
    )


def distinctiveness_blind_gate() -> dict:
    gate = _receipt_gate(
        receipt_path=DESIGN_ROUNDTABLE / "distinctiveness-blind.r1.json",
        expected_schema="grahama.distinctiveness_blind.v1",
        needs="site/design-roundtable/distinctiveness-blind.r1.json with blind-rater outputs",
        evidence_fields=[
            "thresholds",
            "aggregate",
            "section_corpus_manifest",
            "failure_signature",
            "blocked_by_systemic_failure",
            "excluded_transport_blockers",
            "does_not_prove",
        ],
        required_artifacts=["contact_sheet.path", "section_corpus_manifest.path"],
    )
    receipt, err = _load_json(DESIGN_ROUNDTABLE / "distinctiveness-blind.r1.json")
    if err or not receipt:
        return gate

    subgates = {}
    subgates.update(_corpus_subgates(receipt))
    rater_subgates, rater_errors = _rater_subgates(receipt)
    subgates.update(rater_subgates)
    gate["subgates"] = subgates
    gate["evidence_pipeline_status"] = "PASS" if all(
        subgates.get(name, {}).get("status") == "PASS"
        for name in (
            "corpus_current",
            "section_crop_review_units",
            "contact_sheet_current",
            "fresh_rater_set_complete",
            "raw_outputs_preserved",
            "aggregate_replay_ready",
        )
    ) else ("FAIL" if any(
        subgate.get("status") == "FAIL" for subgate in subgates.values()
    ) else "NOT_TESTED")
    gate["design_outcome_status"] = subgates.get("thresholds_met", {}).get("status", "NOT_TESTED")
    if rater_errors:
        gate.setdefault("errors", []).extend(rater_errors)

    if any(subgate.get("status") == "FAIL" for subgate in subgates.values()):
        gate["status"] = "FAIL"
    elif gate.get("status") == "PASS" and gate["design_outcome_status"] != "PASS":
        gate["status"] = "FAIL"
        gate.setdefault("errors", []).append("receipt claims PASS but G11 subgates are not all PASS")
    elif gate.get("status") != "PASS":
        gate["status"] = gate.get("status") or "NOT_TESTED"

    reason_code, next_action = _g11_reason_and_next(gate)
    if reason_code:
        gate["reason_code"] = reason_code
        gate["next_action"] = next_action

    if gate.get("status") != "PASS":
        return gate

    errors = []
    thresholds = receipt.get("thresholds") or {}
    aggregate = receipt.get("aggregate") or {}
    raters = receipt.get("raters") or []
    min_raters = int(thresholds.get("min_raters") or 5)
    if int(aggregate.get("usable") or 0) < min_raters:
        errors.append(f"PASS requires aggregate.usable >= {min_raters}")
    if len([r for r in raters if isinstance(r, dict) and r.get("usable")]) < min_raters:
        errors.append(f"PASS requires at least {min_raters} usable rater records")
    if int(aggregate.get("positive_classification") or 0) < int(thresholds.get("min_positive_classification") or 0):
        errors.append("PASS does not meet positive classification threshold")
    if int(aggregate.get("competitor_swap_tension") or 0) < int(thresholds.get("min_competitor_swap_tension") or 0):
        errors.append("PASS does not meet competitor-swap tension threshold")
    if int(aggregate.get("cross_screen_family") or 0) < int(thresholds.get("min_cross_screen_family") or 0):
        errors.append("PASS does not meet cross-screen-family threshold")
    if int(aggregate.get("generic_ai_template_primary") or 0) > int(thresholds.get("max_generic_ai_template_primary") or 0):
        errors.append("PASS exceeds generic AI/template classification threshold")
    for index, rater in enumerate(raters):
        if not isinstance(rater, dict) or not rater.get("usable"):
            continue
        for field in ("output_path", "raw_output_path"):
            value = rater.get(field)
            if not value or not _artifact_exists(str(value)):
                errors.append(f"usable rater {index + 1} missing {field}")
    if errors:
        gate["status"] = "FAIL"
        gate.setdefault("errors", []).extend(errors)
    return gate


def craft_integrity_render_gate() -> dict:
    gate = _receipt_gate(
        receipt_path=DESIGN_ROUNDTABLE / "craft-integrity.r1.json",
        expected_schema="grahama.craft_integrity.v1",
        needs="site/design-roundtable/craft-integrity.r1.json with rendered screenshot hashes",
        evidence_fields=[
            "visual_assets_check",
            "effects_check",
            "section_corpus_manifest",
            "rendered_screens",
            "prohibited_findings",
            "does_not_prove",
        ],
        required_artifacts=["section_corpus_manifest.path"],
    )
    receipt, err = _load_json(DESIGN_ROUNDTABLE / "craft-integrity.r1.json")
    if err or not receipt:
        return gate

    missing = []
    hash_mismatches = []
    for screen in receipt.get("rendered_screens", []):
        if not isinstance(screen, dict):
            continue
        path = str(screen.get("path") or "")
        if not path or not _artifact_exists(path):
            missing.append(path)
            continue
        mismatch = _hash_mismatch(path, screen.get("sha256"))
        if mismatch:
            hash_mismatches.append(mismatch)
    if missing:
        gate["status"] = "FAIL"
        gate.setdefault("errors", []).append("missing rendered screenshot artifacts")
        gate["missing_artifacts"] = missing
    if hash_mismatches:
        gate["status"] = "FAIL"
        gate.setdefault("errors", []).append("rendered screenshot hash mismatch")
        gate["hash_mismatches"] = hash_mismatches
    return gate


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contract", default=str(SITE / "design-world.yml"))
    ap.add_argument("--css-dir", default=str(SITE / "app"))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    contract_path = Path(a.contract)
    result = {"schema": "monitor_website.design_world_check.v1",
              "contract": str(contract_path), "gates": {}}
    if not contract_path.is_file():
        result["gates"]["contract"] = {"status": "FAIL", "errors": ["contract file missing"]}
        result["status"] = "FAIL"
        print(json.dumps(result, indent=2)); return 1

    c = _load_yaml(contract_path)
    cerrs = validate_contract(c)
    result["gates"]["contract"] = {"status": "PASS" if not cerrs else "FAIL", "errors": cerrs}

    css_files = sorted(Path(a.css_dir).glob("*.css"))
    viol = scan_mono_on_human_labels(css_files, c.get("machine_output_selectors", []))
    result["gates"]["no_mono_on_human_labels"] = {
        "status": "PASS" if not viol else "FAIL",
        "violations": viol,
        "css_files_scanned": [f.name for f in css_files],
    }
    result["gates"]["responsive_choreography"] = responsive_choreography_gate()
    result["gates"]["distinctiveness_blind"] = distinctiveness_blind_gate()
    result["gates"]["craft_integrity_render"] = craft_integrity_render_gate()

    statuses = [g["status"] for g in result["gates"].values()]
    if "FAIL" in statuses:
        result["status"] = "FAIL"
    elif "NOT_TESTED" in statuses:
        result["status"] = "NOT_TESTED"   # never PASS without rendered/blind evidence
    else:
        result["status"] = "PASS"
    print(json.dumps(result, indent=2))
    return 0 if result["status"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
