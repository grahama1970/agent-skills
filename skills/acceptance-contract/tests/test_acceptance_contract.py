from pathlib import Path
import zipfile

import pytest
from pydantic import ValidationError

from acceptance_contract.extract import build_bundle
from acceptance_contract.models import AcceptanceBundle, GoalMode
from acceptance_contract.reporting import build_report


def test_extracts_clear_requirements_from_directory(tmp_path: Path) -> None:
    brief = tmp_path / "brief.md"
    brief.write_text(
        "# Brief\n"
        "- The system must redact phone numbers in every representation.\n"
        "- Valid JSON input must accept non-sensitive literals unchanged.\n"
        "- Outputs must not leak policy values.\n"
        "- Should we support images?\n",
        encoding="utf-8",
    )

    bundle = build_bundle(tmp_path, "demo", GoalMode.CREATE)

    assert len(bundle.requirements) == 3
    assert len(bundle.acceptance_cases) == 3
    assert len(bundle.open_questions) == 1
    assert bundle.acceptance_cases[1].kind == "MUST_ACCEPT"
    assert bundle.acceptance_cases[2].kind == "MUST_REJECT"
    assert bundle.immutable_goal is not None
    assert "draft only" in bundle.immutable_goal.markdown


def test_accepts_zip_bundle(tmp_path: Path) -> None:
    zip_path = tmp_path / "brief.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("docs/brief.txt", "The gate shall fail closed when the judge errors.\n")

    bundle = build_bundle(zip_path, "demo", GoalMode.AMEND)

    assert bundle.source.kind == "zip"
    assert bundle.requirements[0].kind == "forbidden"
    assert bundle.immutable_goal is not None
    assert bundle.immutable_goal.mode == "amend"


def test_rejects_unsafe_zip_member(tmp_path: Path) -> None:
    zip_path = tmp_path / "bad.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("../brief.txt", "The system must reject traversal.\n")

    with pytest.raises(ValueError, match="unsafe zip member"):
        build_bundle(zip_path, "demo", GoalMode.CREATE)


def test_bundle_validation_rejects_case_without_requirement(tmp_path: Path) -> None:
    payload = build_bundle(tmp_path, "demo", GoalMode.NONE).model_dump(by_alias=True) if False else {
        "schema": "acceptance_contract.bundle.v1",
        "project_name": "demo",
        "source": {"kind": "file", "path": "brief.md", "sha256": "0" * 64, "files": []},
        "requirements": [],
        "acceptance_cases": [
            {
                "id": "AC-001",
                "requirement_id": "REQ-999",
                "kind": "MUST_VERIFY",
                "predicate": "must pass",
                "deterministic_check": "run check",
                "proof_artifacts": ["receipt.json"],
            }
        ],
        "open_questions": [{"id": "Q-001", "question": "missing requirement?", "source_path": "brief.md", "source_line": 1}],
        "immutable_goal": None,
        "non_claims": ["fixture"],
    }

    with pytest.raises(ValidationError):
        AcceptanceBundle.model_validate(payload)


def test_create_report_shape_is_valid_for_extracted_bundle(tmp_path: Path) -> None:
    brief = tmp_path / "brief.md"
    brief.write_text("The product must preserve literal non-PII text.\n", encoding="utf-8")
    bundle = build_bundle(brief, "demo", GoalMode.CREATE)

    report = build_report(bundle)

    assert report["schema"] == "create_report.report.v1"
    assert report["findings"][0]["id"] == "F-001"
    assert report["plan_iterate_seed"]["human_decisions"] == ["create new immutable goal or amend existing immutable goal"]
