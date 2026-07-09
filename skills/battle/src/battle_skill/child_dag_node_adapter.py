"""Battle child exploit DAG node adapter invoked by Tau command specs."""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


NODE_RECEIPT_SCHEMA = "battle.child_dag_node_receipt.v1"

NEXT_NODE = {
    "lineage-summarizer": "research-scout",
    "research-scout": "method-combiner",
    "method-combiner": "exploit-code-author",
    "exploit-code-author": "compile-repair",
    "compile-repair": "artifact-reviewer",
    "artifact-reviewer": "battle-handoff-writer",
    "battle-handoff-writer": "human",
}


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: python -m battle_skill.child_dag_node_adapter <node-id>", file=sys.stderr)
        return 2
    node_id = args[0]
    try:
        start_payload = _read_stdin_handoff()
        artifact_dir = _artifact_dir()
        response, exit_code = run_node(node_id=node_id, start_payload=start_payload, artifact_dir=artifact_dir)
        if response is not None:
            print(json.dumps(response, sort_keys=True))
        return exit_code
    except Exception as exc:  # pragma: no cover - fail-closed command boundary.
        print(f"battle child DAG node adapter failed: {exc}", file=sys.stderr)
        return 1


def run_node(*, node_id: str, start_payload: dict[str, Any], artifact_dir: Path) -> tuple[dict[str, Any] | None, int]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    selected = os.environ.get("TAU_HANDOFF_SELECTED_AGENT") or node_id
    if selected != node_id:
        receipt = _node_receipt(node_id=node_id, status="BLOCKED", verdict="SELECTED_AGENT_MISMATCH", evidence=[])
        receipt["errors"] = [f"selected agent {selected!r} did not match adapter node {node_id!r}"]
        _write_json(artifact_dir / f"{node_id}-node-receipt.json", receipt)
        return None, 1

    if node_id == "lineage-summarizer":
        return _run_lineage_summarizer(start_payload=start_payload, artifact_dir=artifact_dir), 0

    return _blocked_missing_adapter(node_id=node_id, start_payload=start_payload, artifact_dir=artifact_dir), 1


def _run_lineage_summarizer(*, start_payload: dict[str, Any], artifact_dir: Path) -> dict[str, Any]:
    dag_path = _dag_contract_path(start_payload)
    spawn_root = dag_path.parent if dag_path is not None else None
    child_packet_path = spawn_root / "child-knowledge-packet.json" if spawn_root is not None else None
    spawn_policy_path = spawn_root / "spawn-policy-decision.json" if spawn_root is not None else None
    child_packet = _read_json(child_packet_path) if child_packet_path is not None and child_packet_path.exists() else {}
    spawn_policy = _read_json(spawn_policy_path) if spawn_policy_path is not None and spawn_policy_path.exists() else {}

    lineage_summary = {
        "schema": "battle.child_lineage_summary.v1",
        "status": "PASS",
        "mocked": False,
        "live": "tau_command_spec_node",
        "agentic": False,
        "battle_id": child_packet.get("battle_id") or _target_value(start_payload, "battle_id"),
        "parent_lane_id": child_packet.get("parent_lane_id"),
        "child_lane_id": child_packet.get("child_lane_id"),
        "parent_specimen_count": len(child_packet.get("parent_specimens", [])) if isinstance(child_packet.get("parent_specimens"), list) else 0,
        "inherited_methods": child_packet.get("inherited_methods", []),
        "hypotheses": child_packet.get("hypotheses", []),
        "blocked_ideas": child_packet.get("blocked_ideas", []),
        "next_research_questions": child_packet.get("next_research_questions", []),
        "spawn_policy_decision": spawn_policy.get("decision"),
        "claims": {
            "proves": ["Battle child DAG lineage-summarizer read the parent-approved child knowledge packet."],
            "does_not_prove": ["Tau researched new sources.", "Tau generated exploit code.", "Exploit success."],
        },
    }
    lineage_path = artifact_dir / "lineage_summary.json"
    _write_json(lineage_path, lineage_summary)

    evidence = [_evidence("lineage_summary.json", lineage_path)]
    if child_packet_path is not None and child_packet_path.exists():
        evidence.append(_evidence("child_knowledge_packet.json", child_packet_path))
    receipt = _node_receipt(node_id="lineage-summarizer", status="PASS", verdict="PASS", evidence=evidence)
    receipt["source_artifacts"] = {
        "dag_contract": str(dag_path) if dag_path is not None else None,
        "child_knowledge_packet": str(child_packet_path) if child_packet_path is not None else None,
        "spawn_policy_decision": str(spawn_policy_path) if spawn_policy_path is not None else None,
    }
    receipt_path = artifact_dir / "lineage-summarizer-node-receipt.json"
    _write_json(receipt_path, receipt)
    evidence.append(_evidence("lineage-summarizer-node-receipt.json", receipt_path))
    return _handoff(
        start_payload=start_payload,
        previous_subagent="lineage-summarizer",
        status="PASS",
        summary="Lineage summary created from parent-approved child knowledge packet.",
        evidence=evidence,
        next_agent="research-scout",
        artifacts=[str(lineage_path), str(receipt_path)],
    )


