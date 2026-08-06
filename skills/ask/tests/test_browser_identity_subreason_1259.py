"""#1259: distinct browser identity sub-errors must map to distinct failure
codes with correct actions, so the project agent gets an actionable reason
instead of a one-size 'rebind' recommendation."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

WORKER = Path(__file__).resolve().parents[1] / "scripts" / "tau_roundtable_worker.py"
spec = importlib.util.spec_from_file_location("trw_subreason", WORKER)
w = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = w
spec.loader.exec_module(w)


def _classify(meta: dict) -> str:
    return w._classify_browser_failure(
        handler="webgpt", failure="", response_text="", raw_text="",
        prompt_text="", submit_meta=meta, commands=[],
    )


def test_unverified_multiple_maps_to_expect_url_code() -> None:
    code = _classify({"tab_identity_preflight": {"ok": False, "error": "unverified_tab_id_with_multiple_chatgpt_tabs"}})
    assert code == w.BROWSER_TAB_UNVERIFIED_MULTIPLE
    fc = w.BROWSER_FAILURE_CODES[code]
    assert "expect-url" in fc.reason.lower()
    assert fc.auto_retry_blocked_reason == "browser_tab_needs_expect_url_or_fewer_tabs"


def test_tab_not_open_maps_to_reprovision_code() -> None:
    code = _classify({"tab_identity_preflight": {"ok": False, "error": "tab_not_open_chatgpt"}})
    assert code == w.BROWSER_TAB_NOT_OPEN
    assert w.BROWSER_FAILURE_CODES[code].auto_retry_blocked_reason == "browser_tab_reprovision_required"


def test_true_url_mismatch_still_maps_to_rebind() -> None:
    code = _classify({"failure": "expected_url_mismatch", "tab_identity_preflight": {"ok": False, "error": "expected_url_mismatch"}})
    assert code == w.BROWSER_TAB_IDENTITY_MISMATCH
    assert w.BROWSER_FAILURE_CODES[code].auto_retry_blocked_reason == "browser_tab_identity_rebind_required"
