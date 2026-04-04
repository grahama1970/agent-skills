"""CLI for /extract-entities skill.

Thin wrapper around graph_memory.entity_extraction.extract_entities().
All logic lives in graph_memory — this is just the Typer CLI + formatting.

Inputs: Question text via CLI arg or --text flag.
Outputs: JSON EntityExtractionResult to stdout.
Failures: Falls back to regex-only if ArangoDB unavailable.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

# graph_memory is imported lazily inside extract() and check() commands only.
# The resolve() command uses httpx + flashtext directly — no graph_memory needed.

app = typer.Typer(
    name="extract-entities",
    help="Extract control IDs, phrases, and relationships from question text.",
    no_args_is_help=True,
)
console = Console()


def _make_memory_client():
    import httpx

    memory_base_url = os.getenv("MEMORY_API_BASE", "").strip()
    if memory_base_url:
        return httpx.Client(base_url=memory_base_url, timeout=15)

    socket_path = os.getenv("MEMORY_SOCKET", "/run/user/1000/embry/memory.sock")
    transport = httpx.HTTPTransport(uds=socket_path)
    return httpx.Client(transport=transport, base_url="http://localhost", timeout=15)


def _split_tokens(text: str, delimiter: str) -> list[str]:
    mode = delimiter.strip()
    if mode.lower() == "auto":
        return [token for token in re.split(r"[,\s;]+", text) if token]
    if mode.lower() == "nlp":
        return []
    return [token.strip() for token in text.split(mode) if token.strip()]


def _extract_nlp_entities(
    *,
    text: str,
    client,
    collection: str,
    name_field: str,
    label_field: str,
    type_field: str,
    framework_field: str,
    scope: str,
    limit: int,
) -> list[dict]:
    from flashtext import KeywordProcessor

    # 1. Load entity dictionary from ArangoDB collection
    try:
        r = client.post("/list", json={
            "collection": collection,
            "limit": limit,
            "return_fields": [
                "_id",
                "_key",
                name_field,
                label_field,
                type_field,
                framework_field,
                "description",
                "cluster",
                "namespace",
            ],
        })
        docs = r.json().get("documents", [])
    except Exception as e:
        logger.warning(f"Failed to load entities from {collection}: {e}")
        docs = []

    # 2. Build FlashText keyword processor from entity names
    kp = KeywordProcessor(case_sensitive=False)
    entity_map: dict[str, dict] = {}  # keyword -> entity doc

    for doc in docs:
        name = doc.get(name_field, "")
        label = doc.get(label_field, "")
        etype = doc.get(type_field, "")
        framework = doc.get(framework_field, "")
        doc_id = doc.get("_id", "")

        # Add both name and label as keywords (skip short/generic ones)
        for keyword in [name, label]:
            if keyword and len(keyword) > 3 and keyword not in entity_map:
                kp.add_keyword(keyword, keyword)
                entity_map[keyword] = {
                    "id": doc_id,
                    "key": doc.get("_key", ""),
                    "name": name,
                    "label": label,
                    "type": etype,
                    "framework": framework,
                    "description": (doc.get("description") or "")[:100],
                    "cluster": doc.get("cluster", ""),
                    "namespace": doc.get("namespace", ""),
                    "exists": True,
                }

    logger.info(f"Loaded {len(entity_map)} entities from {collection} into FlashText")

    # 3. Extract mentioned entities from input text
    found_keywords = kp.extract_keywords(text, span_info=True)
    entities = []
    seen_ids = set()
    for keyword, start, end in found_keywords:
        entity = entity_map.get(keyword)
        if entity and entity["id"] not in seen_ids:
            entities.append({**entity, "span": [start, end], "mention": text[start:end]})
            seen_ids.add(entity["id"])

    # 3b. RapidFuzz fallback: if FlashText found nothing, try fuzzy matching
    if len(entities) == 0:
        from rapidfuzz import fuzz, process as rfprocess

        # Extract candidate words from text (skip stop words)
        stop = {
            "the", "and", "show", "me", "all", "its", "click", "on", "related",
            "nodes", "what", "how", "does", "is", "are", "to", "of", "in", "a", "an",
        }
        words = [w for w in text.lower().replace(",", " ").replace(".", " ").split() if w not in stop and len(w) > 2]

        # Try each word against all entity names
        all_names = list(entity_map.keys())
        for word in words:
            matches = rfprocess.extract(word, all_names, scorer=fuzz.ratio, limit=3, score_cutoff=70)
            for match_name, score, _ in matches:
                entity = entity_map.get(match_name)
                if entity and entity["id"] not in seen_ids:
                    entities.append({
                        **entity,
                        "span": [0, 0],
                        "mention": word,
                        "fuzzy_score": score,
                        "fuzzy_match": match_name,
                    })
                    seen_ids.add(entity["id"])
                    break  # One fuzzy match per word
        if entities:
            logger.info(f"RapidFuzz fallback found {len(entities)} entities")

    # 4. Enrich with /recall context for each entity
    for entity in entities:
        try:
            recall_q = f"{entity['name']} {entity['type']} {entity.get('cluster', '')}"
            r = client.post("/recall", json={
                "q": recall_q,
                "k": 2,
                **({"scope": scope} if scope else {}),
            })
            items = r.json().get("items", [])
            if items:
                entity["recall_context"] = items[0].get("solution", items[0].get("problem", ""))[:200]
        except Exception:
            pass

    return entities


def _lookup_token_by_filter(
    *,
    client,
    collection: str,
    token: str,
    name_field: str,
    label_field: str,
    type_field: str,
    framework_field: str,
    limit: int,
) -> dict | None:
    """Look up a single token by exact filter match (control_id or name/label fallback).

    First tries ``filters: {"control_id": token}`` — the canonical lookup for
    sparta_controls. Falls back to a ``q``-based search with name/label exact
    match for other collections.
    """
    # Primary: exact filter on control_id (canonical for sparta_controls)
    try:
        r = client.post("/list", json={
            "collection": collection,
            "limit": 1,
            "filters": {"control_id": token},
            "return_fields": ["control_id", "name", "source_framework"],
        })
        docs = r.json().get("documents", [])
        if docs:
            doc = docs[0]
            return {
                "id": doc.get("_id", doc.get("control_id", token)),
                "name": doc.get("name", doc.get(name_field, token)),
                "label": doc.get("control_id", doc.get(label_field, "")),
                "framework": doc.get("source_framework", doc.get(framework_field, "")),
                "type": doc.get(type_field, ""),
                "exists": True,
            }
    except Exception as e:
        logger.warning(f"filter lookup failed for '{token}' in {collection}: {e}")

    # Fallback: q-based search with name/label exact match
    try:
        r = client.post("/list", json={
            "collection": collection,
            "q": token,
            "limit": limit,
            "return_fields": ["_id", "_key", name_field, label_field, type_field, framework_field],
        })
        docs = r.json().get("documents", [])
    except Exception as e:
        logger.warning(f"Failed to lookup token '{token}' in {collection}: {e}")
        docs = []

    token_lc = token.lower()
    doc = None
    for candidate in docs:
        name_val = str(candidate.get(name_field, "")).strip()
        label_val = str(candidate.get(label_field, "")).strip()
        if name_val.lower() == token_lc or label_val.lower() == token_lc:
            doc = candidate
            break
    if not doc and docs:
        doc = docs[0]

    if doc:
        return {
            "id": doc.get("_id", ""),
            "name": doc.get(name_field, ""),
            "label": doc.get(label_field, ""),
            "framework": doc.get(framework_field, ""),
            "type": doc.get(type_field, ""),
            "exists": True,
        }
    return None


def _extract_delimited_entities(
    *,
    text: str,
    client,
    collection: str,
    name_field: str,
    label_field: str,
    type_field: str,
    framework_field: str,
    delimiter: str,
    limit: int,
) -> list[dict]:
    tokens = _split_tokens(text, delimiter)
    entities = []

    for token in tokens:
        hit = _lookup_token_by_filter(
            client=client,
            collection=collection,
            token=token,
            name_field=name_field,
            label_field=label_field,
            type_field=type_field,
            framework_field=framework_field,
            limit=limit,
        )
        if hit:
            entities.append({"token": token, **hit})
        else:
            entities.append({
                "token": token,
                "id": "",
                "name": token,
                "label": "",
                "framework": "",
                "type": "",
                "exists": False,
            })

    return entities


@app.command()
def extract(
    text: str = typer.Argument(..., help="Question or claim text to extract entities from"),
    taxonomy: bool = typer.Option(False, "--taxonomy", "-t", help="Include taxonomy bridge attributes"),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress Rich formatting"),
) -> None:
    """Extract entities from question text."""
    from graph_memory.entity_extraction import extract_entities

    result = extract_entities(text, include_taxonomy=taxonomy)

    if json_output or quiet:
        # Merge to_dict() (serializable fields) with agent_view() (grounding_ok, warnings, headline)
        output = result.to_dict()
        if hasattr(result, "agent_view"):
            output.update(result.agent_view() or {})
        print(json.dumps(output, indent=2, default=str))
        return

    # Rich formatted output
    console.print(f"\n[bold]Entity Extraction[/]")
    console.print(f"[dim]Question:[/] {text[:100]}")
    console.print()

    if result.control_ids:
        console.print(f"[cyan]Regex control IDs:[/] {', '.join(result.control_ids)}")
    if result.phrase_controls:
        console.print(f"[cyan]Phrase-discovered:[/] {', '.join(result.phrase_controls)}")
    if result.phrases:
        console.print(f"[cyan]Domain phrases:[/] {', '.join(result.phrases)}")

    console.print(f"\n[bold]All control IDs ({len(result.all_control_ids)}):[/] {', '.join(result.all_control_ids)}")

    if result.control_metadata:
        console.print()
        table = Table(title="Control Metadata")
        table.add_column("Control ID", style="cyan")
        table.add_column("Name")
        table.add_column("Framework", style="green")
        table.add_column("Domain")
        for c in result.control_metadata:
            table.add_row(
                c.get("control_id", ""),
                str(c.get("name", ""))[:40],
                c.get("framework", ""),
                c.get("domain", ""),
            )
        console.print(table)

    if result.related_pairs:
        console.print()
        console.print(f"[bold green]Related pairs ({len(result.related_pairs)}):[/]")
        for pair in result.related_pairs[:10]:
            console.print(f"  {pair['source']} --[{pair.get('method', '?')}]--> {pair['target']}")
    elif len(result.all_control_ids) > 1:
        console.print()
        console.print("[bold red]No relationship edges found between controls[/]")
        console.print("[dim]These controls may not be in the same SPARTA technique[/]")

    if result.taxonomy_tags:
        console.print()
        console.print(f"[bold]Taxonomy tags:[/]")
        for collection, tags in result.taxonomy_tags.items():
            if tags:
                console.print(f"  {collection}: {', '.join(tags)}")

    # Summary verdict
    console.print()
    if result.all_control_ids and result.related_pairs:
        console.print("[bold green]Coherent:[/] Entities share technique relationships")
    elif result.all_control_ids and not result.related_pairs and len(result.all_control_ids) > 1:
        console.print("[bold yellow]Incoherent:[/] Entities exist but no shared technique — may need decomposition")
    elif result.all_control_ids:
        console.print("[bold green]Single entity:[/] Coherent by definition")
    else:
        console.print("[bold red]No entities found:[/] Question may be off-topic or too vague")


@app.command()
def check(
    text: str = typer.Argument(..., help="Quick coherence check — are all entities in the same technique?"),
) -> None:
    """Quick boolean: are extracted entities coherent (same technique)?"""
    from graph_memory.entity_extraction import extract_entities

    result = extract_entities(text)

    coherent = (
        len(result.all_control_ids) <= 1
        or len(result.related_pairs) > 0
    )

    output = {
        "coherent": coherent,
        "control_count": len(result.all_control_ids),
        "control_ids": result.all_control_ids,
        "related_pairs": len(result.related_pairs),
        "phrases": result.phrases,
    }

    if not coherent:
        output["reason"] = f"Controls {result.all_control_ids} have no shared relationship edges"

    print(json.dumps(output, indent=2))


@app.command()
def resolve(
    text: str = typer.Argument(..., help="Text to extract entities from"),
    collection: str = typer.Option("binary_features", "--collection", "-c", help="ArangoDB collection to match against"),
    name_field: str = typer.Option("name", "--name-field", help="Field containing entity names"),
    label_field: str = typer.Option("label", "--label-field", help="Field containing display labels"),
    type_field: str = typer.Option("node_type", "--type-field", help="Field containing entity type"),
    framework_field: str = typer.Option("framework", "--framework-field", help="Field containing framework"),
    delimiter: str = typer.Option("nlp", "--delimiter", "-d", help="Entity extraction mode: nlp, auto, or custom delimiter character(s)"),
    scope: str = typer.Option("", "--scope", "-s", help="Scope filter for /recall"),
    json_output: bool = typer.Option(True, "--json", help="Output JSON"),
    limit: int = typer.Option(500, "--limit", help="Max entities to load for FlashText dictionary"),
) -> None:
    """Collection-agnostic entity extraction via FlashText + /memory recall.

    Loads entity names from any ArangoDB collection, builds a FlashText keyword
    processor, extracts mentions from the input text, then enriches with /recall
    context. Zero LLM cost.

    Used by all ux-lab chat wells for entity grounding before intent routing.
    """
    client = _make_memory_client()

    if delimiter.strip().lower() == "nlp":
        entities = _extract_nlp_entities(
            text=text,
            client=client,
            collection=collection,
            name_field=name_field,
            label_field=label_field,
            type_field=type_field,
            framework_field=framework_field,
            scope=scope,
            limit=limit,
        )
    else:
        entities = _extract_delimited_entities(
            text=text,
            client=client,
            collection=collection,
            name_field=name_field,
            label_field=label_field,
            type_field=type_field,
            framework_field=framework_field,
            delimiter=delimiter,
            limit=limit,
        )

    # 5. Output
    result = {
        "text": text,
        "collection": collection,
        "delimiter": delimiter,
        "entity_count": len(entities),
        "entities": entities,
        "entity_names": [e.get("name", "") for e in entities],
        "entity_ids": [e.get("id", "") for e in entities if e.get("id")],
    }

    client.close()
    print(json.dumps(result, indent=2, default=str))


def _run_default_mode() -> None:
    """Default stdin mode: invoked without a subcommand.

    Reads text from stdin, then:
    - If ``--delimiter`` is present: split tokens and lookup each via /list filters.
    - Otherwise: use the existing NLP extraction path (graph_memory).

    Flags:
      --delimiter <mode>    auto | custom string | omit for NLP
      --collection <name>   ArangoDB collection (default: sparta_controls)
      --name-field <field>  name field (default: name)
      --label-field <field> label field (default: control_id)
      --framework-field <f> framework field (default: source_framework)
      --type-field <field>  type field (default: node_type)
      --limit <n>           max docs for NLP dictionary (default: 500)
      --scope <s>           scope filter for /recall (NLP mode only)
    """
    # Use typer-style argument parsing for the default stdin mode
    default_app = typer.Typer()

    @default_app.command()
    def _default_cmd(
        delimiter: str = typer.Option(None, "--delimiter", "-d", help="Entity extraction mode: auto, custom string, or omit for NLP"),
        collection: str = typer.Option("sparta_controls", "--collection", "-c", help="ArangoDB collection"),
        name_field: str = typer.Option("name", "--name-field", help="Field containing entity names"),
        label_field: str = typer.Option("control_id", "--label-field", help="Field containing display labels"),
        framework_field: str = typer.Option("source_framework", "--framework-field", help="Field containing framework"),
        type_field: str = typer.Option("node_type", "--type-field", help="Field containing entity type"),
        limit: int = typer.Option(500, "--limit", help="Max entities to load for FlashText dictionary"),
        scope: str = typer.Option("", "--scope", help="Scope filter for /recall"),
    ) -> None:
        text = sys.stdin.read().strip()
        if not text:
            print(json.dumps({"error": "no input text", "entities": [], "entity_count": 0}))
            return

        client = _make_memory_client()

        if delimiter is not None:
            entities = _extract_delimited_entities(
                text=text,
                client=client,
                collection=collection,
                name_field=name_field,
                label_field=label_field,
                type_field=type_field,
                framework_field=framework_field,
                delimiter=delimiter,
                limit=limit,
            )
        else:
            entities = _extract_nlp_entities(
                text=text,
                client=client,
                collection=collection,
                name_field=name_field,
                label_field=label_field,
                type_field=type_field,
                framework_field=framework_field,
                scope=scope,
                limit=limit,
            )

        result = {
            "text": text,
            "collection": collection,
            "delimiter": delimiter,
            "entity_count": len(entities),
            "entities": entities,
            "entity_names": [e.get("name", "") for e in entities],
            "entity_ids": [e.get("id", "") for e in entities if e.get("id")],
        }
        client.close()
        print(json.dumps(result, indent=2, default=str))

    default_app()


# Known Typer subcommands — anything else (or no args besides flags) goes to default stdin mode.
_TYPER_SUBCOMMANDS = {"extract", "check", "resolve"}


if __name__ == "__main__":
    # If the first non-flag argument is a known subcommand, delegate to Typer.
    # Otherwise, run the default stdin mode.
    positional_args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if positional_args and positional_args[0] in _TYPER_SUBCOMMANDS:
        app()
    else:
        _run_default_mode()
