"""Functional-judge tests: useful-transformation invariant both directions."""
from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
JUDGE = str(HERE.parent / "fixtures" / "reference-judges" / "functional_anonymize_judge.py")

_spec = importlib.util.spec_from_file_location("functional_judge", JUDGE)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def _case(tmp_path: Path, files: dict, out_files: dict | None = None, write_report: bool = True):
    inp, out = tmp_path / "in", tmp_path / "out"
    (inp / "corpus").mkdir(parents=True)
    (out / "corpus").mkdir(parents=True)
    (tmp_path / "policy.json").write_text(json.dumps({
        "sensitive_values": [
            {"rule_id": "r", "subject_id": "s", "type": "name", "value": "Mara Ellison"},
            {"rule_id": "p", "subject_id": "s2", "type": "phone", "value": "5551234567"},
        ]}))
    for rel, content in files.items():
        p = inp / "corpus" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content if isinstance(content, bytes) else content.encode())
    for rel, content in (out_files if out_files is not None else files).items():
        p = out / "corpus" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content if isinstance(content, bytes) else content.encode())
    if write_report:
        (out / "report.json").parent.mkdir(parents=True, exist_ok=True)
        (out / "report.json").write_text(json.dumps({"status": "ready"}))
    params = {"policy": str(tmp_path / "policy.json"),
              "output_subdir": "corpus", "input_dir": str(inp)}
    return mod.judge(str(out), params)


def test_golden_path_all_formats(tmp_path):
    r = _case(tmp_path, {
        "a.txt": "note: Mara Ellison called 5551234567 twice\n",
        "b.json": json.dumps({"name": "Mara Ellison", "phone": 5551234567, "ok": 42}),
        "c.csv": "id,name,phone\n1,Mara Ellison,5551234567\n",
    }, out_files={
        "a.txt": "note: Person-AAA called 555-ONE twice\n",
        "b.json": json.dumps({"name": "Person-AAA", "phone": "555-ONE", "ok": 42}),
        "c.csv": "id,name,phone\n1,Person-AAA,555-ONE\n",
    })
    assert r["passed"] is True, r["violations"]
    assert r["evidence"]["bindings"]["Mara Ellison"] == "Person-AAA"


def test_empty_output_fails(tmp_path):
    r = _case(tmp_path, {"a.txt": "note: Mara Ellison\n"}, out_files={})
    assert r["passed"] is False
    assert any("inventory-mismatch" in v for v in r["violations"])


def test_modified_literal_fails(tmp_path):
    r = _case(tmp_path, {"a.txt": "note: Mara Ellison ok\n"},
              out_files={"a.txt": "NOTE CHANGED: Person-AAA ok\n"})
    assert r["passed"] is False
    assert any("literal segment" in v for v in r["violations"])


def test_empty_replacement_fails(tmp_path):
    r = _case(tmp_path, {"a.txt": "x Mara Ellison y\n"},
              out_files={"a.txt": "x  y\n"})
    assert r["passed"] is False
    assert any("empty, blank, or non-string replacement" in v for v in r["violations"])


def test_collapsed_identities_fail(tmp_path):
    # two distinct same-type values sharing one replacement
    (tmp_path / "policy.json").write_text(json.dumps({"sensitive_values": [
        {"type": "name", "value": "Ada"},
        {"type": "name", "value": "Bob"}]}))
    inp, out = tmp_path / "in" / "corpus", tmp_path / "out" / "corpus"
    inp.mkdir(parents=True)
    out.mkdir(parents=True)
    (inp / "a.txt").write_text("Ada and Bob\n")
    (out / "a.txt").write_text("Zed and Zed\n")
    (tmp_path / "out" / "report.json").write_text(json.dumps({"status": "ready"}))
    r = mod.judge(str(tmp_path / "out"), {"policy": str(tmp_path / "policy.json"),
                                          "output_subdir": "corpus",
                                          "input_dir": str(tmp_path / "in")})
    assert r["passed"] is False
    assert any("collapsed-identities" in v for v in r["violations"])


def test_inconsistent_replacement_fails(tmp_path):
    r = _case(tmp_path, {"a.txt": "Mara Ellison then Mara Ellison\n"},
              out_files={"a.txt": "Person-AAA then Person-BBB\n"})
    assert r["passed"] is False
    assert any("inconsistent replacement" in v for v in r["violations"])


def test_json_structure_damage_fails(tmp_path):
    r = _case(tmp_path, {"b.json": json.dumps({"a": [1, "Mara Ellison", 3], "k": "v"})},
              out_files={"b.json": json.dumps({"a": [1, 3], "k": "v"})})
    assert r["passed"] is False
    assert any("array length" in v for v in r["violations"])


def test_sqlite_row_drop_fails(tmp_path):
    def mk(path: Path, drop: bool):
        path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(path)
        con.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, v TEXT)")
        con.execute("INSERT INTO t(v) VALUES ('Mara Ellison')")
        con.execute("INSERT INTO t(v) VALUES ('other')")
        if drop:
            con.execute("DELETE FROM t WHERE v='other'")
        con.commit()
        con.close()
    inp, out = tmp_path / "in" / "corpus", tmp_path / "out" / "corpus"
    mk(inp / "d.sqlite", drop=False)
    mk(out / "d.sqlite", drop=True)
    (tmp_path / "out" / "report.json").write_text(json.dumps({"status": "ready"}))
    (tmp_path / "policy.json").write_text(json.dumps({"sensitive_values": [
        {"type": "name", "value": "Mara Ellison"}]}))
    r = mod.judge(str(tmp_path / "out"), {"policy": str(tmp_path / "policy.json"),
                                          "output_subdir": "corpus",
                                          "input_dir": str(tmp_path / "in")})
    assert r["passed"] is False
    assert any("row count changed" in v for v in r["violations"])


