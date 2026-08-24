#!/usr/bin/env python3
"""
Mine real human conversations from CLI agents for bridge classifier training.

Integrates with:
- /taxonomy - Bridge label extraction
- /memory - Deduplication against existing lessons
- /episodic-archiver - Emotional context from sessions

Two-tier training approach:
1. Developer (Graham) - baseline attunement
2. Client - specific adaptation
"""

import typer
import hashlib
import json
import os
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional
import httpx
from loguru import logger

# ── TaskClient integration ──────────────────────────────────────────────────
try:
    sys.path.insert(0, str(Path.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

# Skill paths
SKILL_DIR = Path(__file__).parent
PI_SKILLS = SKILL_DIR.parent
TAXONOMY_SKILL = PI_SKILLS / "taxonomy"
MEMORY_SKILL = PI_SKILLS / "memory"
EPISODIC_SKILL = PI_SKILLS / "episodic-archiver"
CLASSIFIER_SKILL = PI_SKILLS / "create-classifier"

# Output directory
DATA_DIR = SKILL_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Import from taxonomy skill
sys.path.insert(0, str(TAXONOMY_SKILL))
try:
    from taxonomy import extract_keywords, BRIDGE_TAGS, BRIDGE_KEYWORDS
    BRIDGE_LABELS = list(BRIDGE_TAGS)
    TAXONOMY_AVAILABLE = True
except ImportError:
    print("[WARN] Taxonomy skill not available, using fallback")
    BRIDGE_LABELS = ["Corruption", "Precision", "Resilience", "Fragility", "Loyalty", "Stealth"]
    BRIDGE_TAGS = set(BRIDGE_LABELS)
    TAXONOMY_AVAILABLE = False
    def extract_keywords(text: str) -> list[str]:
        return []

# Memory-first: route all DB access through /memory subprocess
import subprocess as _sp

# Removed: memory accessed via httpx to Unix socket (see _memory_cmd)
MEMORY_AVAILABLE = True  # Assume available; fails loud at call site


def _chain_task_text(chain: dict) -> str:
    """Build the typed skill-chain task text from a mined transcript record."""
    request = str(chain.get("request", "")).strip()
    project = str(chain.get("project", "")).strip()
    source = str(chain.get("source", "")).strip()
    suffix_parts = []
    if project:
        suffix_parts.append(f"Project: {project}")
    if source:
        suffix_parts.append(f"Source: {source}")
    suffix = f" ({'; '.join(suffix_parts)})" if suffix_parts else ""
    return f"{request[:360]}{suffix}"[:500]


def _store_mined_chains_to_typed_memory(
    chains_found: list[dict],
    memory_run: Path = MEMORY_SKILL / "run.sh",
    limit: int = 100,
) -> int:
    """Store mined chains as typed ``skill_chains`` records.

    Skill-chain recall reads the first-class ``skill_chains`` collection. Using
    ``memory learn`` here would write ordinary lessons and recreate issue #145.
    """
    stored = 0
    for chain in chains_found[:limit]:
        raw_chain = chain.get("chain", [])
        if not isinstance(raw_chain, list):
            continue
        skills = [str(skill).lstrip("/") for skill in raw_chain if str(skill).strip()]
        if len(skills) < 2:
            continue
        try:
            result = _sp.run(
                [
                    str(memory_run),
                    "chain-learn",
                    "--skills",
                    ",".join(skills),
                    "--task",
                    _chain_task_text(chain),
                    "--source",
                    "transcript",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (_sp.TimeoutExpired, FileNotFoundError):
            continue
        if result.returncode == 0:
            stored += 1
        else:
            logger.warning(
                "Typed skill_chain storage failed for source={} stderr={}",
                chain.get("source", ""),
                result.stderr.strip()[:500],
            )
    return stored


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

CLI_AGENT_SOURCES = {
    "claude": Path.home() / ".claude" / "projects",
    "codex_history": Path.home() / ".codex" / "history.jsonl",
    "codex_sessions": Path.home() / ".codex" / "sessions",
    "gemini": Path.home() / ".gemini" / "projects",
    "pi": Path.home() / ".pi" / "projects",
}

# Patterns that indicate system-injected prompts (not real human messages)
SYSTEM_PROMPT_PATTERNS = [
    "You are an expert",
    "You are a",
    "<system",
    "Provide a high-reasoning",
    "Return only",
    "Given this query",
    "Given the following",
    "Design Rules:",
    "Use a 24x24",
    "As an expert",
    "Your task is",
    "Create a",
    "Generate a",
    "Analyze the",
    "Based on the",
    "Please provide",
    "Consider the following",
]


# ─────────────────────────────────────────────────────────────────────────────
# Emotional State Detection
# ─────────────────────────────────────────────────────────────────────────────

def detect_emotional_state(text: str) -> dict:
    """Detect emotional state - both frustration AND satisfaction."""
    text_lower = text.lower()

    frustration_signals = [
        "wrong", "not what", "error", "failed", "no!",
        "frustrat", "livid", "angry", "annoyed", "stop",
        "shouldn't", "why did", "crashed", "not working",
        "broken", "useless", "terrible", "disappointed",
        "confused", "stuck", "blocked",
    ]

    satisfaction_signals = [
        "perfect", "great", "thanks", "excellent", "good job",
        "works", "working", "correct", "yes!", "nice",
        "love it", "exactly", "brilliant", "amazing", "awesome",
        "happy", "pleased", "satisfied", "impressed", "well done",
        "that's it", "nailed it", "spot on", "beautiful",
        "finally", "makes sense", "understand now", "got it",
        "proceed", "continue", "looks good", "ship it",
    ]

    state = {
        "frustrated": any(sig in text_lower for sig in frustration_signals),
        "satisfied": any(sig in text_lower for sig in satisfaction_signals),
        "unresolved": "unresolved" in text_lower or "still broken" in text_lower,
    }

    # Intensity estimation
    frustration_count = sum(1 for sig in frustration_signals if sig in text_lower)
    satisfaction_count = sum(1 for sig in satisfaction_signals if sig in text_lower)

    if frustration_count >= 2:
        state["intensity"] = "high_frustration"
    elif satisfaction_count >= 2:
        state["intensity"] = "very_satisfied"
    elif state["satisfied"]:
        state["intensity"] = "satisfied"
    elif state["frustrated"]:
        state["intensity"] = "frustrated"
    else:
        state["intensity"] = "neutral"

    return state


# ─────────────────────────────────────────────────────────────────────────────
# Bridge Extraction (uses /taxonomy)
# ─────────────────────────────────────────────────────────────────────────────

def extract_bridges(text: str) -> list[str]:
    """Extract bridges using taxonomy skill + emotional context."""
    # Use taxonomy skill's keyword extraction
    bridges = extract_keywords(text) if TAXONOMY_AVAILABLE else []

    # Enhance with emotional context
    emotional = detect_emotional_state(text)
    text_lower = text.lower()

    # Frustrated → Fragility
    if emotional["frustrated"] and "Fragility" not in bridges:
        bridges.append("Fragility")

    # Satisfied → Resilience (system worked)
    if emotional["satisfied"] and "Resilience" not in bridges:
        bridges.append("Resilience")

    # Satisfaction/understanding → Loyalty (good collaboration)
    if emotional["satisfied"] or any(w in text_lower for w in ["understand", "attune", "human"]):
        if "Loyalty" not in bridges:
            bridges.append("Loyalty")

    # High satisfaction → both Resilience AND Loyalty
    if emotional.get("intensity") == "very_satisfied":
        if "Resilience" not in bridges:
            bridges.append("Resilience")
        if "Loyalty" not in bridges:
            bridges.append("Loyalty")

    return bridges


# ─────────────────────────────────────────────────────────────────────────────
# Text Utilities
# ─────────────────────────────────────────────────────────────────────────────

def text_hash(text: str) -> str:
    """Generate hash for deduplication."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def is_real_human_message(content: str) -> bool:
    """Check if content is real human message vs system-injected prompt."""
    content = content.strip()

    if len(content) < 20:
        return False
    if content.startswith("/"):
        return False
    if content.startswith("<"):
        return False

    content_lower = content.lower()
    for pattern in SYSTEM_PROMPT_PATTERNS:
        if content_lower.startswith(pattern.lower()):
            return False

    if any(tag in content for tag in ["task-id>", "output-file>", "agent-id>", "task-notification"]):
        return False

    return True


# ─────────────────────────────────────────────────────────────────────────────
# Memory Integration (deduplication)
# ─────────────────────────────────────────────────────────────────────────────

def get_existing_lesson_hashes() -> set:
    """Get hashes of existing lessons in memory for deduplication."""
    try:
        # Sample a batch of lessons to build dedup set
        data = _memory_cmd([
            "sample", "--collection", "lessons",
            "--limit", "5000", "--fields", "problem",
        ])
        hashes = set()
        for item in data.get("items", []):
            body = item.get("problem", "")
            if body:
                hashes.add(text_hash(body[:500]))
        return hashes
    except Exception as e:
        print(f"[WARN] Failed to get memory hashes: {e}")
        return set()


def store_to_memory(examples: list[dict]) -> int:
    """Store mined examples via /memory learn."""
    stored = 0
    for ex in examples:
        try:
            _memory_cmd([
                "learn",
                "--problem", f"Training example: {ex['text'][:200]}",
                "--solution", json.dumps({"labels": ex["labels"], "source": ex.get("source", "unknown")}),
                "--scope", "training_examples",
                "--tag", "mined_transcript",
            ])
            stored += 1
        except Exception as e:
            logger.debug("memory learn failed: {}", e)
    return stored


# ─────────────────────────────────────────────────────────────────────────────
# Transcript Extraction
# ─────────────────────────────────────────────────────────────────────────────

def discover_sources() -> dict[str, Path]:
    """Discover available CLI agent transcript sources."""
    sources = {}
    for name, path in CLI_AGENT_SOURCES.items():
        if path.exists():
            sources[name] = path
    return sources


def iter_transcripts(directory: Path) -> Iterator[Path]:
    """Iterate over transcript JSONL files."""
    for jsonl in directory.rglob("*.jsonl"):
        if "agent-" in jsonl.name:
            continue
        yield jsonl


def extract_claude_messages(transcript_path: Path) -> list[dict]:
    """Extract messages from Claude transcript format."""
    messages = []
    try:
        with open(transcript_path, "r") as f:
            for line in f:
                try:
                    msg = json.loads(line)
                    if msg.get("type") == "user":
                        content = msg.get("message", {}).get("content", "")
                        if isinstance(content, str):
                            content = content.strip()
                            if is_real_human_message(content) and len(content) < 1000:
                                messages.append({
                                    "text": content,
                                    "source": f"claude:{transcript_path.name}",
                                    "timestamp": msg.get("timestamp"),
                                    "hash": text_hash(content),
                                })
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.debug("encoding failed: {}", e)
    return messages


def extract_codex_messages(history_path: Path) -> list[dict]:
    """Extract messages from Codex history.jsonl (pure human input!)."""
    messages = []
    try:
        with open(history_path, "r") as f:
            for line in f:
                try:
                    msg = json.loads(line)
                    text = msg.get("text", "").strip()
                    if is_real_human_message(text) and len(text) < 1000:
                        messages.append({
                            "text": text,
                            "source": f"codex:{msg.get('session_id', 'unknown')}",
                            "timestamp": msg.get("ts"),
                            "hash": text_hash(text),
                        })
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.debug("encoding failed: {}", e)
    return messages


# ─────────────────────────────────────────────────────────────────────────────
# Main Mining Function
# ─────────────────────────────────────────────────────────────────────────────

def mine_all_sources(
    output_path: Path,
    dedupe: bool = False,
    store_memory: bool = False,
    sample_size: int = 0,
) -> int:
    """Mine from all discovered CLI agent sources."""
    all_messages = []
    seen_hashes = set()

    # Get existing hashes for deduplication
    if dedupe:
        print("[INFO] Loading existing hashes for deduplication...")
        seen_hashes = get_existing_lesson_hashes()

        # Also dedupe against existing training data
        classifier_train = CLASSIFIER_SKILL / "data" / "bridge_classifier" / "train.jsonl"
        if classifier_train.exists():
            with open(classifier_train) as f:
                for line in f:
                    ex = json.loads(line)
                    seen_hashes.add(text_hash(ex.get("text", "")))

        print(f"[INFO] Deduplicating against {len(seen_hashes)} existing examples")

    sources = discover_sources()
    print(f"[INFO] Discovered {len(sources)} CLI agent sources")

    duplicates_skipped = 0

    for source_name, source_path in sources.items():
        print(f"[INFO] Mining {source_name}...")

        if source_name == "codex_history":
            messages = extract_codex_messages(source_path)
        elif source_path.is_dir():
            messages = []
            for transcript_path in iter_transcripts(source_path):
                messages.extend(extract_claude_messages(transcript_path))
        else:
            continue

        # Deduplicate
        for msg in messages:
            msg_hash = msg.get("hash", text_hash(msg["text"]))
            if msg_hash in seen_hashes:
                duplicates_skipped += 1
                continue
            seen_hashes.add(msg_hash)
            all_messages.append(msg)

        print(f"  {source_name}: {len(messages)} messages found")

    print(f"[INFO] Total: {len(all_messages)} unique messages")
    if duplicates_skipped > 0:
        print(f"[INFO] Skipped {duplicates_skipped} duplicates")

    # Sample if requested
    if sample_size > 0 and len(all_messages) > sample_size:
        all_messages = random.sample(all_messages, sample_size)
        print(f"[INFO] Sampled {sample_size} messages")

    # Label with bridges
    labeled = []
    monitor = TaskClient("mine-transcripts", total=len(all_messages)) if TaskClient else None
    for i, msg in enumerate(all_messages):
        bridges = extract_bridges(msg["text"])
        emotional = detect_emotional_state(msg["text"])

        if bridges:  # Only include if we got labels
            labeled.append({
                "text": msg["text"],
                "labels": bridges,
                "source": msg.get("source", "unknown"),
                "emotional_state": emotional.get("intensity", "neutral"),
            })

        if monitor:
            monitor.update(item=msg.get("source", "unknown"))

        if (i + 1) % 500 == 0:
            print(f"[INFO] Labeled {i + 1}/{len(all_messages)}")

    # Save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for ex in labeled:
            f.write(json.dumps({
                "text": ex["text"],
                "labels": ex["labels"],
            }) + "\n")

    if monitor:
        monitor.finish()

    print(f"[INFO] Saved {len(labeled)} labeled examples to {output_path}")

    # Optionally store to memory
    if store_memory and labeled:
        stored = store_to_memory(labeled)
        print(f"[INFO] Stored {stored} examples to memory")

    return len(labeled)


def analyze_coverage(data_path: Path):
    """Analyze bridge coverage in dataset."""
    counts = {b: 0 for b in BRIDGE_LABELS}
    total = 0

    with open(data_path) as f:
        for line in f:
            ex = json.loads(line)
            total += 1
            for label in ex.get("labels", []):
                if label in counts:
                    counts[label] += 1

    print(f"\nBridge Coverage ({total} examples):")
    print("-" * 40)
    for bridge, count in sorted(counts.items(), key=lambda x: -x[1]):
        pct = count / total * 100 if total > 0 else 0
        bar = "#" * int(pct / 2)
        print(f"{bridge:12} {count:5} ({pct:5.1f}%) {bar}")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

app = typer.Typer(help="Mine transcripts for bridge classifier")


@app.command()
def mine(
    all_agents: bool = typer.Option(False, help="Mine from all CLI agents"),
    dedupe: bool = typer.Option(False, help="Deduplicate against memory and existing training data"),
    store_memory: bool = typer.Option(False, help="Store examples to memory"),
    output: Path = typer.Option(DATA_DIR / "mined.jsonl", help="Output file"),
    sample: int = typer.Option(0, help="Sample N examples"),
):
    """Mine transcripts from CLI agent conversations."""
    random.seed(42)
    if all_agents:
        mine_all_sources(
            output,
            dedupe=dedupe,
            store_memory=store_memory,
            sample_size=sample,
        )
    else:
        print("Use --all-agents to mine from all CLI sources")
        raise typer.Exit(code=1)


@app.command()
def mine_chains(
    output: Path = typer.Option(DATA_DIR / "skill_chains.jsonl", help="Output JSONL"),
    store_memory: bool = typer.Option(True, help="Store chains to /memory"),
    all_projects: bool = typer.Option(True, "--all-projects", help="Scan all agent-inbox registered projects"),
):
    """Mine skill chains from transcripts across all registered projects.

    Scans Claude Code JSONL transcripts for /skill-name invocations in
    assistant tool_use messages. Extracts {request, chain, project} tuples.
    Stores to /memory with skill-chain tag for /recommend-skill-chain and
    /skill-lab gap detection.
    """
    import re

    SKILL_RE = re.compile(r"/([a-z][a-z0-9-]+)")
    CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"
    INBOX_REGISTRY = Path(os.environ.get(
        "AGENT_INBOX_DIR", Path.home() / ".agent-inbox",
    )) / "projects.json"

    def _load_skill_names() -> set[str]:
        try:
            return {
                d.name for d in PI_SKILLS.iterdir()
                if d.is_dir() and not d.name.startswith(".")
            }
        except OSError:
            return set()

    def _coerce_text(content: object) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return " ".join(
                b.get("text", "")
                for b in content
                if isinstance(b, dict) and b.get("text")
            )
        if isinstance(content, dict):
            return str(content.get("text", ""))
        return ""

    def _normalize_skill(name: str, skills: set[str]) -> Optional[str]:
        if not name:
            return None
        name = name[1:] if name.startswith("/") else name
        if name in skills:
            return f"/{name}"
        return None

    # Discover transcript dirs: all Claude project dirs, or just local
    transcript_dirs: list[Path] = []
    if all_projects and CLAUDE_PROJECTS.is_dir():
        transcript_dirs = [d for d in CLAUDE_PROJECTS.iterdir() if d.is_dir()]
    elif CLAUDE_PROJECTS.is_dir():
        cwd = Path.cwd().resolve()
        project_name: Optional[str] = None
        if INBOX_REGISTRY.exists():
            try:
                registry = json.loads(INBOX_REGISTRY.read_text())
                for name, path_str in registry.items():
                    try:
                        root = Path(path_str).resolve()
                    except OSError:
                        continue
                    if root == cwd or root in cwd.parents:
                        project_name = name
                        break
            except json.JSONDecodeError:
                pass
        candidates = []
        if project_name:
            candidates.append(project_name)
        candidates.append(cwd.name)
        for candidate in candidates:
            candidate_dir = CLAUDE_PROJECTS / candidate
            if candidate_dir.is_dir():
                transcript_dirs = [candidate_dir]
                break

    logger.info(f"Scanning {len(transcript_dirs)} project transcript dirs")

    chains_found: list[dict] = []
    seen_hashes: set[str] = set()
    skill_names = _load_skill_names()

    for proj_dir in transcript_dirs:
        project_name = proj_dir.name
        for jsonl_file in proj_dir.glob("*.jsonl"):
            if "agent-" in jsonl_file.name:
                continue
            try:
                with jsonl_file.open() as handle:
                    # Collect user requests and skill invocations per session
                    current_request = None
                    session_skills: list[str] = []

                    for line in handle:
                        if not line.strip():
                            continue
                        try:
                            msg = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        msg_type = msg.get("type", "")

                        # User message = new request context
                        if msg_type == "user" or msg.get("role") == "user":
                            # Save previous request+chain if we have one
                            if current_request and session_skills:
                                chain_key = hashlib.md5(
                                    f"{current_request}:{','.join(session_skills)}".encode()
                                ).hexdigest()
                                if chain_key not in seen_hashes:
                                    seen_hashes.add(chain_key)
                                    chains_found.append({
                                        "request": current_request[:300],
                                        "chain": session_skills,
                                        "project": project_name,
                                        "source": str(jsonl_file.name),
                                    })
                            # Reset for new request
                            content = _coerce_text(msg.get("content", ""))
                            current_request = content[:500] if content else None
                            session_skills = []

                        # Assistant tool_use = skill invocation
                        elif msg_type == "tool_use" or msg.get("type") == "tool_use":
                            tool = msg.get("name", "")
                            if tool in ("Read", "Write", "Edit", "Glob", "Grep", "Bash"):
                                continue
                            # Check for Skill tool with skill param
                            if tool == "Skill":
                                inp = msg.get("input", {})
                                if isinstance(inp, dict) and inp.get("skill"):
                                    normalized = _normalize_skill(str(inp["skill"]), skill_names)
                                    if normalized and normalized not in session_skills:
                                        session_skills.append(normalized)

                        # Assistant content blocks (Claude JSONL)
                        elif msg.get("role") == "assistant":
                            content = msg.get("content", "")
                            if isinstance(content, list):
                                for block in content:
                                    if not isinstance(block, dict):
                                        continue
                                    if block.get("type") == "tool_use":
                                        tool = block.get("name", "")
                                        if tool in ("Read", "Write", "Edit", "Glob", "Grep", "Bash"):
                                            continue
                                        if tool == "Skill":
                                            inp = block.get("input", {})
                                            if isinstance(inp, dict) and inp.get("skill"):
                                                normalized = _normalize_skill(str(inp["skill"]), skill_names)
                                                if normalized and normalized not in session_skills:
                                                    session_skills.append(normalized)
                                    elif block.get("type") == "text":
                                        text = block.get("text", "")
                                        skills_in_text = SKILL_RE.findall(text)
                                        for s in skills_in_text:
                                            normalized = _normalize_skill(s, skill_names)
                                            if normalized and normalized not in session_skills:
                                                session_skills.append(normalized)
                            elif isinstance(content, str):
                                skills_in_text = SKILL_RE.findall(content)
                                for s in skills_in_text:
                                    normalized = _normalize_skill(s, skill_names)
                                    if normalized and normalized not in session_skills:
                                        session_skills.append(normalized)

                    # Don't forget last request in file
                    if current_request and session_skills:
                        chain_key = hashlib.md5(
                            f"{current_request}:{','.join(session_skills)}".encode()
                        ).hexdigest()
                        if chain_key not in seen_hashes:
                            seen_hashes.add(chain_key)
                            chains_found.append({
                                "request": current_request[:300],
                                "chain": session_skills,
                                "project": project_name,
                                "source": str(jsonl_file.name),
                            })
            except OSError:
                continue

    # Save to JSONL
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        for chain in chains_found:
            f.write(json.dumps(chain) + "\n")

    logger.info(f"Mined {len(chains_found)} skill chains from {len(transcript_dirs)} projects → {output}")

    # Store typed skill_chains for consumption by /skill-lab and
    # /recommend-skill-chain. Do not use memory learn here; that writes ordinary
    # lessons and makes mined chains invisible to chain recall.
    if store_memory and chains_found:
        memory_run = MEMORY_SKILL / "run.sh"
        stored = _store_mined_chains_to_typed_memory(chains_found, memory_run=memory_run)
        logger.info(f"Stored {stored} typed skill_chains to /memory")

    return len(chains_found)


@app.command()
def analyze(
    file: Path = typer.Argument(..., help="JSONL file to analyze"),
):
    """Analyze bridge coverage in dataset."""
    random.seed(42)
    analyze_coverage(file)


@app.command()
def sources():
    """List discovered CLI agent transcript sources."""
    random.seed(42)
    found_sources = discover_sources()
    print(f"\nDiscovered {len(found_sources)} CLI agent sources:\n")
    for name, path in found_sources.items():
        size = "?"
        if path.is_file():
            size = f"{path.stat().st_size / 1024 / 1024:.1f}MB"
        elif path.is_dir():
            count = len(list(path.rglob("*.jsonl")))
            size = f"{count} files"
        print(f"  {name:20} {path} ({size})")


@app.command()
def export(
    sample: int = typer.Option(500, help="Number of samples to export"),
    output: Path = typer.Option(DATA_DIR / "for_review.jsonl", help="Output file"),
):
    """Export mined data for review."""
    random.seed(42)
    mine_all_sources(output, sample_size=sample)
    print(f"\nExported {sample} samples to {output}")


@app.command()
def merge(
    reviewed: Path = typer.Argument(..., help="Reviewed JSONL file"),
    target: Path = typer.Argument(..., help="Target JSONL file to merge into"),
):
    """Merge reviewed data into target dataset."""
    random.seed(42)
    existing = {}
    if target.exists():
        with open(target) as f:
            for line in f:
                ex = json.loads(line)
                existing[ex["text"]] = ex

    with open(reviewed) as f:
        for line in f:
            ex = json.loads(line)
            existing[ex["text"]] = ex

    with open(target, "w") as f:
        for ex in existing.values():
            f.write(json.dumps({"text": ex["text"], "labels": ex["labels"]}) + "\n")

    print(f"Merged to {len(existing)} examples in {target}")


if __name__ == "__main__":
    app()
