"""Generated JSON Schema drift tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from captcha_skill.errors import CaptchaSkillError, ErrorCode
from captcha_skill.schemas import export_schemas, schema_documents

SKILL_ROOT = Path(__file__).resolve().parents[1]


def test_checked_in_schemas_match_pydantic_contracts() -> None:
    result = export_schemas(SKILL_ROOT / "references", check=True)

    assert result["status"] == "PASS"
    assert set(result["files"]) == set(schema_documents())


def test_schema_check_fails_on_drift(tmp_path: Path) -> None:
    for filename, value in schema_documents().items():
        (tmp_path / filename).write_text(json.dumps(value))
    first = next(iter(schema_documents()))
    (tmp_path / first).write_text("{}")

    with pytest.raises(CaptchaSkillError) as raised:
        export_schemas(tmp_path, check=True)

    assert raised.value.code is ErrorCode.RECEIPT_INVALID
    assert first in raised.value.details["drift"]
