"""Regression tests for receiver-aware Python parameter enrichment."""

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
):
    return ingest_code._build_code_symbol_record(
        {
            "kind": kind,
            "name": name,
            "start_line": start_line,
            "end_line": end_line,
            "signature": f"{kind} {name}(...): ...",
        },
        source,
        repo,
        "code",
        "repo",
        "branch",
        "commit",
        [],
    )


def test_instance_and_async_methods_drop_first_positional_receiver(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Service:\n"
        "    def run(receiver, value):\n"
        "        return value\n"
        "\n"
        "    async def async_run(self, value):\n"
        "        return value\n",
    )

    run = _record(
        source,
        repo,
        kind="function",
        name="run",
        start_line=2,
        end_line=3,
    )
    async_run = _record(
        source,
        repo,
        kind="function",
        name="async_run",
        start_line=5,
        end_line=6,
    )

    assert run is not None
    assert async_run is not None
    assert run.parameters == ["value"]
    assert async_run.parameters == ["value"]
    assert run.signature == "def run(receiver, value):"


def test_classmethod_drops_first_positional_receiver(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Service:\n"
        "    @classmethod\n"
        "    def build(cls, value):\n"
        "        return value\n",
    )

    record = _record(
        source,
        repo,
        kind="function",
        name="build",
        start_line=2,
        end_line=4,
    )

    assert record is not None
    assert record.parameters == ["value"]


def test_staticmethod_keeps_first_parameter_even_when_named_self(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Service:\n"
        "    @builtins.staticmethod\n"
        "    def util(self, value):\n"
        "        return value\n",
    )

    record = _record(
        source,
        repo,
        kind="function",
        name="util",
        start_line=2,
        end_line=4,
    )

    assert record is not None
    assert record.parameters == ["self", "value"]


def test_top_level_and_nested_functions_keep_literal_self(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "def run(self, value):\n"
        "    return value\n"
        "\n"
        "class Service:\n"
        "    def method(self):\n"
        "        def helper(self, value):\n"
        "            return value\n"
        "        return helper\n",
    )

    run = _record(
        source,
        repo,
        kind="function",
        name="run",
        start_line=1,
        end_line=2,
    )
    helper = _record(
        source,
        repo,
        kind="function",
        name="helper",
        start_line=6,
        end_line=7,
    )

    assert run is not None
    assert helper is not None
    assert run.parameters == ["self", "value"]
    assert helper.parameters == ["self", "value"]


def test_keyword_only_self_and_varargs_are_not_dropped(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Service:\n"
        "    def run(receiver, *args, self, **kwargs):\n"
        "        return args, self, kwargs\n"
        "\n"
        "    def collect(*args):\n"
        "        return args\n",
    )

    run = _record(
        source,
        repo,
        kind="function",
        name="run",
        start_line=2,
        end_line=3,
    )
    collect = _record(
        source,
        repo,
        kind="function",
        name="collect",
        start_line=5,
        end_line=6,
    )

    assert run is not None
    assert collect is not None
    assert run.parameters == ["args", "self", "kwargs"]
    assert collect.parameters == ["args"]


def test_record_parameter_payload_and_lexical_terms_are_receiver_aware(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "class Service:\n"
        "    def run(receiver, value, *, option):\n"
        "        return value, option\n",
    )

    record = _record(
        source,
        repo,
        kind="function",
        name="run",
        start_line=2,
        end_line=3,
    )

    assert record is not None
    assert record.parameters == ["value", "option"]
    document = record.to_document()
    assert document["parameters"] == ["value", "option"]
    assert "Parameters: value, option" in document["solution"]
    assert "param:value" in document["lexical_terms"]
    assert "param:option" in document["lexical_terms"]
    assert "param:receiver" not in document["lexical_terms"]
    assert record.signature == "def run(receiver, value, *, option):"
