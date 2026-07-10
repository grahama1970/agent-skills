"""Battle child exploit DAG node adapter invoked by Tau command specs."""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .child_dag_code_author import run_code_author
from .child_dag_method_combiner import run_method_combiner
from .child_dag_research import run_research_scout


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
    if node_id == "research-scout":
        response = _run_research_scout(start_payload=start_payload, artifact_dir=artifact_dir)
        return response, 0 if response is not None else 1
    if node_id == "method-combiner":
        response = _run_method_combiner(start_payload=start_payload, artifact_dir=artifact_dir)
        return response, 0 if response is not None else 1
    if node_id == "exploit-code-author":
        response = _run_exploit_code_author(start_payload=start_payload, artifact_dir=artifact_dir)
        return response, 0 if response is not None and response.get("result", {}).get("status") == "PASS" else 1

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


def _run_exploit_code_author(*, start_payload: dict[str, Any], artifact_dir: Path) -> dict[str, Any] | None:
    lineage_path = _find_named_artifact(start_payload, "lineage_summary.json")
    research_path = _find_named_artifact(start_payload, "research_receipts.json")
    candidates_path = _find_named_artifact(start_payload, "candidate_methods.json")
    genome_path = _find_named_artifact(start_payload, "exploit_genome.json")
    child_packet_path = _find_named_artifact(start_payload, "child-knowledge-packet.json")
    missing = [
        name
        for name, path in {
            "lineage_summary.json": lineage_path,
            "research_receipts.json": research_path,
            "candidate_methods.json": candidates_path,
            "exploit_genome.json": genome_path,
        }.items()
        if path is None
    ]
    if missing:
        receipt = _node_receipt(node_id="exploit-code-author", status="BLOCKED", verdict="UPSTREAM_CODE_AUTHOR_INPUT_MISSING", evidence=[])
        receipt["reason"] = f"exploit-code-author missing upstream artifacts: {', '.join(missing)}"
        receipt["claims"] = {
            "proves": ["Battle reached the exploit-code-author command-spec boundary."],
            "does_not_prove": ["A provider authored exploit code.", "Exploit success."],
        }
        _write_json(artifact_dir / "exploit-code-author-node-receipt.json", receipt)
        return None

    result = run_code_author(
        artifact_dir=artifact_dir,
        lineage_summary_path=lineage_path,
        research_receipts_path=research_path,
        candidate_methods_path=candidates_path,
        exploit_genome_path=genome_path,
        child_knowledge_packet_path=child_packet_path,
        dag_id=_target_value(start_payload, "dag_id"),
        goal_hash=_goal_hash(start_payload),
    )
    evidence = [
        _evidence("lineage_summary.json", lineage_path),
        _evidence("research_receipts.json", research_path),
        _evidence("candidate_methods.json", candidates_path),
        _evidence("exploit_genome.json", genome_path),
        _evidence("exploit-code-author-work-order.json", result["battle_work_order_path"]),
        _evidence("tau-scillm-worker-work-order.json", result["tau_work_order_path"]),
        _evidence("tau-scillm-worker-launch-receipt.json", result["launch_receipt_path"]),
        _evidence("provider-artifact-validation.json", result["artifact_validation_path"]),
        _evidence("provider-authorship-receipt.json", result["provider_authorship_path"]),
        _evidence("provider-code-author-boundary-receipt.json", result["boundary_receipt_path"]),
    ]
    if result.get("worker_result_path") is not None:
        evidence.append(_evidence("provider-worker-result.json", result["worker_result_path"]))
    if result.get("validation_receipt_path") is not None:
        evidence.append(_evidence("tau-worker-validation-receipt.json", result["validation_receipt_path"]))
    if result.get("code_path") is not None:
        evidence.append(_evidence("exploit_specimen.py", result["code_path"]))
    if result.get("specimen_path") is not None:
        evidence.append(_evidence("specimen.json", result["specimen_path"]))

    status = result["status"]
    receipt = _node_receipt(
        node_id="exploit-code-author",
        status=status,
        verdict=result["verdict"],
        evidence=evidence,
    )
    receipt["provider_live"] = result["authorship"].get("provider_live")
    receipt["agentic"] = bool(result["authorship"].get("agentic"))
    receipt["execution_mode"] = result["authorship"].get("execution_mode")
    receipt["authored_by"] = result["authorship"].get("authored_by")
    receipt["errors"] = result["authorship"].get("errors", [])
    receipt["claims"] = result["claims"]
    receipt_path = artifact_dir / "exploit-code-author-node-receipt.json"
    _write_json(receipt_path, receipt)

    if status != "PASS":
        return _handoff(
            start_payload=start_payload,
            previous_subagent="exploit-code-author",
            status="BLOCKED",
            summary=f"Exploit Code Author blocked at {result['verdict']}.",
            evidence=[*evidence, _evidence("exploit-code-author-node-receipt.json", receipt_path)],
            next_agent="compile-repair",
            artifacts=[str(item["path"]) for item in evidence if item.get("path")],
        )

    return _handoff(
        start_payload=start_payload,
        previous_subagent="exploit-code-author",
        status="PASS",
        summary="Exploit Code Author materialized provider-authored exploit specimen artifact.",
        evidence=[*evidence, _evidence("exploit-code-author-node-receipt.json", receipt_path)],
        next_agent="compile-repair",
        artifacts=[str(result["code_path"]), str(result["specimen_path"]), str(result["provider_authorship_path"]), str(result["boundary_receipt_path"]), str(receipt_path)],
    )


