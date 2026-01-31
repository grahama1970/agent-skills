---
name: consume-feed
description: >
  Manage and run nightly ingestion of upstream feeds (RSS, GitHub, NVD).
  Fetch updates, store summaries in ArangoDB, and integrate with Memory.
  Use this skill to "check for updates" or "add a new source" to the knowledge graph.
triggers:
  - pull the feeds
  - run feed ingest
  - check upstream updates
  - fetch nightly updates
  - add rss feed
  - add github repo
  - track nvd
  - check feed ingest health
metadata:
  short-description: Ingest RSS/GitHub/NVD feeds into Memory
---

# Consume Feed Skill

A robust, resilient ingestion engine for upstream data sources.

## Triggers

- "Pull the feeds now" -> `run --mode manual`
- "Add this RSS feed <url>" -> `sources add rss --url <url>`
- "Add GitHub repo <owner>/<repo>" -> `sources add github --repo <owner>/<repo>`
- "Track NVD for <keyword>" -> `sources add nvd --query <keyword>`
- "Check feed ingest health" -> `doctor`

## Usage

### Run Ingestion

```bash
# Run nightly crawl (all sources, respect intervals)
./run.sh run --mode nightly

# Run specific source immediately
./run.sh run --source <key>
```

### Manage Sources

```bash
# Add RSS
./run.sh sources add rss --url "https://github.blog/feed/"

# Add GitHub (Releases, Issues, Discussions)
./run.sh sources add github --repo "microsoft/vscode"

# Add NVD (Security Vulnerabilities)
./run.sh sources add nvd --query "paramiko"
```

### Diagnosis

```bash
./run.sh doctor
```

## Resilience

- Uses **exponential backoff** and **jitter** for all network requests.
- Persists **checkpoints** (ETags, Timestamps) to resume efficiently.
- Stores **deadletters** for inspection on failure.
