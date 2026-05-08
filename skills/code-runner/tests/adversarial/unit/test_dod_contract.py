from __future__ import annotations

from pathlib import Path

from code_runner.dod import assertion_passed, run_dod


def test_contains_assertion_cannot_pass_with_nonzero_exit() -> None:
    assert assertion_passed("contains:DOD_OK", "DOD_OK\n", "", 1) is False


def test_plain_assertion_cannot_pass_with_nonzero_exit() -> None:
    assert assertion_passed("DOD_OK", "DOD_OK\n", "", 1) is False


def test_dod_records_timeout_as_failure(tmp_path: Path) -> None:
    result = run_dod(
        tmp_path,
        "python - <<'PY'\nimport time\ntime.sleep(2)\nPY",
        "contains:DOD_OK",
        timeout=1,
    )

    assert result.exit_code == 124
    assert result.passed is False
    assert "timed out" in result.stderr
