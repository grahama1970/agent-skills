import json
import pytest

from sprite_atlas.promote import promote_candidate
from sprite_atlas.receipts import sha256_file


def test_promote_rejects_blocked_receipt(tmp_path):
    job = tmp_path
    (job / "repair-receipt.json").write_text(
        json.dumps({"status": "BLOCKED_MISSING_FRAMES"}), encoding="utf-8"
    )
    (job / "validation.json").write_text(
        json.dumps({"passed": False}), encoding="utf-8"
    )
    (job / "atlas.candidate.png").write_bytes(b"")
    (job / "atlas.candidate.json").write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError):
        promote_candidate(
            job_dir=job, out_png=tmp_path / "out.png", out_json=tmp_path / "out.json"
        )


def test_promote_accepts_passing_frame_patch_receipt(tmp_path):
    job = tmp_path / "job"
    job.mkdir()
    (job / "frame-patch-receipt.json").write_text(
        json.dumps({"status": "PASS_FRAME_PATCH"}), encoding="utf-8"
    )
    (job / "validation.json").write_text(json.dumps({"passed": True}), encoding="utf-8")
    (job / "atlas.candidate.png").write_bytes(b"png-candidate")
    (job / "atlas.candidate.json").write_text("{}", encoding="utf-8")
    out_png = tmp_path / "production" / "runner.png"
    out_json = tmp_path / "production" / "runner.json"
    promote_candidate(job_dir=job, out_png=out_png, out_json=out_json)
    promotion = json.loads((job / "promotion-receipt.json").read_text(encoding="utf-8"))
    assert promotion["status"] == "PASS_PROMOTED"
    assert promotion["promoted_png_sha256"] == sha256_file(out_png)


def test_promote_accepts_passing_named_frame_pack_receipt(tmp_path):
    job = tmp_path / "job"
    job.mkdir()
    (job / "named-frame-pack-receipt.json").write_text(
        json.dumps({"status": "PASS_NAMED_FRAME_PACK"}), encoding="utf-8"
    )
    (job / "validation.json").write_text(json.dumps({"passed": True}), encoding="utf-8")
    (job / "atlas.candidate.png").write_bytes(b"png-candidate")
    (job / "atlas.candidate.json").write_text("{}", encoding="utf-8")
    out_png = tmp_path / "production" / "runner.png"
    out_json = tmp_path / "production" / "runner.json"

    promote_candidate(job_dir=job, out_png=out_png, out_json=out_json)

    promotion = json.loads((job / "promotion-receipt.json").read_text(encoding="utf-8"))
    assert promotion["status"] == "PASS_PROMOTED"
    assert promotion["source_receipt"] == "named-frame-pack-receipt.json"
