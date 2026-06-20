"""Build a local female-humming source dataset from HF and YouTube audio."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import urllib.request
import zipfile

import pyarrow.parquet as pq

TINY_HUMMING_PARQUET_URL = (
    "https://huggingface.co/datasets/ylacombe/tiny-humming/resolve/main/data/train-00000-of-00001.parquet"
)
HUMTRANS_BASE_URL = "https://huggingface.co/datasets/dadinghh2/HumTrans/resolve/main"


def _safe_name(value: str, fallback: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return name[:120] or fallback


def _download(url: str, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists() and out_path.stat().st_size > 0:
        return out_path
    urllib.request.urlretrieve(url, out_path)
    return out_path


def collect_tiny_humming(out_dir: Path, *, female_only: bool = True) -> list[dict]:
    parquet_path = _download(TINY_HUMMING_PARQUET_URL, out_dir / "_downloads" / "tiny-humming.parquet")
    table = pq.read_table(parquet_path, columns=["audio", "description"])
    rows = table.to_pylist()
    audio_dir = out_dir / "source_audio" / "hf_tiny_humming"
    audio_dir.mkdir(parents=True, exist_ok=True)

    items: list[dict] = []
    for index, row in enumerate(rows):
        description = str(row.get("description") or "")
        if female_only and not re.search(r"\b(female|woman)\b", description, flags=re.IGNORECASE):
            continue
        audio = row.get("audio") or {}
        data = audio.get("bytes")
        if not data:
            continue
        original_path = str(audio.get("path") or f"hf_tiny_humming_{index:03d}.wav")
        filename = f"{index:03d}-{_safe_name(Path(original_path).stem, f'hf_tiny_humming_{index:03d}')}.wav"
        out_path = audio_dir / filename
        out_path.write_bytes(data)
        items.append(
            {
                "id": f"hf_tiny_humming_{index:03d}",
                "source": "huggingface:ylacombe/tiny-humming",
                "description": description,
                "audio_path": str(out_path),
                "original_path": original_path,
            }
        )
    return items


def collect_youtube(urls: list[str], out_dir: Path, *, limit: int | None = None, quiet: bool = False) -> list[dict]:
    if not urls:
        return []
    if not shutil.which("yt-dlp"):
        raise RuntimeError("yt-dlp is required to collect YouTube audio")

    audio_dir = out_dir / "source_audio" / "youtube"
    audio_dir.mkdir(parents=True, exist_ok=True)
    error_log = out_dir / "youtube_errors.jsonl"
    items: list[dict] = []
    for url_index, url in enumerate(urls):
        before = {p.resolve() for p in audio_dir.rglob("*.wav")}
        cmd = [
            "yt-dlp",
            "--yes-playlist",
            "--extract-audio",
            "--audio-format",
            "wav",
            "--audio-quality",
            "0",
            "-o",
            str(audio_dir / f"{url_index:02d}-%(playlist_index)s-%(title).200B.%(ext)s"),
        ]
        if limit is not None:
            cmd.extend(["--max-downloads", str(limit)])
        cmd.append(url)
        completed = subprocess.run(cmd, check=False, capture_output=quiet, text=True)
        after = {p.resolve() for p in audio_dir.rglob("*.wav")}
        new_files = sorted(after - before)
        if completed.returncode not in {0, 101} and not new_files:
            error_log.parent.mkdir(parents=True, exist_ok=True)
            with error_log.open("a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "url": url,
                            "exit_code": completed.returncode,
                            "stderr": completed.stderr[-4000:] if completed.stderr else None,
                        }
                    )
                    + "\n"
                )
            continue
        if not new_files:
            new_files = sorted(after)
        for path in new_files:
            items.append(
                {
                    "id": f"youtube_{len(items):03d}",
                    "source": "youtube",
                    "source_url": url,
                    "audio_path": str(path),
                }
            )
    return items


def _head_size(url: str) -> int | None:
    try:
        request = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(request, timeout=30) as response:
            length = response.headers.get("content-length")
            return int(length) if length else None
    except Exception:
        return None


def humtrans_metadata() -> dict:
    wav_url = f"{HUMTRANS_BASE_URL}/all_wav.zip"
    midi_url = f"{HUMTRANS_BASE_URL}/all_midi.zip"
    splits_url = f"{HUMTRANS_BASE_URL}/train_valid_test_keys.json"
    return {
        "id": "huggingface:dadinghh2/HumTrans",
        "role": "melody_supervision_candidate",
        "license": "cc-by-nc-4.0",
        "wav_zip_url": wav_url,
        "wav_zip_size_bytes": _head_size(wav_url),
        "midi_zip_url": midi_url,
        "midi_zip_size_bytes": _head_size(midi_url),
        "splits_url": splits_url,
        "splits_size_bytes": _head_size(splits_url),
        "auto_downloaded": False,
        "reason_not_auto_downloaded": "all_wav.zip is large; require an explicit bounded ingestion step.",
    }


def _download_with_curl(url: str, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists() and out_path.stat().st_size > 0:
        return out_path
    if shutil.which("curl"):
        tmp_path = out_path.with_suffix(out_path.suffix + ".part")
        cmd = ["curl", "-L", "--fail", "--continue-at", "-", url, "-o", str(tmp_path)]
        subprocess.run(cmd, check=True)
        tmp_path.rename(out_path)
        return out_path
    return _download(url, out_path)


def _extract_zip(zip_path: Path, extract_dir: Path, *, limit: int | None = None) -> list[str]:
    extract_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[str] = []
    with zipfile.ZipFile(zip_path) as zf:
        members = [m for m in zf.infolist() if not m.is_dir()]
        if limit is not None:
            members = members[:limit]
        for member in members:
            target = extract_dir / member.filename
            if target.exists() and target.stat().st_size == member.file_size:
                extracted.append(str(target))
                continue
            zf.extract(member, extract_dir)
            extracted.append(str(target))
    return extracted


def _zip_stems(zip_path: Path, suffix: str) -> dict[str, str]:
    if not zip_path.exists():
        return {}
    stems: dict[str, str] = {}
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            if member.is_dir() or not member.filename.lower().endswith(suffix):
                continue
            stems[Path(member.filename).stem] = member.filename
    return stems


def build_humtrans_pair_manifest(
    humtrans_dir: Path,
    *,
    output_jsonl: Path | None = None,
    female_only: bool = True,
    require_wav: bool = True,
    limit: int | None = None,
) -> dict:
    """Create a training manifest from HumTrans WAV/MIDI ZIP members."""
    downloads_dir = humtrans_dir / "downloads"
    midi_zip = downloads_dir / "all_midi.zip"
    wav_zip = downloads_dir / "all_wav.zip"
    splits_json = downloads_dir / "train_valid_test_keys.json"
    if not midi_zip.exists():
        raise FileNotFoundError(f"Missing HumTrans MIDI zip: {midi_zip}")
    if require_wav and not wav_zip.exists():
        raise FileNotFoundError(f"Missing HumTrans WAV zip: {wav_zip}")
    if not splits_json.exists():
        raise FileNotFoundError(f"Missing HumTrans split file: {splits_json}")

    split_data = json.loads(splits_json.read_text(encoding="utf-8"))
    split_by_key = {
        key: split.lower()
        for split, keys in split_data.items()
        for key in keys
    }
    midi_members = _zip_stems(midi_zip, ".mid")
    wav_members = _zip_stems(wav_zip, ".wav") if wav_zip.exists() else {}

    rows: list[dict] = []
    missing_midi = 0
    missing_wav = 0
    for key, split in sorted(split_by_key.items()):
        if female_only and not key.startswith("F"):
            continue
        midi_member = midi_members.get(key)
        wav_member = wav_members.get(key)
        if not midi_member:
            missing_midi += 1
            continue
        if require_wav and not wav_member:
            missing_wav += 1
            continue
        rows.append(
            {
                "id": key,
                "split": split,
                "speaker_id": key.split("_", 1)[0],
                "gender_prefix": key[0],
                "midi_zip": str(midi_zip),
                "midi_member": midi_member,
                "wav_zip": str(wav_zip) if wav_member else None,
                "wav_member": wav_member,
                "source": "huggingface:dadinghh2/HumTrans",
                "license": "cc-by-nc-4.0",
            }
        )
        if limit is not None and len(rows) >= limit:
            break

    output_jsonl = output_jsonl or humtrans_dir / "pairs.jsonl"
    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with output_jsonl.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")

    summary = {
        "schema": "hum.humtrans_pairs.v1",
        "humtrans_dir": str(humtrans_dir),
        "pairs_jsonl": str(output_jsonl),
        "count": len(rows),
        "female_only": female_only,
        "require_wav": require_wav,
        "limit": limit,
        "split_counts": {
            split: sum(1 for row in rows if row["split"] == split)
            for split in ["train", "valid", "test"]
        },
        "missing_midi": missing_midi,
        "missing_wav": missing_wav,
        "midi_member_count": len(midi_members),
        "wav_member_count": len(wav_members),
        "notes": [
            "This manifest points into ZIP members; extraction can be limited to the selected rows.",
            "Female-only uses the HumTrans key prefix Fxx.",
            "This prepares melody-supervised hum rendering data, not Embry voice cloning data.",
        ],
    }
    summary_path = output_jsonl.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_json"] = str(summary_path)
    return summary


def ingest_humtrans(
    out_dir: Path,
    *,
    download_wav: bool = False,
    extract: bool = False,
    extract_limit: int | None = None,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    downloads_dir = out_dir / "downloads"
    extracted_dir = out_dir / "extracted"
    metadata = humtrans_metadata()

    midi_zip = _download_with_curl(metadata["midi_zip_url"], downloads_dir / "all_midi.zip")
    splits_json = _download_with_curl(metadata["splits_url"], downloads_dir / "train_valid_test_keys.json")
    wav_zip = None
    if download_wav:
        wav_zip = _download_with_curl(metadata["wav_zip_url"], downloads_dir / "all_wav.zip")

    extracted_midi: list[str] = []
    extracted_wav: list[str] = []
    if extract:
        extracted_midi = _extract_zip(midi_zip, extracted_dir / "midi", limit=extract_limit)
        if wav_zip:
            extracted_wav = _extract_zip(wav_zip, extracted_dir / "wav", limit=extract_limit)

    manifest = {
        "schema": "hum.humtrans_ingest.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "out_dir": str(out_dir),
        "metadata": metadata,
        "downloads": {
            "midi_zip": str(midi_zip),
            "midi_zip_bytes": midi_zip.stat().st_size,
            "splits_json": str(splits_json),
            "splits_json_bytes": splits_json.stat().st_size,
            "wav_zip": str(wav_zip) if wav_zip else None,
            "wav_zip_bytes": wav_zip.stat().st_size if wav_zip else None,
        },
        "extract": {
            "enabled": extract,
            "limit": extract_limit,
            "midi_count": len(extracted_midi),
            "wav_count": len(extracted_wav),
            "midi_dir": str(extracted_dir / "midi") if extracted_midi else None,
            "wav_dir": str(extracted_dir / "wav") if extracted_wav else None,
        },
        "notes": [
            "HumTrans is a supervised humming melody dataset, not an Embry voice dataset.",
            "License metadata from Hugging Face is recorded as cc-by-nc-4.0.",
            "Use extracted WAV/MIDI pairs for model training experiments only after rights review.",
        ],
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    manifest["manifest_json"] = str(manifest_path)
    return manifest


def build_female_humming_dataset(
    out_dir: Path,
    *,
    youtube_urls: list[str] | None = None,
    include_hf_tiny: bool = True,
    female_only: bool = True,
    youtube_limit: int | None = None,
    include_humtrans_metadata: bool = True,
    quiet_youtube: bool = False,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    items: list[dict] = []
    if include_hf_tiny:
        items.extend(collect_tiny_humming(out_dir, female_only=female_only))
    items.extend(collect_youtube(youtube_urls or [], out_dir, limit=youtube_limit, quiet=quiet_youtube))

    manifest = {
        "schema": "hum.female_humming_sources.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "out_dir": str(out_dir),
        "count": len(items),
        "items": items,
        "candidate_sources": [humtrans_metadata()] if include_humtrans_metadata else [],
        "notes": [
            "This is a source dataset for decomposition experiments, not an Embry voice dataset.",
            "Hugging Face tiny-humming rows are filtered by description for female/woman when female_only is true.",
            "YouTube sources require rights review before any downstream publication.",
        ],
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    manifest["manifest_json"] = str(manifest_path)
    return manifest
