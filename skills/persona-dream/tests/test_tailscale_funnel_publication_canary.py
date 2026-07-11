from argparse import Namespace
from pathlib import Path
import importlib.util


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


canary_module = load_module(
    "tailscale_funnel_publication_canary",
    ROOT / "scripts/tailscale_funnel_publication_canary.py",
)


def test_funnel_canary_default_is_plan_only(tmp_path):
    asset = tmp_path / "locked-frame.png"
    asset.write_bytes(b"not-a-real-png-but-locked-bytes")
    output_root = tmp_path / "out"
    args = Namespace(
        asset=asset,
        output_root=output_root,
        asset_id="asset_001",
        asset_role="start_frame",
        https_port=443,
        max_exposure_seconds=60,
        probe_timeout=5,
        probe_deadline_seconds=10,
        execute=False,
        allow_publication=False,
    )

    receipt = canary_module.run_canary(args)

    assert receipt["status"] == "DRY_RUN_PROVIDER_MEDIA_PUBLICATION_PLAN"
    assert receipt["publication_backend"] == "tailscale_funnel"
    assert receipt["provider_live"] is False
    assert receipt["actual_provider_call_attempts"] == 0
    assert receipt["submitted"] is False
    assert receipt["provider_ready"] is False
    assert receipt["live_submit_ready"] is False
    assert receipt["live"] is False
