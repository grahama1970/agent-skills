"""Tests for scripts/create_successor_revision.py.

These exercise the identity-source successor revision builder end to end against
the frozen source revision and a fake Memory server:

* successor derivation (durable repo-rooted revision, active/consistent, Memory
  exact reread of the 42-step bundle),
* out-of-repository ``revisionRoot`` rejection (activation fails closed),
* montage-stale ledger coverage (every Phase 07-11 montage artifact marked
  stale/superseded), and
* durable active-pointer schema.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


SKILL_ROOT = Path(__file__).parents[1]
CREATE_SCRIPT = SKILL_ROOT / "scripts" / "create_successor_revision.py"
ACTIVATION_SCRIPT = SKILL_ROOT / "scripts" / "activate_revision_qualification.py"
PREPARE_TESTS = SKILL_ROOT / "tests" / "test_revision_memory_qualification.py"
FROZEN_REVISION_ID = "rev_upstream_bf3b05d47fb8"
FROZEN_REVISION_ROOT = (
    SKILL_ROOT
    / "reports"
    / "pipeline-complete"
    / ".persona-dream"
    / "revisions"
    / FROZEN_REVISION_ID
)
IDENTITY_RECEIPT = SKILL_ROOT / "reports" / "embry-contact-sheet-qualification-20260717.json"
SOURCE_COMMIT = "62c255c9b8d380079ce37c39cab3ab9adada30e3"


def load_module(name: str, path: Path) -> ModuleType:
    sys.path.insert(0, str(SKILL_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


MEMORY_FIXTURE = load_module("persona_dream_memory_fixture_helpers", PREPARE_TESTS)
ACTIVATION = load_module("persona_dream_activation_script", ACTIVATION_SCRIPT)

requires_frozen = pytest.mark.skipif(
    not FROZEN_REVISION_ROOT.is_dir() or not IDENTITY_RECEIPT.is_file(),
    reason="frozen source revision or identity qualification receipt is unavailable",
)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_source_run_root(tmp_path: Path) -> Path:
    """Copy the frozen revision into an isolated run root (minus heavy media)."""
    run_root = tmp_path / "pipeline-complete"
    revisions = run_root / ".persona-dream" / "revisions"
    revisions.mkdir(parents=True)
    shutil.copytree(
        FROZEN_REVISION_ROOT,
        revisions / FROZEN_REVISION_ID,
        symlinks=False,
        ignore=shutil.ignore_patterns("provider_return"),
    )
    write_json(
        run_root / ".persona-dream" / "state" / "active_revision.json",
        {
            "schemaVersion": "persona_dream.active_revision_pointer.v1",
            "runId": run_root.name,
            "revisionId": FROZEN_REVISION_ID,
            "revisionRoot": str(revisions / FROZEN_REVISION_ID),
            "revisionManifestSha256": "sha256:" + "0" * 64,
            "ideaId": "pd_idea_placeholder",
            "ideaSha256": "sha256:" + "0" * 64,
        },
    )
    return run_root


def run_create(run_root: Path, memory_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(CREATE_SCRIPT),
            "--run-root",
            str(run_root),
            "--source-commit",
            SOURCE_COMMIT,
            "--memory-url",
            memory_url,
            "--collection",
            MEMORY_FIXTURE.COLLECTION,
            "--connect-timeout",
            "2",
            "--read-timeout",
            "10",
            "--test-fixture",
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )


@requires_frozen
def test_successor_derivation_activates_with_durable_pointer(tmp_path: Path) -> None:
    run_root = build_source_run_root(tmp_path)
    with MEMORY_FIXTURE.fake_memory_server() as (memory_url, state):
        completed = run_create(run_root, memory_url)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        receipt = json.loads(completed.stdout)

    assert receipt["status"] == "PASS_IDENTITY_SOURCE_SUCCESSOR_ACTIVE"
    assert receipt["source_revision_id"] == FROZEN_REVISION_ID
    successor_id = receipt["target_revision_id"]
    assert successor_id.startswith("rev_successor_")
    assert successor_id != FROZEN_REVISION_ID
    assert receipt["memory_prepare_status"] == "PASS_MEMORY_REVISION_PREPARED"
    assert receipt["memory_verify_status"] == "PASS_MEMORY_REVISION_VERIFIED"
    assert receipt["activation_status"] == "PASS_ACTIVE_CONSISTENT"
    assert receipt["pipeline_step_memory_status"].startswith("PASS_EXACT_REREAD_42_OF_42")
    assert receipt["pipeline_step_memory_exact_reread_count"] == 42
    assert receipt["bound_identity_source"]["asset_id"] == "embry_contact_sheet_v3"
    assert receipt["bound_identity_source"]["memory_record_key"] == "b11474f2fd5b54f332223a253fd743d1"

    # The frozen source revision is never mutated.
    assert (FROZEN_REVISION_ROOT / "revision_manifest.json").is_file()

    # The durable successor revision lives in the repo run root, never /tmp worktree.
    successor_root = run_root / ".persona-dream" / "revisions" / successor_id
    assert successor_root.is_dir()
    assert not (successor_root / "phase_11_submit_return").exists()

    # The active pointer is durable and repo-rooted.
    pointer = json.loads(
        (run_root / ".persona-dream" / "state" / "active_revision.json").read_text(encoding="utf-8")
    )
    assert pointer["schemaVersion"] == "persona_dream.active_revision_pointer.v1"
    assert pointer["revisionId"] == successor_id
    assert Path(pointer["revisionRoot"]) == successor_root.resolve()
    assert Path(pointer["revisionRoot"]).is_relative_to(run_root)

    # The step bundle was durably re-read from Memory.
    steps = state.collections.get("persona_dream_pipeline_steps", {})
    successor_steps = [d for d in steps.values() if d.get("revision_id") == successor_id]
    assert len(successor_steps) == 42


@requires_frozen
def test_ledger_marks_every_montage_artifact_stale(tmp_path: Path) -> None:
    run_root = build_source_run_root(tmp_path)
    with MEMORY_FIXTURE.fake_memory_server() as (memory_url, _state):
        completed = run_create(run_root, memory_url)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        receipt = json.loads(completed.stdout)
    successor_root = run_root / ".persona-dream" / "revisions" / receipt["target_revision_id"]

    ledger = json.loads(
        (successor_root / "identity_successor_invalidation_ledger.v1.json").read_text(encoding="utf-8")
    )
    assert ledger["ledger_kind"] == "identity_source_successor"
    assert ledger["accepted_identity_source"]["asset_id"] == "embry_contact_sheet_v3"
    assert ledger["rejected_identity_source"]["rejection_status"] == "FAIL_IDENTITY_REFERENCE_INCONSISTENT"

    relatives = {entry["relative_path"] for entry in ledger["stale_artifacts"]}
    # Eight storyboard start/end frames.
    for panel in ("sb_001", "sb_002", "sb_003", "sb_004"):
        for role in ("start", "end"):
            assert (
                f"phase_07_storyboard_live_tau/generated_storyboard_frames/{panel}_{role}_frame.png"
                in relatives
            )
    # Storyboard packet, media lock, rejected reference, rejection receipt, provider packet.
    assert "phase_07_storyboard_live_tau/storyboard_packet.json" in relatives
    assert "phase_08_media_lock/storyboard_media_lock_manifest.json" in relatives
    assert "phase_07_storyboard_live_tau/references/01-embry_character_sheet.jpg" in relatives
    assert "phase_07_storyboard_live_tau/receipts/identity_reference_qualification.v1.json" in relatives
    assert "phase_11_submit_return/canonical/phase11_live_request.v1.json" in relatives

    # Every stale artifact carries a fail-closed disposition and count matches.
    dispositions = {entry["disposition"] for entry in ledger["stale_artifacts"]}
    assert dispositions <= {
        "STALE_IDENTITY_SOURCE_SUPERSEDED",
        "SUPERSEDED_PROVIDER_EVIDENCE_PRIOR_REVISION",
    }
    assert ledger["stale_artifact_count"] == len(ledger["stale_artifacts"])
    assert ledger["stale_artifact_count"] >= 15

    # Successor-relative artifacts are hash-bound; provider evidence is superseded.
    for entry in ledger["stale_artifacts"]:
        if entry["location"] == "successor_revision":
            assert entry["sha256"] and entry["sha256"].startswith("sha256:")
            assert entry["disposition"] == "STALE_IDENTITY_SOURCE_SUPERSEDED"


@requires_frozen
def test_activation_rejects_out_of_repository_revision_root(tmp_path: Path) -> None:
    run_root = build_source_run_root(tmp_path)
    with MEMORY_FIXTURE.fake_memory_server() as (memory_url, _state):
        completed = run_create(run_root, memory_url)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        receipt = json.loads(completed.stdout)
        successor_id = receipt["target_revision_id"]

        # Point the durable pointer at a volatile out-of-repository worktree.
        pointer_path = run_root / ".persona-dream" / "state" / "active_revision.json"
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        volatile_root = tmp_path.parent / "volatile-worktree" / successor_id
        volatile_root.mkdir(parents=True, exist_ok=True)
        pointer["revisionRoot"] = str(volatile_root)
        write_json(pointer_path, pointer)

        completed = subprocess.run(
            [
                sys.executable,
                str(ACTIVATION_SCRIPT),
                "--run-root",
                str(run_root),
                "--revision-id",
                successor_id,
                "--source-commit",
                SOURCE_COMMIT,
                "--memory-url",
                memory_url,
                "--collection",
                MEMORY_FIXTURE.COLLECTION,
                "--connect-timeout",
                "2",
                "--read-timeout",
                "10",
                "--test-fixture",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    assert completed.returncode != 0
    assert (
        json.loads(completed.stdout)["status"]
        == "BLOCKED_ACTIVATION_REVISION_ROOT_OUTSIDE_REPOSITORY"
    )


def test_validate_local_pointer_rejects_tmp_root(tmp_path: Path) -> None:
    """Focused fail-closed unit test on the pointer validator."""
    run_root, revision_root = MEMORY_FIXTURE.write_revision(tmp_path)
    snapshot = ACTIVATION.load_snapshot(run_root, MEMORY_FIXTURE.REVISION_ID, SOURCE_COMMIT)
    lineage = MEMORY_FIXTURE.install_idea_lineage_fixture(revision_root)
    pointer_path = run_root / ".persona-dream" / "state" / "active_revision.json"

    # A durable in-repo pointer validates.
    write_json(
        pointer_path,
        {
            "schemaVersion": "persona_dream.active_revision_pointer.v1",
            "runId": run_root.name,
            "revisionId": MEMORY_FIXTURE.REVISION_ID,
            "revisionRoot": str(revision_root),
            "revisionManifestSha256": snapshot.manifest_sha256,
            "ideaId": lineage.idea_id,
            "ideaSha256": lineage.idea_sha256,
        },
    )
    assert ACTIVATION.validate_local_pointer(snapshot)["value"]["revisionId"] == MEMORY_FIXTURE.REVISION_ID

    # A /tmp-style out-of-repo pointer fails closed.
    outside = tmp_path.parent / "detached" / MEMORY_FIXTURE.REVISION_ID
    outside.mkdir(parents=True, exist_ok=True)
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["revisionRoot"] = str(outside)
    write_json(pointer_path, pointer)
    with pytest.raises(ACTIVATION.GateBlocked) as excinfo:
        ACTIVATION.validate_local_pointer(snapshot)
    assert excinfo.value.code == "BLOCKED_ACTIVATION_REVISION_ROOT_OUTSIDE_REPOSITORY"
