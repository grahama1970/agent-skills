"""Pytest cases for documentation organization and the best-practices gate.

Split out of test_cleanup.py to keep every file under the 800-line rule from
/best-practices-python. sanity.sh runs test_cleanup.py's behavioral suite; these
run under pytest.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cleanup  # noqa: E402


def test_conventional_root_docs_are_never_relocated():
    tracked = {"README.md", "LICENSE.md", "SECURITY.md", "CONTRIBUTING.md"}
    proposals = cleanup.scan_doc_organization(
        tracked=tracked, commit_times={}, now=0.0
    )
    assert {p["verdict"] for p in proposals} == {"keep_root_conventional"}
    assert all(p["proposed_path"] is None for p in proposals)


def test_root_doc_is_proposed_into_a_docs_home():
    tracked = {"DESIGN.md"}
    proposals = cleanup.scan_doc_organization(
        tracked=tracked, commit_times={}, now=0.0
    )
    assert proposals[0]["verdict"] == "relocate_proposed"
    assert proposals[0]["proposed_path"] == "docs/architecture/DESIGN.md"


def test_unknown_root_doc_lands_in_plain_docs_dir():
    proposals = cleanup.scan_doc_organization(
        tracked={"WEIRDNAME.md"}, commit_times={}, now=0.0
    )
    assert proposals[0]["proposed_path"] == "docs/WEIRDNAME.md"


def test_stale_unreferenced_doc_is_proposed_for_deprecation():
    now = 100_000_000.0
    old = now - (cleanup.DOC_STALE_DAYS + 10) * 86400
    proposals = cleanup.scan_doc_organization(
        tracked={"docs/OLD.md"}, commit_times={"docs/OLD.md": old}, now=now
    )
    assert proposals[0]["verdict"] == "deprecate_proposed"
    assert proposals[0]["proposed_path"] == "docs/deprecated/OLD.md"


def test_doc_already_under_docs_is_kept():
    now = 100_000_000.0
    proposals = cleanup.scan_doc_organization(
        tracked={"docs/CURRENT.md"}, commit_times={"docs/CURRENT.md": now}, now=now
    )
    assert proposals[0]["verdict"] == "keep"


def test_best_practices_mapping_by_suffix_and_path():
    assert cleanup.best_practices_skill_for("src/app.py") == "best-practices-python"
    assert cleanup.best_practices_skill_for("ui/Button.tsx") == "best-practices-react"
    assert cleanup.best_practices_skill_for("core/lib.rs") == "best-practices-rust"
    assert cleanup.best_practices_skill_for("skills/foo/SKILL.md") == "best-practices-skills"
    assert cleanup.best_practices_skill_for("data/blob.bin") is None


def test_best_practices_gate_counts_and_status(tmp_path):
    skills_root = tmp_path / "skills"
    (skills_root / "best-practices-python").mkdir(parents=True)
    gate = cleanup.evaluate_best_practices_gate(
        ["a.py", "b.tsx", "c.bin"], skills_root=skills_root
    )
    assert gate["status"] == "requires_run"
    assert gate["counts"]["not_applicable"] == 1
    assert "best-practices-python" in gate["required_skills"]
    # react is mapped but not installed in this fixture
    assert "best-practices-react" in gate["unavailable_skills"]


def test_best_practices_gate_is_satisfied_with_no_changed_files():
    gate = cleanup.evaluate_best_practices_gate([])
    assert gate["status"] == "satisfied"
    assert gate["counts"]["checked"] == 0


def test_best_practices_gate_never_claims_a_run_happened():
    gate = cleanup.evaluate_best_practices_gate(["a.py"])
    assert "mapping_only" in gate["proof_limit"]
    assert gate["counts"]["failed"] == 0


def test_empty_doc_is_flagged_and_never_deleted():
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        cwd = os.getcwd()
        try:
            os.chdir(d)
            open("EMPTY.md", "w").close()
            proposals = cleanup.scan_doc_organization(
                tracked={"EMPTY.md"}, commit_times={}, now=0.0
            )
        finally:
            os.chdir(cwd)
    assert proposals[0]["verdict"] == "empty_doc"
    # the only disposition is a move into docs/deprecated
    assert proposals[0]["proposed_path"] == "docs/deprecated/EMPTY.md"


def test_copy_artifact_filename_is_flagged():
    proposals = cleanup.scan_doc_organization(
        tracked={"docs/thing copy.md"}, commit_times={}, now=0.0
    )
    assert proposals[0]["verdict"] == "duplicate_copy"
    assert proposals[0]["proposed_path"].startswith("docs/deprecated/")


def test_foreign_repo_doc_is_detected():
    content = "# Request\n\n* Fork/Repo: `someoneelse/otherproject`\n"
    slug = cleanup._foreign_repo_reference(content, "docs/REQ.md")
    assert slug == "someoneelse/otherproject"


def test_foreign_repo_ignores_this_repository():
    ours = list(cleanup._current_repo_slugs())[0]
    content = f"# Doc\n\nSee https://github.com/{ours} for details.\n"
    assert cleanup._foreign_repo_reference(content, "docs/X.md") is None


def test_no_verdict_ever_proposes_deletion():
    """Every disposition is a move; the skill has no delete path for docs."""
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        cwd = os.getcwd()
        try:
            os.chdir(d)
            open("EMPTY.md", "w").close()
            proposals = cleanup.scan_doc_organization(
                tracked={"EMPTY.md", "docs/a copy.md", "DESIGN.md"},
                commit_times={}, now=0.0,
            )
        finally:
            os.chdir(cwd)
    for p in proposals:
        assert "delete" not in p["verdict"]
        assert "remove" not in p["verdict"]
        if p["proposed_path"]:
            assert p["proposed_path"].startswith("docs/")


def test_tool_resolved_root_docs_are_protected():
    """PROJECT_KNOWLEDGE.md is read by /project-knowledge at cwd; never move it."""
    proposals = cleanup.scan_doc_organization(
        tracked={"PROJECT_KNOWLEDGE.md"}, commit_times={}, now=0.0
    )
    assert proposals[0]["verdict"] == "keep_root_conventional"
    assert proposals[0]["proposed_path"] is None
