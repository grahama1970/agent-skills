"""#1127 fail-closed fixtures for the pre-rater technical confound screen.

The live proof is that the screen blocked the real bundle: the dream and
adversarial stimuli are ~4.2 and ~3.7 LKFS louder than neutral against a
same-parameter neutral spread of sd 0.79 (tolerance 2.38). These fixtures pin
the behaviours that must stay fail-closed so a later change cannot quietly
tune the screen until the existing WAVs pass.
"""
import importlib.util
import json
import math
from pathlib import Path

import numpy as np
import pytest

soundfile = pytest.importorskip("soundfile")
pytest.importorskip("librosa")

ROOT = Path(__file__).resolve().parents[1]
SR = 24000


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


screen = _load("technical_screen_blinded_listener_study")

TEXT = "I need you to wait before you commit to that plan."


def _speechlike(seconds: float = 3.0, *, amp: float = 0.2, f0: float = 190.0,
                seed: int = 0, tone_hz: float | None = None, tone_amp: float = 0.0,
                noise_floor: float = 0.0004) -> np.ndarray:
    """A crude voiced signal: harmonic stack, a pause, and a noise floor."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * SR)) / SR
    sig = np.zeros_like(t)
    for harmonic, weight in ((1, 1.0), (2, 0.5), (3, 0.25), (4, 0.12)):
        sig += weight * np.sin(2 * np.pi * f0 * harmonic * t + rng.uniform(0, 0.1))
    sig *= amp / np.max(np.abs(sig))
    # One interior pause so pause diagnostics have something to find.
    gap = slice(int(0.45 * len(t)), int(0.55 * len(t)))
    sig[gap] *= 0.001
    sig += rng.normal(0, noise_floor, size=sig.shape)
    if tone_hz and tone_amp:
        sig += tone_amp * np.sin(2 * np.pi * tone_hz * t)
    return sig.astype(np.float32)


def _write(path: Path, samples: np.ndarray) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    soundfile.write(str(path), samples, SR, subtype="PCM_16")
    return path


def _bundle(tmp_path: Path, conditions: dict[str, np.ndarray], *,
            neutral_seeds: int = 8, neutral_kwargs: dict | None = None) -> Path:
    """A minimal study dir: prereg, stimuli, neutral calibration, ASR receipt."""
    study = tmp_path / "study"
    (study / "stimuli").mkdir(parents=True)
    neutral_dir = study / screen.NEUTRAL_DIR_NAME
    neutral_dir.mkdir(parents=True)

    renders = []
    for idx in range(1, neutral_seeds + 1):
        wav = _write(neutral_dir / f"neutral_{idx:02d}.wav",
                     _speechlike(seed=idx, **(neutral_kwargs or {})))
        renders.append({"index": idx, "wav": str(wav), "wav_sha256": screen.sha_file(wav),
                        "engine": "chatterbox_base"})
    (neutral_dir / "NEUTRAL_CALIBRATION_MANIFEST.json").write_text(
        json.dumps({"schema": "persona_dream.technical_screen_neutral_calibration.v1",
                    "live": True, "mocked": False, "render_count": len(renders),
                    "renders": renders}, indent=2), encoding="utf-8")

    stimuli, manifest = [], []
    for slot, (condition, samples) in enumerate(conditions.items(), start=1):
        wav = _write(study / "stimuli" / f"{condition}.wav", samples)
        stimuli.append({
            "condition": condition,
            "audio": str(wav),
            "sha256": screen.sha_file(wav),
            "bytes": wav.stat().st_size,
            "engine": "chatterbox_base",
            "voice_delivery": {"tone": condition, "intensity": 0.5, "valence": 0.0},
        })
        manifest.append({"condition": condition, "slot": slot, "stimulus_id": f"S{slot:02d}"})
    (study / "PREREGISTRATION.json").write_text(json.dumps({
        "schema": "persona_dream.blinded_listener_study.v1",
        "stimuli": stimuli,
        "presentation_manifest": manifest,
        "stimulus_source": {"answer_text": TEXT, "engine": "chatterbox_base",
                            "reference": "/data/embry_ref.wav"},
    }, indent=2), encoding="utf-8")
    (study / "STIMULUS_VALIDATION_RECEIPT.json").write_text(json.dumps({
        "status": "PASS_BLINDED_LISTENER_STUDY_READY_FOR_HUMAN_RATERS",
        "stimuli": [{"condition": c, "asr": {"transcript": TEXT, "wer": 0.0}}
                    for c in conditions],
    }, indent=2), encoding="utf-8")
    return study


def _run(study: Path, tmp_path: Path):
    args = type("Args", (), {
        "study_dir": study,
        "out": tmp_path / "receipt.json",
        "manifest_out": tmp_path / "manifest.json",
        "render_neutral": 0,
        "min_neutral": 4,
        "ref_audio": "/data/embry_ref.wav",
    })()
    return screen.run(args)


def _matched_conditions() -> dict[str, np.ndarray]:
    """Four conditions that differ only by pitch, an intended mediator."""
    return {
        "control": _speechlike(seed=101, f0=190.0),
        "baseline": _speechlike(seed=102, f0=196.0),
        "dream": _speechlike(seed=103, f0=186.0),
        "adversarial": _speechlike(seed=104, f0=200.0),
    }


def test_matched_stimuli_pass(tmp_path):
    got = _run(_bundle(tmp_path, _matched_conditions()), tmp_path)
    assert got["status"] == "PASS_STIMULUS_TECHNICAL_SCREEN", got["failed_gates"]
    assert got["neutral_render_count"] == 8


def test_loudness_offset_blocks(tmp_path):
    """The real-bundle failure mode: one condition louder than neutral spread."""
    conditions = _matched_conditions()
    conditions["dream"] = _speechlike(seed=103, f0=186.0, amp=0.45)

    got = _run(_bundle(tmp_path, conditions), tmp_path)

    assert got["status"] == "BLOCKED_STIMULUS_TECHNICAL_CONFOUND"
    assert any("k_weighted_loudness_lkfs" in gate and "dream" in gate
               for gate in got["failed_gates"]), got["failed_gates"]


def test_injected_4900hz_line_blocks(tmp_path):
    conditions = _matched_conditions()
    conditions["dream"] = _speechlike(seed=103, f0=186.0, tone_hz=4900.0, tone_amp=0.05)

    got = _run(_bundle(tmp_path, conditions), tmp_path)

    assert got["status"] == "BLOCKED_STIMULUS_TECHNICAL_CONFOUND"
    assert any("band_4900_prominence_db" in gate for gate in got["failed_gates"]), got["failed_gates"]


def test_noise_floor_elevation_blocks(tmp_path):
    conditions = _matched_conditions()
    conditions["adversarial"] = _speechlike(seed=104, f0=200.0, noise_floor=0.02)

    got = _run(_bundle(tmp_path, conditions), tmp_path)

    assert got["status"] == "BLOCKED_STIMULUS_TECHNICAL_CONFOUND"
    assert any("silence_floor_dbfs" in gate for gate in got["failed_gates"]), got["failed_gates"]


def test_clipping_blocks_on_hard_gate(tmp_path):
    conditions = _matched_conditions()
    clipped = _speechlike(seed=103, f0=186.0, amp=0.2)
    clipped[: int(0.2 * len(clipped))] = 1.0
    conditions["dream"] = clipped

    got = _run(_bundle(tmp_path, conditions), tmp_path)

    assert got["status"] == "BLOCKED_STIMULUS_TECHNICAL_CONFOUND"
    assert "clipping_exceeds_hard_gate:dream" in got["failed_gates"]


def test_truncation_blocks(tmp_path):
    conditions = _matched_conditions()
    conditions["dream"] = _speechlike(seconds=1.2, seed=103, f0=186.0)

    got = _run(_bundle(tmp_path, conditions), tmp_path)

    assert got["status"] == "BLOCKED_STIMULUS_TECHNICAL_CONFOUND"
    assert any("duration_s" in gate for gate in got["failed_gates"]), got["failed_gates"]


def test_asr_drift_and_repetition_block(tmp_path):
    study = _bundle(tmp_path, _matched_conditions())
    receipt = json.loads((study / "STIMULUS_VALIDATION_RECEIPT.json").read_text())
    receipt["stimuli"][2]["asr"] = {
        "transcript": "wait wait wait wait wait wait", "wer": 0.6,
    }
    (study / "STIMULUS_VALIDATION_RECEIPT.json").write_text(json.dumps(receipt), encoding="utf-8")

    got = _run(study, tmp_path)

    assert got["status"] == "BLOCKED_STIMULUS_TECHNICAL_CONFOUND"
    assert any("asr_wer_exceeds_hard_gate" in gate for gate in got["failed_gates"])
    assert any("repetition_exceeds_hard_gate" in gate for gate in got["failed_gates"])


def test_backend_mismatch_blocks(tmp_path):
    study = _bundle(tmp_path, _matched_conditions())
    prereg = json.loads((study / "PREREGISTRATION.json").read_text())
    prereg["stimuli"][2]["engine"] = "chatterbox_turbo"
    (study / "PREREGISTRATION.json").write_text(json.dumps(prereg), encoding="utf-8")

    got = _run(study, tmp_path)

    assert got["status"] == "BLOCKED_STIMULUS_TECHNICAL_CONFOUND"
    assert any("backend_mismatch_across_conditions" in gate for gate in got["failed_gates"])


def test_selective_post_processing_blocks(tmp_path):
    """Denoising only one condition must fail, not silently pass."""
    conditions = _matched_conditions()
    quiet = _speechlike(seed=103, f0=186.0, noise_floor=1e-7)
    conditions["dream"] = quiet

    got = _run(_bundle(tmp_path, conditions), tmp_path)

    assert got["status"] == "BLOCKED_STIMULUS_TECHNICAL_CONFOUND"
    assert any("silence_floor_dbfs" in gate for gate in got["failed_gates"]), got["failed_gates"]


def test_missing_neutral_calibration_blocks(tmp_path):
    study = _bundle(tmp_path, _matched_conditions())
    (study / screen.NEUTRAL_DIR_NAME / "NEUTRAL_CALIBRATION_MANIFEST.json").unlink()

    got = _run(study, tmp_path)

    assert got["status"] == "BLOCKED_STIMULUS_TECHNICAL_CONFOUND"
    assert "neutral_calibration_set_missing" in got["failed_gates"]


def test_tampered_neutral_render_blocks(tmp_path):
    study = _bundle(tmp_path, _matched_conditions())
    path = study / screen.NEUTRAL_DIR_NAME / "NEUTRAL_CALIBRATION_MANIFEST.json"
    manifest = json.loads(path.read_text())
    manifest["renders"][0]["wav_sha256"] = "sha256:" + "0" * 64
    path.write_text(json.dumps(manifest), encoding="utf-8")

    got = _run(study, tmp_path)

    assert got["status"] == "BLOCKED_STIMULUS_TECHNICAL_CONFOUND"
    assert any("neutral_render_hash_mismatch" in gate for gate in got["failed_gates"])


def test_raw_rows_survive_a_block(tmp_path):
    """Blocking must not hide the measurements that caused it."""
    conditions = _matched_conditions()
    conditions["dream"] = _speechlike(seed=103, f0=186.0, amp=0.45)
    study = _bundle(tmp_path, conditions)

    got = _run(study, tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text())

    assert got["status"] == "BLOCKED_STIMULUS_TECHNICAL_CONFOUND"
    assert len(manifest["condition_metrics_raw"]) == 4
    assert manifest["neutral_metrics_raw"]
    assert manifest["comparison_rows"]
    assert got["nuisance_rows_outside_neutral_spread"]


def test_pass_does_not_claim_emotion(tmp_path):
    got = _run(_bundle(tmp_path, _matched_conditions()), tmp_path)
    proves = " ".join(got["claims"]["proves"]).lower()
    does_not = " ".join(got["claims"]["does_not_prove"]).lower()
    assert "emotion" not in proves
    assert "perceived emotion" in does_not
