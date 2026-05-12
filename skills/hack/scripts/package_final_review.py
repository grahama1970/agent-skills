#!/usr/bin/env python3
"""Package a replayable /hack final report review bundle with raw ledgers."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import time
import zipfile
from typing import Any


def load_json(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text()) if path.exists() else {}


def latest_dir(root: pathlib.Path, pattern: str) -> pathlib.Path:
    matches = sorted(root.glob(pattern))
    if not matches:
        raise SystemExit(f"missing {pattern} under {root}")
    return matches[-1]


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def add_existing(bundle: zipfile.ZipFile, manifest: list[dict[str, Any]], path: pathlib.Path, arcname: str) -> None:
    if not path.exists():
        manifest.append({"path": arcname, "source_path": str(path), "exists": False, "sha256": None})
        return
    bundle.write(path, arcname)
    manifest.append(
        {
            "path": arcname,
            "source_path": str(path),
            "exists": True,
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
        }
    )


def build_package(run_root: pathlib.Path, output: pathlib.Path) -> pathlib.Path:
    evolve_dir = latest_dir(run_root, "evolve-campaign-*")
    manifest: list[dict[str, Any]] = []
    output.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name in [
            "OPENCLAW_PREFLIGHT.json",
            "CLOSURE_VERDICT.json",
            "HACK_FINAL_REPORT.json",
            "HACK_FINAL_REPORT.md",
            "HACK_FINAL_REPORT.html",
            "focused-repro-assessment.json",
            "battle-mode-assessment.json",
            "battle-command.log",
            "dogpile-citation-assessment.json",
            "dogpile-openclaw-citation-run.txt",
            "final-report-assessment.json",
            "ui-verification-marker.json",
            "openclaw-hooks-wake-patch-objective.json",
        ]:
            add_existing(bundle, manifest, run_root / name, f"run-artifacts/{name}")

        post_path = run_root / "post-patch-verification.json"
        if post_path.exists():
            add_existing(bundle, manifest, post_path, "run-artifacts/post-patch-verification.json")
        else:
            missing_payload = {
                "status": "blocked_patch_not_applied",
                "pass": False,
                "reason": "No post-patch verification artifact exists.",
            }
            missing_bytes = (json.dumps(missing_payload, indent=2) + "\n").encode()
            bundle.writestr("run-artifacts/post-patch-verification.MISSING.json", missing_bytes)
            manifest.append(
                {
                    "path": "run-artifacts/post-patch-verification.MISSING.json",
                    "source_path": str(post_path),
                    "exists": False,
                    "sha256": hashlib.sha256(missing_bytes).hexdigest(),
                    "bytes": len(missing_bytes),
                }
            )

        add_existing(bundle, manifest, evolve_dir / "attempts.jsonl", "raw-ledgers/attempts.jsonl")
        add_existing(bundle, manifest, evolve_dir / "anomalies.jsonl", "raw-ledgers/anomalies.jsonl")
        add_existing(bundle, manifest, evolve_dir / "summary.json", "raw-ledgers/summary.json")
        add_existing(bundle, manifest, evolve_dir / "strategies.seed.json", "raw-ledgers/strategies.seed.json")
        add_existing(bundle, manifest, evolve_dir / "next-dogpile-seed.json", "raw-ledgers/next-dogpile-seed.json")
        add_existing(
            bundle,
            manifest,
            evolve_dir / "proof-candidates" / "hooks-wake-websocket-repro.json",
            "raw-ledgers/proof-candidates/hooks-wake-websocket-repro.json",
        )
        for path in sorted(evolve_dir.glob("generation-*.json")):
            add_existing(bundle, manifest, path, f"raw-ledgers/{path.name}")
        for path in sorted((evolve_dir / "promotion-tasks").glob("*")) if (evolve_dir / "promotion-tasks").exists() else []:
            if path.is_file():
                add_existing(bundle, manifest, path, f"raw-ledgers/promotion-tasks/{path.name}")
        product_patch_dir = run_root / "openclaw-product-patch"
        for path in sorted(product_patch_dir.glob("*")) if product_patch_dir.exists() else []:
            if path.is_file():
                add_existing(bundle, manifest, path, f"product-patch/{path.name}")

        manifest_payload = {
            "schema": "hack.final_review_package_manifest.v1",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "run_root": str(run_root),
            "evolve_dir": str(evolve_dir),
            "entries": manifest,
        }
        bundle.writestr("MANIFEST.json", json.dumps(manifest_payload, indent=2) + "\n")

    return output


def main_for_test(run_root: pathlib.Path, output: pathlib.Path) -> pathlib.Path:
    return build_package(run_root, output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_root", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    print(build_package(args.run_root, args.output))


if __name__ == "__main__":
    main()
