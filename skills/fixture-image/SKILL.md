---
name: fixture-image
description: >
  DEPRECATED - Use /create-image instead. Renamed for clarity.
allowed-tools: Bash, Read, Write
triggers: []  # Triggers removed - use /create-image instead
metadata:
  short-description: "DEPRECATED - Use /create-image instead"
  deprecated: true
  deprecated-since: "2026-01-29"
  replacement: "/create-image"
---

# fixture-image (DEPRECATED)

> **This skill has been renamed to `/create-image`.**
>
> | Old | New |
> |-----|-----|
> | `fixture-image` | `create-image` |

## Why the Change?

The `create-*` naming convention is more intuitive for agents:
- `create-table` - Creates detectable PDF tables
- `create-image` - Creates images (AI/Mermaid/placeholder)
- `create-figure` - Creates publication figures (50+ types)
- `create-icon` - Creates Stream Deck icons
- `create-pdf-fixture` - Creates test PDF fixtures

## Quick Migration

```bash
# Old
./fixture-image/run.sh ...

# New
./create-image/run.sh ...
```
