from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from battle_skill.receipt_store import InjectedTermination, ReceiptStore


def test_immutable_attempt_commit_is_idempotent_and_content_addressed(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("evidence", encoding="utf-8")
    store = ReceiptStore(tmp_path / "store")
    receipt = {"schema": "x", "verdict": "PASS"}

    first = store.commit(
        run_id="run-1",
        attempt_id="attempt-1",
        event_id="judge-1",
        receipt=receipt,
        artifacts={"stdout": artifact},
    )
    second = store.commit(
        run_id="run-1",
        attempt_id="attempt-1",
        event_id="judge-1",
        receipt=receipt,
        artifacts={"stdout": artifact},
    )

    assert first == second
    assert first["status"] == "COMMITTED"
    assert first["receipt_sha256"].startswith("sha256:")
    blob = tmp_path / "store" / first["receipt_blob"]
    assert json.loads(blob.read_text(encoding="utf-8"))["verdict"] == "PASS"
    assert (tmp_path / "store" / first["artifacts"][0]["blob"]).read_text(encoding="utf-8") == "evidence"

    with pytest.raises(FileExistsError):
        store.commit(
            run_id="run-1",
            attempt_id="attempt-1",
            event_id="judge-1",
            receipt={"schema": "x", "verdict": "FAIL"},
        )


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("run_id", ""),
        ("run_id", "."),
        ("run_id", ".."),
        ("run_id", "../escape"),
        ("attempt_id", "attempt/escape"),
        ("event_id", "event/escape"),
        *([("event_id", f"event{os.altsep}escape")] if os.altsep else []),
    ],
)
def test_attempt_identity_segments_reject_path_traversal(tmp_path: Path, field: str, bad_value: str) -> None:
    store_root = tmp_path / "store"
    outside = tmp_path / "escape"
    values = {"run_id": "run-1", "attempt_id": "attempt-1", "event_id": "judge-1"}
    values[field] = bad_value

    with pytest.raises(ValueError, match="safe path component"):
        store = ReceiptStore(store_root)
        store.commit(**values, receipt={"verdict": "PASS"})

    assert not outside.exists()
    assert not (tmp_path / "attempts").exists()
    assert not any(store_root.rglob("*")) if store_root.exists() else True


def test_crash_recovery_keeps_previous_evidence_and_marks_ambiguous_incomplete(tmp_path: Path) -> None:
    store = ReceiptStore(tmp_path / "store")
    committed = store.commit(
        run_id="run-1",
        attempt_id="attempt-ok",
        event_id="judge-1",
        receipt={"verdict": "PASS"},
    )

    with pytest.raises(InjectedTermination):
        store.commit(
            run_id="run-1",
            attempt_id="attempt-crash",
            event_id="judge-1",
            receipt={"verdict": "PASS"},
            failpoint="after_incomplete",
        )

    recovered = store.recover()

    assert (tmp_path / "store" / "attempts" / "run-1" / "attempt-ok" / "judge-1" / "attempt.json").exists()
    assert committed["status"] == "COMMITTED"
    assert any(item["attempt_id"] == "attempt-crash" and item["status"] == "INCOMPLETE" for item in recovered)
    assert not (tmp_path / "store" / "attempts" / "run-1" / "attempt-crash" / "judge-1" / "attempt.json").exists()
