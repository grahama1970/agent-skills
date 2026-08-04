#!/usr/bin/env python3
"""Have Embry read her own journal aloud, into the run directory (#1208).

Every piece existed and nothing connected them: `journal_spoken.txt` is written
by the journal renderer, the delivery tone is chosen by the mood mapper, and
Chatterbox renders audio. But the audio landed in Chatterbox's own log tree
(`/out/<label>/` inside the container, `chatterbox/logs/<label>/` on the host),
which the journal UX has no business reaching into. So no run directory has ever
contained a wav, and Embry has never actually read her journal.

This copies the render into the run directory and binds it to the text:
sha256 of `journal_spoken.txt` is recorded next to the audio, so a later reader
can prove the wav is that entry rather than some other run's.

The receipt records the requested delivery tone AND the persona mood it came
from, and never claims the tone was achieved -- Chatterbox reports preset-driven
acoustic shifts below same-parameter stochastic spread, so that question needs
measurement (#1209), not assertion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
CHATTERBOX = os.environ.get("CHATTERBOX_BASE_URL", "http://127.0.0.1:8018")
#: Container `/out` is bind-mounted here on the host.
CHATTERBOX_OUT_HOST_ROOT = Path(
    os.environ.get("CHATTERBOX_OUT_HOST_ROOT",
                   "/home/graham/workspace/experiments/chatterbox/logs")
)
DEFAULT_REF_AUDIO = "/data/embry_ref.wav"


def utc_now() -> str:
    return datetime.now().astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def rel(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path)


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def sha_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_sibling(name: str):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(f"{name}.py"))
    if not spec or not spec.loader:
        raise RuntimeError(f"cannot load sibling script: {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve_host_audio(container_path: str) -> Path | None:
    """Map the container path Chatterbox returns onto the host bind mount."""
    if not container_path:
        return None
    p = Path(container_path)
    if p.is_file():
        return p
    if p.is_absolute() and len(p.parts) > 2 and p.parts[1] == "out":
        host = CHATTERBOX_OUT_HOST_ROOT.joinpath(*p.parts[2:])
        if host.is_file():
            return host
    return None


def post_json(url: str, payload: dict[str, Any], timeout: int = 900) -> dict[str, Any]:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir)
    spoken_path = run_dir / "journal_spoken.txt"
    failed: list[str] = []

    if not spoken_path.is_file():
        return {
            "schema": "persona_dream.journal_audio_receipt.v1",
            "created_at": utc_now(), "status": "BLOCKED_NO_SPOKEN_TEXT",
            "mocked": False, "live": False, "run_dir": rel(run_dir),
            "failed_gates": [f"journal_spoken_missing:{rel(spoken_path)}"],
        }

    spoken = spoken_path.read_text(encoding="utf-8").strip()

    # The tone comes from the dream's own tension, not from a caller's guess.
    mapper = _load_sibling("map_delivery_tone")
    contradictions: list[dict[str, Any]] = []
    cpath = run_dir / "contradiction_report.json"
    if cpath.is_file():
        contradictions = json.loads(cpath.read_text(encoding="utf-8")).get("contradictions") or []
    mood_label = args.mood_label
    if not mood_label:
        packet = run_dir / "dream_packet.json"
        if packet.is_file():
            sm = json.loads(packet.read_text(encoding="utf-8")).get("session_mood")
            if isinstance(sm, dict):
                mood_label = sm.get("mood_label")
    mapping = mapper.map_mood(mood_label, contradictions, args.intensity, args.valence)

    label = args.label or f"pd_journal_{run_dir.name}"
    request = {
        "answer_text": spoken[: args.max_chars],
        "label": label,
        "use_blessed_qra_cache": False,
        "asr_verify": bool(args.asr_verify),
        "asr_cache": False,
        "asr_max_candidates": 1,
        "voice_delivery": mapping["voice_delivery"],
        "ref_audio": args.ref_audio,
    }
    response = post_json(f"{CHATTERBOX}/synthesize-batch", request)

    engine = response.get("engine")
    normalized = response.get("normalized_tone")
    requested = mapping["voice_delivery"]["tone"]
    if normalized != requested:
        failed.append(f"tone_did_not_survive:requested={requested},normalized={normalized}")

    source = resolve_host_audio(str(response.get("finished_response_audio") or ""))
    dest = run_dir / "journal.wav"
    if source is None:
        failed.append(f"audio_not_found_on_host:{response.get('finished_response_audio')}")
    else:
        shutil.copyfile(source, dest)

    # The transcript is not top-level: it sits under the accepted candidate of
    # the first chunk's asr_verification. Reading `asr_transcript` returns None
    # and silently loses the only evidence that she said what was written.
    chunk = (response.get("chunks") or [{}])[0]
    verification = chunk.get("asr_verification") or {}
    candidates = verification.get("candidates") or []
    idx = verification.get("accepted_candidate_index") or 0
    accepted = candidates[idx] if idx < len(candidates) else (candidates[0] if candidates else {})
    asr = (accepted or {}).get("asr") or {}
    transcript = asr.get("transcript")
    asr_gate = asr.get("gate") or {}
    if args.asr_verify and verification.get("enabled") and not transcript:
        failed.append("asr_transcript_missing_despite_verification_enabled")

    receipt = {
        "schema": "persona_dream.journal_audio_receipt.v1",
        "created_at": utc_now(),
        "status": "PASS_JOURNAL_SPOKEN" if not failed else "BLOCKED_JOURNAL_AUDIO",
        "mocked": False,
        "live": True,
        "endpoint": f"POST {CHATTERBOX}/synthesize-batch",
        "run_dir": rel(run_dir),
        "spoken_text": rel(spoken_path),
        "spoken_text_sha256": sha_text(spoken),
        "spoken_chars": len(spoken),
        "truncated_to": args.max_chars if len(spoken) > args.max_chars else None,
        "audio": rel(dest) if dest.is_file() else None,
        "audio_sha256": sha_file(dest) if dest.is_file() else None,
        "audio_bytes": dest.stat().st_size if dest.is_file() else 0,
        "engine": engine,
        "persona_mood_label": mapping["persona_mood_label"],
        "dominant_tension_axis": mapping["dominant_tension_axis"],
        "requested_delivery_tone": requested,
        "normalized_delivery_tone": normalized,
        "tone_survived": normalized == requested,
        "asr_transcript": transcript,
        "asr_wer": asr_gate.get("wer"),
        "asr_ok": asr.get("ok"),
        "finished_response_metrics": response.get("finished_response_metrics"),
        "failed_gates": failed,
        "claims": {
            "proves": [
                "the journal text published for this run was rendered to audio by a live renderer",
                "the audio in the run directory is bound by hash to that exact spoken text",
                "the delivery tone derived from the dream's own tension survived normalization",
                "an independent transcription of the rendered audio was captured",
            ] if not failed else [],
            "does_not_prove": [
                "that the requested tone is audible in the waveform -- see #1209",
                "perceived emotion, naturalness, or human acceptance",
            ],
        },
    }
    out = Path(args.out) if args.out else run_dir / "JOURNAL_AUDIO_RECEIPT.json"
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--label", default=None)
    ap.add_argument("--mood-label", default=None)
    ap.add_argument("--intensity", type=float, default=0.6)
    ap.add_argument("--valence", type=float, default=-0.1)
    ap.add_argument("--ref-audio", default=DEFAULT_REF_AUDIO)
    ap.add_argument("--max-chars", type=int, default=1200,
                    help="Chatterbox chunks internally; this bounds a runaway entry.")
    ap.add_argument("--asr-verify", action="store_true", default=True)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    r = run(args)
    print(json.dumps(r, indent=2, sort_keys=True) if args.json else
          f"{r['status']}  audio={r.get('audio')}  tone={r.get('requested_delivery_tone')} "
          f"survived={r.get('tone_survived')}")
    return 0 if r["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
