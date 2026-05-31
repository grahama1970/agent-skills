"""Tests for Kimi web UI capacity/busy detection."""

from ask.kimi_capacity import KimiCapacityBusyError, is_kimi_capacity_busy


def test_system_busy_message():
    text = "System is currently busy. Please try again later."
    assert is_kimi_capacity_busy(text)


def test_capacity_busy_upgrade():
    text = "Capacity is busy. Please wait or upgrade"
    assert is_kimi_capacity_busy(text)


def test_normal_prose_not_busy():
    text = "Please wait for the deployment to finish before you upgrade the chart."
    assert not is_kimi_capacity_busy(text)


def test_verdict_review_not_busy():
    text = "VERDICT: NEEDS_CHANGES\n\nExecutive summary\nThe README is clear."
    assert not is_kimi_capacity_busy(text)


def test_capacity_busy_error_excerpt():
    err = KimiCapacityBusyError(response_excerpt="Capacity is busy. Please wait or upgrade")
    assert "Capacity is busy" in str(err)
