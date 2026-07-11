#!/usr/bin/env python3
"""Regression checks for the storyboard-first dry-run fixture.

These checks intentionally mutate a temporary generated fixture to prove the
validator fails closed for the failure modes that previously caused false green
workflow claims.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import shutil
import tempfile
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
FIXTURE_SCRIPT = SCRIPT_DIR / "storyboard_first_fixture.py"


def load_fixture_module() -> Any:
    spec = importlib.util.spec_from_file_location("storyboard_first_fixture", FIXTURE_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {FIXTURE_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def assert_failed(validation: dict[str, Any], expected_check: str) -> None:
    if validation.get("status") != "FAILED_AUTOMATED_CHECK":
        raise AssertionError(f"expected FAILED_AUTOMATED_CHECK, got {validation.get('status')}")
    failed = {check["name"]: check for check in validation.get("checks", []) if not check.get("ok")}
    if expected_check not in failed:
        raise AssertionError(
            f"expected failed check {expected_check!r}; got {sorted(failed)}"
        )


def clone_fixture(src: Path, name: str, workspace: Path) -> Path:
    dst = workspace / name
    shutil.copytree(src, dst)
    return dst


def main() -> None:
    fixture = load_fixture_module()
    with tempfile.TemporaryDirectory(prefix="persona-dream-storyboard-regressions.") as tmp:
        workspace = Path(tmp)
        root = workspace / "base"
        manifest = fixture.build_fixture(
            root,
            image_backend="fixture",
            create_image_backend="scillm",
            create_image_model="gpt-image-2",
            strict_generated_images=False,
            image_timeout_s=30,
        )
        if manifest.get("status") != "ACCEPTED_AUTOMATED":
            raise AssertionError(f"base fixture did not validate: {manifest.get('status')}")
        base_validation = fixture.validate_fixture(root)
        if base_validation.get("failed") != 0:
            raise AssertionError(f"base fixture has failed checks: {base_validation}")

        refs_gate = __import__("subprocess").run(
            [
                sys.executable,
                str(SCRIPT_DIR / "validate_phase_05_contact_sheet_gate.py"),
                "--run-root",
                str(root),
                "--refs-only",
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if refs_gate.returncode != 0:
            raise AssertionError(
                "reference_sheets dimension gate failed for base fixture: "
                + (refs_gate.stdout or refs_gate.stderr)
            )


        stretched = clone_fixture(root, "stretched-layout", workspace)
        layout_path = stretched / "reference_sheets" / "layout_validation.json"
        layout = read_json(layout_path)
        layout["nonuniform_scaling_detected"] = True
        write_json(layout_path, layout)
        assert_failed(fixture.validate_fixture(stretched), "layout_no_nonuniform_scaling")

        missing_storyboard = clone_fixture(root, "missing-storyboard", workspace)
        (missing_storyboard / "storyboard" / "storyboard_board.png").unlink()
        assert_failed(
            fixture.validate_fixture(missing_storyboard),
            "exists:storyboard/storyboard_board.png",
        )

        paid_call = clone_fixture(root, "paid-call", workspace)
        provider_path = paid_call / "provider_packet" / "provider_request_dry_run.json"
        provider = read_json(provider_path)
        provider["paid_call_performed"] = True
        write_json(provider_path, provider)
        assert_failed(fixture.validate_fixture(paid_call), "provider_paid_false")

        review_only = clone_fixture(root, "review-page-only", workspace)
        (review_only / "stage_status_receipt.json").unlink()
        assert_failed(
            fixture.validate_fixture(review_only),
            "exists:stage_status_receipt.json",
        )

        missing_idea = clone_fixture(root, "missing-idea", workspace)
        (missing_idea / "idea_contract.json").unlink()
        assert_failed(fixture.validate_fixture(missing_idea), "exists:idea_contract.json")

        print(json.dumps(
            {
                "status": "ok",
                "base_root": str(root),
                "negative_fixtures": [
                    "stretched-layout",
                    "missing-storyboard",
                    "paid-call",
                    "review-page-only",
                    "missing-idea",
                ],
            },
            indent=2,
            sort_keys=True,
        ))


if __name__ == "__main__":
    main()
