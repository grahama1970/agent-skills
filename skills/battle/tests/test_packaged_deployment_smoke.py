import json
from pathlib import Path

from battle_skill.packaged_deployment_smoke import (
    _receipt_errors,
    _rewrite_interaction_manifest,
)


def test_rewrite_interaction_manifest_targets_packaged_ports(tmp_path: Path) -> None:
    source = tmp_path / "manifest.json"
    dest = tmp_path / "rewritten.json"
    source.write_text(
        json.dumps(
            {
                "base_url": "http://127.0.0.1:3016/#battle",
                "surfaces": [
                    {
                        "name": "live",
                        "path": "/live?engine=pixi&battle=battle-004&liveBase=http%3A%2F%2F127.0.0.1%3A18766&ti=x",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    _rewrite_interaction_manifest(
        source=source,
        dest=dest,
        preview_base="http://127.0.0.1:3111",
        adapter_base="http://127.0.0.1:18888",
    )

    rewritten = json.loads(dest.read_text(encoding="utf-8"))
    assert rewritten["base_url"] == "http://127.0.0.1:3111/#battle"
    assert "liveBase=http%3A%2F%2F127.0.0.1%3A18888" in rewritten["surfaces"][0]["path"]
    assert rewritten["surfaces"][0]["path"].endswith("&ti=x")


def test_packaged_receipt_error_gate_requires_zero_failures(tmp_path: Path) -> None:
    screenshot = tmp_path / "screen.png"
    screenshot.write_bytes(b"png")
    visual_findings = tmp_path / "visual-findings.jsonl"
    visual_findings.write_text("", encoding="utf-8")

    assert (
        _receipt_errors(
            health={"status": "PASS"},
            backend_receipt={"status": "PASS", "mocked": False},
            pr8_summary={"mocked": False, "failed": []},
            interaction_results={"failed": 0, "warned": 0},
            visual_findings_path=visual_findings,
            screenshot_path=screenshot,
        )
        == []
    )

    errors = _receipt_errors(
        health={"status": "PASS"},
        backend_receipt={"status": "PASS", "mocked": False},
        pr8_summary={"mocked": False, "failed": ["bad"]},
        interaction_results={"failed": 0, "warned": 0},
        visual_findings_path=visual_findings,
        screenshot_path=screenshot,
    )
    assert errors == ["packaged PR8 live transport proof has failures"]
