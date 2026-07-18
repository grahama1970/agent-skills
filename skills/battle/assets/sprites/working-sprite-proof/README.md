# Working Sprite Proof — Adaptive Lineage Goal Reference Set

Durable reference artifacts for `skills/battle/GOAL_ADAPTIVE_LINEAGE.md`
(PixiJS Sprite Acceptance). These are extracted, rendered frames — not asset
files sitting unrendered on disk — proving the atlases actually paint.

| Artifact | Atlas | Frame | Role |
|---|---|---|---|
| `WORKING--plague_nurgling--plague_nurgling_idle_0.png` | `plague_nurgling` | `plague_nurgling_idle_0` (64x64, 2122 opaque px) | **Included working sprite (mandatory floor).** The one atlas the code enables today (`BATTLE_ACTIVE_RUNNER_SPRITE_ID`); produced by the `/sprite-atlas` + `/tau` creator<->reviewer acceptance loop. The goal must never regress below this. |
| `red_human--red_human_idle_0.png` | `red_human` | `red_human_idle_0` (64x64, 1470 opaque px) | **Second-atlas viability proof.** Confirms a non-nurgling atlas also extracts and renders, so distinct per-specimen sprites are achievable — pending promotion through the same acceptance loop. |

## How these were produced

Frames were cut from the packed atlases in
`skills/battle/assets/sprites/pixijs/<atlas>.{png,json}` using the atlas frame
rects (same manifests PixiJS `runnerSpritesheet(...)` loads at runtime). Opaque
pixel counts are recorded above to prove each is a real character frame, not a
blank/transparent cell.

## Regeneration

Re-cut a frame from any atlas the same way (atlas PNG + `.json` frame rect ->
crop). Keep `plague_nurgling` here as the standing floor; add a rendered frame
for each additional atlas only after it passes the `/sprite-atlas` validation and
the `/tau` sprite creator<->reviewer visual-acceptance loop.
