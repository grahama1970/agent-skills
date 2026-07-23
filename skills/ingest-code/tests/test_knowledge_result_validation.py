"""Regression tests for functional-knowledge result validation."""

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


class _EmptyTaxonomy:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def extract_taxonomy(self, text: str, **kwargs):
        self.calls.append(text)
        return {"bridge_tags": [], "collection_tags": {}}


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


def _valid_item(**overrides) -> dict:
    item = {
        "problem": "What does app do?",
        "solution": "Returns one.",
        "tags": ["codebase", "function", "app"],
    }
    item.update(overrides)
    return item


def _install_scan_common(monkeypatch, tmp_path: Path, source: Path, items) -> None:
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.py")
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(ingest_code, "collect_files", lambda *args, **kwargs: [source])
    monkeypatch.setattr(ingest_code, "extract_knowledge", lambda *args, **kwargs: items)


def test_knowledge_validator_accepts_valid_empty_result(tmp_path: Path) -> None:
    assert ingest_code._validate_knowledge_items(tmp_path / "app.py", []) == ()


def test_knowledge_validator_normalizes_valid_item(tmp_path: Path) -> None:
    source = tmp_path / "app.py"
    result = ingest_code._validate_knowledge_items(
        source,
        [{
            "problem": "  What does app do?  ",
            "solution": "\nReturns one.\n",
            "tags": [" codebase ", "function", "codebase", " app "],
        }],
    )

    assert result == ({
        "problem": "What does app do?",
        "solution": "Returns one.",
        "tags": ["codebase", "function", "app"],
    },)


def test_knowledge_validator_preserves_unknown_fields(tmp_path: Path) -> None:
    result = ingest_code._validate_knowledge_items(
        tmp_path / "app.py",
        [_valid_item(confidence=0.7, source="ast")],
    )

    assert result[0]["confidence"] == 0.7
    assert result[0]["source"] == "ast"


def test_knowledge_validator_does_not_mutate_input(tmp_path: Path) -> None:
    item = _valid_item(problem=" p ", tags=[" codebase ", "codebase"])

    result = ingest_code._validate_knowledge_items(tmp_path / "app.py", [item])

    assert result[0]["problem"] == "p"
    assert result[0]["tags"] == ["codebase"]
    assert item["problem"] == " p "
    assert item["tags"] == [" codebase ", "codebase"]


def test_knowledge_validator_rejects_non_array_result(tmp_path: Path) -> None:
    with pytest.raises(ingest_code.KnowledgeItemError) as exc_info:
        ingest_code._validate_knowledge_items(tmp_path / "app.py", {"items": []})

    assert exc_info.value.item_index == -1
    assert exc_info.value.location == "result"


def test_knowledge_validator_rejects_non_object_item(tmp_path: Path) -> None:
    with pytest.raises(ingest_code.KnowledgeItemError) as exc_info:
        ingest_code._validate_knowledge_items(tmp_path / "app.py", ["bad"])

    assert exc_info.value.item_index == 0
    assert exc_info.value.location == "items[0]"


@pytest.mark.parametrize("problem", [None, "", "  ", 42])
def test_knowledge_validator_rejects_missing_or_blank_problem(tmp_path: Path, problem) -> None:
    with pytest.raises(ingest_code.KnowledgeItemError) as exc_info:
        ingest_code._validate_knowledge_items(tmp_path / "app.py", [_valid_item(problem=problem)])

    assert exc_info.value.location == "items[0].problem"


@pytest.mark.parametrize("solution", [None, "", "  ", 42])
def test_knowledge_validator_rejects_missing_or_blank_solution(tmp_path: Path, solution) -> None:
    with pytest.raises(ingest_code.KnowledgeItemError) as exc_info:
        ingest_code._validate_knowledge_items(tmp_path / "app.py", [_valid_item(solution=solution)])

    assert exc_info.value.location == "items[0].solution"


