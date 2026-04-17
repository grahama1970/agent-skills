---
name: embedding
description: >
  Dual-backend embedding service for semantic search. Text-only (MiniLM, 384d)
  and multimodal (Qwen3-VL-Embedding-2B via vLLM, 2048d). Persistent Docker
  containers with automatic routing by modality.
internal: true
allowed-tools: Bash, WebFetch
triggers:
  - embed this
  - embed text
  - start embedding service
  - get embeddings
  - generate vectors
  - semantic search vectors
  - multimodal embedding
  - embed image
metadata:
  short-description: Dual-backend embedding service (text + multimodal)
provides:
  - embedding
composes:
  - memory
  - edge-verifier
  - scillm
  - task-monitor

taxonomy:
  - search
  - similarity
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Embedding Skill

Dual-backend embedding service for semantic search across any database.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    embed.py (routing layer)                   │
│  Routes by modality: text → :8602, multimodal → :8603        │
└────────────┬──────────────────────────────┬──────────────────┘
             │                              │
   ┌─────────▼──────────┐       ┌──────────▼───────────┐
   │ memory-embedding    │       │ embry-embedding-mm   │
   │ MiniLM-L6-v2       │       │ Qwen3-VL-Embed-2B   │
   │ 384 dims, CPU/GPU  │       │ 2048 dims, GPU       │
   │ sentence-transformers│      │ vLLM                │
   │ Port 8602           │       │ Port 8603            │
   └─────────────────────┘       └──────────────────────┘
             │                              │
   ┌─────────▼──────────────────────────────▼──────────┐
   │  ArangoDB: doc.embedding (384d) ← existing        │
   │            doc.embedding_visual (2048d) ← new  │
   └───────────────────────────────────────────────────┘
```

## Quick Start

```bash
# Start both backends
docker compose -f .pi/skills/embedding/docker-compose.yml up -d

# Start only multimodal backend
docker compose -f .pi/skills/embedding/docker-compose.yml up -d memory-embedding-mm

# Text embedding (MiniLM, 384d — existing behavior)
./run.sh embed --text "your query here"

# Multimodal embedding (Qwen3-VL, 2048d)
./run.sh embed --text "your query here" --multimodal

# Check both backends
./run.sh info
```

## Commands

| Command                                | Description                                     |
| -------------------------------------- | ----------------------------------------------- |
| `./run.sh serve`                       | Start FastAPI server (text backend, inside container) |
| `./run.sh embed --text "..." `         | Embed via text backend (384d)                   |
| `./run.sh embed --text "..." -m`       | Embed via multimodal backend (2048d)            |
| `./run.sh embed-batch --file f.txt`    | Batch embed via text backend                    |
| `./run.sh embed-batch --file f.txt -m` | Batch embed via multimodal backend              |
| `./run.sh info`                        | Show status of both backends                    |

## Backfill: embedding_visual Field

The backfill script writes `embedding_visual` (2048d) alongside existing `embedding` (384d).
**Never overwrites the `embedding` field.**

```bash
# Check coverage
uv run --project .pi/skills/embedding python .pi/skills/embedding/backfill_multimodal.py status

# Dry run
uv run --project .pi/skills/embedding python .pi/skills/embedding/backfill_multimodal.py embed --dry-run

# Run backfill (all collections, resumable)
uv run --project .pi/skills/embedding python .pi/skills/embedding/backfill_multimodal.py embed

# Single collection
uv run --project .pi/skills/embedding python .pi/skills/embedding/backfill_multimodal.py embed -c sparta_qra

# Verify service + dimensions
uv run --project .pi/skills/embedding python .pi/skills/embedding/backfill_multimodal.py verify
```

## Configuration

| Variable                        | Default                     | Description                          |
| ------------------------------- | --------------------------- | ------------------------------------ |
| `EMBEDDING_MODEL`               | `all-MiniLM-L6-v2`         | Text backend model                   |
| `EMBEDDING_DEVICE`              | `auto`                      | Text backend device                  |
| `EMBEDDING_PORT`                | `8602`                      | Text backend port                    |
| `EMBEDDING_SERVICE_URL`         | `http://127.0.0.1:8602`    | Text backend URL                     |
| `EMBEDDING_MULTIMODAL_URL`      | `http://127.0.0.1:8603`    | Multimodal backend URL (vLLM)      |
| `EMBEDDING_MULTIMODAL_DIMENSIONS` | `2048`                    | Multimodal vector dimensions         |
| `EMBEDDING_CONTAINER`           | `memory-embedding`          | Text backend container name          |
| `EMBEDDING_CONTAINER_MM`        | `embry-embedding-mm`        | Multimodal backend container name    |

## Backends

### Text (MiniLM, :8602) — Production

