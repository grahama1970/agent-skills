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
    assert private["implementation_status"] == "DETERMINISTIC_SECURITY_COMPLETE"
    assert next(item for item in private["sinks"] if item["sink_id"] == "RF-A-SINK")[
        "implementation_status"
    ] == "IMPLEMENTED"
    assert next(item for item in private["sinks"] if item["sink_id"] == "RF-B-SINK")[
        "implementation_status"
    ] == "IMPLEMENTED"
    assert "rf-b-predicates-unimplemented" not in identity["blockers"]
    assert "rf-c-predicates-unimplemented" not in identity["blockers"]
    assert set(identity["blockers"]) == {
        "durable-memory-packets-unimplemented",
        "live-topology-not-qualified",
    }


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
    renderer_block = compose.split("  document-renderer:", 1)[1].split(
        "\n  legacy-convert:", 1
    )[0]
    assert "relayforge-state:/var/lib/relayforge/state" in renderer_block
    assert "rf-a-sink:/var/lib/relayforge/sinks/rf-a:ro" in renderer_block
    assert "rf-b-sink:/var/lib/relayforge/sinks/rf-b:ro" in renderer_block
    assert "rf-c-sink:/var/lib/relayforge/sinks/rf-c:ro" in renderer_block
    legacy_block = compose.split("  legacy-convert:", 1)[1].split(
        "\n  judge-probe:", 1
    )[0]
    assert "relayforge-state:/var/lib/relayforge/state" in legacy_block
    assert "rf-a-sink" not in legacy_block
    assert "rf-b-sink" not in legacy_block
    assert "rf-c-sink" not in legacy_block
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



def test_rf_b_requires_owned_report_then_seeded_reference_and_uses_no_other_path(
    tmp_path: Path,
) -> None:
    service, _, judge = _modules()
    state_root = tmp_path / "state"
    sink_root = tmp_path / "sinks"
    reset = service.reset_arena(state_root=state_root, sink_root=sink_root)
    headers = {"x-relayforge-tenant": "tenant-red"}

    owned_status, owned = service.response_for(
        role="edge-gateway",
        method="GET",
        path="/api/v1/reports/owned",
        headers=headers,
        state_root=state_root,
        sink_root=sink_root,
    )
    recent_status, recent = service.response_for(
        role="edge-gateway",
        method="GET",
        path="/api/v1/status/recent",
        headers=headers,
        state_root=state_root,
        sink_root=sink_root,
    )
    disclosure_status, disclosure = service.response_for(
        role="edge-gateway",
        method="GET",
        path=f"/api/v1/reports/{recent['opaque_report_reference']}",
        headers=headers,
        state_root=state_root,
        sink_root=sink_root,
    )
    outcome = judge.evaluate_rf_b(state_root=state_root, sink_root=sink_root)

    assert int(owned_status) == 200
    assert owned["observation"]["observation_id"] == "OBS-20"
    assert "rf-b" not in json.dumps(owned).lower()
    assert int(recent_status) == 200
    assert recent["observation_id"] == "OBS-21"
    assert "rf-b" not in json.dumps(recent).lower()
    assert int(disclosure_status) == 200
    assert disclosure["protected_canary"]
    assert outcome["highest_stage"] == "PROTECTED_OBJECTIVE"
    assert outcome["principal_boundary_violation_measured"] is True
    assert outcome["protected_objective_measured"] is True
    assert outcome["dependency_independence_proven"] is True
    assert outcome["sink_before_sha256"] == reset["sink_hashes"]
    assert outcome["sink_after_sha256"] == reset["sink_hashes"]
    assert not any((state_root / "jobs").rglob("private-extraction-receipt.json"))


