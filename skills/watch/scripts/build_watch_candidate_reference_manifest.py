#!/usr/bin/env python3
"""Build candidate-only Watch reference manifests from search/oracle outputs.

This is the first concrete reference-hydration rung after query planning. It
normalizes provider outputs into a reviewable `watch.reference_manifest.v1`
artifact. It does not download images, approve references, embed vectors, write
memory, or promote identity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REFERENCE_MANIFEST_SCHEMA = "watch.reference_manifest.v1"


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, value: Any) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(value, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def stable_id(prefix: str, value: Any) -> str:
    material = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"{prefix}:{hashlib.sha256(material.encode('utf-8')).hexdigest()[:32]}"


def build_manifest(
    plan: dict[str, Any],
    *,
    brave_llm_context: dict[str, Any] | None = None,
    brave_image_search: dict[str, Any] | None = None,
    perplexity_leads: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if plan.get("schema") != "watch.asset_reference_hydration_plan.v1":
        raise ValueError(f"unsupported plan schema: {plan.get('schema')!r}")

    asset_id = str(plan["asset_id"])
    references: list[dict[str, Any]] = []
    query_entities = _entities_from_plan(plan)

    if brave_llm_context:
        references.extend(_references_from_brave_llm_context(asset_id, query_entities, brave_llm_context))
    if brave_image_search:
        references.extend(_references_from_brave_image_search(asset_id, query_entities, brave_image_search))
    if perplexity_leads:
        references.extend(_references_from_perplexity_leads(asset_id, query_entities, perplexity_leads))

    deduped = _dedupe_references(references)
    return {
        "schema": REFERENCE_MANIFEST_SCHEMA,
        "asset_id": asset_id,
        "source_type": "movie_domain_search",
        "status": "REFERENCE_CANDIDATES_COLLECTED" if deduped else "REFERENCE_DISCOVERY_PLANNED",
        "references": deduped,
        "approved_reference_count": 0,
        "embedded_reference_count": 0,
        "scene_truth_claimed": False,
        "identity_promotion_allowed": False,
        "candidate_only": True,
        "approval_required": True,
        "providers": sorted({ref["provider"] for ref in deduped}),
        "provider_policy": {
            "brave_image_search_api": "image candidate discovery only",
            "brave_llm_context": "source/content grounding candidate discovery only",
            "perplexity_image_leads": "image lead discovery only",
        },
        "claim_boundary": (
            "This manifest contains reference candidates only. It does not prove "
            "that any character appears in a Watch segment, and it cannot support "
            "identity until images are downloaded, source-reviewed, approved, "
            "embedded, compared against track crops, and recalled through memory."
        ),
    }


def _entities_from_plan(plan: dict[str, Any]) -> list[dict[str, str]]:
    entities: dict[str, dict[str, str]] = {}
    for query in plan.get("candidate_reference_queries", []):
        entity_id = str(query.get("target_entity_id") or "unknown_entity")
        entities.setdefault(
            entity_id,
            {
                "entity_id": entity_id,
                "actor_name": str(query.get("target_actor_name") or ""),
                "query": str(query.get("query") or ""),
            },
        )
    if not entities:
        entities["unknown_entity"] = {"entity_id": "unknown_entity", "actor_name": "", "query": ""}
    return list(entities.values())


def _primary_entity(query_entities: list[dict[str, str]]) -> dict[str, str]:
    return query_entities[0] if query_entities else {"entity_id": "unknown_entity", "actor_name": "", "query": ""}


def _base_reference(
    *,
    asset_id: str,
    entity: dict[str, str],
    provider: str,
    source_url: str,
    title: str | None,
    snippet: str | None,
    image_url: str | None = None,
    thumbnail_url: str | None = None,
    publisher: str | None = None,
    raw_ref: dict[str, Any] | None = None,
) -> dict[str, Any]:
    material = {
        "asset_id": asset_id,
        "entity_id": entity["entity_id"],
        "provider": provider,
        "source_url": source_url,
        "image_url": image_url,
        "thumbnail_url": thumbnail_url,
        "title": title,
    }
    return {
        "reference_id": stable_id("watch_ref_candidate", material),
        "asset_id": asset_id,
        "entity_id": entity["entity_id"],
        "actor_name": entity.get("actor_name"),
        "provider": provider,
        "source_url": source_url,
        "image_url": image_url,
        "thumbnail_url": thumbnail_url,
        "title": title,
        "snippet": snippet,
        "publisher": publisher,
        "approval_status": "CANDIDATE",
        "download_status": "NOT_DOWNLOADED",
        "embedding_status": "NOT_EMBEDDED",
        "candidate_only": True,
        "approval_required": True,
        "scene_truth_claimed": False,
        "identity_promotion_allowed": False,
        "raw_ref": raw_ref or {},
    }


def _references_from_brave_llm_context(
    asset_id: str,
    query_entities: list[dict[str, str]],
    packet: dict[str, Any],
) -> list[dict[str, Any]]:
    entity = _primary_entity(query_entities)
    refs: list[dict[str, Any]] = []
    generic = ((packet.get("grounding") or {}).get("generic") or [])
    sources = packet.get("sources") or {}
    for item in generic:
        url = str(item.get("url") or "")
        if not url:
            continue
        source_meta = sources.get(url) or {}
        snippets = item.get("snippets") or []
        snippet = "\n".join(str(part) for part in snippets[:3])
        refs.append(
            _base_reference(
                asset_id=asset_id,
                entity=entity,
                provider="brave_llm_context",
                source_url=url,
                title=item.get("title") or source_meta.get("title"),
                snippet=snippet,
                publisher=source_meta.get("hostname"),
                raw_ref={"source_age": source_meta.get("age")},
            )
        )
    return refs


def _references_from_brave_image_search(
    asset_id: str,
    query_entities: list[dict[str, str]],
    packet: dict[str, Any],
) -> list[dict[str, Any]]:
    entity = _primary_entity(query_entities)
    candidates = packet.get("results") or packet.get("items") or []
    refs: list[dict[str, Any]] = []
    for item in candidates:
        image_url = _first_string(item, ["image_url", "image", "url", "original"])
        source_url = _first_string(item, ["source_page_url", "page_url", "source", "webpage", "url"])
        thumbnail_url = _first_string(item, ["thumbnail_url", "thumbnail", "thumb"])
        if not (image_url or source_url):
            continue
        refs.append(
            _base_reference(
                asset_id=asset_id,
                entity=entity,
                provider="brave_image_search_api",
                source_url=source_url or image_url,
                image_url=image_url,
                thumbnail_url=thumbnail_url,
                title=item.get("title"),
                snippet=item.get("description") or item.get("snippet"),
                publisher=item.get("publisher") or item.get("domain"),
                raw_ref={"dimensions": item.get("image_dimensions") or item.get("dimensions")},
            )
        )
    return refs


def _references_from_perplexity_leads(
    asset_id: str,
    query_entities: list[dict[str, str]],
    packet: dict[str, Any],
) -> list[dict[str, Any]]:
    entity = _primary_entity(query_entities)
    refs: list[dict[str, Any]] = []
    for lead in packet.get("leads", []):
        source_url = str(lead.get("url") or "")
        image_urls = [str(url) for url in lead.get("image_urls", []) if url]
        if not source_url and not image_urls:
            continue
        if image_urls:
            for image_url in image_urls:
                refs.append(
                    _base_reference(
                        asset_id=asset_id,
                        entity=entity,
                        provider="perplexity_image_leads",
                        source_url=source_url or image_url,
                        image_url=image_url,
                        thumbnail_url=lead.get("thumbnail_url"),
                        title=lead.get("title"),
                        snippet=lead.get("snippet"),
                        publisher=lead.get("publisher"),
                        raw_ref={"query": lead.get("query")},
                    )
                )
        else:
            refs.append(
                _base_reference(
                    asset_id=asset_id,
                    entity=entity,
                    provider="perplexity_image_leads",
                    source_url=source_url,
                    title=lead.get("title"),
                    snippet=lead.get("snippet"),
                    publisher=lead.get("publisher"),
                    raw_ref={"query": lead.get("query")},
                )
            )
    return refs


def _first_string(item: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, dict):
            nested = _first_string(value, ["url", "src"])
            if nested:
                return nested
    return None


def _dedupe_references(references: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str | None, str | None]] = set()
    deduped: list[dict[str, Any]] = []
    for ref in references:
        key = (ref["provider"], ref.get("source_url"), ref.get("image_url"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ref)
    return deduped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--brave-llm-context", type=Path)
    parser.add_argument("--brave-image-search", type=Path)
    parser.add_argument("--perplexity-leads", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    manifest = build_manifest(
        load_json(args.plan),
        brave_llm_context=load_json(args.brave_llm_context) if args.brave_llm_context else None,
        brave_image_search=load_json(args.brave_image_search) if args.brave_image_search else None,
        perplexity_leads=load_json(args.perplexity_leads) if args.perplexity_leads else None,
    )
    write_json(args.out, manifest)
    print("candidate_reference_manifest_ok", len(manifest["references"]))
    print("approved_reference_count", manifest["approved_reference_count"])
    print("embedded_reference_count", manifest["embedded_reference_count"])
    print("scene_truth_claimed", manifest["scene_truth_claimed"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
