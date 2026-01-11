---
name: memory
description: Search and recall from persistent knowledge base. Use for finding previous solutions, logging episodes, agent-to-agent coordination, and formal verification of claims.
allowed-tools: Bash, Read
metadata:
  short-description: Graph-based knowledge recall for AI agents
---

# Memory - Knowledge Recall

Search and recall from a persistent "Lessons Learned" knowledge base with graph traversal, episode logging, agent coordination, and optional formal proof verification.

## Simplest Usage

```bash
memory-agent search --q "cdp puppeteer timeout" --scope tabbed --k 5
memory-agent recall --q "authentication error" --scope tabbed --depth 2
memory-agent add-episode --text "Fixed by increasing timeout to 30s" --scope tabbed
```

## Formal Proof Integration

Memory integrates with `certainly-prover` and `scillm-completions` to formally verify claims using Lean4.

### Assess if a claim is provable
```bash
# Check if claim can be formalized in Lean4
memory-agent prove --assess "For all n, n + 0 = n"

# Returns:
# {
#   "provable": true,
#   "confidence": 0.95,
#   "reason": "Standard natural number identity",
#   "lean4_sketch": "theorem add_zero (n : Nat) : n + 0 = n",
#   "suggested_tactics": ["simp", "rfl"]
# }
```

### Log episode with proof assessment
```bash
# Assess and queue for proof if provable
memory-agent add-episode \
  --text "Array index i is valid when i < array.size" \
  --scope tabbed \
  --prove

# Assess only (don't queue, just check)
memory-agent add-episode \
  --text "Buffer size must be >= max chunk size" \
  --scope tabbed \
  --prove --assess-only
```

### Search for proved knowledge
```bash
# Only return formally verified lessons
memory-agent search --q "array bounds" --scope tabbed --proved-only

# Include proof status in results
memory-agent search --q "timeout" --scope tabbed --include-proofs
```

### Background proof processing
```bash
# Process pending proofs (run as daemon or cron)
memory-agent proof-worker --concurrency 4

# Manually prove pending lessons
memory-agent prove-pending --scope tabbed --limit 100

# Check proof queue status
memory-agent prove-status --scope tabbed
```

### Proof parameters
```bash
--prove              # Assess provability, queue if provable
--assess-only        # Only assess, don't queue for proof
--proved-only        # Filter results to proved lessons only
--include-proofs     # Include lean4_code in search results
--prove-timeout 30   # Timeout for proof attempts (seconds)
```

## How Proof Assessment Works

```
┌─────────────────────────────────────────────────────────────────┐
│  1. INLINE: DeepSeek Prover V2 assessment (~500ms)             │
│     via scillm.paved.chat_json(model=deepseek-prover-v2)       │
│     → Returns: provable, confidence, sketch, tactics            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  2. If provable: Queue for background proof                    │
│     Lesson tagged: proof_status="pending"                       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  3. BACKGROUND: certainly-prover attempts full proof           │
│     Uses sketch + tactics from assessment as hints             │
│     → Success: proof_status="proved", lean4_code stored        │
│     → Failure: retry with different tactics, then mark failed  │
└─────────────────────────────────────────────────────────────────┘
```

## Proof Status Values

| Status | Meaning |
|--------|---------|
| `null` | Never assessed (no --prove flag) |
| `pending` | Queued for proof, not yet attempted |
| `proving` | Currently being proved |
| `proved` | Formally verified in Lean4 |
| `failed` | Proof attempted but failed |
| `not_provable` | DeepSeek assessed as not formalizable |

## Common Patterns

### Search for solutions
```bash
# Basic search (BM25 + graph fusion)
memory-agent search --q "rate limit 429" --scope tabbed --k 5

# Search with temporal filter (last 30 days)
memory-agent search --q "playwright" --scope tabbed --within-days 30

# Search only proved knowledge (high confidence)
memory-agent search --q "bounds check" --scope tabbed --proved-only
```

