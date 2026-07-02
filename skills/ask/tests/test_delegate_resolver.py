"""Deterministic tests for agent/persona/skill delegate resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from ask.delegate import DelegateError, load_delegate_registry, resolve_delegate_invocation
from ask.delegate.models import DelegateRegistry, RegistryEntry


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture()
def delegate_root(tmp_path: Path) -> Path:
    _write(
        tmp_path / "agents" / "code-reviewer" / "AGENTS.md",
        """---
id: code-reviewer
kind: worker
title: Code reviewer
surface: opencode_transport
mode: propose_patches
composes:
- review-code
- memory
---

# Code reviewer
""",
    )
    _write(
        tmp_path / "agents" / "backend-coder" / "AGENTS.md",
        """---
id: backend-coder
kind: worker
title: Backend coder
surface: opencode_transport
mode: workspace_write
allowed_modes:
- workspace_write
composes:
- code-runner
---

# Backend coder
""",
    )
    _write(
        tmp_path / "skills" / "review-code" / "SKILL.md",
        """---
name: review-code
description: Deterministic code review workflow.
---

# review-code
""",
    )
    _write(
        tmp_path / "skills" / "code-runner" / "SKILL.md",
        """---
name: code-runner
description: Code execution workflow.
---

# code-runner
""",
    )
    return tmp_path


def test_worker_registry_entry_normalizes_to_agent(delegate_root: Path):
    registry = load_delegate_registry(delegate_root)

    envelope = resolve_delegate_invocation(
        "$ask $code-reviewer to review src/foo.rs with $review-code",
        registry,
        request_id="delegate-test-001",
    )

    assert envelope["schema"] == "agent_skills.delegate.v1"
    assert envelope["request_id"] == "delegate-test-001"
    assert envelope["invocation_id"] == "delegate-test-001"
    assert envelope["caller"] == {"type": "agent", "id": "ask-cli"}
    assert envelope["actor"] == {
        "id": "code-reviewer",
        "kind": "agent",
        "target_type": "repo_worker",
        "source_kind": "worker",
    }
    assert envelope["skills"][0]["id"] == "review-code"
    assert envelope["skills"][0]["kind"] == "skill"
    assert envelope["skills"][0]["version_or_digest"].startswith("sha256:")
    assert envelope["mode"] == "read_only_review"
    assert envelope["runtime"]["selected"] == "opencode_serve"
    assert envelope["policy"]["mutation"] == "read_only"
    assert envelope["override_policy"] == {
        "skill_composition": "strict",
        "prompt_level_override_allowed": False,
        "privileged_override_supported": False,
        "privileged_override_requires": [
            "registry_policy",
            "caller_authority",
            "envelope_record",
            "receipt_record",
        ],
    }
    assert envelope["receipt_requirements"] == {
        "preserve_invocation_id": True,
        "preserve_caller": True,
        "preserve_actor_id": True,
        "preserve_skill_ids": True,
        "preserve_skill_versions_or_digests": True,
        "include_target": True,
        "include_mode": True,
        "include_runtime": True,
        "include_override_policy": True,
        "include_materialized_skill_bundle": True,
        "include_artifact_paths": True,
    }


def test_builtin_persona_resolves_to_scillm_chat(delegate_root: Path):
    registry = load_delegate_registry(delegate_root)

    envelope = resolve_delegate_invocation("$ask Brandon to critique this retry design", registry)

    assert envelope["actor"]["id"] == "brandon"
    assert envelope["actor"]["kind"] == "persona"
    assert envelope["mode"] == "persona_review"
    assert envelope["runtime"]["selected"] == "scillm_chat"
    assert envelope["policy"]["mutation"] == "read_only"


def test_webgpt_delegate_fails_closed(delegate_root: Path):
    registry = load_delegate_registry(delegate_root)

    with pytest.raises(DelegateError) as exc_info:
        resolve_delegate_invocation("$ask webgpt to review REVIEW_BUNDLE_MD", registry)

    assert exc_info.value.reason == "unknown_actor"


def test_skill_used_as_actor_fails_closed(delegate_root: Path):
    registry = load_delegate_registry(delegate_root)

    with pytest.raises(DelegateError) as exc_info:
        resolve_delegate_invocation("$ask $review-code to review src/foo.rs", registry)

    assert exc_info.value.reason == "unknown_actor"
    attention = exc_info.value.as_needs_attention()
    assert attention["safe_default"] == "do_not_delegate"
    assert "review-code" in attention["details"]["token"]


def test_actor_used_as_skill_fails_closed(delegate_root: Path):
    registry = load_delegate_registry(delegate_root)

    with pytest.raises(DelegateError) as exc_info:
        resolve_delegate_invocation("$ask $code-reviewer to review src/foo.rs with $backend-coder", registry)

    assert exc_info.value.reason == "unknown_skill"
    assert exc_info.value.as_needs_attention()["details"]["expected_kinds"] == ["skill"]


def test_unknown_actor_fails_closed(delegate_root: Path):
    registry = load_delegate_registry(delegate_root)

    with pytest.raises(DelegateError) as exc_info:
        resolve_delegate_invocation("$ask $missing-agent to review src/foo.rs", registry)

    assert exc_info.value.reason == "unknown_actor"
    assert exc_info.value.as_needs_attention()["resume_hint"]


def test_ambiguous_actor_fails_closed():
    registry = DelegateRegistry(
        (
            RegistryEntry(id="reviewer-a", kind="agent", aliases=("reviewer",), target_type="repo_worker"),
            RegistryEntry(id="reviewer-b", kind="agent", aliases=("reviewer",), target_type="repo_worker"),
        )
    )

    with pytest.raises(DelegateError) as exc_info:
        resolve_delegate_invocation("$ask reviewer to review src/foo.rs", registry)

    assert exc_info.value.reason == "ambiguous_actor"
    assert len(exc_info.value.as_needs_attention()["details"]["matches"]) == 2


def test_incompatible_skill_fails_closed(delegate_root: Path):
    registry = load_delegate_registry(delegate_root)

    with pytest.raises(DelegateError) as exc_info:
        resolve_delegate_invocation("$ask $code-reviewer to review src/foo.rs with $code-runner", registry)

    assert exc_info.value.reason == "actor_skill_not_compatible"
    attention = exc_info.value.as_needs_attention()
    assert attention["details"]["override_policy"]["allowed_by_prompt"] is False
    assert attention["details"]["override_policy"]["required_authority"] == "privileged_registry_policy"


def test_mutation_requires_allowed_mode(delegate_root: Path):
    registry = load_delegate_registry(delegate_root)

    with pytest.raises(DelegateError) as exc_info:
        resolve_delegate_invocation("$ask $code-reviewer to fix src/foo.rs with $review-code", registry)

    assert exc_info.value.reason == "mutation_mode_not_allowed"

    envelope = resolve_delegate_invocation("$ask $backend-coder to fix src/foo.rs with $code-runner", registry)
    assert envelope["mode"] == "workspace_write"
    assert envelope["policy"]["mutation"] == "workspace_write"
