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
    ap.add_argument("--visual-world-brief", default=str(SITE / "design-roundtable" / "visual-world-brief.r1.yaml"))
    ap.add_argument("--territory-selection", default=str(SITE / "design-roundtable" / "territory-selection.r1.json"))
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
    result["gates"].update(validate_pr1_source_lock(c, Path(a.visual_world_brief), Path(a.territory_selection)))

    css_files = sorted(Path(a.css_dir).glob("*.css"))
    viol = scan_mono_on_human_labels(css_files, c.get("machine_output_selectors", []))
    result["gates"]["no_mono_on_human_labels"] = {
        "status": "PASS" if not viol else "FAIL",
        "violations": viol,
        "css_files_scanned": [f.name for f in css_files],
    }
    result["gates"]["font_receipt"] = validate_font_receipt(Path(a.font_receipt))
    # Gates that require evidence this command cannot supply.
    for g in ("responsive_choreography", "distinctiveness_blind", "craft_integrity_render"):
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
