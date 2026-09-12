from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

JUDGE = Path(__file__).resolve().parents[1] / "fixtures/reference-judges/no_data_leak_judge.py"


def _judge(tmp_path: Path, value: str, *, max_scan_bytes: int | None = None) -> dict:
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"sensitive_values": [{"value": value}]}))
    spec = importlib.util.spec_from_file_location("no_data_leak_judge", JUDGE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    params = {"policy": str(policy), "output_subdir": "corpus"}
    if max_scan_bytes is not None:
        params["max_scan_bytes"] = max_scan_bytes
    return mod.judge(tmp_path, params)


def _db(tmp_path: Path) -> Path:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    return corpus / "d.sqlite"


def test_sqlite_blob_cell_raw_text_fails(tmp_path: Path) -> None:
    secret = "B17-BLOB-secret"
    con = sqlite3.connect(_db(tmp_path))
    con.execute("CREATE TABLE clean(public TEXT, payload BLOB)")
    con.execute("INSERT INTO clean VALUES (?, ?)", ("redacted", secret.encode()))
    con.commit(); con.close()

    result = _judge(tmp_path, secret)

    assert not result["passed"]
    assert result["violations"] == [f"policy value survives in output: '{secret}'"]


def test_sqlite_released_tail_bytes_fail_even_when_cells_are_clean(tmp_path: Path) -> None:
    secret = "B17-TAIL-secret"
    db = _db(tmp_path)
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE clean(value TEXT)")
    con.execute("INSERT INTO clean VALUES ('redacted')")
    con.commit(); con.close()
    with db.open("ab") as f:
        f.write(b"\0" + secret.encode() + b"\0")

    result = _judge(tmp_path, secret)

    assert not result["passed"]


def test_sqlite_raw_scan_uses_frozen_text_decoders(tmp_path: Path) -> None:
    secret = "B17-UTF16-secret"
    db = _db(tmp_path)
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE clean(value TEXT)")
    con.execute("INSERT INTO clean VALUES ('redacted')")
    con.commit(); con.close()
    with db.open("ab") as f:
        f.write(secret.encode("utf-16-le"))

    result = _judge(tmp_path, secret)

    assert not result["passed"]


def test_clean_sqlite_control_passes(tmp_path: Path) -> None:
    con = sqlite3.connect(_db(tmp_path))
    con.execute("CREATE TABLE clean(value TEXT, payload BLOB)")
    con.execute("INSERT INTO clean VALUES (?, ?)", ("redacted", b"public bytes"))
    con.commit(); con.close()

    assert _judge(tmp_path, "B17-absent-secret")["passed"]


def test_sqlite_scan_limit_fails_closed(tmp_path: Path) -> None:
    con = sqlite3.connect(_db(tmp_path))
    con.execute("CREATE TABLE clean(value TEXT)")
    con.execute("INSERT INTO clean VALUES ('redacted')")
    con.commit(); con.close()

    result = _judge(tmp_path, "B17-absent-secret", max_scan_bytes=1)

    assert not result["passed"]
    assert any("scan incomplete:" in v and "scan limit exceeded" in v for v in result["violations"])
