#!/usr/bin/env python3
"""Retained fault-injection proof for watchdog publication/native recovery."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


TESTS = [
    "tests/test_primary_main_revision.py::test_private_index_publication_preserves_head_index_and_unrelated_files",
    "tests/test_primary_main_revision.py::test_disjoint_remote_advance_is_preserved_without_rebase",
    "tests/test_primary_main_revision.py::test_same_target_remote_advance_is_scoped_conflict_without_overwrite",
    "tests/test_primary_main_revision.py::test_failed_publication_push_retains_command_diagnostics",
    "tests/test_primary_main_revision.py::test_native_close_lost_response_is_read_back_without_second_close",
    "tests/test_primary_main_revision.py::test_native_close_failed_mutation_never_becomes_completed",
    "tests/test_primary_main_revision.py::test_native_close_rejects_foreign_generation_and_changed_proof",
    "tests/test_primary_main_revision.py::test_owned_release_does_not_remove_foreign_generation",
    "tests/test_primary_main_revision.py::test_closure_outbox_recovery_retries_native_close_without_new_provider",
    "tests/test_primary_main_revision.py::test_closed_ticket_with_release_pending_is_not_finished_completed",
    "tests/test_primary_main_revision.py::test_unknown_remote_run_recovery_never_dispatches_duplicate",
    "tests/test_primary_main_revision.py::test_retryable_resume_reattaches_native_lease_and_sets_watchdog_journal",
    "tests/test_primary_main_revision.py::test_native_shell_keeps_lease_until_close_and_never_bypasses_retention",
    "tests/test_project_rotation.py::test_target_is_read_from_the_line_ticket_writes",
    "tests/test_project_rotation.py::test_markdown_target_paths_override_orientation_skill_mentions",
    "tests/test_project_rotation.py::test_markdown_target_paths_accept_coarse_exact_skill_path",
    "tests/test_project_rotation.py::test_an_unreadable_target_is_its_own_namespace",
]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: publication_recovery.py OUTPUT_JSON", file=sys.stderr)
        return 2
    skill_dir = Path(__file__).resolve().parents[1]
    output = Path(sys.argv[1]).expanduser().resolve()
    command = [sys.executable, "-m", "pytest", *TESTS, "-q"]
    completed = subprocess.run(command, cwd=skill_dir, capture_output=True, text=True, check=False)
    passed = completed.returncode == 0
    report = {
        "schema": "agent_skills.project_watchdog.publication_recovery_eval.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "status": "PASS" if passed else "FAIL",
        "mocked": True,
        "live": False,
        "evidence_class": "fault_injected_deterministic",
        "command": command,
        "test_count": len(TESTS),
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "coverage": {
            "disjoint remote-main advance": "test_disjoint_remote_advance_is_preserved_without_rebase reads publication-recovery.json push/ancestor/readback fields",
            "same-target remote conflict": "test_same_target_remote_advance_is_scoped_conflict_without_overwrite verifies scoped conflict and unchanged local HEAD",
            "failed push": "test_failed_publication_push_retains_command_diagnostics verifies retained exit/stdout/stderr",
            "helper nonzero": "test_owned_release_does_not_remove_foreign_generation verifies native-release-command.json exit/stderr",
            "close readback still OPEN": "test_native_close_failed_mutation_never_becomes_completed refuses unconfirmed close",
            "process interruption boundaries": "closure outbox, unknown remote run, retryable resume, and release-pending tests retain journals without rerunning providers",
            "target parsing": "project rotation tests verify inline and section-form targets plus unknown-target namespace",
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "passed": passed, "test_count": len(TESTS)}, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
