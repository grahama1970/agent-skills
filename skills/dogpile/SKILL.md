---
name: dogpile
description: >
  Deep research aggregator that searches Brave (Web), Perplexity (AI), GitHub (Code/Issues),
  ArXiv (Papers), YouTube (Videos), and Wayback Machine simultaneously.
  Provides a consolidated Markdown report with an ambiguity check and Agentic Handoff.
allowed-tools:
  - run_command
  - read_file
triggers:
  - dogpile
  - research
  - deep search
  - find code
  - search everything
metadata:
  short-description: Deep research aggregator (Web, AI, Code, Papers, Videos)
---

# Dogpile: Deep Research Aggregator

Orchestrate a multi-source deep search to "dogpile" on a problem from every angle.

## Analyzed Sources

1.  **Codex (🤖)**: High-reasoning technical starting point and final synthesis (gpt-5.2).
2.  **Perplexity (🧠)**: AI-synthesized deep answers and reasoning (Sonar Reasoning).
3.  **Brave Search (🌐)**: **Three-Stage Search** (Search → Evaluate → Deep Extract via /fetcher).
4.  **ArXiv (📄)**: **Three-Stage Search** (Abstracts → Details → Full Paper via /fetcher + /extractor).
5.  **YouTube (📺)**: **Two-Stage Search** (Metadata → Detailed Transcripts via Whisper/Direct).
6.  **GitHub (🐙)**: **Three-Stage Search**:
    - **Stage 1**: Search repositories and issues
    - **Stage 2**: Fetch README.md and metadata for top repos, agent evaluates relevance
    - **Stage 3**: Deep code search inside the selected repository
7.  **Wayback Machine (🏛️)**: Historical snapshots for URLs.

## Features

1.  **Query Tailoring**: Uses Codex to generate service-specific queries optimized for each source:
    - **ArXiv**: Academic/technical terms
    - **Perplexity**: Natural language questions
    - **Brave**: Documentation-style queries
    - **GitHub**: Code patterns, library names
    - **YouTube**: Tutorial-style phrases

2.  **Ambiguity Guard**: Uses Codex High Reasoning to analyze the query first. If ambiguous, it asks you for clarification before wasting resources.

3.  **Three-Stage Deep Dive**:
    - **ArXiv**: Fetches detailed metadata → Agent evaluates → Full PDF extraction via /fetcher + /extractor
    - **GitHub**: Fetches README + metadata → Agent evaluates most relevant repo → Deep code search
    - **Brave**: Fetches results → Agent evaluates → Full page extraction via /fetcher
    - **YouTube**: Extracts full transcripts for the most relevant videos

4.  **Codex Synthesis**: Consolidates all results into a coherent, high-reasoning conclusion.

5.  **Textual TUI Monitor**: Real-time progress tracking of all concurrent searches via `run.sh monitor`.

6.  **Resilience Features** (2025-2026 Best Practices):
    - **Per-provider semaphores**: Limits concurrent requests to avoid rate limit bans
    - **Exponential backoff with jitter**: Prevents thundering herd on retries (via tenacity)
    - **Rate limit header parsing**: Respects Retry-After, x-ratelimit-*, and IETF RateLimit-* headers
    - **Automatic retry**: Retries rate-limited requests after appropriate backoff

## GitHub Three-Stage Search

The GitHub search uses intelligent evaluation to find the most relevant repository:

```
Stage 1: Broad Search
├── Search repos: gh search repos "query"
├── Search issues: gh search issues "query"
└── Returns: Top 5 repos and issues

Stage 2: README Analysis & Evaluation
├── For top 3 repos:
│   ├── gh repo view <repo> --json ... (metadata)
│   ├── gh api repos/<repo>/readme (README content)
│   └── gh api repos/<repo>/languages (language breakdown)
├── Codex evaluates based on:
│   ├── README content relevance
│   ├── Topics and tags
│   ├── Language/tech stack match
│   └── Activity (stars, recent updates)
└── Returns: Selected target repository

Stage 3: Deep Code Search
├── gh api repos/<repo>/contents (file tree)
├── gh search code --repo <repo> "query" (code matches)
└── Returns: File structure + code locations with context
```

## Presets (For Security Research)

**Don't think about 100+ resources. Pick ONE preset:**

| Preset | Use When |
|--------|----------|
| `vulnerability_research` | CVE lookup, exploit availability |
| `red_team` | Privesc, bypasses, payloads |
| `blue_team` | Detection rules, threat hunting |
| `threat_intel` | APT groups, IOCs, campaigns |
| `malware_analysis` | Sample analysis, sandboxes |
| `osint` | Recon, domain intel |
| `bleeding_edge` | Latest zero-days |
| `community` | Reddit, Discord discussions |
| `general` | Non-security research |

```bash
# Use a preset (recommended for security research)
./run.sh search "CVE-2024-1234" --preset vulnerability_research
./run.sh search "privesc linux" --preset red_team

# Auto-detect preset from query
./run.sh search "CVE-2024-1234" --auto-preset

# List all presets
python dogpile.py presets
```

Presets use **Brave site: filters** to search curated domains (Exploit-DB, GTFOBins, MITRE ATT&CK, etc.) plus **direct API calls** for resources with APIs (NVD, CISA KEV, MalwareBazaar).

## Commands

- `./run.sh search "query"`: Run a search.
- `./run.sh search "query" --preset NAME`: Search with a preset.
- `./run.sh monitor`: Open the Real-time TUI Monitor.
- `python dogpile.py presets`: List available presets.
- `python dogpile.py resources`: List all resources.

## Usage

```bash
# General research
./run.sh search "AI agent memory systems"

# Security research with preset
./run.sh search "CVE-2024-1234" --preset vulnerability_research
```

## Agentic Handoff

The skill automatically analyzes queries for ambiguity.

- If the query is clear (e.g., "python sort list"), it proceeds.
- If ambiguous (e.g., "apple"), it returns a JSON object with clarifying questions.
  - The calling agent should interpret this JSON and ask the user the questions.
