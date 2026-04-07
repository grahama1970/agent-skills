"""Shared memory, embedding, and LLM helper utilities for episodic archiver.

Provides httpx-based access to memory daemon (Unix socket), embedding service,
scillm LLM proxy, content extraction from Claude Code JSONL, and dedup.

Codex 5.3 review fixes (2026-03-30):
- Reusable httpx client (no per-call creation)
- Full doc storage via /learn (not lossy truncation)
- Silent failure → structured error metrics
- Retry with backoff for transient HTTP errors
"""

import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger

# ── TaskClient integration ──────────────────────────────────────────────────
try:
    sys.path.insert(0, str(Path.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

PROJECT_ROOT = Path(__file__).resolve().parents[3]
LOG_PATH = PROJECT_ROOT / "logs" / "episodic-archiver.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logger.add(LOG_PATH, rotation="10 MB", retention="7 days")

MEMORY_SOCK = "/run/user/1000/embry/memory.sock"
EMBEDDING_URL = os.getenv("EMBEDDING_SERVICE_URL", "http://127.0.0.1:8602")
SCILLM_URL = os.getenv("SCILLM_URL", "http://localhost:4001")
LOCKFILE = Path("/tmp/episodic-archiver.lock")

# ── Error tracking ──────────────────────────────────────────────────────────

_error_counts: Dict[str, int] = {}
# Fail job if any error type exceeds its threshold
_ERROR_THRESHOLDS = {
    "learn_422": 5000,      # Taxonomy rejection — expected for short turns, not a bug
    "llm_categorize": 100,  # LLM failures — scillm may be down
}
ERROR_THRESHOLD = 50  # default for unlisted categories


def track_error(category: str, detail: str = ""):
    """Track errors by category. Raises if threshold exceeded."""
    _error_counts[category] = _error_counts.get(category, 0) + 1
    count = _error_counts[category]
    if count <= 3 or count % 10 == 0:
        logger.warning(f"[{category}] ({count}x): {detail[:200]}")
    threshold = _ERROR_THRESHOLDS.get(category, ERROR_THRESHOLD)
    if count >= threshold:
        raise RuntimeError(
            f"Error threshold exceeded: {category} hit {count}x. "
            f"Failing job to prevent silent data loss. Last: {detail[:200]}"
        )


def error_summary() -> Dict[str, int]:
    """Return accumulated error counts for reporting."""
    return dict(_error_counts)


# ── Cron lock ───────────────────────────────────────────────────────────────

def acquire_lock() -> Optional[int]:
    """Acquire exclusive lock for cron. Returns fd or None if already locked."""
    try:
        fd = os.open(str(LOCKFILE), os.O_CREAT | os.O_WRONLY)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        os.write(fd, str(os.getpid()).encode())
        return fd
    except (OSError, BlockingIOError):
        logger.error("Another episodic-archiver instance is running. Exiting.")
        return None


def release_lock(fd: int):
    """Release cron lock."""
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
        LOCKFILE.unlink(missing_ok=True)
    except OSError:
        pass


# ── Reusable httpx client ──────────────────────────────────────────────────

def _make_memory_client(timeout: float = 30.0) -> httpx.Client:
    """Create httpx client for memory daemon."""
    transport = httpx.HTTPTransport(uds=MEMORY_SOCK)
    return httpx.Client(transport=transport, base_url="http://localhost", timeout=timeout)


def _retry_request(client: httpx.Client, method: str, url: str, **kwargs) -> httpx.Response:
    """HTTP request with retry for transient errors (429, 503, timeouts)."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            resp = getattr(client, method)(url, **kwargs)
            if resp.status_code in (429, 503) and attempt < max_retries - 1:
                wait = (attempt + 1) * 2
                logger.debug(f"Retrying {url} after {resp.status_code} (wait {wait}s)")
                time.sleep(wait)
                continue
            return resp
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            if attempt < max_retries - 1:
                wait = (attempt + 1) * 2
                logger.debug(f"Retrying {url} after {type(e).__name__} (wait {wait}s)")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Unreachable")


# ── Health checks ───────────────────────────────────────────────────────────

def check_services() -> Dict[str, bool]:
    """Pre-flight health check for all required services."""
    results = {}
    # Memory daemon
    try:
        with _make_memory_client(timeout=5.0) as c:
            r = c.get("/health")
            results["memory"] = r.status_code == 200
    except Exception:
        results["memory"] = False

    # Embedding service
    try:
        r = httpx.get(f"{EMBEDDING_URL}/health", timeout=5.0)
        results["embedding"] = r.status_code == 200
    except Exception:
        results["embedding"] = False

    return results


# ── Memory operations ───────────────────────────────────────────────────────

def store_turn(doc: Dict[str, Any], client: httpx.Client = None) -> Dict[str, Any]:
    """Store a full conversation turn document to memory.

    Stores the FULL document (body, embedding, taxonomy, dedupe_key, timestamps)
    via /learn. No truncation. Returns the stored document reference.
    """
    body = (doc.get("body") or "").strip()
    if not body:
        return {"_id": "empty", "skipped": True}

    session_id = doc.get("session_id", "unknown")
    category = doc.get("category", "info")
    dedupe = doc.get("dedupe_key", "")

    # Build the full solution payload — no lossy truncation
    solution_data = {
        "body": body,
        "session_id": session_id,
        "category": category,
        "user_id": doc.get("user_id"),
        "persona_id": doc.get("persona_id"),
        "id_from": doc.get("id_from"),
        "timestamp": doc.get("timestamp"),
        "taxonomy": doc.get("taxonomy", {}),
        "dedupe_key": dedupe,
    }

    # Store embedding separately if present (too large for /learn solution field)
    embedding = doc.get("embedding")

    payload = {
        "problem": f"[{category}] session:{session_id} dedupe:{dedupe[:12]}",
        "solution": json.dumps(solution_data),
        "scope": "agent_conversations",
        "tags": [f"session:{session_id}", f"category:{category}"],
    }

    own_client = client is None
    if own_client:
        client = _make_memory_client()
    try:
        resp = _retry_request(client, "post", "/learn", json=payload)
        if resp.status_code == 422:
            # Taxonomy extraction failed — store without taxonomy requirement
            track_error("learn_422", f"session:{session_id} category:{category}")
            return {"_id": f"{session_id}/{dedupe[:12]}", "skipped_taxonomy": True}
        if resp.status_code >= 400:
            track_error("learn_http", f"HTTP {resp.status_code}: {resp.text[:200]}")
            return {"_id": f"{session_id}/error", "error": resp.status_code}
        return resp.json()
    except Exception as e:
        track_error("learn_exception", str(e))
        return {"_id": f"{session_id}/error", "error": str(e)}
    finally:
        if own_client:
            client.close()


def store_perspectives(session_id: str, perspectives: List[Dict], client: httpx.Client = None):
    """Store multi-POV perspectives via /learn (not broken --data flag)."""
    own_client = client is None
    if own_client:
        client = _make_memory_client()
    try:
        resp = _retry_request(client, "post", "/learn", json={
            "problem": f"Multi-POV perspectives for session:{session_id}",
            "solution": json.dumps({"session_id": session_id, "perspectives": perspectives}),
            "scope": "session_summaries",
            "tags": [f"session:{session_id}", "multi-pov"],
        })
        if resp.status_code < 400:
            logger.info(f"Stored {len(perspectives)} perspectives for session {session_id}")
        else:
            track_error("perspectives_store", f"HTTP {resp.status_code}")
    except Exception as e:
        track_error("perspectives_store", str(e))
    finally:
        if own_client:
            client.close()


def _memory_recall(
    query: str, scope: str = "episodes", k: int = 5, collections: str = ""
) -> List[Dict[str, Any]]:
    """Call /memory recall via embry-memory Unix socket."""
    try:
        with _make_memory_client() as client:
            body: dict = {"q": query, "scope": scope, "k": k}
            if collections:
                body["collections"] = [c.strip() for c in collections.split(",")]
            resp = _retry_request(client, "post", "/recall", json=body)
            if resp.status_code != 200:
                return []
            return resp.json().get("items", [])
    except Exception as exc:
        logger.warning(f"/memory recall error: {exc}")
        return []


def _memory_cmd(args: list, timeout: int = 60) -> dict:
    """Call embry-memory daemon via Unix socket HTTP API.

    Legacy CLI-style interface preserved for backward compatibility.
    New code should use store_turn() and store_perspectives() directly.
    """
    str_args = [str(a) for a in args]
    subcmd = str_args[0] if str_args else ""
    rest = str_args[1:]

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

    with _make_memory_client(timeout=float(timeout)) as client:
        if subcmd == "recall":
            body = {"q": params.get("q", params.get("query", "")), "k": int(params.get("k", params.get("limit", 5)))}
            for opt in ("scope", "threshold"):
                if opt in params:
                    body[opt] = float(params[opt]) if opt == "threshold" else params[opt]
            if "collections" in params:
                c = params["collections"]
                body["collections"] = c if isinstance(c, list) else [c]
            resp = _retry_request(client, "post", "/recall", json=body)
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
            resp = _retry_request(client, "post", "/learn", json=body)
        elif subcmd == "count":
            coll = params.get("collection", params.get("scope", "lessons"))
            resp = _retry_request(client, "post", "/query", json={"aql": f"RETURN LENGTH({coll})", "bind_vars": {}})
        elif subcmd == "sample":
            body = {"collection": params.get("collection", "lessons"), "limit": int(params.get("limit", 10))}
            if "fields" in params:
                body["return_fields"] = [f.strip() for f in str(params["fields"]).split(",")]
            resp = _retry_request(client, "post", "/list", json=body)
        elif subcmd == "search":
            body = {"q": params.get("q", params.get("query", "")), "k": int(params.get("limit", 10))}
            if "collection" in params:
                body["collections"] = [params["collection"]]
            resp = _retry_request(client, "post", "/recall", json=body)
        elif subcmd == "archive-session":
            payload = params.get("json", "{}")
            doc_data = json.loads(payload) if isinstance(payload, str) else payload
            doc = doc_data.get("doc", doc_data)
            return store_turn(doc, client)
        elif subcmd == "add-edge":
            body = {}
            if "json" in params:
                body = json.loads(params["json"]) if isinstance(params["json"], str) else params["json"]
            resp = _retry_request(client, "post", "/add-edge", json=body)
        else:
            raise RuntimeError(f"Unsupported memory subcommand: {subcmd}")
        if resp.status_code == 422:
            return {"skipped": True, "status": 422}
        resp.raise_for_status()
        return resp.json()


# ── Embedding ───────────────────────────────────────────────────────────────

def get_embedding(text: str) -> list:
    """Get embedding from service. No local fallback (avoid OOM on nightly)."""
    try:
        resp = httpx.post(
            f"{EMBEDDING_URL}/embed",
            json={"text": text[:8000]},  # Cap input to avoid token overflow
            timeout=10,
        )
        if resp.status_code == 200:
            body = resp.json()
            return body.get("vector") or body.get("embedding", [])
    except Exception as e:
        track_error("embedding", str(e))
    return []  # Empty embedding — still store the turn, just without vectors


# ── LLM categorization ─────────────────────────────────────────────────────

# Ordered list for deterministic matching (not set iteration)
VALID_CATEGORIES = ["task", "question", "solution", "error", "chat", "meta"]


_SCILLM_AUTH = os.getenv("LITELLM_MASTER_KEY", "sk-dev-proxy-123")


def call_llm_simple(prompt: str) -> str:
    """Categorize a turn using scillm proxy via httpx (not import)."""
    try:
        resp = httpx.post(
            f"{SCILLM_URL}/v1/chat/completions",
            headers={"Authorization": f"Bearer {_SCILLM_AUTH}"},
            json={
                "model": "text",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 64,
                "temperature": 0.0,
            },
            timeout=15.0,
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
        track_error("llm_categorize", f"HTTP {resp.status_code}")
        return "info"
    except Exception as e:
        track_error("llm_categorize", str(e))
        return "info"


# ── Edge verification ───────────────────────────────────────────────────────

def trigger_edge_verification(source_id: str, content: str):
    """Invoke the external edge-verifier skill."""
    if not source_id or source_id.endswith("/error"):
        return  # Don't verify phantom IDs
    script_path = os.path.join(os.path.dirname(__file__), "../edge-verifier/run.sh")
    if not os.path.exists(script_path):
        return
    try:
        subprocess.run(
            [script_path, "--source-id", source_id, "--text", content[:500]],
            check=False,
            timeout=30,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
    except Exception as e:
        logger.debug(f"Edge verifier failed: {e}")


# ── Content extraction ──────────────────────────────────────────────────────

def msg_content(msg: Dict[str, Any]) -> str:
    """Extract text content from a Claude Code JSONL message line.

    Handles both legacy format (msg["content"] as str) and Claude Code
    format (msg["message"]["content"] as list of typed blocks).
    """
    raw_msg = msg.get("message") or {}
    if isinstance(raw_msg, dict):
        raw = raw_msg.get("content") or msg.get("content")
    else:
        raw = msg.get("content") or raw_msg
    return extract_text(raw).strip()


def msg_role(msg: Dict[str, Any]) -> str:
    """Extract the role/sender from a message."""
    role = msg.get("from") or ""
    if not role:
        raw_msg = msg.get("message")
        if isinstance(raw_msg, dict):
            role = raw_msg.get("role", "")
    return role.lower()


def extract_text(value: Any) -> str:
    """Extract plain text from various message content formats."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                parts.append(item.get("text", ""))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    if isinstance(value, dict):
        return value.get("text", value.get("content", ""))
    return ""


# ── Deduplication ───────────────────────────────────────────────────────────

_msg_sequence = 0


def dedupe_key(session_id: str, msg: Dict[str, Any]) -> str:
    """Generate a SHA-1 dedup key. Includes sequence counter for identical msgs."""
    global _msg_sequence
    _msg_sequence += 1
    body = msg_content(msg)[:500]
    stamp = msg.get("timestamp") or ""
    sender = msg_role(msg)
    key = f"{session_id}|{stamp}|{sender}|{_msg_sequence}|{body}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


# ── File locking for JSONL appends ──────────────────────────────────────────

def locked_append(path: Path, lines: List[str]):
    """Append lines to a JSONL file with exclusive locking."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            for line in lines:
                f.write(line + "\n")
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
