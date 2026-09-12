"""Beyond-brief generator for the anonymization trial.

The brief matrix (anon_brief_matrix.py) is the spec floor. This generator is
the next adversarial rung: representations the brief does NOT enumerate but a
real data-release attacker uses. Each case plants exactly one policy value in
exactly one representation, so a Judge FAIL names the exact leak.

Case families:
- structural positions: JSON object KEY (plain + \\u-escaped + numeric alias),
  duplicate JSON keys, CSV header row, late/multiline CSV columns, deep JSON
  array, JSON root scalar (string and int), JSONL.
- SQLite schema positions: table/column identifiers, DEFAULT/CHECK literals,
  generated expressions, partial indexes, trigger body literals.
- encoding/transport: UTF-16LE text file, policy value carried in a FILE NAME
  (contents clean), and digit-only aliases in paths/headers.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

PHONE = "5551234567"
FORMATTED_PHONE = "555-123-4567"
NAME = "Mara Ellison"


def _bundle(root: Path, name: str, value: str, writer, expectation: str = "MAY_REJECT") -> tuple[str, str, str]:
    d = root / name
    (d / "corpus").mkdir(parents=True, exist_ok=True)
    (d / "policy.json").write_text(json.dumps({
        "version": 1, "protected_values": [],
        "sensitive_values": [{"rule_id": "r", "subject_id": "s", "type": "name", "value": value}],
    }), encoding="utf-8")
    writer(d / "corpus")
    return name, str(d), expectation


def generate(work_dir, params):
    root = Path(work_dir)
    root.mkdir(parents=True, exist_ok=True)

    # Two-axis expectations (WebGPT roadmap #1): MUST_ACCEPT = valid in-domain
    # input the target must process and judge clean; MUST_REJECT = out-of-domain
    # input the target must safely fail-closed on; MAY_REJECT = spec-interpretation
    # case where anonymize-and-pass or safe rejection are both acceptable.
    yield _bundle(root, "bb-json-object-key", NAME,
                  lambda c: (c / "d.json").write_text(json.dumps({NAME: "x"})),
                  "MAY_REJECT")
    yield _bundle(root, "bb-json-object-key-uescape", NAME,
                  lambda c: (c / "d.json").write_text('{"M\\u0061ra Ellison": "x"}'),
                  "MAY_REJECT")
    yield _bundle(root, "bb-json-object-key-numeric-alias", FORMATTED_PHONE,
                  lambda c: (c / "d.json").write_text(json.dumps({PHONE: "x"})),
                  "MUST_REJECT")
    yield _bundle(root, "bb-json-duplicate-key-sensitive-first", NAME,
                  lambda c: (c / "d.json").write_text('{"who":"Mara Ellison","who":"safe"}\n'),
                  "MUST_REJECT")
    yield _bundle(root, "bb-json-duplicate-key-sensitive-second", NAME,
                  lambda c: (c / "d.json").write_text('{"who":"safe","who":"Mara Ellison"}\n'),
                  "MUST_REJECT")
    yield _bundle(root, "bb-csv-header-cell", NAME,
                  lambda c: (c / "d.csv").write_text(f"id,{NAME},note\n1,2,3\n"),
                  "MAY_REJECT")
    yield _bundle(root, "bb-csv-header-numeric-alias", FORMATTED_PHONE,
                  lambda c: (c / "d.csv").write_text(f"id,{PHONE},note\n1,2,3\n"),
                  "MUST_REJECT")
    yield _bundle(root, "bb-csv-late-column", NAME,
                  lambda c: (c / "d.csv").write_text(",".join(["c"] * 6) + f"\n1,2,3,4,5,{NAME}\n"),
                  "MUST_ACCEPT")
    yield _bundle(root, "bb-csv-multiline-quoted-cell", NAME,
                  lambda c: (c / "d.csv").write_text('id,note\n1,"first line\nMara Ellison"\n'),
                  "MUST_ACCEPT")
    yield _bundle(root, "bb-json-deep-array", NAME,
                  lambda c: (c / "d.json").write_text(json.dumps(["safe", ["nested", ["deep", NAME]]])),
                  "MUST_ACCEPT")
    yield _bundle(root, "bb-json-root-string", NAME,
                  lambda c: (c / "d.json").write_text(json.dumps(NAME)),
                  "MUST_ACCEPT")
    yield _bundle(root, "bb-json-root-int", PHONE,
                  lambda c: (c / "d.json").write_text(PHONE),
                  "MUST_ACCEPT")
    yield _bundle(root, "bb-jsonl-lines", NAME,
                  lambda c: (c / "d.json").write_text('{"a":1}\n{"b":' + json.dumps(NAME) + '}\n{"c":3}\n'),
                  "MUST_REJECT")

    # -- SQLite schema positions --
    yield _bundle(root, "bb-sqlite-table-identifier", PHONE,
                  lambda c: _sql_ident(c, PHONE), "MAY_REJECT")
    yield _bundle(root, "bb-sqlite-column-identifier-numeric-alias", FORMATTED_PHONE,
                  lambda c: _sql_column_ident(c, PHONE), "MUST_REJECT")
    yield _bundle(root, "bb-sqlite-default-numeric-alias", FORMATTED_PHONE,
                  lambda c: _sql_default_literal(c, PHONE), "MUST_REJECT")
    yield _bundle(root, "bb-sqlite-generated-reconstruction", "SECRET",
                  lambda c: _sql_generated(c), "MUST_REJECT")
    yield _bundle(root, "bb-sqlite-partial-index", "SECRET",
                  lambda c: _sql_partial_index(c), "MUST_REJECT")
    yield _bundle(root, "bb-sqlite-trigger-literal", PHONE,
                  lambda c: _sql_trigger(c, PHONE), "MAY_REJECT")

    # -- encoding / transport --
    yield _bundle(root, "bb-utf16le-text", NAME, _utf16_text(NAME), "MUST_REJECT")
    yield _bundle(root, "bb-utf16le-bomless-text", NAME, _utf16_bomless_text(NAME), "MUST_REJECT")
    yield _bundle(root, "bb-filename-value", NAME,
                  lambda c: (c / f"{NAME}.txt").write_text("clean contents\n"),
                  "MAY_REJECT")
    yield _bundle(root, "bb-filename-numeric-alias", FORMATTED_PHONE,
                  lambda c: (c / f"{PHONE}.txt").write_text("clean contents\n"),
                  "MUST_REJECT")


def _sql_ident(corpus: Path, value: str):
    db = corpus / "d.sqlite"
    if db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    con.executescript(f'CREATE TABLE "t_{value}"(x TEXT); INSERT INTO "t_{value}" VALUES(\'safe\');')
    con.commit(); con.close()


def _sql_column_ident(corpus: Path, value: str):
    db = corpus / "d.sqlite"
    if db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    con.executescript(f'CREATE TABLE t("{value}" TEXT); INSERT INTO t VALUES(\'safe\');')
    con.commit(); con.close()


def _sql_default_literal(corpus: Path, value: str):
    db = corpus / "d.sqlite"
    if db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    con.executescript(f"CREATE TABLE t(x TEXT DEFAULT '{value}'); INSERT INTO t(x) VALUES('safe');")
    con.commit(); con.close()


def _sql_generated(corpus: Path):
    db = corpus / "d.sqlite"
    if db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    con.executescript(
        "CREATE TABLE t(a TEXT,b TEXT,g TEXT GENERATED ALWAYS AS (a||b) VIRTUAL);"
        "INSERT INTO t(a,b) VALUES('SEC','RET');")
    con.commit(); con.close()


def _sql_partial_index(corpus: Path):
    db = corpus / "d.sqlite"
    if db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    con.executescript("CREATE TABLE t(x TEXT); INSERT INTO t VALUES('safe'); CREATE INDEX i ON t(x) WHERE x <> 'SECRET';")
    con.commit(); con.close()


def _sql_trigger(corpus: Path, value: str):
    db = corpus / "d.sqlite"
    if db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    con.executescript(
        "CREATE TABLE t(x TEXT); INSERT INTO t VALUES('safe');"
        f"CREATE TRIGGER g AFTER INSERT ON t BEGIN SELECT '{value}'; END;")
    con.commit(); con.close()


def _utf16_text(value: str):
    def w(c: Path):
        (c / "d.txt").write_bytes(b"\xff\xfe" + f"note: {value}\n".encode("utf-16-le"))
    return w


def _utf16_bomless_text(value: str):
    # ASCII-range UTF-16LE without BOM passes strict UTF-8 decode with embedded
    # NULs (battle Red win #18): invisible to naive scanners and to targets
    # that only reject on UnicodeDecodeError.
    def w(c: Path):
        (c / "d.txt").write_bytes(f"note: {value}\n".encode("utf-16-le"))
    return w
