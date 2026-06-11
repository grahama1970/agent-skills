# Kling Video Prompt Template

Kling’s Image-to-Video guidance emphasizes describing visible motion as:

```text
Subject + Movement, Background + Movement
```

## Single-shot template

```text
[@AssetName] performs [specific visible action].
Camera: [shot size], [camera angle], [camera movement], [lens/depth-of-field feel].
Background: [what moves in the environment].
Keep consistent: [fixed identity details].
Avoid: [morphing, duplicated subject, outfit change, altered logo, inconsistent scale, extra limbs, warped hands].
```

## Multi-shot template

```text
Shot 1 ([duration]): [@AssetName] [subject movement]. Camera: [camera direction]. Background: [movement].
Shot 2 ([duration]): [@AssetName] [subject movement]. Camera: [camera direction]. Background: [movement].
Shot 3 ([duration]): [@AssetName] [subject movement]. Camera: [camera direction]. Background: [movement].

Keep consistent across all shots: [identity locks].
Avoid: [failure modes].
```

## Motion verbs that help

Prefer visible, grounded actions:

- walks, turns, pauses, reaches, grips, lifts, opens, closes, leans, kneels, steps back
- rain falls, dust drifts, steam rises, neon flickers, leaves sway, water ripples
- camera tracks, pushes in, tilts up, pans left, circles slowly, holds still

Avoid vague-only instructions:

- make it cinematic
- animate this
- make it cool
- add drama
- improve motion

Use vague style words only after specifying the action.
