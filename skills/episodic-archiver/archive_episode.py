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


SKILLS_DIR = Path(__file__).resolve().parents[1]
if str(SKILLS_DIR) not in sys.path:
    sys.path.append(str(SKILLS_DIR))

try:
    from dotenv_helper import load_env as _load_env  # type: ignore
except Exception:
    from dotenv import load_dotenv, find_dotenv  # type: ignore

    def _load_env():
        try:
            load_dotenv(find_dotenv(usecwd=True), override=False)
        except Exception:
            pass

_load_env()

# 1. Setup Paths for graph_memory
try:
    from graph_memory.arango_client import get_db
    from graph_memory.embeddings import encode_texts
except ImportError:
    sys.path.append(os.path.join(os.path.dirname(__file__), "../../../src"))
    from graph_memory.arango_client import get_db
    from graph_memory.embeddings import encode_texts

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
            [script_path, "--source_id", source_id, "--text", content, "--type", "episode_turn"],
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

    print(f"Archiving {len(messages)} messages for session {session_id}...")

    for msg in tqdm(messages, desc="Archiving turns", unit="turn"):
        content = (msg.get("message") or msg.get("content") or "").strip()
        if not content:
            skipped += 1
            continue

        dedupe = _dedupe_key(session_id, msg)
        # 1. Embed
        embedding = encode_texts([content])[0]

        # 2. Categorize (LLM)
        category = "info"
        if len(content) > 50:
            prompt = (
                "Categorize this agent message into one word "
                "(Task, Question, Solution, Error, Chat, Meta): "
                f"{content[:500]}"
            )
            category = call_llm_simple(prompt)

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

        # 4. Verify Edges (External Skill) where relevant
        if category.lower() in ["solution", "task"] and len(content) > 30:
            trigger_edge_verification(stored_id, content)

    log(
        f"Archive summary: inserted={inserted}, updated={updated}, skipped={skipped}, errors={errors}"
    )

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: archive_episode.py <transcript.json>")
        sys.exit(1)
    
    analyze_and_archive(sys.argv[1])
