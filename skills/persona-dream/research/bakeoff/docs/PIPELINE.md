# Pipeline Contract

The bake-off uses this invariant:

```text
one contract
one base video
two TTS lanes
two lip-sync outputs
one verifier
```

The video prompt is intentionally front-facing and simple because Kling LipSync requires the video input to be a 2–10 second .mp4/.mov at 720p/1080p, with a visible face.

## Lane A

```text
contract.dialogue
→ fal-ai/elevenlabs/tts/eleven-v3
→ audio_url
→ fal-ai/kling-video/lipsync/audio-to-video
```

## Lane B

```text
contract.dialogue
→ wavtts_infer-cli --model WavTTS --ref_audio ... --ref_text ... --gen_text ...
→ local wav
→ fal upload
→ audio_url
→ fal-ai/kling-video/lipsync/audio-to-video
```

## Verifier

For each lane:

```text
download audio/video
ffprobe durations
fal-ai/whisper transcript of generated audio
fal-ai/whisper transcript of final lip-sync video
string similarity against expected dialogue
duration fit checks
manual visual review fields
```

## Source-grounding

The sample contract includes placeholder residue IDs. Replace them with real accepted no-write records before production tests.
