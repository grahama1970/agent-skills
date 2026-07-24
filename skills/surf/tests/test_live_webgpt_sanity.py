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
