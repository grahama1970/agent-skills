# Kling source material contract

Goal: turn a large persona-dream packet into the smallest inputs Kling can obey.

## Inputs from persona-dream

| Source artifact | Use in Kling | Optimization |
|---|---|---|
| `character_scene_bible.json` | Character identity roster | Do not paste descriptions into prompt when refs exist. Use names only in `@ElementN is Name.` |
| Character contact sheets | Human review only | Crop/export one clean portrait or full-body single-subject image per character before upload. |
| Environment contact sheet | `image_urls[]` style/environment reference | Prefer one uncropped establishing frame without captions or panel borders. If only sheet exists, prompt must say which panel/visual facts to match. |
| `storyboard.json` | Action + blocking | Pick one action beat per clip. |
| `look_lock.json` | Camera + light + palette | Condense to one shot type, one motion, one palette/light fact. |
| `script_dna_selection.json` | Dialogue pressure / intent | Use only for action text or audio plan; do not paste prose analysis. |
| `timed_transcript.json` | Audio lane | Kling visual prompt does not create real persona speech. Render/mux speech separately unless provider voice IDs exist. |

## Reference image rules

1. One element = one subject. No collages, no captions, no multiple poses unless
   there is no alternative.
2. Character refs should show face, torso, silhouette, wardrobe, and no other
   named character.
3. Environment refs should show the set: furniture, sky, props, scale, creatures.
4. Avoid visible text in refs; Kling reproduces text as gibberish or treats it as
   image content.
5. Upload every ref to a public HTTPS URL before submission. Local paths are only
   allowed in offline packets and must be rewritten by submit.

## Prompt shape

```text
@Element1 is <Name>. @Element2 is <Name>. Exactly N people; no one else present.
<One action beat>. <Environment facts from @Image1>. <Camera/look>. no text overlays.
```

## Visual fact extraction

Use concrete visible facts, not lore labels:

- Bad: `Zeitch Eye`
- Good: `dark eclipsed black sphere ringed by a glowing purple corona in storm clouds`

- Bad: `SPARTA evidence system`
- Good: `rugged black laptop on the tea table, glowing cyan SPARTA Explorer map on the screen`

## Audio boundary

`generate_audio` is ambient/provider audio, not faithful persona speech. Faithful
speech needs one of:

1. local Chatterbox/Kokoro/voice lane render -> ffmpeg mux;
2. provider voice clone -> `voice_id`/voice-list lane when live voice IDs exist.

A silent Kling MP4 plus a separate speech WAV is not a complete voiced video.
The mux receipt must prove video stream + audio stream and duration.
