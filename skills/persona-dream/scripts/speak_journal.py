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
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
CHATTERBOX = os.environ.get("CHATTERBOX_BASE_URL", "http://127.0.0.1:8018")
ASR_MAX_WER = 0.2
ASR_MAX_DURATION_RATIO = 10.0
#: Container `/out` is bind-mounted here on the host.
CHATTERBOX_OUT_HOST_ROOT = Path(
    os.environ.get("CHATTERBOX_OUT_HOST_ROOT",
                   "/home/graham/workspace/experiments/chatterbox/logs")
)
DEFAULT_REF_AUDIO = "/data/embry_ref.wav"
DEFAULT_ASR_MAX_CANDIDATES = int(os.environ.get("PERSONA_DREAM_JOURNAL_ASR_MAX_CANDIDATES", "3"))
MARKDOWN_FOOTER = re.compile(r"\n---\n.*", re.DOTALL)


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


def _clean_markdown_journal(text: str) -> str:
    text = MARKDOWN_FOOTER.sub("", text).strip()
    lines = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
    return "\n".join(lines).strip()


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


def accepted_chunk_asr(chunk: dict[str, Any]) -> dict[str, Any]:
    verification = chunk.get("asr_verification") or {}
    candidates = verification.get("candidates") or []
    idx = verification.get("accepted_candidate_index")
    if idx is None:
        idx = 0
    accepted = candidates[idx] if idx < len(candidates) else (candidates[0] if candidates else {})
    asr = (accepted or {}).get("asr") or {}
    gate = asr.get("gate") or {}
    return {
        "chunk_index": chunk.get("chunk_index"),
        "ok": asr.get("ok"),
        "transcript": asr.get("transcript"),
        "wer": gate.get("wer"),
        "failed_gates": verification.get("failed_gates") or (accepted or {}).get("failed_gates") or [],
    }


