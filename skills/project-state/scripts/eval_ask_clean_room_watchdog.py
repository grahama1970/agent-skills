#!/usr/bin/env python3
"""Verify clean-room on the ask skill emits project-watchdog-routable evidence."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
ASK = REPO / "skills" / "ask"


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proof-output", type=Path)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        state = work / "ask-state.json"
        state.write_text(
            json.dumps(
                {
                    "schema": "project_state.report.v1",
                    "project": "ask",
                    "project_root": str(ASK),
                    "phase_6_gaps": {
                        "gaps": [
                            {
                                "severity": "critical",
                                "gap": "ask must not own clean-room zip/WebGPT delivery",
                                "action": "route forced iteration through project-watchdog tickets",
                            }
                        ],
                        "improvements": [],
                    },
                    "phase_3_doc_drift": {"drift_items": []},
                    "phase_4_best_practices": {"findings": []},
                }
            ),
            encoding="utf-8",
        )
        webgpt = work / "webgpt-not-ready.md"
        webgpt.write_text(
            "CLASSIFICATION: not-ready\n"
            "FOCUSED_TICKETS:\n"
            "- title: Keep ask out of clean-room delivery\n"
            "  target: skills/ask\n"
            "  observed: ask still appears to own WebGPT zip delivery\n"
            "  expected: project-state emits the bundle and project-watchdog owns repair iteration\n"
            "  proof: cd skills/project-state && uv run python scripts/eval_ask_clean_room_watchdog.py\n",
            encoding="utf-8",
        )
        out = work / "out"
        result = run(
            [
                str(ROOT / "run.sh"),
                "clean-room",
                str(ASK),
                "--output-dir",
                str(out),
                "--project-state-json",
                str(state),
                "--webgpt-response",
                str(webgpt),
                "--tab-id",
                "ask-tab-777",
                "--conversation-url",
                "https://chatgpt.com/c/ask-clean-room",
                "--watchdog-project",
                "agent-skills",
            ]
        )
        assert result.returncode == 2, result.stderr + result.stdout
        receipt = json.loads(result.stdout)
        assert receipt["target"] == str(ASK.resolve())
        assert receipt["status"] == "not-ready"
        assert receipt["iteration_driver"] == "project-watchdog"
        assert receipt["project_watchdog"]["eligible_route"] == "ticket_repair"
        assert receipt["project_watchdog"]["tick_command"] == "skills/project-watchdog/run.sh tick --apply --project agent-skills --max-tickets 1"
        assert receipt["triage_error"]["code"]
        assert receipt["controlled_tab_id"] == "ask-tab-777"
        assert receipt["conversation_url"] == "https://chatgpt.com/c/ask-clean-room"
        assert receipt["tickets"][0]["target"] == "skills/ask"

        round_dir = out / "round-01"
        preview = (round_dir / "ticket_previews.md").read_text(encoding="utf-8")
        prompt = (round_dir / "prompt.md").read_text(encoding="utf-8")
        assert "$project-watchdog" in prompt
        assert "Web seats are advisory only" in prompt
        assert "Review seats: `webgpt, webkimi, webgemini`" in prompt
        assert "--required-skill project-watchdog" in preview
        assert "--required-skill triage-error" in preview
        assert "--label \"executor:local\"" in preview
        assert "skills/project-watchdog/run.sh tick --apply --project agent-skills --max-tickets 1" in preview
        assert "triage_error_code" in preview
        assert "# readback receipt" in preview
        assert "skills/ask" in preview

        ticket_preview = subprocess.run(
            [
                str(REPO / "skills" / "ticket" / "run.sh"),
                "feature",
                "Keep ask out of clean-room delivery",
                "--target",
                "skills/ask",
                "--limitation",
                "ask still appears to own WebGPT zip delivery",
                "--capability",
                "project-state emits the bundle and project-watchdog owns repair iteration",
                "--workflow",
                "Continue in WebGPT tab ask-tab-777 at https://chatgpt.com/c/ask-clean-room; project-watchdog owns iteration",
                "--acceptance",
                "project-state emits the bundle and project-watchdog owns repair iteration",
                "--proof",
                "cd skills/agentic-evals && ./run.sh run ../project-state/fixtures/agentic_eval.json --only-category agentic-evals:agent-skills:clean-room-webgpt-loop --map ../project-state/fixtures/category_map.json must report readiness READY; python3 -c 'import json; print(json.load(open(\"/tmp/nonexistent-clean-room-manifest.json\"))[\"schema\"])' # readback receipt",
                "--route",
                "backend_python_or_skill_runtime",
                "--lane",
                "be",
                "--agent",
                "coder",
                "--required-skill",
                "project-watchdog",
                "--required-skill",
                "triage-error",
                "--label",
                "executor:local",
                "--json",
            ],
            cwd=REPO,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
        )
        assert ticket_preview.returncode == 0, ticket_preview.stderr + ticket_preview.stdout
        ticket_data = json.loads(ticket_preview.stdout[ticket_preview.stdout.find("{") :])
        assert "agent-work" in ticket_data.get("labels", [])
        assert "executor:local" in ticket_data.get("labels", [])

        zip_path = Path(receipt["zip_path"])
        assert zip_path.exists()
        with zipfile.ZipFile(zip_path) as zf:
            names = set(zf.namelist())
        assert len(names) <= 5
        assert {"manifest.json", "review_context.md", "ticket_previews.md", "webgpt_response.md"} <= names

        if args.proof_output:
            args.proof_output.parent.mkdir(parents=True, exist_ok=True)
            args.proof_output.write_text(
                json.dumps(
                    {
                        "schema": "project_state.ask_clean_room_watchdog_eval.v1",
                        "ok": True,
                        "target": receipt["target"],
                        "status": receipt["status"],
                        "iteration_driver": receipt["iteration_driver"],
                        "watchdog_route": receipt["project_watchdog"]["eligible_route"],
                        "watchdog_tick": receipt["project_watchdog"]["tick_command"],
                        "triage_error_code": receipt["triage_error"]["code"],
                        "ticket_target": receipt["tickets"][0]["target"],
                        "ticket_preview_routable": True,
                        "zip_members": sorted(names),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

    print("ASK_CLEAN_ROOM_WATCHDOG_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
