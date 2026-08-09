#!/usr/bin/env python3
"""Capture real evidence artifacts for the on-page Receipts section.

Emits site/artifacts.json. Every entry is captured from a real source —
a live audit run, an actual tau node receipt from the run that designed
this site, and the inventory provenance — with SHA-256 of the source
material so the excerpts are checkable. Nothing here is authored prose.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REQUIRED_IDS = ("roundtable-receipt", "live-audit", "inventory-provenance")
LOCKED_ROUNDTABLE_DIGEST = "e697899eb7dcc021"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unavailable(
    artifact_id: str,
    title: str,
    source: str,
    reason: str,
    *,
    proves: str,
    does_not_prove: str,
) -> dict:
    return {
        "id": artifact_id,
        "title": title,
        "capture_status": "unavailable",
        "source": source,
        "digest": None,
        "judgment": "UNAVAILABLE",
        "proves": proves,
        "does_not_prove": does_not_prove,
        "caption": reason,
        "body": "",
        "unavailable_reason": reason,
    }


def roundtable_receipt() -> dict:
    proof_path = REPO / "site/proof-explainer.json"
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    stage = next((s for s in proof["stages"] if s.get("name") == "Captured evidence"), None)
    if not stage:
        return unavailable(
            "roundtable-receipt",
            "tau node receipt — the run that designed this site",
            str(proof_path.relative_to(REPO)),
            "proof-explainer.json has no Captured evidence stage",
            proves="No roundtable receipt was captured.",
            does_not_prove="That the roundtable run occurred or answered live.",
        )
    if stage.get("digest") != LOCKED_ROUNDTABLE_DIGEST:
        raise SystemExit(
            "roundtable receipt digest drift: "
            f"{stage.get('digest')} != {LOCKED_ROUNDTABLE_DIGEST}"
        )
    excerpt = {
        "run": proof["run"],
        "stage": stage["name"],
        "artifact": stage["artifact"],
        "digest": stage["digest"],
        "excerpt": stage["excerpt"],
        "invariant": stage["invariant"],
    }
    return {
        "id": "roundtable-receipt",
        "title": "tau node receipt — the run that designed this site",
        "capture_status": "captured",
        "source": str(proof_path.relative_to(REPO)),
        "digest": f"sha256:{stage['digest']}",
        "judgment": "PREFLIGHT: PASS",
        "proves": stage["proves"],
        "does_not_prove": stage["not"],
        "caption": (
            f"{stage['artifact']} · {proof['run']} · "
            f"sha256 {stage['digest']}…"
        ),
        "body": json.dumps(excerpt, indent=2),
    }


def live_audit_receipt() -> dict:
    audit = subprocess.run(
        [
            str(REPO / "skills/monitor-website/run.sh"),
            "audit",
            "--ignore-surface",
            "artifacts.json",
            "--json",
        ],
        capture_output=True,
        text=True,
    )
    source = "skills/monitor-website/run.sh audit --ignore-surface artifacts.json --json"
    if audit.returncode != 0:
        try:
            failed = json.loads(audit.stdout)
            reason = json.dumps(
                {
                    "drift": failed.get("drift", []),
                    "live": failed.get("live", {}),
                },
                indent=2,
            )
        except json.JSONDecodeError:
            reason = (audit.stdout or audit.stderr or "audit exited nonzero").strip()[-800:]
        return unavailable(
            "live-audit",
            "monitor-website audit — this page, checked against the repo",
            source,
            reason,
            proves="No audit receipt was captured.",
            does_not_prove="That local generated surfaces agreed or public endpoints responded.",
        )
    d = json.loads(audit.stdout)
    live = d.get("live", {})
    live_ok = sum(1 for v in live.values() if v.get("ok"))
    compact = {"ok": d["ok"], "drift": d["drift"], "live": live}
    return {
        "id": "live-audit",
        "title": "monitor-website audit — this page, checked against the repo",
        "capture_status": "captured",
        "source": source,
        "digest": f"sha256:{hashlib.sha256(audit.stdout.encode()).hexdigest()}",
        "judgment": f"LOCAL DRIFT: {len(d['drift'])} · PUBLIC ENDPOINTS: {live_ok}/{len(live)}",
        "proves": (
            "The checkout's generated surfaces agreed with their source files, "
            "excluding artifacts.json while it was being regenerated, and the "
            "named public endpoints returned expected markers at capture time."
        ),
        "does_not_prove": (
            "That the deployed HTML was built from this exact commit, or that "
            "every interaction works."
        ),
        "caption": source,
        "body": json.dumps(compact, indent=2),
    }


def inventory_receipt() -> dict:
    inv_path = REPO / "site/inventory.json"
    inv = json.loads(inv_path.read_text(encoding="utf-8"))
    return {
        "id": "inventory-provenance",
        "title": "inventory provenance — where the numbers come from",
        "capture_status": "captured",
        "source": str(inv_path.relative_to(REPO)),
        "digest": f"sha256:{sha(inv_path)}",
        "judgment": f"BUILD: {inv['commit']}",
        "proves": "The numbers above came from checked source state, not marketing copy.",
        "does_not_prove": "That every skill is complete, useful, or production-ready.",
        "caption": f"site/inventory.json · sha256 {sha(inv_path)[:16]}…",
        "body": json.dumps(
            {
                "generator": inv["generator"],
                "commit": inv["commit"],
                "as_of": inv["as_of"],
                "stats": inv["stats"],
            },
            indent=2,
        ),
    }


def main() -> None:
    commit = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=REPO, text=True
    ).strip()
    as_of = subprocess.check_output(
        ["git", "show", "-s", "--format=%cs", "HEAD"], cwd=REPO, text=True
    ).strip()

    artifacts = [roundtable_receipt(), live_audit_receipt(), inventory_receipt()]
    got_ids = tuple(a["id"] for a in artifacts)
    if got_ids != REQUIRED_IDS:
        raise SystemExit(f"receipt manifest order drift: {got_ids}")

    out = {"commit": commit, "as_of": as_of, "artifacts": artifacts}
    (REPO / "site/artifacts.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{len(artifacts)} artifacts @ {commit}")


if __name__ == "__main__":
    main()
