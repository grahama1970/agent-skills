---
title: Always Use build_page for New Pages
impact: CRITICAL
impactDescription: Writing config then reloading causes race conditions — widget services overwrite before reload fires
tags: pages, build_page, race-condition, architecture
---

## Always Use build_page for New Pages

New pages MUST be created via the atomic `build_page` socket command. Never write config then call `reload_config` — widget services overwrite config before the QTimer reload fires.

**Incorrect:**
```python
# Write config then reload — RACE CONDITION
config["state"][deck_id]["buttons"]["10"] = page_data
json.dump(config, open(CONFIG_PATH, "w"))
send_socket_command({"command": "reload_config"})
# ↑ Widget services write _save_state() between dump and reload
```

**Also incorrect:**
```python
# Send individual set_icon for new pages — crashes
for i, btn in enumerate(buttons):
    send_socket_command({"command": "set_icon", "page": 10, "button": i, ...})
# ↑ DisplayGrid.pages doesn't have page 10 yet → KeyError crash
```

**Correct:**
```python
from streamdeck.utils.page_builder import build_page, ButtonDef

buttons = [ButtonDef(icon="icon/foo.png", text="FOO", command="do_foo"), ...]
build_page(buttons, page_idx=10, back_page=0, navigate=True)
```

The `build_page` socket command atomically:
1. Creates page in API state via `_button_state()`
2. Initializes page in `DisplayGrid` via `initialize_page()`
3. Sets all button properties (runs synchronously on socket thread)
4. Rebuilds UI tabs via `QTimer.singleShot(0, build_device)` (deferred to Qt)

### Page Index Conventions

| Range | Usage | Example |
|-------|-------|---------|
| 0-9 | Static/manual pages | Home (0), Prompts (2), Sentinel (2) |
| 10+ | Dynamic context/topic pages | Context monitor, topic pages, generated |

### Notes
- `push_page()` is the agent-friendly wrapper — handles template loading + index management
- `build_page()` falls back to config writes when socket unavailable (offline/testing)
- Back button auto-wired at position 31 unless you pass `back_page=-1`
- Page removal still uses config write + reload_config (no socket delete command yet)
