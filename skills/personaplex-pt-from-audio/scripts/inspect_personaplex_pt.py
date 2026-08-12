#!/usr/bin/env python3
"""Inspect PersonaPlex .pt prompt caches with required audio provenance.

Validates that a candidate PersonaPlex prompt-cache .pt is well-formed (a dict
with cache/embeddings tensors of the expected shape), records the source audio
segment's provenance (hash, duration, format via wave or ffprobe), and can
create a filename alias symlink inside a server voice directory. Emits a single
JSON receipt.

RECONSTRUCTED 2026-08-12 from the surviving compiled bytecode
(inspect_personaplex_pt.cpython-312.pyc) after the .py source was lost (never
tracked in git, no disk copy survived). Faithful to the 3.12 disassembly of
every function. Now TRACKED.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import wave
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def inspect_audio(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"path": str(path), "exists": path.exists(), "ok": False}
    if not path.exists():
        result["error"] = "missing_audio_segment"
        return result
    result["bytes"] = path.stat().st_size
    result["sha256"] = sha256_file(path)
    try:
        with wave.open(str(path), "rb") as handle:
            frames = handle.getnframes()
            rate = handle.getframerate()
            result.update({
                "format": "wav",
                "channels": handle.getnchannels(),
                "sample_width": handle.getsampwidth(),
                "sample_rate": rate,
                "frames": frames,
                "duration_seconds": round(frames / rate, 6) if rate else 0.0,
            })
    except Exception as exc:
        ffprobe = run_ffprobe(path)
        result["ffprobe"] = ffprobe
        if ffprobe.get("ok"):
            result.update({
                "format": ffprobe.get("format_name"),
                "duration_seconds": ffprobe.get("duration_seconds"),
                "sample_rate": ffprobe.get("sample_rate"),
                "channels": ffprobe.get("channels"),
            })
        else:
            result["error"] = f"audio_decode_failed:{type(exc).__name__}:{exc}"
            return result
    result["ok"] = bool(float(result.get("duration_seconds") or 0.0) > 0.0)
    if not result["ok"]:
        result["error"] = "zero_duration_audio_segment"
    return result


def run_ffprobe(path: Path) -> dict[str, Any]:
    if not shutil_which("ffprobe"):
        return {"ok": False, "error": "ffprobe_not_found"}
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries",
            "stream=sample_rate,channels:format=duration,format_name",
            "-of", "json", str(path),
        ],
        text=True, capture_output=True,
    )
    if proc.returncode != 0:
        return {"ok": False, "stderr": proc.stderr[-1000:]}
    data = json.loads(proc.stdout or "{}")
    stream = (data.get("streams") or [{}])[0]
    fmt = data.get("format") or {}
    return {
        "ok": True,
        "format_name": fmt.get("format_name"),
        "duration_seconds": float(fmt.get("duration") or 0.0),
        "sample_rate": int(stream["sample_rate"]) if stream.get("sample_rate") else None,
        "channels": stream.get("channels"),
    }


def shutil_which(name: str) -> str | None:
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(folder) / name
        if not candidate.is_file():
            continue
        if not os.access(candidate, os.X_OK):
            continue
        return str(candidate)
    return None


def tensor_report(value: Any) -> dict[str, Any]:
    if hasattr(value, "shape"):
        return {
            "type": type(value).__name__,
            "shape": list(value.shape),
            "dtype": str(getattr(value, "dtype", "")),
        }
    if isinstance(value, (list, tuple)):
        return {"type": type(value).__name__, "len": len(value)}
    return {"type": type(value).__name__, "repr": repr(value)[:200]}


def inspect_pt(path: Path) -> dict[str, Any]:
    import torch

    result: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "is_symlink": path.is_symlink(),
        "resolved": str(path.resolve()) if path.exists() else None,
        "ok": False,
    }
    if not path.exists():
        result["error"] = "missing_pt"
        return result
    resolved = path.resolve()
    result["bytes"] = resolved.stat().st_size
    result["sha256"] = sha256_file(resolved)
    try:
        obj = torch.load(path, map_location="cpu", weights_only=False)
    except Exception as exc:
        result["error"] = f"torch_load_failed:{type(exc).__name__}:{exc}"
        return result
    result["object_type"] = type(obj).__name__
    if not isinstance(obj, dict):
        result["error"] = "pt_not_dict"
        return result
    result["keys"] = sorted(str(k) for k in obj.keys())
    result["tensors"] = {str(key): tensor_report(value) for key, value in obj.items()}
    missing = [key for key in ("cache", "embeddings") if key not in obj]
    result["missing_required_keys"] = missing
    embeddings = obj.get("embeddings")
    cache = obj.get("cache")
    emb_shape = list(getattr(embeddings, "shape", []))
    cache_shape = list(getattr(cache, "shape", []))
    result["ok"] = (
        not missing
        and len(emb_shape) == 4
        and emb_shape[-1] == 4096
        and bool(cache_shape)
    )
    if not result["ok"]:
        result["error"] = "invalid_personaplex_prompt_cache_shape"
    return result


def create_alias(server_voice_dir: Path, alias: str, target: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "requested": True,
        "server_voice_dir": str(server_voice_dir),
        "alias": alias,
        "target": str(target),
        "ok": False,
    }
    if "/" in alias or alias in ("", ".", ".."):
        result["error"] = "alias_must_be_filename"
        return result
    if not server_voice_dir.is_dir():
        result["error"] = "server_voice_dir_missing"
        return result
    alias_path = server_voice_dir / alias
    try:
        if alias_path.exists() or alias_path.is_symlink():
            alias_path.unlink()
        os.symlink(os.path.relpath(target.resolve(), server_voice_dir), alias_path)
        result["ok"] = alias_path.exists()
        result["path"] = str(alias_path)
        result["resolved"] = str(alias_path.resolve()) if alias_path.exists() else None
        return result
    except Exception as exc:
        result["error"] = f"alias_create_failed:{type(exc).__name__}:{exc}"
        return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect PersonaPlex .pt prompt caches with required audio provenance."
    )
    parser.add_argument("--audio-segment", required=True, type=Path)
    parser.add_argument("--working-pt", required=True, type=Path)
    parser.add_argument("--candidate-pt", required=True, type=Path)
    parser.add_argument("--server-voice-dir", type=Path)
    parser.add_argument("--alias", help="Optional filename alias to create inside --server-voice-dir for candidate-pt.")
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    receipt: dict[str, Any] = {
        "schema": "personaplex_pt_from_audio.inspect_receipt.v1",
        "created_at_utc": utc_now(),
        "audio_segment": inspect_audio(args.audio_segment.expanduser()),
        "working": inspect_pt(args.working_pt.expanduser()),
        "candidate": inspect_pt(args.candidate_pt.expanduser()),
        "alias": {"requested": False},
    }
    if args.alias or args.server_voice_dir:
        if not (args.alias and args.server_voice_dir):
            receipt["alias"] = {
                "requested": True,
                "ok": False,
                "error": "alias_requires_server_voice_dir_and_alias",
            }
        else:
            receipt["alias"] = create_alias(
                args.server_voice_dir.expanduser(), args.alias, args.candidate_pt.expanduser()
            )
            alias_path = args.server_voice_dir.expanduser() / args.alias
            receipt["alias_candidate"] = inspect_pt(alias_path)

    receipt["ok"] = bool(
        receipt["audio_segment"].get("ok")
        and receipt["working"].get("ok")
        and receipt["candidate"].get("ok")
        and (
            not receipt["alias"].get("requested")
            or (
                receipt["alias"].get("ok")
                and receipt.get("alias_candidate")
                and receipt["alias_candidate"].get("ok")
            )
        )
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": receipt["ok"], "receipt": str(args.out)}, indent=2))
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
