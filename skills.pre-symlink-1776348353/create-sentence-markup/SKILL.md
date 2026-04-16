---
name: create-sentence-markup
description: >
  Grammarly-like sentence decomposition with NVIS confidence colors.
  Decomposes question text into annotated fragments showing which entities
  resolved, which are misspelled, which are fabricated, and which are unknown.
  Composes /extract-entities for grounding data and /interview for "Did you mean?" clarify prompts.
allowed-tools: [Bash, Read]
triggers:
  - markup sentence
  - annotate sentence
  - sentence markup
  - create sentence markup
  - grammarly
  - highlight entities
metadata:
  short-description: NVIS-colored sentence annotation from entity grounding
  author: "Claude"
  version: "0.1.0"
provides:
  - sentence-markup
composes:
  - extract-entities
  - interview
---

# /create-sentence-markup

Grammarly-like sentence decomposition with NVIS confidence colors (MIL-STD-3009).

## Usage

```bash
# Annotate a question — returns JSON annotations
./run.sh annotate "How does SPARTA control X23-MUSTARD mitigate spoofing?"

# Annotate with rendered markdown output
./run.sh annotate "How does the SPRTA framework work?" --format markdown

# Annotate with HTML output (NVIS colors)
./run.sh annotate "What countermesures protect firmware?" --format html

# Pipe from /extract-entities (skip redundant extraction)
./run.sh annotate --entities-json entities.json "How does X23-MUSTARD work?"
```

## Output (JSON default)

```json
{
  "text": "How does SPARTA control X23-MUSTARD mitigate spoofing?",
  "annotations": [
    {
      "term": "X23-MUSTARD",
      "level": "RED",
      "label": "fabricated ID — not in corpus",
      "action": "reject",
      "closest_match": "CM0028"
    },
    {
      "term": "SPARTA",
      "level": "GREEN",
      "label": "confirmed framework",
      "action": null
    }
  ],
  "summary": {
    "total_annotations": 2,
    "red": 1,
    "amber": 0,
    "yellow": 0,
    "green": 1,
    "needs_clarify": 0,
    "needs_reject": 1
  }
}
```

## NVIS Color System (MIL-STD-3009)

| Level | Color | RGB | Meaning | Action |
|-------|-------|-----|---------|--------|
| GREEN | Green | (0,255,136) | Exact match — confirmed in corpus | None |
| AMBER | Amber | (255,170,0) | Fuzzy match or misspelling | /memory clarify via /interview |
| RED | Red | (255,68,68) | Fabricated ID — not in corpus | Reject |
| YELLOW | Yellow | (255,230,0) | Term not found anywhere | Investigate |

## Composition

- **Input**: Question text (string)
- **Depends on**: `/extract-entities` → `get_annotations()` for grounding data
- **Triggers**: `/interview` for AMBER "Did you mean?" clarify prompts
- **Consumed by**: `/create-evidence-case` (report grounding), `/ask` (inline annotations),
  `/lean4-prove` (proof obligations from RED/YELLOW annotations)

## Output Formats

| Format | Flag | Use case |
|--------|------|----------|
| JSON | `--format json` (default) | Machine-readable, piping to other skills |
| Markdown | `--format markdown` | Agent/human readable in terminal |
| HTML | `--format html` | Rich rendering with NVIS colors |
