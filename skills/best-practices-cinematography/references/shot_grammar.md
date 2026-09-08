# Shot grammar vocabulary (prompt-ready)

## Shot sizes

| Code | Name | Use for | Prompt phrase |
|---|---|---|---|
| EWS | Extreme wide | World/scale, openings | "extreme wide establishing shot, figures small" |
| WS | Wide | Establish set + blocking | "wide shot, both characters and the full table visible" |
| MWS | Medium wide | Group beats, movement | "medium wide, waist-up, both characters" |
| MS | Medium | Neutral dialogue | "medium shot, waist-up" |
| MCU | Medium close-up | Dialogue singles (default) | "medium close-up, chest-up, face clearly visible" |
| CU | Close-up | Emotional peaks | "close-up on her face" |
| ECU | Extreme close-up | Detail/object inserts | "extreme close-up on the teacup" |
| OTS | Over-the-shoulder | Dialogue depth | see SKILL.md Rule 3 — bind the shoulder to the element |
| 2S | Two-shot | Master, shared beats | "two-shot, both seated at the table" |

## Camera height

| Height | Effect | Phrase |
|---|---|---|
| Eye level | Neutral, equal | "camera at eye level" |
| Low angle | Power, scale (good for Horus) | "low angle looking up" |
| High angle | Vulnerability, smallness | "high angle looking down" |

## Lenses

| Focal | Effect | Phrase |
|---|---|---|
| 24mm wide | Space, isolation, slight distortion near edges | "wide 24mm perspective" |
| 35mm | Natural documentary feel | "35mm natural perspective" |
| 50mm | Neutral human eye | "50mm neutral lens" |
| 85mm | Portrait compression, intimacy, creamy background | "85mm portrait compression, shallow depth of field" |
| 135mm+ | Voyeuristic compression, stacked planes | "long lens compression" |

## Movement (one per clip, or static)

| Move | Emotional use | Phrase |
|---|---|---|
| Static | Stability, observation | "static camera" |
| Slow push-in | Rising attention/intimacy | "slow push-in" |
| Slow pull-back | Release, ending, loneliness | "very slow pull-back" |
| Lateral drift | Dreamlike observation | "slow lateral drift" |
| Handheld sway | Unease, immediacy | "subtle handheld sway" |
| Orbit | Revelation, showcase (use sparingly) | "slow orbit" |

Never stack movements. Never use orbit/drone/crane language on an intimate
dialogue beat.

## Lighting setups

| Setup | Use | Prompt phrase |
|---|---|---|
| Three-point | Neutral coverage baseline | "balanced key and soft fill" |
| Motivated practical | Default for scenes | "lit by [the named source in the scene]" |
| Low-key / chiaroscuro | Tension, mystery | "low-key lighting, deep shadows, single motivated source" |
| High-key | Openness, comedy, safety | "soft high-key lighting" |
| Rim/edge | Separation from busy backgrounds | "rim light separating characters from the background" |
| Golden hour | Warmth, nostalgia, transitions | "warm golden-hour side light" |
| Screen glow | Tech intimacy | "faces lit by the screen's glow" |

Hard light = tension/texture. Soft light = intimacy/beauty. Match hardness to
tone, name the source, keep key direction constant across the scene.

## Dialogue coverage recipe (default)

```text
1. Master 2S (wide or MWS)      — anchors set, axis, lighting
2. MCU single A (speaker beat)  — A faces camera-right (if A is screen-left)
3. MCU single B (reply beat)    — B faces camera-left, SAME framing size
4. Optional CU reaction insert  — the listener, not the speaker
5. Return to 2S or pull-back    — scene punctuation
```

Axis: fixed by the master. Eyelines explicitly stated per single. Looking
room on the facing side. Insert-cut reactions are cheap emotional value.

## AI-video failure modes (dated receipts)

| Failure | Cause | Fix |
|---|---|---|
| Third person spawned in OTS | "X seen from behind" while X also described in scene (2026-09-08) | Bind foreground to element body part + costume; negative-prompt "extra person" |
| Random casting | No reference images sent (2026-09-07) | elements[] with clean single-subject crops |
| Eyeline flip between clips | Eyeline not stated | "facing camera-right/left" explicitly per single |
| Silent re-talk after line | Base clip mouth motion outlives audio (2026-09-08) | End beats "mouth closed"; trim to beat |
| Literal lore rendering | Lore name instead of visual facts (2026-09-07: "Zeitch Eye" = floating eyeball) | Describe what the camera sees |
| Drifting light direction | Source not named/pinned | Name the practical source every clip; chain refs |
