from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
LIVE_WEBGPT_SANITY = REPO_ROOT / "skills/surf/scripts/live_webgpt_sanity.py"


def load_live_webgpt_sanity():
    spec = importlib.util.spec_from_file_location("live_webgpt_sanity", LIVE_WEBGPT_SANITY)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_validate_roundtrip_reports_provider_rate_limit_detail() -> None:
    module = load_live_webgpt_sanity()

    ok, detail = module.validate_roundtrip(
        {
            "status": "fail",
            "warnings": [],
            "meta": {
                "status": "failed",
                "proof_status": "rate_limited",
                "blocker": "BLOCKED_WEBGPT_PROVIDER_RATE_LIMIT",
                "failure": "chatgpt_provider_limit_preflight",
                "submitted_to_chatgpt": False,
            },
        }
    )

    assert ok is False
    assert "rate_limited" in detail
    assert "BLOCKED_WEBGPT_PROVIDER_RATE_LIMIT" in detail
    assert "chatgpt_provider_limit_preflight" in detail


def test_roundtrip_process_timeout_includes_default_rate_limit_wait(monkeypatch) -> None:
    monkeypatch.delenv("SURF_WEBGPT_ROUNDTRIP_RATE_LIMIT_WAIT_SECONDS", raising=False)
    monkeypatch.delenv("SURF_WEBGPT_RATE_LIMIT_WAIT_SECONDS", raising=False)
    module = load_live_webgpt_sanity()

    assert module.configured_rate_limit_wait_seconds() == 300
    assert module.roundtrip_process_timeout(180, 90) == 420


def test_roundtrip_process_timeout_honors_roundtrip_override(monkeypatch) -> None:
    monkeypatch.setenv("SURF_WEBGPT_RATE_LIMIT_WAIT_SECONDS", "300")
    monkeypatch.setenv("SURF_WEBGPT_ROUNDTRIP_RATE_LIMIT_WAIT_SECONDS", "7")
    module = load_live_webgpt_sanity()

    assert module.configured_rate_limit_wait_seconds() == 7
    assert module.roundtrip_process_timeout(180, 90) == 180
