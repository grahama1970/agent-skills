"""Jev shadow remains explicit-upload, pinned, durable, and non-authoritative."""
import json

from ai_detection.jev_shadow import PINNED_JEV_MODEL, run_shadow


def test_jev_shadow_blocks_upload_and_writes_receipt(tmp_path):
    source = tmp_path / "candidate.py"
    output = tmp_path / "shadow.json"
    source.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    receipt = run_shadow(source, output, allow_provider_upload=False,
                         agent_skills_root=tmp_path / "missing")

    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert receipt.outcome == "blocked"
    assert persisted["outcome"] == "blocked"
    assert persisted["provider_upload_authorized"] is False
    assert persisted["advisory_only"] is True
    assert persisted["production_disposition_changed"] is False
    assert persisted["battle_authority"] is False
    assert persisted["model"] == PINNED_JEV_MODEL


def test_jev_shadow_accounts_for_missing_runtime_after_authorization(tmp_path):
    source = tmp_path / "candidate.py"
    output = tmp_path / "shadow.json"
    source.write_text("x = 1\n", encoding="utf-8")

    receipt = run_shadow(source, output, allow_provider_upload=True,
                         agent_skills_root=tmp_path / "missing")

    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert receipt.outcome == "failed"
    assert persisted["outcome"] == "failed"
    assert persisted["provider_upload_authorized"] is True
    assert persisted["error"]
