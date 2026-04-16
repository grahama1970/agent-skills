"""MIDI ↔ Piano Roll Spec conversion utilities.

Converts between piano-roll-spec.json and MIDI files using pretty_midi.
MIDI is planning IR only — fed to generators for timing guidance, NEVER in final output.
"""
import json
from pathlib import Path

import typer
from loguru import logger

app = typer.Typer(help="MIDI ↔ Piano Roll Spec conversion")

INSTRUMENT_MAP = {
    "vocal": 0, "guitar": 25, "bass": 33, "drums": 0,
    "keys": 0, "synth": 80, "strings": 48, "brass": 56, "pad": 89,
}


@app.command("from-spec")
def from_spec(
    spec: str = typer.Option(..., help="Path to piano-roll-spec.json"),
    out: str = typer.Option(..., help="Output MIDI file path"),
):
    """Convert piano-roll-spec.json → MIDI file."""
    import pretty_midi

    spec_path = Path(spec)
    if not spec_path.exists():
        logger.error(f"Spec not found: {spec_path}")
        raise typer.Exit(1)

    data = json.loads(spec_path.read_text())
    bpm = data["bpm"]
    midi = pretty_midi.PrettyMIDI(initial_tempo=bpm)
    beats_per_second = bpm / 60.0

    instruments_by_name: dict[str, pretty_midi.Instrument] = {}

    for note in data.get("notes", []):
        inst_name = note["instrument"]
        if inst_name not in instruments_by_name:
            is_drum = inst_name == "drums"
            program = INSTRUMENT_MAP.get(inst_name, 0)
            instruments_by_name[inst_name] = pretty_midi.Instrument(
                program=program, is_drum=is_drum, name=inst_name,
            )

        pitch = note["pitch"]
        if isinstance(pitch, str):
            pitch = pretty_midi.note_name_to_number(pitch)

        start_time = note["start_beat"] / beats_per_second
        end_time = start_time + note["duration_beats"] / beats_per_second
        velocity = note.get("velocity", 100)

        midi_note = pretty_midi.Note(
            velocity=velocity, pitch=pitch, start=start_time, end=end_time,
        )
        instruments_by_name[inst_name].notes.append(midi_note)

    for inst in instruments_by_name.values():
        midi.instruments.append(inst)

    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    midi.write(str(out_path))
    logger.info(f"Wrote MIDI: {out_path} ({len(data.get('notes', []))} notes, {bpm} BPM)")


@app.command("to-spec")
def to_spec(
    midi_file: str = typer.Option(..., "--midi", help="Input MIDI file path"),
    out: str = typer.Option(..., help="Output piano-roll-spec.json path"),
):
    """Convert MIDI file → piano-roll-spec.json."""
    import pretty_midi

    midi_path = Path(midi_file)
    if not midi_path.exists():
        logger.error(f"MIDI not found: {midi_path}")
        raise typer.Exit(1)

    midi = pretty_midi.PrettyMIDI(str(midi_path))
    tempo_times, tempos = midi.get_tempo_changes()
    bpm = round(tempos[0]) if len(tempos) > 0 else 120
    beats_per_second = bpm / 60.0
    total_beats = midi.get_end_time() * beats_per_second
    beats_per_bar = 4
    total_bars = int(total_beats / beats_per_bar) + 1

    reverse_map = {v: k for k, v in INSTRUMENT_MAP.items()}
    notes = []
    for inst in midi.instruments:
        inst_name = inst.name or reverse_map.get(inst.program, "synth")
        if inst.is_drum:
            inst_name = "drums"
        for note in inst.notes:
            notes.append({
                "pitch": note.pitch,
                "start_beat": round(note.start * beats_per_second, 3),
                "duration_beats": round((note.end - note.start) * beats_per_second, 3),
                "velocity": note.velocity,
                "instrument": inst_name,
            })

    spec = {
        "bpm": bpm,
        "time_signature": "4/4",
        "key": "C major",
        "total_bars": total_bars,
        "sections": [{"section_name": "full", "start_bar": 1, "end_bar": total_bars}],
        "notes": sorted(notes, key=lambda n: n["start_beat"]),
    }

    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(spec, indent=2))
    logger.info(f"Wrote spec: {out_path} ({len(notes)} notes, {bpm} BPM)")


if __name__ == "__main__":
    app()
