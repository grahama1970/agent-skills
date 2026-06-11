# Pre-Upload Quality Gate

Run this checklist before uploading an asset to Kling.

## File and count checks

```text
[ ] One Element contains 2–4 reference images.
[ ] Each image is .jpg, .jpeg, or .png.
[ ] Each image is at least 300 px wide and 300 px tall.
[ ] Each image is 10 MB or less.
[ ] Filenames are ordered and descriptive.
[ ] The main image is the clearest front/hero reference.
```

## Visual consistency checks

```text
[ ] Same character/prop/scene across all references.
[ ] Same style and realism level.
[ ] Same outfit/material/color palette unless variants are intentional.
[ ] No contradictory scars, logos, symbols, side placement, or scale.
[ ] No important detail is cropped off or hidden.
[ ] No extra characters or props unless they are part of the asset.
[ ] No large text, labels, arrows, or watermarks over the subject.
```

## Description checks

```text
[ ] Core identity is clear.
[ ] Key details are listed.
[ ] Do-not-change items are specific.
[ ] Allowed variation is explicit.
[ ] Ignore list covers temporary background, pose, labels, holder hands, stands, and shadows.
[ ] Video prompt uses subject movement and background movement.
```

## Common final fixes

- If the model may confuse the grid as multiple subjects, upload separate panels instead.
- If outfit consistency matters, remove alternate outfits from the pack.
- If the asset has critical left/right details, verify every reference agrees.
- If the prop scale matters, include a scale reference.
- If the scene layout matters, include a wide view and list landmark positions.
