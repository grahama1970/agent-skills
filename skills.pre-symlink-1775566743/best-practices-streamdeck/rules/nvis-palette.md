---
title: Use NVIS Palette for Tactical and Widget Icons
impact: MEDIUM
impactDescription: Inconsistent colors break visual coherence and MIL-STD-3009 compliance
tags: nvis, palette, icons, rendering, mil-std
---

## Use NVIS Palette for Tactical and Widget Icons

All dynamically rendered icons (widgets, sentinel HUD, generated buttons) must use the NVIS color palette from `nvis_base.py`. This ensures MIL-STD-3009 compliance and visual consistency.

**Incorrect:**
```python
# Random colors, no consistency
img = Image.new("RGB", (72, 72), (0, 0, 0))
draw = ImageDraw.Draw(img)
draw.text((36, 36), "OK", fill=(0, 255, 0))  # Pure green — too bright
```

**Correct:**
```python
from streamdeck.widgets.nvis_base import (
    C_BG, C_GREEN, C_AMBER, C_RED, C_BLUE, C_WHITE, C_DIM,
    FONTS, new_icon, draw_label, draw_value, draw_unit,
)

img, draw = new_icon()  # (8, 10, 12) background
draw_label(draw, "STATUS")
draw_value(draw, "OK", color=C_GREEN)  # (0, 255, 136) — NVIS green
```

### NVIS Palette Reference

| Name | RGB | Usage |
|------|-----|-------|
| `C_BG` | (8, 10, 12) | Background |
| `C_GREEN` | (0, 255, 136) | Healthy, nominal, ownship |
| `C_RED` | (255, 68, 68) | Critical, hostile, failed |
| `C_AMBER` | (255, 170, 0) | Warning, degraded |
| `C_BLUE` | (68, 170, 255) | Info, friendly |
| `C_WHITE` | (200, 200, 200) | Text labels |
| `C_DIM` | (80, 80, 80) | Muted, secondary text |
| `C_YELLOW` | (255, 230, 0) | Unknown |

### Standard Helpers

```python
new_icon()          # → (Image, Draw) — 72x72 RGB with C_BG background
draw_label(draw, "LABEL")  # Dim tiny text at top (max 8 chars)
draw_value(draw, "42%", color=C_GREEN)  # Large centered value
draw_unit(draw, "MB/s")    # Dim tiny text at bottom
draw_bar(draw, 75, color=C_AMBER)  # Horizontal progress bar
status_color("warn")       # → C_AMBER — string to color mapping
```

### Notes
- `icon_generator.py` also supports NVIS via `palette="nvis"` parameter
- Standard (non-tactical) pages can use `palette="standard"` with lighter colors
- Font stack: DejaVu Sans Mono Bold → Liberation Mono Bold → fallback
- Pillow must use `.anchor="mt"` (middle-top) for centered text
