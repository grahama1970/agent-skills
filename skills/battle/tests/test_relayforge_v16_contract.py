from __future__ import annotations

import importlib.util
import json
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


def test_freeze_is_byte_stable_and_never_qualifies(tmp_path: Path) -> None:
    first_receipt, first = _freeze(tmp_path, "first")
    second_receipt, second = _freeze(tmp_path, "second")

    names = sorted(path.name for path in first.iterdir() if path.is_file())
    assert names == sorted(path.name for path in second.iterdir() if path.is_file())
    for name in names:
        assert (first / name).read_bytes() == (second / name).read_bytes()

    first_identity = json.loads((first / "target-identity.json").read_text())
    second_identity = json.loads((second / "target-identity.json").read_text())
    assert first_receipt["status"] == "CONTRACT_FROZEN"
    assert first_receipt["pass_emitted"] is False
    assert first_receipt["qualification_eligible"] is False
    assert first_identity == second_identity
    assert first_receipt["target_identity_sha256"] == second_receipt[
        "target_identity_sha256"
    ]
    assert first_identity["status"] == "FROZEN_NOT_QUALIFIED"


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


def test_compose_declares_only_gateway_port_and_three_independent_sinks() -> None:
    compose = (
        _skill_root() / "arena" / "relayforge-v16" / "compose.yaml"
    ).read_text(encoding="utf-8")
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
    assert "rf-a-sink:" in compose
    assert "rf-b-sink:" in compose
    assert "rf-c-sink:" in compose
    assert "relayforge-judge:" in compose
    assert "internal: true" in compose


def test_service_skeleton_healths_and_blocks_security_workflows() -> None:
    service_path = _skill_root() / "arena" / "relayforge-v16" / "service.py"
    spec = importlib.util.spec_from_file_location("relayforge_service_test", service_path)
    assert spec is not None and spec.loader is not None
    service = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(service)

    health_status, health = service.response_for(
        role="edge-gateway", method="GET", path="/healthz"
    )
    import_status, blocked = service.response_for(
        role="edge-gateway",
        method="POST",
        path="/api/v1/jobs/import",
        body=b"fixture",
    )
    judge_status, judge = service.response_for(
        role="judge-probe", method="POST", path="/judge/evaluate"
    )

    assert int(health_status) == 200
    assert health["implementation_status"] == "SKELETON_BLOCKED"
    assert int(import_status) == 503
    assert blocked["status"] == "BLOCKED"
    assert blocked["qualification_eligible"] is False
    assert int(judge_status) == 503
    assert judge["status"] == "BLOCKED"
    assert judge["pass_emitted"] is False


def test_deterministic_qualification_fails_closed(tmp_path: Path) -> None:
    _, freeze = _freeze(tmp_path)
    result = relayforge_v16.run_relayforge_deterministic_qualification(
        freeze=freeze,
        out=tmp_path / "qualification",
        skill_root=_skill_root(),
    )

    assert result["status"] == "BLOCKED"
    assert result["pass_emitted"] is False
    assert "judge_evaluator_registry_unimplemented" in result["blockers"]
    assert "reference_exploit_receipts_missing" in result["blockers"]
    assert (tmp_path / "qualification" / "judge-outcome.json").is_file()
    assert (tmp_path / "qualification" / "deterministic-qualification.json").is_file()


def test_cli_freezes_then_returns_nonzero_for_unfinished_qualification(
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

    qualify_result = runner.invoke(
        app,
        [
            "v16-arena-deterministic-qualify",
            "--target",
            relayforge_v16.TARGET_ID,
            "--freeze",
            str(freeze_dir),
            "--out",
            str(tmp_path / "cli-qualification"),
        ],
    )
    assert qualify_result.exit_code == 1
    assert '"status": "BLOCKED"' in qualify_result.output
