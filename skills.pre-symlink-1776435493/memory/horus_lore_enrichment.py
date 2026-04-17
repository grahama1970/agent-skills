"""
Horus Lore Ingest - Enrichment Module
LLM batch processing for document enrichment (abstracts, topics, cleaning).
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompt-lab" / "prompts"


def _load_prompt(name: str) -> str:
    path = _PROMPT_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt '{name}' not found at {path}")
    return path.read_text().strip()


ENRICH_PROMPT_TEMPLATE = _load_prompt("memory_horus_lore_enrichment_v1") + "\n"


# =============================================================================
# Batch Preparation
# =============================================================================

def prepare_enrichment_batch(db: Any, output_path: Path, limit: int = 0) -> int:
    """
    Prepare JSONL batch file for scillm enrichment.

    Output format matches scillm batch.py input: {"prompt": "..."} per line.
    A sidecar file (<output_path>.keys.json) maps index -> doc _key for
    apply_enrichment_results().

    Returns number of documents prepared.
    """
    # Get documents without enrichment
    aql = """
    FOR doc IN horus_lore_docs
    FILTER doc.abstract == null
    LIMIT @limit
    RETURN {
        _key: doc._key,
        source: doc.source,
        full_text: doc.full_text
    }
    """

    bind_vars = {"limit": limit if limit > 0 else 1000000}
    docs = list(db.aql.execute(aql, bind_vars=bind_vars))

    if not docs:
        print("No documents need enrichment.")
        return 0

    # Write JSONL for scillm batch (simple {"prompt": "..."} format)
    key_map: dict[int, str] = {}
    with open(output_path, "w") as f:
        for idx, doc in enumerate(docs):
            # Take first 2000 words for enrichment
            text_excerpt = " ".join(doc["full_text"].split()[:2000])
            request = {"prompt": ENRICH_PROMPT_TEMPLATE + text_excerpt}
            f.write(json.dumps(request) + "\n")
            key_map[idx] = doc["_key"]

    # Write sidecar key map so apply_enrichment_results can correlate
    sidecar = Path(str(output_path) + ".keys.json")
    sidecar.write_text(json.dumps(key_map))

    print(f"Prepared {len(docs)} documents for enrichment: {output_path}")
    print(f"Key map written to: {sidecar}")
    return len(docs)


# =============================================================================
# Results Application
# =============================================================================

def apply_enrichment_results(db: Any, results_path: Path) -> dict[str, int]:
    """
    Apply enrichment results from scillm batch output.

    Expects scillm batch output format: {"index": N, "content": "...", "ok": true}
    Uses sidecar key map (<results_path>.keys.json or inferred from input) to
    map index -> doc _key.

    Returns counts of success/errors.
    """
    docs_col = db.collection("horus_lore_docs")
    stats = {"success": 0, "errors": 0}

    # Load sidecar key map (index -> doc _key)
    sidecar = Path(str(results_path) + ".keys.json")
    if not sidecar.exists():
        # Try sibling with .keys.json extension based on results path
        sidecar = results_path.with_suffix(".keys.json")

    key_map: dict[str, str] = {}
    if sidecar.exists():
        key_map = json.loads(sidecar.read_text())

    with open(results_path) as f:
        for line in f:
            if not line.strip():
                continue

            try:
                result = json.loads(line)

                # scillm batch output: {"index": N, "content": "...", "ok": true}
                idx = result.get("index")
                doc_key = key_map.get(str(idx)) if idx is not None else result.get("custom_id")

                if not result.get("ok") or not result.get("content"):
                    stats["errors"] += 1
                    continue

                content = result.get("content", "")

                # Parse JSON from response
                # Handle potential markdown code blocks
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]

                enrichment = json.loads(content)

                # Update document
                update_doc = {
                    "_key": doc_key,
                    "abstract": enrichment.get("abstract"),
                    "topics": enrichment.get("topics", []),
                    "primary_characters": enrichment.get("primary_characters", []),
                    "bridge_attributes": enrichment.get("bridge_attributes", []),
                    "plot_points": enrichment.get("plot_points", []),
                    "timeline_position": enrichment.get("timeline_position"),
                    "lore_text": enrichment.get("lore_text"),  # Cleaned lore-only content
                    "is_lore": enrichment.get("is_lore", True),
                    "enriched_at": datetime.now(timezone.utc).isoformat(),
                }

                # If lore_text provided, update word count
                if enrichment.get("lore_text"):
                    update_doc["lore_word_count"] = len(enrichment["lore_text"].split())

                docs_col.update(update_doc)
                stats["success"] += 1

            except Exception as e:
                print(f"Error processing result: {e}")
                stats["errors"] += 1

    return stats
