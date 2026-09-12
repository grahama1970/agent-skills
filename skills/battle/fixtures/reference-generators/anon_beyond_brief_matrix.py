"""Beyond-brief generator for the anonymization trial.

The brief matrix (anon_brief_matrix.py) is the spec floor. This generator is
the next adversarial rung: representations the brief does NOT enumerate but a
real data-release attacker uses. Each case plants exactly one policy value in
exactly one representation, so a Judge FAIL names the exact leak.

Case families:
- structural positions: JSON object KEY (plain + \\u-escaped), CSV header row,
  late CSV column, deep JSON array, JSON root scalar (string and int), JSONL.
- SQLite schema positions: table identifier carrying the value, trigger body
  literal.
- encoding/transport: UTF-16LE text file, policy value carried in a FILE NAME
  (contents clean).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

PHONE = "5551234567"
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
    yield _bundle(root, "bb-csv-header-cell", NAME,
                  lambda c: (c / "d.csv").write_text(f"id,{NAME},note\n1,2,3\n"),
                  "MAY_REJECT")
    yield _bundle(root, "bb-csv-late-column", NAME,
                  lambda c: (c / "d.csv").write_text(",".join(["c"] * 6) + f"\n1,2,3,4,5,{NAME}\n"),
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
                  "MAY_REJECT")

    # -- SQLite schema positions --
    yield _bundle(root, "bb-sqlite-table-identifier", PHONE,
                  lambda c: _sql_ident(c, PHONE), "MAY_REJECT")
    yield _bundle(root, "bb-sqlite-trigger-literal", PHONE,
                  lambda c: _sql_trigger(c, PHONE), "MAY_REJECT")

    # -- encoding / transport --
    yield _bundle(root, "bb-utf16le-text", NAME, _utf16_text(NAME), "MUST_REJECT")
    yield _bundle(root, "bb-utf16le-bomless-text", NAME, _utf16_bomless_text(NAME), "MUST_REJECT")
    yield _bundle(root, "bb-filename-value", NAME,
                  lambda c: (c / f"{NAME}.txt").write_text("clean contents\n"),
                  "MAY_REJECT")


def _sql_ident(corpus: Path, value: str):
    con = sqlite3.connect(corpus / "d.sqlite")
    con.executescript(f'CREATE TABLE "t_{value}"(x TEXT); INSERT INTO "t_{value}" VALUES(\'safe\');')
    con.commit(); con.close()


def _sql_trigger(corpus: Path, value: str):
    con = sqlite3.connect(corpus / "d.sqlite")
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
