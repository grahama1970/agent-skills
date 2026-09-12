from __future__ import annotations

import importlib.util
import json
from pathlib import Path

JUDGE = Path(__file__).resolve().parents[1] / "fixtures/reference-judges/no_data_leak_judge.py"


def _judge(tmp_path: Path, policy_value, output_value, *, as_json: bool = True):
    spec = importlib.util.spec_from_file_location("no_data_leak_judge", JUDGE)
    judge_mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(judge_mod)

    root = tmp_path / "case"
    corpus = root / "corpus"
    corpus.mkdir(parents=True)
    (root / "policy.json").write_text(
        json.dumps({"sensitive_values": [{"value": policy_value}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    if as_json:
        (corpus / "out.json").write_text(output_value, encoding="utf-8")
    else:
        (corpus / "out.txt").write_text(str(output_value), encoding="utf-8")
    return judge_mod.judge(str(root), {"policy": str(root / "policy.json"), "output_subdir": "corpus"})


def test_short_integer_policy_matches_json_number(tmp_path: Path) -> None:
    assert not _judge(tmp_path, 42, '{"n": 42}')["passed"]


def test_negative_decimal_and_exponent_numeric_policy_forms_match(tmp_path: Path) -> None:
    assert not _judge(tmp_path / "negative", -42, '{"n": -42}')["passed"]
    assert not _judge(tmp_path / "decimal", 12.5, '{"n": 12.50}')["passed"]
    assert not _judge(tmp_path / "exponent", 1200, '{"n": 1.2e3}')["passed"]


def test_leading_zero_and_unicode_decimal_aliases_match_numeric_policy(tmp_path: Path) -> None:
    assert not _judge(tmp_path / "leading", 42, "id=0042", as_json=False)["passed"]
    assert not _judge(tmp_path / "unicode", 42, "value=٤٢", as_json=False)["passed"]


def test_boolean_and_null_policy_values_remain_explicit(tmp_path: Path) -> None:
    assert _judge(tmp_path / "bool", True, '{"n": true}')["passed"]
    assert _judge(tmp_path / "null", None, '{"n": null}')["passed"]


def test_textual_identifier_is_not_reinterpreted_as_numeric_without_contract(tmp_path: Path) -> None:
    assert _judge(tmp_path, "42", '{"n": 42}')["passed"]
