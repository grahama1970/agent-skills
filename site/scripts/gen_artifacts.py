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
ROUNDTABLE_RUN = Path(
    "/mnt/storage12tb/skills/ask/outputs/.ask_artifacts/tau-dag-runs/"
    "ask-tau-roundtable-round-2-webgpt-webcla-ce79c8ef960c"
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    commit = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=REPO, text=True
    ).strip()
    as_of = subprocess.check_output(
        ["git", "show", "-s", "--format=%cs", "HEAD"], cwd=REPO, text=True
    ).strip()

    artifacts = []

    # 1. The tau node receipt from the roundtable that designed this site.
    receipt_path = ROUNDTABLE_RUN / "node-artifacts/handler-webclaude/node-receipt.json"
    if receipt_path.exists():
        r = json.loads(receipt_path.read_text())
        excerpt = {
            "run": ROUNDTABLE_RUN.name,
            "node": "handler-webclaude",
            "backend": r["browser_oracle"]["backend"],
            "binding_status": r["browser_oracle"]["status"],
            "tab_id": r["browser_oracle"]["tab_id"],
            "model_preference": r.get("browser_model_preference"),
            "attachment": Path(r["browser_attachment_paths"][0]).name,
            "path_preflight": r["browser_local_path_preflight"]["status"],
        }
        artifacts.append(
            {
                "id": "roundtable-receipt",
                "title": "tau node receipt — the run that designed this site",
                "caption": f"node-receipt.json · {ROUNDTABLE_RUN.name} · sha256 {sha(receipt_path)[:16]}…",
                "body": json.dumps(excerpt, indent=2),
            }
        )

    # 2. Live drift audit of this site against the repo README.
    audit = subprocess.run(
        [str(REPO / "skills/monitor-website/run.sh"), "audit", "--json"],
        capture_output=True,
        text=True,
    )
    if audit.returncode == 0:
        d = json.loads(audit.stdout)
        compact = {"ok": d["ok"], "drift": d["drift"], "live": d["live"]}
        artifacts.append(
            {
                "id": "live-audit",
                "title": "monitor-website audit — this page, checked against the repo",
                "caption": "skills/monitor-website/run.sh audit --json · captured at build",
                "body": json.dumps(compact, indent=2),
            }
        )

    # 3. Inventory provenance.
    inv_path = REPO / "site/inventory.json"
    inv = json.loads(inv_path.read_text())
    artifacts.append(
        {
            "id": "inventory-provenance",
            "title": "inventory provenance — where the numbers come from",
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
    )

    out = {"commit": commit, "as_of": as_of, "artifacts": artifacts}
    (REPO / "site/artifacts.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{len(artifacts)} artifacts @ {commit}")


if __name__ == "__main__":
    main()
