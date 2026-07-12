from pathlib import Path
import importlib.util
import json


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("media_requirements", ROOT / "scripts/write_phase11_media_requirement_manifest.py")
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_eight_locked_assets_receive_explicit_roles(tmp_path: Path):
    assets = []
    panels = []
    for index in range(1, 5):
        panel = f"sb_{index:03d}"
        start = f"{panel}.start_frame"
        end = f"{panel}.end_frame"
        assets.extend([
            {"asset_id": start, "panel_id": panel, "frame_role": "start_frame", "sha256": "sha256:" + "a" * 64, "path": f"/{start}.png", "provider_accessible_url": None},
            {"asset_id": end, "panel_id": panel, "frame_role": "end_frame", "sha256": "sha256:" + "b" * 64, "path": f"/{end}.png", "provider_accessible_url": None},
        ])
        panels.append({"panel_id": panel, "source_start_image_asset_id": start, "source_end_image_asset_id": end})
    lock = tmp_path / "lock.json"
    payload = tmp_path / "payload.json"
    lock.write_text(json.dumps({"assets": assets}))
    payload.write_text(json.dumps({"panel_payloads": panels}))
    manifest = module.build_manifest(lock, payload, "rev-1")
    assert manifest["status"] == "PASS_PHASE11_MEDIA_REQUIREMENTS_DRY_RUN"
    assert manifest["all_locked_asset_count"] == 8
    assert manifest["submission_required_count"] == 8
    assert all(asset["provider_role"] == "submission_required" for asset in manifest["assets"])
    assert manifest["publication_performed"] is False
    assert manifest["actual_provider_call_attempts"] == 0
