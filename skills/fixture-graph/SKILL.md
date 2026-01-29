---
name: fixture-graph
description: >
  DEPRECATED - Use /create-figure instead. Renamed for clarity.
allowed-tools: Bash, Read
triggers: []  # Triggers removed - use /create-figure instead
metadata:
  short-description: "DEPRECATED - Use /create-figure instead"
  deprecated: true
  deprecated-since: "2026-01-29"
  replacement: "/create-figure"
---

# fixture-graph (DEPRECATED)

> **This skill has been renamed to `/create-figure`.**
>
> | Old | New |
> |-----|-----|
> | `fixture-graph` | `create-figure` |

## Why the Change?

The name "fixture-graph" was misleading - this skill does far more than PDF fixture generation:
- 50+ visualization types (charts, plots, UML, etc.)
- Publication-quality IEEE figures
- Multiple domains (ML, control systems, biology, etc.)

The `create-*` naming convention is more intuitive for agents:
- `create-table` - Creates detectable PDF tables
- `create-image` - Creates images (AI/Mermaid/placeholder)
- `create-figure` - Creates publication figures (50+ types)
- `create-icon` - Creates Stream Deck icons
- `create-pdf-fixture` - Creates test PDF fixtures

## Quick Migration

```bash
# Old
./fixture-graph/run.sh ...

# New
./create-figure/run.sh ...
```
