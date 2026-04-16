"""feed_storage - consume-feed.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

import os
import json
import subprocess
import time
from typing import Dict, Any, List, Optional
from pathlib import Path
from rich.console import Console
import httpx

console = Console()

# Removed: memory accessed via httpx to Unix socket (see _memory_cmd)
def _memory_cmd(args: list, timeout: int = 60) -> dict:
    """Call embry-memory daemon via Unix socket HTTP API."""
    str_args = [str(a) for a in args]
    subcmd = str_args[0] if str_args else ""
    rest = str_args[1:]

    # Parse CLI-style flags into a dict
    params: dict = {}
    list_keys: dict[str, list] = {}
    i = 0
    while i < len(rest):
        if rest[i].startswith("--"):
            key = rest[i][2:].replace("-", "_")
            if i + 1 < len(rest) and not rest[i + 1].startswith("--"):
                val = rest[i + 1]
                if key in ("tag", "tags", "collections"):
                    list_keys.setdefault(key, []).append(val)
                else:
                    params[key] = val
                i += 2
            else:
                params[key] = True
                i += 1
        else:
            i += 1
    for k, v in list_keys.items():
        params[k] = v

    transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
    with httpx.Client(transport=transport, base_url="http://localhost", timeout=float(timeout)) as client:
        if subcmd == "recall":
            body = {"q": params.get("q", params.get("query", "")), "k": int(params.get("k", params.get("limit", 5)))}
            for opt in ("scope", "threshold"):
                if opt in params:
                    body[opt] = float(params[opt]) if opt == "threshold" else params[opt]
            if "collections" in params:
                c = params["collections"]
                body["collections"] = c if isinstance(c, list) else [c]
            if "tags" in params:
                t = params["tags"]
                body["tags"] = t if isinstance(t, list) else [t]
            resp = client.post("/recall", json=body)
        elif subcmd == "learn":
            body = {"problem": params.get("problem", ""), "solution": params.get("solution", "")}
            if "scope" in params:
                body["scope"] = params["scope"]
            if "collection" in params:
                body["scope"] = params["collection"]
            if "tag" in params:
                body["tags"] = params["tag"] if isinstance(params["tag"], list) else [params["tag"]]
            if "tags" in params:
                body["tags"] = params["tags"] if isinstance(params["tags"], list) else [params["tags"]]
            if "json" in params:
                body.update(json.loads(params["json"]))
            resp = client.post("/learn", json=body)
            # 422 from /learn means taxonomy extraction failed — not fatal for feed items.
            if resp.status_code == 422:
                return {"ok": False, "status": 422, "detail": resp.text}
        elif subcmd == "count":
            coll = params.get("collection", params.get("scope", "lessons"))
            resp = client.post("/query", json={"aql": f"RETURN LENGTH({coll})", "bind_vars": {}})
        elif subcmd == "sample":
            body = {"collection": params.get("collection", "lessons"), "limit": int(params.get("limit", 10))}
            if "fields" in params:
                body["return_fields"] = [f.strip() for f in str(params["fields"]).split(",")]
            resp = client.post("/list", json=body)
        elif subcmd == "tag":
            if "doc" in params:
                doc = json.loads(params["doc"]) if isinstance(params["doc"], str) else params["doc"]
                resp = client.post("/upsert", json={"collection": params.get("collection", "lessons"), "documents": [doc]})
            elif "key" in params:
                tags_val = params.get("tags", "[]")
                tags_list = json.loads(tags_val) if isinstance(tags_val, str) else tags_val
                field = params.get("field", "tags")
                resp = client.post("/upsert", json={"collection": params.get("collection", "lessons"), "documents": [{"_key": params["key"], field: tags_list}]})
            else:
                raise RuntimeError(f"Unsupported tag args: {rest}")
        elif subcmd == "search":
            body = {"q": params.get("q", params.get("query", "")), "k": int(params.get("limit", 10))}
            if "collection" in params:
                body["collections"] = [params["collection"]]
            if "scope" in params:
                body["scope"] = params["scope"]
            resp = client.post("/recall", json=body)
        else:
            raise RuntimeError(f"Unsupported memory subcommand via httpx: {subcmd}")
        resp.raise_for_status()
        return resp.json()

class FeedStorage:
    def __init__(self, url: str = None, db_name: str = "memory", auth: dict = None):
        """Initialize — verify /memory is available."""
        try:
            _memory_cmd(["count", "--collection", "lessons"])
            self.available = True
        except Exception as e:
            console.print(f"[red]Failed to connect to /memory: {e}[/red]")
            raise

    def ensure_schema(self, force: bool = False):
        """Schema management delegated to /ops-arango. No-op here."""
        pass

    def upsert_items(self, items: List[Dict[str, Any]]) -> int:
        if not items:
            return 0
        count = 0
        for item in items:
            try:
                title = item.get("title", "feed item")
                summary = item.get("summary", item.get("description", ""))
                link = item.get("link", item.get("url", ""))
                source = item.get("source", item.get("feed_name", ""))
                # Problem field must have enough content for taxonomy extraction.
                # Short titles get 422'd by /memory — include all available context.
                parts = [p for p in [title, summary, source, link] if p]
                problem = ". ".join(parts)
                if len(problem) < 30:
                    # Still too short — skip rather than crash the whole run
                    continue
                _memory_cmd([
                    "learn",
                    "--problem", problem,
                    "--solution", json.dumps(item),
                    "--scope", "feed_items",
                    "--tag", "feed",
                ])
                count += 1
            except Exception:
                pass  # Skip items that fail taxonomy extraction (422) or any other error
        return count

    def get_state(self, source_key: str) -> Dict[str, Any]:
        try:
            data = _memory_cmd(["sample", "--collection", "feed_state",
                                "--limit", "1", "--filter", f"doc._key == '{source_key}'"])
            items = data.get("items", [])
            return items[0] if items else {"_key": source_key}
        except RuntimeError:
            return {"_key": source_key}

    def save_state(self, source_key: str, state: Dict[str, Any]):
        state["_key"] = source_key
        state["updated_at"] = time.time()
        _memory_cmd([
            "learn",
            "--problem", f"Feed state: {source_key}",
            "--solution", json.dumps(state),
            "--scope", "feed_state",
            "--tag", "feed_state",
        ])

    def log_deadletter(self, doc: Dict[str, Any]):
        doc["logged_at"] = time.time()
        _memory_cmd([
            "learn",
            "--problem", f"Feed deadletter: {doc.get('source_key', 'unknown')}",
            "--solution", json.dumps(doc),
            "--scope", "feed_deadletters",
            "--tag", "deadletter",
        ])

    def log_run(self, run_stats: Dict[str, Any]):
        run_stats["logged_at"] = time.time()
        _memory_cmd([
            "learn",
            "--problem", f"Feed run: {run_stats.get('source_key', 'unknown')}",
            "--solution", json.dumps(run_stats),
            "--scope", "feed_runs",
            "--tag", "feed_run",
        ])
