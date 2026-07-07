# BATTLE Sprite Pipeline

This document defines the art-to-runtime boundary for BATTLE animated exploit
agents.

## Boundary

```text
Annotated contact sheet = art direction only.
Runtime Pixi asset      = transparent frame atlas + PixiJS JSON only.
```

The backend does not emit Pixi asset paths, animation names, or frame indices.
It may emit `actor_visual.variant_id` and receipt-backed semantic state changes.
Pixi maps those values through `battle.sprite_theme.v1`.

## Runtime Atlas

Runtime atlas requirements:

```text
transparent background
no labels
no text
no side panel
no grid lines
frames only
strict 8 column x 14 row grid
64x64 heavy agents or 48x48 normal agents
margin 0
spacing 0
side profile facing right
feet aligned to common baseline
nearest-neighbor pixel art
unused cells transparent
```

Rows:

```text
0  idle           4 frames
1  walk           6 frames
2  run            8 frames
3  research       6 frames
4  payload        6 frames
5  mutate         6 frames
6  handoff        6 frames
7  spawn          8 frames
8  blocked        6 frames
9  hit            3 frames
10 killed         8 frames
11 victory        8 frames
12 promoted       8 frames
13 fastest_crash  8 frames
```

For a 64x64 atlas:

```text
width  = 8 * 64  = 512
height = 14 * 64 = 896
```

## Generation

Generate matching PixiJS JSON with:

```bash
python3 skills/battle/scripts/generate_battle_sprite_atlas_json.py \
  --sprite-id space_pirate_hornbreaker \
  --image space_pirate_hornbreaker.png \
  --out /tmp/space_pirate_hornbreaker.json
```

The generated JSON follows PixiJS `Spritesheet` format:

```text
frames{} + animations{} + meta.image
```

Pixi loads it with `Assets.load("space_pirate_hornbreaker.json")` and plays a
state with `new AnimatedSprite({ textures: sheet.animations[state] })`.

## Receipt Gates

The sheet may contain terminal animations, but the engine may play them only
after matching Battle proof exists:

```text
spawn          requires lineage spawn receipt
blocked        requires Blue/Judge block receipt
killed         requires Judge kill receipt
promoted       requires promotion receipt
fastest_crash  requires crash proof + timing receipt
victory        requires terminal winning outcome or battle-end receipt
```

## Shared Effects

Do not duplicate these inside every character sheet unless character-specific
art is required:

```text
death_burst
shield_impact
green_explosion
purple_spawn_burst
yellow_signal_ping
green_rocket_trail
promotion_aura
```

Use shared atlases such as:

```text
battle_effects_common.png
battle_effects_common.json
```
