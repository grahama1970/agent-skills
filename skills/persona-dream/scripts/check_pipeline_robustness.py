#!/usr/bin/env python3
"""Aggregate offline robustness checks for the Persona Dream pipeline.

This harness answers a narrow question: do the existing deterministic checkers
and fixtures still enforce the agent-facing pipeline boundaries? It is not a
content-quality review and does not call paid or live provider services.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "tests" / "fixtures"
DEFAULT_OUTPUT_ROOT = Path("/tmp")
PASS_STATUS = "PASS_PERSONA_DREAM_PIPELINE_ROBUSTNESS"
BLOCKED_STATUS = "BLOCKED_PERSONA_DREAM_PIPELINE_ROBUSTNESS"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _run_command(
    *,
    name: str,
    cmd: list[str],
    cwd: Path,
    expected_exit: int,
    receipt_path: Path | None,
    timeout_s: int,
) -> dict[str, Any]:
    started = time.monotonic()
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout_s,
        check=False,
    )
    duration_s = round(time.monotonic() - started, 3)
    receipt: dict[str, Any] | None = None
    if receipt_path and receipt_path.exists():
        receipt = _read_json(receipt_path)

    errors: list[str] = []
    if proc.returncode != expected_exit:
        errors.append(f"exit_mismatch:{proc.returncode}:expected:{expected_exit}")
    if receipt and str(receipt.get("status", "")).startswith("BLOCKED"):
        errors.append(f"blocked_status:{receipt.get('status')}")

    return {
        "name": name,
        "command": cmd,
        "cwd": str(cwd),
        "exit_code": proc.returncode,
        "expected_exit": expected_exit,
        "duration_s": duration_s,
        "stdout": proc.stdout.strip()[-4000:],
        "stderr": proc.stderr.strip()[-4000:],
        "receipt_path": str(receipt_path) if receipt_path else None,
        "receipt_status": receipt.get("status") if receipt else None,
        "fixture_count": receipt.get("fixture_count") if receipt else None,
        "observed_blockers": receipt.get("observed_blockers") if receipt else None,
        "errors": errors,
    }


def _require_files(root: Path, names: list[str]) -> list[str]:
    return [name for name in names if not (root / name).exists()]


def _autonomous_fixture_checks(output_root: Path, timeout_s: int) -> dict[str, Any]:
    static_dir = output_root / "autonomous-static-dream"
    video_dir = output_root / "autonomous-video-plan"

    static_cmd = [
        sys.executable,
        str(SCRIPTS / "persona_dream.py"),
        "generate",
        "--persona",
        "embry",
        "--fixture",
        str(SCRIPTS / "fixtures" / "sample_residue.json"),
        "--output-dir",
        str(static_dir),
        "--run-id",
        "robustness-autonomous-static",
        "--no-write-memory",
    ]
    video_cmd = [
        sys.executable,
        str(SCRIPTS / "persona_dream.py"),
        "generate",
        "--mode",
        "video_plan",
        "--persona",
        "horus",
        "--secondary-persona",
        "embry",
        "--fixture",
        str(SCRIPTS / "fixtures" / "sample_residue.json"),
        "--about",
        "creating a deterministic pipeline robustness artifact",
        "--scene",
        "Horus and Embry discuss a receipt-backed dream pipeline at a quiet table.",
        "--duration-seconds",
        "30",
        "--output-dir",
        str(video_dir),
        "--run-id",
        "robustness-autonomous-video",
        "--no-write-memory",
    ]

    static = _run_command(
        name="autonomous_static_fixture_generate",
        cmd=static_cmd,
        cwd=ROOT,
        expected_exit=0,
        receipt_path=None,
        timeout_s=timeout_s,
    )
    video = _run_command(
        name="autonomous_video_plan_fixture_generate",
        cmd=video_cmd,
        cwd=ROOT,
        expected_exit=0,
        receipt_path=None,
        timeout_s=timeout_s,
    )

    static_required = [
        "dream_request.json",
        "response.json",
        "residue_links.json",
        "contradiction_report.json",
        "dream_packet.json",
        "dream_prompt.txt",
        "frame_prompts.json",
        "contact_sheet.png",
        "dream_reflection.md",
        "memory_write_receipt.json",
    ]
    video_required = [
        "dream_story.md",
        "dream_story.json",
        "character_scene_bible.json",
        "storyboard.json",
        "timed_transcript.json",
        "multimodal_prompts.json",
        "voice_handoff_plan.json",
        "pipeline_stage_report.json",
        "pipeline_stage_report.md",
        "manifest.json",
    ]

    errors = list(static["errors"]) + list(video["errors"])
    missing_static = _require_files(static_dir, static_required)
    missing_video = _require_files(video_dir, video_required)
    if missing_static:
        errors.append(f"missing_static_artifacts:{','.join(missing_static)}")
    if missing_video:
        errors.append(f"missing_video_artifacts:{','.join(missing_video)}")

    static_receipt: dict[str, Any] = {}
    if (static_dir / "memory_write_receipt.json").exists():
        static_receipt = _read_json(static_dir / "memory_write_receipt.json")
        if static_receipt.get("status") != "skipped":
            errors.append(f"static_memory_write_not_skipped:{static_receipt.get('status')}")

    video_manifest: dict[str, Any] = {}
    if (video_dir / "manifest.json").exists():
        video_manifest = _read_json(video_dir / "manifest.json")
        if video_manifest.get("mode") != "video_plan":
            errors.append(f"video_manifest_mode:{video_manifest.get('mode')}")

    return {
        "name": "autonomous_fixture_generation",
        "status": "PASS_AUTONOMOUS_FIXTURE_GENERATION" if not errors else "BLOCKED_AUTONOMOUS_FIXTURE_GENERATION",
        "fixture_backed": True,
        "human_content_judgment_required": False,
        "memory_write_status": static_receipt.get("status"),
        "video_mode": video_manifest.get("mode"),
        "static_output_dir": str(static_dir),
        "video_output_dir": str(video_dir),
        "commands": [static, video],
        "errors": errors,
    }


def _checker_specs(receipt_root: Path) -> list[dict[str, Any]]:
    return [
        {
            "name": "pipeline_contract",
            "script": "check_persona_dream_pipeline_contract.py",
            "args": ["--receipt-out", str(receipt_root / "pipeline_contract.json"), "--json"],
            "receipt": receipt_root / "pipeline_contract.json",
        },
        {
            "name": "respawn_plan_fixtures",
            "script": "check_persona_dream_respawn_plan.py",
            "args": [
                "--fixtures-root",
                str(FIXTURES / "respawn"),
                "--receipt-out",
                str(receipt_root / "respawn_plan.json"),
                "--json",
            ],
            "receipt": receipt_root / "respawn_plan.json",
        },
        {
            "name": "stale_write_fence_fixtures",
            "script": "check_persona_dream_stale_write_fence.py",
            "args": [
                "--fixtures-root",
                str(FIXTURES / "stale-write-fence"),
                "--receipt-out",
                str(receipt_root / "stale_write_fence.json"),
                "--json",
            ],
            "receipt": receipt_root / "stale_write_fence.json",
        },
        {
            "name": "global_progress_rollup_fixtures",
            "script": "check_persona_dream_global_progress_rollup.py",
            "args": [
                "--fixtures-root",
                str(FIXTURES / "global-progress-rollup"),
                "--receipt-out",
                str(receipt_root / "global_progress_rollup.json"),
                "--json",
            ],
            "receipt": receipt_root / "global_progress_rollup.json",
        },
        {
            "name": "dynamic_respawn_event_fixtures",
            "script": "check_persona_dream_dynamic_respawn_events.py",
            "args": [
                "--fixtures-root",
                str(FIXTURES / "dynamic-respawn-events"),
                "--receipt-out",
                str(receipt_root / "dynamic_respawn_events.json"),
                "--json",
            ],
            "receipt": receipt_root / "dynamic_respawn_events.json",
        },
        {
            "name": "creator_reviewer_respawn_loop_fixtures",
            "script": "check_persona_dream_creator_reviewer_respawn_loop.py",
            "args": [
                "--fixtures-root",
                str(FIXTURES / "creator-reviewer-respawn-loop"),
                "--receipt-out",
                str(receipt_root / "creator_reviewer_respawn_loop.json"),
                "--json",
            ],
            "receipt": receipt_root / "creator_reviewer_respawn_loop.json",
        },
        {
            "name": "run_state_fixtures",
            "script": "check_persona_dream_run_state.py",
            "args": [
                "--fixtures-root",
                str(FIXTURES / "run-state"),
                "--receipt-out",
                str(receipt_root / "run_state.json"),
                "--json",
            ],
            "receipt": receipt_root / "run_state.json",
        },
        {
            "name": "run_root_state_fixtures",
            "script": "check_persona_dream_run_root_state.py",
            "args": [
                "--fixtures-root",
                str(FIXTURES / "run-root-state"),
                "--receipt-out",
                str(receipt_root / "run_root_state.json"),
                "--json",
            ],
            "receipt": receipt_root / "run_root_state.json",
        },
        {
            "name": "video_provider_selection_fixtures",
            "script": "check_video_provider_selection.py",
            "args": [
                "--fixtures-root",
                str(FIXTURES / "video-provider-selection"),
                "--receipt-out",
                str(receipt_root / "video_provider_selection.json"),
                "--json",
            ],
            "receipt": receipt_root / "video_provider_selection.json",
        },
        {
            "name": "video_provider_registry_refresh_fixtures",
            "script": "check_video_provider_registry_refresh.py",
            "args": [
                "--fixtures-root",
                str(FIXTURES / "video-provider-registry-refresh"),
                "--receipt-out",
                str(receipt_root / "video_provider_registry_refresh.json"),
                "--json",
            ],
            "receipt": receipt_root / "video_provider_registry_refresh.json",
        },
        {
            "name": "video_provider_packet_routing_fixtures",
            "script": "check_video_provider_packet_routing.py",
            "args": [
                "--fixtures-root",
                str(FIXTURES / "video-provider-packet-routing"),
                "--receipt-out",
                str(receipt_root / "video_provider_packet_routing.json"),
                "--json",
            ],
            "receipt": receipt_root / "video_provider_packet_routing.json",
        },
        {
            "name": "fal_api_preflight_fixtures",
            "script": "check_fal_api_preflight_fixtures.py",
            "args": [
                "--fixtures-root",
                str(FIXTURES / "fal-api-preflight"),
                "--receipt-out",
                str(receipt_root / "fal_api_preflight.json"),
                "--json",
            ],
            "receipt": receipt_root / "fal_api_preflight.json",
        },
    ]


def _run_spine_chain(receipt_root: Path, timeout_s: int) -> dict[str, Any]:
    receipt_dir = receipt_root / "spine_chain"
    result = _run_command(
        name="spine_chain_contract_fixtures",
        cmd=[sys.executable, str(SCRIPTS / "check_persona_dream_spine_chain.py"), "--receipt-dir", str(receipt_dir)],
        cwd=ROOT,
        expected_exit=0,
        receipt_path=receipt_dir / "spine_chain_validator_receipt.v1.json",
        timeout_s=timeout_s,
    )
    return result


def build_receipt(output_root: Path, timeout_s: int) -> dict[str, Any]:
    started = time.monotonic()
    output_root.mkdir(parents=True, exist_ok=True)
    receipt_root = output_root / "subreceipts"
    receipt_root.mkdir(parents=True, exist_ok=True)

    checks: list[dict[str, Any]] = []
    checks.append(_autonomous_fixture_checks(output_root, timeout_s))
    for spec in _checker_specs(receipt_root):
        checks.append(
            _run_command(
                name=str(spec["name"]),
                cmd=[sys.executable, str(SCRIPTS / spec["script"]), *spec["args"]],
                cwd=ROOT,
                expected_exit=0,
                receipt_path=spec["receipt"],
                timeout_s=timeout_s,
            )
        )
    checks.append(_run_spine_chain(receipt_root, timeout_s))

    failed = [check for check in checks if check.get("errors")]
    passed_count = len(checks) - len(failed)
    pass_rate = passed_count / len(checks) if checks else 0.0
    status = PASS_STATUS if not failed and pass_rate == 1.0 else BLOCKED_STATUS
    observed_blockers = sorted(
        {
            str(blocker)
            for check in checks
            for blocker in (check.get("observed_blockers") or [])
        }
    )

    return {
        "schema": "persona_dream.pipeline_robustness_check.v1",
        "created_at": _now_iso(),
        "status": status,
        "output_root": str(output_root),
        "processing_time_s": round(time.monotonic() - started, 3),
        "check_count": len(checks),
        "passed_count": passed_count,
        "failed_count": len(failed),
        "minimum_pass_rate": 1.0,
        "pass_rate": pass_rate,
        "mocked": False,
        "live": False,
        "fixture_backed": True,
        "paid_call_authorized": False,
        "provider_live": False,
        "actual_provider_call_attempts": 0,
        "human_content_judgment_required": False,
        "coverage": {
            "pipeline_checks_robust_end_to_end": "PARTIAL_OFFLINE_FIXTURE_COVERAGE",
            "stage_lineage_hash_recompute": "PARTIAL_OFFLINE_FIXTURE_COVERAGE",
            "autonomous_without_human_content_judgment": "FIXTURE_BACKED_STATIC_AND_VIDEO_PLAN_GENERATION",
            "negative_fixtures_fail_closed": "MULTI_FAMILY_OFFLINE_FIXTURE_COVERAGE",
        },
        "observed_blockers": observed_blockers,
        "checks": checks,
        "claims": {
            "proves": [
                "fixture-backed static dream generation writes the required artifacts without human content judgment",
                "fixture-backed video_plan generation writes the required artifacts without human content judgment",
                "existing contract, lineage, stale-write, respawn, run-state, run-root, provider-routing, and FAL-preflight fixture families execute under one deterministic harness",
                "negative fixture families in this harness fail closed with their expected blockers",
            ]
            if status == PASS_STATUS
            else [],
            "does_not_prove": [
                "live memory recall",
                "semantic quality of a dream",
                "human preference or acceptance",
                "paid provider execution",
                "complete Phase 01-16 live runtime execution",
                "that every repository checker recomputes every transitive hash dependency",
                "repeatability beyond these fixture families",
            ],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--receipt-out", type=Path)
    parser.add_argument("--timeout-s", type=int, default=120)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    run_id = time.strftime("persona-dream-robustness-%Y%m%dT%H%M%SZ", time.gmtime())
    output_root = (args.output_root or DEFAULT_OUTPUT_ROOT / run_id).resolve()
    receipt_out = (args.receipt_out or output_root / "pipeline_robustness_receipt.v1.json").resolve()

    receipt = build_receipt(output_root, args.timeout_s)
    _write_json(receipt_out, receipt)
    receipt["receipt_path"] = str(receipt_out)
    _write_json(receipt_out, receipt)

    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(str(receipt_out))
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
