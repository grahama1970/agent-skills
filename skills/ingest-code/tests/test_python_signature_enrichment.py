"""Regression tests for exact-AST Python signature canonicalization."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "ingest_code.py"
sys.path.insert(0, str(MODULE_PATH.parent))
spec = importlib.util.spec_from_file_location("ingest_code", MODULE_PATH)
assert spec and spec.loader
ingest_code = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ingest_code
spec.loader.exec_module(ingest_code)


def _write(repo: Path, relative_path: str, content: str) -> Path:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _record(
    source: Path,
    repo: Path,
    *,
    kind: str,
    name: str,
    start_line: int,
    end_line: int,
    signature: str = "",
):
    return ingest_code._build_code_symbol_record(
        {
            "kind": kind,
            "name": name,
            "start_line": start_line,
            "end_line": end_line,
            "signature": signature or f"{kind} {name}(...): ...",
        },
        source,
        repo,
        "code",
        "repo",
        "branch",
        "commit",
        [],
    )


def test_exact_function_signature_overrides_conflicting_treesitter_value(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def run(value: int = 1) -> str:\n"
        "    return str(value)\n",
    )

    record = _record(
        source,
        repo,
        kind="function",
        name="run",
        start_line=1,
        end_line=2,
        signature="stale treesitter signature",
    )

    assert record is not None
    assert record.signature == "def run(value: int=1) -> str:"


def test_exact_async_function_and_class_signatures_are_canonicalized(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Service(Base, metaclass=Meta, **opts):\n"
        "    pass\n"
        "\n"
        "async def run(value: int) -> None:\n"
        "    return None\n",
    )

    cls = _record(
        source,
        repo,
        kind="class",
        name="Service",
        start_line=1,
        end_line=2,
        signature="class Service: ...",
    )
    function = _record(
        source,
        repo,
        kind="function",
        name="run",
        start_line=4,
        end_line=5,
        signature="async stale",
    )

    assert cls is not None
    assert function is not None
    assert cls.signature == "class Service(Base, metaclass=Meta, **opts):"
    assert function.signature == "async def run(value: int) -> None:"


def test_all_argument_kinds_annotations_defaults_and_return_are_rendered(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def run(pos, /, value: int = 1, *args: str, flag: bool, "
        "named='x', **kwargs: object) -> list[str]:\n"
        "    return []\n",
    )

    record = _record(
        source,
        repo,
        kind="function",
        name="run",
        start_line=1,
        end_line=2,
        signature="stale",
    )

    assert record is not None
    assert record.signature == (
        "def run(pos, /, value: int=1, *args: str, flag: bool, "
        "named='x', **kwargs: object) -> list[str]:"
    )


def test_decorated_multiline_declaration_has_one_line_body_free_signature(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "@decorator\n"
        "def run(\n"
        "    value: int,\n"
        "    *,\n"
        "    flag: bool = True,\n"
        ") -> None:\n"
        "    return None\n",
    )

    record = _record(
        source,
        repo,
        kind="function",
        name="run",
        start_line=1,
        end_line=7,
        signature="@decorator def run body",
    )

    assert record is not None
    assert record.signature == "def run(value: int, *, flag: bool=True) -> None:"
    assert "decorator" not in record.signature
    assert "return None" not in record.signature


def test_document_solution_and_payload_use_only_canonical_signature(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def run(value: int) -> str:\n"
        "    return str(value)\n",
    )

    record = _record(
        source,
        repo,
        kind="function",
        name="run",
        start_line=1,
        end_line=2,
        signature="stale treesitter signature",
    )

    assert record is not None
    document = record.to_document()
    assert document["signature"] == "def run(value: int) -> str:"
    assert "Signature: def run(value: int) -> str:" in document["solution"]
    assert "Signature: def run(value: int) -> str:" in document["text"]
    assert "stale treesitter signature" not in document["solution"]
    assert "stale treesitter signature" not in document["text"]


def test_unmatched_ast_preserves_treesitter_signature(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def run(value: int) -> str:\n"
        "    return str(value)\n",
    )

    record = _record(
        source,
        repo,
        kind="function",
        name="run",
        start_line=2,
        end_line=2,
        signature="treesitter signature",
    )

    assert record is not None
    assert record.signature == "treesitter signature"
