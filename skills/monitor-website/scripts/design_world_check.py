#!/usr/bin/env python3
"""design-world-check (#1337): validate grahama.co's visual-world contract and
scan for deterministically-checkable AI-template residue. Returns NOT_TESTED
rather than PASS when rendered/blind evidence is absent — prose is not proof.
"""
from __future__ import annotations
import argparse, json, re, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SITE = REPO / "site"


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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contract", default=str(SITE / "design-world.yml"))
    ap.add_argument("--css-dir", default=str(SITE / "app"))
    ap.add_argument("--font-receipt", default=str(SITE / "design-roundtable" / "font-receipt.r1.json"))
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
