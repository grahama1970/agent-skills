"""Regression tests for Python code-symbol import scope attribution."""

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
    kind: str = "function",
    name: str,
    start_line: int,
):
    return ingest_code._build_code_symbol_record(
        {
            "kind": kind,
            "name": name,
            "start_line": start_line,
            "end_line": start_line,
            "signature": "treesitter signature",
        },
        source,
        repo,
        "code",
        "repo",
        "branch",
        "commit",
        ingest_code.extract_python_imports(source, repo),
    )


def test_exact_function_includes_module_and_own_imports_only(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "import os\n"
        "\n"
        "def target():\n"
        "    import json\n"
        "    return json.dumps(os.environ)\n"
        "\n"
        "def sibling():\n"
        "    import sys\n"
        "    return sys.version\n",
    )

    record = _record(source, repo, name="target", start_line=3)

    assert record is not None
    assert record.imports == ["json", "os"]


def test_nested_function_includes_enclosing_function_imports(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "import os\n"
        "\n"
        "def outer():\n"
        "    import pathlib\n"
        "    def helper():\n"
        "        import decimal\n"
        "        return decimal.Decimal('1')\n"
        "    return helper\n",
    )

    record = _record(source, repo, name="helper", start_line=5)

    assert record is not None
    assert record.imports == ["decimal", "os", "pathlib"]


def test_method_excludes_class_body_and_sibling_method_imports(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "import os\n"
        "\n"
        "class Service:\n"
        "    import pathlib\n"
        "\n"
        "    def run(self):\n"
        "        import json\n"
        "        return json.dumps({})\n"
        "\n"
        "    def other(self):\n"
        "        import sys\n"
        "        return sys.version\n",
    )

    record = _record(source, repo, name="run", start_line=6)

    assert record is not None
    assert record.imports == ["json", "os"]


def test_class_includes_own_but_not_method_or_nested_class_imports(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "import os\n"
        "\n"
        "class Service:\n"
        "    import pathlib\n"
        "\n"
        "    def run(self):\n"
        "        import json\n"
        "        return json.dumps({})\n"
        "\n"
        "    class Inner:\n"
        "        import decimal\n",
    )

    record = _record(source, repo, kind="class", name="Service", start_line=3)

    assert record is not None
    assert record.imports == ["os", "pathlib"]


def test_exact_relative_imports_keep_repository_normalization(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "pkg/service.py",
        "from .shared import thing\n"
        "\n"
        "def run():\n"
        "    from .local import tool\n"
        "    return tool(thing)\n",
    )

    record = _record(source, repo, name="run", start_line=3)

    assert record is not None
    assert record.imports == [
        "pkg.local",
        "pkg.local.tool",
        "pkg.shared",
        "pkg.shared.thing",
        "thing",
        "tool",
    ]


def test_document_import_payload_and_terms_are_scope_isolated(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "import os\n"
        "\n"
        "def run():\n"
        "    import json\n"
        "    return json.dumps({})\n"
        "\n"
        "def other():\n"
        "    import sys\n"
        "    return sys.version\n",
    )

    record = _record(source, repo, name="run", start_line=3)
    assert record is not None
    document = record.to_document()

    assert document["imports"] == ["json", "os"]
    assert "import:json" in document["lexical_terms"]
    assert "import:os" in document["lexical_terms"]
    assert "import:sys" not in document["lexical_terms"]
    assert "Imports: json, os" in document["solution"]


def test_unmatched_ast_preserves_filewide_import_fallback(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = _write(
        repo,
        "app.py",
        "import os\n"
        "\n"
        "def run():\n"
        "    import json\n"
        "    return json.dumps({})\n"
        "\n"
        "def other():\n"
        "    import sys\n"
        "    return sys.version\n",
    )

    record = _record(source, repo, name="run", start_line=99)

    assert record is not None
    assert record.imports == ["json", "os", "sys"]
