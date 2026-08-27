"""Issue #1531: a WebGPT attachment bundle rejected before browser dispatch
(surf zip file-count limit) must classify as webgpt_attachment_bundle_rejected
with a recovery packet that NAMES the file-count cause -- not a generic
browser_handler_timeout with a stale open-bind/rebind next_command.
"""
from __future__ import annotations

from pathlib import Path

from ask import tau_dag


def _summary(meta: dict) -> dict:
    return tau_dag._browser_orphan_artifact_summary(
        submit_meta=meta,
        submit_receipt={},
        inflight={},
        heartbeat={},
        handler="webgpt",
        surf_run=Path("skills/surf/run.sh"),
        prompt_path=Path("/tmp/p.md"),
        response_path=Path("/tmp/r.md"),
        raw_path=Path("/tmp/raw.md"),
        meta_path=Path("/tmp/m.json"),
        attachment_paths=["/tmp/bundle.zip"],
    )


def test_zip_over_limit_is_classified_as_attachment_rejection_not_timeout() -> None:
    meta = {
        "status": "failed",
        "failure": "attach_file_preflight_failed",
        "attach_file_preflight": {
            "ok": False,
            "file_count": 9,
            "max_files": 5,
            "error": "zip contains 9 files; maximum is 5",
        },
    }
    s = _summary(meta)
    assert s["failure_code"] == "webgpt_attachment_bundle_rejected"
    instr = s.get("fallback_instruction") or ""
    assert "9 files" in instr and "maximum is 5" in instr
    # It must NOT advise the stale tab-binding recovery.
    joined = " ".join(str(x) for x in s.get("next_command", []))
    assert "open-bind" not in joined and "--create-tab" not in joined
    # The deterministic next command is a resubmit with a corrected bundle.
    assert s["next_command"][:2] == ["skills/surf/run.sh", "webgpt.submit"]


def test_non_attachment_failure_still_uses_generic_path() -> None:
    # A plain timeout (no attach preflight failure) keeps the generic code.
    s = _summary({"status": "prepared_prompt", "submitted_to_chatgpt": False})
    assert s["failure_code"] != "webgpt_attachment_bundle_rejected"
