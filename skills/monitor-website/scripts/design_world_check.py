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
    if err or not receipt or gate.get("status") != "PASS":
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
