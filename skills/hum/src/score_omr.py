"""Score PDF/Image to MIDI helpers for controlled melody input."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Literal


ScoreBackend = Literal["auto", "musicxml", "audiveris", "musescore", "melogen"]


@dataclass(frozen=True)
class ScoreMidiResult:
    input_score: str
    out_dir: str
    backend: str
    midi_path: str | None
    musicxml_path: str | None
    manifest_json: str
    status: str
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


def _run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, check=False, capture_output=True, text=True)


def _find_first(root: Path, suffixes: tuple[str, ...]) -> Path | None:
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in suffixes:
            return path
    return None


def _musicxml_to_midi(musicxml_path: Path, midi_path: Path) -> Path:
    try:
        from music21 import converter
    except ImportError as exc:
        raise RuntimeError("music21 is required to convert MusicXML to MIDI") from exc

    score = converter.parse(str(musicxml_path))
    midi_path.parent.mkdir(parents=True, exist_ok=True)
    score.write("midi", fp=str(midi_path))
    if not midi_path.exists() or midi_path.stat().st_size <= 0:
        raise RuntimeError(f"music21 did not create MIDI: {midi_path}")
    return midi_path


def _convert_with_audiveris(score_path: Path, out_dir: Path) -> tuple[Path | None, list[str]]:
    audiveris = shutil.which("audiveris")
    if not audiveris:
        return None, ["audiveris executable not found in PATH"]
    cmd = [audiveris, "-batch", "-transcribe", "-export", str(score_path)]
    completed = _run(cmd, cwd=out_dir)
    logs = [" ".join(cmd), completed.stdout[-4000:], completed.stderr[-4000:]]
    musicxml = _find_first(out_dir, (".musicxml", ".mxl", ".xml"))
    return musicxml, logs


def _convert_with_musescore(score_path: Path, out_dir: Path) -> tuple[Path | None, Path | None, list[str]]:
    musescore = shutil.which("musescore") or shutil.which("mscore")
    if not musescore:
        return None, None, ["musescore/mscore executable not found in PATH"]
    musicxml_path = out_dir / f"{score_path.stem}.musicxml"
    midi_path = out_dir / f"{score_path.stem}.mid"
    logs: list[str] = []

    if score_path.suffix.lower() in {".musicxml", ".xml", ".mxl"}:
        musicxml_path = score_path
    else:
        cmd = [musescore, "--import-pdf", str(score_path), "--export", str(musicxml_path)]
        completed = _run(cmd, cwd=out_dir)
        logs.extend([" ".join(cmd), completed.stdout[-4000:], completed.stderr[-4000:]])

    if musicxml_path.exists():
        cmd = [musescore, str(musicxml_path), "-o", str(midi_path)]
        completed = _run(cmd, cwd=out_dir)
        logs.extend([" ".join(cmd), completed.stdout[-4000:], completed.stderr[-4000:]])
    return (musicxml_path if musicxml_path.exists() else None), (midi_path if midi_path.exists() else None), logs


def _convert_with_melogen(score_path: Path, out_dir: Path) -> tuple[Path | None, list[str]]:
    if not os.environ.get("MELOGEN_API_KEY"):
        return None, ["MELOGEN_API_KEY is not set"]
    if not shutil.which("melogen"):
        return None, ["melogen CLI not found in PATH; install melogenai first"]

    cmd = ["melogen", "sheet2midi", str(score_path)]
    completed = _run(cmd, cwd=out_dir)
    logs = [" ".join(cmd), completed.stdout[-4000:], completed.stderr[-4000:]]
    midi = _find_first(out_dir, (".mid", ".midi"))
    return midi, logs


def score_to_midi(score_path: Path, out_dir: Path, *, backend: ScoreBackend = "auto") -> ScoreMidiResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "score_to_midi_manifest.json"
    if not score_path.exists():
        raise FileNotFoundError(score_path)

    logs: list[str] = []
    musicxml_path: Path | None = None
    midi_path: Path | None = None
    chosen = backend

    try:
        if backend == "musicxml" or score_path.suffix.lower() in {".musicxml", ".xml", ".mxl"}:
            chosen = "musicxml"
            musicxml_path = score_path
            midi_path = _musicxml_to_midi(musicxml_path, out_dir / f"{score_path.stem}.mid")
        elif backend in {"auto", "audiveris"}:
            chosen = "audiveris"
            musicxml_path, audiveris_logs = _convert_with_audiveris(score_path, out_dir)
            logs.extend(audiveris_logs)
            if musicxml_path:
                midi_path = _musicxml_to_midi(musicxml_path, out_dir / f"{score_path.stem}.mid")
            elif backend == "audiveris":
                raise RuntimeError("Audiveris did not produce MusicXML")
        if midi_path is None and backend in {"auto", "musescore"}:
            chosen = "musescore"
            musicxml_path, midi_path, musescore_logs = _convert_with_musescore(score_path, out_dir)
            logs.extend(musescore_logs)
            if midi_path is None and musicxml_path:
                midi_path = _musicxml_to_midi(musicxml_path, out_dir / f"{score_path.stem}.mid")
            elif midi_path is None and backend == "musescore":
                raise RuntimeError("MuseScore did not produce MIDI or MusicXML")
        if midi_path is None and backend in {"auto", "melogen"}:
            chosen = "melogen"
            midi_path, melogen_logs = _convert_with_melogen(score_path, out_dir)
            logs.extend(melogen_logs)
            if midi_path is None and backend == "melogen":
                raise RuntimeError("Melogen did not produce MIDI")
    except Exception as exc:
        payload = {
            "schema": "hum.score_to_midi.v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "input_score": str(score_path),
            "out_dir": str(out_dir),
            "backend": chosen,
            "status": "blocked",
            "message": str(exc),
            "logs": logs,
        }
        manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return ScoreMidiResult(
            input_score=str(score_path),
            out_dir=str(out_dir),
            backend=chosen,
            midi_path=None,
            musicxml_path=str(musicxml_path) if musicxml_path else None,
            manifest_json=str(manifest_path),
            status="blocked",
            message=str(exc),
        )

    status = "ok" if midi_path and midi_path.exists() else "blocked"
    message = "score converted to MIDI" if status == "ok" else "no OMR backend produced MIDI"
    payload = {
        "schema": "hum.score_to_midi.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input_score": str(score_path),
        "out_dir": str(out_dir),
        "backend": chosen,
        "status": status,
        "message": message,
        "musicxml_path": str(musicxml_path) if musicxml_path else None,
        "midi_path": str(midi_path) if midi_path else None,
        "logs": logs,
    }
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return ScoreMidiResult(
        input_score=str(score_path),
        out_dir=str(out_dir),
        backend=chosen,
        midi_path=str(midi_path) if midi_path else None,
        musicxml_path=str(musicxml_path) if musicxml_path else None,
        manifest_json=str(manifest_path),
        status=status,
        message=message,
    )
