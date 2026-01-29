---
name: fixture-table
description: >
  DEPRECATED - Use /create-table instead. Renamed for clarity.
allowed-tools: Bash, Read, Write
triggers: []  # Triggers removed - use /create-table instead
metadata:
  short-description: "DEPRECATED - Use /create-table instead"
  deprecated: true
  deprecated-since: "2026-01-29"
  replacement: "/create-table"
---

# fixture-table (DEPRECATED)

> **This skill has been renamed to `/create-table`.**
>
> | Old | New |
> |-----|-----|
> | `fixture-table` | `create-table` |

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
./fixture-table/run.sh ...

# New
./create-table/run.sh ...
```