def _blocked_missing_adapter(*, node_id: str, start_payload: dict[str, Any], artifact_dir: Path) -> None:
    verdict = _blocked_verdict(node_id)
    receipt = _node_receipt(node_id=node_id, status="BLOCKED", verdict=verdict, evidence=[])
    receipt["reason"] = _blocked_reason(node_id)
    receipt["claims"] = {
        "proves": [f"Battle reached the {node_id} command-spec boundary."],
        "does_not_prove": ["A real adapter produced this node's required artifacts.", "Exploit success."],
    }
    _write_json(artifact_dir / f"{node_id}-node-receipt.json", receipt)
    return None


def _blocked_verdict(node_id: str) -> str:
    if node_id == "research-scout":
        return "RESEARCH_ADAPTER_MISSING"
    if node_id == "exploit-code-author":
        return "PROVIDER_OR_TAU_CODE_AUTHOR_ADAPTER_MISSING"
    if node_id == "compile-repair":
        return "UPSTREAM_CODE_ARTIFACT_MISSING"
    return "UPSTREAM_ARTIFACT_MISSING"


def _blocked_reason(node_id: str) -> str:
    if node_id == "research-scout":
        return "No real source-bearing research adapter is configured for PR3a; fixture research fallback is forbidden."
    if node_id == "exploit-code-author":
        return "No real Tau/provider code-authoring adapter is configured; fixture child code fallback is forbidden."
    return "Required upstream artifacts are missing; this PR3a adapter does not synthesize fixture outputs."


def _handoff(
    *,
    start_payload: dict[str, Any],
    previous_subagent: str,
    status: str,
    summary: str,
    evidence: list[dict[str, Any]],
    next_agent: str,
    artifacts: list[str],
) -> dict[str, Any]:
    return {
        "schema": "tau.agent_handoff.v1",
        "github": start_payload.get("github") if isinstance(start_payload.get("github"), dict) else {"repo": "grahama1970/agent-skills", "target": "skills/battle"},
        "goal": start_payload.get("goal") if isinstance(start_payload.get("goal"), dict) else {},
        "previous_subagent": previous_subagent,
        "context": {
            "summary": summary,
            "artifacts": artifacts,
        },
        "result": {
            "status": status,
            "summary": summary,
            "evidence": evidence,
        },
        "rationale": "The Tau DAG contract controls the next Battle child exploit node.",
        "next_agent": {
            "name": next_agent,
            "executor": "human" if next_agent == "human" else "local",
            "reason": "Continue along the Battle child exploit DAG route.",
        },
        "required_evidence": start_payload.get("required_evidence") if isinstance(start_payload.get("required_evidence"), list) else [],
        "stop_condition": "Stop at human or any fail-closed Battle/Tau invariant.",
    }


def _node_receipt(*, node_id: str, status: str, verdict: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": NODE_RECEIPT_SCHEMA,
        "node_id": node_id,
        "status": status,
        "verdict": verdict,
        "mocked": False,
        "live": "tau_command_spec_node",
        "agentic": node_id not in {"lineage-summarizer", "artifact-reviewer", "battle-handoff-writer"},
        "fixture_fallback_used": False,
        "evidence": evidence,
        "created_at": _utc_stamp(),
    }


def _dag_contract_path(start_payload: dict[str, Any]) -> Path | None:
    for item in _context_artifacts(start_payload):
        path = Path(item)
        if path.name == "child-exploit-dag.yaml" and path.exists():
            return path.resolve()
    for item in _result_evidence(start_payload):
        if isinstance(item, dict) and item.get("kind") == "dag_contract":
            path_value = item.get("path")
            if isinstance(path_value, str):
                path = Path(path_value)
                if path.exists():
                    return path.resolve()
    return None


def _context_artifacts(payload: dict[str, Any]) -> list[str]:
    context = payload.get("context")
    if not isinstance(context, dict):
        return []
    artifacts = context.get("artifacts")
    return [item for item in artifacts if isinstance(item, str)] if isinstance(artifacts, list) else []


def _result_evidence(payload: dict[str, Any]) -> list[Any]:
    result = payload.get("result")
    if not isinstance(result, dict):
        return []
    evidence = result.get("evidence")
    return evidence if isinstance(evidence, list) else []


def _target_value(payload: dict[str, Any], key: str) -> Any:
    context = payload.get("context")
    tau_node = context.get("tau_dag_node") if isinstance(context, dict) else None
    target = tau_node.get("target") if isinstance(tau_node, dict) else None
    return target.get(key) if isinstance(target, dict) else None


def _evidence(kind: str, path: Path) -> dict[str, Any]:
    return {"kind": kind, "path": str(path)}


def _read_stdin_handoff() -> dict[str, Any]:
    payload = json.loads(sys.stdin.read())
    if not isinstance(payload, dict):
        raise RuntimeError("stdin handoff root must be a JSON object")
    return payload


def _artifact_dir() -> Path:
    value = os.environ.get("TAU_HANDOFF_COMMAND_ARTIFACT_DIR")
    if not value:
        raise RuntimeError("TAU_HANDOFF_COMMAND_ARTIFACT_DIR is required")
    return Path(value).expanduser().resolve()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _utc_stamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":  # pragma: no cover - command entrypoint.
    raise SystemExit(main())
