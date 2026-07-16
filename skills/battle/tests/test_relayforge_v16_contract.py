from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from battle_skill import relayforge_v16
from battle_skill.cli import app


IMAGE_ID = "sha256:" + "a" * 64
BASE_IMAGE = "python@sha256:" + "b" * 64
COMMIT = "c" * 40


def _skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _arena_root() -> Path:
    return _skill_root() / "arena" / "relayforge-v16"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _modules():
    service = _load_module("test_relayforge_service", _arena_root() / "service.py")
    reference = _load_module(
        "test_relayforge_reference", _arena_root() / "rf_a_reference.py"
    )
    judge = _load_module("test_relayforge_judge", _arena_root() / "judge" / "judge.py")
    return service, reference, judge


def _freeze(tmp_path: Path, name: str = "freeze") -> tuple[dict, Path]:
    out = tmp_path / name
    receipt = relayforge_v16.freeze_relayforge_target(
        out=out,
        image_digest=IMAGE_ID,
        base_image_digest=BASE_IMAGE,
        repository_commit=COMMIT,
        skill_root=_skill_root(),
    )
    return receipt, out


def test_freeze_is_byte_stable_partial_and_never_qualifies(tmp_path: Path) -> None:
    first_receipt, first = _freeze(tmp_path, "first")
    second_receipt, second = _freeze(tmp_path, "second")

    names = sorted(path.name for path in first.iterdir() if path.is_file())
    assert names == sorted(path.name for path in second.iterdir() if path.is_file())
    for name in names:
        assert (first / name).read_bytes() == (second / name).read_bytes()

    identity = json.loads((first / "target-identity.json").read_text())
    private = json.loads((first / "private-truth-manifest.json").read_text())
    assert first_receipt["status"] == "CONTRACT_FROZEN"
    assert first_receipt["pass_emitted"] is False
    assert first_receipt["qualification_eligible"] is False
    assert first_receipt["target_identity_sha256"] == second_receipt[
        "target_identity_sha256"
    ]
    assert identity["status"] == "FROZEN_NOT_QUALIFIED"
    assert private["implementation_status"] == "PARTIAL_RF_A"
    assert next(item for item in private["sinks"] if item["sink_id"] == "RF-A-SINK")[
        "implementation_status"
    ] == "IMPLEMENTED"
    assert "rf-b-predicates-unimplemented" in identity["blockers"]


def test_public_context_contains_no_private_identifier(tmp_path: Path) -> None:
    _, out = _freeze(tmp_path)
    public_context = json.loads((out / "public-context-manifest.json").read_text())
    private_truth = json.loads((out / "private-truth-manifest.json").read_text())
    public_text = json.dumps(public_context, sort_keys=True).casefold()
    leaked = [
        item
        for item in private_truth["private_identifiers"]
        if item.casefold() in public_text
    ]
    assert leaked == []


def test_freeze_rejects_mutable_image_and_uncommitted_identity(tmp_path: Path) -> None:
    with pytest.raises(relayforge_v16.RelayForgeContractError, match="image-digest"):
        relayforge_v16.freeze_relayforge_target(
            out=tmp_path / "bad-image",
            image_digest="relayforge-v16:dev",
            base_image_digest=BASE_IMAGE,
            repository_commit=COMMIT,
            skill_root=_skill_root(),
        )
    with pytest.raises(relayforge_v16.RelayForgeContractError, match="repository-commit"):
        relayforge_v16.freeze_relayforge_target(
            out=tmp_path / "bad-commit",
            image_digest=IMAGE_ID,
            base_image_digest=BASE_IMAGE,
            repository_commit="WORKTREE",
            skill_root=_skill_root(),
        )


