---
name: create-text
description: >
  Deterministic public-domain text corpus chunker with seeded selectors for
  reproducible sampling across engineering/government corpora.
allowed-tools: Bash, Read, Write
triggers:
  - create text
  - text chunker
  - deterministic text
  - build text bank
  - select text chunks
metadata:
  short-description: "Deterministic corpus text chunker"
provides:
  - create-text
composes:
  - ingest-doc
  - extract-pdf
  - best-practices-python
complies:
  - best-practices-skills
  - best-practices-python
disciplines:
  - data-engineering
---

# /create-text

Deterministic public-domain text corpus chunker with seeded selector.

## Quick Start

```bash
# Build text banks from extracted datalake corpus
./run.sh build

# Build from Wikipedia (specific categories)
./run.sh build --source wikipedia --categories "Cybersecurity" "Avionics"

# Get 16 requirement-style text chunks from defense domain, seed 42
./run.sh select --content-type requirement --domain defense --count 16 --seed 42

# Get prose paragraphs from any domain
./run.sh select --content-type prose --count 8 --seed 7

# List available domains and content types
./run.sh list
```

## Content Types

| Type | Description | Source |
|------|-------------|--------|
| `prose` | Continuous paragraphs (3+ sentences) | PDF corpus, Wikipedia |
| `bullet_list` | Enumerated/bulleted items | PDF corpus |
| `requirement` | Unconditional SHALL/MUST clauses | PDF corpus (MIL-STD, ECSS, NASA-STD) |
| `conditional_requirement` | When/If/Unless + SHALL guard clauses | PDF corpus (engineering specs) |
| `compound_requirement` | SHALL + enumerated sub-obligations | PDF corpus (rare — extractors split blocks) |
| `heading` | Section headers at various levels | PDF corpus |
| `latex_equation` | Math equations (raw LaTeX or unicode) | PDF corpus (arxiv) |
| `table_cell` | Table content fragments | PDF corpus |
| `glossary` | Definition-style entries | PDF corpus, Wikipedia |
| `footnote` | Footnote/endnote text | PDF corpus |

## Domains

Auto-discovered from datalake at `/mnt/storage12tb/extractor_corpus/`.
Common domains: `arxiv`, `defense`, `government`, `engineering`, `nasa`, `nist`, `ietf`, `wikipedia`.

## Interface

```python
from create_text import create_text

# Deterministic: same seed = same output
chunks = create_text(content_type="requirement", domain="defense", count=16, seed=42)
# Returns: list[dict] with keys: text, content_type, domain, source_doc, block_id
```

## Banks

Built once via `./run.sh build`, stored as JSON at `/mnt/storage12tb/text_banks/`.
One file per domain: `defense.json`, `arxiv.json`, `wikipedia.json`, etc.

## Common Mistakes

```bash
# WRONG: Generate synthetic text with an LLM
# → Use real extracted text for ground truth

# WRONG: Random selection without seed
# → Always pass a seed for reproducibility

# WRONG: Build banks on every call
# → Banks are built once and cached. Use ./run.sh build explicitly.
```
