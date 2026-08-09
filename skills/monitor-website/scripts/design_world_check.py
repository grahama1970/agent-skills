#!/usr/bin/env python3
"""design-world-check (#1337): validate grahama.co's visual-world contract and
scan for deterministically-checkable AI-template residue. Returns NOT_TESTED
rather than PASS when rendered/blind evidence is absent — prose is not proof.
"""
from __future__ import annotations
import argparse, hashlib, json, re, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SITE = REPO / "site"


def _load_yaml(p: Path):
    import yaml
    return yaml.safe_load(p.read_text())


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _is_sha256(s: object) -> bool:
    return bool(isinstance(s, str) and re.fullmatch(r"[0-9a-f]{64}", s))


def _repo_path(value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else REPO / p


def validate_contract(c: dict) -> list[str]:
    errs = []
    if c.get("schema") != "grahama.design_world.v1":
        errs.append("contract: schema must be grahama.design_world.v1")
    if not str(c.get("premise", "")).strip():
        errs.append("contract: premise missing")
    if not str(c.get("responsive_geometry_receipt", "")).strip():
        errs.append("contract: responsive_geometry_receipt missing")
    if not str(c.get("craft_integrity_receipt", "")).strip():
        errs.append("contract: craft_integrity_receipt missing")
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


def validate_font_receipt(receipt_path: Path) -> dict:
    if not receipt_path.is_file():
        return {
            "status": "NOT_TESTED",
            "needs": f"font receipt missing: {receipt_path}",
        }
    validator = REPO / "skills" / "best-practices-font" / "scripts" / "validate_font_receipt.py"
    if not validator.is_file():
        return {
            "status": "FAIL",
            "errors": [f"font receipt validator missing: {validator}"],
        }
    proc = subprocess.run(
        ["python3", str(validator), str(receipt_path)],
        cwd=str(REPO),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if proc.returncode == 0:
        return {
            "status": "PASS",
            "receipt": str(receipt_path),
            "validator_output": proc.stdout.strip(),
        }
    return {
        "status": "FAIL",
        "receipt": str(receipt_path),
        "validator_output": proc.stdout.strip(),
    }


def validate_responsive_geometry(receipt_path: Path) -> dict:
    required_routes = {
        "/",
        "/explore.html",
        "/how-proof-works.html",
        "/ledger.html",
        "/capabilities.html",
        "/resume.html",
    }
    required_viewports = {
        "phone-390",
        "phone-430",
        "tablet-768",
        "desktop-1366",
        "desktop-1440",
    }
    if not receipt_path.is_file():
        return {
            "status": "NOT_TESTED",
            "needs": f"responsive geometry receipt missing: {receipt_path}",
        }
    try:
        receipt = json.loads(receipt_path.read_text())
    except json.JSONDecodeError as exc:
        return {
            "status": "FAIL",
            "receipt": str(receipt_path),
            "errors": [f"responsive geometry receipt is not JSON: {exc}"],
        }

    errors: list[str] = []
    if receipt.get("schema") != "monitor_website.responsive_geometry_check.v1":
        errors.append("schema must be monitor_website.responsive_geometry_check.v1")
    if receipt.get("status") != "PASS":
        errors.append("receipt status must be PASS")
    counts = receipt.get("counts") or {}
    expected_counts = {"routes": 6, "viewports": 5, "checks": 30, "failures": 0}
    for key, expected in expected_counts.items():
        if counts.get(key) != expected:
            errors.append(f"counts.{key} must be {expected}")
    failures = receipt.get("failures") or []
    if failures:
        errors.append("failures must be empty")
    results = receipt.get("results") or []
    if len(results) != 30:
        errors.append("results must contain 30 route/viewport records")

    seen_routes = {r.get("route") for r in results}
    seen_viewports = {r.get("viewport") for r in results}
    if seen_routes != required_routes:
        errors.append(f"routes must match required set: {sorted(required_routes)}")
    if seen_viewports != required_viewports:
        errors.append(f"viewports must match required set: {sorted(required_viewports)}")

    for i, record in enumerate(results):
        label = f"result[{i}] {record.get('route')} {record.get('viewport')}"
        width = record.get("width")
        status = record.get("status")
        if record.get("ok") is not True:
            errors.append(f"{label}: ok must be true")
        if not isinstance(status, int) or not (200 <= status < 400):
            errors.append(f"{label}: status must be 2xx/3xx")
        for key in ("scrollWidth", "bodyScrollWidth"):
            value = record.get(key)
            if not isinstance(width, int) or not isinstance(value, int) or value > width:
                errors.append(f"{label}: {key} must be <= width")
        if record.get("overflowPx") != 0 or record.get("bodyOverflowPx") != 0:
            errors.append(f"{label}: document overflow must be zero")
        if record.get("offscreenActions"):
            errors.append(f"{label}: offscreenActions must be empty")

    if errors:
        return {
            "status": "FAIL",
            "receipt": str(receipt_path),
            "errors": errors,
        }
    return {
        "status": "PASS",
        "receipt": str(receipt_path),
        "counts": counts,
        "does_not_prove": [
            "200% text zoom reading order",
            "WCAG contrast or keyboard completion",
            "performance budgets",
            "blind distinctiveness",
            "craft/material fidelity",
        ],
    }


def validate_craft_integrity(receipt_path: Path) -> dict:
    if not receipt_path.is_file():
        return {
            "status": "NOT_TESTED",
            "needs": f"craft integrity receipt missing: {receipt_path}",
        }
    try:
        receipt = json.loads(receipt_path.read_text())
    except json.JSONDecodeError as exc:
        return {
            "status": "FAIL",
            "receipt": str(receipt_path),
            "errors": [f"craft integrity receipt is not JSON: {exc}"],
        }

    errors: list[str] = []
    if receipt.get("schema") != "grahama.craft_integrity.v1":
        errors.append("schema must be grahama.craft_integrity.v1")
    if receipt.get("status") != "PASS":
        errors.append("receipt status must be PASS")
    if (receipt.get("visual_assets_check") or {}).get("status") != "PASS":
        errors.append("visual_assets_check.status must be PASS")
    if (receipt.get("effects_check") or {}).get("status") != "PASS":
        errors.append("effects_check.status must be PASS")
    if receipt.get("prohibited_findings"):
        errors.append("prohibited_findings must be empty")

    visual_counts = (receipt.get("visual_assets_check") or {}).get("counts") or {}
    if visual_counts.get("registered_assets", 0) < 1:
        errors.append("visual_assets_check.counts.registered_assets must be positive")
    if visual_counts.get("public_visuals") != visual_counts.get("registered_assets"):
        errors.append("visual asset counts must show every public visual is registered")
    if visual_counts.get("evidence_assets", 0) < 1:
        errors.append("at least one evidence asset is required")
    effects_counts = (receipt.get("effects_check") or {}).get("counts") or {}
    if effects_counts.get("registered_effects", 0) < 1:
        errors.append("effects_check.counts.registered_effects must be positive")
    if effects_counts.get("removed_public_effects", 0) < 1:
        errors.append("effects_check.counts.removed_public_effects must be positive")

    screens = receipt.get("rendered_screens") or []
    required_ids = {"home-desktop", "ledger-tablet", "explore-desktop"}
    seen_ids = {s.get("id") for s in screens}
    if seen_ids != required_ids:
        errors.append(f"rendered_screens ids must match {sorted(required_ids)}")
    for screen in screens:
        label = screen.get("id", "<missing-id>")
        path_value = screen.get("path")
        digest = screen.get("sha256")
        if not path_value:
            errors.append(f"{label}: path missing")
            continue
        p = _repo_path(str(path_value))
        if not p.is_file():
            errors.append(f"{label}: screenshot missing: {path_value}")
            continue
        if not _is_sha256(digest):
            errors.append(f"{label}: invalid sha256")
        elif _sha256(p) != digest:
            errors.append(f"{label}: screenshot digest mismatch")
        if screen.get("status") != 200:
            errors.append(f"{label}: HTTP status must be 200")
        metrics = screen.get("metrics") or {}
        width = screen.get("width")
        if not isinstance(width, int):
            errors.append(f"{label}: width must be an integer")
        for key in ("scrollWidth", "bodyScrollWidth"):
            value = metrics.get(key)
            if not isinstance(value, int) or not isinstance(width, int) or value > width:
                errors.append(f"{label}: {key} must be <= width")

    if errors:
        return {
            "status": "FAIL",
            "receipt": str(receipt_path),
            "errors": errors,
        }
    return {
        "status": "PASS",
        "receipt": str(receipt_path),
        "rendered_screens": len(screens),
        "does_not_prove": [
            "blind distinctiveness",
            "independent Impeccable finish review",
            "WCAG keyboard/contrast completion",
            "performance budgets",
        ],
    }


def validate_pr1_source_lock(contract: dict, brief_path: Path, selection_path: Path) -> dict[str, dict]:
    gates: dict[str, dict] = {}
    provenance_errors: list[str] = []
    territory_errors: list[str] = []
    premise_errors: list[str] = []

    if not brief_path.is_file():
        provenance_errors.append(f"visual-world brief missing: {brief_path}")
        brief = {}
    else:
        brief = _load_yaml(brief_path) or {}

    if not selection_path.is_file():
        territory_errors.append(f"territory selection missing: {selection_path}")
        selection = {}
    else:
        selection = json.loads(selection_path.read_text())

    contract_sha = contract.get("source_bundle_sha256")
    brief_sha = (brief.get("provenance") or {}).get("source_bundle_sha256")
    if not _is_sha256(contract_sha):
        provenance_errors.append("contract: source_bundle_sha256 must be a 64-char sha256")
    if not _is_sha256(brief_sha):
        provenance_errors.append("brief: provenance.source_bundle_sha256 must be a 64-char sha256")
    if _is_sha256(contract_sha) and _is_sha256(brief_sha) and contract_sha != brief_sha:
        provenance_errors.append("contract and brief source_bundle_sha256 differ")
    if brief.get("status") in {None, "", "PROVISIONAL_NOT_APPROVED"}:
        provenance_errors.append("brief status remains provisional or empty")
    for src in (brief.get("provenance") or {}).get("authoritative_sources", []):
        loc = str(src.get("location", ""))
        if "NOT_ESTABLISHED" in loc or not loc:
            provenance_errors.append(f"source {src.get('source_id', '<unknown>')}: location incomplete")

    territories = brief.get("concept_territories") or []
    if len(territories) != 3:
        territory_errors.append("brief must contain exactly three concept territories")
    seen_dimensions = {
        "semantic_premise": set(),
        "composition_model": set(),
        "primary_motif": set(),
    }
    for territory in territories:
        tid = territory.get("id", "<unknown>")
        for dim in seen_dimensions:
            value = str(territory.get(dim, "")).strip()
            if not value:
                territory_errors.append(f"{tid}: {dim} missing")
            seen_dimensions[dim].add(value)
        artifacts = territory.get("keyframe_artifacts") or []
        viewports = {a.get("viewport") for a in artifacts}
        if not {"desktop", "mobile"}.issubset(viewports):
            territory_errors.append(f"{tid}: desktop and mobile keyframe artifacts required")
        for artifact in artifacts:
            path_value = artifact.get("path")
            digest = artifact.get("sha256")
            if not path_value:
                territory_errors.append(f"{tid}: artifact path missing")
                continue
            p = _repo_path(str(path_value))
            if not p.is_file():
                territory_errors.append(f"{tid}: artifact missing: {path_value}")
                continue
            if not _is_sha256(digest):
                territory_errors.append(f"{tid}: artifact {path_value} has invalid sha256")
            elif _sha256(p) != digest:
                territory_errors.append(f"{tid}: artifact digest mismatch: {path_value}")
    for dim, values in seen_dimensions.items():
        if len(values) != 3:
            territory_errors.append(f"territories are not separated by {dim}")

    constraints = selection.get("board_constraints") or {}
    for key in ("grayscale", "logo_removed", "brand_name_removed", "identical_claims_evidence_and_judgments"):
        if constraints.get(key) is not True:
            territory_errors.append(f"selection board_constraints.{key} must be true")
    if constraints.get("territory_specific_invented_copy") is not False:
        territory_errors.append("selection board_constraints.territory_specific_invented_copy must be false")
    selected = selection.get("selected_territory_id")
    if selected != (brief.get("selection") or {}).get("selected_territory_id"):
        territory_errors.append("selected territory differs between brief and selection record")
    selection_territories = selection.get("territories") or []
    if {t.get("id") for t in selection_territories} != {t.get("id") for t in territories}:
        territory_errors.append("selection record territory ids must match brief territory ids")
    rejected = selection.get("rejected_territories") or []
    if len(rejected) < 2:
        territory_errors.append("selection record must include rejected alternatives")

    if not str(contract.get("premise", "")).strip():
        premise_errors.append("contract premise missing")
    narrative = brief.get("narrative_premise") or {}
    if not str(narrative.get("sentence", "")).strip():
        premise_errors.append("brief narrative premise missing")
    if not narrative.get("source_claim_ids"):
        premise_errors.append("brief narrative premise must cite source_claim_ids")
    if not selection.get("selection_rationale"):
        premise_errors.append("selection rationale missing")
    if "NOT_TESTED" in json.dumps(brief.get("selection") or {}):
        premise_errors.append("brief selection still contains NOT_TESTED placeholders")

    gates["provenance_source_lock"] = {
        "status": "PASS" if not provenance_errors else "FAIL",
        "errors": provenance_errors,
        "brief": str(brief_path),
        "selection": str(selection_path),
    }
    gates["territory_separation"] = {
        "status": "PASS" if not territory_errors else "FAIL",
        "errors": territory_errors,
        "territory_count": len(territories),
    }
    gates["narrative_premise"] = {
        "status": "PASS" if not premise_errors else "FAIL",
        "errors": premise_errors,
        "selected_territory_id": selected,
    }
    return gates


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contract", default=str(SITE / "design-world.yml"))
    ap.add_argument("--css-dir", default=str(SITE / "app"))
    ap.add_argument("--font-receipt", default=str(SITE / "design-roundtable" / "font-receipt.r1.json"))
    ap.add_argument("--responsive-geometry", default=None)
    ap.add_argument("--craft-integrity", default=None)
    ap.add_argument("--visual-world-brief", default=str(SITE / "design-roundtable" / "visual-world-brief.r1.yaml"))
    ap.add_argument("--territory-selection", default=str(SITE / "design-roundtable" / "territory-selection.r1.json"))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    contract_path = _repo_path(a.contract)
    result = {"schema": "monitor_website.design_world_check.v1",
              "contract": str(contract_path), "gates": {}}
    if not contract_path.is_file():
        result["gates"]["contract"] = {"status": "FAIL", "errors": ["contract file missing"]}
        result["status"] = "FAIL"
        print(json.dumps(result, indent=2)); return 1

    c = _load_yaml(contract_path)
    cerrs = validate_contract(c)
    result["gates"]["contract"] = {"status": "PASS" if not cerrs else "FAIL", "errors": cerrs}
    result["gates"].update(validate_pr1_source_lock(c, _repo_path(a.visual_world_brief), _repo_path(a.territory_selection)))

    css_files = sorted(_repo_path(a.css_dir).glob("*.css"))
    viol = scan_mono_on_human_labels(css_files, c.get("machine_output_selectors", []))
    result["gates"]["no_mono_on_human_labels"] = {
        "status": "PASS" if not viol else "FAIL",
        "violations": viol,
        "css_files_scanned": [f.name for f in css_files],
    }
    result["gates"]["font_receipt"] = validate_font_receipt(_repo_path(a.font_receipt))
    responsive_geometry = (
        a.responsive_geometry
        or c.get("responsive_geometry_receipt")
        or str(SITE / "design-roundtable" / "responsive-geometry.r1.json")
    )
    result["gates"]["responsive_choreography"] = validate_responsive_geometry(_repo_path(responsive_geometry))
    craft_integrity = (
        a.craft_integrity
        or c.get("craft_integrity_receipt")
        or str(SITE / "design-roundtable" / "craft-integrity.r1.json")
    )
    result["gates"]["craft_integrity_render"] = validate_craft_integrity(_repo_path(craft_integrity))
    # Gates that require evidence this command cannot supply.
    for g in ("distinctiveness_blind",):
        result["gates"][g] = {"status": "NOT_TESTED",
                              "needs": "rendered screenshot corpus / blind-rater outputs (#1343)"}

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
