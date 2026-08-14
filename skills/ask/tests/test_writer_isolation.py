"""Writer isolation must be decided before execution, not discovered in a merge (#1404).

The failures guarded here: a reviewer acquiring write capability because a
sibling writes, two writers racing in one tree, overlapping claims found only
when both have already done the work, and a writer accepted on prose.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "src"))

from ask.writer_isolation import (  # noqa: E402
    SCHEMA,
    IsolationError,
    compile_isolation,
    overlapping_claims,
    reviewer_inputs,
    verify_writer_receipt,
)

BASE = "abc123"


def _writer(stream_id: str, paths: list[str], **over) -> dict:
    stream = {
        "id": stream_id,
        "role": "coder",
        "mutation_intent": "workspace_write",
        "isolation_policy": "managed_worktree",
        "allowed_paths": paths,
        "base_commit": BASE,
    }
    stream.update(over)
    return stream


def _reader(stream_id: str, role: str = "reviewer") -> dict:
    return {"id": stream_id, "role": role, "mutation_intent": "none"}


def test_a_read_only_plan_compiles_with_no_worktrees() -> None:
    """Required proof 1: read-only plans stay read-only."""
    contract = compile_isolation({"workstreams": [_reader("r1"), _reader("r2", "judge")]})
    assert contract["schema"] == SCHEMA
    assert contract["writer_count"] == 0
    assert contract["worktrees_required"] == []


def test_one_writer_may_share_the_tree() -> None:
    contract = compile_isolation(
        {"workstreams": [_writer("w1", ["src/app"], isolation_policy="shared_single_writer", base_commit="")]}
    )
    assert contract["writer_count"] == 1
    assert contract["worktrees_required"] == []


def test_two_isolated_writers_each_require_a_worktree() -> None:
    """Required proof 2: separate worktrees, one immutable base."""
    contract = compile_isolation(
        {"workstreams": [_writer("w1", ["src/app"]), _writer("w2", ["docs"])]}
    )
    assert contract["worktrees_required"] == ["w1", "w2"]
    assert {w["base_commit"] for w in contract["workstreams"] if w["mutation_intent"] == "workspace_write"} == {BASE}


def test_two_writers_without_isolation_fail_before_execution() -> None:
    """Required proof 3: two writers in one tree is a race, not a config."""
    with pytest.raises(IsolationError, match="lack managed_worktree isolation"):
        compile_isolation(
            {
                "workstreams": [
                    _writer("w1", ["src/app"], isolation_policy="shared_single_writer", base_commit=""),
                    _writer("w2", ["docs"], isolation_policy="shared_single_writer", base_commit=""),
                ]
            }
        )


def test_parallel_writers_must_share_one_base_commit() -> None:
    with pytest.raises(IsolationError, match="one immutable base commit"):
        compile_isolation(
            {"workstreams": [_writer("w1", ["src/app"]), _writer("w2", ["docs"], base_commit="different")]}
        )


def test_managed_worktree_requires_a_base_commit() -> None:
    with pytest.raises(IsolationError, match="requires an immutable base_commit"):
        compile_isolation({"workstreams": [_writer("w1", ["src"], base_commit="")]})


def test_overlapping_claims_block_without_an_integrator() -> None:
    """Required proof 4: found before execution, not in a merge conflict."""
    with pytest.raises(IsolationError, match="overlapping path claims block execution"):
        compile_isolation(
            {"workstreams": [_writer("w1", ["src/app"]), _writer("w2", ["src/app/models"])]}
        )


def test_overlapping_claims_are_allowed_with_a_declared_integrator() -> None:
    contract = compile_isolation(
        {
            "conflict_policy": "explicit_integrator",
            "workstreams": [
                _writer("w1", ["src/app"]),
                _writer("w2", ["src/app/models"]),
                {"id": "integrator", "role": "coder", "mutation_intent": "none",
                 "integration_policy": "downstream_integrator"},
            ],
        }
    )
    assert contract["integrators"] == ["integrator"]
    assert contract["overlaps"]


def test_a_shared_string_prefix_is_not_an_overlap() -> None:
    """`src/app` must not read as covering `src/application`."""
    assert overlapping_claims(
        [_writer("w1", ["src/app"]), _writer("w2", ["src/application"])]
    ) == []


@pytest.mark.parametrize("role", ["scout", "researcher", "reviewer", "judge", "browser_reviewer"])
def test_a_read_only_role_can_never_declare_write_intent(role: str) -> None:
    """Required proof 5: no write capability from ambient configuration."""
    with pytest.raises(IsolationError, match="read-only"):
        compile_isolation(
            {"workstreams": [{"id": "r", "role": role, "mutation_intent": "workspace_write",
                              "allowed_paths": ["src"], "base_commit": BASE}]}
        )


def test_a_non_writer_may_not_claim_writable_paths() -> None:
    with pytest.raises(IsolationError, match="must not claim writable paths"):
        compile_isolation(
            {"workstreams": [{"id": "r", "role": "coder", "mutation_intent": "none",
                              "allowed_paths": ["src"]}]}
        )


def test_a_writer_must_declare_allowed_paths() -> None:
    with pytest.raises(IsolationError, match="must declare allowed_paths"):
        compile_isolation({"workstreams": [_writer("w1", [])]})


def test_a_prose_only_writer_receipt_is_rejected() -> None:
    """Required proof 7: 'I made the change' is what an unverified writer says."""
    contract = compile_isolation({"workstreams": [_writer("w1", ["src/app"])]})
    entry = contract["workstreams"][0]
    verdict = verify_writer_receipt({"workstream": "w1", "summary": "I made the change"}, entry)
    assert verdict["accepted"] is False
    assert any("prose-only" in p for p in verdict["problems"])


def test_a_complete_writer_receipt_is_accepted() -> None:
    contract = compile_isolation({"workstreams": [_writer("w1", ["src/app"])]})
    verdict = verify_writer_receipt(
        {
            "workstream": "w1",
            "patch_digest": "sha256:deadbeef",
            "changed_files": ["src/app/main.py"],
            "test_evidence": {"command": "pytest", "exit_code": 0},
        },
        contract["workstreams"][0],
    )
    assert verdict["accepted"] is True


def test_a_change_outside_the_declared_scope_rejects_the_receipt() -> None:
    """Required proof 6: out-of-scope changes are a typed non-success."""
    contract = compile_isolation({"workstreams": [_writer("w1", ["src/app"])]})
    verdict = verify_writer_receipt(
        {
            "workstream": "w1",
            "patch_digest": "sha256:d",
            "changed_files": ["src/app/main.py", "/etc/passwd"],
            "test_evidence": {"exit_code": 0},
        },
        contract["workstreams"][0],
    )
    assert verdict["accepted"] is False
    assert any("outside the declared scope" in p for p in verdict["problems"])


def test_a_denied_path_rejects_the_receipt() -> None:
    contract = compile_isolation(
        {"workstreams": [_writer("w1", ["src"], denied_paths=["src/secrets"])]}
    )
    verdict = verify_writer_receipt(
        {"workstream": "w1", "patch_digest": "d", "changed_files": ["src/secrets/key.py"],
         "test_evidence": {"ok": True}},
        contract["workstreams"][0],
    )
    assert verdict["accepted"] is False
    assert any("denied path" in p for p in verdict["problems"])


def test_the_reviewer_sees_only_accepted_manifests() -> None:
    """Required proof 8: reviewing work nobody admitted is not review."""
    contract = compile_isolation(
        {
            "conflict_policy": "explicit_integrator",
            "workstreams": [_writer("w1", ["src/app"]), _writer("w2", ["docs"])],
        }
    )
    inputs = reviewer_inputs(
        contract,
        [
            {"workstream": "w1", "patch_digest": "sha256:a", "changed_files": ["src/app/x.py"],
             "test_evidence": {"ok": True}},
            {"workstream": "w2", "summary": "trust me"},
        ],
    )
    assert [m["workstream"] for m in inputs["accepted_manifests"]] == ["w1"]
    assert inputs["withheld"][0]["workstream"] == "w2"
    assert inputs["grants_filesystem_access"] is False


def test_the_reviewer_receives_digests_it_can_verify() -> None:
    contract = compile_isolation({"workstreams": [_writer("w1", ["src/app"])]})
    inputs = reviewer_inputs(
        contract,
        [{"workstream": "w1", "patch_digest": "sha256:abc", "changed_files": ["src/app/x.py"],
          "test_evidence": {"ok": True}}],
    )
    assert inputs["accepted_manifests"][0]["patch_digest"] == "sha256:abc"


def test_the_contract_digest_changes_with_the_plan() -> None:
    a = compile_isolation({"workstreams": [_writer("w1", ["src/app"])]})
    b = compile_isolation({"workstreams": [_writer("w1", ["src/other"])]})
    assert a["digest"] != b["digest"]
