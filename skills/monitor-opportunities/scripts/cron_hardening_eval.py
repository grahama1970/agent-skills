from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise AssertionError(f"expected object JSON: {path}")
    return data


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scheduler-exec-receipt", required=True, type=Path)
    args = parser.parse_args()

    receipt = _read_json(args.scheduler_exec_receipt)
    checks = receipt.get("checks") or {}
    failed = sorted(key for key, value in checks.items() if not value)
    _assert(receipt.get("status") == "PASS", f"scheduler exec status not PASS: {receipt.get('status')}")
    _assert(receipt.get("live") is True, "scheduler exec was not live")
    _assert(receipt.get("mocked") is False, "scheduler exec was mocked")
    _assert(receipt.get("external_effects") is False, "scheduler exec had external effects")
    _assert(not failed, f"scheduler exec failed checks: {failed}")

    preflight = receipt.get("preflight") or {}
    command = str(preflight.get("command") or "")
    _assert("--skip-tracker" in command, "promoted cron command does not skip tracker")
    _assert("--skip-ats-memory" in command, "promoted cron command does not skip ATS memory writes")
    _assert("--tau-semantic-provider" in command, "promoted cron command does not enable Tau provider")
    _assert(
        "--tau-semantic-handler gpt-5.5-high" in command,
        "promoted cron command is not pinned to the live non-browser Tau semantic handler",
    )

    schedule_path = Path(str(preflight.get("schedule_receipt") or ""))
    _assert(schedule_path.is_file(), f"schedule receipt missing: {schedule_path}")
    schedule = _read_json(schedule_path)
    effect_policy = schedule.get("effect_policy") or {}
    _assert(effect_policy.get("tracker") == "SKIPPED", "tracker effect policy is not SKIPPED")
    _assert(
        effect_policy.get("ats_selector_memory_write") == "SKIPPED",
        "ATS selector memory write policy is not SKIPPED",
    )
    _assert(
        effect_policy.get("prior_application_history") == "ENABLED",
        "prior application history read is not enabled",
    )
    print("TRACKER_POLICY_OK")
    print("ATS_MEMORY_POLICY_OK")

    run_dir = Path(str(receipt.get("nightly_out") or ""))
    _assert(run_dir.is_dir(), f"nightly output dir missing: {run_dir}")
    nightly = _read_json(run_dir / "nightly-receipt.json")
    steps = nightly.get("steps") or {}

    tracker = steps.get("tracker") or {}
    _assert(tracker.get("skipped") is True, f"tracker was not skipped: {tracker}")
    _assert(int(tracker.get("tracked") or 0) == 0, f"tracker created issues: {tracker}")

    ats = steps.get("ats_form_capture") or {}
    ats_results = ats.get("results") or []
    for row in ats_results:
        _assert(row.get("memory_stored") in {False, None}, f"ATS memory write happened: {row}")

    run_receipt = _read_json(run_dir / "run-receipt.json")
    application_history = _read_json(run_dir / "discovery" / "application-history-receipt.json")
    if application_history.get("status") != "OK":
        codes = {
            str(row.get("code") or "")
            for row in run_receipt.get("degraded_contracts", [])
            if isinstance(row, dict)
        }
        _assert(
            "APPLICATION_HISTORY_UNKNOWN" in codes,
            "application history degraded without APPLICATION_HISTORY_UNKNOWN contract",
        )
    print("APPLICATION_HISTORY_DEGRADATION_EXPLICIT_OK")

    browser_control = steps.get("browser_control") or {}
    tab_close_failures = int((browser_control.get("counts") or {}).get("tab_close_failed") or 0)
    _assert(tab_close_failures == 0, f"tab close cleanup failures remain: {browser_control}")
    print("SURF_TAB_CLEANUP_OK")

    tau = steps.get("tau_semantic") or {}
    provider_results = tau.get("provider_results") or []
    pass_indexes = [
        index
        for index, row in enumerate(provider_results)
        if row.get("status") == "PASS" and row.get("provider_live") is True
    ]
    _assert(tau.get("provider_live") is True, f"Tau provider was not live: {tau}")
    _assert(int(tau.get("installed_addenda") or 0) == 1, f"expected one installed addendum: {tau}")
    _assert(pass_indexes, f"no provider-live PASS result: {provider_results}")
    _assert(
        provider_results[pass_indexes[0]].get("handler") == "gpt-5.5-high",
        f"provider-live PASS did not use gpt-5.5-high: {provider_results}",
    )
    _assert(
        len(provider_results) == pass_indexes[0] + 1,
        f"provider loop continued after first provider-live PASS: {provider_results}",
    )
    print("TAU_PROVIDER_HANDLER_OK")
    print("TAU_PROVIDER_EARLY_STOP_OK")
    print("CRON_HARDENING_EVAL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
