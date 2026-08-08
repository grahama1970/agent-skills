---
name: compliance-timeline
description: Chronological audit timeline of compliance changes from ArangoDB revision history
triggers:
  - "compliance timeline"
  - "audit timeline"
  - "show changes"
allowed-tools:
  - Bash
provides:
  - compliance-timeline
composes:
  - task-monitor
  - agentic-evals
disciplines:
  - compliance-security
  - memory-knowledge
---

# compliance-timeline

Chronological audit view of compliance changes from append-only revision
collections in ArangoDB (`lessons` database). Queries `lesson_revisions` and
`edge_revisions` to build a unified timeline of every compliance mutation.

## Usage

```bash
# Show last 30 days of compliance changes (default)
./run.sh show --days 30

# Filter to a specific scope
./run.sh show --scope sparta

# Show changes between two dates
./run.sh diff --from 2026-01-01 --to 2026-02-01

# Dry-run mode -- sample data, no ArangoDB required
./run.sh show --days 30 --dry-run
./run.sh diff --from 2026-01-01 --to 2026-02-01 --dry-run
```

## Subcommands

### show

Display a chronological table of compliance changes.

| Flag        | Default | Description                        |
|-------------|---------|------------------------------------|
| `--days N`  | 30      | How many days back to query        |
| `--scope S` |         | Filter to a specific scope/domain  |
| `--dry-run` |         | Emit sample data without querying  |

### diff

Show changes between two explicit dates.

| Flag         | Required | Description            |
|--------------|----------|------------------------|
| `--from`     | yes      | Start date (ISO-8601)  |
| `--to`       | yes      | End date (ISO-8601)    |
| `--dry-run`  |          | Emit sample data       |

## Output

```
TIMESTAMP            | ACTION   | SCOPE          | DOCUMENT                     | DETAIL
---------------------+----------+----------------+------------------------------+-------------------------------
2026-02-18T14:32:00Z | CREATE   | sparta         | ctrl/AC-2                    | Added access control baseline
2026-02-18T15:10:00Z | UPDATE   | manufacturing  | proc/welding-spec-7A         | Tolerance changed 0.05 -> 0.03
```
