# Consume Feed Skill Walkthrough

Robust, resilient ingestion for upstream feeds (RSS).  
GitHub and NVD are planned for Phase 2.

## 1. Installation & Structure

The skill is located at `.pi/skills/consume-feed`.

```bash
.pi/skills/consume-feed/
├── run.sh                  # Wrapper (PYTHONPATH + uv run)
├── SKILL.md                # Triggers & Usage
├── pyproject.toml          # Deps: httpx, tenacity, feedparser, python-arango
├── cli.py                  # CLI Entrypoint
├── feed_config.py          # Pydantic Configuration
├── feed_runner.py          # Orchestration & Concurrency
├── feed_storage.py         # ArangoDB Schema & Memory Reuse
├── sources/
│   ├── base.py             # Abstract Base Source
│   └── rss.py              # Robust RSS Source
├── util/
│   ├── http.py             # HTTP Client with Backoff/Jitter
│   ├── dedupe.py           # Stable Key Generation
│   └── text.py             # Summary cleanup utilities
└── sanity/
    ├── mock_server.py      # Deterministic Test Server
    ├── test_arango_conn.py # DB & View Verification
    ├── test_retry_logic.py # Resilience Verification
    └── test_live_rss.py    # Live Network Verification
```

## 2. Capabilities Implemented

### Memory Integration (No Bespoke Wrappers)

- **Reusable Connection**: `feed_storage.py` imports `get_db()` from `.pi/skills/memory/db.py` to use the canonical memory database connection.
- **Schema**: Maps to `feed_items` collection within the `memory` database.
- **View**: Automatically creates `feed_items_view` for Memory skill recall compatibility.

### Resilience

- **HTTP**: `httpx` client wrapped in `tenacity`.
- **Retries**: Exponential backoff (2-60s) + jitter for Network Errors and 5xx.
- **Deduplication**: Stable hash keys for all items.

### Efficiency

- **Conditional GET**: RSS source respects `ETag` and `Last-Modified`.
- **Concurrency**: `feed_runner.py` uses `ThreadPoolExecutor` for parallel fetching.

## 3. Verification

### Connectivity Check

`./run.sh doctor` and `sanity/test_arango_conn.py` verify connection to the shared memory DB.

```text
Testing ArangoDB Connection...
# Uses memory/db.py logic
✅ Connected to 'memory'
✅ Collection 'feed_items' exists
✅ View 'feed_items_view' exists
```

### Live Feed Check

`sanity/test_live_rss.py` performs a real network request (dry-run) to the GitHub Blog to verify end-to-end XML parsing and network stack integrity.

```text
Testing Live RSS Ingestion (GitHub Blog)...
Fetching https://github.blog/feed/...
Dry run: would upsert 3 items
✅ Successfully parsed 3 items from live feed!
```

### Resilience Check

`sanity/test_retry_logic.py` proves 500 recovery.

```text
Attempting to fetch http://localhost:9999...
127.0.0.1 - "GET / HTTP/1.1" 500 -
127.0.0.1 - "GET / HTTP/1.1" 500 -
127.0.0.1 - "GET / HTTP/1.1" 200 -
✅ Retry logic worked!
```

## 4. Next Steps

1. **GitHub/NVD Sources**: Implement `sources/github_*.py` and `sources/nvd.py`.
2. **Memory Config**: Update `.env` in `experiments/memory` or `RECALL_SOURCES_JSON` to include `feed_items_view` as a supplemental source.
