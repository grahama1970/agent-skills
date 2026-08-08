"""Label flywheel: verdict/board-state -> training label mapping (no network)."""

from __future__ import annotations

import monitor_opportunities.training_labels as tl


def _capture(monkeypatch) -> list[dict]:
    captured: list[dict] = []
    monkeypatch.setattr(tl, "_store", lambda doc, memory_url=tl.MEMORY_URL: captured.append(doc) or True)
    return captured


def test_verdict_mapping(monkeypatch) -> None:
    got = _capture(monkeypatch)
    assert tl.label_from_verdict("Staff AI Engineer", "KEEP") is True
    assert tl.label_from_verdict("Forklift Operator", "REJECT") is True
    assert tl.label_from_verdict("Ambiguous role", "NEEDS_REVIEW") is False  # not a training signal
    labels = {d["text"]: d["label"] for d in got}
    assert labels["Staff AI Engineer"] == 1
    assert labels["Forklift Operator"] == 0
    assert "Ambiguous role" not in labels


def test_board_state_mapping(monkeypatch) -> None:
    got = _capture(monkeypatch)
    assert tl.label_from_board_state("AI Engineer", "state:approved") is True
    assert tl.label_from_board_state("Sales role", "verdict:reject") is True
    assert tl.label_from_board_state("AI Engineer", "state:shortlisted") is False  # neutral
    labels = {d["text"]: (d["label"], d["source"]) for d in got}
    assert labels["AI Engineer"] == (1, "human")
    assert labels["Sales role"] == (0, "human")


def test_bad_input_rejected(monkeypatch) -> None:
    _capture(monkeypatch)
    assert tl.append_label("", 1, "adversarial") is False
    assert tl.append_label("x", 2, "adversarial") is False  # label must be 0 or 1
