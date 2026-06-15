#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


TERMINAL_ISSUE_STATUSES = {"repaired"}
COURSE_CORRECTION_SCHEMA_VERSION = "book_extractor_course_correction.v1"
VALID_COURSE_CORRECTION_ACTIONS = {"patch_code", "repair_data", "rerun_command", "adjust_prompt", "cleanup_memory"}
VALID_COURSE_CORRECTION_OUTCOMES = {"accepted", "needs_repair", "blocked"}
REPAIR_ACTIONS_REQUIRE_ARTIFACTS = {"patch_code", "repair_data", "rerun_command", "adjust_prompt", "cleanup_memory"}
REQUIRED_COURSE_CORRECTION_FIELDS = (
    "schema_version",
    "correction_id",
    "issue_id",
    "action",
    "files_changed",
    "commands",
    "verification_artifacts",
    "outcome",
)
REQUIRED_FILES = [
    "job.yaml",
    "state.json",
    "events.jsonl",
    "issues.jsonl",
    "course_corrections.jsonl",
    "missing_features.jsonl",
    "commands.jsonl",
    "artifacts.json",
    "status.md",
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception as exc:
                rows.append({"__parse_error__": str(exc), "__line__": line_no})
                continue
            if not isinstance(row, dict):
                rows.append({"__parse_error__": "not_object", "__line__": line_no})
                continue
            row.setdefault("__line__", line_no)
            rows.append(row)
    return rows


def walk_paths(value: Any) -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for item in value.values():
            paths.extend(walk_paths(item))
    elif isinstance(value, list):
        for item in value:
            paths.extend(walk_paths(item))
    elif isinstance(value, str) and value.startswith("/"):
        paths.append(value)
    return paths


def validate_course_correction_row(row: dict[str, Any], *, controller_root: Path) -> list[dict[str, Any]]:
    defects: list[dict[str, Any]] = []
    correction_id = row.get("correction_id")
    missing = [field for field in REQUIRED_COURSE_CORRECTION_FIELDS if field not in row]
    if missing:
        defects.append({"kind": "course_correction_missing_fields", "correction_id": correction_id, "line": row.get("__line__"), "missing": missing})

    if row.get("schema_version") != COURSE_CORRECTION_SCHEMA_VERSION:
        defects.append(
            {
                "kind": "course_correction_invalid_schema_version",
                "correction_id": correction_id,
                "line": row.get("__line__"),
                "schema_version": row.get("schema_version"),
            }
        )

    for field in ("correction_id", "issue_id"):
        value = row.get(field)
        if not isinstance(value, str) or not value.strip():
            defects.append(
                {
                    "kind": f"course_correction_invalid_{field}",
                    "correction_id": correction_id,
                    "line": row.get("__line__"),
                    "actual_type": type(value).__name__,
                }
            )

    action = row.get("action")
    if action not in VALID_COURSE_CORRECTION_ACTIONS:
        defects.append({"kind": "course_correction_invalid_action", "correction_id": correction_id, "line": row.get("__line__"), "action": action})

    for field in ("files_changed", "commands"):
        value = row.get(field)
        if not isinstance(value, list):
            defects.append(
                {
                    "kind": f"course_correction_invalid_{field}_type",
                    "correction_id": correction_id,
                    "line": row.get("__line__"),
                    "actual_type": type(value).__name__,
                }
            )
            continue
        for index, item in enumerate(value):
            if not isinstance(item, str) or not item.strip():
                defects.append(
                    {
                        "kind": f"course_correction_invalid_{field}_entry",
                        "correction_id": correction_id,
                        "line": row.get("__line__"),
                        "index": index,
                    }
                )

    outcome = row.get("outcome")
    if outcome not in VALID_COURSE_CORRECTION_OUTCOMES:
        defects.append({"kind": "course_correction_invalid_outcome", "correction_id": correction_id, "line": row.get("__line__"), "outcome": outcome})
    raw_artifacts = row.get("verification_artifacts")
    artifacts_for_row: list[str] = []
    if raw_artifacts is None:
        artifacts_for_row = []
    elif not isinstance(raw_artifacts, list):
        defects.append(
            {
                "kind": "course_correction_invalid_verification_artifacts_type",
                "correction_id": correction_id,
                "line": row.get("__line__"),
                "actual_type": type(raw_artifacts).__name__,
            }
        )
    else:
        for index, item in enumerate(raw_artifacts):
            if not isinstance(item, str) or not item.strip():
                defects.append(
                    {
                        "kind": "course_correction_invalid_verification_artifact",
                        "correction_id": correction_id,
                        "line": row.get("__line__"),
                        "index": index,
                    }
                )
                continue
            artifacts_for_row.append(item)

    if action in REPAIR_ACTIONS_REQUIRE_ARTIFACTS and not artifacts_for_row:
        defects.append({"kind": "course_correction_missing_verification_artifacts", "correction_id": correction_id, "line": row.get("__line__")})
    for artifact in artifacts_for_row:
        path = Path(artifact)
        if not path.is_absolute():
            defects.append(
                {
                    "kind": "course_correction_non_absolute_verification_artifact_path",
                    "correction_id": correction_id,
                    "line": row.get("__line__"),
                    "path": artifact,
                }
            )
            continue
        if not path.exists():
            defects.append(
                {
                    "kind": "course_correction_missing_verification_artifact_path",
                    "correction_id": correction_id,
                    "line": row.get("__line__"),
                    "path": artifact,
                }
            )

    return defects


def validate(controller_root: Path) -> dict[str, Any]:
    defects: list[dict[str, Any]] = []
    missing_files = [name for name in REQUIRED_FILES if not (controller_root / name).exists()]
    for name in missing_files:
        defects.append({"kind": "missing_required_file", "path": str(controller_root / name)})

    state: dict[str, Any] = {}
    artifacts: dict[str, Any] = {}
    if (controller_root / "state.json").exists():
        try:
            state = load_json(controller_root / "state.json")
        except Exception as exc:
            defects.append({"kind": "state_parse_error", "error": str(exc)})
    if (controller_root / "artifacts.json").exists():
        try:
            artifacts = load_json(controller_root / "artifacts.json")
        except Exception as exc:
            defects.append({"kind": "artifacts_parse_error", "error": str(exc)})

    issue_rows = load_jsonl(controller_root / "issues.jsonl")
    command_rows = load_jsonl(controller_root / "commands.jsonl")
    correction_rows = load_jsonl(controller_root / "course_corrections.jsonl")

    for ledger_name, rows in (
        ("issues.jsonl", issue_rows),
        ("commands.jsonl", command_rows),
        ("course_corrections.jsonl", correction_rows),
        ("events.jsonl", load_jsonl(controller_root / "events.jsonl")),
        ("missing_features.jsonl", load_jsonl(controller_root / "missing_features.jsonl")),
    ):
        for row in rows:
            if row.get("__parse_error__"):
                defects.append({"kind": "ledger_parse_error", "ledger": ledger_name, "line": row.get("__line__"), "error": row.get("__parse_error__")})

    latest_issue: dict[str, dict[str, Any]] = {}
    for row in issue_rows:
        issue_id = row.get("issue_id")
        if issue_id:
            latest_issue[str(issue_id)] = row

    unresolved_blockers = [
        row
        for row in latest_issue.values()
        if row.get("severity") == "blocking" and row.get("status") not in TERMINAL_ISSUE_STATUSES
    ]
    for row in unresolved_blockers:
        defects.append(
            {
                "kind": "unresolved_blocking_issue",
                "issue_id": row.get("issue_id"),
                "status": row.get("status"),
                "symptom": row.get("symptom"),
            }
        )

    status_text = str(state.get("status") or "")
    phase_text = str(state.get("phase") or "")
    ready_state = status_text in {"ready_for_end_of_book_review", "accepted", "complete"} or status_text.startswith("accepted") or phase_text in {
        "end_of_book_review",
        "complete",
    }
    latest_correction: dict[str, dict[str, Any]] = {}
    for row in correction_rows:
        defects.extend(validate_course_correction_row(row, controller_root=controller_root))
        correction_id = row.get("correction_id")
        if correction_id:
            latest_correction[str(correction_id)] = row
    if ready_state:
        for row in latest_correction.values():
            outcome = row.get("outcome")
            if outcome != "accepted":
                defects.append(
                    {
                        "kind": "ready_state_with_unaccepted_course_correction",
                        "correction_id": row.get("correction_id"),
                        "line": row.get("__line__"),
                        "outcome": outcome,
                    }
                )

    if ready_state and unresolved_blockers:
        defects.append(
            {
                "kind": "ready_state_with_unresolved_blockers",
                "state_status": state.get("status"),
                "state_phase": state.get("phase"),
                "unresolved_issue_ids": [row.get("issue_id") for row in unresolved_blockers],
            }
        )

    monitor_state_path = controller_root / "monitor_state.json"
    monitor_stop_path = controller_root / "monitor_stop_report.json"
    if ready_state and monitor_state_path.exists():
        try:
            monitor_state = load_json(monitor_state_path)
        except Exception as exc:
            defects.append({"kind": "monitor_state_parse_error", "error": str(exc)})
            monitor_state = {}
        if not monitor_stop_path.exists():
            defects.append({"kind": "missing_monitor_stop_report", "path": str(monitor_stop_path)})
        else:
            try:
                stop_report = load_json(monitor_stop_path)
            except Exception as exc:
                defects.append({"kind": "monitor_stop_report_parse_error", "error": str(exc)})
                stop_report = {}
            if stop_report.get("active_child_processes"):
                defects.append(
                    {
                        "kind": "monitor_stop_report_has_active_children",
                        "active_child_processes": stop_report.get("active_child_processes"),
                    }
                )
            if monitor_state.get("cron_installed") is True and stop_report.get("cron_entry_removed") is not True:
                defects.append(
                    {
                        "kind": "monitor_cron_not_removed",
                        "monitor_state": str(monitor_state_path),
                        "monitor_stop_report": str(monitor_stop_path),
                    }
                )

    missing_artifact_paths = []
    for path_text in walk_paths(artifacts):
        path = Path(path_text)
        if not path.exists():
            missing_artifact_paths.append(path_text)
    for path_text in missing_artifact_paths[:50]:
        defects.append({"kind": "missing_artifact_path", "path": path_text})

    return {
        "schema_version": "book_extractor_controller_state_validation.v1",
        "controller_root": str(controller_root),
        "accepted": not defects,
        "defect_count": len(defects),
        "defects": defects,
        "issue_count": len(issue_rows),
        "latest_blocking_issue_count": sum(1 for row in latest_issue.values() if row.get("severity") == "blocking"),
        "unresolved_blocking_issue_count": len(unresolved_blockers),
        "command_count": len(command_rows),
        "course_correction_count": len(correction_rows),
        "state_status": state.get("status"),
        "state_phase": state.get("phase"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate book-extractor controller ledgers and phase gates.")
    parser.add_argument("--controller-root", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    result = validate(args.controller_root)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    raise SystemExit(0 if result["accepted"] else 1)


if __name__ == "__main__":
    main()
