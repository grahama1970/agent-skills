"""test_render_blinded_listener_stimuli - tests.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


renderer = _load("render_blinded_listener_stimuli")


TEXT = "I need you to wait before you commit to that plan, because the constraint changed this morning."


def _fake_normalize(raw_audio: Path, final_audio: Path) -> dict:
    final_audio.parent.mkdir(parents=True, exist_ok=True)
    final_audio.write_bytes(raw_audio.read_bytes())
    return {
        "command": ["fake-ffmpeg"],
        "exit_code": 0,
        "stdout": "",
        "stderr": "",
    }


def _prereg(study: Path) -> dict:
    stimuli = []
    manifest = []
    for idx, condition in enumerate(("control", "baseline", "dream", "adversarial"), start=1):
        stimuli.append(
            {
                "condition": condition,
                "audio": str(study / "stimuli" / f"{condition}.wav"),
                "bytes": 0,
                "sha256": "sha256:old",
                "engine": "chatterbox_base",
                "voice_delivery": {
                    "tone": "neutral" if condition == "control" else condition,
                    "intensity": 0.0 if condition == "control" else 0.6,
                    "valence": 0.0 if condition == "control" else -0.2,
                },
            }
        )
        manifest.append({"condition": condition, "slot": idx, "stimulus_id": f"S{idx:02d}"})
    return {
        "schema": "persona_dream.blinded_listener_study.v1",
        "stimulus_source": {"answer_text": TEXT, "engine": "chatterbox_base"},
        "presentation_manifest": manifest,
        "stimuli": stimuli,
    }


def _write_study(tmp_path: Path) -> Path:
    study = tmp_path / "study"
    study.mkdir()
    prereg = _prereg(study)
    for name in ("PREREGISTRATION.json", "PREREGISTRATION_V2.json"):
        (study / name).write_text(json.dumps(prereg, indent=2), encoding="utf-8")
    return study


def _response(condition: str, *, norm_loudness=True) -> dict:
    return {
        "ok": True,
        "engine": "chatterbox_base",
        "finished_response_audio": f"/out/{condition}.wav",
        "cache_material": {
            "generation_params": {"norm_loudness": norm_loudness},
            "reference_audio": {"norm_loudness": norm_loudness},
        },
        "chunks": [
            {
                "generation_params": {"norm_loudness": norm_loudness},
                "asr_verification": {
                    "accepted_candidate_index": 0,
                    "candidates": [
                        {
                            "asr": {
                                "transcript": TEXT,
                                "gate": {"ok": True, "wer": 0.0, "failed_gates": []},
                            }
                        }
                    ],
                }
            }
        ],
        "affect_effect": {"applied": True},
        "finished_response_metrics": {"duration_seconds": 3.1, "bytes": 128},
    }


def test_render_updates_both_preregs_with_shared_norm_loudness(monkeypatch, tmp_path):
    study = _write_study(tmp_path)
    host_root = tmp_path / "chatterbox_logs"
    host_root.mkdir()
    for condition in ("control", "baseline", "dream", "adversarial"):
        (host_root / f"{condition}.wav").write_bytes(b"RIFFfixtureWAVE" + condition.encode())
    monkeypatch.setattr(renderer, "CHATTERBOX_OUT_HOST_ROOT", host_root)
    monkeypatch.setattr(renderer, "normalize_wav", _fake_normalize)
    seen_requests = []

    def fake_post_json(url, payload, timeout=900):
        seen_requests.append(payload)
        condition = payload["label"].rsplit("_", 1)[-1]
        return _response(condition)

    monkeypatch.setattr(renderer, "get_json", lambda url: {"supported_params": ["norm_loudness"], "voice_backends": {}})
    monkeypatch.setattr(renderer, "post_json", fake_post_json)
    out = study / "RENDER_STIMULI_RECEIPT.json"
    args = type(
        "Args",
        (),
        {
            "study_dir": study,
            "out": out,
            "run_id": "unit",
            "ref_audio": "/data/embry_ref.wav",
            "norm_loudness": True,
            "json": True,
        },
    )()

    receipt = renderer.run(args)

    assert receipt["status"] == "PASS_RENDERED_BLINDED_LISTENER_STIMULI"
    assert {request["norm_loudness"] for request in seen_requests} == {True}
    assert len(seen_requests) == 4
    for name in ("PREREGISTRATION.json", "PREREGISTRATION_V2.json"):
        prereg = json.loads((study / name).read_text(encoding="utf-8"))
        assert prereg["stimulus_source"]["normalization_policy"]["norm_loudness"] is True
        assert {s["normalization_policy_sha256"] for s in prereg["stimuli"]}
        assert {s["post_processing_sha256"] for s in prereg["stimuli"]}
        assert all(s["sha256"].startswith("sha256:") and s["sha256"] != "sha256:old" for s in prereg["stimuli"])
        assert all(s["raw_sha256"].startswith("sha256:") for s in prereg["stimuli"])
        assert all(Path(s["audio"]).is_file() for s in prereg["stimuli"])


def test_render_blocks_on_norm_loudness_echo_mismatch(monkeypatch, tmp_path):
    study = _write_study(tmp_path)
    host_root = tmp_path / "chatterbox_logs"
    host_root.mkdir()
    for condition in ("control", "baseline", "dream", "adversarial"):
        (host_root / f"{condition}.wav").write_bytes(b"RIFFfixtureWAVE" + condition.encode())
    monkeypatch.setattr(renderer, "CHATTERBOX_OUT_HOST_ROOT", host_root)
    monkeypatch.setattr(renderer, "normalize_wav", _fake_normalize)

    def fake_post_json(url, payload, timeout=900):
        condition = payload["label"].rsplit("_", 1)[-1]
        return _response(condition, norm_loudness=False if condition == "dream" else True)

    monkeypatch.setattr(renderer, "get_json", lambda url: {"supported_params": ["norm_loudness"], "voice_backends": {}})
    monkeypatch.setattr(renderer, "post_json", fake_post_json)
    args = type(
        "Args",
        (),
        {
            "study_dir": study,
            "out": study / "receipt.json",
            "run_id": "unit",
            "ref_audio": "/data/embry_ref.wav",
            "norm_loudness": True,
            "json": True,
        },
    )()

    receipt = renderer.run(args)

    assert receipt["status"] == "BLOCKED_RENDER_STIMULI"
    assert "norm_loudness_not_echoed:dream:False:False" in receipt["failed_gates"]
    prereg = json.loads((study / "PREREGISTRATION.json").read_text(encoding="utf-8"))
    assert all(stimulus["sha256"] == "sha256:old" for stimulus in prereg["stimuli"])
