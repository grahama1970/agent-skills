"""Tests for the persona-dream -> Tau text-reasoning adapter.

No live LLM/scillm: subprocess to the Tau node is mocked. These prove the adapter
parses the Tau receipt, fails closed on a bad/blocked receipt, and never itself
touches scillm (it only invokes Tau).
"""
import importlib.util
import json
import subprocess
import threading
import time
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
    def __init__(self, stdout="", returncode=0, stderr="", delay_s=0.0):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self.pid = 999999
        self.delay_s = delay_s

    def communicate(self, input=None, timeout=None):
        self.input = input
        self.timeout = timeout
        if self.delay_s:
            time.sleep(self.delay_s)
        return self._stdout, self._stderr

    def wait(self, timeout=None):
        return self.returncode


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

    def fake_popen(cmd, stdin=None, stdout=None, stderr=None, text=None, cwd=None, start_new_session=None):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        captured["start_new_session"] = start_new_session
        captured["proc"] = _Proc(json.dumps(_receipt()))
        return captured["proc"]

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(adapter, "TAU_REPO", tmp_path)  # exists

    parsed, receipt = adapter.dispatch_text_reasoning(
        "prompt text", role="persona-self-interpretation", output_contract={"type": "object"},
    )
    captured["request"] = json.loads(captured["proc"].input)
    assert parsed == {"candidates": [{"id": "x"}]}
    assert receipt["api_key_source"] == "docker:scillm-proxy:SCILLM_MASTER_KEY"
    # It dispatches to the Tau node module, in the Tau repo cwd.
    assert "tau_coding.persona_dream_text_reasoning_agent" in captured["cmd"]
    assert captured["cwd"] == str(tmp_path)
    assert captured["start_new_session"] is True
    assert captured["request"]["role"] == "persona-self-interpretation"
    assert captured["request"]["output_contract"] == {"type": "object"}
    prov = adapter.receipt_provenance(receipt)
    assert prov["route"] == "tau:persona-dream-text-reasoning"
    assert prov["status"] == "PASS"


def test_adapter_fail_closed_on_blocked_receipt(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "Popen",
                        lambda *a, **k: _Proc(json.dumps(_receipt(status="BLOCKED", parsed=None)), returncode=1))
    monkeypatch.setattr(adapter, "TAU_REPO", tmp_path)
    parsed, receipt = adapter.dispatch_text_reasoning("p", role="r")
    assert parsed is None  # caller must fail closed
    assert receipt["status"] == "BLOCKED"


def test_adapter_raises_on_wrong_schema(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "Popen",
                        lambda *a, **k: _Proc(json.dumps({"schema": "something.else", "status": "PASS"})))
    monkeypatch.setattr(adapter, "TAU_REPO", tmp_path)
    with pytest.raises(adapter.TauRoutingError):
        adapter.dispatch_text_reasoning("p", role="r")


def test_adapter_raises_when_tau_repo_missing(monkeypatch):
    monkeypatch.setattr(adapter, "TAU_REPO", Path("/no/such/tau/repo"))
    with pytest.raises(adapter.TauRoutingError):
        adapter.dispatch_text_reasoning("p", role="r")


def test_adapter_raises_on_empty_output(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: _Proc("", returncode=1, stderr="boom"))
    monkeypatch.setattr(adapter, "TAU_REPO", tmp_path)
    with pytest.raises(adapter.TauRoutingError):
        adapter.dispatch_text_reasoning("p", role="r")


def test_adapter_wall_clock_timeout_kills_process_group(monkeypatch, tmp_path):
    killed = []
    proc = _Proc("", delay_s=1.0)

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: proc)
    monkeypatch.setattr(adapter, "TAU_REPO", tmp_path)
    monkeypatch.setattr(adapter.os, "killpg", lambda pid, sig: killed.append((pid, sig)))

    started = time.monotonic()
    with pytest.raises(adapter.TauRoutingError, match="timed out"):
        adapter.dispatch_text_reasoning("p", role="r", timeout_s=0.1)

    assert time.monotonic() - started < 0.8
    assert killed


def test_adapter_timer_timeout_kills_process_group_from_non_main_thread(monkeypatch, tmp_path):
    killed = []
    proc = _Proc(json.dumps(_receipt()), delay_s=0.2)
    result = {}

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: proc)
    monkeypatch.setattr(adapter, "TAU_REPO", tmp_path)
    monkeypatch.setattr(adapter.os, "killpg", lambda pid, sig: killed.append((pid, sig)))

    def _run():
        try:
            adapter.dispatch_text_reasoning("p", role="r", timeout_s=0.05)
        except Exception as exc:
            result["exc"] = exc

    thread = threading.Thread(target=_run)
    thread.start()
    thread.join(timeout=1.0)

    assert not thread.is_alive()
    assert isinstance(result.get("exc"), adapter.TauRoutingError)
    assert "timed out" in str(result["exc"])
    assert killed
