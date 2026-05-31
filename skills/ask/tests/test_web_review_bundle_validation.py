"""Tests for browser-backed review bundle path validation."""

from __future__ import annotations

import pathlib
import sys
import zipfile

import pytest

THIS_DIR = pathlib.Path(__file__).resolve().parent
SRC_DIR = THIS_DIR.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ask.webgpt_runtime import (
    WebReviewBundleError,
    extract_file_attachments,
    resolve_web_review_delivery,
)


def test_accepts_single_concatenated_bundle(tmp_path: pathlib.Path) -> None:
    bundle = tmp_path / "review-bundle.md"
    bundle.write_text("# Review\n\nAll evidence is inlined here.\n", encoding="utf-8")
    question = f"Review the bundle at {bundle}"
    attachments = extract_file_attachments(question)
    assert resolve_web_review_delivery(question, attachments, backend="webgpt") == ""


def test_accepts_small_zip_bundle_for_webgpt(tmp_path: pathlib.Path) -> None:
    archive = tmp_path / "review-bundle.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("REVIEW_REQUEST.md", "# Review\n")
        zf.writestr("gate_output.json", '{"ok": true}')
    question = f"Review {archive}"
    attachments = extract_file_attachments(question)
    assert resolve_web_review_delivery(question, attachments, backend="webgpt") == str(archive)


def test_rejects_zip_with_too_many_files(tmp_path: pathlib.Path) -> None:
    archive = tmp_path / "review-bundle.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for i in range(6):
            zf.writestr(f"file{i}.txt", "x")
    question = f"Review {archive}"
    attachments = extract_file_attachments(question)
    with pytest.raises(WebReviewBundleError, match="can't read local file paths"):
        resolve_web_review_delivery(question, attachments, backend="webgpt")


def test_friendly_error_for_path_only_manifest(tmp_path: pathlib.Path) -> None:
    request = tmp_path / "REVIEW_REQUEST.md"
    evidence = tmp_path / "diagnosis.json"
    evidence.write_text('{"ok": true}', encoding="utf-8")
    request.write_text(
        "# Review\n\nSee evidence at:\n"
        f"- {evidence}\n",
        encoding="utf-8",
    )
    question = f"Review {request}"
    attachments = extract_file_attachments(question)
    with pytest.raises(WebReviewBundleError) as exc:
        resolve_web_review_delivery(question, attachments, backend="webgpt")
    assert "can't read local file paths" in str(exc.value)
    assert "zip review bundle" in str(exc.value)
    assert "concatenated text file" in str(exc.value)


def test_friendly_error_for_directory_path(tmp_path: pathlib.Path) -> None:
    bundle_dir = tmp_path / "review-bundle"
    bundle_dir.mkdir()
    question = f"Review bundle at {bundle_dir}"
    attachments = extract_file_attachments(question)
    with pytest.raises(WebReviewBundleError, match="concatenated text file"):
        resolve_web_review_delivery(question, attachments, backend="webkimi")


def test_friendly_error_for_missing_paths() -> None:
    question = "Review /tmp/does-not-exist-review-bundle.md"
    attachments = extract_file_attachments(question)
    with pytest.raises(WebReviewBundleError, match="can't read local file paths"):
        resolve_web_review_delivery(question, attachments, backend="webgemini")


def test_skill_slash_mentions_are_not_treated_as_missing_paths(tmp_path: pathlib.Path) -> None:
    bundle = tmp_path / "review-bundle.md"
    bundle.write_text("# Review\n\nCompare /ask, /scillm, and /code-runner boundaries.\n", encoding="utf-8")
    question = f"Review {bundle}. Be harsh about /ask versus /scillm and /code-runner."
    attachments = extract_file_attachments(question)

    assert resolve_web_review_delivery(question, attachments, backend="webgpt") == ""
