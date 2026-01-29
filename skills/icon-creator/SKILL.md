---
name: icon-creator
description: >
  DEPRECATED - Use /create-icon instead. Renamed for consistency.
allowed-tools: ["Bash", "Read", "Write", "surf"]
triggers: []  # Triggers removed - use /create-icon instead
metadata:
  short-description: "DEPRECATED - Use /create-icon instead"
  deprecated: true
  deprecated-since: "2026-01-29"
  replacement: "/create-icon"
---

# icon-creator (DEPRECATED)

> **This skill has been renamed to `/create-icon`.**
>
> | Old | New |
> |-----|-----|
> | `icon-creator` | `create-icon` |

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
./icon-creator/run.sh ...

# New
./create-icon/run.sh ...
```
