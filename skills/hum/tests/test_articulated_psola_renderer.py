import json
from pathlib import Path

import numpy as np
import pretty_midi
import soundfile as sf

from src.articulated_psola_renderer import OUTPUT_FILENAMES, REQUIRED_TOKENS, main


def _write_samples(samples_dir: Path, sr: int = 44100) -> None:
    samples_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20260620)
    for i, token in enumerate(REQUIRED_TOKENS):
        duration = 0.45 if token != "breath" else 0.25
        t = np.linspace(0.0, duration, int(sr * duration), endpoint=False)
        if token == "breath":
            y = rng.normal(0.0, 0.025, len(t)).astype(np.float32)
        else:
            f0 = 180.0 + 2.0 * i
            y = 0.22 * np.sin(2.0 * np.pi * f0 * t)
            y += 0.05 * np.sin(2.0 * np.pi * 2.0 * f0 * t)
            fade = min(len(y) // 4, int(0.025 * sr))
            envelope = np.ones(len(y), dtype=np.float32)
            envelope[:fade] = np.linspace(0.0, 1.0, fade, endpoint=False)
            envelope[-fade:] = np.linspace(1.0, 0.0, fade, endpoint=False)
            y = (y * envelope).astype(np.float32)
        sf.write(samples_dir / f"{token}.wav", y, sr)


def _write_melody(midi_path: Path) -> None:
    pm = pretty_midi.PrettyMIDI(initial_tempo=120)
    inst = pretty_midi.Instrument(program=0, name="Melody")
    start = 0.0
    for pitch in [60, 62, 64, 65, 67, 69, 67, 65, 64, 62, 60, 60]:
        inst.notes.append(pretty_midi.Note(velocity=92, pitch=pitch, start=start, end=start + 0.28))
        start += 0.34
    pm.instruments.append(inst)
    pm.write(str(midi_path))


def test_articulated_psola_renderer_writes_review_bundle(tmp_path: Path):
    samples = tmp_path / "samples"
    midi = tmp_path / "melody.mid"
    phrases = tmp_path / "phrases.json"
    out_dir = tmp_path / "render"
    _write_samples(samples)
    _write_melody(midi)
    phrases.write_text(json.dumps({"phrases": [["ha", "tu", "pi", "ko", "lu", "wa"]]}) + "\n")

    exit_code = main(
        [
            "--midi",
            str(midi),
            "--samples",
            str(samples),
            "--phrases-json",
            str(phrases),
            "--output-dir",
            str(out_dir),
            "--cycles",
            "1",
            "--allow-no-swing-pairs",
        ]
    )

    assert exit_code in {0, 2}
    for key in ("inventory", "alignment", "timeline", "midi", "audio", "manifest", "qa"):
        assert (out_dir / OUTPUT_FILENAMES[key]).is_file()
    qa = json.loads((out_dir / OUTPUT_FILENAMES["qa"]).read_text())
    assert qa["schema"] == "qa_metrics_v1"
    assert qa["scope_note"].startswith("Machine QA does not establish")
    manifest = json.loads((out_dir / OUTPUT_FILENAMES["manifest"]).read_text())
    assert manifest["renderer"] == "hawaiian_war_chant_articulated_psola_v1"