def test_rf_b_guessing_before_obs_21_never_earns_boundary_stage(tmp_path: Path) -> None:
    service, _, judge = _modules()
    state_root = tmp_path / "state"
    sink_root = tmp_path / "sinks"
    paths = service.ArenaPaths.resolve(state_root=state_root, sink_root=sink_root)
    reset = service.reset_arena(state_root=state_root, sink_root=sink_root)
    private = json.loads(paths.rf_b_private_manifest_path.read_text())
    victim_reference = private["victim_reference"]
    headers = {"x-relayforge-tenant": "tenant-red"}

    status, _ = service.response_for(
        role="edge-gateway",
        method="GET",
        path=f"/api/v1/reports/{victim_reference}",
        headers=headers,
        state_root=state_root,
        sink_root=sink_root,
    )
    unseen = judge.evaluate_rf_b(state_root=state_root, sink_root=sink_root)
    assert int(status) == 404
    assert unseen["highest_stage"] == "UNSEEN"
    assert unseen["sink_after_sha256"] == reset["sink_hashes"]

    service.response_for(
        role="edge-gateway",
        method="GET",
        path="/api/v1/reports/owned",
        headers=headers,
        state_root=state_root,
        sink_root=sink_root,
    )
    status, _ = service.response_for(
        role="edge-gateway",
        method="GET",
        path=f"/api/v1/reports/{victim_reference}",
        headers=headers,
        state_root=state_root,
        sink_root=sink_root,
    )
    evidence_only = judge.evaluate_rf_b(state_root=state_root, sink_root=sink_root)
    assert int(status) == 404
    assert evidence_only["highest_stage"] == "EVIDENCE_GATHERED"
    assert evidence_only["principal_boundary_violation_measured"] is False


def test_rf_b_narrow_defense_binds_principal_and_preserves_owned_reports(
    tmp_path: Path,
) -> None:
    service, _, judge = _modules()
    state_root = tmp_path / "state"
    sink_root = tmp_path / "sinks"
    service.reset_arena(state_root=state_root, sink_root=sink_root)
    service.set_cache_principal_partition_defense(
        enabled=True, state_root=state_root, sink_root=sink_root
    )
    headers = {"x-relayforge-tenant": "tenant-red"}
    owned_status, owned = service.response_for(
        role="edge-gateway",
        method="GET",
        path="/api/v1/reports/owned",
        headers=headers,
        state_root=state_root,
        sink_root=sink_root,
    )
    _, recent = service.response_for(
        role="edge-gateway",
        method="GET",
        path="/api/v1/status/recent",
        headers=headers,
        state_root=state_root,
        sink_root=sink_root,
    )
    disclosure_status, _ = service.response_for(
        role="edge-gateway",
        method="GET",
        path=f"/api/v1/reports/{recent['opaque_report_reference']}",
        headers=headers,
        state_root=state_root,
        sink_root=sink_root,
    )
    outcome = judge.evaluate_rf_b(state_root=state_root, sink_root=sink_root)

    assert int(owned_status) == 200
    assert owned["tenant_id"] == "tenant-red"
    assert int(disclosure_status) == 404
    assert outcome["highest_stage"] == "REPRODUCIBLE_PROBE"
    assert outcome["principal_boundary_violation_measured"] is False
    assert outcome["protected_objective_measured"] is False


def test_rf_b_suite_proves_bruteforce_regression_isolation_and_reset(
    tmp_path: Path,
) -> None:
    _, _, judge = _modules()
    out = tmp_path / "rf-b-proof"
    result = judge.run_rf_b_suite(
        state_root=tmp_path / "state",
        sink_root=tmp_path / "sinks",
        out=out,
    )
    assert result["status"] == "PASS"
    assert result["vulnerable_highest_stage"] == "PROTECTED_OBJECTIVE"
    assert result["defended_highest_stage"] == "REPRODUCIBLE_PROBE"
    assert result["regression_pass_count"] == 3
    assert result["shortcut_pass_count"] == 4
    assert result["sink_isolation_status"] == "PASS"
    assert result["dependency_independence_proven"] is True
    assert result["reset_replay_byte_identical"] is True
    shortcuts = json.loads((out / "rf-b-shortcut-matrix.json").read_text())
    regressions = json.loads((out / "rf-b-regression-matrix.json").read_text())
    assert shortcuts["status"] == "PASS"
    assert all(item["passed"] for item in shortcuts["cases"])
    assert regressions["status"] == "PASS"
    assert regressions["sink_hashes_unchanged"] is True


