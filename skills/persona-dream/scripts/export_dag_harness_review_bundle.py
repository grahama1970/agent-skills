#!/usr/bin/env python3
"""Export raw harness-phase evidence for WebGPT or human review."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

DEFAULT_ARTIFACT_ROOT = Path(__file__).resolve().parents[1] / ".artifacts/persona-dream-local-proof"
DEFAULT_OUT = Path(
    "/mnt/storage12tb/skills/persona-dream/outputs/dag-harness-review-20260623/evidence-export"
)
RUNGS = ("scillm-one", "scillm-two-concurrent", "real-gates")


def latest_dir(root: Path, rung: str) -> Path:
    matches = sorted(root.glob(f"*-{rung}-*"), key=lambda p: p.name, reverse=True)
    if not matches:
        raise FileNotFoundError(f"No output for rung {rung}")
    return matches[0]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--zip", type=Path, default=None)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {"rungs": {}, "viewer": {}}

    for rung in RUNGS:
        src = latest_dir(args.artifact_root, rung)
        dest = args.out / rung
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        summary_path = dest / "context/proof-summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        manifest["rungs"][rung] = {
            "source_dir": str(src),
            "status": summary.get("status"),
            "proof_scope": summary.get("proof_scope"),
            "output_dir_hash": sha256(summary_path),
            "claims": summary.get("claims"),
        }

    # geometry + CDP artifacts if present
    geom_script = Path(
        "/home/graham/workspace/experiments/pi-mono/packages/ux-lab/scripts/verify-dag-harness-geometry.cjs"
    )
    if geom_script.is_file():
        proc = subprocess.run(
            ["node", str(geom_script)],
            cwd=geom_script.parents[1],
            capture_output=True,
            text=True,
            check=False,
        )
        (args.out / "geometry.json").write_text(proc.stdout or proc.stderr, encoding="utf-8")
        manifest["viewer"]["geometry_exit_code"] = proc.returncode

    for name, src in [
        ("geometry-screenshot.png", Path("/tmp/persona-dream-dag-harness-transport-style-3002.png")),
        ("cdp-screenshot.png", Path("/tmp/codex-ui-verification/pi-mono/scillm-dag-harness/20260623T115951Z.png")),
    ]:
        if src.is_file():
            shutil.copy2(src, args.out / name)

    public_manifest = Path(
        "/home/graham/workspace/experiments/pi-mono/packages/ux-lab/public/scillm-dag-runs/manifest.json"
    )
    if public_manifest.is_file():
        shutil.copy2(public_manifest, args.out / "public-manifest.json")
        manifest["viewer"]["public_manifest_sha256"] = sha256(public_manifest)

    manifest["node_count_contract"] = {
        "evidence_nodes": "Adapter TransportDagEvidence nodes (e.g. 5 for scillm-two-concurrent expanded graph)",
        "canvas_nodes": "React Flow nodes including topology:context, fanout-bus, join-bus (e.g. 6)",
        "rule": "Side panel 'evidence nodes' counts receipt graph nodes; canvas includes transport topology buses.",
    }

    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    zip_path = args.zip or (args.out.parent / "review-bundle-full.zip")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(args.out.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(args.out))
    print(json.dumps({"export_dir": str(args.out), "zip": str(zip_path), "manifest": manifest}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
