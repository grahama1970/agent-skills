---
name: create-midi
description: >
  Compose MIDI arrangements and convert between JSON spec and MIDI files.
  Two modes: 'compose' uses LLM (via /prompt-lab prompt) to create a full
  arrangement from annotated lyrics + reference MIDI fragments + heart tags.
  'from-spec' and 'to-spec' are mechanical JSON↔MIDI conversion via pretty_midi.
  The arrangement is the creative heart of the music pipeline — it decides what
  every instrument plays at every beat.
triggers:
  - create midi
  - compose arrangement
  - generate midi
  - midi from spec
  - midi to spec
  - arrange song
  - write arrangement
  - compose music
allowed-tools: [Bash, Read, Write]
metadata:
  short-description: Compose MIDI arrangements + JSON↔MIDI conversion
provides:
  - midi-composition
  - midi-conversion
  - arrangement-creation
composes:
  - memory
  - consume-midi
  - prompt-lab
  - review-music
read_before_use:
  - compose.py
  - midi_utils.py
  - run.sh
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# /create-midi

Two capabilities in one skill:

## 1. Compose Arrangement (`compose`)

LLM creates a full multi-track arrangement given:
- **Annotated lyrics** (S04 output) — vocal melody timing, syllable stress
- **MIDI fragments** (from /consume-midi) — reference bass lines, drum patterns, chord voicings
- **Arrangement notes** (from S02) — natural language description of reference song structure
- **Heart tags** (from S00) — emotional dynamics per section (anger→sadness→fear)

```bash
./run.sh compose \
  --lyrics annotated-lyrics.json \
  --references consume_midi_results.json \
  --arrangement arrangement_notes.md \
  --heart "anger,sadness,fear" \
  --out piano-roll-spec.json
```

**Prompt managed by /prompt-lab** — the composition prompt needs to understand:
- Chord voicings and voice leading
- Bass line patterns (root, fifth, walking, pedal)
- Drum grooves (kick/snare/hihat patterns per feel)
- Counter-melody construction
- Energy curve shaping (build, drop, sustain)
- How heart tags translate to musical choices (fear = sparse, anger = driving, sadness = sustained)

Output: `piano-roll-spec.json` with notes for vocal, bass, drums, keys, guitar, synth.

## 2. Convert (`from-spec`, `to-spec`)

Mechanical JSON↔MIDI conversion via pretty_midi. No LLM involved.

```bash
# JSON → MIDI (compile the arrangement to playable file)
./run.sh from-spec --spec piano-roll-spec.json --out arrangement.mid

# MIDI → JSON (import existing MIDI for analysis or editing)
./run.sh to-spec --midi input.mid --out spec.json
```

The MIDI file has separate tracks per instrument. This is the song's
intermediate representation — between creative decisions and audio rendering.

## Architecture Note

`midi_utils.py` was originally in `/create-music`. It moved here because
arrangement composition is a distinct creative step, not a sub-feature
of audio generation.
