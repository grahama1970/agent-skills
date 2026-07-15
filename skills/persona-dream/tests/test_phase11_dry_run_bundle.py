from datetime import datetime, timezone
from pathlib import Path
import importlib.util
import json


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "phase11_bundle", ROOT / "scripts/write_phase11_dry_run_bundle.py"
)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def write(path: Path, value: dict):
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_legacy_bundle_is_fail_closed_and_cannot_emit_pass(tmp_path: Path):
    placeholder = write(tmp_path / "placeholder.json", {"status": "PASS"})
    metadata, approvals, gate = module.build_bundle(
        placeholder,
        placeholder,
        placeholder,
        placeholder,
        "invented-revision",
        datetime(2026, 7, 15, tzinfo=timezone.utc),
    )
    assert metadata["status"] == "BLOCKED_PROVIDER_GATE"
    assert approvals["status"] == "BLOCKED_PROVIDER_GATE"
    assert gate["status"] == "BLOCKED_PROVIDER_GATE"
    assert "BLOCKED_LEGACY_FREE_FORM_REVISION_ID" in gate["technical_blockers"]
    assert "BLOCKED_LEGACY_PAYLOAD_HASHES_RECEIPT_NOT_REQUEST_BODY" in gate["technical_blockers"]
    assert gate["actual_provider_call_attempts"] == 0
    assert gate["provider_ready"] is False
    assert gate["live_submit_ready"] is False
    assert gate["submitted"] is False
