"""Memory bridge for SFX catalog — routes all DB access through /memory."""

import os
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional
import httpx


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
        elif subcmd == "count":
            coll = params.get("collection", params.get("scope", "lessons"))
            # Use /list endpoint instead of raw AQL (all AQL must be in memory project)
            list_resp = client.post("/list", json={"collection": coll, "limit": 1})
            list_resp.raise_for_status()
            return {"documents": [list_resp.json().get("total", 0)]}
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

class SFXMemoryBridge:
    """Bridge between SFX catalog and /memory system."""

    def __init__(self):
        """Initialize memory bridge — checks /memory availability."""
        self.available = False
        try:
            _memory_cmd(["count", "--collection", "lessons"])
            self.available = True
        except Exception as e:
            print(f"[WARN] /memory unavailable: {e}", file=sys.stderr)

    def test_connection(self) -> bool:
        """Test if /memory is available."""
        return self.available

    def ingest_catalog(self, manifest: dict) -> bool:
        """Ingest catalog manifest via /memory learn."""
        if not self.available:
            print("[WARN] /memory unavailable, skipping ingest", file=sys.stderr)
            return False

        try:
            items = manifest.get("items", [])
            for item in items:
                desc = item.get("description", "")
                name = item.get("name", item.get("_key", "sfx"))

                _memory_cmd([
                    "learn",
                    "--problem", f"SFX: {name} — {desc}",
                    "--solution", json.dumps(item),
                    "--scope", "sfx_library",
                    "--tag", "sfx",
                ])
            return True
        except Exception as e:
            print(f"[ERROR] Ingest failed: {e}", file=sys.stderr)
            return False

    def search_sfx(
        self,
        query: str,
        categories: Optional[list[str]] = None,
        duration_range: Optional[tuple[float, float]] = None,
        k: int = 5,
    ) -> list[dict]:
        """Search SFX catalog via /memory recall."""
        if not self.available:
            return []

        try:
            data = _memory_cmd([
                "recall", "--q", query,
                "--scope", "sfx_library",
                "--k", str(k * 3),
            ])
            items = data.get("items", [])

            results = []
            for item in items:
                doc = item
                sol = item.get("solution", "")
                if isinstance(sol, str) and sol.startswith("{"):
                    try:
                        doc = json.loads(sol)
                    except json.JSONDecodeError:
                        pass

                if categories:
                    item_cats = doc.get("categories", [])
                    if not any(c in item_cats for c in categories):
                        continue

                if duration_range:
                    dur = doc.get("duration", 0)
                    if dur < duration_range[0] or dur > duration_range[1]:
                        continue

                results.append(doc)
                if len(results) >= k:
                    break

            return results
        except Exception as e:
            print(f"[ERROR] Search failed: {e}", file=sys.stderr)
            return []
