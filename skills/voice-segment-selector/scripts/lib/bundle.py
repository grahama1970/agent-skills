"""Build a target-duration bundle from ranked candidates."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from lib.audio_io import extract_clip
from lib.constants import DEFAULT_MIN_SCORE, SAMPLE_RATE
from lib.score import rank_score


def select_collection(rows: list[dict], target_sec: float, gender: str | None, min_score: float) -> list[dict]:
    filtered = []
    for row in rows:
        if gender and row.get("gender_label") != gender:
            continue
        if float(row.get("gender_score") or 0.0) < min_score and row.get("gender_score") is not None:
            continue
        if row.get("gender_label") == "unknown":
            continue
        filtered.append(row)
    filtered.sort(key=lambda row: rank_score(row), reverse=True)

    chosen: list[dict] = []
    total = 0.0
    for row in filtered:
        if total >= target_sec:
            break
        remaining = target_sec - total
        use_duration = min(float(row["duration_sec"]), remaining)
        if use_duration <= 0:
            continue
        chosen.append(
            {
                **row,
                "use_start_sec": row["start_sec"],
                "use_end_sec": row["start_sec"] + use_duration,
                "use_duration_sec": round(use_duration, 3),
            }
        )
        total += use_duration
    return chosen


def build_bundle(
    *,
    job_dir: Path,
    out_path: Path,
    gender: str,
    target_sec: float = 30.0,
    min_score: float = DEFAULT_MIN_SCORE,
) -> dict:
    rows = []
    for line in (job_dir / "candidates.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    chosen = select_collection(rows, target_sec, gender, min_score)
    if sum(row["use_duration_sec"] for row in chosen) < target_sec:
        raise RuntimeError("Not enough high-quality clips to reach target duration.")

    source_wav = job_dir / "_work" / "source.mono16k.wav"
    if not source_wav.exists():
        raise FileNotFoundError(f"Missing normalized source wav: {source_wav}")

    clip_dir = out_path.parent / f"{out_path.stem}_clips"
    clip_dir.mkdir(parents=True, exist_ok=True)
    clip_paths: list[Path] = []
    for index, row in enumerate(chosen, start=1):
        clip_path = clip_dir / f"{index:02d}.wav"
        extract_clip(source_wav, row["use_start_sec"], row["use_end_sec"], clip_path)
        clip_paths.append(clip_path)

    if len(clip_paths) == 1:
        clip_paths[0].replace(out_path)
    else:
        list_file = out_path.with_suffix(".concat.txt")
        list_file.write_text("".join(f"file '{path.resolve()}'\n" for path in clip_paths))
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(out_path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    payload = {
        "gender": gender,
        "target_sec": target_sec,
        "achieved_sec": round(sum(row["use_duration_sec"] for row in chosen), 3),
        "parts": chosen,
        "output_wav": str(out_path.resolve()),
    }
    (out_path.with_suffix(".json")).write_text(json.dumps(payload, indent=2))
    return payload
