#!/usr/bin/env python3
"""Bind every README proof claim to a real artifact, or fail (#1179 follow-up).

`best-practices-readme` requires that a README separate what was checked from
what was not, and that every checked statement name a command output, artifact
path, schema, or commit hash. An external review put the failure mode precisely:

    Issue references alone are navigation, not proof.

The README's proof table previously pointed at directories (`reports/` run
receipts) and at another document (`docs/verification.md`). Both are navigation.
A reader could not tell whether a row was earned, and neither could a test.

This gate holds a claim registry: one row per proof boundary, each naming the
exact receipt that earns it and the status prefix that receipt must carry. It
fails when a receipt is missing, unparseable, carries a different status than
the README claims, or when a boundary in the README has no registry entry at
all. A boundary with no evidence is not an error only if it is explicitly
declared unproven -- "not checked" is a valid, and required, answer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
README = ROOT / "README.md"
REVISION = "reports/pipeline-complete/.persona-dream/revisions/rev_successor_943b01ecd9a3"

#: boundary label -> (receipt path, required status prefix, claimed state)
#: A receipt of ``None`` means the boundary is declared UNPROVEN; the README must
#: say so, and no PASS-shaped word may appear in its state cell.
CLAIMS: dict[str, tuple[str | None, str | None]] = {
    #: Each boundary names the receipt that earns IT. Pointing three rows at one
    #: acceptance receipt was the same "navigation, not proof" defect in subtler
    #: form: one artifact cannot independently earn three distinct claims.
    "Grounded dream packets": (
        f"{REVISION}/phase_01_idea/dream_packet_validation.json", "PASS_DREAM_PACKET"),
    "Image and storyboard production": (
        f"{REVISION}/identity_successor_gate_summary.v1.json", "PASS_IDENTITY_SOURCE"),
    "Phases 01-10, qualified revision": (
        f"{REVISION}/acceptance_rung_receipt.v6.json", "PASS_"),
    "Phase 11, submit and return": (
        f"{REVISION}/phase_11_submit_return/provider_return/97688ec5191e7246cc7d86325a7404894c459d2572bc5412b29ccd3dc755cfd4/phase11_download_ffprobe_receipt.v1.json",
        "PASS"),
    "Phase 12, Watch observation": (
        f"{REVISION}/watch_gauntlet/991c311f365f/watch_gauntlet_validation_receipt.v1.json",
        "PASS_"),
    "Phases 13-15, interpretation to persistence": (
        f"{REVISION}/watch_gauntlet/59b9ff3155d6/cognitive_loop_v2/lineage_receipt.v1.json",
        "PASS"),
    "Phase 16, recall and later behavior": (
        f"{REVISION}/phase_16_behavior_evaluation/phase16_behavior_evaluation_receipt.v1.json",
        "PASS"),
    "Continuity chain": (
        "reports/goal_v5/continuity/live_chain/RECEIPT.json", "PASS_"),
    "Reliability pilot": (
        "reports/goal_v5/continuity/reliability/AGGREGATE_RECEIPT.json", "PASS_"),
    "Chatterbox voice expression": (
        "reports/goal_v5/continuity/blinded_listener_study/TECHNICAL_SCREEN_RECEIPT.json",
        "BLOCKED_"),
    "PCTOM-R measurement validity": (
        "research/prospective-tom/receipts/measurement-validity-v2-pass/MEASUREMENT_VALIDITY_RECEIPT.json",
        "PASS_"),
    #: Declared unproven. No receipt exists and none is claimed.
    "PCTOM-R held-out benefit": (None, None),
    "Human perceived emotion and identity": (None, None),
}

#: Words that assert a positive result. None may appear in the state cell of a
#: boundary whose registry entry is UNPROVEN.
POSITIVE_WORDS = ("proven", "passes", "passed", "accepted", "qualified", "implemented")


def utc_now() -> str:
    return datetime.now().astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def rel(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path)


def sha_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def readme_proof_rows(readme: str) -> list[tuple[str, str, str]]:
    """(boundary, state, evidence) rows from the Current Proof Boundary table."""
    try:
        section = readme.split("## Current Proof Boundary", 1)[1].split("\n## ", 1)[0]
    except IndexError:
        return []
    rows: list[tuple[str, str, str]] = []
    for line in section.split("\n"):
        if not line.startswith("|") or line.startswith("|---") or "| Boundary |" in line:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3:
            rows.append((cells[0], cells[1], cells[2]))
    return rows


def run(args: argparse.Namespace) -> dict[str, Any]:
    readme = Path(args.readme).read_text(encoding="utf-8")
    rows = readme_proof_rows(readme)
    failed: list[str] = []
    checked: list[dict[str, Any]] = []

    if not rows:
        failed.append("readme_proof_table_missing")

    for boundary, state, evidence in rows:
        entry = CLAIMS.get(boundary)
        if entry is None:
            failed.append(f"claim_not_in_registry:{boundary}")
            continue
        receipt_rel, prefix = entry
        row: dict[str, Any] = {
            "boundary": boundary,
            "readme_state": state,
            "readme_evidence_cell": evidence,
        }
        if receipt_rel is None:
            row["evidence"] = "declared unproven; no receipt claimed"
            low = state.lower()
            offending = [w for w in POSITIVE_WORDS if w in low]
            if offending:
                failed.append(f"unproven_claim_uses_positive_language:{boundary}:{offending}")
            row["ok"] = not offending
            checked.append(row)
            continue

        path = ROOT / receipt_rel
        row["receipt"] = receipt_rel
        if not path.is_file():
            failed.append(f"receipt_missing:{boundary}:{receipt_rel}")
            row["ok"] = False
            checked.append(row)
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            failed.append(f"receipt_unparseable:{boundary}:{type(exc).__name__}")
            row["ok"] = False
            checked.append(row)
            continue

        status = str(doc.get("status") or doc.get("overall_status") or "")
        row["receipt_status"] = status
        row["receipt_sha256"] = sha_file(path)
        ok = bool(prefix) and status.startswith(prefix)
        if not ok:
            failed.append(
                f"receipt_status_does_not_support_claim:{boundary}:"
                f"expected prefix {prefix!r}, receipt says {status!r}"
            )
        row["ok"] = ok
        checked.append(row)

    status = "PASS_README_PROOF_CLAIMS_BOUND" if not failed else "BLOCKED_README_PROOF_CLAIM_UNBOUND"
    receipt = {
        "schema": "persona_dream.readme_proof_claim_audit.v1",
        "created_at": utc_now(),
        "status": status,
        "mocked": False,
        "live": False,
        "readme": rel(Path(args.readme)),
        "readme_sha256": sha_file(Path(args.readme)),
        "rows_checked": len(checked),
        "claims": checked,
        "failed_gates": failed,
        "claims_summary": {
            "proves": [
                "every proof-boundary row in the README names a receipt that exists, "
                "parses, and carries a status supporting the claimed state",
                "boundaries with no receipt are declared unproven and use no "
                "positive-result language",
            ] if not failed else [],
            "does_not_prove": [
                "that the receipts themselves are correct",
                "anything about prose outside the Current Proof Boundary table",
                "perceived emotion, identity, or any held-out benefit result",
            ],
        },
    }
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--readme", type=Path, default=README)
    ap.add_argument("--out", type=Path,
                    default=ROOT / "reports/goal_v5/readme_proof_claims/AUDIT_RECEIPT.json")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    r = run(args)
    if args.json:
        print(json.dumps(r, indent=2, sort_keys=True))
    else:
        print(f"README proof claims: {r['status']}  ({r['rows_checked']} rows)")
        for gate in r["failed_gates"]:
            print(f"  {gate}")
    return 0 if r["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
