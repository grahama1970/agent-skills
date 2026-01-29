---
name: pdf-fixture
description: >
  DEPRECATED - Use /create-pdf-fixture instead. Renamed for consistency.
allowed-tools: Bash, Read, Write
triggers: []  # Triggers removed - use /create-pdf-fixture instead
metadata:
  short-description: "DEPRECATED - Use /create-pdf-fixture instead"
  deprecated: true
  deprecated-since: "2026-01-29"
  replacement: "/create-pdf-fixture"
---

# pdf-fixture (DEPRECATED)

> **This skill has been renamed to `/create-pdf-fixture`.**
>
> | Old | New |
> |-----|-----|
> | `pdf-fixture` | `create-pdf-fixture` |

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
./pdf-fixture/run.sh ...

# New
./create-pdf-fixture/run.sh ...
```
