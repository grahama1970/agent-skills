---
name: brave-search
description: >
  Free web, local, LLM Context, and optional Summarizer search via Brave Search API. Use when user says "brave search",
  "search with brave", "brave web search", "brave local search", "local search",
  "find businesses near", "near me", "Brave LLM context", or "Brave summarizer".
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
provides:
  - web-search
  - llm-context-search
composes:
  - dogpile
  - task-monitor

taxonomy:
  - research
  - web
---

# Brave Search

Web, local, LLM Context, and optional Summarizer search using the Brave Search
API. The normal `web` command returns raw results unless `--summary-key` is
requested. Use `context` when the caller is an LLM/agent and needs extracted
grounding context.

## Prerequisites

- `BRAVE_API_KEY` or `BRAVE_SEARCH_API_KEY` in environment or `.env`
- Optional `BRAVE_API_KEY_PAID` for explicit summary/LLM-context lanes. The paid
  key is necessary for those lanes in this skill, but not sufficient proof that
  the account has Brave AI entitlement. Do not spend the paid key for default
  raw web search.
- Install CLI deps: `pip install typer`
- Default to the free key for `web` and `local`. A project agent must explicitly
  request `context`, `summarize`, or `web --summary-key` before the paid key is
  used.
- LLM Context, Summarizer Search, and Answers access depend on the active Brave
  Search API plan. If the endpoint returns 400/403 plan errors such as
  `OPTION_NOT_IN_PLAN`, or no `summarizer.key` is returned, report the lane as
  unavailable for that query/plan and fall back to raw `web` plus Dogpile/Tau
  synthesis.

## When to Use

- You need raw web results without LLM synthesis
- You need LLM-ready grounding context from Brave's LLM Context endpoint
- You need Brave's own AI summary and the plan supports Summarizer Search
- You want local business info (addresses, ratings, phone numbers)
- You want a second opinion vs other search tools

## Quick Start

```bash
# Web search (JSON by default)
python .pi/skills/brave-search/brave_search.py web "site:openai.com gpt-4o"

# LLM Context search for agent/RAG grounding
python .pi/skills/brave-search/brave_search.py context "site:github.com satellite security testbed" --max-tokens 4096

# Request a summarizer key from web search
python .pi/skills/brave-search/brave_search.py web "spacecraft cybersecurity testbed" --summary-key

# Fetch Brave Summarizer output when available
python .pi/skills/brave-search/brave_search.py summarize "spacecraft cybersecurity testbed"

# Local search
python .pi/skills/brave-search/brave_search.py local "coffee near Cambridge MA" --no-json
```

## CLI Usage

```bash
python .pi/skills/brave-search/brave_search.py web "query" [--count N] [--offset N] [--json/--no-json]
python .pi/skills/brave-search/brave_search.py web "query" [--freshness pw] [--extra-snippets] [--summary-key]
python .pi/skills/brave-search/brave_search.py context "query" [--count N] [--max-urls N] [--max-tokens N] [--threshold strict|balanced|lenient|disabled]
python .pi/skills/brave-search/brave_search.py summarize "query" [--entity-info] [--no-inline-references]
python .pi/skills/brave-search/brave_search.py local "query" [--count N] [--json/--no-json]
```

## Python API

```python
from brave_search import web_search, local_search, llm_context, summarize_search

results = web_search("site:openai.com gpt-4o", count=5)
context = llm_context("site:github.com satellite security testbed", max_tokens=4096)
summary = summarize_search("spacecraft cybersecurity testbed")
local = local_search("pizza near Boston", count=5)
```

## Brave AI Endpoints

Official references:

- Web Search API: <https://api-dashboard.search.brave.com/api-reference/web/search/get>
- LLM Context API: <https://api-dashboard.search.brave.com/api-reference/summarizer/llm_context/get>
- LLM Context service guide: <https://api-dashboard.search.brave.com/documentation/services/llm-context>
- Summarizer Search guide: <https://api-dashboard.search.brave.com/app/documentation/summarizer-search>

Use `context` for RAG/agent grounding. It calls
`GET https://api.search.brave.com/res/v1/llm/context` and returns Brave's raw
context response with source metadata when the plan allows it.

Use `summarize` only when Brave's own summary is desired. It first calls
`/res/v1/web/search` with `summary=1`, treats `summarizer.key` as opaque, then
calls `/res/v1/summarizer/search`. If no key is returned, the command reports
`skipped_no_summary_key` instead of inventing an answer. If key generation or
summary retrieval returns a plan/request error, the command reports
`unavailable_plan_or_request_error`.

Brave's documentation says Summarizer Search is deprecated in favor of the newer
Answers API, while existing Summarizer access remains tied to discontinued Pro
AI-plan entitlement. Treat `BRAVE_API_KEY_PAID` as a separate explicit-spend key,
not as proof that Summarizer, LLM Context, or Answers is enabled.

## Agent Tool Usage (MCP)

If MCP tools are available, prefer:
- `mcp__brave-search__brave_web_search` for general web queries
- `mcp__brave-search__brave_local_search` for places/nearby queries

## Examples

```bash
python .pi/skills/brave-search/brave_search.py web "ArangoDB ArangoSearch BM25"
python .pi/skills/brave-search/brave_search.py local "restaurants near Pike Place Market" --no-json
```

## Tips

- Use `--no-json` for quick human-readable output
- Use `context` instead of raw `web` when another LLM or agent will consume the
  output directly.
- Use concurrent `web` or `context` calls with different queries for sparse
  domains before handing candidate URLs to `$github-search` or Dogpile.
- Use `--freshness pw` for pages from the last 7 days, or a custom
  `YYYY-MM-DDtoYYYY-MM-DD` freshness range when the date window matters.
- Local search falls back to web if no locations are found
