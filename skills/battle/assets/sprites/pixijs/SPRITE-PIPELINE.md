# BATTLE sprite pipeline — worker instructions

Hand this folder to a cheaper image/code agent. Follow steps exactly.

## Two artifacts (do not confuse)

| Artifact | Size | Alpha | Labels/grid | Used by Pixi? |
|----------|------|-------|-------------|---------------|
| Contact sheet | ~948×1659 RGB | No | Yes — allowed | **NO** |
| Runtime atlas | 512×896 RGBA | Yes — real | **NO** — forbidden | **YES** |

**Failure mode we hit:** running `convert-contact-sheet` on a contact sheet and shipping the result. That bakes grid lines and mis-slices uneven cells. Contact sheets are art review only.

## Fill-in templates

1. Copy `sprite-work-order.template.json` → `{{sprite_id}}.work-order.json`
2. Fill `contact-sheet-prompt.template.txt` OR `runtime-atlas-prompt.template.txt`
3. Paste `negative-prompt.txt` into model negative prompt field

## Preferred path (correct)

```text
reference image
  → contact sheet (optional, human approves)
  → runtime atlas image gen (512×896 transparent, from runtime-atlas-prompt.template.txt)
  → validate-png + validate-json
  → {sprite_id}.png + {sprite_id}.json in this directory
```

## Convert an existing generated sheet → runtime atlas (automated)

When you already have a generated sheet (e.g. a ChatGPT/Gemini transparent or
checkerboard sheet) and want the 512×896 runtime atlas, use `convert-autogrid`.
It is the robust one-shot: it **auto-detects the background** (checker / dark /
transparent), **detects row bands by content projection** (so rows that drift
off a uniform grid are not clipped — the classic failure of the older
`convert-contact-sheet`/`clean-checkerboard`), slices columns by the canonical
per-row frame counts, **de-slivers** each cell (drops neighbour-frame edge bleed
while keeping VFX), and **holds the last frame** to fill any row the generator
under-drew.

```bash
python3 skills/battle/utils/clean_sprite_atlas.py convert-autogrid \
  --source path/to/{{sprite_id}}-sheet.png \
  --sprite-id {{sprite_id}} \
  --out-png skills/battle/assets/sprites/pixijs/{{sprite_id}}.png \
  --out-json skills/battle/assets/sprites/pixijs/{{sprite_id}}.json
# prints e.g. "... rows=detected frames=91 bg=checker"
```

If it prints `rows=uniform` it could not find 14 bands and fell back to a uniform
grid — inspect the sheet. Always eyeball the output PNG: the validator checks
structure, not visual quality. Regression tests: `skills/battle/tests/test_sprite_atlas_autogrid.py`.

### Legacy fallback (lossy — avoid)

The older `convert-contact-sheet` assumes a perfectly uniform grid in canonical
row order and is lossy on uneven/AI-generated sheets. Prefer `convert-autogrid`.

```bash
python3 skills/battle/utils/clean_sprite_atlas.py convert-contact-sheet \
  --source path/to/{{sprite_id}}-contact-sheet.png \
  --sprite-id {{sprite_id}} \
  --out-png skills/battle/assets/sprites/pixijs/{{sprite_id}}.png \
  --out-json skills/battle/assets/sprites/pixijs/{{sprite_id}}.json
```

## Generate Pixi JSON (if PNG exists, JSON missing)

```bash
cd agent-skills
skills/create-battle-sprite-sheet/run.sh manifest \
  --sprite-id {{sprite_id}} \
  --image {{sprite_id}}.png \
  --out skills/battle/assets/sprites/pixijs/{{sprite_id}}.json
```

## Validate (must PASS)

```bash
cd agent-skills
SKILL=skills/create-battle-sprite-sheet
PNG=skills/battle/assets/sprites/pixijs/{{sprite_id}}.png
JSON=skills/battle/assets/sprites/pixijs/{{sprite_id}}.json

$SKILL/run.sh validate-png --png "$PNG"
$SKILL/run.sh validate-json --json "$JSON" --png "$PNG"
```

## Transparency check (quick, no tools)

```bash
python3 - <<'PY'
from PIL import Image
p = "skills/battle/assets/sprites/pixijs/{{sprite_id}}.png"
im = Image.open(p)
px = im.getpixel((0, 0))
print(im.size, im.mode, "corner_rgba", px, "OK" if len(px)==4 and px[3]==0 else "FAIL_NOT_TRANSPARENT")
PY
```

- `RGBA` mode, corner alpha `0` → real transparent PNG
- Checkerboard in GIMP/Preview → viewer preview, not file content
- Solid black in dark-themed viewer → transparent pixels on black background

## Pixi load contract

```ts
await Assets.load("/battle-sprites/pixijs/{{sprite_id}}.json");
const sheet = Assets.get("{{sprite_id}}.json");
const sprite = new AnimatedSprite(sheet.animations.walk);
sprite.anchor.set(0.5, 0.85);
sprite.texture.source.scaleMode = "nearest";
```

## Frame naming

```
{{sprite_id}}_{animation}_{frame_index}
```

Examples: `plague_nurgling_idle_0`, `plague_nurgling_payload_2`, `plague_nurgling_blocked_5`

## Grid layout (512×896)

```text
列→  0    1    2    3    4    5    6    7
     64px cells (x = col * 64)
行↓
 0   idle (4 frames, rest empty)
 1   walk (6)
 2   run (8)
 3   research (6)
 4   payload (6)
 5   mutate (6)
 6   handoff (6)
 7   spawn (8)
 8   blocked (6)
 9   hit (3)
10   killed (8)
11   victory (8)
12   promoted (8)
13   fastest_crash (8)
```

Row pixel y = `row * 64`. Character faces **right**. Feet on shared baseline (anchor y = 0.85).

## Example: plague_nurgling

Work order fields:

- `sprite_id`: `plague_nurgling`
- `display_name`: `Plague Nurgling`
- Traits: olive-green pudgy creature, brown horns, yellow eyes, toothy grin, slime effects

Runtime prompt: see `pi-mono/packages/ux-lab/assets/battle-sprites/plague_nurgling/plague_nurgling-runtime-prompt-canonical.json`

## What to return to orchestrator

```json
{
  "sprite_id": "{{sprite_id}}",
  "png": "skills/battle/assets/sprites/pixijs/{{sprite_id}}.png",
  "json": "skills/battle/assets/sprites/pixijs/{{sprite_id}}.json",
  "validate_png": "PASS",
  "validate_json": "PASS",
  "source": "runtime_image_gen|contact_conversion_fallback",
  "notes": ""
}
```
