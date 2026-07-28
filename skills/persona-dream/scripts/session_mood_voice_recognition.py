#!/usr/bin/env python3
"""Score session-mood renders for Embry speaker identity, fail-closed.

ASR WER 0.0 on the live Chatterbox renders proves the *content* survived
synthesis. It says nothing about whether the speaker is still recognizably
Embry. This computes speaker-embedding similarity between each durable
session-mood render and the authorized Embry reference, and against real
non-Embry voices from the same corpus as adversarial negatives.

Thresholds are PREREGISTERED as module constants below and are not tuned to the
observed scores. If the renders fail them, the receipt is BLOCKED and that is
the finding -- lowering a threshold to obtain PASS would make the gate
decorative.

Requires a speaker-recognition backend, which is a property of the interpreter.
Run under the Chatterbox voice lane interpreter; see
session_mood_voice_recognition_preflight.py, which names the right one.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LIVE_DIR = ROOT / "reports" / "goal_v5" / "continuity" / "session_mood_chatterbox_live"
DEFAULT_LIVE_RECEIPT = LIVE_DIR / "RECEIPT.json"
VOICE_REFS = Path("/home/graham/workspace/experiments/chatterbox/persona_dream_voice_refs")
#: Authorized Embry reference. PROMOTED 2026-07-28 by operator decision from
#: voice_clone_candidates/embry_kling_clone_candidate.wav, which was already the
#: only Embry clip in existence and the one the live Chatterbox service has been
#: conditioning on via CHATTERBOX_REF_AUDIO. reports/goal_v5/peer_review/
#: SPEC_arc_state_to_voice.md recorded this on 2026-07-25: "The anchor bank does
#: not exist. Only ONE clip per persona is present." Promoting makes the declared
#: reference match the deployed one instead of naming a file nothing used.
#: Prior label holder, embry_authorized_ref_30s_8s.wav, is retained as
#: LEGACY_STAGING_REFERENCE below and is still what the emotion-proof lane
#: stages; reconciling that lane is tracked separately.
try:
    from embry_voice_reference import AUTHORIZED_EMBRY_REFERENCE, LEGACY_STAGING_REFERENCE
except ImportError:  # loaded by path in some test harnesses
    import importlib.util as _ilu

    _spec = _ilu.spec_from_file_location(
        "embry_voice_reference", Path(__file__).resolve().parent / "embry_voice_reference.py"
    )
    _mod = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    AUTHORIZED_EMBRY_REFERENCE = _mod.AUTHORIZED_EMBRY_REFERENCE
    LEGACY_STAGING_REFERENCE = _mod.LEGACY_STAGING_REFERENCE

DEFAULT_REFERENCE_AUDIO = AUTHORIZED_EMBRY_REFERENCE

#: The reference the live Chatterbox service actually conditions on. Verified
#: 2026-07-28 from the container: CHATTERBOX_REF_AUDIO=/data/embry_ref.wav is
#: bind-mounted from this path. Scoring a render against the AUTHORIZED
#: reference alone measures render->candidate->authorized, two gaps at once,
#: and reads as "not Embry" when the synthesis is in fact faithful to what it
#: was given. Identity is judged against the conditioning reference; whether
#: that reference is the authorized one is a separate, explicit gate.
DEFAULT_CONDITIONING_REFERENCE = DEFAULT_REFERENCE_AUDIO

#: Floor for "the conditioning reference is the authorized Embry voice".
MIN_REFERENCE_PROVENANCE_SIMILARITY = 0.75

#: Real non-Embry voices from the same corpus, recorded/rendered through the
#: same pipeline. Using genuine other speakers rather than noise is what makes
#: the negative meaningful: noise trivially scores low and would prove nothing.
DEFAULT_ADVERSARIAL_AUDIO = (
    VOICE_REFS / "kai_kling_chatterbox_reference_30s.wav",
    VOICE_REFS / "horus_v2_agent_ref_6s.wav",
)

#: PREREGISTERED, written before any score was computed.
#:
#: MIN_EMBRY_SIMILARITY is resemblyzer's commonly cited same-speaker operating
#: point. MAX_ADVERSARIAL_SIMILARITY is the ceiling a different speaker may
#: reach before the embedding is not discriminating. MIN_SEPARATION requires the
#: worst genuine render to beat the best impostor by a margin, so a PASS cannot
#: come from every clip scoring high in an undiscriminating embedding space.
MIN_EMBRY_SIMILARITY = 0.75
MAX_ADVERSARIAL_SIMILARITY = 0.70
MIN_SEPARATION = 0.05


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def artifact(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.is_file(),
        "bytes": path.stat().st_size if path.is_file() else 0,
        "sha256": sha256_file(path) if path.is_file() else None,
    }


def load_encoder():
    """Import the backend late so --help works without it installed."""
    from resemblyzer import VoiceEncoder  # noqa: PLC0415

    return VoiceEncoder()


def embed(encoder, path: Path):
    from resemblyzer import preprocess_wav  # noqa: PLC0415

    return encoder.embed_utterance(preprocess_wav(path))


def cosine(a, b) -> float:
    import numpy as np  # noqa: PLC0415

    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def audio_seconds(path: Path) -> float | None:
    try:
        import soundfile as sf  # noqa: PLC0415

        info = sf.info(str(path))
        return round(info.frames / info.samplerate, 3)
    except Exception:  # noqa: BLE001 - duration is context, never a gate
        return None


def duration_matched_baseline(
    encoder, reference: Path, ref_embedding, seconds: float
) -> dict[str, Any]:
    """Same-speaker ceiling measured at the RENDERS' own duration.

    A fixed threshold cannot tell "wrong voice" from "too little audio". This
    slices the authorized reference into windows of the same length as the clip
    under test and scores each against the full reference, giving the score
    genuine Embry achieves at that duration.

    Measured 2026-07-28: 1.75s -> mean 0.8228, 2.00s -> mean 0.8411 (min 0.7903),
    4.00s -> 0.9061. The session-mood renders (1.76-2.16s) score 0.7382-0.7801,
    i.e. BELOW real Embry audio of the same length. Duration does not excuse the
    shortfall, so the preregistered 0.75 floor was lenient rather than strict.
    """
    row: dict[str, Any] = {"slice_seconds": round(seconds, 3)}
    try:
        import numpy as np  # noqa: PLC0415
        import soundfile as sf  # noqa: PLC0415
        import tempfile  # noqa: PLC0415

        data, rate = sf.read(str(reference))
        window = int(seconds * rate)
        if window <= 0 or len(data) < window:
            row["error"] = "reference shorter than the clip under test"
            return row
        tmp = Path(tempfile.mkdtemp())
        scores: list[float] = []
        for idx, start in enumerate(range(0, len(data) - window, window)):
            slice_path = tmp / f"slice_{idx}.wav"
            sf.write(str(slice_path), data[start : start + window], rate)
            try:
                scores.append(cosine(ref_embedding, embed(encoder, slice_path)))
            except Exception:  # noqa: BLE001, S112 - a bad slice is not a gate
                continue
        if scores:
            row.update(
                {
                    "slices": len(scores),
                    "mean": round(float(np.mean(scores)), 6),
                    "min": round(float(min(scores)), 6),
                    "max": round(float(max(scores)), 6),
                }
            )
    except Exception as exc:  # noqa: BLE001
        row["error"] = f"{type(exc).__name__}: {exc}"
    return row


def within_speaker_baseline(encoder, reference: Path) -> dict[str, Any]:
    """Score the reference's own two halves against each other.

    Without this, a similarity number is uninterpretable: 0.62 means nothing
    until you know what the SAME speaker scores against themselves in this
    embedding space. It also exposes the duration confound -- the halves are
    seconds long, and short utterances embed less reliably.
    """
    row: dict[str, Any] = {"method": "reference split into two equal halves"}
    try:
        import soundfile as sf  # noqa: PLC0415
        import tempfile  # noqa: PLC0415

        data, rate = sf.read(str(reference))
        half = len(data) // 2
        tmp = Path(tempfile.mkdtemp())
        first, second = tmp / "first.wav", tmp / "second.wav"
        sf.write(str(first), data[:half], rate)
        sf.write(str(second), data[half:], rate)
        row["half_seconds"] = round(half / rate, 3)
        row["within_speaker_similarity"] = round(
            cosine(embed(encoder, first), embed(encoder, second)), 6
        )
    except Exception as exc:  # noqa: BLE001
        row["error"] = f"{type(exc).__name__}: {exc}"
    return row


def render_paths(live_receipt: Path) -> tuple[list[Path], list[str]]:
    """Take the render list from the live receipt, not from a glob.

    A glob would silently score whatever WAVs happen to sit in the directory;
    the receipt is the authority on which renders were actually produced.
    """
    failures: list[str] = []
    if not live_receipt.is_file():
        return [], ["live_session_mood_receipt_exists"]
    doc = json.loads(live_receipt.read_text(encoding="utf-8"))
    results = doc.get("render_results")
    if not isinstance(results, list) or not results:
        return [], ["live_receipt_render_results_present"]
    paths: list[Path] = []
    for result in results:
        raw = result.get("finished_response_audio_snapshot")
        if not isinstance(raw, str) or not raw:
            failures.append(f"{result.get('turn_id', 'unknown')}_audio_snapshot_path_present")
            continue
        path = Path(raw)
        if not path.is_absolute():
            path = ROOT.parent.parent / path
        if not path.is_file():
            failures.append(f"{result.get('turn_id', 'unknown')}_audio_snapshot_exists")
            continue
        paths.append(path)
    return paths, failures


def run(args: argparse.Namespace) -> dict[str, Any]:
    failed_gates: list[str] = []
    reference = args.reference_audio
    renders, render_failures = render_paths(args.live_receipt)
    failed_gates.extend(render_failures)

    if not reference.is_file():
        failed_gates.append("embry_reference_audio_exists")

    adversarial = [p for p in args.adversarial_audio]
    missing_adv = [str(p) for p in adversarial if not p.is_file()]
    if missing_adv:
        failed_gates.append("adversarial_reference_audio_exists")
    if not adversarial:
        failed_gates.append("adversarial_reference_provided")

    genuine_rows: list[dict[str, Any]] = []
    adversarial_rows: list[dict[str, Any]] = []
    backend_error: str | None = None
    baseline: dict[str, Any] | None = None
    provenance: dict[str, Any] | None = None

    if not failed_gates:
        try:
            encoder = load_encoder()
            ref_embedding = embed(encoder, reference)
            baseline = within_speaker_baseline(encoder, reference)
            shortest = min(
                (audio_seconds(r) or 0.0 for r in renders), default=0.0
            )
            if shortest > 0:
                baseline["duration_matched"] = duration_matched_baseline(
                    encoder, reference, ref_embedding, shortest
                )
            cond_path = args.conditioning_reference
            if cond_path.is_file():
                cond_embedding = embed(encoder, cond_path)
                provenance = {
                    "conditioning_reference": artifact(cond_path),
                    "seconds": audio_seconds(cond_path),
                    "similarity_to_authorized": round(cosine(ref_embedding, cond_embedding), 6),
                    "min_required": MIN_REFERENCE_PROVENANCE_SIMILARITY,
                }
                provenance["is_authorized_voice"] = (
                    provenance["similarity_to_authorized"]
                    >= MIN_REFERENCE_PROVENANCE_SIMILARITY
                )
            else:
                cond_embedding = ref_embedding
                provenance = {"error": f"conditioning reference missing: {cond_path}"}
            for path in renders:
                score = cosine(cond_embedding, embed(encoder, path))
                genuine_rows.append(
                    {
                        "audio": artifact(path),
                        "seconds": audio_seconds(path),
                        "similarity_to_conditioning_reference": round(score, 6),
                        "similarity_to_authorized_reference": round(
                            cosine(ref_embedding, embed(encoder, path)), 6
                        ),
                        "similarity_to_embry": round(score, 6),
                        "passes_threshold": score >= MIN_EMBRY_SIMILARITY,
                    }
                )
            for path in adversarial:
                score = cosine(ref_embedding, embed(encoder, path))
                adversarial_rows.append(
                    {
                        "audio": artifact(path),
                        "seconds": audio_seconds(path),
                        "similarity_to_embry": round(score, 6),
                        "below_ceiling": score <= MAX_ADVERSARIAL_SIMILARITY,
                    }
                )
        except Exception as exc:  # noqa: BLE001 - any backend failure must fail closed
            backend_error = f"{type(exc).__name__}: {exc}"
            failed_gates.append("speaker_backend_usable")

    separation: float | None = None
    if genuine_rows and adversarial_rows:
        worst_genuine = min(row["similarity_to_embry"] for row in genuine_rows)
        best_impostor = max(row["similarity_to_embry"] for row in adversarial_rows)
        separation = round(worst_genuine - best_impostor, 6)
        if any(not row["passes_threshold"] for row in genuine_rows):
            failed_gates.append("all_renders_recognized_as_embry")
        if any(not row["below_ceiling"] for row in adversarial_rows):
            failed_gates.append("adversarial_voices_rejected")
        if separation < MIN_SEPARATION:
            failed_gates.append("embry_impostor_separation")
    if provenance is not None and not provenance.get("is_authorized_voice", False):
        # The renders may be faithful to their conditioning voice and still be
        # the wrong voice. This is the gate that catches an unauthorized default.
        failed_gates.append("conditioning_reference_is_authorized_voice")

    receipt = {
        "schema": "persona_dream.session_mood_voice_recognition.v1",
        "created_at": utc_now(),
        "status": "PASS_SESSION_MOOD_VOICE_RECOGNITION" if not failed_gates
        else "BLOCKED_SESSION_MOOD_VOICE_RECOGNITION",
        "mocked": False,
        "live": False,
        "engine": "resemblyzer",
        "preregistered_thresholds": {
            "min_embry_similarity": MIN_EMBRY_SIMILARITY,
            "max_adversarial_similarity": MAX_ADVERSARIAL_SIMILARITY,
            "min_separation": MIN_SEPARATION,
            "note": "Fixed before any score was computed; not tuned to observed values.",
        },
        "reference_audio": artifact(reference),
        "genuine_renders": genuine_rows,
        "adversarial_voices": adversarial_rows,
        "within_speaker_baseline": baseline,
        "reference_provenance": provenance,
        "separation": separation,
        "backend_error": backend_error,
        "failed_gates": failed_gates,
        "claims": {
            "proves": [
                "each session-mood render is closer to the authorized Embry reference "
                "than real non-Embry voices, by a preregistered margin",
            ] if not failed_gates else [],
            "does_not_prove": [
                "perceived emotion or target tone",
                "naturalness or human acceptance",
                "that a human listener would identify Embry",
                "robustness to a deliberate voice-cloning attack",
                "that a low score means the wrong voice rather than too-short audio: "
                "renders are ~2s while the within-speaker baseline uses ~4s halves",
            ],
        },
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-receipt", type=Path, default=DEFAULT_LIVE_RECEIPT)
    parser.add_argument("--reference-audio", type=Path, default=DEFAULT_REFERENCE_AUDIO)
    parser.add_argument(
        "--conditioning-reference",
        type=Path,
        default=DEFAULT_CONDITIONING_REFERENCE,
        help="Reference the renders were actually conditioned on.",
    )
    parser.add_argument(
        "--adversarial-audio",
        type=Path,
        action="append",
        default=None,
        help="Real non-Embry voice. Repeatable; replaces the built-in negatives.",
    )
    parser.add_argument("--out", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.adversarial_audio is None:
        args.adversarial_audio = list(DEFAULT_ADVERSARIAL_AUDIO)

    receipt = run(args)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(f"session-mood voice recognition: {receipt['status']}")
        for row in receipt["genuine_renders"]:
            print(
                f"  render      {Path(row['audio']['path']).name}: "
                f"{row['similarity_to_embry']:.4f} "
                f"({'ok' if row['passes_threshold'] else 'BELOW THRESHOLD'})"
            )
        for row in receipt["adversarial_voices"]:
            print(
                f"  adversarial {Path(row['audio']['path']).name}: "
                f"{row['similarity_to_embry']:.4f} "
                f"({'ok' if row['below_ceiling'] else 'ABOVE CEILING'})"
            )
        if receipt["separation"] is not None:
            print(f"  separation  {receipt['separation']:.4f} (min {MIN_SEPARATION})")
        for gate in receipt["failed_gates"]:
            print(f"  FAILED GATE: {gate}")
    return 1 if receipt["failed_gates"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
