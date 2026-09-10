#!/usr/bin/env python3
"""Validate explain-project deployment templates without deploying anything."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parents[1]
REQUIRED_ENV = {
    "AGENT_SKILLS_ROOT",
    "EXPLAIN_PROJECT_API_PORT",
    "EXPLAIN_PROJECT_UI_PORT",
    "EXPLAIN_PROJECT_EXPLAINERS",
    "MEMORY_URL",
    "CHATTERBOX_URL",
    "REALTIMESTT_URL",
}
REQUIRED_FILES = [
    "deploy/docker-compose.yml",
    "deploy/.env.example",
    "deploy/schema-catalog.json",
    "deploy/memory-graph-export.example.json",
    "infra/terraform/versions.tf",
    "infra/terraform/variables.tf",
    "infra/terraform/main.tf",
    "infra/terraform/outputs.tf",
]


def _env_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped.removeprefix("export ").strip()
        if "=" in stripped:
            keys.add(stripped.split("=", 1)[0].strip())
    return keys


def _json_from_stdout(stdout: str) -> dict[str, Any]:
    start = stdout.find("{")
    if start < 0:
        return {}
    try:
        return json.loads(stdout[start:])
    except json.JSONDecodeError:
        return {}


def _terraform_check(module_dir: Path) -> dict[str, Any]:
    ops = SKILL_DIR.parent / "ops-terraform" / "run.sh"
    if not ops.is_file():
        return {
            "status": "NOT_CONFIGURED",
            "reason": "ops-terraform skill not present",
            "next_command": f"terraform -chdir={module_dir} init -backend=false && terraform -chdir={module_dir} validate",
        }

    proc = subprocess.run(
        [str(ops), "check", str(module_dir)],
        cwd=str(SKILL_DIR),
        capture_output=True,
        text=True,
        timeout=180,
    )
    payload = _json_from_stdout(proc.stdout)
    status = payload.get("status")
    if status == "PASS":
        return {
            "status": "PASS",
            "command": f"{ops} check {module_dir}",
            "summary": payload,
        }
    if status == "NOT_CONFIGURED" or payload.get("failure_code") == "terraform_binary_missing":
        return {
            "status": "NOT_CONFIGURED",
            "command": f"{ops} check {module_dir}",
            "next_command": f"terraform -chdir={module_dir} init -backend=false && terraform -chdir={module_dir} validate",
            "summary": payload,
        }
    return {
        "status": "FAIL",
        "command": f"{ops} check {module_dir}",
        "returncode": proc.returncode,
        "summary": payload,
        "stderr_tail": proc.stderr[-500:],
    }


def main() -> int:
    files = {rel: (SKILL_DIR / rel).is_file() for rel in REQUIRED_FILES}
    missing_files = [rel for rel, present in files.items() if not present]

    catalog_path = SKILL_DIR / "deploy/schema-catalog.json"
    try:
        schema_catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        schema_catalog = {"error": str(exc)}

    graph_path = SKILL_DIR / "deploy/memory-graph-export.example.json"
    try:
        graph_export = json.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        graph_export = {"error": str(exc)}

    env_path = SKILL_DIR / "deploy/.env.example"
    env_keys = _env_keys(env_path) if env_path.is_file() else set()
    missing_env = sorted(REQUIRED_ENV - env_keys)

    compose_path = SKILL_DIR / "deploy/docker-compose.yml"
    compose_text = compose_path.read_text(encoding="utf-8") if compose_path.is_file() else ""
    compose_markers = {
        "api_service": "explain-project-api:" in compose_text,
        "ui_service": "explain-project-ui:" in compose_text,
        "memory_url": "MEMORY_URL" in compose_text,
        "chatterbox_url": "CHATTERBOX_URL" in compose_text,
        "realtimestt_url": "REALTIMESTT_URL" in compose_text,
        "no_private_home_path": "/home/graham" not in compose_text,
    }

    terraform = _terraform_check(SKILL_DIR / "infra/terraform")
    schema_contracts = {item.get("schema") for item in schema_catalog.get("record_contracts", [])}
    graph_contract = schema_catalog.get("graph_export_contract", {})
    required_node_types = {"Project", "Explainer", "Question", "Diagram", "SourceSymbol", "DebuggerStop", "Schema"}
    required_edge_types = {"ANSWERS", "USES_DIAGRAM", "CITES_SOURCE", "HAS_BREAKPOINT", "RELATED_TO", "SAME_DIAGRAM_AS", "IMPLEMENTS_SCHEMA"}
    graph_node_types = {node.get("type") for node in graph_export.get("nodes", [])}
    graph_edge_types = {edge.get("type") for edge in graph_export.get("edges", [])}
    graph_node_ids = {node.get("id") for node in graph_export.get("nodes", [])}
    graph_edges_resolve = all(
        edge.get("from") in graph_node_ids and edge.get("to") in graph_node_ids
        for edge in graph_export.get("edges", [])
    )
    diagram_nodes = [node for node in graph_export.get("nodes", []) if node.get("type") == "Diagram"]
    graph_required_fields_ok = (
        any("estimated_read_seconds" in node for node in graph_export.get("nodes", []))
        and any("estimated_speak_seconds" in node for node in graph_export.get("nodes", []))
        and all(
            {"diagram_id", "source_path", "rendered_svg_path"} <= set(node)
            for node in diagram_nodes
        )
    )
    graph_export_ok = (
        graph_export.get("schema") == "explain_project.memory_graph_export.v1"
        and graph_export.get("memory_collection")
        and graph_node_types >= required_node_types
        and graph_edge_types >= required_edge_types
        and graph_edges_resolve
        and graph_required_fields_ok
    )
    feature_contract = next(
        (item for item in schema_catalog.get("record_contracts", []) if item.get("schema") == "project.feature_explainer.v1"),
        {},
    )
    voice_contract = next(
        (item for item in schema_catalog.get("record_contracts", []) if item.get("schema") == "explain_project.voice_driver_intent.v1"),
        {},
    )
    read_time_ok = (
        feature_contract.get("read_time", {}).get("wpm_default") == 150
        and "estimated_read_seconds" in feature_contract.get("required_surfaces", [])
        and "steps[].estimated_speak_seconds" in feature_contract.get("required_surfaces", [])
        and graph_export.get("read_time", {}).get("wpm_default") == 150
        and graph_required_fields_ok
    )
    interrupt_boundary_ok = (
        graph_export.get("interrupt_boundary", {}).get("transcript_is_speaker_identity") is False
        and graph_export.get("interrupt_boundary", {}).get("health_is_readiness") is False
        and schema_catalog.get("interrupt_boundary", {}).get("transcript_is_speaker_identity") is False
        and schema_catalog.get("interrupt_boundary", {}).get("health_is_readiness") is False
    )
    voice_driver_ok = (
        voice_contract.get("status") in {"catalog_only_optional_boundary", "disabled_by_default_optional_boundary"}
        and set(voice_contract.get("actions", [])) >= {"current-step", "next", "previous", "ask-question", "speak-step"}
        and schema_catalog.get("voice_driver_boundary", {}).get("disabled_by_default") is True
        and schema_catalog.get("voice_driver_boundary", {}).get("revision_fenced") is True
        and graph_export.get("voice_driver_boundary", {}).get("revision_fenced") is True
        and "interrupt" not in set(schema_catalog.get("voice_driver_boundary", {}).get("allowed_actions", []))
        and "interrupt" not in set(graph_export.get("voice_driver_boundary", {}).get("allowed_actions", []))
    )
    schema_catalog_ok = (
        schema_catalog.get("schema") == "explain_project.schema_catalog.v1"
        and schema_catalog.get("memory_collection") in {"skill_schemas", "explain_project_schemas"}
        and "project.feature_explainer.v1" in schema_contracts
        and "explain_project.route_decision.v1" in schema_contracts
        and "explain_project.voice_driver_intent.v1" in schema_contracts
        and schema_catalog.get("question_reuse_command")
        and schema_catalog.get("source_of_truth")
        and schema_catalog.get("prior_answer_routing")
        and graph_contract.get("schema") == "explain_project.memory_graph_export.v1"
        and set(graph_contract.get("node_types", [])) >= required_node_types
        and set(graph_contract.get("edge_types", [])) >= required_edge_types
        and set(schema_catalog.get("graph_recall_fields", [])) >= {"diagram_id", "source_path", "rendered_svg_path"}
        and interrupt_boundary_ok
        and schema_catalog.get("emotion_intent_boundary", {}).get("owner") == "chatterbox-speak"
        and read_time_ok
        and voice_driver_ok
    )
    failures = []
    if missing_files:
        failures.append({"missing_files": missing_files})
    if missing_env:
        failures.append({"missing_env": missing_env})
    bad_markers = [name for name, ok in compose_markers.items() if not ok]
    if bad_markers:
        failures.append({"compose_markers": bad_markers})
    if not schema_catalog_ok:
        failures.append({"schema_catalog": schema_catalog})
    if not graph_export_ok:
        failures.append({"memory_graph_export": graph_export})
    if terraform["status"] == "FAIL":
        failures.append({"terraform": terraform})

    payload = {
        "schema": "explain_project.deploy_validation.v1",
        "status": "PASS" if not failures else "FAIL",
        "files": files,
        "env": {
            "required": sorted(REQUIRED_ENV),
            "present": sorted(env_keys),
            "missing": missing_env,
        },
        "compose": compose_markers,
        "terraform": terraform,
        "memory_publish": {
            "artifact": "deploy/schema-catalog.json",
            "memory_collection": schema_catalog.get("memory_collection"),
            "alternate_memory_collection": schema_catalog.get("alternate_memory_collection"),
            "graph_export_artifact": "deploy/memory-graph-export.example.json",
            "graph_memory_collection": graph_export.get("memory_collection"),
            "write_boundary": schema_catalog.get("memory_write_boundary"),
        },
        "schema_catalog": {
            "status": "PASS" if schema_catalog_ok else "FAIL",
            "schemas": sorted(schema_contracts),
            "question_reuse_command": schema_catalog.get("question_reuse_command"),
            "graph_export_contract": graph_contract,
            "read_time": feature_contract.get("read_time"),
            "voice_driver_boundary": schema_catalog.get("voice_driver_boundary"),
        },
        "memory_graph_export": {
            "status": "PASS" if graph_export_ok else "FAIL",
            "node_types": sorted(t for t in graph_node_types if t),
            "edge_types": sorted(t for t in graph_edge_types if t),
            "edges_resolve": graph_edges_resolve,
            "read_time_ok": read_time_ok,
            "voice_driver_ok": voice_driver_ok,
            "interrupt_boundary_ok": interrupt_boundary_ok,
            "required_fields_ok": graph_required_fields_ok,
        },
        "proof_boundary": "Template/config validation only. No docker compose up, live Memory, Chatterbox, RealtimeSTT, Terraform plan, Terraform apply, or Memory write was run.",
        "failures": failures,
    }
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
