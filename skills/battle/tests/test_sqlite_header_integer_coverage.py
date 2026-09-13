from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

JUDGE = Path(__file__).resolve().parents[1] / "fixtures/reference-judges/no_data_leak_judge.py"

HEADER_FIELDS = (
    (16, 2, 4096),
    (18, 1, 1),
    (19, 1, 1),
    (20, 1, 0),
    (21, 1, 64),
    (22, 1, 32),
    (23, 1, 32),
    (24, 4, 20240224),
    (28, 4, 1),
    (32, 4, 20240232),
    (36, 4, 20240236),
    (40, 4, 20240240),
    (44, 4, 4),
    (48, 4, 20240248),
    (52, 4, 20240252),
    (56, 4, 1),
    (60, 4, 20240260),
    (64, 4, 20240264),
    (68, 4, 20240268),
    (92, 4, 20240292),
    (96, 4, 3045000),
)


def _judge_mod():
    spec = importlib.util.spec_from_file_location("no_data_leak_judge", JUDGE)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _case(tmp_path: Path, offset: int, width: int, encoded: int, policy_value: int):
    root = tmp_path / f"case-{offset}"
    corpus = root / "corpus"
    corpus.mkdir(parents=True)
    db = corpus / "out.sqlite"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE t(x TEXT)")
    con.commit()
    con.close()
    data = bytearray(db.read_bytes())
    data[offset : offset + width] = encoded.to_bytes(width, "big")
    db.write_bytes(data)
    (root / "policy.json").write_text(json.dumps({"sensitive_values": [{"value": policy_value}]}))
    return root


def test_every_documented_sqlite_header_integer_matches_numeric_policy(tmp_path: Path) -> None:
    judge = _judge_mod()
    missed = []
    for offset, width, value in HEADER_FIELDS:
        root = _case(tmp_path, offset, width, value, value)
        result = judge.judge(str(root), {"policy": str(root / "policy.json"), "output_subdir": "corpus"})
        if result["passed"]:
            missed.append((offset, width, value))
    assert missed == []


def test_sqlite_page_size_encoding_one_matches_65536_policy(tmp_path: Path) -> None:
    judge = _judge_mod()
    root = _case(tmp_path, 16, 2, 1, 65536)
    result = judge.judge(str(root), {"policy": str(root / "policy.json"), "output_subdir": "corpus"})
    assert not result["passed"]


def test_sqlite_header_clean_numeric_control_passes(tmp_path: Path) -> None:
    judge = _judge_mod()
    root = _case(tmp_path, 24, 4, 20240224, 99999999)
    result = judge.judge(str(root), {"policy": str(root / "policy.json"), "output_subdir": "corpus"})
    assert result["passed"]
