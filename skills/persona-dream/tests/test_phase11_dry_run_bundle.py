from datetime import datetime, timezone
from pathlib import Path
import importlib.util
import json


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("phase11_bundle", ROOT / "scripts/write_phase11_dry_run_bundle.py")
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def write(path: Path, value: dict):
    path.write_text(json.dumps(value))
    return path


def test_dry_run_gate_passes_with_live_blockers_and_zero_side_effects(tmp_path: Path):
    phase10 = write(tmp_path / "phase10.json", {"status": "PASS_PHASE10_PROVIDER_CONTRACT_DRY_RUN_WITH_LIVE_BLOCKERS", "actual_provider_call_attempts": 0})
    schema = write(tmp_path / "schema.json", {"status": "PASS_PROVIDER_SCHEMA_DRY_RUN_REVIEWED", "provider": "kling", "model_endpoint": "fal-ai/kling", "generated_at": "2026-07-10T00:00:00Z", "source_urls": ["https://fal.ai/docs"], "observed_schema": {"input": {}}})
    preflight = write(tmp_path / "preflight.json", {"status": "PASS_FAL_API_PREFLIGHT", "actual_provider_call_attempts": 0})
    media = write(tmp_path / "media.json", {"status": "PASS_PHASE11_MEDIA_REQUIREMENTS_DRY_RUN", "publication_performed": False, "provider_accessible_url_created": False, "actual_provider_call_attempts": 0})
    metadata, approvals, gate = module.build_bundle(phase10, schema, preflight, media, "rev-1", datetime(2026, 7, 12, tzinfo=timezone.utc))
    assert metadata["status"] == "PASS_PHASE11_PROVIDER_METADATA_DRY_RUN"
    assert approvals["paid_call_authorized"] is False
    assert gate["status"] == "PASS_PHASE11_SUBMIT_GATE_DRY_RUN"
    assert gate["live_submit_status"] == "BLOCKED_PHASE11_LIVE_SUBMIT"
    assert gate["dry_run_blockers"] == []
    assert len(gate["live_blockers"]) == 6
    assert gate["actual_provider_call_attempts"] == 0
    assert gate["submitted"] is False
