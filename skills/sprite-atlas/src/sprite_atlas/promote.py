"""Promote staged candidates after a passing receipt."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from sprite_atlas.receipts import sha256_file, write_json


def promote_candidate(
    *,
    job_dir: Path,
    out_png: Path,
    out_json: Path,
) -> None:
    receipt_path = job_dir / "repair-receipt.json"
    allowed = {"PASS_NATIVE", "PASS_REPAIRED"}
    if not receipt_path.is_file():
        receipt_path = job_dir / "frame-patch-receipt.json"
        allowed = {"PASS_FRAME_PATCH"}
    if not receipt_path.is_file():
        receipt_path = job_dir / "named-frame-pack-receipt.json"
        allowed = {"PASS_NAMED_FRAME_PACK"}
    if not receipt_path.is_file():
        raise RuntimeError(
            "promotion blocked: passing repair, frame-patch, or named-frame-pack receipt missing"
        )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    status = receipt.get("status", "")
    if status not in allowed:
        raise RuntimeError(f"promotion blocked: receipt status is {status}")
    validation = json.loads((job_dir / "validation.json").read_text(encoding="utf-8"))
    if not validation.get("passed"):
        raise RuntimeError("promotion blocked: validation.json not passed")

    candidate_png = job_dir / "atlas.candidate.png"
    candidate_json = job_dir / "atlas.candidate.json"
    if not candidate_png.exists() or not candidate_json.exists():
        raise RuntimeError("promotion blocked: candidate atlas files missing")

    out_png.parent.mkdir(parents=True, exist_ok=True)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(candidate_png, out_png)
    shutil.copy2(candidate_json, out_json)
    write_json(
        job_dir / "promotion-receipt.json",
        {
            "schema": "sprite_atlas.promotion_receipt.v1",
            "status": "PASS_PROMOTED",
            "source_receipt": receipt_path.name,
            "source_receipt_sha256": sha256_file(receipt_path),
            "validation_sha256": sha256_file(job_dir / "validation.json"),
            "promoted_png": str(out_png),
            "promoted_png_sha256": sha256_file(out_png),
            "promoted_json": str(out_json),
            "promoted_json_sha256": sha256_file(out_json),
        },
    )
