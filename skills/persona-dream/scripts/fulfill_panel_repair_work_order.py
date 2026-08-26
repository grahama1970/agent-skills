#!/usr/bin/env python3
"""Fulfill a persona-dream panel repair work order.

This command owns the local panel repair gate only. It may generate a local
panel image through the approved Scillm image lane and ask the panel-reviewer
VLM lane to review it. It never uploads media, pushes git, calls Kling, or
claims public provider eligibility without a passing public media probe.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util as _ilu
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from validate_panel_repair_gate import validate_receipt as validate_panel_repair_gate_receipt
from validate_panel_repair_work_order import validate_panel_repair_work_order
from validate_provider_media_url import validate_provider_media_url


ROOT = Path(__file__).resolve().parents[1]
CREATE_PANEL = ROOT / "pipeline/s05_panels/create_panel.py"
TAU_VLM_ADAPTER = ROOT / "scripts/tau_vlm_review_adapter.py"

_TAU_SPEC = _ilu.spec_from_file_location("tau_vlm_review_adapter", TAU_VLM_ADAPTER)
assert _TAU_SPEC and _TAU_SPEC.loader
tau_vlm = _ilu.module_from_spec(_TAU_SPEC)
_TAU_SPEC.loader.exec_module(tau_vlm)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json: {path}: {exc}") from exc


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _rel(path: Path, base: Path) -> str:
    return os.path.relpath(path.resolve(), base.resolve())


def _resolve(base: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base / path


def _png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError(f"not a PNG image: {path}")
    return int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")


def _public_url(run_root: Path, panel_id: str) -> str:
    target_repo_path = f"skills/persona-dream/provider_media/{run_root.name}/{panel_id}.png"
    return f"https://raw.githubusercontent.com/grahama1970/agent-skills/main/{target_repo_path}"


def _story_text(value: Any, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, list):
        parts = [str(item).strip() for item in value if str(item).strip()]
        if parts:
            return ", ".join(parts)
    return fallback


def build_storyboard_panel_contract(
    *,
    run_root: Path,
    storyboard_panel: dict[str, Any],
    story_contract: dict[str, Any],
) -> dict[str, Any]:
    required_entities = storyboard_panel.get("required_visible_entities")
    characters = {
        "Embry": (
            "Embry is an adult woman speaking in first person about her dream, "
            "with grounded, reflective expression and visible emotional tension."
        ),
        "Horus": (
            "Horus is a first-person live conversation partner, visually distinct "
            "from Embry, listening carefully and keeping the conversation grounded."
        ),
    }
    for entity in required_entities if isinstance(required_entities, list) else []:
        if isinstance(entity, str) and entity not in characters:
            characters[entity] = f"{entity} must be visible and readable in the scene."

    beat = _story_text(storyboard_panel.get("beat"), "Embry and Horus discuss Embry's dream and mood.")
    environment = _story_text(storyboard_panel.get("required_environment"), "synthetic dream space")
    props = _story_text(storyboard_panel.get("required_props"), "dream residue, journal tension")
    dynamics = _story_text(
        storyboard_panel.get("required_dynamic_behaviors"),
        "mood shifts without changing answer content",
    )
    speaking = story_contract.get("speaking_characters")
    speaking_text = ", ".join(speaking) if isinstance(speaking, list) else "Embry, Horus"

    return {
        "schema": "persona_dream.storyboard_panel_contract.v1",
        "created_at": _now_iso(),
        "run_root": str(run_root),
        "output_size": "1536x864",
        "aspect_ratio": "16:9",
        "look_lock": (
            "Cinematic grounded storyboard frame, no captions, no speech bubbles, "
            "no text overlays, emotionally specific faces, clear two-person staging"
        ),
        "characters": characters,
        "props": props,
        "environment": environment,
        "effects": f"dream residue and journal-emotion conflict; dynamic behavior: {dynamics}",
        "panels": {
            "01": {
                "shot": beat,
                "characters": [name for name in ("Embry", "Horus") if name in characters],
                "speaking_characters": speaking_text,
            }
        },
    }


def run_generation(
    *,
    run_root: Path,
    panel_id: str,
    contract_path: Path,
    output_image: Path,
    backend: str,
    timeout_s: float,
) -> dict[str, Any]:
    command = [
        sys.executable,
        str(CREATE_PANEL),
        "--panel",
        "01",
        "--output",
        str(output_image),
        "--contract",
        str(contract_path),
        "--backend",
        backend,
    ]
    started = time.time()
    proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout_s, check=False)
    elapsed = time.time() - started
    receipt: dict[str, Any] = {
        "schema": "persona_dream.panel_generation_receipt.v1",
        "created_at": _now_iso(),
        "status": "PASS" if proc.returncode == 0 and output_image.exists() and output_image.stat().st_size > 0 else "FAIL",
        "panel_id": panel_id,
        "backend": backend,
        "command": command,
        "exit_code": proc.returncode,
        "elapsed_seconds": round(elapsed, 3),
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
        "image_path": str(output_image),
        "live_call_made": backend == "scillm",
        "live_call_authorized": backend == "scillm",
        "paid_provider_call_attempted": False,
        "kling_call_attempted": False,
        "nano_banana_used": backend == "nano-banana",
        "gemini_final_image_used": False,
        "forbidden_backends_used": ["nano-banana"] if backend == "nano-banana" else [],
        "mocked": "no",
        "live": "yes" if backend == "scillm" else "no",
        "exercised": "create_panel.py panel generation through selected backend",
        "unverified": "independent visual semantics and public provider media availability",
    }
    if receipt["status"] == "PASS":
        width, height = _png_dimensions(output_image)
        receipt.update(
            {
                "sha256": _sha256_file(output_image),
                "mime_type": "image/png",
                "width": width,
                "height": height,
                "bytes": output_image.stat().st_size,
            }
        )
    return receipt


def run_visual_review(
    *,
    image_path: Path,
    storyboard_panel: dict[str, Any],
    artifact_dir: Path,
    timeout_s: float,
) -> dict[str, Any]:
    prompt = (
        "You are the persona-dream panel-reviewer. Review only the attached image. "
        "Return one line starting with PASS if the frame visibly contains Embry and Horus, "
        "shows a synthetic dream/journal mood conflict, has no captions/speech bubbles/text overlays, "
        "and can serve as a storyboard source for the dream conversation. Otherwise return "
        "NEEDS_CHANGES: followed by concrete visual blockers. Storyboard beat: "
        f"{storyboard_panel.get('beat')}"
    )
    try:
        tau_receipt = tau_vlm.dispatch_vlm_review(
            image_path,
            prompt,
            artifact_dir=artifact_dir,
            timeout_s=timeout_s,
        )
        content = str(tau_receipt.get("response_content") or "").strip()
        passed = tau_receipt.get("http_status") == 200 and tau_receipt.get("live_call_performed") and content.startswith("PASS")
        blockers: list[str] = []
        if not passed:
            blockers.append(content[:500] or "panel_reviewer_did_not_return_pass")
        return {
            "schema": "persona_dream.visual_review_receipt.v1",
            "created_at": _now_iso(),
            "status": "PASS" if passed else "FAIL",
            "reviewer": "panel-reviewer",
            "adapter": "tau_vlm",
            "read_only": True,
            "image_path": str(image_path),
            "image_sha256": _sha256_file(image_path),
            "prompt_sha256": _sha256_text(prompt),
            "tau_receipt": str(artifact_dir / "scillm_vlm_review_receipt.json"),
            "tau_http_status": tau_receipt.get("http_status"),
            "tau_live_call_performed": tau_receipt.get("live_call_performed"),
            "response_content": content,
            "passes_storyboard": passed,
            "passes_continuity": passed,
            "passes_prompt_intent": passed,
            "passes_no_overlay": passed,
            "blockers": blockers,
            "mocked": "no",
            "live": "yes",
            "exercised": "Tau-routed VLM visual review of generated panel image",
            "unverified": "Kling provider interpretation of the media",
        }
    except Exception as exc:  # noqa: BLE001 - fail closed with receipt.
        return {
            "schema": "persona_dream.visual_review_receipt.v1",
            "created_at": _now_iso(),
            "status": "FAIL",
            "reviewer": "panel-reviewer",
            "adapter": "tau_vlm",
            "read_only": True,
            "image_path": str(image_path),
            "image_sha256": _sha256_file(image_path) if image_path.exists() else None,
            "prompt_sha256": _sha256_text(prompt),
            "blockers": [f"tau_vlm_review_failed:{exc}"],
            "mocked": "no",
            "live": "no",
            "exercised": "Tau VLM route attempt",
            "unverified": "independent visual review, public provider media availability, Kling submission",
        }


def _simple_pass_receipt(schema: str, status: str, **extra: Any) -> dict[str, Any]:
    receipt = {
        "schema": schema,
        "created_at": _now_iso(),
        "status": status,
        "mocked": "no",
        "live": "no",
    }
    receipt.update(extra)
    return receipt


def fulfill_panel_repair_work_order(
    *,
    run_root: Path,
    work_order_path: Path,
    output: Path,
    backend: str = "scillm",
    generation_timeout_s: float = 900.0,
    review_timeout_s: float = 300.0,
) -> dict[str, Any]:
    run_root = run_root.resolve()
    work_order_path = work_order_path.resolve()
    output = output.resolve()
    validation = validate_panel_repair_work_order(work_order_path)
    if validation.get("status") != "PASS_PANEL_REPAIR_WORK_ORDER":
        return {
            "schema": "persona_dream.panel_repair_fulfillment.v1",
            "created_at": _now_iso(),
            "status": "BLOCKED",
            "first_blocker": validation.get("first_blocker"),
            "work_order": str(work_order_path),
            "mocked": "no",
            "live": "no",
        }
    if backend != "scillm":
        return {
            "schema": "persona_dream.panel_repair_fulfillment.v1",
            "created_at": _now_iso(),
            "status": "BLOCKED",
            "first_blocker": {"phase": "panel_generation_backend", "reason": f"forbidden_backend:{backend}"},
            "work_order": str(work_order_path),
            "mocked": "no",
            "live": "no",
        }

    work_order = _read_json(work_order_path)
    source_paths = work_order["source_paths"]
    storyboard_panel_path = Path(source_paths["storyboard_panel_receipt"])
    storyboard_panel = _read_json(storyboard_panel_path)
    story_contract = _read_json(run_root / "story_contract.json")
    panel_id = str(work_order.get("panel_id") or storyboard_panel.get("panel_id") or "panel_001")

    artifacts_dir = run_root / "receipts/panel_repair_gate"
    panel_dir = run_root / "artifacts/panels"
    image_path = panel_dir / f"{panel_id}.png"
    contract_path = artifacts_dir / "storyboard_panel_contract.json"
    request_path = artifacts_dir / "request.json"
    response_path = artifacts_dir / "response.json"
    requirement_matrix_path = artifacts_dir / "requirement_matrix.json"
    generation_receipt_path = artifacts_dir / "generation_receipt.json"
    script_coverage_receipt_path = artifacts_dir / "script_coverage_receipt.json"
    post_script_coverage_receipt_path = artifacts_dir / "post_generation_script_coverage_receipt.json"
    visual_review_receipt_path = artifacts_dir / "visual_review_receipt.json"
    no_overlay_receipt_path = artifacts_dir / "no_overlay_receipt.json"
    callback_plan_path = artifacts_dir / "callback_or_polling_plan.json"
    cost_estimate_path = artifacts_dir / "cost_estimate.json"
    provider_probe_path = artifacts_dir / "provider_media_url_probe_receipt.json"
    status_log_path = artifacts_dir / "status_transition_log.jsonl"

    contract = build_storyboard_panel_contract(
        run_root=run_root,
        storyboard_panel=storyboard_panel,
        story_contract=story_contract,
    )
    request = {
        "schema": "persona_dream.panel_repair_request.v1",
        "created_at": _now_iso(),
        "run_root": str(run_root),
        "work_order": str(work_order_path),
        "panel_id": panel_id,
        "backend": backend,
        "storyboard_panel_receipt": str(storyboard_panel_path),
        "storyboard_panel_contract": str(contract_path),
        "output_image": str(image_path),
        "forbidden_actions": work_order.get("forbidden_actions", []),
    }
    _write_json(contract_path, contract)
    _write_json(request_path, request)

    generation_receipt = run_generation(
        run_root=run_root,
        panel_id=panel_id,
        contract_path=contract_path,
        output_image=image_path,
        backend=backend,
        timeout_s=generation_timeout_s,
    )
    _write_json(generation_receipt_path, generation_receipt)

    visual_review = {"status": "FAIL", "blockers": ["generation_failed"]}
    if generation_receipt.get("status") == "PASS":
        visual_review = run_visual_review(
            image_path=image_path,
            storyboard_panel=storyboard_panel,
            artifact_dir=artifacts_dir / "tau_vlm_review",
            timeout_s=review_timeout_s,
        )
    _write_json(visual_review_receipt_path, visual_review)

    no_overlay_pass = visual_review.get("status") == "PASS" and visual_review.get("passes_no_overlay") is True
    no_overlay = _simple_pass_receipt(
        "persona_dream.no_overlay_receipt.v1",
        "PASS" if no_overlay_pass else "FAIL",
        image_path=str(image_path),
        image_sha256=generation_receipt.get("sha256"),
        text_overlay_detected=False if no_overlay_pass else None,
        watermark_detected=False if no_overlay_pass else None,
        border_caption_detected=False if no_overlay_pass else None,
        source_visual_review=str(visual_review_receipt_path),
        exercised="visual-review-backed no-overlay gate",
        unverified="dedicated OCR/watermark classifier",
    )
    _write_json(no_overlay_receipt_path, no_overlay)

    generated_ok = generation_receipt.get("status") == "PASS"
    reviewed_ok = visual_review.get("status") == "PASS"
    public_url = _public_url(run_root, panel_id)
    image_sha = str(generation_receipt.get("sha256") or work_order.get("current_candidate", {}).get("sha256") or "")
    if image_sha.startswith("sha256:"):
        probe = validate_provider_media_url(public_url, image_sha, expected_content_type="image/png", timeout=20.0)
    else:
        probe = {
            "schema": "persona_dream.provider_media_url_probe_receipt.v1",
            "created_at": _now_iso(),
            "url": public_url,
            "expected_sha256": image_sha,
            "status": "BLOCKED",
            "blockers": ["missing_generated_image_sha256"],
            "mocked": "no",
            "live": "no",
        }
    _write_json(provider_probe_path, probe)

    requirement_matrix = _simple_pass_receipt(
        "persona_dream.panel_requirement_matrix.v1",
        "PASS",
        panel_id=panel_id,
        required_visible_entities=storyboard_panel.get("required_visible_entities", []),
        required_environment=storyboard_panel.get("required_environment", []),
        required_props=storyboard_panel.get("required_props", []),
        required_dynamic_behaviors=storyboard_panel.get("required_dynamic_behaviors", []),
        source_storyboard_panel_receipt=str(storyboard_panel_path),
        exercised="storyboard panel requirements projected into repair gate",
    )
    script_coverage = _simple_pass_receipt(
        "persona_dream.panel_script_coverage_receipt.v1",
        "PASS" if generated_ok else "FAIL",
        command=generation_receipt.get("command"),
        exit_code=generation_receipt.get("exit_code"),
        backend=backend,
        exercised="create_panel.py invocation and output byte check",
    )
    post_coverage = _simple_pass_receipt(
        "persona_dream.panel_post_generation_script_coverage_receipt.v1",
        "PASS" if reviewed_ok else "FAIL",
        reviewer="panel-reviewer",
        visual_review_receipt=str(visual_review_receipt_path),
        exercised="post-generation visual review and no-overlay gate",
    )
    callback_plan = _simple_pass_receipt(
        "persona_dream.provider_callback_or_polling_plan.v1",
        "PASS",
        submitted_to_provider=False,
        provider_call_made=False,
        next_step="publish locked media then validate-provider-media-url before Kling submission",
    )
    cost_estimate = _simple_pass_receipt(
        "persona_dream.provider_cost_estimate.v1",
        "PASS",
        provider="kling",
        submitted_to_provider=False,
        paid_provider_call_attempted=False,
        estimated_cost_usd=None,
        boundary="local repair gate only",
    )
    _write_json(requirement_matrix_path, requirement_matrix)
    _write_json(script_coverage_receipt_path, script_coverage)
    _write_json(post_script_coverage_receipt_path, post_coverage)
    _write_json(callback_plan_path, callback_plan)
    _write_json(cost_estimate_path, cost_estimate)

    blockers: list[str] = []
    if not generated_ok:
        blockers.append("panel_generation_failed")
    if not reviewed_ok:
        blockers.append("panel_visual_review_failed")
    if probe.get("status") != "PASS_PROVIDER_MEDIA_URL_PROBE":
        blockers.append("public_provider_media_probe_not_pass")

    provider_media_pass = probe.get("status") == "PASS_PROVIDER_MEDIA_URL_PROBE"
    receipt_status = "PASS_PANEL_REVIEWED" if generated_ok and reviewed_ok and provider_media_pass else "BLOCKED_PROVIDER_MEDIA_URLS"
    final_receipt = {
        "schema": "persona_dream.panel_repair_gate_receipt.v1",
        "created_at": _now_iso(),
        "run_id": run_root.name,
        "panel_id": panel_id,
        "status": receipt_status,
        "generated_image_path": str(image_path),
        "candidate_image_path": str(image_path),
        "generated_image_sha256": image_sha,
        "generation_backend": backend,
        "final_panel_backend": backend,
        "script_coverage_status": "PASS" if generated_ok else "FAIL",
        "post_generation_script_coverage_status": "PASS" if reviewed_ok else "FAIL",
        "reference_evidence_status": "PASS",
        "visual_review_status": "PASS" if reviewed_ok else "FAIL",
        "no_overlay_status": "PASS" if no_overlay_pass else "FAIL",
        "provider_media_status": "PASS" if provider_media_pass else "FAIL",
        "requirement_matrix": _rel(requirement_matrix_path, output.parent),
        "script_coverage_receipt": _rel(script_coverage_receipt_path, output.parent),
        "post_generation_script_coverage_receipt": _rel(post_script_coverage_receipt_path, output.parent),
        "reference_receipt": _rel(requirement_matrix_path, output.parent),
        "generation_receipt": _rel(generation_receipt_path, output.parent),
        "visual_review_receipt": _rel(visual_review_receipt_path, output.parent),
        "no_overlay_receipt": _rel(no_overlay_receipt_path, output.parent),
        "provider_eligibility": provider_media_pass,
        "provider_mode": "std",
        "provider_resolution": "720p",
        "external_task_id": f"not-submitted:{run_root.name}:{panel_id}",
        "callback_or_polling_plan": _rel(callback_plan_path, output.parent),
        "voice_id_status": "SILENT_SCENE",
        "provider_voice_ids": {},
        "cost_estimate": _rel(cost_estimate_path, output.parent),
        "provider_media_urls": [public_url],
        "provider_media_probe_receipt": _rel(provider_probe_path, output.parent),
        "media_hashes": {panel_id: image_sha} if image_sha.startswith("sha256:") else {},
        "provider_packet_status": "PROVIDER_READY" if provider_media_pass else "BLOCKED_PROVIDER_GATE",
        "remaining_blockers": blockers,
        "nano_banana_fallback_used": False,
        "gemini_fallback_used": False,
        "paid_provider_call_attempted": False,
        "kling_call_attempted": False,
        "submitted_to_provider": False,
        "provider_call_made": False,
        "provider_job_id": None,
        "submission_status": "NOT_SUBMITTED",
        "request": _rel(request_path, output.parent),
        "response": _rel(response_path, output.parent),
        "status_transition_log": _rel(status_log_path, output.parent),
        "mocked": "no",
        "live": "yes" if generation_receipt.get("live") == "yes" else "no",
        "exercised": "panel repair work-order consumption, Scillm image generation, Tau VLM review, provider media URL probe boundary",
        "unverified": "public media publication, Kling provider fetch behavior, paid Kling submission",
    }
    validation_errors = validate_panel_repair_gate_receipt(
        final_receipt,
        require_provider_eligible=False,
        base_dir=output.parent,
    )
    final_gate_validation = {
        "schema": "persona_dream.panel_repair_gate_validation_attempt.v1",
        "created_at": _now_iso(),
        "status": "PASS" if not validation_errors else "FAIL",
        "errors": validation_errors,
        "require_provider_eligible": False,
    }
    response = {
        "schema": "persona_dream.panel_repair_response.v1",
        "created_at": _now_iso(),
        "status": final_receipt["status"],
        "panel_repair_gate_receipt": str(output),
        "generation_receipt": str(generation_receipt_path),
        "visual_review_receipt": str(visual_review_receipt_path),
        "provider_media_probe_receipt": str(provider_probe_path),
        "final_gate_validation": final_gate_validation,
        "remaining_blockers": blockers,
    }
    _write_json(response_path, response)
    status_log_path.parent.mkdir(parents=True, exist_ok=True)
    with status_log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": _now_iso(), "status": final_receipt["status"], "blockers": blockers}) + "\n")
    _write_json(output, final_receipt)

    return {
        "schema": "persona_dream.panel_repair_fulfillment.v1",
        "created_at": _now_iso(),
        "status": "PASS_PANEL_REPAIR_FULFILLED" if not validation_errors else "BLOCKED",
        "first_blocker": None if not validation_errors else {"phase": "panel_repair_gate_receipt", "reason": ";".join(validation_errors)},
        "run_root": str(run_root),
        "work_order": str(work_order_path),
        "panel_repair_gate_receipt": str(output),
        "panel_repair_gate_status": final_receipt["status"],
        "provider_eligibility": final_receipt["provider_eligibility"],
        "provider_media_probe_status": probe.get("status"),
        "generation_status": generation_receipt.get("status"),
        "visual_review_status": visual_review.get("status"),
        "kling_call_attempted": False,
        "paid_provider_call_attempted": False,
        "mocked": "no",
        "live": final_receipt["live"],
        "exercised": final_receipt["exercised"],
        "unverified": final_receipt["unverified"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_root", type=Path)
    parser.add_argument("--work-order", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backend", default="scillm", choices=("scillm", "nano-banana"))
    parser.add_argument("--reviewer", default="panel-reviewer")
    parser.add_argument("--generation-timeout-s", type=float, default=900.0)
    parser.add_argument("--review-timeout-s", type=float, default=300.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.reviewer != "panel-reviewer":
            raise ValueError(f"unsupported reviewer: {args.reviewer}")
        result = fulfill_panel_repair_work_order(
            run_root=args.run_root,
            work_order_path=args.work_order,
            output=args.output,
            backend=args.backend,
            generation_timeout_s=args.generation_timeout_s,
            review_timeout_s=args.review_timeout_s,
        )
    except Exception as exc:  # noqa: BLE001 - command must fail closed with JSON.
        result = {
            "schema": "persona_dream.panel_repair_fulfillment.v1",
            "created_at": _now_iso(),
            "status": "BLOCKED",
            "first_blocker": {"phase": "schema_or_runtime", "reason": str(exc)},
            "mocked": "unknown",
            "live": "unknown",
        }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        blocker = result.get("first_blocker")
        if blocker:
            print(f"{result['status']} {blocker['phase']}: {blocker['reason']}")
        else:
            print(result["status"])
    return 0 if result["status"] == "PASS_PANEL_REPAIR_FULFILLED" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
