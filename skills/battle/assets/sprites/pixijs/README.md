# BATTLE PixiJS runner sprite atlases — single folder

Everything for runtime sprites, prompts, contact sheets, and worker handoffs lives **here**.

## Runtime assets (ship to Pixi)

| File | Purpose |
|------|---------|
| `{sprite_id}.png` | 512×896 RGBA runtime atlas |
| `{sprite_id}.json` | PixiJS spritesheet manifest |
| `battle-sprite-assets.manifest.json` | Index of all runtime sprites |

## Image-gen prompts (per character)

| File | Purpose |
|------|---------|
| `{sprite_id}-runtime-prompt-canonical.json` | **Use this** for production atlas image gen |
| `{sprite_id}-runtime-prompt.json` | Standard runtime prompt |
| `{sprite_id}-contact-prompt.json` | Contact sheet prompt (art review only) |
| `{sprite_id}-contact-sheet.png` | Contact sheet image (**not** for Pixi) |

### plague_nurgling (example)

```
plague_nurgling-runtime-prompt-canonical.json   ← feed to image model
plague_nurgling-contact-sheet.png               ← reference only
plague_nurgling.png + plague_nurgling.json      ← runtime (currently contact-converted, needs regen)
plague_nurgling.work-order.json                 ← filled worker job
```

## Worker templates

| File | Purpose |
|------|---------|
| `sprite-work-order.template.json` | Copy + fill for any character |
| `contact-sheet-prompt.template.txt` | Contact sheet text template |
| `runtime-atlas-prompt.template.txt` | Runtime atlas text template |
| `negative-prompt.txt` | Negative prompt block |
| `SPRITE-PIPELINE.md` | Commands, validation, do-not list |

## Shared prompts (`prompts/`)

Canonical copies from `skills/battle/prompts/`:

- `runtime-atlas-canonical.txt`
- `runtime-atlas-template.txt`
- `spacing-repair.txt`
- `pixijs-json-manifest.txt`

## Grid contract

- 8×14 grid, 64×64 cells → 512×896 PNG
- Anchor `0.5, 0.85`, nearest-neighbor, real RGBA transparency

## Validate

```bash
SKILL=skills/create-battle-sprite-sheet
$SKILL/run.sh validate-png --png skills/battle/assets/sprites/pixijs/{sprite_id}.png
```

## Characters with prompts in this folder

- `plague_nurgling`
- `crimson_hornbreaker`
- `crimson_chainsword_berserker`
- `crimson_chainsaw_demon`

Runtime PNG+JSON also present for: `blue_lizard`, `green_horn`, `nurgling`, `purple_horn_imp`, `red_human`, `skull_horn`, `slug_demon`, `typhus` (no prompt JSONs copied — generate from templates).
