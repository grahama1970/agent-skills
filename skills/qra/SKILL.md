---
name: qra
description: >
  ⚠️ DEPRECATED - Use /doc2qra instead. This skill has been merged into /doc2qra.
  Migration: './run.sh --file text.md' → './doc2qra/run.sh --file text.md'
allowed-tools: [Bash, Read]
triggers: []  # Triggers removed - use /doc2qra instead
metadata:
  short-description: "DEPRECATED - Use /doc2qra instead"
  deprecated: true
  deprecated-since: "2026-01-29"
  replacement: "/doc2qra"
---

# QRA (DEPRECATED)

> ⚠️ **This skill has been merged into /doc2qra.**
>
> Use `doc2qra` instead:
>
> | Old Command | New Command |
> |-------------|-------------|
> | `./run.sh --file text.md --scope X` | `./doc2qra/run.sh --file text.md --scope X` |
> | `./run.sh --text "content" --scope X` | `./doc2qra/run.sh --text "content" --scope X` |
> | `./run.sh --dry-run` | `./doc2qra/run.sh --dry-run` |

## Why the Change?

The `doc2qra` skill is more descriptive and consolidates three overlapping skills:
- `distill` → merged into `doc2qra`
- `qra` → merged into `doc2qra`
- `doc-to-qra` → merged into `doc2qra`

## New Features in doc2qra

- **Document Summary**: Always generates a 2-3 paragraph summary alongside QRAs
- **`--summary-only`**: Generate only the summary without Q&A extraction
- **Unified triggers**: All QRA-related commands route to one skill
- **PDF Support**: Now handles PDFs directly (no need for separate distill)

## Quick Migration

```bash
# Old
./qra/run.sh --file notes.txt --scope research

# New
./doc2qra/run.sh --file notes.txt --scope research
```
