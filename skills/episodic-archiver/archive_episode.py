#!/usr/bin/env python3
import atexit
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import requests
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[3]
LOG_PATH = PROJECT_ROOT / "logs" / "episodic-archiver.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_PATH.open("a", encoding="utf-8")
atexit.register(LOG_FILE.close)


def log(message: str) -> None:
    stamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {message}"
    print(line)
    LOG_FILE.write(line + "\n")
    LOG_FILE.flush()


from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(usecwd=True))

# 1. Setup Paths for graph_memory (fallback only)
def get_embedding(text: str) -> list:
    """Get embedding from service, fallback to graph_memory."""
    service_url = os.getenv("EMBEDDING_SERVICE_URL", "http://127.0.0.1:8602")
    
    # Try embedding service first
    try:
        resp = requests.post(
            f"{service_url}/embed",
            json={"text": text},
            timeout=10
        )
        if resp.status_code == 200:
            return resp.json()["vector"]
    except Exception as e:
        log(f"[embedding] Service unavailable ({e}), falling back to local...")
    
    # Fallback to local graph_memory import (handled by uv)
    from graph_memory.embeddings import encode_texts
    return encode_texts([text])[0]


def get_db():
    """Get ArangoDB connection."""
    from graph_memory.arango_client import get_db as _get_db
    return _get_db()

