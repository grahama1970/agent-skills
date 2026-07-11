import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT.parent / "battle" / "profiles" / "pixijs-runtime-atlas-64.v1.json"
SOURCE = ROOT.parent / "battle" / "assets" / "sprites" / "pixijs" / "plague_nurgling-contact-sheet.png"
RUN = ROOT / "run.sh"


def test_plague_contact_sheet_overflow_blocks_but_lists_missing(tmp_path):
    job = tmp_path / "plague"
    proc = subprocess.run(
        [
            str(RUN),
            "repair",
            "--source",
            str(SOURCE),
            "--profile",
            str(PROFILE),
            "--sprite-id",
            "plague_nurgling",
            "--job-dir",
            str(job),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 4, proc.stdout + proc.stderr
    receipt = json.loads((job / "repair-receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "BLOCKED_FRAME_OVERFLOW"
    missing = json.loads((job / "missing-frames.json").read_text(encoding="utf-8"))
    assert missing["complete"] is False
    assert missing["missing_cell_count"] > 0
    assert not (job / "atlas.candidate.png").exists()
