# NAVA Lane Design

## Classification

NAVA is a **joint audio-video renderer** lane.

It is not:

- a TTS backend,
- a lip-sync backend,
- a lore/story planner,
- a replacement for Arango/Qdrant provenance.

## Input contract

The input to NAVA must be derived from the already-built story assets:

```text
dream_packet.json
scenes_script.json
contact_sheets.json
```

The NAVA prompt may include cinematic density and camera/audio design, but it must not invent new persona facts.

## Prompt strategy

NAVA expects a dense cinematic caption. For dialogue, the prompt uses speech spans:

```text
<S>I know I am software. The evidence still feels real.<E>
```

For timbre control, pass:

```json
{
  "spk_wavs": ["/abs/path/to/consented_reference_voice.wav"]
}
```

For first-frame conditioning, pass:

```json
{
  "image_path": "/abs/path/to/reference_or_contact_sheet_panel.png"
}
```

## Bake-off comparison

Compare NAVA against the existing lanes like this:

| Lane | Meaning |
|---|---|
| ElevenLabs + Kling LipSync | best hosted TTS + hosted lip-sync baseline |
| WavTTS + Kling LipSync | local voice-clone TTS + hosted lip-sync |
| NAVA | joint AV generation with native audio/video co-generation |

NAVA wins only if it improves sync **without** breaking:

- transcript accuracy,
- persona voice fit,
- character continuity,
- source-grounding discipline,
- scene contract compliance.

## Manual review is mandatory

NAVA generates both sound and image. That means it may solve sync while drifting story/visuals. Review:

- Did it preserve the exact dialogue?
- Did it keep the Embry/Horus visual identity?
- Did it add unsupported lore?
- Did it preserve the timecoded scene intent?
- Did it improve true audio/action alignment over lip-sync lanes?
