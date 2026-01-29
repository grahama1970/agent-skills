"""
Horus Lore Ingest - Enrichment Module
LLM batch processing for document enrichment (abstracts, topics, cleaning).
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# =============================================================================
# LLM Enrichment Prompt Template
# =============================================================================

ENRICH_PROMPT_TEMPLATE = """You are analyzing a Warhammer 40,000 Horus Heresy transcript for a knowledge base.

Given the following transcript excerpt, provide:

1. **abstract**: A 1-2 sentence summary of the LORE content (ignore YouTuber commentary)
2. **topics**: List of 3-7 key lore topics/themes (e.g., "Davin", "Betrayal", "Siege of Terra")
3. **primary_characters**: List of main 40k characters featured (Primarchs, named characters)
4. **plot_points**: List of major plot events/developments in this content. Each should be:
   - A brief description (1 sentence)
   - Characters involved
   - Consequences or what it leads to
   Format: [{"event": "...", "characters": [...], "leads_to": "..."}]
5. **timeline_position**: Where this fits in the Heresy timeline:
   - "pre_heresy" (Great Crusade, before Davin)
   - "early_heresy" (Davin to Isstvan)
   - "mid_heresy" (Shadow Crusade, Imperium Secundus)
   - "late_heresy" (March to Terra)
   - "siege_of_terra" (The Siege)
   - "unknown" if unclear
6. **lore_text**: The lore-relevant content ONLY, with these removed:
   - Channel promotions ("subscribe", "like", "Patreon", "support the channel")
   - Sponsor messages and ads
   - YouTuber personal commentary ("in my opinion", "what do you think")
   - Intro/outro phrases ("welcome back", "thanks for watching")
   - Timestamps and chapter markers
   - Fix Warhammer proper noun spellings (Horus, Sanguinius, Erebus, etc.)
7. **is_lore**: true if this contains substantial 40k lore, false if mostly non-lore content

Respond in JSON format with these exact keys: abstract, topics, primary_characters, plot_points, timeline_position, lore_text, is_lore

TRANSCRIPT:
"""


# =============================================================================
# Batch Preparation
# =============================================================================

def prepare_enrichment_batch(db: Any, output_path: Path, limit: int = 0) -> int:
    """
    Prepare JSONL batch file for scillm enrichment.

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

    # Write JSONL for scillm batch
    with open(output_path, "w") as f:
        for doc in docs:
            # Take first 2000 words for enrichment
            text_excerpt = " ".join(doc["full_text"].split()[:2000])

            request = {
                "custom_id": doc["_key"],
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 2000,
                    "messages": [
                        {
                            "role": "user",
                            "content": ENRICH_PROMPT_TEMPLATE + text_excerpt
                        }
                    ]
                }
            }
            f.write(json.dumps(request) + "\n")

    print(f"Prepared {len(docs)} documents for enrichment: {output_path}")
    return len(docs)


# =============================================================================
# Results Application
# =============================================================================

def apply_enrichment_results(db: Any, results_path: Path) -> dict[str, int]:
    """
    Apply enrichment results from scillm batch output.

    Returns counts of success/errors.
    """
    docs_col = db.collection("horus_lore_docs")
    stats = {"success": 0, "errors": 0}

    with open(results_path) as f:
        for line in f:
            if not line.strip():
                continue

            try:
                result = json.loads(line)
                doc_key = result.get("custom_id")

                # Extract response
                response = result.get("response", {})
                body = response.get("body", {})
                choices = body.get("choices", [])

                if not choices:
                    stats["errors"] += 1
                    continue

                content = choices[0].get("message", {}).get("content", "")

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