### Deep recall with graph traversal
```bash
# Multihop recall (finds related solutions)
memory-agent recall --q "browser automation fails" --scope tabbed --depth 2

# With dense embeddings (semantic similarity)
memory-agent recall --q "authentication" --scope tabbed --use-dense --mmr
```

### Log episodes with proof
```bash
# Log and assess for provability
memory-agent add-episode \
  --text "For all timeouts t > latency, connection succeeds" \
  --scope tabbed \
  --status success \
  --prove

# Log without proof (fast path)
memory-agent add-episode \
  --text "Restart fixed the issue" \
  --scope tabbed \
  --status success
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

# Search proved only
res = client.search("array bounds", proved_only=True)

# Log episode with proof assessment
client.log_episode(
    status="success",
    title="Array bounds theorem",
    text="For all i < a.size, a[i] is valid",
    prove=True,  # Assess and queue for proof
)

# Check if claim is provable
assessment = client.assess_provability(
    "For all n, n + 1 > n"
)
if assessment["provable"]:
    print(f"Sketch: {assessment['lean4_sketch']}")

# Get proof status for a lesson
lesson = client.get("lessons/123")
print(lesson["proof_status"])  # "proved", "pending", etc.
print(lesson["lean4_code"])    # The Lean4 proof if proved
```

## Command Reference

| Category | Commands |
|----------|----------|
| **Search** | `search`, `recall`, `recall-diff`, `explain` |
| **Graph** | `related`, `multihop`, `add-edge`, `approve-edge` |
| **Episodes** | `add-episode`, `list-episodes` |
| **Proofs** | `prove --assess`, `prove-pending`, `proof-worker`, `prove-status` |
| **Feedback** | `feedback` |
| **Relationships** | `build-relationships`, `build-relationships-llm` |
| **Agent Comms** | `agent-request-add`, `agent-request-list`, `agent-request-ack` |
| **Workspace** | `workspace-detect`, `workspace-ingest`, `workspace-build` |

## Parameterized Knowledge

When multiple lessons describe the same pattern with different values, proof assessment can generalize them:

```
Before (3 lessons):
  "Timeout of 30s fixed CDP"
  "Timeout of 45s fixed CDP on slow network"
  "Timeout of 20s was enough locally"

After (1 parameterized theorem):
  theorem timeout_sufficient (t latency : Nat) :
    t > latency + margin → cdp_succeeds t

  Parameters: latency (runtime), margin (5s proved sufficient)
```

Use `--prove` to enable automatic parameterization of similar lessons.

## Scopes

| Scope | Purpose |
|-------|---------|
| `tabbed` | Browser automation knowledge |
| `research` | Research and papers |
| `devops` | Infrastructure and deployment |
| `security` | Security and compliance |

## Response Format

```json
{
  "meta": {"scope": "tabbed", "k": 5, "query": "..."},
  "items": [
    {
      "_key": "lessons/123",
      "title": "Array Bounds Check",
      "score": 0.85,
      "text": "...",
      "proof_status": "proved",
      "lean4_code": "theorem array_valid..."
    }
  ],
  "errors": []
}
```

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `MEMORY_ARANGO_URL` | ArangoDB connection URL |
| `MEMORY_ARANGO_DB` | Database name |
| `MEMORY_DEFAULT_SCOPE` | Default scope for queries |
| `OPENROUTER_API_KEY` | For DeepSeek Prover V2 assessment |
| `MEMORY_PROOF_WORKER_CONCURRENCY` | Background worker parallelism |

## Troubleshooting

| Problem | Solution |
|---------|----------|
| No results | Try broader query or increase `--k` |
| Stale results | Use `--within-days` filter |
| Need context | Use `--depth 2` for multihop |
| Proof stuck | Check `prove-status`, increase timeout |
| Not provable | Claim may be heuristic, not mathematical |
