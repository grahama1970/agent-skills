---
name: doc-to-qra
description: >
  ⚠️ DEPRECATED - Use /doc2qra instead. This skill has been merged into /doc2qra.
  Migration: './run.sh doc.pdf scope' → './doc2qra/run.sh --file doc.pdf --scope X'
allowed-tools: [Bash, Read]
triggers: []  # Triggers removed - use /doc2qra instead
metadata:
  short-description: "DEPRECATED - Use /doc2qra instead"
  deprecated: true
  deprecated-since: "2026-01-29"
  replacement: "/doc2qra"
---

# doc-to-qra (DEPRECATED)

> ⚠️ **This skill has been merged into /doc2qra.**
>
> Use `doc2qra` instead:
>
> | Old Command | New Command |
> |-------------|-------------|
> | `./run.sh doc.pdf scope` | `./doc2qra/run.sh --file doc.pdf --scope scope` |
> | `./run.sh URL scope` | `./doc2qra/run.sh --url URL --scope scope` |
> | `./run.sh doc.pdf scope "context"` | `./doc2qra/run.sh --file doc.pdf --scope scope --context "context"` |

## Why the Change?

The `doc2qra` skill is more descriptive and consolidates three overlapping skills:
- `distill` → merged into `doc2qra`
- `qra` → merged into `doc2qra`
- `doc-to-qra` → merged into `doc2qra`

## New Features in doc2qra

- **Document Summary**: Always generates a 2-3 paragraph summary alongside QRAs
- **`--summary-only`**: Generate only the summary without Q&A extraction
- **Unified triggers**: All QRA-related commands route to one skill
- **Consistent CLI**: Uses standard `--file`, `--url`, `--scope` flags

## Quick Migration

```bash
# Old
./doc-to-qra/run.sh paper.pdf research

# New
./doc2qra/run.sh --file paper.pdf --scope research
```
