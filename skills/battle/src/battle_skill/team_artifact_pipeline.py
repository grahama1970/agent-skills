"""Deterministic Red/Blue artifact compile, review, and handoff pipeline."""

from __future__ import annotations

import ast
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


def review_artifact_errors(team: str, text: str) -> list[str]:
    """Deterministic review scan for one artifact's source text.

    Shared gate logic: the same private-marker + role-interface checks the live
    pipeline applies to a champion are reused by the mutation-load specimen gate so
    both measure viability with an identical rule set (no divergent copy).
    """
    lowered = text.lower()
    errors: list[str] = [
        f"private marker present: {marker}"
        for marker in PRIVATE_MARKERS
        if marker in lowered
    ]
    if team == "red" and not _red_binds_public_app_import_zip(text):
        errors.append("red artifact does not bind the public app import interface")
    if team == "blue" and "def import_zip" not in lowered:
        errors.append("blue artifact does not preserve import_zip interface")
    return errors


def _red_binds_public_app_import_zip(text: str) -> bool:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    direct_names, module_names = _local_app_import_zip_bindings(tree)
    return (
        bool(direct_names)
        or any(
            _is_local_import_zip_lookup(node, module_names) for node in ast.walk(tree)
        )
        or bool(_local_import_zip_factory_names(tree, module_names))
    )


def _local_app_import_zip_bindings(tree: ast.AST) -> tuple[set[str], set[str]]:
    direct_names: set[str] = set()
    module_names: set[str] = set()
    importlib_names = {"importlib"}
    import_module_names: set[str] = set()
    importlib_util_names = {"importlib.util"}
    spec_from_file_location_names: set[str] = set()
    module_from_spec_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "app":
                direct_names.update(
                    alias.asname or alias.name
                    for alias in node.names
                    if alias.name == "import_zip"
                )
            elif node.module == "importlib":
                for alias in node.names:
                    if alias.name == "import_module":
                        import_module_names.add(alias.asname or alias.name)
                    elif alias.name == "util":
                        importlib_util_names.add(alias.asname or alias.name)
            elif node.module == "importlib.util":
                for alias in node.names:
                    if alias.name == "spec_from_file_location":
                        spec_from_file_location_names.add(alias.asname or alias.name)
                    elif alias.name == "module_from_spec":
                        module_from_spec_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                bound_name = alias.asname or alias.name.split(".", 1)[0]
                if alias.name == "app":
                    module_names.add(bound_name)
                elif alias.name == "importlib":
                    importlib_names.add(bound_name)
                elif alias.name == "importlib.util":
                    importlib_util_names.add(alias.asname or alias.name)

    assignments = _name_assignments(tree)
    spec_names = {
        name
        for name, value in assignments.items()
        if isinstance(value, ast.Call)
        and _is_importlib_util_call(
            value.func,
            importlib_util_names=importlib_util_names,
            direct_names=spec_from_file_location_names,
            attr_name="spec_from_file_location",
        )
        and len(value.args) >= 2
        and _is_local_app_path(value.args[1], assignments, set())
    }

    for name, value in assignments.items():
        if isinstance(value, ast.Call) and (
            _is_importlib_import_module_call(
                value,
                importlib_names=importlib_names,
                direct_names=import_module_names,
            )
            or (
                _is_importlib_util_call(
                    value.func,
                    importlib_util_names=importlib_util_names,
                    direct_names=module_from_spec_names,
                    attr_name="module_from_spec",
                )
                and value.args
                and isinstance(value.args[0], ast.Name)
                and value.args[0].id in spec_names
            )
        ):
            module_names.add(name)

    spec_module_names = {
        name
        for name, value in assignments.items()
        if isinstance(value, ast.Call)
        and _is_importlib_util_call(
            value.func,
            importlib_util_names=importlib_util_names,
            direct_names=module_from_spec_names,
            attr_name="module_from_spec",
        )
    }
    loaded_module_names = {
        name
        for name in module_names
        if name not in spec_module_names
        or _executes_local_module(tree, name, spec_names)
    }
    return direct_names, loaded_module_names


def _name_assignments(tree: ast.AST) -> dict[str, ast.AST]:
    assignments: dict[str, ast.AST] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assignments[target.id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            assignments[node.target.id] = node.value
    return assignments


def _local_import_zip_factory_names(tree: ast.AST, module_names: set[str]) -> set[str]:
    factory_names: set[str] = set()
    for function in (
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    ):
        local_callables: set[str] = set()
        for node in ast.walk(function):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and _is_local_import_zip_lookup(
                        node.value, module_names
                    ):
                        local_callables.add(target.id)
            elif (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and _is_local_import_zip_lookup(node.value, module_names)
            ):
                local_callables.add(node.target.id)
            elif isinstance(node, ast.Return):
                if _is_local_import_zip_lookup(node.value, module_names):
                    factory_names.add(function.name)
                elif (
                    isinstance(node.value, ast.Name)
                    and node.value.id in local_callables
                ):
                    factory_names.add(function.name)
    return factory_names


def _executes_local_module(
    tree: ast.AST, module_name: str, spec_names: set[str]
) -> bool:
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "exec_module"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "loader"
        and isinstance(node.func.value.value, ast.Name)
        and node.func.value.value.id in spec_names
        and node.args
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == module_name
        for node in ast.walk(tree)
    )