@pytest.mark.parametrize("tags", [None, [], (), "codebase"])
def test_knowledge_validator_rejects_invalid_or_empty_tags(tmp_path: Path, tags) -> None:
    with pytest.raises(ingest_code.KnowledgeItemError) as exc_info:
        ingest_code._validate_knowledge_items(tmp_path / "app.py", [_valid_item(tags=tags)])

    assert exc_info.value.location == "items[0].tags"


@pytest.mark.parametrize("tag", [None, "", " ", 42])
def test_knowledge_validator_rejects_non_string_or_blank_tag(tmp_path: Path, tag) -> None:
    with pytest.raises(ingest_code.KnowledgeItemError) as exc_info:
        ingest_code._validate_knowledge_items(tmp_path / "app.py", [_valid_item(tags=["codebase", tag])])

    assert exc_info.value.location == "items[0].tags[1]"


def test_knowledge_validator_deduplicates_tags_in_order(tmp_path: Path) -> None:
    result = ingest_code._validate_knowledge_items(
        tmp_path / "app.py",
        [_valid_item(tags=["function", "codebase", "function", "app", "codebase"])],
    )

    assert result[0]["tags"] == ["function", "codebase", "app"]


def test_extractor_exception_becomes_knowledge_item_error(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "app.py"
    monkeypatch.setattr(ingest_code, "extract_knowledge", lambda filepath: (_ for _ in ()).throw(ValueError("bad ast")))

    with pytest.raises(ingest_code.KnowledgeItemError) as exc_info:
        ingest_code._extract_validated_knowledge(source)

    assert exc_info.value.filepath == source
    assert exc_info.value.location == "extractor"
    assert "ValueError: bad ast" in str(exc_info.value)


def test_scan_invalid_knowledge_result_stops_before_taxonomy_and_writes(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    repo, source = _source_repo(tmp_path)
    taxonomy = _EmptyTaxonomy()
    calls = {"learn": [], "cwe": [], "edges": [], "treesitter": [], "marker": []}
    _install_scan_common(monkeypatch, tmp_path, source, [_valid_item(), {"problem": "", "solution": "s", "tags": ["t"]}])
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: taxonomy)
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: calls["learn"].append(args) or True)
    monkeypatch.setattr(ingest_code, "scan_file_cwe", lambda *args, **kwargs: calls["cwe"].append(args) or {"cwe_mappings": []})
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: calls["edges"].append(args) or [])
    monkeypatch.setattr(ingest_code, "_extract_configured_scan_roots", lambda path: calls["treesitter"].append(path) or [])
    monkeypatch.setattr(ingest_code, "_write_required_ingest_marker", lambda *args, **kwargs: calls["marker"].append(args))

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(repo, treesitter=True))

    assert exc_info.value.code == 1
    assert taxonomy.calls == []
    assert calls == {"learn": [], "cwe": [], "edges": [], "treesitter": [], "marker": []}
    error = _stderr_json(capsys)
    assert error["error"] == "Functional knowledge result invalid"
    assert error["location"] == "items[1].problem"


