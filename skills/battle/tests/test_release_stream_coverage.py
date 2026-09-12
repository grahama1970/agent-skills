from __future__ import annotations

import importlib.util
import json
from pathlib import Path

JUDGE = Path(__file__).resolve().parents[1] / "fixtures/reference-judges/no_data_leak_judge.py"


def _judge_module():
    spec = importlib.util.spec_from_file_location("no_data_leak_judge", JUDGE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _policy(root: Path, value: str = "Alice Secret") -> Path:
    path = root / "policy.json"
    path.write_text(json.dumps({"sensitive_values": [{"value": value}]}), encoding="utf-8")
    return path


def _run(root: Path, **params):
    return _judge_module().judge(root, {"policy": str(_policy(root)), **params})


def test_log_stream_secret_fails(tmp_path: Path) -> None:
    (tmp_path / "corpus").mkdir()
    logs = tmp_path / ".battle-execution"
    logs.mkdir()
    (logs / "stderr.log").write_text("oops Alice Secret", encoding="utf-8")

    result = _run(tmp_path)

    assert result["passed"] is False
    assert result["evidence"]["release_inventory"]


def test_extensionless_release_artifact_secret_fails(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "release_artifact").write_text("Alice Secret", encoding="utf-8")

    assert _run(tmp_path)["passed"] is False


def test_binary_text_release_artifact_secret_fails(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "blob.bin").write_bytes(b"\x00Alice Secret\x00")

    assert _run(tmp_path)["passed"] is False


def test_scan_limit_exceeded_fails_closed(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "big.log").write_text("harmless", encoding="utf-8")

    result = _run(tmp_path, max_scan_bytes=3)

    assert result["passed"] is False
    assert any("scan incomplete" in v for v in result["violations"])
