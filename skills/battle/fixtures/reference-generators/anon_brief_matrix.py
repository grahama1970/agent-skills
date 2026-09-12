"""Brief-matrix generator for the anonymization trial.

Yields (case_name, input_dir) covering every 'version' the brief names -- the
four formats x the representations each admits x documented edge cases -- plus
random fuzz. Each input_dir is a complete bundle: policy.json + corpus/. The
planted sensitive value appears in exactly one representation per case, so the
Judge's verdict is exact.
"""
from __future__ import annotations

import json
import random
import sqlite3
import unicodedata
from pathlib import Path

PHONE = "5551234567"
NAME = "Mara Ellison"
ACCENT = unicodedata.normalize("NFC", "Jos\u00e9 Malk\u00e9")


def _bundle(root: Path, name: str, value: str, writer) -> tuple[str, str]:
    d = root / name
    (d / "corpus").mkdir(parents=True, exist_ok=True)
    (d / "policy.json").write_text(json.dumps({
        "version": 1, "protected_values": [],
        "sensitive_values": [{"rule_id": "r", "subject_id": "s", "type": "name", "value": value}],
    }), encoding="utf-8")
    writer(d / "corpus")
    return name, str(d)


def generate(work_dir, params):
    root = Path(work_dir)
    root.mkdir(parents=True, exist_ok=True)
    rng = random.Random(params.get("seed", 1))

    # --- the four formats, base representation ---
    yield _bundle(root, "json-string", NAME, lambda c: (c / "d.json").write_text(json.dumps({"v": NAME})))
    yield _bundle(root, "csv-cell", NAME, lambda c: (c / "d.csv").write_text(f"col\n{NAME}\n"))
    yield _bundle(root, "utf8-text", NAME, lambda c: (c / "d.txt").write_text(f"note: {NAME}\n"))
    yield _bundle(root, "sqlite-text", NAME, lambda c: _sql(c, "TEXT", NAME))

    # --- JSON numeric representations of a phone ---
    yield _bundle(root, "json-integer", PHONE, lambda c: (c / "d.json").write_text(json.dumps({"v": int(PHONE)})))
    yield _bundle(root, "json-float", PHONE, lambda c: (c / "d.json").write_text(json.dumps({"v": float(PHONE)})))
    yield _bundle(root, "json-scientific", "100000000000000000000",
                  lambda c: (c / "d.json").write_text('{"v": 1e20}'))

    # --- SQLite numeric storage classes ---
    yield _bundle(root, "sqlite-integer", PHONE, lambda c: _sql(c, "INTEGER", int(PHONE)))
    yield _bundle(root, "sqlite-real", PHONE, lambda c: _sql(c, "REAL", float(PHONE)))

    # --- Unicode normalization (brief: normalization policy) ---
    yield _bundle(root, "unicode-nfd-json", ACCENT,
                  lambda c: (c / "d.json").write_text(json.dumps({"v": unicodedata.normalize("NFD", ACCENT)})))
    yield _bundle(root, "unicode-nfd-text", ACCENT,
                  lambda c: (c / "d.txt").write_text("who: " + unicodedata.normalize("NFD", ACCENT) + "\n"))

    # --- encoding edge (brief: BOM, multibyte) ---
    yield _bundle(root, "utf8-bom-text", NAME,
                  lambda c: (c / "d.txt").write_bytes(b"\xef\xbb\xbf" + f"note {NAME}".encode("utf-8")))
    yield _bundle(root, "json-uescape", NAME,
                  lambda c: (c / "d.json").write_bytes(b'{"v":"' + NAME.replace(" ", " ").encode().replace(b"M", b"\\u004d") + b'"}'))

    # --- SQLite schema-DDL literal (CHECK) ---
    yield _bundle(root, "sqlite-check-literal", PHONE, lambda c: _sql_check(c, PHONE))

    # --- BEYOND the brief: the full adversarial surface a real attacker uses,
    # none of which the brief enumerates. A hardened pipeline must anonymize or
    # fail-closed on every one; a value surviving in any is a Red win. ---
    yield _bundle(root, "adv-sqlite-blob", NAME, lambda c: _sql_blob(c, NAME))
    yield _bundle(root, "adv-sqlite-view-reconstruction", "Alice", lambda c: _sql_view(c))
    yield _bundle(root, "adv-sqlite-expression-index", "SECRET", lambda c: _sql_exprindex(c))
    yield _bundle(root, "adv-sqlite-computed-default", "SECRET", lambda c: _sql_default(c))
    yield _bundle(root, "adv-sqlite-header-user-version", "123456789", lambda c: _sql_header(c))

    # --- fuzz: random value in a random representation ---
    for i in range(int(params.get("fuzz", 20))):
        v = "".join(rng.choices("0123456789", k=10))
        reps = [
            ("fuzz-json-str", lambda c, v=v: (c / "d.json").write_text(json.dumps({"v": v}))),
            ("fuzz-json-int", lambda c, v=v: (c / "d.json").write_text(json.dumps({"v": int(v)}))),
            ("fuzz-sqlite-int", lambda c, v=v: _sql(c, "INTEGER", int(v))),
            ("fuzz-sqlite-text", lambda c, v=v: _sql(c, "TEXT", v)),
            ("fuzz-csv", lambda c, v=v: (c / "d.csv").write_text(f"c\n{v}\n")),
            ("fuzz-text", lambda c, v=v: (c / "d.txt").write_text(f"n {v}\n")),
        ]
        label, w = rng.choice(reps)
        yield _bundle(root, f"{label}-{i}", v, w)


def _sql(corpus: Path, coltype: str, value):
    con = sqlite3.connect(corpus / "d.sqlite")
    con.execute(f"CREATE TABLE t(id INTEGER PRIMARY KEY, v {coltype})")
    con.execute("INSERT INTO t(v) VALUES(?)", (value,))
    con.commit(); con.close()


def _sql_check(corpus: Path, value: str):
    db = corpus / "d.sqlite"
    if db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    con.executescript(f"CREATE TABLE b(x TEXT, CHECK (x <> '{value}')); INSERT INTO b(x) VALUES('safe');")
    con.commit(); con.close()


def _sql_blob(corpus: Path, value: str):
    db = corpus / "d.sqlite"
    if db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, b BLOB)")
    con.execute("INSERT INTO t(b) VALUES(?)", (value.encode(),))
    con.commit(); con.close()


def _sql_view(corpus: Path):
    db = corpus / "d.sqlite"
    if db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    con.executescript("CREATE TABLE t(a TEXT,b TEXT); INSERT INTO t VALUES('Al','ice');"
                      "CREATE VIEW v AS SELECT a||b AS f FROM t;")
    con.commit(); con.close()


def _sql_exprindex(corpus: Path):
    db = corpus / "d.sqlite"
    if db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    con.executescript("CREATE TABLE t(x TEXT); INSERT INTO t VALUES('clean');"
                      "CREATE INDEX i ON t(char(83,69,67,82,69,84));")
    con.commit(); con.close()


def _sql_default(corpus: Path):
    db = corpus / "d.sqlite"
    if db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    con.executescript("CREATE TABLE t(x TEXT DEFAULT (char(83,69,67,82,69,84)));")
    con.commit(); con.close()


def _sql_header(corpus: Path):
    db = corpus / "d.sqlite"
    if db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    con.executescript("CREATE TABLE h(x TEXT); INSERT INTO h VALUES('safe'); PRAGMA user_version=123456789;")
    con.commit(); con.close()
