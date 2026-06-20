from pathlib import Path

import numpy as np
import pretty_midi
import soundfile as sf

from src.cache import HumTrack
from src.defaults import DEFAULT_SOURCE_HUM_RENDERER
from src.pipeline import HumPipeline
from src.source_hum_gate import (
    IMPORT_RENDERERS,
    analyze_midi,
    normalize_renderer,
    renderer_requires_import,
    validate_midi_for_hum,
    validate_source_hum_wav,
)


def test_normalize_renderer_aliases():
    assert normalize_renderer("midi_hum") == "old_synth"
    assert normalize_renderer("vocal_stem") == DEFAULT_SOURCE_HUM_RENDERER
    assert normalize_renderer("vocal_stem_diag") == "vocal_stem_diag"
    assert normalize_renderer("elevenlabs") == "elevenlabs_manual"
    assert "elevenlabs_manual" in IMPORT_RENDERERS
    assert renderer_requires_import("elevenlabs")


def test_default_renderer_is_vocal_stem_everywhere():
    assert DEFAULT_SOURCE_HUM_RENDERER == "vocal_stem"
    assert HumTrack(id="sample", title="Sample").source_hum_renderer == DEFAULT_SOURCE_HUM_RENDERER
    assert HumTrack(id="sample", title="Sample").melody_source == DEFAULT_SOURCE_HUM_RENDERER

    skill_md = Path(__file__).resolve().parents[1] / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8")
    assert "| `--source-hum-renderer` |" in text
    assert f"| `{DEFAULT_SOURCE_HUM_RENDERER}` |" in text

    add_defaults = HumPipeline.add.__kwdefaults__ or {}
    assert add_defaults["source_hum_renderer"] == DEFAULT_SOURCE_HUM_RENDERER


def test_validate_source_hum_wav_rejects_silence(tmp_path: Path):
    wav = tmp_path / "silent.wav"
    sf.write(wav, np.zeros(44100, dtype=np.float32), 44100)
    errors, metrics = validate_source_hum_wav(wav)
    assert errors
    assert metrics["duration_s"] >= 1.0


def test_midi_gate_sparse(tmp_path: Path):
    pm = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(0)
    inst.notes.append(pretty_midi.Note(80, 60, 0.0, 0.2))
    midi = tmp_path / "sparse.mid"
    pm.write(str(midi))
    metrics = analyze_midi(midi)
    errors = validate_midi_for_hum(metrics, 20.0)
    assert errors
