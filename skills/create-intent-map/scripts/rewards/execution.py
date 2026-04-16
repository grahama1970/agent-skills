"""Query execution for reward computation.

Converts QuerySpec JSON to /memory subprocess calls.
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Optional

from loguru import logger

SKILLS_DIR = Path(__file__).resolve().parents[3]
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

class QuerySpec:
    """Parsed QuerySpec from model output."""

    def __init__(self, data: dict):
        self.action = data.get("action", "QUERY")
        self.scope = data.get("scope", "sparta")
        self.entities = data.get("entities", [])
        self.tier0 = data.get("tier0", [])
        self.tier1 = data.get("tier1", [])
        self.keywords = data.get("keywords", [])
        self.lanes = data.get("lanes", ["bm25", "dense"])
        self.k = data.get("k", 12)
        self.min_grounding = data.get("min_grounding", 0.7)

    @classmethod
    def from_json(cls, text: str) -> Optional["QuerySpec"]:
        """Parse QuerySpec from JSON string."""
        try:
            # Try direct parse
            data = json.loads(text)
            return cls(data)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end > start:
                try:
                    data = json.loads(text[start:end].strip())
                    return cls(data)
                except json.JSONDecodeError:
                    pass

        # Try extracting any JSON object
        import re
        match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                return cls(data)
            except json.JSONDecodeError:
                pass

        return None


class MemoryExecutor:
    """Execute QuerySpecs via /memory subprocess recall."""

    def __init__(self):
        self._fail_count = 0
        self._fail_limit = 3

    def execute(self, spec: QuerySpec) -> list[dict]:
        """Execute QuerySpec via /memory recall and return results."""
        if spec.action == "NO_MATCH":
            return []

        if spec.action == "CLARIFY":
            return []

        # Build search query from entities + keywords
        query_parts = []
        if spec.entities:
            query_parts.extend(spec.entities)
        if spec.keywords:
            query_parts.extend(spec.keywords)
        if spec.tier1:
            query_parts.extend(spec.tier1)

        query = " ".join(query_parts) if query_parts else "sparta"

        try:
            result = _memory_cmd([
                "recall", "--q", query,
                "--scope", "brandon_bailey",
                "--k", str(spec.k),
            ])
            items = result.get("items", result.get("results", []))
            # Normalize field names for downstream compatibility
            for item in items:
                item.setdefault("qra_id", item.get("_key", ""))
                item.setdefault("grounding_score", item.get("_score", 0.7))
            return items
        except Exception as e:
            self._fail_count += 1
            logger.error(f"Memory recall failed (#{self._fail_count}): {e}")
            if self._fail_count >= self._fail_limit:
                raise RuntimeError("Memory execution circuit-breaker tripped") from e
            return []

    def execute_json(self, spec_json: str) -> list[dict]:
        """Execute from JSON string."""
        spec = QuerySpec.from_json(spec_json)
        if spec is None:
            return []
        return self.execute(spec)

    def close(self) -> None:
        """No-op — subprocess connections are stateless."""
        pass


class MockExecutor:
    """Mock executor for testing without ArangoDB."""

    def __init__(self):
        self.call_count = 0

    def execute(self, spec: QuerySpec) -> list[dict]:
        """Return mock results based on spec."""
        self.call_count += 1

        if spec.action == "NO_MATCH":
            return []

        if spec.action == "CLARIFY":
            return []

        # Generate mock results
        k = min(spec.k, 5)
        results = []
        for i in range(k):
            results.append({
                "qra_id": f"mock_{i}",
                "question": f"Mock question {i} about {spec.keywords[0] if spec.keywords else 'topic'}",
                "answer": f"Mock answer {i}",
                "entities": spec.entities[:2] if spec.entities else [],
                "grounding_score": 0.7 + (0.3 * (k - i) / k),  # Descending scores
            })
        return results

    def execute_json(self, spec_json: str) -> list[dict]:
        """Execute from JSON string."""
        spec = QuerySpec.from_json(spec_json)
        if spec is None:
            return []
        return self.execute(spec)

    def close(self) -> None:
        """No-op for mock executor."""
        pass


def get_executor(mock: bool = False) -> MemoryExecutor | MockExecutor:
    """Get appropriate executor based on environment."""
    if mock:
        return MockExecutor()

    # Check if /memory is reachable
    try:
        _memory_cmd(["count", "--scope", "brandon_bailey"])
        return MemoryExecutor()
    except Exception as e:
        logger.warning(f"Memory not available ({e}), using mock executor")
        return MockExecutor()
