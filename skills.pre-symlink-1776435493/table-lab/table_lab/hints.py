"""Read/write strategy hint files for S05 integration.

Two-tier storage:
1. Per-skill hints at ~/.pi/table-lab/hints/<preset>_<category>.json
2. Corpus-level aggregation at CORPUS_ROOT/metadata/table_hints.json

S05 reads the corpus-level file at extraction time.
Key format: S05 looks up "{preset}:{category}" using values from pipeline_context.json.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from .config import CORPUS_HINTS_PATH, CORPUS_ROOT, HINTS_DIR, KNOWN_PRESETS


def _hint_key(preset: str, category: str) -> str:
    """Build filesystem-safe key from preset and category."""
    p = (preset or "unknown").replace("/", "_").replace(" ", "_")
    c = (category or "unknown").replace("/", "_").replace(" ", "_")
    return f"{p}_{c}"


def save_hint(preset: str, category: str, hint_data: dict, store_memory: bool = True) -> Path:
    """Save hint to local skill data directory and optionally to /memory.

    Args:
        preset: Document preset (e.g., "arxiv", "requirements_spec")
        category: Document category (e.g., "Scientific", "Engineering")
        hint_data: Tuning parameters and metadata
        store_memory: If True, also store in /memory for recall during extraction

    Returns:
        Path to saved hint file
    """
    key = _hint_key(preset, category)
    path = HINTS_DIR / f"{key}.json"
    hint_data["saved_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(hint_data, indent=2))
    logger.info(f"Saved hint to {path}")

    # Store in /memory for deterministic recall during extraction
    if store_memory:
        hint_data["preset"] = preset
        hint_data["category"] = category
        store_in_memory(hint_data)

    return path


def load_hint(preset: str, category: str) -> dict | None:
    """Load hint from local skill data directory."""
    key = _hint_key(preset, category)
    path = HINTS_DIR / f"{key}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def list_hints() -> list[dict]:
    """List all stored hints."""
    hints = []
    for path in sorted(HINTS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
            data["_file"] = path.name
            hints.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return hints


def export_to_corpus(corpus_hints_path: Path | None = None) -> Path:
    """Merge all local hints into the corpus-level table_hints.json.

    This is the file that S05 reads at extraction time.
    """
    target = corpus_hints_path or CORPUS_HINTS_PATH

    # Load existing corpus hints
    existing: dict = {"version": 1, "hints": {}}
    if target.exists():
        try:
            existing = json.loads(target.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    # Merge local hints — write under both original key AND S05-canonical key
    for hint in list_hints():
        preset = hint.get("preset", "unknown")
        category = hint.get("category", "unknown")
        original_key = f"{preset}:{category}"

        hint_data = {
            "flavor": hint.get("flavor", "lattice"),
            "line_scale": hint.get("line_scale"),
            "edge_tol": hint.get("edge_tol"),
            "process_background": hint.get("process_background", False),
            "confidence": hint.get("confidence", "medium"),
            "source_pdf": hint.get("pdf_tested", ""),
            "tuned_at": hint.get("tuned_at", ""),
            "fragmentation_score": hint.get("fragmentation_score", 0),
            "cell_count": hint.get("cell_count", 0),
            "bridge_tags": hint.get("bridge_tags", []),
        }

        # Write under original key
        existing["hints"][original_key] = hint_data

        # Also write under S05-canonical key if a mapping exists
        s05_key = hint.get("s05_key", "")
        if s05_key and s05_key != original_key:
            existing["hints"][s05_key] = hint_data
            logger.debug(f"Wrote alias key {s05_key} for {original_key}")

    existing["updated_at"] = datetime.now(timezone.utc).isoformat()

    # Write atomically
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(existing, indent=2))
    tmp.rename(target)

    logger.info(f"Exported {len(existing['hints'])} hints to {target}")
    return target


def load_corpus_hints(corpus_hints_path: Path | None = None) -> dict:
    """Load corpus-level hints (for S05 integration).

    Returns dict mapping 'preset:category' -> hint params.
    """
    target = corpus_hints_path or CORPUS_HINTS_PATH
    if not target.exists():
        return {}
    try:
        data = json.loads(target.read_text())
        return data.get("hints", {})
    except (json.JSONDecodeError, OSError):
        return {}


def resolve_preset_category(pdf_path: Path) -> tuple[str, str]:
    """Read pipeline_context.json to get S00's preset/category for this PDF.

    Strategy 1: Walk up from the PDF to find pipeline_context.json in parent dirs.
    Strategy 2: Filename-based heuristics using KNOWN_PRESETS.

    Returns:
        (preset_name, category) e.g. ("requirements_spec", "Engineering")
    """
    pdf_name = pdf_path.stem

    # Strategy 1: Walk up from PDF to find pipeline_context.json in parent dirs.
    # Typical layout: results/<dir_name>/01_annotation_processor/<pdf>.pdf
    # pipeline_context.json lives at: results/<dir_name>/pipeline_context.json
    current = pdf_path.parent
    for _ in range(4):  # max 4 levels up
        ctx_path = current / "pipeline_context.json"
        if ctx_path.exists():
            try:
                ctx = json.loads(ctx_path.read_text())
                preset = ctx.get("preset_name", "")
                # category is nested under config.category
                category = ctx.get("config", {}).get("category", "") or ctx.get("category", "")
                if preset:
                    logger.debug(f"Resolved {pdf_name} -> {preset}:{category} from {ctx_path}")
                    return preset, category
            except (json.JSONDecodeError, OSError):
                pass
        parent = current.parent
        if parent == current:
            break
        current = parent

    # Strategy 2: Use KNOWN_PRESETS heuristics based on filename patterns
    name_lower = pdf_name.lower()
    for prefix, category in [
        ("arxiv", "Scientific"),
        ("nist", "Engineering"),
        ("mil_std", "Engineering"),
        ("mil-std", "Engineering"),
        ("ecss", "Engineering"),
        ("nasa", "Engineering"),
        ("faa", "Engineering"),
    ]:
        if name_lower.startswith(prefix):
            for preset, cat in KNOWN_PRESETS.items():
                if cat == category:
                    logger.debug(f"Resolved {pdf_name} -> {preset}:{category} via filename heuristic")
                    return preset, category

    return "", ""


def read_s00_profile(pdf_path: Path) -> dict:
    """Read S00 profile data from pipeline_context.json near the PDF.

    Returns dict with keys: estimated_table_count, page_count, estimated_timeout_seconds,
    max_tables_per_page, or empty dict if not found.
    """
    current = pdf_path.parent
    for _ in range(4):
        ctx_path = current / "pipeline_context.json"
        if ctx_path.exists():
            try:
                ctx = json.loads(ctx_path.read_text())
                return {
                    "estimated_table_count": ctx.get("estimated_table_count", 0),
                    "page_count": ctx.get("page_count", 0),
                    "estimated_timeout_seconds": ctx.get("estimated_timeout_seconds", 0),
                    "max_tables_per_page": ctx.get("max_tables_per_page", 0),
                    "file_size_mb": ctx.get("file_size_mb", 0),
                }
            except (json.JSONDecodeError, OSError):
                pass
        parent = current.parent
        if parent == current:
            break
        current = parent
    return {}


def normalize_hint_key(preset: str, category: str) -> str:
    """Build the canonical hint key that S05 will look up.

    S05 constructs keys as f"{preset}:{category or ''}" from pipeline_context.json.
    This function ensures our hints use the same vocabulary.
    """
    return f"{preset}:{category or ''}"


def store_in_memory(hint_data: dict) -> bool:
    """Store tuning pattern in /memory for recall during extraction.

    This enables the agent to:
    1. Recall similar patterns when extracting a new PDF
    2. Query "table extraction lattice engineering" to find optimal params
    3. Use multi-hop queries via Federated Taxonomy bridge tags

    NOTE: Also writes to a sync queue file for batch synchronization
    if the HTTP call fails (e.g., due to subprocess network restrictions).

    Args:
        hint_data: The hint dictionary with preset, category, flavor, params, bridge_tags

    Returns:
        True if successfully stored in memory, False otherwise
    """
    import subprocess

    MEMORY_API_URL = "http://127.0.0.1:8601/learn"
    SYNC_QUEUE_FILE = Path.home() / ".pi" / "table-lab" / "memory_sync_queue.jsonl"

    preset = hint_data.get("preset", "unknown")
    category = hint_data.get("category", "unknown")
    flavor = hint_data.get("flavor", "lattice")
    bridge_tags = hint_data.get("bridge_tags", [])
    fragmentation = hint_data.get("fragmentation_score", 0)
    cell_count = hint_data.get("cell_count", 0)
    line_scale = hint_data.get("line_scale")
    edge_tol = hint_data.get("edge_tol")
    pdf_tested = hint_data.get("pdf_tested", "")

    # Build problem description for recall
    problem = (
        f"Table extraction for {preset} {category} documents. "
        f"Characteristics: {', '.join(bridge_tags) if bridge_tags else 'standard'}. "
        f"Similar to: {pdf_tested}"
    )

    # Build structured solution
    solution_parts = [
        f"Use {flavor} extraction strategy.",
    ]
    if line_scale:
        solution_parts.append(f"Set line_scale={line_scale}.")
    if edge_tol:
        solution_parts.append(f"Set edge_tol={edge_tol}.")
    if fragmentation == 0:
        solution_parts.append("Expect clean extraction (fragmentation=0).")
    elif fragmentation > 5:
        solution_parts.append(f"Expect fragmentation issues (score={fragmentation}). Consider fixture-tricky patterns.")
    solution_parts.append(f"Validated on {cell_count} cells.")

    solution = " ".join(solution_parts)

    # Build tags list
    tags = list(bridge_tags) + [
        "table-extraction",
        f"flavor:{flavor}",
    ]
    if preset:
        tags.append(f"preset:{preset}")
    if category:
        tags.append(f"category:{category}")

    # Use curl (urllib has connectivity issues with local services)
    try:
        payload = json.dumps({
            "problem": problem,
            "solution": solution,
            "tags": tags,
        })

        cmd = [
            "curl", "-s", "-X", "POST", MEMORY_API_URL,
            "-H", "Content-Type: application/json",
            "-d", payload,
            "--max-time", "10",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)

        if result.returncode == 0 and result.stdout:
            response = json.loads(result.stdout)
            if response.get("meta", {}).get("ok"):
                logger.info(f"Stored pattern in /memory: {preset}:{category} [{flavor}]")
                return True
            else:
                logger.debug(f"Memory learn returned not ok, queueing: {response}")
                _queue_for_sync(SYNC_QUEUE_FILE, problem, solution, tags)
                return True  # Queued
        else:
            # curl failed (return code 28 = timeout, etc.) - queue for later sync
            logger.debug(f"curl failed (rc={result.returncode}), queueing for batch sync")
            _queue_for_sync(SYNC_QUEUE_FILE, problem, solution, tags)
            return True  # Queued

    except subprocess.TimeoutExpired:
        logger.debug("Memory HTTP timed out, queueing for batch sync")
        _queue_for_sync(SYNC_QUEUE_FILE, problem, solution, tags)
        return True  # Queued successfully
    except Exception as e:
        logger.debug(f"Memory HTTP error ({e}), queueing for batch sync")
        _queue_for_sync(SYNC_QUEUE_FILE, problem, solution, tags)
        return True  # Queued successfully


def _queue_for_sync(queue_file: Path, problem: str, solution: str, tags: list[str]) -> None:
    """Write pattern to sync queue for batch processing by memory_sync.sh."""
    queue_file.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "problem": problem,
        "solution": solution,
        "tags": tags,
        "queued_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(queue_file, "a") as f:
        f.write(json.dumps(entry) + "\n")
    logger.info(f"Queued pattern for memory sync: {problem[:50]}...")


def recall_similar_patterns(query: str, limit: int = 5) -> list[dict]:
    """Recall similar tuning patterns from /memory.

    Use this during extraction to find optimal parameters for similar documents.

    Args:
        query: Search query like "lattice engineering tables" or "arxiv scientific"
        limit: Max patterns to return

    Returns:
        List of recalled patterns with problem/solution pairs
    """
    import subprocess
    import urllib.parse

    MEMORY_API_URL = "http://127.0.0.1:8601/recall"

    try:
        # Build query with table extraction context
        full_query = f"table extraction {query}"

        params = urllib.parse.urlencode({
            "q": full_query,
            "limit": limit,
        })

        cmd = [
            "curl", "-s", "-X", "GET",
            f"{MEMORY_API_URL}?{params}",
            "--max-time", "10",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)

        if result.returncode == 0 and result.stdout:
            response = json.loads(result.stdout)
            if response.get("meta", {}).get("ok"):
                items = response.get("items", [])
                logger.debug(f"Recalled {len(items)} patterns for '{query}'")
                return items
            return []
        return []

    except subprocess.TimeoutExpired:
        logger.debug("Memory recall timed out")
        return []
    except Exception as e:
        logger.debug(f"Memory recall error: {e}")
        return []
