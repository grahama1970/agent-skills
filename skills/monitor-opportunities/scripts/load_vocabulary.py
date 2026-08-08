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


@app.command()
def load(corpus: Path = typer.Option(CORPUS, "--corpus"), memory_url: str = typer.Option(MEMORY_URL, "--memory-url")) -> None:
    """Upsert every concept from the corpus into opportunity_vocabulary."""
    data = json.loads(corpus.read_text(encoding="utf-8"))
    collection = data["collection"]
    ok = 0
    for concept in data["concepts"]:
        if _store(concept, collection):
            ok += 1
    typer.echo(json.dumps({"status": "PASS", "collection": collection, "loaded": ok, "total": len(data["concepts"])}))


if __name__ == "__main__":
    app()
