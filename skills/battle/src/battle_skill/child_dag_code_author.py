"""PR3c exploit-code-author node boundary for Battle child DAGs."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .provider_artifact_validator import validate_provider_artifact
from .provider_authorship import (
    build_phase1_boundary_receipt,
    build_provider_authorship_receipt,
)


BATTLE_WORK_ORDER_SCHEMA = "battle.exploit_code_author_work_order.v1"
TAU_SCILLM_WORK_ORDER_SCHEMA = "tau.executor.scillm_worker.v1"
WORKSPACE_BASELINE_SCHEMA = "battle.provider_workspace_baseline.v1"
SPECIMEN_SCHEMA = "battle.exploit_specimen.v2"
DEFAULT_PROVIDER_WORKSPACE_ROOT = Path(
    "/mnt/storage12tb/skills/battle/pr3c-provider-workspaces"
)


def run_code_author(
    *,
    artifact_dir: Path,
    lineage_summary_path: Path,
    research_receipts_path: Path,
    candidate_methods_path: Path,
    exploit_genome_path: Path,
    child_knowledge_packet_path: Path | None,
    dag_id: str | None,
    goal_hash: str | None,
    tau_root: Path | None = None,
    scillm_base_url: str | None = None,
    request_timeout_s: int | None = None,
) -> dict[str, Any]:
    """Run the PR3c provider-authorship boundary.

    The node may return BLOCKED when Tau/provider attestation is absent. It must
    never synthesize fixture exploit code.
    """

    artifact_dir = artifact_dir.expanduser().resolve()
    workspace = _provider_workspace_for(artifact_dir)
    if workspace.exists():
        shutil.rmtree(workspace)
    inputs = workspace / "inputs"
    outputs = workspace / "outputs"
    receipts = workspace / "receipts"
    logs = workspace / "logs"
    for path in (inputs, outputs, receipts, logs):
        path.mkdir(parents=True, exist_ok=True)

    lineage = _read_json(lineage_summary_path)
    research = _read_json(research_receipts_path)
    _read_json(candidate_methods_path)
    genome = _read_json(exploit_genome_path)
    child_packet = (
        _read_json(child_knowledge_packet_path)
        if child_knowledge_packet_path and child_knowledge_packet_path.exists()
        else {}
    )
    battle_id = str(
        genome.get("battle_id")
        or research.get("battle_id")
        or lineage.get("battle_id")
        or "battle-004"
    )
    child_lane_id = str(
        genome.get("child_lane_id")
        or research.get("child_lane_id")
        or lineage.get("child_lane_id")
        or child_packet.get("child_lane_id")
        or ""
    )

    copied_inputs = {
        "lineage_summary": _copy_input(lineage_summary_path, inputs),
        "research_receipts": _copy_input(research_receipts_path, inputs),
        "candidate_methods": _copy_input(candidate_methods_path, inputs),
        "exploit_genome": _copy_input(exploit_genome_path, inputs),
    }
    if child_knowledge_packet_path and child_knowledge_packet_path.exists():
        copied_inputs["child_knowledge_packet"] = _copy_input(
            child_knowledge_packet_path, inputs
        )

    baseline = _workspace_baseline(workspace=workspace, inputs=inputs, outputs=outputs)
    baseline_path = receipts / "workspace-baseline-manifest.json"
    _write_json(baseline_path, baseline)

    battle_work_order = _battle_work_order(
        battle_id=battle_id,
        dag_id=dag_id,
        child_lane_id=child_lane_id,
        goal_hash=goal_hash,
        input_paths=copied_inputs,
        output_root=outputs,
    )
    battle_work_order_path = inputs / "exploit-code-author-work-order.json"
    _write_json(battle_work_order_path, battle_work_order)

    tau_work_order = _tau_work_order(
        battle_work_order=battle_work_order,
        repo=workspace,
        result_path=Path("outputs/provider-worker-result.json"),
        receipt_path=Path("receipts/tau-worker-validation-receipt.json"),
    )
    tau_work_order_path = inputs / "tau-scillm-worker-work-order.json"
    _write_json(tau_work_order_path, tau_work_order)

    launch_receipt_path = receipts / "tau-scillm-worker-launch-receipt.json"
    validation_receipt_path = receipts / "tau-worker-validation-receipt.json"
    tau_root = tau_root or Path(
        os.environ.get("BATTLE_TAU_ROOT", "/home/graham/workspace/experiments/tau")
    )
    scillm_base_url = scillm_base_url or os.environ.get(
        "BATTLE_SCILLM_BASE_URL", "http://localhost:4001"
    )
    request_timeout_s = request_timeout_s or int(
        os.environ.get("BATTLE_PR3C_REQUEST_TIMEOUT_S", "600")
    )
    launch = _run_tau_scillm_launch(
        tau_root=tau_root,
        work_order_path=tau_work_order_path,
        out_path=launch_receipt_path,
        scillm_base_url=scillm_base_url,
        request_timeout_s=request_timeout_s,
    )

    worker_result_path = outputs / "provider-worker-result.json"
    worker_result = (
        _read_json(worker_result_path) if worker_result_path.exists() else None
    )
    validation = None
    if worker_result is not None:
        validation = _run_tau_scillm_validate(
            tau_root=tau_root,
            work_order_path=tau_work_order_path,
            result_path=worker_result_path,
            out_path=validation_receipt_path,
            launch_receipt_path=launch_receipt_path,
        )

    code_path = outputs / "exploit_specimen.py"
    artifact_validation = validate_provider_artifact(
        code_path=code_path,
        output_root=outputs,
        baseline_manifest=baseline,
        tau_worker_result=worker_result,
        tau_worker_validation=validation,
        out_path=receipts / "provider-artifact-validation.json",
    )

    authorship = build_provider_authorship_receipt(
        out_path=receipts / "provider-authorship-receipt.json",
        battle_id=battle_id,
        dag_id=dag_id,
        node_id="exploit-code-author",
        child_lane_id=child_lane_id,
        goal_hash=goal_hash,
        battle_work_order_path=battle_work_order_path,
        tau_work_order_path=tau_work_order_path,
        launch_receipt_path=launch_receipt_path,
        worker_result_path=worker_result_path if worker_result_path.exists() else None,
        worker_validation_path=validation_receipt_path
        if validation_receipt_path.exists()
        else None,
        artifact_validation=artifact_validation,
        launch_receipt=launch,
        worker_result=worker_result,
        worker_validation=validation,
    )
    boundary = build_phase1_boundary_receipt(
        out_path=receipts / "provider-code-author-boundary-receipt.json",
        authorship=authorship,
    )

    specimen_path = None
    if authorship.get("status") == "PASS":
        specimen_path = outputs / "specimen.json"
        _write_json(
            specimen_path,
            _specimen_metadata(
                battle_id=battle_id,
                child_lane_id=child_lane_id,
                genome=genome,
                code_path=code_path,
                authorship_path=receipts / "provider-authorship-receipt.json",
            ),
        )

    return {
        "status": "PASS" if boundary.get("status") == "PASS" else "BLOCKED",
        "verdict": "PASS"
        if boundary.get("status") == "PASS"
        else _blocked_verdict(authorship),
        "workspace": workspace,
        "inputs": inputs,
        "outputs": outputs,
        "receipts": receipts,
        "battle_work_order_path": battle_work_order_path,
        "tau_work_order_path": tau_work_order_path,
        "launch_receipt_path": launch_receipt_path,
        "worker_result_path": worker_result_path
        if worker_result_path.exists()
        else None,
        "validation_receipt_path": validation_receipt_path
        if validation_receipt_path.exists()
        else None,
        "artifact_validation_path": receipts / "provider-artifact-validation.json",
        "provider_authorship_path": receipts / "provider-authorship-receipt.json",
        "boundary_receipt_path": receipts
        / "provider-code-author-boundary-receipt.json",
        "code_path": code_path if code_path.exists() else None,
        "specimen_path": specimen_path,
        "authorship": authorship,
        "boundary": boundary,
        "claims": boundary.get("claims", {}),
    }


def _run_tau_scillm_launch(
    *,
    tau_root: Path,
    work_order_path: Path,
    out_path: Path,
    scillm_base_url: str,
    request_timeout_s: int,
) -> dict[str, Any] | None:
    command = [
        "uv",
        "run",
        "tau",
        "scillm-worker-launch",
        "--work-order",
        str(work_order_path),
        "--out",
        str(out_path),
        "--scillm-base-url",
        scillm_base_url,
        "--caller-skill",
        "battle",
        "--request-timeout-s",
        str(request_timeout_s),
        "--apply",
    ]
    return _run_tau_command(command=command, cwd=tau_root, expected_json=out_path)


def _run_tau_scillm_validate(
    *,
    tau_root: Path,
    work_order_path: Path,
    result_path: Path,
    out_path: Path,
    launch_receipt_path: Path,
) -> dict[str, Any] | None:
    command = [
        "uv",
        "run",
        "tau",
        "scillm-worker-validate",
        "--work-order",
        str(work_order_path),
        "--result",
        str(result_path),
        "--out",
        str(out_path),
        "--launch-receipt",
        str(launch_receipt_path),
    ]
    return _run_tau_command(command=command, cwd=tau_root, expected_json=out_path)


def _run_tau_command(
    *, command: list[str], cwd: Path, expected_json: Path
) -> dict[str, Any] | None:
    expected_json.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        command, cwd=cwd, text=True, capture_output=True, timeout=900, check=False
    )
    (expected_json.parent / f"{expected_json.stem}.stdout.txt").write_text(
        completed.stdout, encoding="utf-8"
    )
    (expected_json.parent / f"{expected_json.stem}.stderr.txt").write_text(
        completed.stderr, encoding="utf-8"
    )
    if expected_json.exists():
        return _read_json(expected_json)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict):
        _write_json(expected_json, payload)
        return payload
    return None


def _battle_work_order(
    *,
    battle_id: str,
    dag_id: str | None,
    child_lane_id: str,
    goal_hash: str | None,
    input_paths: dict[str, Path],
    output_root: Path,
) -> dict[str, Any]:
    return {
        "schema": BATTLE_WORK_ORDER_SCHEMA,
        "battle_id": battle_id,
        "dag_id": dag_id,
        "node_id": "exploit-code-author",
        "child_lane_id": child_lane_id,
        "goal_hash": goal_hash,
        "inputs": {key: str(path) for key, path in input_paths.items()},
        "required_outputs": [
            "outputs/exploit_specimen.py",
            "outputs/provider-worker-result.json",
        ],
        "output_root": str(output_root),
        "constraints": [
            "Do not claim exploit success.",
            "Do not reference private Arena artifacts.",
            "Generated code may be incorrect.",
            "Materialize code as an artifact; do not return code only in prose.",
            "Do not execute, compile, import, or run the exploit from the provider node.",
        ],
        "claims": {
            "proves": ["Battle wrote a semantic code-author work order."],
            "does_not_prove": [
                "A provider executed the work order.",
                "Exploit code was generated.",
            ],
        },
    }


def _tau_work_order(
    *,
    battle_work_order: dict[str, Any],
    repo: Path,
    result_path: Path,
    receipt_path: Path,
) -> dict[str, Any]:
    model_provider_route: dict[str, Any] = {
        "surface": "opencode_serve",
        "endpoint": "/v1/scillm/opencode/runs",
        "agent": os.environ.get("BATTLE_PR3C_SCILLM_AGENT", "build"),
        "provider": os.environ.get("BATTLE_PR3C_PROVIDER", "scillm"),
        "skills": ["battle", "tau"],
    }
    if os.environ.get("BATTLE_PR3C_MODEL"):
        model_provider_route["model"] = os.environ["BATTLE_PR3C_MODEL"]

    return {
        "schema": TAU_SCILLM_WORK_ORDER_SCHEMA,
        "dag_id": battle_work_order.get("dag_id"),
        "node_id": "exploit-code-author",
        "agent": "battle-exploit-code-author",
        "attempt": 1,
        "goal_hash": battle_work_order.get("goal_hash"),
        "repo": str(repo),
        "allowed_paths": ["outputs/**"],
        "forbidden_paths": [
            "inputs/**",
            "receipts/**",
            "logs/**",
            "arena/private/**",
            "judge/oracle/**",
            "**/hidden-ground-truth.json",
            "**/hidden-vulnerability-ledger.json",
        ],
        "required_artifacts": ["outputs/exploit_specimen.py"],
        "result_path": result_path.as_posix(),
        "receipt_path": receipt_path.as_posix(),
        "execution_substrate": "local-low-risk",
        "high_stakes": False,
        "zero_trust": False,
        "model_provider_route": model_provider_route,
        "task": _worker_task_text(battle_work_order),
        "timeout_s": 600,
    }


def _worker_task_text(work_order: dict[str, Any]) -> str:
    return "\n".join(
        [
            "Generate one Python exploit-shaped specimen candidate for the Battle child DAG.",
            "Use only the input JSON files referenced in the Battle work order.",
            "Write the source artifact to outputs/exploit_specimen.py.",
            "Write a tau.scillm_worker_result.v1 JSON artifact to outputs/provider-worker-result.json.",
            "Set provider-worker-result.json status to exactly PASS when required artifacts were written, BLOCKED when execution cannot continue, or NEEDS_REVIEW when human review is required; do not use completed or success.",
            "The worker result must include schema, status, goal_hash, changed_files, artifacts, tests_run, findings, and next_recommended_route.",
            "The worker result must list outputs/exploit_specimen.py in artifacts.",
            "Do not compile, import, run, Docker-execute, or judge the code.",
            "Do not claim exploit success, target contact, Blue bypass, Blue detection, or Judge verification.",
            "Battle work order:",
            json.dumps(work_order, sort_keys=True),
        ]
    )


def _provider_workspace_for(artifact_dir: Path) -> Path:
    configured = os.environ.get("BATTLE_PR3C_PROVIDER_WORKSPACE_ROOT")
    if configured:
        root = Path(configured).expanduser()
    elif _is_writable_dir(DEFAULT_PROVIDER_WORKSPACE_ROOT.parent):
        root = DEFAULT_PROVIDER_WORKSPACE_ROOT
    else:
        root = artifact_dir

    root = root.resolve()
    digest = hashlib.sha256(str(artifact_dir).encode("utf-8")).hexdigest()[:16]
    slug = (
        re.sub(r"[^A-Za-z0-9_.-]+", "-", artifact_dir.name).strip("-") or "artifact-dir"
    )
    return root / f"{slug}-{digest}" / "exploit-code-author"


def _is_writable_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".battle-pr3c-write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def _workspace_baseline(
    *, workspace: Path, inputs: Path, outputs: Path
) -> dict[str, Any]:
    return {
        "schema": WORKSPACE_BASELINE_SCHEMA,
        "workspace": str(workspace),
        "input_tree_sha256": _tree_sha256(inputs),
        "output_files_present": [
            path.relative_to(outputs).as_posix()
            for path in sorted(outputs.rglob("*"))
            if path.is_file()
        ],
        "expected_outputs": [
            "outputs/exploit_specimen.py",
            "outputs/provider-worker-result.json",
        ],
        "created_at": _utc_stamp(),
    }


def _specimen_metadata(
    *,
    battle_id: str,
    child_lane_id: str,
    genome: dict[str, Any],
    code_path: Path,
    authorship_path: Path,
) -> dict[str, Any]:
    data = code_path.read_bytes()
    return {
        "schema": SPECIMEN_SCHEMA,
        "specimen_id": f"{child_lane_id or 'child'}-provider-specimen-0001",
        "battle_id": battle_id,
        "child_lane_id": child_lane_id,
        "generation": 1,
        "selected_method_ids": genome.get("selected_method_ids", []),
        "inherited_method_ids": genome.get("inherited_method_ids", []),
        "language": "python",
        "generated_code_path": str(code_path),
        "code_sha256": f"sha256:{hashlib.sha256(data).hexdigest()}",
        "provider_authorship_receipt": str(authorship_path),
        "created_by": "tau_provider",
        "agentic": True,
        "provider_live": True,
        "compile_status": "NOT_RUN",
        "runtime_status": "NOT_RUN",
        "judge_status": "NOT_RUN",
        "claims": {
            "proves": [
                "A provider-authored child exploit specimen artifact was materialized and bound to a provider-authorship receipt."
            ],
            "does_not_prove": [
                "The code compiles.",
                "The code runs.",
                "The code exploits the target.",
            ],
        },
    }


def _blocked_verdict(authorship: dict[str, Any]) -> str:
    errors = [str(item) for item in authorship.get("errors", [])]
    for preferred in (
        "PROVIDER_EXECUTION_ATTESTATION_MISSING",
        "PROVIDER_OUTPUT_MISSING",
        "PROVIDER_RESULT_OMITS_CODE_ARTIFACT",
    ):
        if preferred in errors:
            return preferred
    return errors[0] if errors else "PROVIDER_CODE_AUTHOR_BLOCKED"


def _copy_input(path: Path, inputs: Path) -> Path:
    target = inputs / path.name
    shutil.copy2(path, target)
    return target


def _tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return f"sha256:{digest.hexdigest()}"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _utc_stamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