def _is_local_import_zip_lookup(node: ast.AST, module_names: set[str]) -> bool:
    if isinstance(node, ast.Attribute):
        return (
            node.attr == "import_zip"
            and isinstance(node.value, ast.Name)
            and node.value.id in module_names
        )
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and len(node.args) >= 2
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id in module_names
        and isinstance(node.args[1], ast.Constant)
        and node.args[1].value == "import_zip"
    )


def _is_importlib_import_module_call(
    node: ast.Call, *, importlib_names: set[str], direct_names: set[str]
) -> bool:
    if not node.args or not (
        isinstance(node.args[0], ast.Constant) and node.args[0].value == "app"
    ):
        return False
    dotted = _dotted_name(node.func)
    if dotted in direct_names:
        return True
    return any(dotted == f"{name}.import_module" for name in importlib_names)


def _is_importlib_util_call(
    node: ast.AST,
    *,
    importlib_util_names: set[str],
    direct_names: set[str],
    attr_name: str,
) -> bool:
    dotted = _dotted_name(node)
    if dotted in direct_names:
        return True
    return any(dotted == f"{name}.{attr_name}" for name in importlib_util_names)


def _is_local_app_path(
    node: ast.AST, assignments: dict[str, ast.AST], seen: set[str]
) -> bool:
    if isinstance(node, ast.Name) and node.id not in seen and node.id in assignments:
        return _is_local_app_path(assignments[node.id], assignments, seen | {node.id})
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "str"
        and len(node.args) == 1
    ):
        return _is_local_app_path(node.args[0], assignments, seen)
    return (
        isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.Div)
        and isinstance(node.right, ast.Constant)
        and node.right.value == "app.py"
        and isinstance(node.left, ast.Call)
        and _dotted_name(node.left.func) == "Path.cwd"
        and not node.left.args
    )


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else None
    return None


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
    provider_payload = _read_json(provider_receipt)
    materialization_payload = _read_json(materialization_receipt)
    declared_path = Path(str(materialization_payload.get("path") or "")).resolve()
    source_sha = _sha(source_artifact)
    expected_role = "red_exploit" if team == "red" else "blue_patch"
    input_errors: list[str] = []
    provider_result = provider_payload.get("result")
    provider_status = (
        provider_result.get("status")
        if isinstance(provider_result, dict)
        else provider_payload.get("status")
    )
    if provider_status != "PASS":
        input_errors.append("Tau provider/subagent receipt status is not PASS")
    if materialization_payload.get("status") != "PASS":
        input_errors.append("Tau materialization receipt status is not PASS")
    if materialization_payload.get("artifact_type") != expected_role:
        input_errors.append(
            "Tau materialization artifact_type does not match team role"
        )
    if declared_path != source_artifact:
        input_errors.append("Tau materialization path does not match source artifact")
    if materialization_payload.get("artifact_sha256") != source_sha:
        input_errors.append(
            "Tau materialization artifact hash does not match source artifact"
        )
    if materialization_payload.get("artifact_bytes") != source_artifact.stat().st_size:
        input_errors.append(
            "Tau materialization byte count does not match source artifact"
        )
    if not materialization_payload.get("scillm_call_receipt_sha256"):
        input_errors.append("Tau materialization receipt lacks SciLLM call binding")
    if input_errors:
        raise ValueError("; ".join(input_errors))
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
        "source_artifact_sha256": source_sha,
        "tau_declared_artifact_sha256": materialization_payload["artifact_sha256"],
        "tau_declared_artifact_bytes": materialization_payload["artifact_bytes"],
        "tau_strategy_genome_sha256": materialization_payload.get(
            "strategy_genome_sha256"
        ),
        "tau_scillm_call_receipt_sha256": materialization_payload[
            "scillm_call_receipt_sha256"
        ],
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
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "64",
        "--memory",
        "256m",
        "--cpus",
        "1",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=16m",
        "-e",
        "PYTHONPYCACHEPREFIX=/tmp/pycache",
        "--user",
        "65534:65534",
        "-v",
        f"{out_dir}:/work:ro",
        "-w",
        "/work",
        docker_image,
        "python",
        "-m",
        "py_compile",
        selected_name,
    ]
    completed = subprocess.run(
        command, capture_output=True, text=True, timeout=120, check=False
    )
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
    text = selected_path.read_text(encoding="utf-8", errors="replace")
    errors.extend(review_artifact_errors(team, text))
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
            "selected_hash_bound": selected_sha
            == compile_receipt["selected_artifact_sha256"],
            "private_reference_scan_passed": not any(
                "private marker" in item for item in errors
            ),
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
            "proves": [
                "Battle bound one provider materialization through Docker compile and deterministic review."
            ]
            if status == "PASS"
            else [],
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


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
