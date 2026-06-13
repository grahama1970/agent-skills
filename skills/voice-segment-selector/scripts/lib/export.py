"""Export accepted candidates into a TTS-ready dataset."""

from __future__ import annotations

import json
import shutil
from pathlib import Path


def load_candidates(job_dir: Path) -> list[dict]:
    path = job_dir / "candidates.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}; run prepare first.")
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    decisions_path = job_dir / "decisions.jsonl"
    if decisions_path.exists():
        decisions = {}
        for line in decisions_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            decisions[row["id"]] = row["decision"]
        filtered: list[dict] = []
        for row in rows:
            decision = decisions.get(row["id"], row.get("status", "pending"))
            if decision == "accept":
                row = {**row, "status": "accepted", "accepted_by": "human"}
                filtered.append(row)
        rows = filtered
    return rows


def export_dataset(
    *,
    job_dir: Path,
    out_dir: Path,
    gender: str | None = None,
    min_quality: float = 0.0,
    min_rank: float = 0.0,
    auto_accept_top: int = 0,
) -> dict:
    rows = load_candidates(job_dir)
    if auto_accept_top > 0 and not (job_dir / "decisions.jsonl").exists():
        rows = sorted(rows, key=lambda row: row.get("rank_score", 0.0), reverse=True)
        if gender:
            rows = [row for row in rows if row.get("gender_label") == gender]
        rows = rows[:auto_accept_top]
        for row in rows:
            row["status"] = "accepted"
            row["accepted_by"] = "auto"
    elif gender:
        rows = [row for row in rows if row.get("gender_label") == gender]

    rows = [
        row
        for row in rows
        if row.get("status") in {"accepted", "accept"}
        and float(row.get("quality_score") or 0.0) >= min_quality
        and float(row.get("rank_score") or 0.0) >= min_rank
    ]

    clips_dir = out_dir / "clips"
    male_dir = out_dir / "male"
    female_dir = out_dir / "female"
    unknown_dir = out_dir / "unknown"
    for directory in (clips_dir, male_dir, female_dir, unknown_dir):
        directory.mkdir(parents=True, exist_ok=True)

    metadata_rows: list[dict] = []
    rejected_rows: list[dict] = []
    for index, row in enumerate(rows, start=1):
        src = job_dir / row["clip"]
        if not src.exists():
            continue
        label = row.get("gender_label", "unknown")
        bucket = {"male": male_dir, "female": female_dir, "unknown": unknown_dir}.get(label, unknown_dir)
        dest_name = f"{index:04d}.wav"
        shutil.copy2(src, clips_dir / dest_name)
        shutil.copy2(src, bucket / dest_name)
        metadata_rows.append(
            {
                "clip": f"clips/{dest_name}",
                "bucket_clip": f"{label}/{dest_name}",
                "source": row.get("source"),
                "start": row.get("start_sec"),
                "end": row.get("end_sec"),
                "duration_sec": row.get("duration_sec"),
                "transcript": row.get("transcript", ""),
                "asr_confidence": row.get("asr_confidence"),
                "quality_score": row.get("quality_score"),
                "rank_score": row.get("rank_score"),
                "gender_label": label,
                "gender_score": row.get("gender_score"),
                "accepted_by": row.get("accepted_by", "human"),
            }
        )

    (out_dir / "metadata.jsonl").write_text(
        "\n".join(json.dumps(row) for row in metadata_rows) + ("\n" if metadata_rows else "")
    )
    (out_dir / "rejected.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rejected_rows) + ("\n" if rejected_rows else "")
    )
    summary = {
        "exported_clips": len(metadata_rows),
        "out_dir": str(out_dir.resolve()),
        "metadata_jsonl": str((out_dir / "metadata.jsonl").resolve()),
    }
    (out_dir / "export_summary.json").write_text(json.dumps(summary, indent=2))
    return summary
