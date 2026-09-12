from __future__ import annotations

import base64
import importlib.util
import json
import sqlite3
from pathlib import Path


HERE = Path(__file__).resolve().parent
JUDGE = HERE.parent / "fixtures/reference-judges/no_data_leak_judge.py"


def _judge():
    spec = importlib.util.spec_from_file_location("no_data_leak_judge", JUDGE)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _policy(root: Path, value: str = "Mara Ellison") -> Path:
    p = root / "policy.json"
    p.write_text(json.dumps({"sensitive_values": [{"value": value}]}), encoding="utf-8")
    return p


def test_base64_and_hex_detection_are_opt_in(tmp_path: Path) -> None:
    out = tmp_path / "out"
    (out / "corpus").mkdir(parents=True)
    policy = _policy(out)
    encoded = base64.b64encode(b"Mara Ellison").decode("ascii")
    hexed = b"Mara Ellison".hex()
    (out / "corpus" / "d.json").write_text(json.dumps({"b64": encoded, "hex": hexed}), encoding="utf-8")

    mod = _judge()
    plain = mod.judge(str(out), {"policy": str(policy), "output_subdir": "corpus"})
    profiled = mod.judge(str(out), {"policy": str(policy), "output_subdir": "corpus", "interpretation_profile": {"decoders": ["base64", "hex"]}})

    assert plain["passed"] is True
    assert profiled["passed"] is False
    assert "Mara Ellison" in profiled["violations"][0]


def test_record_local_reconstruction_is_opt_in_for_json_csv_and_sqlite(tmp_path: Path) -> None:
    out = tmp_path / "out"
    corpus = out / "corpus"
    corpus.mkdir(parents=True)
    policy = _policy(out, "5551234567")
    (corpus / "d.json").write_text(json.dumps({"area": "555", "prefix": "123", "line": "4567"}), encoding="utf-8")
    (corpus / "d.csv").write_text("a,b,c\n555,123,4567\n", encoding="utf-8")
    db = corpus / "d.sqlite"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE t(a TEXT,b TEXT,c TEXT)")
    con.execute("INSERT INTO t VALUES('555','123','4567')")
    con.commit(); con.close()

    mod = _judge()
    plain = mod.judge(str(out), {"policy": str(policy), "output_subdir": "corpus"})
    profiled = mod.judge(str(out), {"policy": str(policy), "output_subdir": "corpus", "interpretation_profile": {"record_local_reconstruction": True}})

    assert plain["passed"] is True
    assert profiled["passed"] is False
    assert "5551234567" in profiled["violations"][0]
