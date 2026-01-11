---
name: memory
description: Search and recall from persistent knowledge base. Use for finding previous solutions, logging episodes, and agent-to-agent coordination.
allowed-tools: Bash, Read
metadata:
  short-description: Graph-based knowledge recall for AI agents
---

# Memory - Knowledge Recall

Search and recall from a persistent "Lessons Learned" knowledge base with graph traversal, episode logging, and agent coordination.

## Simplest Usage

```bash
memory-agent search --q "cdp puppeteer timeout" --scope tabbed --k 5
memory-agent recall --q "authentication error" --scope tabbed --depth 2
memory-agent add-episode --text "Fixed by increasing timeout to 30s" --scope tabbed
```

## Common Patterns

### Search for solutions
```bash
# Basic search (BM25 + graph fusion)
memory-agent search --q "rate limit 429" --scope tabbed --k 5

# Search with temporal filter (last 30 days)
memory-agent search --q "playwright" --scope tabbed --within-days 30

# Search anchored to specific lesson
memory-agent search --q "proxy" --scope tabbed --anchor "IPRoyal Setup"
```

### Deep recall with graph traversal
```bash
# Multihop recall (finds related solutions)
memory-agent recall --q "browser automation fails" --scope tabbed --depth 2

# With dense embeddings (semantic similarity)
memory-agent recall --q "authentication" --scope tabbed --use-dense --mmr
```

### Understand why a result matched
```bash
# Get explanation for a specific lesson
memory-agent explain --key lessons/123 --q "original query" --scope tabbed

# Find related lessons by title
memory-agent related --title "CDP Connection Guide" --scope tabbed
```

### Log episodes (learning from experience)
```bash
# Log a success
memory-agent add-episode --text "Fixed timeout by setting 30s limit" \
  --scope tabbed --status success --thread-id thr-123

# Log a failure (for future reference)
memory-agent add-episode --text "Proxy rotation failed on cloudflare" \
  --scope tabbed --status failure --promote-if-novel
```

### Provide feedback
```bash
# Mark lesson as helpful
memory-agent feedback --lesson-title "CDP Setup Guide" --helpful --note "Solved my issue"

# Mark as not helpful
memory-agent feedback --lesson-title "Old Auth Method" --not-helpful
```

### Agent-to-agent coordination
```bash
# Send request to another agent
memory-agent agent-request-add --agent-from "extractor" --agent-to "fetcher" \
  --request '{"cmd": "fetch", "url": "https://example.com"}'

# Check inbox for pending requests
memory-agent agent-request-list --agent "fetcher" --status pending

# Acknowledge/claim a request
memory-agent agent-request-ack --id req-123 --agent "fetcher"
```

## Python API

```python
from graph_memory.api import MemoryClient

client = MemoryClient(scope="tabbed", k=5)

# Search
res = client.search("cdp puppeteer timeout")
for item in res['items']:
    print(item['title'], item['score'])

# Explain why it matched
ex = client.explain(res['items'][0]['_key'], q="cdp puppeteer timeout")

# Find related lessons
rel = client.related(title=res['items'][0]['title'])

# Multihop traversal
mh = client.multihop(title="CDP Setup", depth=2)

# Log episode
client.log_episode(
    status="success",
    title="Fixed CDP timeout",
    text="Increased timeout to 30s",
    promote_if_novel=True
)

# Add relationship
client.add_edge(from_title="CDP Timeout Error", to_title="Timeout Fix", type="solves")

# Provide feedback
client.feedback(lesson_title="CDP Setup Guide", helpful=True, note="Worked perfectly")
```

## Command Reference

| Category | Commands |
|----------|----------|
| **Search** | `search`, `recall`, `recall-diff`, `explain` |
| **Graph** | `related`, `multihop`, `add-edge`, `approve-edge`, `invalidate-edge` |
| **Episodes** | `add-episode`, `list-episodes` |
| **Feedback** | `feedback` |
| **Relationships** | `build-relationships`, `build-relationships-llm`, `llm-score-edges` |
| **Agent Comms** | `agent-request-add`, `agent-request-list`, `agent-request-ack` |
| **Workspace** | `workspace-detect`, `workspace-ingest`, `workspace-build` |
| **Knowledge** | `lessons-seed`, `lessons-arxiv`, `lessons-youtube` |

## Scopes

Scopes isolate knowledge for different contexts:

| Scope | Purpose |
|-------|---------|
| `tabbed` | Browser automation knowledge |
| `research` | Research and papers |
| `devops` | Infrastructure and deployment |
| `security` | Security and compliance |

## Response Format

All commands return JSON:

```json
{
  "meta": {"scope": "tabbed", "k": 5, "query": "..."},
  "items": [
    {"_key": "lessons/123", "title": "...", "score": 0.85, "text": "..."}
  ],
  "errors": []
}
```

## Agent Workflow

```
1. Encounter problem
   → memory-agent search --q "error message" --scope tabbed

2. Find related solutions
   → memory-agent recall --q "..." --depth 2

3. Understand match
   → memory-agent explain --key lessons/123 --q "..."

4. Apply solution and log outcome
   → memory-agent add-episode --text "..." --status success

5. Link problem to solution
   → memory-agent add-edge --from-title "Error" --to-title "Fix" --type solves

6. Future searches benefit from new relationship
```

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `MEMORY_ARANGO_URL` | ArangoDB connection URL |
| `MEMORY_ARANGO_DB` | Database name |
| `MEMORY_DEFAULT_SCOPE` | Default scope for queries |

## Troubleshooting

| Problem | Solution |
|---------|----------|
| No results | Try broader query or increase `--k` |
| Stale results | Use `--within-days` filter |
| Need context | Use `--depth 2` for multihop |
| Wrong scope | Check `--scope` parameter |
