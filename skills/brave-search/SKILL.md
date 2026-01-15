---
name: brave-search
description: >
  Free web and local search via Brave Search API. Use when user says "brave search",
  "search with brave", "brave web search", "brave local search", "local search",
  "find businesses near", or "near me".
allowed-tools: Bash, Read
triggers:
  - brave search
  - search with brave
  - brave web search
  - brave local search
  - local search
  - find businesses near
  - find restaurants near
  - near me
  - free search
metadata:
  short-description: Web + local search via Brave API
---

# Brave Search

Web and local search using the Brave Search API. Returns raw results (not LLM-summarized).

## Prerequisites

- `BRAVE_API_KEY` or `BRAVE_SEARCH_API_KEY` in environment or `.env`
- Install CLI deps: `pip install typer`

## When to Use

- You need raw web results without LLM synthesis
- You want local business info (addresses, ratings, phone numbers)
- You want a second opinion vs other search tools

## Quick Start

```bash
# Web search (JSON by default)
python .agents/skills/brave-search/brave_search.py web "site:openai.com gpt-4o"

# Local search
python .agents/skills/brave-search/brave_search.py local "coffee near Cambridge MA" --no-json
```

## CLI Usage

```bash
python .agents/skills/brave-search/brave_search.py web "query" [--count N] [--offset N] [--json/--no-json]
python .agents/skills/brave-search/brave_search.py local "query" [--count N] [--json/--no-json]
```

## Python API

```python
from brave_search import web_search, local_search

results = web_search("site:openai.com gpt-4o", count=5)
local = local_search("pizza near Boston", count=5)
```

## Agent Tool Usage (MCP)

If MCP tools are available, prefer:
- `mcp__brave-search__brave_web_search` for general web queries
- `mcp__brave-search__brave_local_search` for places/nearby queries

## Examples

```bash
python .agents/skills/brave-search/brave_search.py web "ArangoDB ArangoSearch BM25"
python .agents/skills/brave-search/brave_search.py local "restaurants near Pike Place Market" --no-json
```

## Tips

- Use `--no-json` for quick human-readable output
- Local search falls back to web if no locations are found