def call_llm_simple(prompt: str) -> str:
    """Categorize a turn using Chutes (SciLLM) only."""
    api_key = os.getenv("CHUTES_API_KEY")
    model = os.getenv("CHUTES_TEXT_MODEL", "sonar-medium")
    base_url = os.getenv("CHUTES_API_BASE", "https://chutes.graham.ai/v1")

    if not api_key:
        return "info"

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
    }

    try:
        resp = requests.post(
            f"{base_url}/chat/completions", json=payload, headers=headers, timeout=15
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return "info"

def trigger_edge_verification(source_id: str, content: str):
    """Invoke the external edge-verifier skill."""
    script_path = os.path.join(os.path.dirname(__file__), "../edge-verifier/run.sh")
    if not os.path.exists(script_path):
        log(f"[-] Warning: edge-verifier skill not found at {script_path}")
        return

    log(f"Triggering edge verification for {source_id}...")
    try:
        # Run in background or wait? 
        # For simplicity in this script, we'll wait, but in production this might be async.
        subprocess.run(
            [script_path, "--source_id", source_id, "--text", content],
            check=False  # Don't crash ifverifier fails
        )
    except Exception as e:
        log(f"[-] Failed to run edge verifier: {e}")

def _dedupe_key(session_id: str, msg: Dict[str, Any]) -> str:
    body = msg.get("message") or msg.get("content") or ""
    stamp = msg.get("timestamp") or ""
    sender = msg.get("from") or ""
    key = f"{session_id}|{stamp}|{sender}|{body}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def analyze_session_resolution(messages: List[Dict], categories: List[str]) -> Dict[str, Any]:
    """Analyze if a session was resolved or has unfinished business.

    Returns:
        {
            "resolved": bool,
            "reason": str,
            "unresolved_items": [{"type": str, "content": str}],
            "confidence": float
        }
    """
    unresolved_items = []

    # Track what happened in the session
    has_error = "error" in categories
    has_solution = "solution" in categories
    has_task = "task" in categories
    ends_with_question = categories[-1] == "question" if categories else False
    ends_with_error = categories[-1] == "error" if categories else False

    # Find specific unresolved items
    for i, (msg, cat) in enumerate(zip(messages, categories)):
        content = (msg.get("message") or msg.get("content") or "")[:300]

        # Error without following solution
        if cat == "error":
            has_following_solution = "solution" in categories[i+1:i+5] if i+1 < len(categories) else False
            if not has_following_solution:
                unresolved_items.append({
                    "type": "unresolved_error",
                    "content": content,
                })

        # Task without completion indicator
        if cat == "task":
            # Check if there's a solution or completion in next few turns
            has_completion = any(c in ["solution", "meta"] for c in categories[i+1:i+10]) if i+1 < len(categories) else False
            if not has_completion:
                unresolved_items.append({
                    "type": "incomplete_task",
                    "content": content,
                })

    # Determine overall resolution
    resolved = True
    reason = "Session appears complete"
    confidence = 0.8

    if ends_with_error:
        resolved = False
        reason = "Session ended with an error"
        confidence = 0.9
    elif ends_with_question:
        resolved = False
        reason = "Session ended with unanswered question"
        confidence = 0.7
    elif has_error and not has_solution:
        resolved = False
        reason = "Errors occurred without solutions"
        confidence = 0.8
    elif len(unresolved_items) > 2:
        resolved = False
        reason = f"Multiple unresolved items ({len(unresolved_items)})"
        confidence = 0.7

    return {
        "resolved": resolved,
        "reason": reason,
        "unresolved_items": unresolved_items[:10],  # Cap at 10
        "confidence": confidence,
    }


def store_unresolved_session(db, session_id: str, resolution: Dict[str, Any], messages: List[Dict]):
    """Store unresolved session for later reflection."""
    try:
        # Ensure collection exists
        if not db.has_collection("unresolved_sessions"):
            db.create_collection("unresolved_sessions")

        collection = db.collection("unresolved_sessions")
        ts = int(time.time())

        # Create summary of the session
        all_content = " ".join(
            (m.get("message") or m.get("content") or "")[:200]
            for m in messages[:20]
        )

        doc = {
            "_key": session_id.replace("/", "_").replace(" ", "_")[:64],
            "session_id": session_id,
            "resolution": resolution,
            "summary": all_content[:1000],
            "message_count": len(messages),
            "archived_at": ts,
            "status": "pending",  # pending, reviewed, resolved
            "embedding": get_embedding(all_content[:500]),
        }

        # Upsert
        try:
            collection.insert(doc)
            log(f"[+] Stored unresolved session: {session_id}")
        except Exception:
            collection.update(doc)
            log(f"[~] Updated unresolved session: {session_id}")

    except Exception as e:
        log(f"[-] Failed to store unresolved session: {e}")


def analyze_and_archive(transcript_path: str):
    with open(transcript_path, "r") as f:
        data = json.load(f)

    messages = data if isinstance(data, list) else data.get("messages", [])
    session_id = data.get("session_id", f"session_{int(time.time())}")

    db = get_db()
    collection = db.collection("agent_conversations")

    inserted = 0
    updated = 0
    skipped = 0
    errors = 0
    categories = []  # Track categories for resolution analysis

    print(f"Archiving {len(messages)} messages for session {session_id}...")

    for msg in tqdm(messages, desc="Archiving turns", unit="turn"):
        content = (msg.get("message") or msg.get("content") or "").strip()
        if not content:
            skipped += 1
            continue

        dedupe = _dedupe_key(session_id, msg)
        # 1. Embed via service (with fallback)
        embedding = get_embedding(content)

        # 2. Categorize (LLM)
        category = "info"
        if len(content) > 50:
            prompt = (
                "Categorize this agent message into one word "
                "(Task, Question, Solution, Error, Chat, Meta): "
                f"{content[:500]}"
            )
            category = call_llm_simple(prompt)
            print(f"DEBUG: Content='{content[:30]}...' -> Category='{category}'")
            # Sanitize: remove markdown bold/italics
            import re
            clean_cat = re.sub(r"[^a-zA-Z]", "", category).lower()
            category = clean_cat if clean_cat else "info"



        # 3. Store
        ts = int(time.time())
        doc = {
            "session_id": session_id,
            "body": content,
            "id_from": msg.get("from"),
            "id_to": msg.get("to") or [],
            "timestamp": msg.get("timestamp") or ts,
            "type": msg.get("type", "unknown"),
            "embedding": embedding,
            "category": category,
            "analyzed_at": ts,
            "dedupe_key": dedupe,
        }
        try:
            existing = list(
                db.aql.execute(
                    "FOR d IN agent_conversations FILTER d.dedupe_key==@k LIMIT 1 RETURN d",
                    bind_vars={"k": dedupe},
                )
            )
            if existing:
                doc_id = existing[0]["_id"]
                collection.update(
                    doc_id,
                    {
                        "body": content,
                        "id_to": doc["id_to"],
                        "embedding": embedding,
                        "category": category,
                        "updated_at": ts,
                    },
                )
                stored_id = doc_id
                updated += 1
            else:
                res = collection.insert(doc)
                stored_id = res["_id"]
                inserted += 1
        except Exception as exc:
            errors += 1
            log(f"[-] Failed to archive turn ({session_id}): {exc}")
            continue

        # 4. Track category for resolution analysis
        categories.append(category)

        # 5. Verify Edges (External Skill) where relevant
        if category in ["solution", "task"] and len(content) > 30:
            trigger_edge_verification(stored_id, content)

    log(
        f"Archive summary: inserted={inserted}, updated={updated}, skipped={skipped}, errors={errors}"
    )

    # 6. Analyze session resolution and store if unresolved
    if categories:
        resolution = analyze_session_resolution(messages, categories)
        log(f"Session resolution: resolved={resolution['resolved']}, reason={resolution['reason']}")

        if not resolution["resolved"]:
            store_unresolved_session(db, session_id, resolution, messages)
            print(f"\n⚠️  UNRESOLVED SESSION: {resolution['reason']}")
            print(f"   Unresolved items: {len(resolution['unresolved_items'])}")
            for item in resolution["unresolved_items"][:3]:
                print(f"   - [{item['type']}] {item['content'][:60]}...")
        else:
            print(f"\n✓ Session resolved: {resolution['reason']}")

def list_unresolved():
    """List all unresolved sessions for reflection."""
    db = get_db()

    if not db.has_collection("unresolved_sessions"):
        print("No unresolved sessions collection yet.")
        return

    query = """
    FOR doc IN unresolved_sessions
        FILTER doc.status == "pending"
        SORT doc.archived_at DESC
        LIMIT 20
        RETURN doc
    """

    sessions = list(db.aql.execute(query))

    if not sessions:
        print("✓ No unresolved sessions pending.")
        return

    print(f"\n⚠️  {len(sessions)} UNRESOLVED SESSIONS:\n")
    print("-" * 80)

    for s in sessions:
        resolution = s.get("resolution", {})
        print(f"Session: {s.get('session_id', 'unknown')}")
        print(f"  Reason: {resolution.get('reason', 'unknown')}")
        print(f"  Items:  {len(resolution.get('unresolved_items', []))}")
        print(f"  Summary: {s.get('summary', '')[:100]}...")
        print()

    print("-" * 80)
    print("Use '/learn --from-gaps' to generate curiosity from these gaps.")


def mark_resolved(session_id: str):
    """Mark a session as resolved after follow-up."""
    db = get_db()

    if not db.has_collection("unresolved_sessions"):
        print("No unresolved sessions collection.")
        return

    ts = int(time.time())
    result = list(db.aql.execute(
        """
        FOR doc IN unresolved_sessions
            FILTER doc.session_id == @sid
            UPDATE doc WITH { status: "resolved", resolved_at: @ts } IN unresolved_sessions
            RETURN NEW
        """,
        bind_vars={"sid": session_id, "ts": ts}
    ))

    if result:
        print(f"✓ Marked session as resolved: {session_id}")
    else:
        print(f"Session not found: {session_id}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  archive_episode.py archive <transcript.json>  - Archive a session")
        print("  archive_episode.py list-unresolved            - List pending sessions")
        print("  archive_episode.py resolve <session_id>       - Mark session resolved")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "archive" and len(sys.argv) >= 3:
        analyze_and_archive(sys.argv[2])
    elif cmd == "list-unresolved":
        list_unresolved()
    elif cmd == "resolve" and len(sys.argv) >= 3:
        mark_resolved(sys.argv[2])
    elif cmd.endswith(".json"):
        # Backward compatibility: treat first arg as transcript path
        analyze_and_archive(cmd)
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
