"""surf composes /triage-error: a normalized failure meta carries the canonical
code when the catalog has a more specific one than the generic browser_handler_*.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import surf_meta_normalize as s


def test_attach_preflight_failure_gets_canonical_triage_code() -> None:
    out = s.finalize_nonterminal_meta(
        {"status": "prepared_prompt", "submitted_to_chatgpt": False},
        returncode=2,
        stderr_text="attach_file_preflight_failed: zip contains 9 files; maximum is 5",
        stdout_text="", duration_seconds=1.0,
    )
    assert out["triage"]["code"] == "webgpt_attachment_bundle_rejected"


def test_plain_timeout_gets_no_bogus_triage() -> None:
    out = s.finalize_nonterminal_meta(
        {"status": "prepared_prompt"}, returncode=124,
        stderr_text="timed out", stdout_text="", duration_seconds=1.0,
    )
    assert "triage" not in out
