#!/usr/bin/env python3
"""Deterministic eval for project-state clean-room loop."""

from __future__ import annotations

import json
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        target = work / "target"
        target.mkdir()
        (target / "SKILL.md").write_text("# Fake Skill\nTODO: conflicting future WebGPT path.\n", encoding="utf-8")
        state = work / "state.json"
        state.write_text(json.dumps({
            "schema": "project_state.report.v1",
            "project": "fake",
            "phase_6_gaps": {"gaps": [{"severity": "high", "gap": "conflicting features", "action": "clean-room"}]},
            "phase_3_doc_drift": {"drift_items": []},
            "phase_4_best_practices": {"findings": []},
        }), encoding="utf-8")
        not_ready = work / "not-ready.md"
        not_ready.write_text(
            "CLASSIFICATION: not-ready\n"
            "FOCUSED_TICKETS:\n"
            "- title: Remove conflicting WebGPT ownership\n"
            "  target: skills/fake\n"
            "  observed: two paths own browser zip delivery\n"
            "  expected: one owner\n"
            "  proof: run deterministic clean-room fixture\n",
            encoding="utf-8",
        )
        out = work / "out"
        result = run([
            str(ROOT / "run.sh"), "clean-room", str(target),
            "--output-dir", str(out),
            "--project-state-json", str(state),
            "--webgpt-response", str(not_ready),
            "--tab-id", "tab-123",
            "--conversation-url", "https://chatgpt.com/c/clean-room",
        ])
        assert result.returncode == 2, result.stderr + result.stdout
        receipt = json.loads(result.stdout)
        assert receipt["status"] == "not-ready"
        assert receipt["controlled_tab_id"] == "tab-123"
        assert receipt["review_handlers"] == ["webgpt", "webkimi", "webgemini"]
        assert receipt["review_mode"] == "ask_tau_roundtable"
        assert "--handler webgpt --handler webkimi --handler webgemini" in receipt["ask_roundtable_shell"]
        assert receipt["tickets"][0]["observed"] == "two paths own browser zip delivery"
        assert receipt["iteration_driver"] == "project-watchdog"
        assert receipt["project_watchdog"]["eligible_route"] == "ticket_repair"
        assert receipt["triage_error"]["code"]
        assert "zip_sha256" in receipt
        assert "project_state.json" in receipt["file_sha256"]
        zip_path = Path(receipt["zip_path"])
        assert zip_path.exists()
        with zipfile.ZipFile(zip_path) as zf:
            assert len(zf.namelist()) <= 5
            assert "review_context.md" in zf.namelist()
            assert "source_excerpts.md" not in zf.namelist()
        prompt_text = (out / "round-01" / "prompt.md").read_text(encoding="utf-8")
        assert str(target) not in prompt_text
        assert f"Target: `{target.name}`" in prompt_text
        assert "Review seats: `webgpt, webkimi, webgemini`" in prompt_text
        preview = out / "round-01" / "ticket_previews.md"
        preview_text = preview.read_text(encoding="utf-8")
        assert "Remove conflicting WebGPT ownership" in preview_text
        assert "two paths own browser zip delivery" in preview_text
        assert "one owner" in preview_text
        assert "run deterministic clean-room fixture" in preview_text
        assert "tab-123" in preview_text
        assert "source_round: 1" in preview_text
        assert "triage_error_code" in preview_text
        assert "project-watchdog/run.sh tick --apply --project agent-skills --max-tickets 1" in preview_text
        assert "--required-skill project-watchdog" in preview_text
        assert "--required-skill triage-error" in preview_text

        ready = work / "ready.md"
        ready.write_text("CLASSIFICATION: ready-to-deploy\n", encoding="utf-8")
        ready_out = work / "ready-out"
        ready_result = run([
            str(ROOT / "run.sh"), "clean-room", str(target),
            "--output-dir", str(ready_out),
            "--project-state-json", str(state),
            "--webgpt-response", str(ready),
            "--tab-id", "tab-123",
            "--conversation-url", "https://chatgpt.com/c/clean-room",
        ])
        assert ready_result.returncode == 0, ready_result.stderr + ready_result.stdout
        ready_receipt = json.loads(ready_result.stdout)
        assert ready_receipt["status"] == "ready-to-deploy"
        assert ready_receipt["status_reason"] == "webgpt_classified_ready_with_same_tab_binding"
        assert Path(ready_receipt["zip_path"]).exists()

        missing_tab = run([
            str(ROOT / "run.sh"), "clean-room", str(target),
            "--output-dir", str(work / "missing-tab-out"),
            "--project-state-json", str(state),
            "--webgpt-response", str(ready),
        ])
        assert missing_tab.returncode == 2, missing_tab.stderr + missing_tab.stdout
        missing_receipt = json.loads(missing_tab.stdout)
        assert missing_receipt["status"] == "not-ready"
        assert missing_receipt["status_reason"] == "missing_same_tab_binding"

        evidence_gap = work / "evidence-gap.md"
        evidence_gap.write_text(
            "CLASSIFICATION: not-ready\n"
            "FOCUSED_TICKETS:\n"
            "- title: Bundle missing source\n"
            "  target: skills/fake\n"
            "  observed: bundle is incomplete and missing source, cannot judge readiness\n"
            "  expected: provide source-first bundle\n"
            "  proof: rerun clean-room bundle\n",
            encoding="utf-8",
        )
        gap_result = run([
            str(ROOT / "run.sh"), "clean-room", str(target),
            "--output-dir", str(work / "evidence-gap-out"),
            "--project-state-json", str(state),
            "--webgpt-response", str(evidence_gap),
            "--tab-id", "tab-123",
            "--conversation-url", "https://chatgpt.com/c/clean-room",
        ])
        assert gap_result.returncode == 2, gap_result.stderr + gap_result.stdout
        gap_receipt = json.loads(gap_result.stdout)
        assert gap_receipt["status"] == "not-ready"
        assert gap_receipt["status_reason"] == "clean_room_bundle_incomplete"
        assert gap_receipt["ticket_count"] == 0
        assert not (work / "evidence-gap-out" / "round-01" / "ticket_previews.md").exists()

    print("CLEAN_ROOM_LOOP_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
