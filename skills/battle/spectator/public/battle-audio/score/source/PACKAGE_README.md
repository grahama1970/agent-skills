# Battle original MIDI score package

This package contains an original first-pass score and motif system for the Battle Pixi spectator experience. It is a compositional prototype: the notes, structure, markers and orchestration are production-ready inputs, while final synth patches, distortion, vocoder design, mix and mastering should be completed in a DAW.

## Main cues

- `cues/battle_intro_death_clock_overture.mid`
- `cues/exploit_death_stinger.mid`
- `cues/exploit_victory_stinger.mid`
- `cues/next_battle_arena_level.mid`
- `cues/battle_started_background_loop.mid`
- `cues/battle_character_motif_reel.mid`

Twelve individual sprite motifs are in `character_motifs/`. OGG previews are in `previews/`.

## Validate

```bash
python tools/validate_midis.py .
```

## Play or render a MIDI

Ubuntu/Debian dependencies:

```bash
sudo apt install libfluidsynth3 fluid-soundfont-gm ffmpeg
python -m pip install -r requirements.txt
python tools/play_midi.py cues/battle_intro_death_clock_overture.mid
```

Render a WAV for the DAW:

```bash
python tools/play_midi.py cues/battle_started_background_loop.mid --output battle-loop.wav
```

## Reproduce the playback decision

```bash
python tools/benchmark_midi_backends.py cues/battle_intro_death_clock_overture.mid > backend_proof.json
```

The decision is deliberately split by responsibility: Mido is the strongest canonical MIDI file/port layer; pyFluidSynth is the strongest single Python binding here for audible SoundFont playback/rendering; pretty-midi provides the convenient bridge for analysis and offline rendering. For Pixi/WebAudio, render approved MIDI to OGG/WAV rather than attempting Python MIDI playback in the browser.