- Model: `all-MiniLM-L6-v2` (sentence-transformers)
- Dimensions: 384
- Field: `embedding`
- Container: `embry-embedding` (existing, custom image)
- CPU or GPU, ~200MB VRAM

### Multimodal (Qwen3-VL, :8603) — New

- Model: `Qwen/Qwen3-VL-Embedding-2B`
- Dimensions: 2048 (MRL: supports 64-2048 at inference time)
- Field: `embedding_visual`
- Container: `embry-embedding-mm` (vLLM image)
- GPU required, ~5-8GB VRAM (bf16)
- OpenAI-compatible API: `/v1/embeddings`
- Supports: text, image, video, mixed modalities

### Finetunes (Ollama, :8604) — Future

- Stubbed in docker-compose.yml
- For domain-specific GGUF finetunes when available

## API Endpoints

### Text Backend (:8602)

```
POST /embed          {"text": "query"}  → {"embedding": [...], "dimensions": 384}
POST /embed/batch    {"texts": [...]}   → {"vectors": [[...]], "count": N}
GET  /info           → model, device, dimensions, status
GET  /health         → {"status": "ok"}
```

### Multimodal Backend (:8603, vLLM)

Text (single pooled vector):
```
POST /v1/embeddings  {"model": "Qwen/Qwen3-VL-Embedding-2B", "input": ["query"]}
                     → {"data": [{"embedding": [...], "index": 0}]}
```

Image (per-token vectors, client mean-pools):
```
POST /pooling  {"model": "...", "messages": [{"role": "user", "content": [
                 {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
               ]}]}
               → {"data": [{"data": [[...], [...], ...]}]}  # mean-pool client-side
```

```
GET  /health   → health status
```

## ArangoDB Embedding Contract

### Document Structure

Every embeddable document has up to two vector fields on the **same document**:

```json
{
  "_key": "abc123",
  "text": "...",
  "embedding": [0.01, -0.03, ...],           // 384d, MiniLM text
  "embedding_visual": [0.005, -0.002, ...]    // 2048d, Qwen3-VL multimodal
}
```

### Writing Embeddings

Use `/upsert` via the daemon socket. **Omit the field entirely** if you don't have the embedding — never set it to `null`.

```python
transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
client = httpx.Client(transport=transport, base_url="http://localhost")

# Text embedding only (384d)
client.post("/upsert", json={"collection": "lessons", "documents": [
    {"_key": "abc123", "embedding": [0.01, -0.03, ...]}  # 384 floats
]})

# Visual embedding only (2048d)
client.post("/upsert", json={"collection": "datalake_chunks", "documents": [
    {"_key": "abc123", "embedding_visual": [0.005, ...]}  # 2048 floats
]})
```

### Finding Docs Missing Embeddings

```python
# Docs missing visual embedding
resp = client.post("/list", json={
    "collection": "datalake_chunks", "limit": 100,
    "filters": {"embedding_visual": None}
})
```

### Vector Index Status

| Collection | Field | Dim | Index | Sparse |
|---|---|---|---|---|
| `datalake_chunks` | `embedding` | 384 | `datalake_chunks_vec_text` | Yes |
| `datalake_chunks` | `embedding_visual` | 2048 | `datalake_chunks_vec_visual` | Yes |
| `lessons` | `embedding` | 384 | `lessons_vec_text` | No |
| `sparta_qra` | `embedding` | 384 | `sparta_qra_vec_text` | No |

### Rules

1. **Never set embedding fields to `null`** — omit the field entirely. Explicit null blocks vector index operations.
2. **Always `DESC`** in `SORT APPROX_NEAR_COSINE(...)` — without it, ArangoDB error 1554.
3. **Dimension must match exactly** — 384 for `embedding`, 2048 for `embedding_visual`. Wrong dimensions corrupt the index.
4. **Use `/upsert`** not `/learn` for embedding-only updates — `/learn` is for full documents with text content.
5. **Verify with sanity check**: `uv run python -m graph_memory.maintenance.sanity_recall integrity`

## Common Mistakes

```python
# WRONG: No timeout on embedding calls
requests.post("http://127.0.0.1:8602/embed", json={"text": query})
# → Service down = 120s hang. Agent blocks entire pipeline.
# RIGHT: httpx with connect timeout <2s
resp = httpx.post("http://127.0.0.1:8602/embed", json={"text": query},
                  timeout=httpx.Timeout(10.0, connect=2.0))

# WRONG: Using port 8602 for multimodal
# RIGHT: Multimodal is ALWAYS port 8603

# WRONG: Setting embedding_visual to null or []
# RIGHT: Omit the field entirely for docs without images

# WRONG: Writing to "embedding" field from multimodal service
# RIGHT: Image vectors go in "embedding_visual" (2048d) ONLY

# WRONG: SORT APPROX_NEAR_COSINE(...) ASC
# RIGHT: SORT APPROX_NEAR_COSINE(...) DESC — always descending
```
