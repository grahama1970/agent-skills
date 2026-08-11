"""Policy tests for local-only, authorization-gated CAPTCHA evaluation."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from captcha_skill.errors import CaptchaSkillError, ErrorCode
from captcha_skill.models import AuthorizationManifest, EvaluationAction
from captcha_skill.policy import canonical_json_bytes, sha256_bytes, validate_authorization

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _manifest_value() -> dict:
    return json.loads((FIXTURES / "authorization-valid-local.json").read_text())


def _validate(value: dict) -> AuthorizationManifest:
    return AuthorizationManifest.model_validate(value)


def test_valid_local_manifest_issues_typed_receipt() -> None:
    value = _manifest_value()
    manifest = _validate(value)
    digest = sha256_bytes(canonical_json_bytes(manifest.model_dump(mode="json")))

    receipt = validate_authorization(
        manifest,
        manifest_sha256=digest,
        required_action=EvaluationAction.EVALUATE,
        now=datetime(2028, 1, 1, tzinfo=timezone.utc),
    )

    assert receipt.status == "PASS"
    assert receipt.action is EvaluationAction.EVALUATE
    assert receipt.manifest_sha256 == digest
    assert receipt.seam_validation.status == "PASS"
    assert receipt.provider == "dynamic"


def test_manifest_set_serialization_is_deterministic() -> None:
    first_value = _manifest_value()
    second_value = _manifest_value()
    first_value["allowed_actions"] = list(reversed(first_value["allowed_actions"]))
    second_value["allowed_captcha_types"] = list(
        reversed(second_value["allowed_captcha_types"])
    )

    first = _validate(first_value).model_dump(mode="json")
    second = _validate(second_value).model_dump(mode="json")

    assert first == second
    assert first["allowed_actions"] == sorted(first["allowed_actions"])
    assert first["allowed_captcha_types"] == sorted(first["allowed_captcha_types"])


def test_public_target_is_rejected_before_execution() -> None:
    value = _manifest_value()
    value["target_url"] = "https://captcha.example.org"
    manifest = _validate(value)

    with pytest.raises(CaptchaSkillError) as raised:
        validate_authorization(
            manifest,
            manifest_sha256="a" * 64,
            required_action=EvaluationAction.EVALUATE,
            now=datetime(2028, 1, 1, tzinfo=timezone.utc),
        )

    assert raised.value.code is ErrorCode.TARGET_NOT_LOOPBACK


def test_public_model_endpoint_is_rejected() -> None:
    value = _manifest_value()
    value["model_base_url"] = "https://api.example.org/v1"
    manifest = _validate(value)

    with pytest.raises(CaptchaSkillError) as raised:
        validate_authorization(
            manifest,
            manifest_sha256="a" * 64,
            required_action=EvaluationAction.EVALUATE,
            now=datetime(2028, 1, 1, tzinfo=timezone.utc),
        )

    assert raised.value.code is ErrorCode.MODEL_ENDPOINT_NOT_LOOPBACK


def test_dns_alias_other_than_localhost_is_rejected() -> None:
    value = _manifest_value()
    value["target_url"] = "http://recap.internal:5000"
    manifest = _validate(value)

    with pytest.raises(CaptchaSkillError) as raised:
        validate_authorization(
            manifest,
            manifest_sha256="a" * 64,
            required_action=EvaluationAction.PLAN,
            now=datetime(2028, 1, 1, tzinfo=timezone.utc),
        )

    assert raised.value.code is ErrorCode.TARGET_NOT_LOOPBACK


def test_target_root_path_is_required() -> None:
    value = _manifest_value()
    value["target_url"] = "http://127.0.0.1:5000/challenge/text"
    manifest = _validate(value)

    with pytest.raises(CaptchaSkillError) as raised:
        validate_authorization(
            manifest,
            manifest_sha256="a" * 64,
            required_action=EvaluationAction.PLAN,
            now=datetime(2028, 1, 1, tzinfo=timezone.utc),
        )

    assert raised.value.code is ErrorCode.TARGET_NOT_LOOPBACK


def test_embedded_credentials_are_rejected() -> None:
    value = _manifest_value()
    value["target_url"] = "http://user:password@127.0.0.1:5000"
    manifest = _validate(value)

    with pytest.raises(CaptchaSkillError) as raised:
        validate_authorization(
            manifest,
            manifest_sha256="a" * 64,
            required_action=EvaluationAction.PLAN,
            now=datetime(2028, 1, 1, tzinfo=timezone.utc),
        )

    assert raised.value.code is ErrorCode.TARGET_NOT_LOOPBACK


def test_expired_manifest_is_rejected() -> None:
    value = _manifest_value()
    value["expires_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    manifest = _validate(value)

    with pytest.raises(CaptchaSkillError) as raised:
        validate_authorization(
            manifest,
            manifest_sha256="a" * 64,
            required_action=EvaluationAction.PLAN,
        )

    assert raised.value.code is ErrorCode.AUTHORIZATION_EXPIRED


def test_unlisted_action_is_rejected() -> None:
    value = _manifest_value()
    value["allowed_actions"] = ["plan"]
    manifest = _validate(value)

    with pytest.raises(CaptchaSkillError) as raised:
        validate_authorization(
            manifest,
            manifest_sha256="a" * 64,
            required_action=EvaluationAction.EVALUATE,
            now=datetime(2028, 1, 1, tzinfo=timezone.utc),
        )

    assert raised.value.code is ErrorCode.ACTION_NOT_AUTHORIZED


def test_false_acknowledgement_is_rejected() -> None:
    value = _manifest_value()
    value["acknowledgements"]["no_third_party_bypass"] = False
    manifest = _validate(value)

    with pytest.raises(CaptchaSkillError) as raised:
        validate_authorization(
            manifest,
            manifest_sha256="a" * 64,
            required_action=EvaluationAction.PLAN,
            now=datetime(2028, 1, 1, tzinfo=timezone.utc),
        )

    assert raised.value.code is ErrorCode.INVALID_MANIFEST


def test_custom_mode_requires_named_allowed_captcha() -> None:
    value = _manifest_value()
    value["captcha_name"] = None

    with pytest.raises(ValidationError):
        _validate(value)


def test_once_mode_is_bounded_to_seven_tasks() -> None:
    value = _manifest_value()
    value["test_mode"] = "once"
    value["captcha_name"] = None
    value["max_tasks"] = 6

    with pytest.raises(ValidationError):
        _validate(value)
