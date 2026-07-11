# Battle Music Style Guide v1

## Creative north star

Battle sounds like a ceremonial execution machine that unexpectedly developed funk, wit, and excellent orchestration. The music must be threatening, memorable, intricate underneath, and faintly ridiculous without becoming parody. All themes in this package are original. The score may use broad genre traits—military procession, arena fanfare, electro-funk, IDM-like detail—but must never quote or trace a recognizable copyrighted melody.

## Signature identity

- **Death clock:** dry synthetic side-stick/woodblock. One hard tick per bar during combat; quarter-note ticks in exposed openings. The clock may omit a tick only for a confirmed terminal/death event.
- **Deep horn:** D1/D2 tuba or synthetic brass stack with a downward pitch envelope in production. It announces arena authority, not a specific faction.
- **Battle hook:** two bars, D-centered. The first bar uses the 16th-note duration grouping `3–1–4–2–2–4`; the second uses `2–2–6–2–4`. It repeats its first pitch, rises, steps down, then makes one conspicuous leap before descending home.
- **Signature groove:** clear 4/4 backbeat with kick accents implying `3+3+2` across eighth-note space. Use medium syncopation. The listener must always know where beat one is.
- **Comic detail:** one immaculate, unnecessary sound per phrase—calliope chirp, tiny laser, absurdly fast snare ratchet, vocoder consonant, or spawn bleep. Never stack all jokes at once.

## Tonal language

Primary center: **D minor**. Color tones: **Eb** for menace/Phrygian friction, **E natural** for synthetic brightness, and **C#** only as dominant pressure or mutation. Victory may flash **F#** for a brief D-major “receipt accepted” glare, then return to the shared D-centered world. Avoid long Hollywood-functional progressions; prefer pedal tones, modal chords, added seconds, open fifths, and A7(b9) as the principal cadence engine.

### Cadences

- **Battle/loop cadence:** A7(b9) → Dm(add9), but delay D in the top voice by an eighth note.
- **Death cadence:** chromatic upper collapse `F–Eb–D–C#–D`, then a low D/Ab/Eb receipt-stamp cluster; omit the expected final clock tick.
- **Victory cadence:** A7(b9) → Dm → very brief D major/add9 flash. It should feel earned and slightly smug, not patriotic.
- **Next-arena cadence:** stop on A7(b9), unresolved, so the live battle loop supplies the D arrival.

## Time signatures and cadence policy

- **4/4:** default combat meter and strongest usability choice for looping, UI synchronization, and stinger overlays.
- **7/8:** exploit mutation, berserker charge, malfunction, and death pre-tail. Group `2+2+3` or `3+2+2`; never use it for an entire long background cue.
- **5/4:** arena machinery, siege characters, and “one extra mechanical step.”
- **6/8 / 9/8 / 12/8:** imp, nurgling, and slug character identities. Keep percussion accents obvious.
- Main loop phrases resolve every **4 bars**, while the complete harmonic cycle resolves every **16 bars**. Stingers must fit over any bar boundary and peak within 250 ms of the receipt-driven visual impact.

## Instrument palette

### Foundation
- Synth bass: rubbery mono bass, fast attack, short release, mild resonance.
- Cellos: real or modeled ensemble doubled by one synthetic oscillator; articulate stalking ostinati and chopped mutation figures.
- Contrabass/tuba: sub authority and terminal impacts. Keep true sub energy below the UI voice range.

### Identity voices
- Synthetic brass lead: bright, slightly nasal, limited vibrato, velocity-sensitive filter.
- French horn/tuba stack: deep arena horn. Production version should layer a clean fundamental, distorted midrange, and short noisy bloom.
- Square/calliope lead: countermelodies and comic punctuation. Use at lower level than the brass hook.
- Vocoder/choir pad: ceremonial bureaucracy. Prefer short vowels or non-lexical syllables; no intelligible lore claims unless receipt-backed.

### Percussion
- Synthetic military snare, side-stick death clock, tight kick, short closed hats, occasional cymbal/metal hit.
- Snare rolls accelerate in subdivisions but must land exactly on a receipt or title strike.
- Glitch edits are arranged events, not random scatter. Preserve a stable kick/snare skeleton.

## Countermelody rules

1. Place the countermelody at least an octave above the bass and normally a sixth or more away from the main brass register.
2. Give it a distinct timbre and softer velocity so listeners perceive two intentional streams rather than a fused chord smear.
3. Prefer contrary or oblique motion when the hook makes its large leap.
4. Do not begin both melodies on every downbeat. The counterline should enter after the hook is established.
5. Reserve C# and tritone gestures for mutation, policy pressure, or mischievous characters.

## Dynamic music architecture

Export stems from the same MIDI source: `clock`, `drums`, `bass_cello`, `harmony_pad`, `main_hook`, `countermelody`, and `glitch_fx`. The 16-bar live loop is the base. Receipt-driven events duck only `main_hook` and `countermelody` by 3–6 dB; keep clock, kick, and bass continuity unless the backend confirms terminal state. Death and victory stingers are overlays, never baked into speculative UI state.

## Sprite motif sequence

| Sprite ID | Meter / BPM | Identity |
|---|---:|---|
| `blue_lizard` | 7/8, 148 | chromatic scamper; fast and smug |
| `green_horn` | 5/4, 84 | long lopsided herald call |
| `nurgling` | 4/4, 132 | bog-bounce calliope |
| `purple_horn_imp` | 6/8, 144 | crystalline tritone wink |
| `red_human` | 4/4, 116 | direct disciplined march |
| `skull_horn` | 3/2, 76 | hollow open fifths |
| `slug_demon` | 12/8, 72 | viscous triplet drag |
| `typhus` | 5/4, 88 | five-step siege engine |
| `crimson_chainsword_berserker` | 7/8, 156 | serrated seven-blade charge |
| `crimson_hornbreaker` | 4/4, 104 | blunt impact motif |
| `crimson_chainsaw_demon` | 4/4, 164 | sixteenth-note ratchet engine |
| `plague_nurgling` | 9/8, 138 | infectious asymmetrical wobble |

## MIDI and render contract

- Standard MIDI File type 1, 480 PPQN.
- Dedicated named tracks; percussion on channel 10 (zero-based channel 9).
- Tempo, key, time-signature and semantic markers embedded in the meta track.
- MIDI is the editable source, not the browser delivery format. Render approved versions to OGG/WAV and let Pixi/WebAudio play those assets.
- Recommended Python stack: **Mido** for SMF creation/validation and timed port messages; **pretty-midi + pyFluidSynth/FluidSynth** for deterministic SoundFont rendering. If one playback binding must be selected, use **pyFluidSynth**, because it produces audible samples in-process rather than only forwarding MIDI messages.

## Research basis used for this draft

- Witek et al., “Syncopation, Body-Movement and Pleasure in Groove Music,” PLOS ONE 9(4), 2014, DOI 10.1371/journal.pone.0094446: medium syncopation produced the strongest movement desire and pleasure in the study.
- Jakubowski et al., “Dissecting an Earworm,” Psychology of Aesthetics, Creativity, and the Arts: familiar/simple melodic shapes with a distinctive interval or repetition anomaly are more likely to recur involuntarily.
- Dai, Yu & Dannenberg, “What is missing in deep music generation?”, 2022: convincing human music uses hierarchical repetition and limited vocabulary rather than random novelty.
- Auditory-stream research associated with Dowling/Bregman: register and timbral differences help listeners separate concurrent melodic lines.
- Mido 1.3 documentation, pretty-midi documentation, pyFluidSynth 1.3.4 package documentation, and FluidSynth’s public API were used for the tooling decision.
