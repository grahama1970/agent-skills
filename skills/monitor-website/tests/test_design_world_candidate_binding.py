from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "skills/monitor-website/scripts/design_world_check.py"


def load_module():
    spec = importlib.util.spec_from_file_location("design_world_check_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_candidate_binding_accepts_matching_git_prefix(monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "EXPECTED_SOURCE_COMMIT", "abcdef1234567890")

    errors = module._candidate_binding_errors({"source_commit": "abcdef1"})

    assert errors == []


def test_candidate_binding_rejects_stale_receipt(monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "EXPECTED_SOURCE_COMMIT", "1234567890abcdef")

    errors = module._candidate_binding_errors({"source_commit": "abcdef1234567890"})

    assert errors == [
        "receipt source_commit abcdef1234567890 does not match active candidate 1234567890abcdef"
    ]


def test_candidate_binding_reads_formal_receipt_project_source_revision(monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "EXPECTED_SOURCE_COMMIT", "fedcba9876543210")

    errors = module._candidate_binding_errors(
        {"project": {"source_revision": "fedcba9876543210"}}
    )

    assert errors == []