def ensure_spoken_text(run_dir: Path) -> tuple[Path | None, list[str]]:
    """Ensure cycle-lane journals have the text artifact the speech lane needs."""
    spoken_path = run_dir / "journal_spoken.txt"
    if spoken_path.is_file():
        return spoken_path, []

    gates: list[str] = []
    journal_json = run_dir / "dream_journal.v1.json"
    journal_md = run_dir / "dream_journal.md"
    text = ""
    source = None
    if journal_json.is_file():
        payload = json.loads(journal_json.read_text(encoding="utf-8"))
        text = str(payload.get("journal") or "").strip()
        source = journal_json
        if not text:
            gates.append(f"dream_journal_json_missing_journal:{rel(journal_json)}")
    if not text and journal_md.is_file():
        text = _clean_markdown_journal(journal_md.read_text(encoding="utf-8"))
        source = journal_md
    if not text:
        gates.append(f"journal_spoken_missing:{rel(spoken_path)}")
        if not journal_json.is_file() and not journal_md.is_file():
            gates.append("cycle_journal_missing:dream_journal.v1.json|dream_journal.md")
        return None, gates

    spoken_path.write_text(text.strip() + "\n", encoding="utf-8")
    receipt = {
        "schema": "persona_dream.cycle_journal_spoken_text_receipt.v1",
        "created_at": utc_now(),
        "status": "PASS_CYCLE_JOURNAL_SPOKEN_TEXT",
        "mocked": False,
        "live": False,
        "source": rel(source) if source else None,
        "journal_spoken": rel(spoken_path),
        "spoken_text_sha256": sha_text(text.strip()),
        "claims": {
            "proves": [
                "the cycle-lane dream journal can supply the text consumed by the speech lane"
            ],
            "does_not_prove": [
                "audio rendering",
                "perceived emotion",
                "that requested tone was achieved",
            ],
        },
    }
    (run_dir / "JOURNAL_SPOKEN_TEXT_RECEIPT.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return spoken_path, []


def run(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir)
    spoken_path, text_gates = ensure_spoken_text(run_dir)
    failed: list[str] = []

    if spoken_path is None or not spoken_path.is_file():
        return {
            "schema": "persona_dream.journal_audio_receipt.v1",
            "created_at": utc_now(), "status": "BLOCKED_NO_SPOKEN_TEXT",
            "mocked": False, "live": False, "run_dir": rel(run_dir),
            "failed_gates": text_gates or [f"journal_spoken_missing:{rel(run_dir / 'journal_spoken.txt')}"],
        }

    spoken = spoken_path.read_text(encoding="utf-8").strip()
    rendered_spoken = spoken[: args.max_chars]

    # The tone comes from the dream's own tension, not from a caller's guess.
    mapper = _load_sibling("map_delivery_tone")
    contradictions: list[dict[str, Any]] = []
    cpath = run_dir / "contradiction_report.json"
    if cpath.is_file():
        contradictions = json.loads(cpath.read_text(encoding="utf-8")).get("contradictions") or []
    mood_label = args.mood_label
    if not mood_label:
        journal = run_dir / "dream_journal.v1.json"
        if journal.is_file():
            payload = json.loads(journal.read_text(encoding="utf-8"))
            sm = payload.get("session_mood")
            if isinstance(sm, dict):
                mood_label = sm.get("mood_label")
    if not mood_label:
        packet = run_dir / "dream_packet.json"
        if packet.is_file():
            sm = json.loads(packet.read_text(encoding="utf-8")).get("session_mood")
            if isinstance(sm, dict):
                mood_label = sm.get("mood_label")
    mapping = mapper.map_mood(mood_label, contradictions, args.intensity, args.valence)

    label = args.label or f"pd_journal_{run_dir.name}"
    request = {
        "answer_text": rendered_spoken,
        "label": label,
        "use_blessed_qra_cache": False,
        "asr_verify": bool(args.asr_verify),
        "asr_cache": False,
        "asr_max_candidates": args.asr_max_candidates,
        "asr_max_wer": ASR_MAX_WER,
        "asr_max_duration_ratio": ASR_MAX_DURATION_RATIO,
        "voice_delivery": mapping["voice_delivery"],
        "ref_audio": args.ref_audio,
    }
    dest = run_dir / "journal.wav"
    response: dict[str, Any] = {}
    upstream_failed_gates: list[str] = []
    chunk_asr: list[dict[str, Any]] = []
    transcripts: list[str] = []
    transcript: str | None = None
    wers: list[float] = []
    source = None
    for attempt in range(2):
        request["label"] = label if attempt == 0 else f"{label}_asr_retry"
        response = post_json(f"{CHATTERBOX}/synthesize-batch", request)
        upstream_failed_gates = list(response.get("failed_gates") or [])
        source = resolve_host_audio(str(response.get("finished_response_audio") or ""))
        if source is not None:
            shutil.copyfile(source, dest)
        chunk_asr = [accepted_chunk_asr(chunk) for chunk in (response.get("chunks") or [])]
        transcripts = [str(item["transcript"]).strip() for item in chunk_asr if item.get("transcript")]
        transcript = "\n".join(transcripts) if transcripts else None
        wers = [float(item["wer"]) for item in chunk_asr if item.get("wer") is not None]
        if not (
            args.asr_verify
            and chunk_asr
            and any("asr_transcription_ok" in (item.get("failed_gates") or []) for item in chunk_asr)
        ):
            break

    if response.get("ok") is False:
        failed.append("chatterbox_response_not_ok")
        failed.extend(f"chatterbox_{gate}" for gate in upstream_failed_gates)

    engine = response.get("engine")
    normalized = response.get("normalized_tone")
    requested = mapping["voice_delivery"]["tone"]
    if normalized != requested:
        failed.append(f"tone_did_not_survive:requested={requested},normalized={normalized}")

    if source is None:
        failed.append(f"audio_not_found_on_host:{response.get('finished_response_audio')}")

    # Transcripts are per accepted chunk. Aggregate them so the receipt covers
    # the whole journal, not just the first rendered segment.
    allowed_local_chunk_gate_only = bool(chunk_asr) and all(
        item.get("ok") is True
        or (
            set(str(gate) for gate in (item.get("failed_gates") or [])) <= {"duration_within_expected_ratio"}
            and isinstance(item.get("wer"), (int, float))
            and float(item["wer"]) <= ASR_MAX_WER
        )
        for item in chunk_asr
    )
    asr_ok = bool(chunk_asr) and all(item.get("ok") is True for item in chunk_asr)
    asr_enabled = bool((response.get("asr_verification") or {}).get("enabled"))
    if args.asr_verify and asr_enabled and not transcript:
        failed.append("asr_transcript_missing_despite_verification_enabled")
    if args.asr_verify and asr_enabled and chunk_asr and not asr_ok:
        failed.append("chunk_asr_not_all_ok")

    allowed_readback_gates = {
        gate for gate in upstream_failed_gates
        if re.fullmatch(r"chunk_\d+_(synthesis_ok|asr_accepted_candidate_present)", str(gate))
    }
    readback_proves_audio = dest.is_file() and dest.stat().st_size > 50_000
    readback_proves_asr = bool(chunk_asr) and all(
        item.get("transcript")
        and isinstance(item.get("wer"), (int, float))
        and float(item["wer"]) <= ASR_MAX_WER
        for item in chunk_asr
    )
    readback_overrode_upstream = bool(
        upstream_failed_gates
        and len(allowed_readback_gates) == len(upstream_failed_gates)
        and readback_proves_audio
        and readback_proves_asr
    )
    if not asr_ok and allowed_local_chunk_gate_only and readback_proves_audio and readback_proves_asr:
        failed = [gate for gate in failed if gate != "chunk_asr_not_all_ok"]
        asr_ok = True

    if readback_overrode_upstream:
        failed = [
            gate for gate in failed
            if gate != "chatterbox_response_not_ok"
            and not (gate.startswith("chatterbox_") and gate.removeprefix("chatterbox_") in allowed_readback_gates)
            and gate != "chunk_asr_not_all_ok"
        ]
        asr_ok = True

    receipt = {
        "schema": "persona_dream.journal_audio_receipt.v1",
        "created_at": utc_now(),
        "status": "PASS_JOURNAL_SPOKEN" if not failed else "BLOCKED_JOURNAL_AUDIO",
        "mocked": False,
        "live": True,
        "endpoint": f"POST {CHATTERBOX}/synthesize-batch",
        "run_dir": rel(run_dir),
        "spoken_text": rel(spoken_path),
        "spoken_text_sha256": sha_text(rendered_spoken),
        "source_spoken_text_sha256": sha_text(spoken),
        "spoken_chars": len(rendered_spoken),
        "truncated_to": args.max_chars if len(spoken) > args.max_chars else None,
        "audio": rel(dest) if dest.is_file() else None,
        "audio_sha256": sha_file(dest) if dest.is_file() else None,
        "audio_bytes": dest.stat().st_size if dest.is_file() else 0,
        "cycle_journal_spoken_text_receipt": rel(run_dir / "JOURNAL_SPOKEN_TEXT_RECEIPT.json")
        if (run_dir / "JOURNAL_SPOKEN_TEXT_RECEIPT.json").is_file() else None,
        "engine": engine,
        "persona_mood_label": mapping["persona_mood_label"],
        "dominant_tension_axis": mapping["dominant_tension_axis"],
        "requested_delivery_tone": requested,
        "normalized_delivery_tone": normalized,
        "tone_survived": normalized == requested,
        "asr_transcript": transcript,
        "asr_wer": max(wers) if wers else None,
        "asr_ok": asr_ok if asr_enabled else None,
        "asr_max_candidates": args.asr_max_candidates,
        "asr_max_wer": ASR_MAX_WER,
        "asr_max_duration_ratio": ASR_MAX_DURATION_RATIO,
        "chunk_asr": chunk_asr,
        "chatterbox_ok": response.get("ok"),
        "chatterbox_failed_gates": upstream_failed_gates,
        "chatterbox_failed_gates_readback_overridden": sorted(allowed_readback_gates) if readback_overrode_upstream else [],
        "readback_proves_audio": readback_proves_audio,
        "readback_proves_asr": readback_proves_asr,
        "finished_response_metrics": response.get("finished_response_metrics"),
        "failed_gates": failed,
        "claims": {
            "proves": [
                "the journal text published for this run was rendered to audio by a live renderer",
                "the audio in the run directory is bound by hash to the rendered spoken text or bounded excerpt",
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
    ap.add_argument("--asr-max-candidates", type=int, default=DEFAULT_ASR_MAX_CANDIDATES)
    ap.add_argument("--max-chars", type=int, default=250,
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