def _run_research_scout(*, start_payload: dict[str, Any], artifact_dir: Path) -> dict[str, Any] | None:
    lineage_path = _find_named_artifact(start_payload, "lineage_summary.json")
    if lineage_path is None:
        receipt = _node_receipt(node_id="research-scout", status="BLOCKED", verdict="RESEARCH_SOURCE_INPUT_MISSING", evidence=[])
        receipt["reason"] = "research-scout requires lineage_summary.json from the live Tau command loop."
        receipt["claims"] = {
            "proves": ["Battle reached the research-scout command-spec boundary."],
            "does_not_prove": ["Research Scout produced source-bearing receipts.", "Exploit success."],
        }
        _write_json(artifact_dir / "research-scout-node-receipt.json", receipt)
        return None

    result = run_research_scout(artifact_dir=artifact_dir, lineage_summary_path=lineage_path)
    evidence = [
        _evidence("lineage_summary.json", lineage_path),
        _evidence("research-source-packet.json", result["source_packet_path"]),
        _evidence("research-source-receipt.json", result["source_receipt_path"]),
        _evidence("research_receipts.json", result["research_receipts_path"]),
        _evidence("candidate_methods.json", result["candidate_methods_path"]),
    ]
    receipt = _node_receipt(
        node_id="research-scout",
        status=result["status"],
        verdict=result["status"],
        evidence=evidence,
    )
    receipt["tau_research_source_receipt"] = str(result["source_receipt_path"])
    receipt["claims"] = result["research_receipts"]["claims"]
    receipt_path = artifact_dir / "research-scout-node-receipt.json"
    _write_json(receipt_path, receipt)
    if result["status"] != "PASS":
        return None
    evidence.append(_evidence("research-scout-node-receipt.json", receipt_path))
    return _handoff(
        start_payload=start_payload,
        previous_subagent="research-scout",
        status="PASS",
        summary="Research Scout produced Tau-validated source-bearing design-input receipts.",
        evidence=evidence,
        next_agent="method-combiner",
        artifacts=[str(result["research_receipts_path"]), str(result["candidate_methods_path"]), str(receipt_path)],
    )


