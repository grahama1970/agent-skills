from pathlib import Path
import json

import numpy as np
import pretty_midi
import soundfile as sf

from src.neural_hum_renderer import evaluate_hum_render, render_neural_hum, train_neural_hum_renderer


def _control_manifest(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    sr = 22050
    items = []
    for split, hz in [("train", 220.0), ("train", 246.94), ("valid", 233.08)]:
        idx = len(items)
        t = np.arange(int(sr * 1.0), dtype=np.float32) / sr
        audio = (
            0.2 * np.sin(2.0 * np.pi * hz * t)
            + 0.07 * np.sin(2.0 * np.pi * hz * 2.0 * t)
        ).astype(np.float32)
        wav = tmp_path / f"{split}_{idx}.wav"
        sf.write(wav, audio, sr)
        items.append(
            {
                "id": f"{split}_{idx}",
                "split": split,
                "audio_path": str(wav),
                "midi_path": str(tmp_path / f"{split}_{idx}.mid"),
                "duration_s": 1.0,
            }
        )
    manifest = {
        "schema": "hum.train_control_dataset.v1",
        "sample_rate": sr,
        "split_counts": {"train": 2, "valid": 1, "test": 0},
        "items": items,
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    return path


def _midi_with_bend(path: Path) -> None:
    midi = pretty_midi.PrettyMIDI(initial_tempo=120)
    inst = pretty_midi.Instrument(program=53, name="MELODY")
    inst.notes.append(pretty_midi.Note(velocity=100, pitch=57, start=0.0, end=0.8))
    inst.pitch_bends.append(pretty_midi.PitchBend(pitch=0, time=0.0))
    inst.pitch_bends.append(pretty_midi.PitchBend(pitch=4096, time=0.4))
    midi.instruments.append(inst)
    midi.write(str(path))


def test_train_render_and_evaluate_neural_hum_renderer(tmp_path: Path):
    _control_manifest(tmp_path / "controls")
    controls_dir = tmp_path / "controls"
    train = train_neural_hum_renderer(controls_dir, tmp_path / "run", harmonics=6)
    assert Path(train.checkpoint).exists()
    metrics = json.loads(Path(train.metrics_json).read_text())
    assert metrics["renderer"] == "control_conditioned_harmonic_ddsp_numpy_v1"
    assert metrics["train_used"] == 2

    midi_path = tmp_path / "melody.mid"
    _midi_with_bend(midi_path)
    render = render_neural_hum(Path(train.checkpoint), midi_path, tmp_path / "render", transpose_semitones=0.0)
    assert Path(render.output_wav).exists()
    manifest = json.loads(Path(render.render_manifest).read_text())
    assert manifest["pitch_bend_note_count"] == 1
    assert manifest["renderer"] == "control_conditioned_harmonic_ddsp_numpy_v1"

    evaluation = evaluate_hum_render(
        tmp_path / "render",
        midi_path,
        tmp_path / "eval.json",
        transpose_semitones=0.0,
    )
    report = json.loads(Path(evaluation.report_json).read_text())
    assert report["gate"]["listening_required"] is True
    assert report["metrics"]["overlap_frame_count"] > 0
