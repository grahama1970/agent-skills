---
name: arxiv
description: >
  Search arXiv for academic papers. Use when user says "find papers on",
  "search arxiv", "look up research", "academic papers about", "what papers exist on",
  "use your arxiv tool", or asks about scientific/ML research topics.
allowed-tools: Bash, Read, WebFetch
triggers:
  - find papers on
  - search arxiv
  - look up research
  - academic papers about
  - recent papers on
  - arxiv search
  - use your arxiv tool
metadata:
  short-description: arXiv paper search and retrieval
---

# arXiv Research Skill

Search, retrieve, and analyze papers from arXiv.org.

## Quick Start

```bash
# Search recent papers on a topic
python .agents/skills/arxiv/arxiv_cli.py search -q "hypergraph transformer" -n 10 --months 18

# Filter by ML categories
python .agents/skills/arxiv/arxiv_cli.py search -q "LLM reasoning" -c cs.LG -c cs.AI -n 15

# Get paper details (includes HTML link)
python .agents/skills/arxiv/arxiv_cli.py get -i 2211.09590

# Download PDF
python .agents/skills/arxiv/arxiv_cli.py download -i 2211.09590 -o ./papers/
```

## Commands

### Search Papers

```bash
python .agents/skills/arxiv/arxiv_cli.py search \
  --query "graph neural networks" \
  --max-results 10 \
  --category cs.LG \
  --months 12
```

**Options:**
| Option | Short | Description |
|--------|-------|-------------|
| `--query` | `-q` | Search query (required) |
| `--max-results` | `-n` | Max results (default: 10) |
| `--sort-by` | `-s` | `relevance`, `date`, `lastUpdatedDate` |
| `--category` | `-c` | Filter by category (repeatable) |
| `--months` | `-m` | Papers from last N months |
| `--since` | | Filter after date (YYYY-MM-DD) |
| `--until` | | Filter before date (YYYY-MM-DD) |
| `--smart` | | Use LLM to translate natural language to arXiv query |

**Examples:**
```bash
# Recent hypergraph papers in ML
python .agents/skills/arxiv/arxiv_cli.py search -q "hypergraph" -c cs.LG --months 18

# Attention papers from 2024
python .agents/skills/arxiv/arxiv_cli.py search -q "attention mechanism" --since 2024-01-01

# Multiple categories
python .agents/skills/arxiv/arxiv_cli.py search -q "transformer" -c cs.CV -c cs.LG -n 20

# Smart mode - natural language query (uses scillm for translation)
python .agents/skills/arxiv/arxiv_cli.py search --smart \
  -q "papers on hypergraph transformers for machine learning" \
  --months 18 -n 10
```

### Smart Query Mode

The `--smart` flag uses scillm to translate natural language to arXiv query syntax:

```bash
# Input: natural language
python arxiv_cli.py search --smart -q "recent work on LLM reasoning and chain of thought"

# LLM translates to:
# (ti:LLM OR ti:language model) AND (ti:reasoning OR abs:chain of thought)
```

**Requires:** `CHUTES_API_KEY` and `CHUTES_MODEL_ID` environment variables.

### Get Paper Details

```bash
python .agents/skills/arxiv/arxiv_cli.py get --paper-id 2301.00001
```

Returns full metadata including `html_url` for ar5iv HTML version.

### Download PDF

```bash
python .agents/skills/arxiv/arxiv_cli.py download \
  --paper-id 2301.00001 \
  --output ./papers/
```

### List Categories

```bash
python .agents/skills/arxiv/arxiv_cli.py categories
```

Common categories:
- `cs.LG` - Machine Learning
- `cs.AI` - Artificial Intelligence
- `cs.CL` - Computation and Language (NLP)
- `cs.CV` - Computer Vision
- `cs.NE` - Neural and Evolutionary Computing
- `stat.ML` - Machine Learning (Stats)

## Output Format

All commands output JSON:
```json
{
  "meta": {
    "query": "hypergraph transformer",
    "count": 5,
    "took_ms": 234,
    "filters": {"categories": ["cs.LG"], "since": "2024-07-01"}
  },
  "items": [
    {
      "id": "2211.09590v5",
      "title": "Hypergraph Transformer for Skeleton-based Action Recognition",
      "abstract": "...",
      "authors": ["Author 1", "Author 2"],
      "published": "2022-11-17",
      "pdf_url": "https://arxiv.org/pdf/2211.09590.pdf",
      "abs_url": "https://arxiv.org/abs/2211.09590v5",
      "html_url": "https://ar5iv.org/abs/2211.09590",
      "categories": ["cs.CV"],
      "primary_category": "cs.CV"
    }
  ],
  "errors": []
}
```

**Key URLs:**
- `pdf_url` - Direct PDF download
- `abs_url` - arXiv abstract page
- `html_url` - ar5iv HTML rendering (better for reading, no PDF needed)

## Common Research Queries

```bash
# "Find all papers on X from the past Y months"
python .agents/skills/arxiv/arxiv_cli.py search -q "hypergraph transformer" --months 18 -n 20

# "Find ML papers on X"
python .agents/skills/arxiv/arxiv_cli.py search -q "knowledge distillation" -c cs.LG -c cs.AI -n 15

# "What's new in X this year?"
python .agents/skills/arxiv/arxiv_cli.py search -q "mixture of experts" --since 2025-01-01 -s date
```

## Integration with Memory

After finding useful papers:
```bash
# Search for papers
python .agents/skills/arxiv/arxiv_cli.py search --query "..." > papers.json

# Ingest into memory (if using memory project)
memory-agent workspace-ingest --source papers.json --scope arxiv
```

## Rate Limits

arXiv API has rate limits (~30 requests/minute). The CLI handles this automatically with backoff.

## No API Key Required

arXiv API is free and open - no authentication needed.
