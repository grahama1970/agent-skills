---
name: ingest-kindle
description: >
  Ingest Kindle books and highlights into the library pipeline.
  Parses My Clippings.txt, converts .epub/.mobi/.azw3 to text,
  and outputs to ~/clawd/library/books/ for downstream QRA extraction.
triggers:
  - ingest kindle
  - kindle highlights
  - my clippings
  - kindle book
  - import kindle
  - parse clippings
allowed-tools:
  - Bash
  - Read
metadata:
  clawdbot:
    emoji: "📖"
    requires:
      bins:
        - uv

provides:
  - ingest-kindle
composes:
  - memory
  - consume-book
  - doc2qra
  - task-monitor
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# ingest-kindle

**Ingest Kindle books and highlights into the library pipeline.**

Parses My Clippings.txt for highlights/annotations, converts ebooks (.epub, .mobi, .azw3) to markdown text, and outputs to `~/clawd/library/books/<Title>/` for downstream processing with `/consume-book` and `/doc2qra`.

## Quick Start

```bash
# Parse Kindle highlights
./run.sh clippings /media/kindle/documents/My\ Clippings.txt

# Ingest a single ebook
./run.sh ingest book.epub --scope hasard_lee

# Batch process a directory of Kindle exports
./run.sh ingest-all ~/kindle-exports/

# Check progress
./run.sh status

# Verify dependencies
./run.sh health
```

## Commands

| Command | Description |
|---------|-------------|
| `clippings [path]` | Parse My Clippings.txt into structured highlights JSON |
| `ingest <file>` | Process single .epub/.mobi/.azw3 to text.md |
| `ingest-all [dir]` | Batch process Kindle export directory |
| `status [--json]` | Show ingestion progress |
| `health` | Verify dependencies (ebooklib, calibre) |

## Output Structure

```
~/clawd/library/books/<Title>/
├── text.md           # Full extracted text
├── highlights.json   # Structured highlights from My Clippings
└── metadata.json     # Author, title, ASIN, format
```

The `<!-- EXTRACTION_COMPLETE -->` marker in text.md signals downstream tools that extraction finished successfully (follows ingest-audiobook quality gate pattern).

## Pipeline Integration

```
Kindle Device/App
    │
    ├── My Clippings.txt ──→ clippings ──→ highlights.json
    │
    └── .epub/.mobi/.azw3 ──→ ingest ──→ text.md
                                              │
                                    ┌─────────┴──────────┐
                                    │                      │
                              /consume-book          /doc2qra
                            (search, annotate)    (QRA extraction)
```

## Format Support

| Format | Library | Notes |
|--------|---------|-------|
| `.epub` | ebooklib | Native Python, no external deps |
| `.mobi` | calibre `ebook-convert` | Optional external dep |
| `.azw3` | calibre `ebook-convert` | Optional external dep |
| My Clippings.txt | Pure Python parser | Well-defined format |

## My Clippings.txt Format

Kindle stores all highlights/notes in a single file with this structure:

```
Book Title (Author Name)
- Your Highlight on page 42 | Location 612-615 | Added on Monday, January 15, 2024 12:30:00 AM

The highlighted text goes here.
==========
```

The parser handles:
- Highlights, notes, and bookmarks
- Multiple books in one file
- Unicode content
- Various date formats

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KINDLE_LIBRARY_DIR` | `~/clawd/library/books` | Output directory |
| `KINDLE_CLIPPINGS_PATH` | - | Default path to My Clippings.txt |

## Dependencies

- `ebooklib` — EPUB parsing (pure Python)
- `typer` — CLI framework
- `rich` — Terminal output
- `python-dotenv` — Environment loading
- `calibre` ebook-convert CLI — Optional, for .mobi/.azw3 conversion