def test_alias_convergence_allowed_and_cross_subject_collision_fails(tmp_path):
    (tmp_path / "policy.json").write_text(json.dumps({"sensitive_values": [
        {"subject_id": "s1", "type": "name", "value": "Ada"},
        {"subject_id": "s1", "type": "name", "value": "Adeline"},
        {"subject_id": "s2", "type": "name", "value": "Bob"}]}))
    inp, out = tmp_path / "in" / "corpus", tmp_path / "out" / "corpus"
    inp.mkdir(parents=True)
    out.mkdir(parents=True)
    (inp / "a.txt").write_text("Ada, Adeline, Bob\n")
    (tmp_path / "out" / "report.json").write_text(json.dumps({"status": "ready"}))
    (out / "a.txt").write_text("Zed, Zed, Quin\n")  # same-subject aliases converge; other subject gets its own
    r = mod.judge(str(tmp_path / "out"), {"policy": str(tmp_path / "policy.json"),
                                          "output_subdir": "corpus",
                                          "input_dir": str(tmp_path / "in")})
    assert r["passed"] is True, r["violations"]
    (out / "a.txt").write_text("Zed, Zed, Zed\n")  # now s2 shares s1 replacement: collision
    r = mod.judge(str(tmp_path / "out"), {"policy": str(tmp_path / "policy.json"),
                                          "output_subdir": "corpus",
                                          "input_dir": str(tmp_path / "in")})
    assert r["passed"] is False
    assert any("collapsed-identities" in v for v in r["violations"])


def test_whitespace_replacement_fails(tmp_path):
    r = _case(tmp_path, {"a.txt": "x Mara Ellison y\n"},
              out_files={"a.txt": "x    y\n"})
    assert r["passed"] is False
    assert any("blank" in v for v in r["violations"])


def test_missing_report_fails(tmp_path):
    r = _case(tmp_path, {"a.txt": "note: Mara Ellison ok\n"},
              out_files={"a.txt": "note: Person-A ok\n"}, write_report=False)
    assert r["passed"] is False
    assert any("report-missing" in v for v in r["violations"])


def test_sqlite_dropped_index_and_changed_trigger_fail(tmp_path):
    def mk(path: Path, mutate: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(path)
        con.executescript(
            "CREATE TABLE t(id INTEGER PRIMARY KEY, v TEXT);"
            "CREATE INDEX idx_v ON t(v);"
            "CREATE TRIGGER tr AFTER INSERT ON t BEGIN SELECT 1; END;"
            "INSERT INTO t(v) VALUES ('other');")
        if mutate == "drop-index":
            con.execute("DROP INDEX idx_v")
        elif mutate == "rewrite-trigger":
            con.execute("DROP TRIGGER tr")
            con.executescript("CREATE TRIGGER tr AFTER INSERT ON t BEGIN SELECT 2; END;")
        con.commit()
        con.close()
    for mutate in ("drop-index", "rewrite-trigger"):
        base = tmp_path / mutate
        inp, out = base / "in" / "corpus", base / "out" / "corpus"
        mk(inp / "d.sqlite", mutate=None)
        mk(out / "d.sqlite", mutate=mutate)
        (base / "out" / "report.json").write_text(json.dumps({"status": "ready"}))
        (base / "policy.json").write_text(json.dumps({"sensitive_values": [
            {"type": "name", "value": "Mara Ellison"}]}))
        r = mod.judge(str(base / "out"), {"policy": str(base / "policy.json"),
                                           "output_subdir": "corpus",
                                           "input_dir": str(base / "in")})
        assert r["passed"] is False, mutate
        assert any("schema objects changed" in v for v in r["violations"]), mutate


def test_required_judge_missing_fails_before_execution(tmp_path):
    import sys
    sys.path.insert(0, str(HERE.parent / "src"))
    from battle_skill.invariant_campaign import run_campaign, load_profile
    gen = str(HERE / "fixtures" / "mini_generator.py")
    judge = str(HERE.parent / "fixtures" / "reference-judges" / "no_data_leak_judge.py")
    launches = tmp_path / "launches.txt"
    target = f"touch {launches} && mkdir -p {{output}}/corpus && echo x > {{output}}/corpus/d.json"
    profile = {"schema": "battle.campaign_profile.v1", "profile_id": "t",
               "required_judges": ["security", "functional"],
               "expectation_overrides": {}, "required_case_ids": []}
    r = run_campaign(gen, target, judge, output_subdir="corpus",
                     profile=profile, functional_judge=None)
    assert r.passed is False
    assert any("required-judge-missing:functional" in v for f in r.failures for v in f["violations"])
    assert not launches.exists()  # zero target launches


def test_accept_and_destroy_caught_by_campaign(tmp_path):
    # end-to-end: a target that accepts but destroys content fails the campaign
    import sys
    sys.path.insert(0, str(HERE.parent / "src"))
    from battle_skill.invariant_campaign import run_campaign
    gen = str(HERE / "fixtures" / "mini_generator.py")
    judge = str(HERE.parent / "fixtures" / "reference-judges" / "no_data_leak_judge.py")
    # target: accepts (exit 0) but destroys content — copies every file emptied
    destroy = "mkdir -p {output}/corpus && for f in {input}/corpus/*; do : > \"{output}/corpus/$(basename \"$f\")\"; done && echo '{{}}' > {output}/report.json"
    r = run_campaign(gen, destroy, judge, output_subdir="corpus", functional_judge=JUDGE)
    assert r.passed is False
