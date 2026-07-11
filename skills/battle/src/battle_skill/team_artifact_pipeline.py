"""Deterministic Red/Blue artifact compile, review, and handoff pipeline."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PRIVATE_MARKERS = (
    "arena/private/",
    "hidden-ground-truth.json",
    "hidden-vulnerability-ledger.json",
    "judge/oracle/",
)


def run_team_artifact_pipeline(
    *,
    battle_id: str,
    run_id: str,
    generation: int,
    team: str,
    source_artifact: Path,
    provider_receipt: Path,
    materialization_receipt: Path,
    target_identity_sha256: str,
    out_dir: Path,
    docker_image: str = "python:3.12-slim",
    genome_sha256: str | None = None,
) -> dict[str, Any]:
    """Compile and review one provider materialization without executing it."""

    if team not in {"red", "blue"}:
        raise ValueError("team must be red or blue")
    source_artifact = source_artifact.resolve()
    provider_receipt = provider_receipt.resolve()
    materialization_receipt = materialization_receipt.resolve()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    role = "red_exploit" if team == "red" else "blue_patch"
    selected_name = "red_exploit_submission.py" if team == "red" else "app.py"
    selected_path = out_dir / selected_name
    shutil.copyfile(source_artifact, selected_path)

    descriptor = {
        "schema": "battle.team_artifact_descriptor.v1",
        "status": "PASS",
        "battle_id": battle_id,
        "run_id": run_id,
        "generation": generation,
        "team": team,
        "artifact_role": role,
        "language": "python",
        "source_artifact_sha256": _sha(source_artifact),
        "provider_receipt_sha256": _sha(provider_receipt),
        "materialization_receipt_sha256": _sha(materialization_receipt),
        "target_identity_sha256": target_identity_sha256,
        "genome_sha256": genome_sha256,
        "created_at": _now(),
    }
    descriptor_path = _write_json(out_dir / "team-artifact-descriptor.json", descriptor)

    stdout_path = out_dir / "compile.stdout.txt"
    stderr_path = out_dir / "compile.stderr.txt"
    command = [
        "docker", "run", "--rm", "--network", "none", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--pids-limit", "64",
        "--memory", "256m", "--cpus", "1", "--read-only",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
        "-e", "PYTHONPYCACHEPREFIX=/tmp/pycache", "--user", "65534:65534",
        "-v", f"{out_dir}:/work:ro", "-w", "/work", docker_image,
        "python", "-m", "py_compile", selected_name,
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    compile_status = "PASS" if completed.returncode == 0 else "BLOCKED"
    selected_sha = _sha(selected_path)
    compile_receipt = {
        "schema": "battle.team_compile_receipt.v1",
        "status": compile_status,
        "team": team,
        "generation": generation,
        "mocked": False,
        "live": "docker_python_compile",
        "docker_image": docker_image,
        "docker_command": command,
        "docker_exit_code": completed.returncode,
        "source_artifact_sha256": descriptor["source_artifact_sha256"],
        "selected_artifact_sha256": selected_sha,
        "target_identity_sha256": target_identity_sha256,
        "stdout_sha256": _sha(stdout_path),
        "stderr_sha256": _sha(stderr_path),
        "created_at": _now(),
    }
    compile_path = _write_json(out_dir / "compile-receipt.json", compile_receipt)

    errors: list[str] = []
    if compile_status != "PASS":
        errors.append("docker compile did not pass")
    text = selected_path.read_text(encoding="utf-8", errors="replace").lower()
    errors.extend(f"private marker present: {marker}" for marker in PRIVATE_MARKERS if marker in text)
    if team == "red" and not ("from app import import_zip" in text or "import app" in text):
        errors.append("red artifact does not bind the public app import interface")
    if team == "blue" and "def import_zip" not in text:
        errors.append("blue artifact does not preserve import_zip interface")
    review_status = "PASS" if not errors else "BLOCKED"
    review = {
        "schema": "battle.team_artifact_review_receipt.v1",
        "status": review_status,
        "team": team,
        "generation": generation,
        "descriptor_sha256": _sha(descriptor_path),
        "compile_receipt_sha256": _sha(compile_path),
        "selected_artifact_sha256": selected_sha,
        "provider_receipt_sha256": descriptor["provider_receipt_sha256"],
        "target_identity_sha256": target_identity_sha256,
        "checks": {
            "docker_compile_passed": compile_status == "PASS",
            "selected_hash_bound": selected_sha == compile_receipt["selected_artifact_sha256"],
            "private_reference_scan_passed": not any("private marker" in item for item in errors),
            "role_interface_preserved": not any("interface" in item for item in errors),
        },
        "errors": errors,
        "created_at": _now(),
    }
    review_path = _write_json(out_dir / "artifact-review-receipt.json", review)
    status = "PASS" if review_status == "PASS" else "BLOCKED"
    handoff = {
        "schema": "battle.team_artifact_pipeline_receipt.v1",
        "status": status,
        "battle_id": battle_id,
        "run_id": run_id,
        "generation": generation,
        "team": team,
        "artifact_role": role,
        "selected_artifact": str(selected_path),
        "selected_artifact_sha256": selected_sha,
        "descriptor_sha256": _sha(descriptor_path),
        "compile_receipt_sha256": _sha(compile_path),
        "artifact_review_receipt_sha256": _sha(review_path),
        "provider_receipt_sha256": descriptor["provider_receipt_sha256"],
        "materialization_receipt_sha256": descriptor["materialization_receipt_sha256"],
        "target_identity_sha256": target_identity_sha256,
        "genome_sha256": genome_sha256,
        "allowed_runner": "battle_docker_judge",
        "claims": {
            "proves": ["Battle bound one provider materialization through Docker compile and deterministic review."] if status == "PASS" else [],
            "does_not_prove": ["The artifact runs.", "Judge verified an outcome."],
        },
        "created_at": _now(),
    }
    handoff_path = _write_json(out_dir / "team-artifact-pipeline-receipt.json", handoff)
    return {
        "status": status,
        "descriptor_path": descriptor_path,
        "compile_receipt_path": compile_path,
        "review_receipt_path": review_path,
        "handoff_path": handoff_path,
        "selected_artifact_path": selected_path,
        "selected_artifact_sha256": selected_sha,
    }


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