def test_scan_dry_run_invalid_result_emits_no_knowledge_preview(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    repo, source = _source_repo(tmp_path)
    _install_scan_common(monkeypatch, tmp_path, source, [_valid_item(), {"bad": True}])

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.scan(**_scan_args(repo, dry_run=True))

    assert exc_info.value.code == 1
    assert "[K]" not in capsys.readouterr().out
    assert not (repo / ".ingest-code.json").exists()


def test_rescan_invalid_late_item_writes_no_knowledge_records(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    files = [repo / "one.py", repo / "two.py"]
    for source in files:
        source.write_text("def app():\n    return 1\n")
    learn_calls = []
    monkeypatch.setattr(ingest_code, "find_memory_skill", lambda: tmp_path / "memory.py")
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: None)
    monkeypatch.setattr(ingest_code, "collect_files", lambda *args, **kwargs: files)
    monkeypatch.setattr(
        ingest_code,
        "extract_knowledge",
        lambda filepath: [_valid_item()] if filepath.name == "one.py" else [{"problem": "", "solution": "s", "tags": ["t"]}],
    )
    monkeypatch.setattr(ingest_code, "_learn", lambda *args, **kwargs: learn_calls.append(args) or True)

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.rescan(**_rescan_args([repo]))

    assert exc_info.value.code == 1
    assert learn_calls == []


def test_rescan_invalid_result_skips_cwe_treesitter_and_markers(monkeypatch, tmp_path: Path) -> None:
    repo, source = _source_repo(tmp_path)
    calls = {"cwe": [], "treesitter": [], "marker": []}
    _install_scan_common(monkeypatch, tmp_path, source, [{"problem": "p", "solution": "s", "tags": []}])
    monkeypatch.setattr(ingest_code, "load_taxonomy_module", lambda: _EmptyTaxonomy())
    monkeypatch.setattr(ingest_code, "scan_file_cwe", lambda *args, **kwargs: calls["cwe"].append(args) or {"cwe_mappings": []})
    monkeypatch.setattr(ingest_code, "_store_treesitter_symbols_for_directory", lambda *args, **kwargs: calls["treesitter"].append(args) or 0)
    monkeypatch.setattr(ingest_code, "_write_required_ingest_marker", lambda *args, **kwargs: calls["marker"].append(args))

    with pytest.raises(SystemExit) as exc_info:
        ingest_code.rescan(**_rescan_args([repo], treesitter=True))

    assert exc_info.value.code == 1
    assert calls == {"cwe": [], "treesitter": [], "marker": []}


def test_scan_and_rescan_write_identically_normalized_items(monkeypatch, tmp_path: Path) -> None:
    repo, source = _source_repo(tmp_path)
    item = _valid_item(problem=" p ", solution=" s ", tags=[" z ", "a", "z"])
    scan_writes: list[tuple[str, str, list[str]]] = []
    rescan_writes: list[tuple[str, str, list[str]]] = []
    _install_scan_common(monkeypatch, tmp_path, source, [item])
    monkeypatch.setenv("INGEST_WORKERS", "1")
    monkeypatch.setattr(ingest_code, "scan_file_cwe", lambda *args, **kwargs: {"cwe_mappings": []})
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "_write_required_ingest_marker", lambda *args, **kwargs: tmp_path / "marker")
    monkeypatch.setattr(ingest_code, "_learn_http", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        ingest_code,
        "_learn",
        lambda _script, problem, solution, _scope, tags: scan_writes.append((problem, solution, list(tags))) or True,
    )

    ingest_code.scan(**_scan_args(repo))

    monkeypatch.setattr(
        ingest_code,
        "_learn",
        lambda _script, problem, solution, _scope, tags: rescan_writes.append((problem, solution, list(tags))) or True,
    )

    ingest_code.rescan(**_rescan_args([repo]))

    assert scan_writes == rescan_writes == [("p", "s", ["z", "a"])]
    assert item["problem"] == " p "
    assert item["tags"] == [" z ", "a", "z"]


def test_valid_empty_result_still_allows_completed_zero_knowledge_marker(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo, source = _source_repo(tmp_path)
    _install_scan_common(monkeypatch, tmp_path, source, [])
    monkeypatch.setattr(ingest_code, "extract_edges", lambda *args, **kwargs: [])
    monkeypatch.setattr(ingest_code, "_learn_http", lambda *args, **kwargs: True)

    ingest_code.scan(**_scan_args(repo))

    status = ingest_code.build_marker_status(repo)
    assert status["status"] == "fresh"
    assert status["knowledge_stored"] == 0


def test_skill_docs_describe_knowledge_result_contract() -> None:
    docs = SKILL_PATH.read_text()

    assert "Functional-knowledge extractors" in docs
    assert "nonblank `problem`" in docs
    assert "status 1" in docs
    assert "zero-knowledge result" in docs
