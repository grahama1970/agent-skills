#!/usr/bin/env python3
"""Validate a Persona Dream story contract.

This gate proves the story contract is a real accepted local artifact that can
feed storyboard planning. It does not prove visual quality, panel generation, or
provider readiness.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import jsonschema
from pydantic_step_gate import pydantic_error_messages


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas/story_contract.schema.json"
ACCEPTED_STATUSES = {
    "ACCEPTED_AUTOMATED",
    "ACCEPTED_MANUAL",
    "PASS_STORY_CONTRACT",
    "STORY_READY",
}


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json: {path}: {exc}") from exc


def _block(result: dict[str, Any], phase: str, reason: str, path: Path) -> dict[str, Any]:
    result["status"] = "BLOCKED"
    result["first_blocker"] = {"phase": phase, "reason": reason, "path": str(path)}
    return result


def validate_story_contract(contract_path: Path, *, run_root: Path | None = None) -> dict[str, Any]:
    contract_path = contract_path.resolve()
    base = run_root.resolve() if run_root else contract_path.parent
    schema = _read_json(SCHEMA)
    contract = _read_json(contract_path)
    result: dict[str, Any] = {
        "schema": "persona_dream.story_contract_validation.v1",
        "contract": str(contract_path),
        "run_root": str(base),
        "status": "PASS_STORY_CONTRACT",
        "first_blocker": None,
        "mocked": "yes" if "fixtures" in base.parts else "no",
        "live": "no",
        "exercised": "local story contract schema, accepted status, positive duration, nonempty story, nonempty speaking characters",
        "unverified": "live memory grounding, Look Lock/Script DNA execution, storyboard generation, panel visual review, provider/Kling execution",
    }

    pydantic_messages = pydantic_error_messages(schema, contract)
    if pydantic_messages:
        return _block(result, "story_contract", f"schema_validation:{pydantic_messages[0]}", contract_path)
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(contract), key=lambda error: list(error.path))
    if errors:
        return _block(result, "story_contract", f"schema_validation:{errors[0].message}", contract_path)

    status = contract.get("status")
    if status not in ACCEPTED_STATUSES:
        return _block(result, "story_contract", f"story_contract_not_accepted:{status}", contract_path)

    if float(contract.get("target_duration_s", 0)) <= 0:
        return _block(result, "story_contract", "target_duration_not_positive", contract_path)

    if not str(contract.get("seed", "")).strip():
        return _block(result, "story_contract", "missing_seed", contract_path)

    if not str(contract.get("story", "")).strip():
        return _block(result, "story_contract", "missing_story", contract_path)

    speaking_characters = contract.get("speaking_characters")
    if not isinstance(speaking_characters, list) or not speaking_characters:
        return _block(result, "story_contract", "missing_speaking_characters", contract_path)
    if any(not isinstance(character, str) or not character.strip() for character in speaking_characters):
        return _block(result, "story_contract", "invalid_speaking_character", contract_path)

    result["artifact_id"] = contract["artifact_id"]
    result["target_duration_s"] = contract["target_duration_s"]
    result["speaking_characters"] = speaking_characters
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path)
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = validate_story_contract(args.contract, run_root=args.run_root)
    except Exception as exc:
        result = {
            "schema": "persona_dream.story_contract_validation.v1",
            "contract": str(args.contract),
            "status": "BLOCKED",
            "first_blocker": {"phase": "schema_or_parse", "reason": str(exc), "path": str(args.contract)},
            "mocked": "unknown",
            "live": "no",
        }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        blocker = result.get("first_blocker")
        if blocker:
            print(f"{result['status']} {blocker['phase']}: {blocker['reason']}")
        else:
            print(result["status"])
    return 0 if result["status"] != "BLOCKED" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
