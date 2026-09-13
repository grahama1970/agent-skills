from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

JUDGE = Path(__file__).resolve().parents[1] / "fixtures/reference-judges/no_data_leak_judge.py"


def _judge(tmp_path: Path, value: int | str) -> dict:
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"sensitive_values": [{"value": value}]}))
    spec = importlib.util.spec_from_file_location("no_data_leak_judge", JUDGE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.judge(tmp_path, {"policy": str(policy), "output_subdir": "corpus"})


def _db(tmp_path: Path) -> Path:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    return corpus / "d.sqlite"


def test_hidden_rowid_numeric_value_fails(tmp_path: Path) -> None:
    con = sqlite3.connect(_db(tmp_path))
    con.execute("CREATE TABLE clean(value TEXT)")
    con.execute("INSERT INTO clean(rowid, value) VALUES (8675309, 'redacted')")
    con.commit(); con.close()

    result = _judge(tmp_path, 8675309)

    assert not result["passed"]
    assert result["violations"] == ["policy value survives in output: '8675309'"]


def test_sqlite_sequence_numeric_value_fails(tmp_path: Path) -> None:
    con = sqlite3.connect(_db(tmp_path))
    con.execute("CREATE TABLE clean(id INTEGER PRIMARY KEY AUTOINCREMENT, value TEXT)")
    con.execute("INSERT INTO clean(id, value) VALUES (4444444, 'redacted')")
    con.commit(); con.close()

    result = _judge(tmp_path, 4444444)

    assert not result["passed"]


def test_quoted_identifier_rowid_value_fails(tmp_path: Path) -> None:
    con = sqlite3.connect(_db(tmp_path))
    con.execute('CREATE TABLE "odd table"(value TEXT)')
    con.execute('INSERT INTO "odd table"(rowid, value) VALUES (2222222, \'redacted\')')
    con.commit(); con.close()

    result = _judge(tmp_path, 2222222)

    assert not result["passed"]


def test_without_rowid_clean_control_passes(tmp_path: Path) -> None:
    con = sqlite3.connect(_db(tmp_path))
    con.execute("CREATE TABLE clean(id INTEGER PRIMARY KEY, value TEXT) WITHOUT ROWID")
    con.execute("INSERT INTO clean(id, value) VALUES (1, 'redacted')")
    con.commit(); con.close()

    assert _judge(tmp_path, 3333333)["passed"]


def test_shadowed_rowid_alias_still_reads_hidden_rowid(tmp_path: Path) -> None:
    con = sqlite3.connect(_db(tmp_path))
    con.execute("CREATE TABLE clean(rowid INTEGER, value TEXT)")
    con.execute("INSERT INTO clean(_rowid_, rowid, value) VALUES (5555555, 1, 'redacted')")
    con.commit(); con.close()

    result = _judge(tmp_path, 5555555)

    assert not result["passed"]


def test_all_shadowed_rowid_aliases_fail_closed(tmp_path: Path) -> None:
    con = sqlite3.connect(_db(tmp_path))
    con.execute("CREATE TABLE clean(rowid INTEGER, _rowid_ INTEGER, oid INTEGER, value TEXT)")
    con.execute("INSERT INTO clean VALUES (1, 2, 3, 'redacted')")
    con.commit(); con.close()

    result = _judge(tmp_path, 9999999)

    assert not result["passed"]
    assert any("scan incomplete:" in v and "rowid aliases are shadowed" in v for v in result["violations"])
