"""Load the opportunity terms corpus into the /memory ArangoDB collection.

The corpus (config/opportunity_vocabulary.json) is version-controlled like the
SPARTA/aerospace corpora; this idempotently upserts each concept (by _key) into
the `opportunity_vocabulary` collection that /extract-entities matches against.
Run after editing the corpus.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import typer

CORPUS = Path(__file__).resolve().parents[1] / "config" / "opportunity_vocabulary.json"
MEMORY_URL = "http://127.0.0.1:8601"

app = typer.Typer(add_completion=False)


def _store(doc: dict, collection: str) -> bool:
    body = json.dumps({"document": doc, "collection": collection}).encode()
    req = urllib.request.Request(f"{MEMORY_URL}/store", data=body, headers={"Content-Type": "application/json"})
    return bool(json.loads(urllib.request.urlopen(req, timeout=30).read()).get("stored"))


def _collection_count(collection: str, memory_url: str) -> int:
    body = json.dumps({"collection": collection}).encode()
    req = urllib.request.Request(
        f"{memory_url}/count", data=body, headers={"Content-Type": "application/json"}
    )
    return int(json.loads(urllib.request.urlopen(req, timeout=20).read()).get("count") or 0)


@app.command()
def load(corpus: Path = typer.Option(CORPUS, "--corpus"), memory_url: str = typer.Option(MEMORY_URL, "--memory-url")) -> None:
    """Upsert every concept from the corpus into opportunity_vocabulary.

    Also reports ORPHANS: documents in the collection that the corpus no longer
    defines. This loader only upserts (the memory service forbids destructive
    AQL), so concepts renamed in the corpus leave their old _key behind forever.
    On 2026-08-13 five such orphans (cybersecurity, ai-verification,
    ai-compliance, rd-innovation, agentic-systems) still carried bare-word
    `category` values — which extract-entities indexes as match terms — so
    "security guard services" matched cyber-security and "verification of
    employment" matched ai-verification. Orphans are a defect signal, not noise.
    """
    data = json.loads(corpus.read_text(encoding="utf-8"))
    collection = data["collection"]
    ok = 0
    for concept in data["concepts"]:
        if _store(concept, collection):
            ok += 1
    total = len(data["concepts"])
    try:
        in_collection = _collection_count(collection, memory_url)
    except Exception:  # noqa: BLE001 - count is diagnostic only
        in_collection = -1
    orphans = in_collection - total if in_collection >= 0 else -1
    receipt = {
        "status": "PASS" if orphans <= 0 else "PASS_WITH_ORPHANS",
        "collection": collection,
        "loaded": ok,
        "total": total,
        "documents_in_collection": in_collection,
        "orphaned_documents": max(orphans, 0),
    }
    if orphans > 0:
        receipt["orphan_warning"] = (
            f"{orphans} document(s) in {collection} are not defined by the corpus. "
            "They still match text. Inspect with: memory/run.sh sample --collection "
            f"{collection}; neutralize bare-word `category` values by re-storing them."
        )
    typer.echo(json.dumps(receipt))


if __name__ == "__main__":
    app()
