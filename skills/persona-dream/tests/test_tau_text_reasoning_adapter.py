"""Tests for the persona-dream -> Tau text-reasoning adapter.

No live LLM/scillm: subprocess to the Tau node is mocked. These prove the adapter
parses the Tau receipt, fails closed on a bad/blocked receipt, and never itself
touches scillm (it only invokes Tau).
"""
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adapter = _load("tau_text_reasoning_adapter")


class _Proc:
    def __init__(self, stdout, returncode=0, stderr=""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


def _receipt(status="PASS", parsed=None):
    return {
        "schema": "tau.persona_dream.scillm_text_reasoning_receipt.v1",
        "status": status,
        "model": "gpt-5.5",
        "api_key_source": "docker:scillm-proxy:SCILLM_MASTER_KEY",
        "prompt_sha256": "sha256:abc",
        "output_contract_sha256": "sha256:def",
        "http_status": 200,
        "live_call_performed": True,
        "parsed_json": parsed if parsed is not None else {"candidates": [{"id": "x"}]},
    }


def test_adapter_returns_parsed_json_and_receipt(monkeypatch, tmp_path):
    captured = {}

    def fake_run(cmd, input=None, capture_output=None, text=None, cwd=None, timeout=None, check=None):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        captured["request"] = json.loads(input)
        return _Proc(json.dumps(_receipt()))

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(adapter, "TAU_REPO", tmp_path)  # exists

    parsed, receipt = adapter.dispatch_text_reasoning(
        "prompt text", role="persona-self-interpretation", output_contract={"type": "object"},
    )
    assert parsed == {"candidates": [{"id": "x"}]}
    assert receipt["api_key_source"] == "docker:scillm-proxy:SCILLM_MASTER_KEY"
    # It dispatches to the Tau node module, in the Tau repo cwd.
    assert "tau_coding.persona_dream_text_reasoning_agent" in captured["cmd"]
    assert captured["cwd"] == str(tmp_path)
    assert captured["request"]["role"] == "persona-self-interpretation"
    assert captured["request"]["output_contract"] == {"type": "object"}
    prov = adapter.receipt_provenance(receipt)
    assert prov["route"] == "tau:persona-dream-text-reasoning"
    assert prov["status"] == "PASS"


def test_adapter_fail_closed_on_blocked_receipt(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: _Proc(json.dumps(_receipt(status="BLOCKED", parsed=None)), returncode=1))
    monkeypatch.setattr(adapter, "TAU_REPO", tmp_path)
    parsed, receipt = adapter.dispatch_text_reasoning("p", role="r")
    assert parsed is None  # caller must fail closed
    assert receipt["status"] == "BLOCKED"


def test_adapter_raises_on_wrong_schema(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: _Proc(json.dumps({"schema": "something.else", "status": "PASS"})))
    monkeypatch.setattr(adapter, "TAU_REPO", tmp_path)
    with pytest.raises(adapter.TauRoutingError):
        adapter.dispatch_text_reasoning("p", role="r")


def test_adapter_raises_when_tau_repo_missing(monkeypatch):
    monkeypatch.setattr(adapter, "TAU_REPO", Path("/no/such/tau/repo"))
    with pytest.raises(adapter.TauRoutingError):
        adapter.dispatch_text_reasoning("p", role="r")


def test_adapter_raises_on_empty_output(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc("", returncode=1, stderr="boom"))
    monkeypatch.setattr(adapter, "TAU_REPO", tmp_path)
    with pytest.raises(adapter.TauRoutingError):
        adapter.dispatch_text_reasoning("p", role="r")