def _run_method_combiner(*, start_payload: dict[str, Any], artifact_dir: Path) -> dict[str, Any] | None:
    research_path = _find_named_artifact(start_payload, "research_receipts.json")
    candidates_path = _find_named_artifact(start_payload, "candidate_methods.json")
    missing = [name for name, path in {"research_receipts.json": research_path, "candidate_methods.json": candidates_path}.items() if path is None]
    if missing:
        receipt = _node_receipt(node_id="method-combiner", status="BLOCKED", verdict="UPSTREAM_RESEARCH_ARTIFACT_MISSING", evidence=[])
        receipt["reason"] = f"method-combiner missing upstream artifacts: {', '.join(missing)}"
        receipt["claims"] = {
            "proves": ["Battle reached the method-combiner command-spec boundary."],
            "does_not_prove": ["A source-backed exploit genome was produced.", "Exploit success."],
        }
        _write_json(artifact_dir / "method-combiner-node-receipt.json", receipt)
        return None

    result = run_method_combiner(
        artifact_dir=artifact_dir,
        research_receipts_path=research_path,
        candidate_methods_path=candidates_path,
    )
    evidence = [
        _evidence("research_receipts.json", research_path),
        _evidence("candidate_methods.json", candidates_path),
        _evidence("exploit_genome.json", result["genome_path"]),
        _evidence("combination_rationale.md", result["rationale_path"]),
    ]
    receipt = _node_receipt(
        node_id="method-combiner",
        status=result["status"],
        verdict=result["status"],
        evidence=evidence,
    )
    receipt["claims"] = result["genome"]["claims"]
    receipt["errors"] = result["errors"]
    receipt_path = artifact_dir / "method-combiner-node-receipt.json"
    _write_json(receipt_path, receipt)
    if result["status"] != "PASS":
        return None
    evidence.append(_evidence("method-combiner-node-receipt.json", receipt_path))
    return _handoff(
        start_payload=start_payload,
        previous_subagent="method-combiner",
        status="PASS",
        summary="Method Combiner produced a deterministic source-backed exploit genome candidate.",
        evidence=evidence,
        next_agent="exploit-code-author",
        artifacts=[str(result["genome_path"]), str(result["rationale_path"]), str(receipt_path)],
    )


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
    carried_artifacts = _dedupe_artifacts([*_context_artifacts(start_payload), *artifacts])
    return {
        "schema": "tau.agent_handoff.v1",
        "github": start_payload.get("github") if isinstance(start_payload.get("github"), dict) else {"repo": "grahama1970/agent-skills", "target": "skills/battle"},
        "goal": start_payload.get("goal") if isinstance(start_payload.get("goal"), dict) else {},
        "previous_subagent": previous_subagent,
        "context": {
            "summary": summary,
            "artifacts": carried_artifacts,
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


def _dedupe_artifacts(artifacts: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for artifact in artifacts:
        if artifact in seen:
            continue
        seen.add(artifact)
        result.append(artifact)
    return result


def _node_receipt(*, node_id: str, status: str, verdict: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": NODE_RECEIPT_SCHEMA,
        "node_id": node_id,
        "status": status,
        "verdict": verdict,
        "mocked": False,
        "live": "tau_command_spec_node",
        "agentic": False,
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


def _find_named_artifact(payload: dict[str, Any], name: str) -> Path | None:
    candidates: list[str] = []
    candidates.extend(_context_artifacts(payload))
    for item in _result_evidence(payload):
        if isinstance(item, dict) and isinstance(item.get("path"), str):
            candidates.append(item["path"])
    for candidate in candidates:
        path = Path(candidate)
        if path.name == name and path.exists():
            return path.resolve()
    return None


def _target_value(payload: dict[str, Any], key: str) -> Any:
    context = payload.get("context")
    tau_node = context.get("tau_dag_node") if isinstance(context, dict) else None
    target = tau_node.get("target") if isinstance(tau_node, dict) else None
    return target.get(key) if isinstance(target, dict) else None


def _goal_hash(payload: dict[str, Any]) -> str | None:
    goal = payload.get("goal")
    value = goal.get("goal_hash") if isinstance(goal, dict) else None
    return value if isinstance(value, str) and value else None


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
