---
title: Socket for Live Updates, Config for Persistent State
impact: CRITICAL
impactDescription: Writing config for icon-only changes triggers race conditions with widget services
tags: architecture, socket, config, race-condition
---

## Socket for Live Updates, Config for Persistent State

The streamdeck-ui service saves in-memory state to `~/.streamdeck_ui.json` on EVERY API mutation (`_save_state()`). Widget services send `set_icon` every 1-5s, each triggering a save. Writing config directly for icon changes creates race conditions.

**Incorrect:**
```python
# Writing config to change an icon — widget services will overwrite before reload
config = json.load(open("~/.streamdeck_ui.json"))
config["state"][deck_id]["buttons"]["0"]["0"]["states"]["0"]["icon"] = new_icon
json.dump(config, open("~/.streamdeck_ui.json", "w"))
```

**Correct:**
```python
from streamdeck.utils.icon_updater import update_streamdeck_icon

# Icon-only update → socket (fast, immediate, no config write)
update_streamdeck_icon(button_index=5, icon_path="icon/new.png", page=0)

# Command/switch_page/text change → config write (persistent, with locking)
update_streamdeck_button(button_index=5, command="new_command", page=0)
```

### When to Use Each

| Change | Method | Persists? |
|--------|--------|-----------|
| Icon only | Socket `set_icon` | No (widget refreshes it) |
| Command | Config write + fcntl lock | Yes |
| Switch page | Config write + fcntl lock | Yes |
| Text label | Config write + fcntl lock | Yes |
| New page | `build_page()` socket command | Yes (via API _save_state) |

### Notes
- `icon_updater.py` handles this automatically — use `update_streamdeck_icon()` or `update_streamdeck_button()`
- Config writes MUST use fcntl exclusive lock via `~/.streamdeck_ui.json.lock`
- Widget services (clock, weather, sentinel) own their button icons — don't fight them
