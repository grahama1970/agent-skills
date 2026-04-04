---
title: Widget Button Lifecycle — Self-Updating Buttons
impact: CRITICAL
impactDescription: Incorrect widget setup causes icon flicker, stale displays, or race conditions
tags: widgets, lifecycle, architecture, self-updating
---

## Widget Button Lifecycle — Self-Updating Buttons

Self-updating buttons (clock, weather, system monitor, CMMC status, etc.) follow a strict lifecycle. The widget service owns the icon — templates and config must not set it.

### The Four Layers

```
┌─────────────────────────────────────────────┐
│ 1. REGISTRATION (widget_buttons.yaml)       │
│    name, render_script, refresh_seconds,    │
│    page, position, data_source              │
├─────────────────────────────────────────────┤
│ 2. RENDERER (widgets/<name>_render.py)      │
│    def render() -> Image.Image (72x72 RGB)  │
│    Reads data_source, returns Pillow image  │
├─────────────────────────────────────────────┤
│ 3. SCHEDULER (widget_renderer.py)           │
│    Calls render() on schedule, saves with   │
│    toggle (_0/_1), pushes via socket        │
├─────────────────────────────────────────────┤
│ 4. TEMPLATE (page_templates/<page>.json)    │
│    Button has "widget": "<name>"            │
│    Icon MUST be "" — widget owns it         │
└─────────────────────────────────────────────┘
```

### Creating a New Widget

**Step 1: Write the renderer** (`src/streamdeck/widgets/my_widget_render.py`):
```python
"""My widget — one-line description of what it shows.

Data source: reads /tmp/my_data.json (or URL, or shell command).
"""
from PIL import Image
from streamdeck.widgets.nvis_base import (
    C_BG, C_GREEN, C_AMBER, C_RED, C_WHITE, C_DIM,
    FONTS, new_icon, draw_label, draw_value, draw_unit, draw_bar,
)

DATA_FILE = Path("/tmp/my_data.json")

def render() -> Image.Image:
    """Return a 72x72 RGB PIL Image. Called on schedule by widget_renderer."""
    img, draw = new_icon()        # Always 72x72 RGB
    draw_label(draw, "MYWIDGET")  # Max 8 chars, dim text at top

    data = _read_data()
    if data is None:
        draw.text((36, 28), "N/A", font=FONTS["large"], fill=C_DIM, anchor="mt")
        draw_unit(draw, "NO DATA")
        return img

    # Render your visualization
    value = data.get("value", 0)
    color = C_GREEN if value > 80 else C_AMBER if value > 50 else C_RED
    draw_value(draw, f"{value}%", color=color)
    draw_bar(draw, value, color=color)

    return img
```

**Step 2: Register** in `config/widget_buttons.yaml`:
```yaml
widgets:
  - name: my_widget
    render_script: streamdeck.widgets.my_widget_render
    refresh_seconds: 30
    data_source: /tmp/my_data.json
    page: 0
    position: 5
    icon_path: icon/widget_my_widget.png
    enabled: true
```

**Step 3: Template button** must have empty icon and widget field:
```json
{
    "icon": "",
    "command": "streamdeck-cli widget my_widget --details",
    "text": "MYWDGT",
    "widget": "my_widget"
}
```

### Cache Busting

The scheduler alternates between `_0.png` and `_1.png` paths so streamdeck-ui detects the file change:

```python
# widget_renderer.py does this automatically:
path_0 = "icon/widget_my_widget_0.png"  # even ticks
path_1 = "icon/widget_my_widget_1.png"  # odd ticks
stable  = "icon/widget_my_widget.png"   # always-current copy for config refs
```

**Incorrect:**
```python
# Saving to the same path every time — streamdeck-ui may cache the old icon
img.save("icon/widget_my_widget.png")
update_streamdeck_icon(5, "icon/widget_my_widget.png")
```

**Correct:**
```python
# Let widget_renderer handle toggle automatically
# OR if doing it manually:
from streamdeck.utils.widget_button import get_icon_toggle_paths
path_0, path_1 = get_icon_toggle_paths("my_widget")
save_path = path_1 if toggle else path_0
img.save(save_path)
update_streamdeck_icon(position, save_path)
```

### Common Mistakes

| Mistake | Consequence | Fix |
|---------|-------------|-----|
| Setting icon in template | Widget overwrites it immediately | Set `"icon": ""` and add `"widget": "name"` |
| Writing config for icon update | Race with widget save cycle | Use socket `set_icon` only |
| No `render() -> Image.Image` signature | Scheduler can't call it | Must return PIL Image, no args |
| Forgetting `new_icon()` | Wrong size/mode | Always start with `nvis_base.new_icon()` |
| Not registering in widget_buttons.yaml | Scheduler doesn't know about it | Add entry with page + position |

### Notes
- The `nvis_base` module provides all NVIS palette colors and standard drawing helpers
- Data sources can be: JSON file, URL, shell command output, or AQL query
- `refresh_seconds` controls update frequency — 5s for clock, 30-60s for status widgets
- Singleton lock at `/tmp/streamdeck_widgets.lock` prevents duplicate renderers
