"""Regression tests for the #1641 unattended acceptance verifier."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


_MODULE_PATH = Path(__file__).resolve().parents[1] / "evals/unattended_acceptance.py"
_SPEC = importlib.util.spec_from_file_location("unattended_acceptance_eval", _MODULE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"cannot load unattended acceptance verifier from {_MODULE_PATH}")
unattended_acceptance = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = unattended_acceptance
_SPEC.loader.exec_module(unattended_acceptance)


def _base_projection(active_work: list[dict[str, object]]) -> dict[str, list[object]]:
    return {
        "historical_error": [],
        "unresolved_error": [],
        "active_work": active_work,
        "dependency_wait": [],
        "resolved_closure": [],
    }


def _scenario_checks(projection: dict[str, list[object]]) -> dict[str, bool]:
    return unattended_acceptance.scenario_checks(
        status={"schema": "status"},
        dry_tick={"result": {"exit_code": 0}, "json": {}},
        receipts=[],
        closures=[],
        projection=projection,
        cron_starts=[],
        operations=[],
        issue_states={},
    )


def test_live_current_task_writer_is_not_stranded_work() -> None:
    projection = _base_projection([
        {
            "ref": "grahama1970/agent-skills#1641",
            "phase": "running",
            "writer_active": True,
            "recovery_command": "recover_primary.py --root repo --apply",
        }
    ])

    checks = _scenario_checks(projection)

    assert checks["no_stranded_current_task_work"] is True


def test_dead_current_task_entry_is_stranded_work() -> None:
    projection = _base_projection([
        {
            "ref": "grahama1970/agent-skills#1641",
            "phase": "retryable",
            "writer_active": False,
            "recovery_command": "recover_primary.py --root repo --apply",
        }
    ])

    checks = _scenario_checks(projection)

    assert checks["no_stranded_current_task_work"] is False