def test_compose_keeps_public_port_and_sink_ownership_bounded() -> None:
    compose = (_arena_root() / "compose.yaml").read_text(encoding="utf-8")
    for service in (
        "edge-gateway",
        "package-api",
        "extract-worker",
        "report-cache",
        "preview-fetcher",
        "capability-broker",
        "document-renderer",
        "legacy-convert",
        "judge-probe",
    ):
        assert f"  {service}:" in compose
    assert compose.count("127.0.0.1:${RELAYFORGE_PUBLIC_PORT:-18080}:8080") == 1
    assert "relayforge-state:" in compose
    extract_block = compose.split("  extract-worker:", 1)[1].split(
        "\n  report-cache:", 1
    )[0]
    assert "rf-a-sink:/var/lib/relayforge/sinks/rf-a" in extract_block
    assert "rf-b-sink:/var/lib/relayforge/sinks/rf-b:ro" in extract_block
    assert "rf-c-sink:/var/lib/relayforge/sinks/rf-c:ro" in extract_block
    assert "relayforge-judge:" in compose
    assert "internal: true" in compose


def test_malformed_filename_alone_earns_no_judge_stage(tmp_path: Path) -> None:
    service, reference, judge = _modules()
    state_root = tmp_path / "state"
    sink_root = tmp_path / "sinks"
    reset = service.reset_arena(state_root=state_root, sink_root=sink_root)
    status, response = service.process_package_import(
        body=service.canonical_bytes(reference.malformed_name_package()),
        state_root=state_root,
        sink_root=sink_root,
    )
    outcome = judge.evaluate_rf_a(
        state_root=state_root,
        sink_root=sink_root,
        job_id="rf-a-malformed",
    )
    assert int(status) == 422
    assert response["reason"] == "invalid_member_name"
    assert outcome["highest_stage"] == "UNSEEN"
    assert outcome["valid_evidence_observed"] is False
    assert outcome["sink_after_sha256"] == reset["sink_hashes"]


def test_valid_staged_package_reaches_only_rf_a_sink(tmp_path: Path) -> None:
    service, reference, judge = _modules()
    state_root = tmp_path / "state"
    sink_root = tmp_path / "sinks"
    paths = service.ArenaPaths.resolve(state_root=state_root, sink_root=sink_root)
    service.reset_arena(state_root=state_root, sink_root=sink_root)
    package = reference.exploit_package(
        rf_a_target=str(paths.sink_dir("RF-A-SINK"))
    )
    status, response = service.process_package_import(
        body=service.canonical_bytes(package),
        state_root=state_root,
        sink_root=sink_root,
    )
    outcome = judge.evaluate_rf_a(
        state_root=state_root,
        sink_root=sink_root,
        job_id="rf-a-reference",
    )
    assert int(status) == 201
    assert response["observations"][0]["observation_id"] == "OBS-10"
    assert response["observations"][1]["observation_id"] == "OBS-11"
    assert outcome["highest_stage"] == "PROTECTED_OBJECTIVE"
    assert outcome["protected_objective_measured"] is True
    assert outcome["sink_isolation_proven"] is True
    assert outcome["sink_before_sha256"]["RF-B-SINK"] == outcome[
        "sink_after_sha256"
    ]["RF-B-SINK"]
    assert outcome["sink_before_sha256"]["RF-C-SINK"] == outcome[
        "sink_after_sha256"
    ]["RF-C-SINK"]


def test_narrow_defense_revalidates_final_identity_and_preserves_behavior(
    tmp_path: Path,
) -> None:
    service, reference, judge = _modules()
    state_root = tmp_path / "state"
    sink_root = tmp_path / "sinks"
    paths = service.ArenaPaths.resolve(state_root=state_root, sink_root=sink_root)
    reset = service.reset_arena(state_root=state_root, sink_root=sink_root)
    service.set_extractor_identity_defense(
        enabled=True, state_root=state_root, sink_root=sink_root
    )
    status, response = service.process_package_import(
        body=service.canonical_bytes(
            reference.exploit_package(rf_a_target=str(paths.sink_dir("RF-A-SINK")))
        ),
        state_root=state_root,
        sink_root=sink_root,
    )
    outcome = judge.evaluate_rf_a(
        state_root=state_root,
        sink_root=sink_root,
        job_id="rf-a-reference",
    )
    assert int(status) == 409
    assert response["status"] == "CONTAINED"
    assert outcome["highest_stage"] == "REPRODUCIBLE_PROBE"
    assert outcome["boundary_violation_measured"] is False
    assert outcome["sink_after_sha256"] == reset["sink_hashes"]