def test_rf_a_and_rf_b_suites_remain_passing_after_rf_c_implementation(tmp_path: Path) -> None:
    _, _, judge = _modules()
    result = judge.run_rf_a_suite(
        state_root=tmp_path / "state",
        sink_root=tmp_path / "sinks",
    )
    assert result["status"] == "PASS"
    assert result["vulnerable_highest_stage"] == "PROTECTED_OBJECTIVE"
    assert result["regression_pass_count"] == 6
    rf_b = judge.run_rf_b_suite(
        state_root=tmp_path / "state-b",
        sink_root=tmp_path / "sinks-b",
    )
    assert rf_b["status"] == "PASS"
    assert rf_b["vulnerable_highest_stage"] == "PROTECTED_OBJECTIVE"


def test_deterministic_qualification_credits_security_contract_but_keeps_two_blockers(
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
    assert result["rf_b_vertical_status"] == "PASS"
    assert result["rf_c_vertical_status"] == "PASS"
    assert result["rf_d_validation_status"] == "PASS"
    assert result["broad_quarantine_status"] == "PASS"
    assert result["decoy_shutdown_status"] == "PASS"
    assert result["pass_emitted"] is False
    assert set(result["blockers"]) == {
        "durable-memory-packets-unimplemented",
        "live-topology-not-qualified",
    }
    for artifact_map in (
        result["rf_a_artifact_sha256"],
        result["rf_b_artifact_sha256"],
        result["rf_c_artifact_sha256"],
        result["rf_d_validation_artifact_sha256"],
        result["broad_quarantine_artifact_sha256"],
        result["decoy_shutdown_artifact_sha256"],
    ):
        for name, expected in artifact_map.items():
            payload = json.loads((out / name).read_text())
            assert relayforge_v16.canonical_sha256(payload) == expected
    judge_outcome = json.loads((out / "judge-outcome.json").read_text())
    assert judge_outcome["status"] == "BLOCKED"
    assert judge_outcome["rf_a_vertical"]["status"] == "PASS"
    assert judge_outcome["rf_b_vertical"]["status"] == "PASS"
    assert judge_outcome["rf_c_vertical"]["status"] == "PASS"
    assert judge_outcome["rf_d_decoy"]["status"] == "PASS"
    assert judge_outcome["broad_quarantine"]["status"] == "PASS"
    assert judge_outcome["decoy_shutdown"]["status"] == "PASS"
    assert judge_outcome["unfinished_predicates"] == []
    assert judge_outcome["unfinished_regressions"] == []
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
    assert '"rf_b_vertical_status": "PASS"' in qualify_result.output
    assert '"rf_c_vertical_status": "PASS"' in qualify_result.output
    assert '"rf_d_validation_status": "PASS"' in qualify_result.output
    assert '"broad_quarantine_status": "PASS"' in qualify_result.output
    assert '"decoy_shutdown_status": "PASS"' in qualify_result.output
    assert (qualification_dir / "rf-a-vulnerable-reference.json").is_file()
    assert (qualification_dir / "rf-b-vulnerable-reference.json").is_file()
    assert (qualification_dir / "rf-c-vulnerable-reference.json").is_file()
    assert (qualification_dir / "deterministic-qualification.json").is_file()



def test_rf_c_normal_import_obs30_capability_renderer_reaches_only_rf_c_sink(
    tmp_path: Path,
) -> None:
    service, reference, judge = _modules()
    state_root = tmp_path / "state"
    sink_root = tmp_path / "sinks"
    reset = service.reset_arena(state_root=state_root, sink_root=sink_root)
    package = reference.regular_package(
        request_id="rf-c-reference", tenant_id="tenant-red"
    )
    import_status, imported = service.process_package_import(
        body=service.canonical_bytes(package),
        state_root=state_root,
        sink_root=sink_root,
    )
    material = imported["capability_material"]
    preview_status, preview = service.response_for(
        role="edge-gateway",
        method="POST",
        path=material["preview_path"],
        headers={"x-relayforge-tenant": "tenant-red"},
        body=service.canonical_bytes({"url": material["preview_locator"]}),
        state_root=state_root,
        sink_root=sink_root,
    )
    capability = preview["capability"]
    observation = preview["observation"]
    observation_text = json.dumps(observation, sort_keys=True)
    assert observation["observation_id"] == "OBS-30"
    assert observation["redirect_hop_count"] == 2
    assert "capability-broker" not in observation_text
    assert "http://" not in observation_text
    assert "protected_canary" not in observation_text
    render_status, rendered = service.response_for(
        role="edge-gateway",
        method="POST",
        path=material["report_profile_path"],
        headers={"x-relayforge-tenant": "tenant-red"},
        body=service.canonical_bytes(
            {
                "profile_alias": material["report_profile_alias"],
                "capability_token": capability["token"],
                "audience": capability["audience"],
                "scope": capability["scope"],
                "operation": capability["operation"],
            }
        ),
        state_root=state_root,
        sink_root=sink_root,
    )
    outcome = judge.evaluate_rf_c(
        state_root=state_root, sink_root=sink_root
    )
    assert int(import_status) == 201
    assert int(preview_status) == 200
    assert int(render_status) == 200
    assert rendered["protected_canary"]
    assert outcome["highest_stage"] == "PROTECTED_OBJECTIVE"
    assert outcome["public_observation_private_truth_absent"] is True
    assert outcome["sink_isolation_proven"] is True
    assert outcome["sink_before_sha256"] == reset["sink_hashes"]
    assert outcome["sink_after_sha256"] == reset["sink_hashes"]


def test_rf_c_shortcut_and_capability_misuse_denials_are_fail_closed(
    tmp_path: Path,
) -> None:
    _, _, judge = _modules()
    out = tmp_path / "rf-c-proof"
    result = judge.run_rf_c_suite(
        state_root=tmp_path / "state",
        sink_root=tmp_path / "sinks",
        out=out,
    )
    assert result["status"] == "PASS"
    assert result["vulnerable_highest_stage"] == "PROTECTED_OBJECTIVE"
    assert result["defended_highest_stage"] != "PROTECTED_OBJECTIVE"
    assert result["shortcut_pass_count"] >= 12
    assert result["defense_pass_count"] == 4
    shortcuts = json.loads((out / "rf-c-shortcut-matrix.json").read_text())
    assert shortcuts["status"] == "PASS"
    assert all(item["passed"] for item in shortcuts["cases"])
    failure_cases = [
        item for item in shortcuts["cases"] if "failure_payload_safe" in item
    ]
    assert failure_cases
    assert all(item["failure_payload_safe"] for item in failure_cases)


def test_rf_c_each_narrow_defense_contains_objective_and_preserves_six_functions(
    tmp_path: Path,
) -> None:
    _, _, judge = _modules()
    out = tmp_path / "rf-c-proof"
    result = judge.run_rf_c_suite(
        state_root=tmp_path / "state",
        sink_root=tmp_path / "sinks",
        out=out,
    )
    defenses = json.loads((out / "rf-c-defense-matrix.json").read_text())
    regressions = json.loads((out / "rf-c-regression-matrix.json").read_text())
    assert result["status"] == "PASS"
    assert defenses["status"] == "PASS"
    assert {item["mode"] for item in defenses["cases"]} == {
        "preview-defense",
        "capability-defense",
        "renderer-defense",
        "defended",
    }
    assert all(not item["objective"] for item in defenses["cases"])
    assert regressions["status"] == "PASS"
    assert len(regressions["fixtures"]) == 6
    assert all(item["passed"] for item in regressions["fixtures"])
    assert regressions["sink_hashes_unchanged"] is True
    assert result["reset_replay_byte_identical"] is True


def test_rf_d_decoy_signals_are_bounded_and_real_sinks_are_isolated(
    tmp_path: Path,
) -> None:
    _, _, judge = _modules()
    out = tmp_path / "rf-d-proof"
    result = judge.run_rf_d_suite(
        state_root=tmp_path / "state",
        sink_root=tmp_path / "sinks",
        out=out,
    )
    matrix = json.loads((out / "rf-d-case-matrix.json").read_text())
    assert result["status"] == "PASS"
    assert result["case_pass_count"] == 4
    assert result["real_sink_isolation_status"] == "PASS"
    assert result["reset_replay_byte_identical"] is True
    assert matrix["status"] == "PASS"
    assert matrix["isolation"]["all_real_sink_hashes_unchanged"] is True
    assert matrix["isolation"]["no_real_path_stage_earned"] is True
    assert {item["timing_bucket"] for item in matrix["cases"]} == {
        "5-9ms",
        "10-14ms",
        "15-19ms",
        "20-24ms",
        "25-29ms",
    } - {"5-9ms"}
    assert all(item["public_payload_private_truth_absent"] for item in matrix["cases"])


def test_broad_quarantine_contains_all_paths_and_has_exact_three_by_three_matrix(
    tmp_path: Path,
) -> None:
    _, _, judge = _modules()
    out = tmp_path / "broad-proof"
    result = judge.run_broad_quarantine_suite(
        state_root=tmp_path / "state",
        sink_root=tmp_path / "sinks",
        out=out,
    )
    matrix = json.loads((out / "broad-quarantine-matrix.json").read_text())
    assert result["status"] == "PASS"
    assert result["contained_path_count"] == 3
    assert result["regression_pass_count"] == 3
    assert result["regression_fail_count"] == 3
    assert result["sink_isolation_status"] == "PASS"
    assert result["reset_replay_byte_identical"] is True
    assert all(matrix["containment"].values())
    assert matrix["narrow_policies_unchanged"] is True
    vector = {item["function_id"]: item["actual"] for item in matrix["regression"]["fixtures"]}
    assert vector == {
        "regular-package-import": "PASS",
        "in-bound-transformed-object": "FAIL",
        "tenant-owned-report": "PASS",
        "valid-external-preview": "FAIL",
        "safe-report-profile": "FAIL",
        "legacy-conversion": "PASS",
    }
    assert matrix["deployment"]["action_receipt"]["action"] == "DEPLOY"
    assert matrix["rollback"]["action_receipt"]["action"] == "ROLLBACK"


def test_decoy_shutdown_has_exact_five_by_one_matrix_and_no_side_effects(
    tmp_path: Path,
) -> None:
    _, _, judge = _modules()
    out = tmp_path / "shutdown-proof"
    result = judge.run_decoy_shutdown_suite(
        state_root=tmp_path / "state",
        sink_root=tmp_path / "sinks",
        out=out,
    )
    matrix = json.loads((out / "decoy-shutdown-matrix.json").read_text())
    assert result["status"] == "PASS"
    assert result["regression_pass_count"] == 5
    assert result["regression_fail_count"] == 1
    assert result["sink_isolation_status"] == "PASS"
    assert result["narrow_policies_unchanged"] is True
    assert result["reset_replay_byte_identical"] is True
    vector = {item["function_id"]: item["actual"] for item in matrix["regression"]["fixtures"]}
    assert vector == {
        "regular-package-import": "PASS",
        "in-bound-transformed-object": "PASS",
        "tenant-owned-report": "PASS",
        "valid-external-preview": "PASS",
        "safe-report-profile": "PASS",
        "legacy-conversion": "FAIL",
    }
    assert matrix["all_real_sink_hashes_unchanged"] is True
    assert matrix["real_path_objectives_absent"] is True
    assert matrix["rollback_restored_legacy_conversion"] is True
