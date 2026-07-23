"""Regression tests for fail-closed taxonomy enrichment."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "ingest_code.py"
SKILL_PATH = MODULE_PATH.parent / "SKILL.md"
sys.path.insert(0, str(MODULE_PATH.parent))
spec = importlib.util.spec_from_file_location("ingest_code", MODULE_PATH)
assert spec and spec.loader
ingest_code = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ingest_code
spec.loader.exec_module(ingest_code)


class _Taxonomy:
    def __init__(self, results) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, dict]] = []

    def extract_taxonomy(self, text: str, **kwargs):
        self.calls.append((text, kwargs))
        if len(self.results) == 1:
            result = self.results[0]
        else:
            result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


def _scan_args(repo: Path, **overrides) -> dict:
    options = {
        "path": repo,
        "glob": [],
        "cwe_only": False,
        "validate": False,
        "treesitter": False,
        "code_index": True,
        "dry_run": False,
        "scope": "code",
        "batch_size": 50,
    }
    options.update(overrides)
    return options


def _rescan_args(repos: list[Path], **overrides) -> dict:
    options = {
        "since": None,
        "validate": False,
        "treesitter": False,
        "code_index": True,
        "verify_embeddings": False,
        "scope": "code",
        "codebase": [str(repo) for repo in repos],
    }
    options.update(overrides)
    return options


def _stderr_json(capsys) -> dict:
    stderr = capsys.readouterr().err.strip().splitlines()
    assert stderr
    return json.loads(stderr[-1])


def _source_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text("def app():\n    return 1\n")
    return repo, source


def _install_scan_common(monkeypatch, tmp_path: Path, source: Path, taxonomy) -> None:
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.py")
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: taxonomy)
    monkeypatch.setattr(ingest_code, "collect_files", lambda *args, **kwargs: [source])
    monkeypatch.setattr(
        ingest_code,
        "extract_knowledge",
        lambda *args, **kwargs: [
            {"problem": "What does app do?", "solution": "Returns one.", "tags": ["codebase", "function", "app"]},
        ],
    )


def test_enrichment_accepts_supported_tag_shapes() -> None:
    item = {"problem": "p", "solution": "s", "tags": ["codebase"]}
    taxonomy = _Taxonomy([{
        "bridge_tags": ("security", "configuration"),
        "collection_tags": {"z": "runtime", "a": ["operational"]},
        "ignored": {"future": True},
    }])

    result = ingest_code.enrich_with_taxonomy([item], taxonomy)

    assert result == [{
        "problem": "p",
        "solution": "s",
        "tags": ["codebase", "security", "configuration", "operational", "runtime"],
    }]
    assert item["tags"] == ["codebase"]
    assert taxonomy.calls == [("s", {"collection": "operational", "fast": True})]


def test_enrichment_rejects_non_dictionary_result() -> None:
    with pytest.raises(ingest_code.TaxonomyEnrichmentError) as exc_info:
        ingest_code.enrich_with_taxonomy(
            [{"problem": "p", "solution": "s", "tags": []}],
            _Taxonomy([["security"]]),
        )

    assert exc_info.value.item_index == 0
    assert "result expected object" in str(exc_info.value)


def test_enrichment_rejects_invalid_bridge_tag_members() -> None:
    with pytest.raises(ingest_code.TaxonomyEnrichmentError) as exc_info:
        ingest_code.enrich_with_taxonomy(
            [{"problem": "p", "solution": "s", "tags": []}],
            _Taxonomy([{"bridge_tags": ["security", 42]}]),
        )

    assert "bridge_tags[1] expected string" in str(exc_info.value)


@pytest.mark.parametrize(
    "taxonomy_result",
    [
        {"collection_tags": ["security"]},
        {"collection_tags": {"operational": ["security", object()]}},
        {"collection_tags": {"operational": 42}},
    ],
)
def test_enrichment_rejects_invalid_collection_tag_shapes(taxonomy_result) -> None:
    with pytest.raises(ingest_code.TaxonomyEnrichmentError):
        ingest_code.enrich_with_taxonomy(
            [{"problem": "p", "solution": "s", "tags": []}],
            _Taxonomy([taxonomy_result]),
        )


def test_enrichment_requires_callable_extract_taxonomy() -> None:
    with pytest.raises(ingest_code.TaxonomyEnrichmentError) as exc_info:
        ingest_code.enrich_with_taxonomy(
            [{"problem": "p", "solution": "s", "tags": []}],
            object(),
        )

    assert exc_info.value.item_index == -1
    assert "no callable extract_taxonomy" in str(exc_info.value)


def test_enrichment_failure_does_not_mutate_prior_items() -> None:
    items = [
        {"problem": "one", "solution": "One.", "tags": ["codebase", "one"]},
        {"problem": "two", "solution": "Two.", "tags": ["codebase", "two"]},
    ]

    with pytest.raises(ingest_code.TaxonomyEnrichmentError):
        ingest_code.enrich_with_taxonomy(
            items,
            _Taxonomy([
                {"bridge_tags": ["security"]},
                {"bridge_tags": [None]},
            ]),
        )

    assert items == [
        {"problem": "one", "solution": "One.", "tags": ["codebase", "one"]},
        {"problem": "two", "solution": "Two.", "tags": ["codebase", "two"]},
    ]


def test_scan_taxonomy_failure_exits_before_memory_and_later_phases(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    repo, source = _source_repo(tmp_path)
    calls = {"learn": [], "cwe": [], "edges": [], "treesitter": [], "marker": []}
    _install_scan_common(monkeypatch, tmp_path, source, _Taxonomy([{"bridge_tags": [42]}]))
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: calls["learn"].append(args) or True)
    monkeypatch.setattr(ingest_code, "scan_file_cwe", lambda *args, **kwargs: calls["cwe"].append(args) or {"cwe_mappings": []})
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: calls["edges"].append(args) or [])
    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", lambda path: calls["treesitter"].append(path) or [])
    monkeypatch.setattr(ingest_code, "_write_required_ingest_marker", lambda *args, **kwargs: calls["marker"].append(args))

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(repo, treesitter=True))

    assert exc_info.value.code == 1
    assert calls == {"learn": [], "cwe": [], "edges": [], "treesitter": [], "marker": []}
    error = _stderr_json(capsys)
    assert error["phase"] == "taxonomy_enrichment"
    assert error["item_index"] == 0


def test_scan_dry_run_taxonomy_failure_writes_nothing(monkeypatch, tmp_path: Path) -> None:
    repo, source = _source_repo(tmp_path)
    calls = {"learn": [], "marker": []}
    _install_scan_common(monkeypatch, tmp_path, source, _Taxonomy([RuntimeError("taxonomy failed")]))
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: calls["learn"].append(args) or True)
    monkeypatch.setattr(ingest_code, "_write_required_ingest_marker", lambda *args, **kwargs: calls["marker"].append(args))

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(repo, dry_run=True))

    assert exc_info.value.code == 1
    assert calls == {"learn": [], "marker": []}
    assert not (repo / ".ingest-code.json").exists()


def test_rescan_applies_taxonomy_enrichment_to_knowledge_writes(monkeypatch, tmp_path: Path) -> None:
    repo, source = _source_repo(tmp_path)
    learned: list[tuple[str, list[str]]] = []
    _install_scan_common(monkeypatch, tmp_path, source, _Taxonomy([{"bridge_tags": ["security"]}]))
    monkeypatch.setattr(ingest_code, "scan_file_cwe", lambda *args, **kwargs: {"cwe_mappings": []})
    monkeypatch.setattr(
        ingest_code,
        "_learn",
        lambda _script, problem, _solution, _scope, tags: learned.append((problem, list(tags))) or True,
    )
    monkeypatch.setattr(ingest_code, "_write_required_ingest_marker", lambda *args, **kwargs: tmp_path / "marker")

    ingest_code.rescan(**_rescan_args([repo]))

    assert learned == [("What does app do?", ["codebase", "function", "app", "security"])]


def test_scan_and_rescan_produce_identical_enriched_tags(monkeypatch, tmp_path: Path) -> None:
    repo, source = _source_repo(tmp_path)
    scan_tags: list[list[str]] = []
    rescan_tags: list[list[str]] = []
    taxonomy_result = {
        "bridge_tags": ["security"],
        "collection_tags": {"operational": ["stable"]},
    }
    _install_scan_common(monkeypatch, tmp_path, source, _Taxonomy([taxonomy_result]))
    monkeypatch.setenv("INGEST_WORKERS", "1")
    monkeypatch.setattr(ingest_code, "scan_file_cwe", lambda *args, **kwargs: {"cwe_mappings": []})
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "_write_required_ingest_marker", lambda *args, **kwargs: tmp_path / "marker")
    monkeypatch.setattr(ingest_code, "_learn", lambda _script, _problem, _solution, _scope, tags: scan_tags.append(list(tags)) or True)
    monkeypatch.setattr(ingest_code, "_learn_http", lambda *args, **kwargs: True)

    ingest_code.scan(**_scan_args(repo))

    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: _Taxonomy([taxonomy_result]))
    monkeypatch.setattr(ingest_code, "_learn", lambda _script, _problem, _solution, _scope, tags: rescan_tags.append(list(tags)) or True)

    ingest_code.rescan(**_rescan_args([repo]))

    assert scan_tags == rescan_tags == [["codebase", "function", "app", "security", "stable"]]


def test_rescan_buffers_all_enrichment_before_first_knowledge_write(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    files = [repo / "one.py", repo / "two.py"]
    for source in files:
        source.write_text("def app():\n    return 1\n")
    learn_calls = []
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.py")
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: _Taxonomy([{"bridge_tags": ["security"]}, {"bridge_tags": [None]}]))
    monkeypatch.setattr(ingest_code, "collect_files", lambda *args, **kwargs: files)
    monkeypatch.setattr(
        ingest_code,
        "extract_knowledge",
        lambda filepath: [{"problem": filepath.name, "solution": "s", "tags": ["codebase"]}],
    )
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: learn_calls.append(args) or True)

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.rescan(**_rescan_args([repo]))

    assert exc_info.value.code == 1
    assert learn_calls == []


def test_rescan_taxonomy_failure_skips_cwe_treesitter_and_marker(monkeypatch, tmp_path: Path) -> None:
    repo, source = _source_repo(tmp_path)
    calls = {"cwe": [], "treesitter": [], "marker": []}
    _install_scan_common(monkeypatch, tmp_path, source, _Taxonomy([{"collection_tags": 42}]))
    monkeypatch.setattr(ingest_code, "scan_file_cwe", lambda *args, **kwargs: calls["cwe"].append(args) or {"cwe_mappings": []})
    monkeypatch.setattr(ingest_code, "_store_treesitter_symbols_for_directory", lambda *args, **kwargs: calls["treesitter"].append(args) or 0)
    monkeypatch.setattr(ingest_code, "_write_required_ingest_marker", lambda *args, **kwargs: calls["marker"].append(args))

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.rescan(**_rescan_args([repo], treesitter=True))

    assert exc_info.value.code == 1
    assert calls == {"cwe": [], "treesitter": [], "marker": []}


def test_missing_taxonomy_module_preserves_unenriched_behavior(monkeypatch, tmp_path: Path) -> None:
    repo, source = _source_repo(tmp_path)
    learned: list[list[str]] = []
    _install_scan_common(monkeypatch, tmp_path, source, None)
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "_write_required_ingest_marker", lambda *args, **kwargs: tmp_path / "marker")
    monkeypatch.setattr(ingest_code, "_learn", lambda _script, _problem, _solution, _scope, tags: learned.append(list(tags)) or True)
    monkeypatch.setattr(ingest_code, "_learn_http", lambda *args, **kwargs: True)

    ingest_code.scan(**_scan_args(repo))

    assert learned == [["codebase", "function", "app"]]


def test_skill_docs_describe_taxonomy_parity_and_failure_boundary() -> None:
    docs = SKILL_PATH.read_text()

    assert "both `scan` and `rescan` enrich" in docs
    assert "status 1" in docs
    assert "completed marker" in docs
    assert "not silently treated as" in docs
    assert "empty enrichment" in docs
