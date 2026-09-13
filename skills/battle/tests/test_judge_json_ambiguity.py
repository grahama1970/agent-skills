"""Battle judges reject ambiguous JSON instead of losing evidence."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NO_LEAK = ROOT / "fixtures" / "reference-judges" / "no_data_leak_judge.py"
FUNCTIONAL = ROOT / "fixtures" / "reference-judges" / "functional_anonymize_judge.py"


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _policy(root: Path, value: str = "secret") -> Path:
    path = root / "policy.json"
    path.write_text(json.dumps({"sensitive_values": [{"value": value}]}), encoding="utf-8")
    return path


def test_no_data_leak_rejects_duplicate_key_with_escaped_secret(tmp_path: Path) -> None:
    judge = _load(NO_LEAK)
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "ambiguous.json").write_text(r'{"x":"\u0073ecret","x":"clean"}', encoding="utf-8")

    result = judge.judge(tmp_path, {"policy": str(_policy(tmp_path))})

    assert result["passed"] is False
    assert any("ambiguous json" in item for item in result["violations"])
    assert any("policy value survives" in item for item in result["violations"])


def test_no_data_leak_rejects_non_finite_json(tmp_path: Path) -> None:
    judge = _load(NO_LEAK)
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "nan.json").write_text('{"x": NaN}', encoding="utf-8")

    result = judge.judge(tmp_path, {"policy": str(_policy(tmp_path, "other"))})

    assert result["passed"] is False
    assert any("non-finite" in item for item in result["violations"])


def test_functional_judge_distinguishes_invalid_input_from_invalid_output(tmp_path: Path) -> None:
    judge = _load(FUNCTIONAL)
    policy = _policy(tmp_path)
    case = tmp_path / "case"
    inp = case / "corpus"
    out = tmp_path / "out" / "corpus"
    inp.mkdir(parents=True)
    out.mkdir(parents=True)
    (inp / "bad_input.json").write_text(r'{"x":"\u0073ecret","x":"clean"}', encoding="utf-8")
    (out / "bad_input.json").write_text('{"x":"clean"}', encoding="utf-8")
    (tmp_path / "out" / "report.json").write_text('{"status":"ready"}', encoding="utf-8")

    result = judge.judge(tmp_path / "out", {"policy": str(policy), "input_dir": str(case)})

    assert result["passed"] is False
    assert any("unsupported-input-json" in item for item in result["violations"])
    assert not any("invalid-released-output-json" in item for item in result["violations"])

    (inp / "bad_input.json").write_text('{"x":"secret"}', encoding="utf-8")
    (out / "bad_input.json").write_text('{"x":"anon","x":"clean"}', encoding="utf-8")
    result = judge.judge(tmp_path / "out", {"policy": str(policy), "input_dir": str(case)})

    assert result["passed"] is False
    assert any("invalid-released-output-json" in item for item in result["violations"])


def test_functional_judge_rejects_non_finite_report_json(tmp_path: Path) -> None:
    judge = _load(FUNCTIONAL)
    policy = _policy(tmp_path, "secret")
    case = tmp_path / "case"
    inp = case / "corpus"
    out = tmp_path / "out" / "corpus"
    inp.mkdir(parents=True)
    out.mkdir(parents=True)
    (inp / "ok.json").write_text('{"x":"secret"}', encoding="utf-8")
    (out / "ok.json").write_text('{"x":"anon"}', encoding="utf-8")
    (tmp_path / "out" / "report.json").write_text('{"status": NaN}', encoding="utf-8")

    result = judge.judge(tmp_path / "out", {"policy": str(policy), "input_dir": str(case)})

    assert result["passed"] is False
    assert any("report-malformed" in item and "non-finite" in item for item in result["violations"])
