"""Regression tests for deterministic taxonomy tag merging."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "ingest_code.py"
sys.path.insert(0, str(MODULE_PATH.parent))
spec = importlib.util.spec_from_file_location("ingest_code", MODULE_PATH)
assert spec and spec.loader
ingest_code = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ingest_code
spec.loader.exec_module(ingest_code)


class _Taxonomy:
    def __init__(self, result) -> None:
        self.result = result

    def extract_taxonomy(self, *args, **kwargs):
        return self.result


class _RaisingTaxonomy:
    def extract_taxonomy(self, *args, **kwargs):
        raise RuntimeError("taxonomy unavailable")


def test_taxonomy_merge_preserves_existing_semantic_tag_order() -> None:
    tags = ingest_code._merge_taxonomy_tags(
        ["codebase", "function", "load_config", "service"],
        ["security"],
        {},
    )

    assert tags[:4] == ["codebase", "function", "load_config", "service"]
    assert tags == ["codebase", "function", "load_config", "service", "security"]
    assert ingest_code._extract_verification_name(tags) == "load_config"


@pytest.mark.parametrize(
    ("existing_tags", "expected_name"),
    [
        (["codebase", "class", "Service"], "Service"),
        (["codebase", "symbol", "method", "Service.run"], "Service.run"),
    ],
)
def test_taxonomy_merge_preserves_class_and_symbol_pairs(
    existing_tags: list[str],
    expected_name: str,
) -> None:
    tags = ingest_code._merge_taxonomy_tags(existing_tags, ["security"], {})

    assert tags[: len(existing_tags)] == existing_tags
    assert ingest_code._extract_verification_name(tags) == expected_name


def test_taxonomy_merge_deduplicates_by_first_occurrence() -> None:
    tags = ingest_code._merge_taxonomy_tags(
        ["codebase", "security", "function", "load_config"],
        ["security", "cwe"],
        {"operational": ["codebase", "cwe", "stable"]},
    )

    assert tags == ["codebase", "security", "function", "load_config", "cwe", "stable"]


def test_collection_mapping_order_does_not_change_output() -> None:
    first = ingest_code._merge_taxonomy_tags(
        ["codebase"],
        [],
        {"z": ["last"], "a": ["first"]},
    )
    second = ingest_code._merge_taxonomy_tags(
        ["codebase"],
        [],
        {"a": ["first"], "z": ["last"]},
    )

    assert first == second == ["codebase", "first", "last"]


def test_bridge_tag_order_is_preserved() -> None:
    tags = ingest_code._merge_taxonomy_tags(
        ["codebase"],
        ["bridge-a", "bridge-b", "bridge-c"],
        {},
    )

    assert tags == ["codebase", "bridge-a", "bridge-b", "bridge-c"]


def test_malformed_taxonomy_values_are_ignored() -> None:
    tags = ingest_code._merge_taxonomy_tags(
        ["codebase", "", 42, " function ", "build"],
        [" security ", "", None, 3],
        {"z": ["", "stable", object()], "a": "operational", "bad": [None]},
    )

    assert tags == ["codebase", "function", "build", "security", "operational", "stable"]
    assert ingest_code._merge_taxonomy_tags(["codebase"], ["security"], ["not", "a", "dict"]) == [
        "codebase",
        "security",
    ]


def test_enrichment_exception_preserves_original_tags() -> None:
    tags = ["codebase", "function", "load_config"]
    item = {"problem": "p", "solution": "s", "tags": list(tags)}

    result = ingest_code.enrich_with_taxonomy([item], _RaisingTaxonomy())

    assert result == [item]
    assert item["tags"] == tags


@pytest.mark.parametrize("taxonomy_result", [None, ["security"], "security"])
def test_non_dictionary_taxonomy_result_preserves_original_tags(taxonomy_result) -> None:
    tags = ["codebase", "function", "load_config"]
    item = {"problem": "p", "solution": "s", "tags": list(tags)}

    ingest_code.enrich_with_taxonomy([item], _Taxonomy(taxonomy_result))

    assert item["tags"] == tags


def test_repeated_enrichment_is_idempotent() -> None:
    item = {"problem": "p", "solution": "s", "tags": ["codebase"]}
    taxonomy = _Taxonomy({
        "bridge_tags": ["security", "codebase"],
        "collection_tags": {"operational": ["stable", "security"]},
    })

    ingest_code.enrich_with_taxonomy([item], taxonomy)
    first = list(item["tags"])
    ingest_code.enrich_with_taxonomy([item], taxonomy)

    assert item["tags"] == first == ["codebase", "security", "stable"]


def test_enriched_lesson_payload_has_stable_tags() -> None:
    item = {
        "problem": "What does load_config do?",
        "solution": "Loads configuration.",
        "tags": ["codebase", "function", "load_config"],
    }
    taxonomy = _Taxonomy({
        "bridge_tags": ["security", "configuration"],
        "collection_tags": {"z": ["runtime"], "a": ["operational", "security"]},
    })

    ingest_code.enrich_with_taxonomy([item], taxonomy)
    document = ingest_code._build_lesson_document(
        item["problem"],
        item["solution"],
        "code",
        item["tags"],
    )

    assert document["tags"] == [
        "codebase",
        "function",
        "load_config",
        "security",
        "configuration",
        "operational",
        "runtime",
    ]
