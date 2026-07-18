"""Deterministic contract tests for code-derived technique signatures."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from battle_skill import technique_signature as ts  # noqa: E402


# A realistic Zip Slip exploit against a `from app import import_zip` target.
PARENT_SOURCE = (
    "import tempfile\n"
    "from pathlib import Path\n"
    "from zipfile import ZipFile\n\n"
    "from app import import_zip\n\n"
    "with tempfile.TemporaryDirectory() as tmp:\n"
    "    root = Path(tmp)\n"
    "    upload = root / 'evil.zip'\n"
    "    dest = root / 'imports'\n"
    "    with ZipFile(upload, 'w') as archive:\n"
    "        archive.writestr('../evil.txt', 'pwned')\n"
    "    written = import_zip(str(upload), str(dest))\n"
    "    escaped = Path(tmp) / 'evil.txt'\n"
    "    if escaped.exists():\n"
    "        print('ZIP_SLIP_CONFIRMED written=' + str(written))\n"
)

# Child differs from parent in EXACTLY one dimension: traversal_representation.
# The malicious arcname flips from a `../` relative path to an absolute path.
# This is an oracle_or_parameter_mutation (payload parameter changed).
CHILD_TRAVERSAL_SOURCE = PARENT_SOURCE.replace("'../evil.txt'", "'/tmp/evil.txt'")

# Child differing in two dimensions (app_load_mode + target_call_form): the app
# is loaded via importlib and hit over HTTP rather than a direct function call.
CHILD_CROSSOVER_SOURCE = (
    "import tempfile\n"
    "import importlib.util\n"
    "from pathlib import Path\n"
    "from zipfile import ZipFile\n\n"
    "import httpx\n\n"
    "spec = importlib.util.spec_from_file_location('app', '/srv/app.py')\n"
    "with tempfile.TemporaryDirectory() as tmp:\n"
    "    root = Path(tmp)\n"
    "    upload = root / 'evil.zip'\n"
    "    with ZipFile(upload, 'w') as archive:\n"
    "        archive.writestr('../evil.txt', 'pwned')\n"
    "    resp = httpx.post('http://localhost:8000/api/import-zip', files={'f': upload.read_bytes()})\n"
    "    escaped = Path(tmp) / 'evil.txt'\n"
    "    if escaped.exists():\n"
    "        print('ZIP_SLIP_CONFIRMED status=' + str(resp))\n"
)


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def test_parent_signature_dimensions() -> None:
    sig = ts.technique_signature(PARENT_SOURCE)
    assert sig["schema"] == "battle.technique_signature.v1"
    assert sig["parse_ok"] is True
    dims = sig["dimensions"]
    assert dims["app_load_mode"] == "from_import_app"
    assert dims["archive_entry_construction"] == "zipfile_writestr"
    assert dims["traversal_representation"] == "dotdot_relative"
    assert dims["target_call_form"] == "function_call"
    assert "file_existence" in dims["success_oracle"]
    assert "printed_marker" in dims["success_oracle"]
    assert dims["exception_handling"] == "none"
    assert set(dims) == set(ts.DIMENSIONS)


def test_single_dimension_change_isolated() -> None:
    parent = ts.technique_signature(PARENT_SOURCE)
    child = ts.technique_signature(CHILD_TRAVERSAL_SOURCE)
    p_dims, c_dims = parent["dimensions"], child["dimensions"]
    changed = [d for d in ts.DIMENSIONS if p_dims[d] != c_dims[d]]
    assert changed == ["traversal_representation"]
    assert p_dims["traversal_representation"] == "dotdot_relative"
    assert c_dims["traversal_representation"] == "absolute_path"


def test_delta_passes_for_consistent_operator_and_fails_for_inconsistent() -> None:
    parent = ts.technique_signature(PARENT_SOURCE)
    child = ts.technique_signature(CHILD_TRAVERSAL_SOURCE)

    ok = ts.validate_technique_delta(
        parent_signature=parent,
        child_signature=child,
        mutation_operator="oracle_or_parameter_mutation",
    )
    assert ok["status"] == "PASS"
    assert ok["schema"] == "battle.technique_delta_validation.v1"
    assert ok["novelty_distance"] == 1
    assert ok["changed_dimensions"] == ["traversal_representation"]
    assert ok["operator_consistent"] is True
    assert ok["sha256_differ"] is True

    bad = ts.validate_technique_delta(
        parent_signature=parent,
        child_signature=child,
        mutation_operator="method_replace",
    )
    assert bad["status"] == "FAIL"
    assert bad["operator_consistent"] is False
    assert any("method_replace" in r for r in bad["reasons"])


def test_identical_source_fails_closed() -> None:
    parent = ts.technique_signature(PARENT_SOURCE)
    same = ts.technique_signature(PARENT_SOURCE)
    assert parent["sha256"] == same["sha256"]

    result = ts.validate_technique_delta(
        parent_signature=parent,
        child_signature=same,
        mutation_operator="oracle_or_parameter_mutation",
    )
    assert result["status"] == "FAIL"
    assert result["novelty_distance"] == 0
    assert result["sha256_differ"] is False
    assert any("sha256" in r for r in result["reasons"])
    assert any("novelty_distance=0" in r for r in result["reasons"])


def test_determinism_byte_identical() -> None:
    first = ts.technique_signature(PARENT_SOURCE)
    second = ts.technique_signature(PARENT_SOURCE)
    assert _canonical(first) == _canonical(second)


def test_out_of_vocab_operator_fails_closed() -> None:
    parent = ts.technique_signature(PARENT_SOURCE)
    child = ts.technique_signature(CHILD_TRAVERSAL_SOURCE)
    result = ts.validate_technique_delta(
        parent_signature=parent,
        child_signature=child,
        mutation_operator="totally_made_up_operator",
    )
    assert result["status"] == "FAIL"
    assert result["operator_in_vocabulary"] is False
    assert result["operator_consistent"] is False
    assert any("vocabulary" in r for r in result["reasons"])


def test_crossover_requires_two_changed_dimensions() -> None:
    parent = ts.technique_signature(PARENT_SOURCE)
    child = ts.technique_signature(CHILD_CROSSOVER_SOURCE)
    changed = [
        d
        for d in ts.DIMENSIONS
        if parent["dimensions"][d] != child["dimensions"][d]
    ]
    assert "app_load_mode" in changed
    assert "target_call_form" in changed
    assert len(changed) >= 2

    ok = ts.validate_technique_delta(
        parent_signature=parent,
        child_signature=child,
        mutation_operator="failure_guided_crossover",
    )
    assert ok["status"] == "PASS"
    assert ok["novelty_distance"] >= 2

    # A single-dimension child is NOT a valid crossover (novelty < 2).
    small_child = ts.technique_signature(CHILD_TRAVERSAL_SOURCE)
    not_crossover = ts.validate_technique_delta(
        parent_signature=parent,
        child_signature=small_child,
        mutation_operator="failure_guided_crossover",
    )
    assert not_crossover["status"] == "FAIL"
    assert any("failure_guided_crossover" in r for r in not_crossover["reasons"])