def test_rf_a_suite_proves_shortcuts_regressions_isolation_and_reset(
    tmp_path: Path,
) -> None:
    _, _, judge = _modules()
    out = tmp_path / "proof"
    result = judge.run_rf_a_suite(
        state_root=tmp_path / "state",
        sink_root=tmp_path / "sinks",
        out=out,
    )
    assert result["status"] == "PASS"
    assert result["vulnerable_highest_stage"] == "PROTECTED_OBJECTIVE"
    assert result["defended_highest_stage"] == "REPRODUCIBLE_PROBE"
    assert result["regression_pass_count"] == 6
    assert result["shortcut_pass_count"] == 4
    assert result["sink_isolation_status"] == "PASS"
    assert result["reset_replay_byte_identical"] is True

    shortcuts = json.loads((out / "rf-a-shortcut-matrix.json").read_text())
    regressions = json.loads((out / "rf-a-regression-matrix.json").read_text())
    assert shortcuts["status"] == "PASS"
    assert all(item["passed"] for item in shortcuts["cases"])
    assert regressions["status"] == "PASS"
    assert regressions["sink_hashes_unchanged"] is True
    assert [item["function_id"] for item in regressions["fixtures"]] == [
        "regular-package-import",
        "in-bound-transformed-object",
        "tenant-owned-report",
        "valid-external-preview",
        "safe-report-profile",
        "legacy-conversion",
    ]
    assert all(item["passed"] for item in regressions["fixtures"])


def test_deterministic_qualification_credits_rf_a_but_full_target_stays_blocked(
    tmp_path: Path,
) -> None:
    _, freeze = _freeze(tmp_path)
    out = tmp_path / "qualification"
    result = relayforge_v16.run_relayforge_deterministic_qualification(
        freeze=freeze,
        out=out,
        skill_root=_skill_root(),
    )
    assert result["status"] == "BLOCKED"
    assert result["rf_a_vertical_status"] == "PASS"
    assert result["pass_emitted"] is False
    assert "rf-b-predicates-unimplemented" in result["blockers"]
    assert "rf-c-predicates-unimplemented" in result["blockers"]
    assert "rf-d-decoy-validation-unimplemented" in result["blockers"]
    assert not any("predicate:rf-a" in item for item in result["blockers"])
    for name, expected in result["rf_a_artifact_sha256"].items():
        payload = json.loads((out / name).read_text())
        assert relayforge_v16.canonical_sha256(payload) == expected
    judge_outcome = json.loads((out / "judge-outcome.json").read_text())
    assert judge_outcome["status"] == "BLOCKED"
    assert judge_outcome["rf_a_vertical"]["status"] == "PASS"
    assert judge_outcome["pass_emitted"] is False


def test_cli_freezes_then_returns_nonzero_for_incomplete_full_target(
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    freeze_dir = tmp_path / "cli-freeze"
    freeze_result = runner.invoke(
        app,
        [
            "v16-arena-freeze",
            "--targets",
            relayforge_v16.TARGET_ID,
            "--out",
            str(freeze_dir),
            "--image-digest",
            IMAGE_ID,
            "--base-image-digest",
            BASE_IMAGE,
            "--repository-commit",
            COMMIT,
        ],
    )
    assert freeze_result.exit_code == 0, freeze_result.output
    assert (freeze_dir / "target-identity.json").is_file()

    qualification_dir = tmp_path / "cli-qualification"
    qualify_result = runner.invoke(
        app,
        [
            "v16-arena-deterministic-qualify",
            "--target",
            relayforge_v16.TARGET_ID,
            "--freeze",
            str(freeze_dir),
            "--out",
            str(qualification_dir),
        ],
    )
    assert qualify_result.exit_code == 1
    assert '"status": "BLOCKED"' in qualify_result.output
    assert '"rf_a_vertical_status": "PASS"' in qualify_result.output
    assert (qualification_dir / "rf-a-vulnerable-reference.json").is_file()
    assert (qualification_dir / "deterministic-qualification.json").is_file()
