---
name: ingest-website
description: >
  Ingest an entire website into /memory as a RAG resource. Chains /fetcher
  (crawl + render JS pages) → /extractor (structured extraction) →
  /doc2qra (extract QRAs) → /taxonomy (bridge tags) → /memory (store).
  Supports image download and local file output.
triggers:
  - ingest website
  - website to memory
  - website to rag
  - crawl website to knowledge
  - turn website into rag resource
  - ingest web documentation
  - learn from website
  - website knowledge base
metadata:
  short-description: Website → RAG resource via fetcher + doc2qra + memory
provides:
  - ingest-website
composes:
  - fetcher
  - extractor
  - doc2qra
  - memory
  - taxonomy
  - embedding
  - task-monitor
taxonomy:
  - operational
disciplines:
  - data-engineering
  - memory-knowledge
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Ingest Website

Single command to ingest a website into `/memory` as a RAG resource:

```
/fetcher (crawl) → /extractor (structured extraction) → /doc2qra (QRA extraction) → /taxonomy (bridge tags) → /memory (store)
```

## Quick Start

```bash
# Ingest a website into memory
./run.sh ingest https://sparta.aerospace.org/resources --scope sparta

# Ingest with image download
./run.sh ingest https://example.com/docs --scope research --images

# Ingest specific URLs (not crawl)
./run.sh ingest --urls urls.txt --scope research

# Save fetched content to local files
./run.sh ingest https://example.com/docs --scope research --output-dir ./reference/

# Dry run (fetch + save locally, no memory storage)
./run.sh ingest https://example.com/docs --dry-run --output-dir ./docs/
```

## Commands

### `ingest` - Fetch website and store as RAG resource

| Option | Description |
|--------|-------------|
| `URL` | Base URL to crawl (follows same-domain links) |
| `--urls FILE` | File with one URL per line (skip crawl) |
| `--scope NAME` | Memory scope (default: research) |
| `--images` | Download images (PNG, JPG, SVG) to output dir |
| `--output-dir DIR` | Save fetched pages as local markdown/images |
| `--max-pages N` | Max pages to fetch (default: 50) |
| `--depth N` | Max crawl depth from base URL (default: 2) |
| `--dry-run` | Fetch + save locally, skip memory storage |
| `--no-qra` | Store raw text chunks, skip QRA extraction |
| `--delay MS` | Delay between requests in ms (default: 500) |

## Pipeline

1. **Crawl** (`/fetcher`): Fetch base URL, extract same-domain links, fetch linked pages up to `--depth` and `--max-pages`.
2. **Images** (optional): Download referenced images to `--output-dir`.
3. **Extract** (`/extractor`): Run structured extraction on fetched HTML via HTMLProvider. Produces clean markdown from raw HTML.
4. **Save** (optional): Write extracted content as markdown files to `--output-dir`.
5. **QRA Extract** (`/doc2qra`): Extract Q&A pairs from each page. doc2qra handles taxonomy + embedding internally.
6. **Taxonomy** (`/taxonomy`): Extract federated bridge tags (Precision, Resilience, etc.) — used on `--no-qra` path.
7. **Store** (`/memory`): Batch learn QRA pairs with bridge tags and source tracking tags.
8. **Post-hooks**: Trigger `/embedding` vectors and edge proposal for graph traversal.

## Output

```
Fetched: 13 pages from sparta.aerospace.org
Images: 4 downloaded to ./reference/images/
Stored: 88 QRA pairs in scope 'sparta'
Saved: 13 markdown files to ./reference/
```

## Integration

- `/dogpile` can use this to turn research findings into permanent RAG
- `/ux-lab` uses this for reference product documentation (SPARTA, ATT&CK)
- `/learn-datalake` can compose this for web source ingestion
