---
title: Use the Right Skill for Stream Deck Operations
impact: MEDIUM
impactDescription: Using the wrong tool leads to icon format issues, broken templates, or manual work that skills automate
tags: skills, tools, workflow, icons
---

## Use the Right Skill for Stream Deck Operations

The Stream Deck has dedicated skills for common operations. Use them instead of manual file editing or ad-hoc scripts.

### Available Skills

| Skill | When to Use |
|-------|-------------|
| `/create-icon` | Create new icons — fetches from web, resizes to 72x72 RGB, handles palettes |
| `/create-streamdeck-page` | Design and deploy new page layouts with button definitions |
| `/ops-streamdeck` | Restart services, check health, push pages, toggle widgets |
| `/streamdeck-lab` | Evaluate pages, test context rules, benchmark anticipation |

### Icon Sources

When you need new icons, `/create-icon` handles the full pipeline. It uses:

1. **Lucide CDN** — primary source for consistent line icons (e.g. `shield-check`, `git-branch`)
2. **Pillow generation** — text labels, status indicators, gauges via `icon_generator.py` or `nvis_base.py`
3. **Web fetch + resize** — any URL, auto-converted to 72x72 RGB PNG

**Incorrect:**
```bash
# Manual download + hope the format is right
wget https://example.com/icon.png -O icon/my_icon.png
# ↑ Might be wrong size, RGBA, or SVG
```

**Correct:**
```
/create-icon shield-check --palette nvis
# or
/create-icon "https://example.com/icon.png" --name my_icon
```

### Page Creation Workflow

```
1. /create-streamdeck-page    → Design buttons, generate template JSON
2. /streamdeck-lab evaluate   → Test against context rules and anticipation
3. /ops-streamdeck push       → Deploy to hardware
```

### Operational Commands

```
/ops-streamdeck restart       → Restart streamdeck.service + widget_renderer
/ops-streamdeck status        → Check all services + socket health
/ops-streamdeck push <page>   → Push a template to hardware
/ops-streamdeck reload        → Reload config without restart
```

### Notes
- Always prefer `/create-icon` over manual icon creation — it enforces 72x72 RGB
- `/streamdeck-lab evaluate-all` tests backward compat with filesystem templates
- `/ops-streamdeck` knows about the socket API, config locking, and service lifecycle
- Templates live in `config/page_templates/` — edit with `/create-streamdeck-page`, not by hand
