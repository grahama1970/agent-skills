"""Representation and schema rejection tests derived from consent and evidence invariants."""
import math

import pytest
from pydantic import ValidationError

from a_detection.contracts import Edit, Policy, SessionRequest
from a_detection.errors import DetectionError
from a_detection.io import strict_json
from tests.helpers import edit


@pytest.mark.parametrize("value", [False, 0, 1, "true", "false", None, [], {}])
def test_consent_is_explicit_boolean(value):
    with pytest.raises(ValidationError):
        SessionRequest(consent=value)


def test_true_consent_and_no_unknown_fields():
    assert SessionRequest(consent=True).consent is True
    with pytest.raises(ValidationError):
        SessionRequest(consent=True, trusted_human=True)


@pytest.mark.parametrize("field,value", [("seq", True), ("seq", "1"), ("seq", 1.5),
    ("client_elapsed_ms", math.nan), ("client_elapsed_ms", math.inf),
    ("start", -1), ("insert_text", "\ud800"), ("kind", "verified-human"),
    ("after_sha256", "not-a-digest"), ("event_id", "../file")])
def test_edit_representation_rejection(field, value):
    valid, _ = edit("", "ok")
    payload = valid.model_dump()
    payload[field] = value
    with pytest.raises(ValidationError):
        Edit.model_validate(payload)


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'\xff'])
def test_json_has_no_ambiguous_members_or_nonfinite_values(raw):
    with pytest.raises(DetectionError):
        strict_json(raw)


@pytest.mark.parametrize("field", ["automatic_penalties", "external_provider_uploads", "behavioral_authorship_scoring"])
def test_unsafe_policy_values_are_rejected(field):
    with pytest.raises(ValidationError):
        Policy.model_validate({field: True})


@pytest.mark.parametrize("value", [0, 0.0, "false", None])
@pytest.mark.parametrize("field", ["automatic_penalties", "external_provider_uploads", "behavioral_authorship_scoring"])
def test_literal_false_rejects_nonboolean_lookalikes(field, value):
    with pytest.raises(ValidationError):
        Policy.model_validate({field: value})


@pytest.mark.parametrize("disposition", ["REVIEW_SUGGESTED", "NO_ELEVATED_SIGNAL"])
def test_missing_model_cannot_be_promoted_to_a_verdict(disposition):
    from a_detection.contracts import Analysis
    with pytest.raises(ValidationError):
        Analysis(disposition=disposition, source_sha256="0" * 64, reasons=[],
                 observations={}, limitations=[], calibration_qualified=False)
