"""Retained guard for the authorized Docker Battle smoke receipt boundary."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_battle_smoke_preserves_cli_behavior_and_records_non_efficacy(tmp_path):
    out = tmp_path / "battle"
    result = subprocess.run(
        [sys.executable, "scripts/battle_smoke.py", "--out", str(out)],
        cwd=ROOT, capture_output=True, text=True, check=False, timeout=180,
    )
    assert result.returncode == 0, result.stderr
    campaign = json.loads((out / "campaign.json").read_text())
    manifest = json.loads((out / "receipt-manifest.json").read_text())
    assert campaign["terminal_state"] == "mechanism_smoke_complete"
    assert campaign["behavior_preserved"] is True
    assert campaign["detector_invariant_preserved"] is True
    assert campaign["judge_before_passed"] is True
    assert campaign["judge_after_passed"] is True
    assert campaign["efficacy"] == "NOT_ESTABLISHED"
    for name, expected in manifest["artifacts"].items():
        actual = hashlib.sha256((out / name).read_bytes()).hexdigest()
        assert actual == expected, name
