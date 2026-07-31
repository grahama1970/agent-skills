# Battle PixiJS runtime sprite atlas prompts

Canonical prompts for generating production-ready PixiJS v8 sprite atlases for BATTLE race-engine characters.

These prompts enforce **runtime atlas** layout (fixed grid, no contact-sheet drift), not presentation sheets with labels, panels, or decorative backgrounds.

## Files

| File | Use |
|------|-----|
| `runtime-atlas-canonical.txt` | Full canonical image-generation prompt (fixed wording) |
| `runtime-atlas-template.txt` | Parameterized form for agents/scripts (`{CHARACTER_NAME}`, `{VARIANT_ID}`, etc.) |
| `negative-prompt.txt` | Negative prompt block for models that support it |
| `spacing-repair.txt` | Reformat pass when art is good but grid spacing is wrong |
| `pixijs-json-manifest.txt` | Separate JSON manifest generation (never embed JSON in the image) |

## Production pipeline

Image generation alone may still fail exact atlas geometry. The reliable pipeline is:

1. Generate visual sprite sheet (use `runtime-atlas-canonical.txt` or `runtime-atlas-template.txt`).
2. Use a script or artist cleanup to snap frames into exact cells.
3. Export transparent PNG atlas.
4. Generate PixiJS JSON from row definitions (`pixijs-json-manifest.txt`).
5. Validate dimensions, transparency, frame count, and empty cells.

Finished runtime assets:

```text
{variant_id}.png
{variant_id}.json
```

Not an annotated contact sheet.

## Grid contract

- **8 columns × 14 rows**
- **64×64** cells → **512×896** atlas (humanoid)
- **96×64** cells → **768×896** atlas (wide slug, tail, beast, long-body)
- Anchor: `{ "x": 0.5, "y": 0.85 }`

## Animation rows

| Row | Animation | Frames |
|-----|-----------|--------|
| 0 | idle | 4 |
| 1 | walk | 6 |
| 2 | run | 8 |
| 3 | research | 6 |
| 4 | payload | 6 |
| 5 | mutate | 6 |
| 6 | handoff | 6 |
| 7 | spawn | 8 |
| 8 | blocked | 6 |
| 9 | hit | 3 |
| 10 | killed | 8 |
| 11 | victory | 8 |
| 12 | promoted | 8 |
| 13 | fastest_crash | 8 |

Rows with fewer than 8 frames leave remaining cells fully transparent.
