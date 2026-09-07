#!/usr/bin/env python3
"""Validate and classify a local persona-dream P0 pipeline run root.

This validator is intentionally local-only. It performs no provider network calls
and never attempts a paid Kling submission.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

import jsonschema
from pydantic_step_gate import pydantic_first_check, pydantic_error_messages

PIPELINE = "persona-dream-end-to-end-pipeline-P0"
LEGACY_PAID_CALL_SCHEMA = "schemas/paid_call_approval_receipt.schema.json"
P0_PAID_CALL_SCHEMA = "schemas/pipeline_paid_call_approval_receipt.schema.json"
KLING_SCENE_PACKET_SCHEMA = "schemas/kling_scene_packet.schema.json"


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json: {path}: {exc}") from exc


def _repo_root_from_run_root(run_root: Path) -> Path:
    # Fixtures live at <repo>/fixtures/<name>. For copied run roots, the caller
    # can pass --repo-root explicitly.
    if run_root.parent.name == "fixtures":
        return run_root.parent.parent
    return Path.cwd()


def _validate(schema_path: Path, instance_path: Path) -> Any:
    schema = _load_json(schema_path)
    instance = _load_json(instance_path)
    jsonschema.Draft202012Validator.check_schema(schema)
    pydantic_first_check(schema, instance)
    jsonschema.Draft202012Validator(schema).validate(instance)
    return instance


def _validate_one_scene_contract(manifest: Dict[str, Any], loaded: Dict[str, Any]) -> bool:
    if manifest["mode"] != "one_scene_kling_dry_run":
        return False

    schema_ref = manifest["schema_refs"].get("kling_scene_packet")
    if schema_ref != KLING_SCENE_PACKET_SCHEMA:
        raise ValueError(f"unexpected Kling scene packet schema path: {schema_ref}")

    call = loaded.get("kling_scene_packet")
    if not isinstance(call, dict):
        raise ValueError("one_scene_kling_dry_run requires kling_scene_packet")

    if call.get("provider") != "kling":
        raise ValueError("Kling scene packet provider must be kling")
    if call.get("schema") != "kling.scene_packet.v1":
        raise ValueError("one-scene dry-run requires kling.scene_packet.v1")
    if call.get("paid_call_authorized") is not False:
        raise ValueError("Kling scene packet must not authorize paid calls")
    if call.get("status") != "GENERATED_UNREVIEWED":
        raise ValueError("one-scene dry-run scene packet must be GENERATED_UNREVIEWED")
    if len(call.get("multi_prompt", [])) != 1:
        raise ValueError("one-scene dry-run requires exactly one prompt block")
    if not call.get("image_list"):
        raise ValueError("Kling scene packet requires an image token manifest")
    if "<<<image_2>>>" not in call["multi_prompt"][0].get("provider_text", ""):
        raise ValueError("provider_text must bind Horus to an image token")
    if "<<<image_3>>>" not in call["multi_prompt"][0].get("provider_text", ""):
        raise ValueError("provider_text must bind Embry to an image token")
    if not call.get("polling_plan"):
        raise ValueError("Kling scene packet requires polling or callback behavior")
    if not call.get("live_call_block_reason"):
        raise ValueError("Kling scene packet requires a live-call block reason")

    return True


def validate_run(run_root: Path, repo_root: Path | None = None) -> Dict[str, Any]:
    run_root = run_root.resolve()
    repo_root = (repo_root or _repo_root_from_run_root(run_root)).resolve()

    manifest_path = run_root / "run_manifest.json"
    manifest = _validate(repo_root / "schemas/pipeline_run_manifest.schema.json", manifest_path)

    if manifest["pipeline"] != PIPELINE:
        raise ValueError(f"unexpected pipeline: {manifest['pipeline']}")

    paid_schema_ref = manifest["schema_refs"].get("pipeline_paid_call_approval_receipt")
    if paid_schema_ref == LEGACY_PAID_CALL_SCHEMA:
        raise ValueError(
            "P0 pipeline must not reference legacy paid-call schema path; "
            f"use {P0_PAID_CALL_SCHEMA}"
        )
    if paid_schema_ref != P0_PAID_CALL_SCHEMA:
        raise ValueError(f"unexpected P0 paid-call schema path: {paid_schema_ref}")

    loaded: Dict[str, Any] = {"run_manifest": manifest}
    for receipt_name, rel_receipt in manifest["receipt_paths"].items():
        schema_rel = manifest["schema_refs"][receipt_name]
        if schema_rel == LEGACY_PAID_CALL_SCHEMA:
            raise ValueError(f"{receipt_name} references legacy paid-call schema path")
        loaded[receipt_name] = _validate(repo_root / schema_rel, run_root / rel_receipt)

    one_scene_call_ready = _validate_one_scene_contract(manifest, loaded)

    stage = loaded["stage_receipt"]
    paid = loaded["pipeline_paid_call_approval_receipt"]
    provider = loaded["provider_readiness_receipt"]
    kling = loaded["kling_submit_gate_receipt"]
    terminal = loaded["pipeline_terminal_report"]

    run_ids = {name: doc.get("run_id") for name, doc in loaded.items() if isinstance(doc, dict)}
    if len(set(run_ids.values())) != 1:
        raise ValueError(f"inconsistent run_id values: {run_ids}")

    if not stage["inputs_complete"]:
        derived = "BLOCKED_MISSING_INPUT"
        expected_gate = "input"
    elif provider["ready_for_dry_run"] and not paid["live_submission_allowed"]:
        derived = "DRY_RUN_NOT_LIVE_SUBMITTABLE"
        expected_gate = "kling_submit"
    elif provider["ready_for_live_submit"] and paid["live_submission_allowed"]:
        derived = "PASS"
        expected_gate = "paid_call"
    else:
        derived = "BLOCKED_INCONSISTENT_RECEIPTS"
        expected_gate = "paid_call"

    if kling["decision"] != derived and derived != "PASS":
        raise ValueError(f"kling gate decision {kling['decision']} != derived status {derived}")
    if terminal["status"] != derived:
        raise ValueError(f"terminal status {terminal['status']} != derived status {derived}")
    if terminal["terminal_gate"] != expected_gate:
        raise ValueError(f"terminal gate {terminal['terminal_gate']} != expected gate {expected_gate}")
    if terminal["live_provider_call_made"] is not False or kling["attempted_live_submit"] is not False:
        raise ValueError("P0 validator requires no live provider call attempts")

    return {
        "run_id": manifest["run_id"],
        "status": derived,
        "terminal_gate": terminal["terminal_gate"],
        "live_provider_call_made": False,
        "paid_call_schema": paid_schema_ref,
        "one_scene_call_ready": one_scene_call_ready,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_root", type=Path, help="Path to a fixture or run root")
    parser.add_argument("--repo-root", type=Path, default=None, help="Repository root containing schemas/")
    parser.add_argument("--json", action="store_true", help="Print full JSON result instead of status only")
    args = parser.parse_args(argv)

    try:
        result = validate_run(args.run_root, args.repo_root)
    except Exception as exc:  # pragma: no cover - command-line failure path
        print(f"BLOCKED_SCHEMA_INVALID: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(result["status"])
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
