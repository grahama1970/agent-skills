---
name: best-practices-streamdeck
description: >
  Project-specific best practices for the Stream Deck control suite: icon format constraints,
  socket vs config boundaries, widget button lifecycle, page creation via build_page,
  ArangoDB fallback patterns, and NVIS palette compliance.
triggers:
  - best practices streamdeck
  - stream deck
  - streamdeck widget
  - streamdeck button
  - NVIS palette
license: MIT
metadata:
  hardware: Stream Deck XL (32 buttons, 96x96 native, 72x72 rendered)
  defaults:
    icon_format: 72x72 RGB PNG
    socket_path: /tmp/streamdeck_ui.sock
    config_path: ~/.streamdeck_ui.json
    page_indexing: 0-9 static, 10+ dynamic
    palette: nvis (MIL-STD-3009)
    logging: loguru
    cli: typer

provides:
  - best-practices-streamdeck
composes:
  - task-monitor
disciplines:
  - engineering-standards
  - developer-tooling
---

# Stream Deck Best Practices (Project Skill)

Curated rules for building and maintaining the Stream Deck control suite.
Covers hardware constraints, service architecture, and the widget lifecycle.

## Project Architecture

- **streamdeck-ui**: Qt app reading `~/.streamdeck_ui.json`, rendering buttons
- **Socket API**: `/tmp/streamdeck_ui.sock` for real-time updates (fast, no disk)
- **Config file**: `~/.streamdeck_ui.json` for persistent state (slow, locked)
- **Widget services**: background daemons rendering icons on schedule
- **Context monitor**: polls environment every 2s, switches pages via templates
- **ArangoDB**: memory graph for pages/buttons (optional, filesystem fallback)

## When to Apply

Use this skill whenever you:
- Create or modify Stream Deck pages, buttons, or templates
- Build a new widget renderer or data source
- Write scripts that update the deck config
- Modify the socket API, context monitor, or page builder
- Work with icons, palettes, or the NVIS display layer

## Categories (priority order)

1. **Hardware Constraints** — icon format, button count, display limits
2. **Socket vs Config** — when to use each, race condition avoidance
3. **Widget Lifecycle** — self-updating buttons, render scripts, cache busting
4. **Page Management** — creation, indexing, context rules, anticipation
5. **ArangoDB Integration** — fallback patterns, collection conventions
6. **NVIS Palette** — MIL-STD-3009 colors, font stack, rendering primitives
