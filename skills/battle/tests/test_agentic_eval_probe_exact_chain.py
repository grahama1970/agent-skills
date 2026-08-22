from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


def _load_probe_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "agentic_eval_probe.py"
    spec = importlib.util.spec_from_file_location("battle_agentic_eval_probe", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exact_chain_probe_regenerates_when_cached_root_missing(
    tmp_path: Path, monkeypatch
) -> None:
    probe = _load_probe_module()
    commands: list[list[str]] = []
    required_checks = [
        "campaign_receipt_present",
        "artifact_integrity_receipt_present",
        "prior_backend_verification_present",
        "fresh_backend_verification_pass",
        "live_required",
        "mock_forbidden",
        "fixture_fallback_forbidden",
        "immutable_slots_match_required_count",
        "exact_replays_match_required_count",
        "docker_observed_input_hashes_bound",
        "red_blue_generation_ids_valid",
    ]

    def fake_run(command: list[str], *, timeout: int = 240):
        commands.append(command)
        if "adaptive-red-blue-lineage-canary" in command:
            out = Path(command[command.index("--out") + 1])
            out.mkdir(parents=True, exist_ok=True)
            (out / "campaign-receipt.json").write_text("{}\n", encoding="utf-8")
            (out / "artifact-integrity-receipt.json").write_text(
                "{}\n", encoding="utf-8"
            )
        if "verify_adaptive_lineage_backend_run.py" in command:
            out = Path(command[command.index("--out") + 1])
            out.write_text('{"status":"PASS"}\n', encoding="utf-8")
        if "arena-adaptive-lineage-qualification" in command:
            proof_root = Path(command[command.index("--proof-dir") + 1])
            proof_root.mkdir(parents=True, exist_ok=True)
            qualification = {
                "status": "PASS",
                "battle_id": "battle-004",
                "mocked": False,
                "live": True,
                "checks": [
                    {"name": name, "status": "PASS"} for name in required_checks
                ],
                "counts": {
                    "slot_hashes_matched": 4,
                    "exact_replays_matched": 2,
                },
            }
            (proof_root / "adaptive-lineage-qualification.json").write_text(
                json.dumps(qualification), encoding="utf-8"
            )
            (proof_root / "adaptive-lineage-verification.json").write_text(
                "{}\n", encoding="utf-8"
            )
        return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

    monkeypatch.delenv("BATTLE_ADAPTIVE_LINEAGE_PROOF_ROOT", raising=False)
    monkeypatch.setattr(probe, "_latest_adaptive_lineage_root", lambda: None)
    monkeypatch.setattr(probe, "_run", fake_run)

    summary_path = tmp_path / "summary.json"
    assert probe.probe_adaptive_lineage_live_exact_chain(
        summary_path, proof_root=None
    ) == 0

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["status"] == "PASS"
    assert (
        summary["checks"][0]["proof_root"]
        == str(tmp_path / "adaptive-lineage-live-exact-chain-fresh" / "qualification")
    )
    rendered = [" ".join(str(part) for part in command) for command in commands]
    assert any("adaptive-red-blue-lineage-canary" in command for command in rendered)
    assert any("verify_adaptive_lineage_backend_run.py" in command for command in rendered)
    assert any("arena-adaptive-lineage-qualification" in command for command in rendered)
