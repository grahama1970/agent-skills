---
name: consume-midi
description: >
  Search and retrieve MIDI fragments from the library for arrangement composition.
  The library is populated from reference songs: /consume-music finds songs →
  /learn-artist downloads + separates stems → /review-music analyzes →
  /create-midi to-spec converts stem audio to MIDI → /memory learn stores with
  HMT tags. Queries by key, BPM, instrument, mood (heart tags).
triggers:
  - find midi
  - search midi patterns
  - midi reference
  - bass line reference
  - drum pattern reference
  - chord progression reference
  - midi library search
  - arrangement reference
allowed-tools: [Bash, Read]
metadata:
  short-description: Search MIDI fragment library by key/BPM/instrument/mood
provides:
  - midi-search
  - arrangement-reference
composes:
  - memory
  - consume-music
  - review-music
read_before_use:
  - run.sh
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# /consume-midi

Search the MIDI fragment library for reference patterns that match a target
song's musical attributes. Used by `/create-midi compose` to provide example
bass lines, drum grooves, chord voicings, and melodies when composing an
arrangement.

## Library Population Chain

```
/consume-music (find reference songs by HMT tags)
  → /learn-artist (download + /create-stems separate)
    → /review-music analyze (per-stem MIR features)
      → /create-midi to-spec (stem features → MIDI JSON)
        → /memory learn (store with key, BPM, instrument, heart tags)
```

## Search

```bash
./run.sh search --key "D minor" --bpm 85 --instrument bass --mood anger,sadness
```

Returns MIDI fragments as JSON matching the query. The fragments are
piano-roll-spec.json snippets with notes for the requested instrument.

## Storage Collection

Stored in ArangoDB collection `consume_midi` via `/memory learn`:
- `key`: musical key (e.g. "D minor")
- `bpm`: tempo
- `instrument`: which stem this came from
- `heart`: heart taxonomy tags from the source song
- `source_song`: title + artist of the reference
- `notes`: array of piano-roll-spec notes for this stem
