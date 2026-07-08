#!/usr/bin/env python3
"""Check Persona Dream revision lineage and write a local respawn plan."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_RESPAWN_PLAN"
BLOCKED_STATUS = "BLOCKED_RESPAWN_PLAN"
DECISIONS = {
    "CURRENT",
    "REUSE_ALLOWED",
    "REVALIDATE_REQUIRED",
    "REGENERATE_REQUIRED",
    "REVIEW_REQUIRED",
    "BLOCKED_HUMAN_DECISION_REQUIRED",
    "SUPERSEDED",
}
PHASE_ORDER = {
    "01_memory_residue": 1,
    "02_story_contract": 2,
    "06_script_contract": 6,
    "07_storyboard": 7,
    "08_kling_scene_packet": 8,
    "reference_asset": 5,
    "kling_settings": 8,
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def add_blocker(blockers: list[dict[str, Any]], status: str, field: str, detail: str = "") -> None:
    blockers.append({"status": status, "field": field, "detail": detail})


def current_sources(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    sources: dict[str, dict[str, Any]] = {}
    raw_sources = manifest.get("current_sources")
    if isinstance(raw_sources, dict):
        for source_id, source in raw_sources.items():
            if isinstance(source, dict):
                item = dict(source)
                item.setdefault("artifact_id", source_id)
                sources[source_id] = item
    for item in manifest.get("reference_assets") or []:
        if isinstance(item, dict) and item.get("asset_id"):
            source_id = f"reference.{item['asset_id']}"
            item = dict(item)
            item.setdefault("artifact_id", source_id)
            item.setdefault("phase", "reference_asset")
            sources[source_id] = item
    for item in manifest.get("kling_settings") or []:
        if isinstance(item, dict) and item.get("settings_id"):
            source_id = f"kling_settings.{item['settings_id']}"
            item = dict(item)
            item.setdefault("artifact_id", source_id)
            item.setdefault("phase", "kling_settings")
            sources[source_id] = item
    return sources


def graph_nodes(manifest: dict[str, Any], sources: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    nodes = {source_id: dict(source) for source_id, source in sources.items()}
    raw_graph = manifest.get("derivation_graph")
    raw_nodes = raw_graph.get("nodes") if isinstance(raw_graph, dict) else None
    if isinstance(raw_nodes, list):
        for node in raw_nodes:
            if isinstance(node, dict) and isinstance(node.get("artifact_id"), str):
                nodes[node["artifact_id"]] = dict(node)
    return nodes


def graph_edges(manifest: dict[str, Any], blockers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw_graph = manifest.get("derivation_graph")
    if not isinstance(raw_graph, dict):
        add_blocker(blockers, "BLOCKED_DERIVATION_GRAPH_MISSING", "derivation_graph", "missing")
        return []
    raw_edges = raw_graph.get("edges")
    if not isinstance(raw_edges, list):
        add_blocker(blockers, "BLOCKED_DERIVATION_GRAPH_MISSING", "derivation_graph.edges", "missing")
        return []
    return [edge for edge in raw_edges if isinstance(edge, dict)]


def validate_manifest(manifest: dict[str, Any], blockers: list[dict[str, Any]]) -> None:
    if manifest.get("schema") != "persona_dream.dream_revision_manifest.v1":
        add_blocker(blockers, "BLOCKED_REVISION_MANIFEST_SCHEMA", "schema", str(manifest.get("schema")))
    policy = manifest.get("policy")
    if not isinstance(policy, dict):
        add_blocker(blockers, "BLOCKED_REVISION_MANIFEST_SCHEMA", "policy", "missing")
        return
    if policy.get("provider_live") is not False:
        add_blocker(blockers, "BLOCKED_PROVIDER_LIVE_IN_RESPAWN_CHECK", "policy.provider_live", "must be false")
    if policy.get("paid_call_authorized") is not False:
        add_blocker(blockers, "BLOCKED_PAID_CALL_AUTHORIZED_IN_RESPAWN_CHECK", "policy.paid_call_authorized", "must be false")
    if policy.get("manual_acceptance_claimed") is True:
        add_blocker(blockers, "BLOCKED_MANUAL_DECISION_REQUIRED", "policy.manual_acceptance_claimed", "respawn cannot claim manual acceptance")


def validate_artifact_bindings(nodes: dict[str, dict[str, Any]], blockers: list[dict[str, Any]], require_reviewer_receipts: bool) -> None:
    for artifact_id, node in nodes.items():
        path = node.get("path")
        sha = node.get("sha256")
        if not path:
            add_blocker(blockers, "BLOCKED_ARTIFACT_PATH_MISSING", f"nodes.{artifact_id}.path", "missing")
        if not isinstance(sha, str) or not sha.startswith("sha256:"):
            add_blocker(blockers, "BLOCKED_ARTIFACT_HASH_MISSING", f"nodes.{artifact_id}.sha256", "missing")
        status = str(node.get("status") or "")
        if require_reviewer_receipts and (
            status.startswith("PASS_") or status.startswith("ACCEPTED") or status == "GENERATED_UNREVIEWED"
        ):
            if node.get("accepted") is True or node.get("phase") in {"07_storyboard", "08_kling_scene_packet"}:
                reviewer_paths = node.get("reviewer_receipt_paths")
                if not isinstance(reviewer_paths, list) or not reviewer_paths:
                    add_blocker(
                        blockers,
                        "BLOCKED_REVIEWER_RECEIPT_MISSING_FOR_ACCEPTED_ARTIFACT",
                        f"nodes.{artifact_id}.reviewer_receipt_paths",
                        "accepted/review artifact requires reviewer receipt lineage",
                    )


def descendants(edges: list[dict[str, Any]]) -> dict[str, set[str]]:
    direct: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        from_id = str(edge.get("from_artifact_id") or "")
        to_id = str(edge.get("to_artifact_id") or "")
        if from_id and to_id:
            direct[from_id].add(to_id)
    result: dict[str, set[str]] = defaultdict(set)
    for start in direct:
        seen: set[str] = set()
        queue = deque(direct[start])
        while queue:
            node = queue.popleft()
            if node in seen:
                continue
            seen.add(node)
            result[start].add(node)
            queue.extend(direct.get(node, set()))
    return result


def reason_for_phase(node: dict[str, Any], changed_source: dict[str, Any], dependency_type: str) -> tuple[str, str]:
    phase = str(node.get("phase") or "")
    source_phase = str(changed_source.get("phase") or "")
    if phase == "08_kling_scene_packet":
        if source_phase == "kling_settings":
            return "REGENERATE_REQUIRED", "BLOCKED_UPSTREAM_HASH_CHANGED"
        if dependency_type in {"SOURCE_STORYBOARD", "MEDIA_LOCK", "REFERENCE_ASSET"}:
            return "REGENERATE_REQUIRED", "BLOCKED_STALE_KLING_SCENE_PACKET"
        return "REGENERATE_REQUIRED", "BLOCKED_STALE_KLING_SCENE_PACKET"
    if phase == "07_storyboard":
        if source_phase == "reference_asset":
            return "REVALIDATE_REQUIRED", "BLOCKED_STALE_MEDIA_LOCK"
        return "REGENERATE_REQUIRED", "BLOCKED_STALE_ACCEPTED_ARTIFACT"
    if phase in {"06_script_contract", "02_story_contract"}:
        return "REGENERATE_REQUIRED", "BLOCKED_UPSTREAM_HASH_CHANGED"
    return "REVALIDATE_REQUIRED", "BLOCKED_UPSTREAM_HASH_CHANGED"


def build_plan(manifest: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
    blockers: list[dict[str, Any]] = []
    validate_manifest(manifest, blockers)
    sources = current_sources(manifest)
    if not sources:
        add_blocker(blockers, "BLOCKED_REVISION_MANIFEST_SCHEMA", "current_sources", "missing")
    nodes = graph_nodes(manifest, sources)
    edges = graph_edges(manifest, blockers)
    require_reviewer_receipts = bool(manifest.get("policy", {}).get("require_reviewer_receipts_for_acceptance", True))
    validate_artifact_bindings(nodes, blockers, require_reviewer_receipts)

    changed_sources: dict[str, dict[str, Any]] = {}
    incoming_by_to: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        from_id = str(edge.get("from_artifact_id") or "")
        to_id = str(edge.get("to_artifact_id") or "")
        if not from_id or not to_id:
            add_blocker(blockers, "BLOCKED_DERIVATION_EDGE_MISSING", "derivation_graph.edges", "missing from/to")
            continue
        incoming_by_to[to_id].append(edge)
        source = sources.get(from_id)
        if source:
            current_sha = source.get("sha256")
            edge_sha = edge.get("from_sha256")
            if current_sha != edge_sha:
                changed_sources[from_id] = {
                    "source": source,
                    "edge": edge,
                    "current_sha": current_sha,
                    "lineage_sha": edge_sha,
                }

    all_descendants = descendants(edges)
    affected: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source_id, change in changed_sources.items():
        for artifact_id in all_descendants.get(source_id, set()):
            affected[artifact_id].append(change)

    decisions: list[dict[str, Any]] = []
    for artifact_id, node in sorted(nodes.items(), key=lambda item: (PHASE_ORDER.get(str(item[1].get("phase")), 99), item[0])):
        if affected.get(artifact_id) and artifact_id not in changed_sources:
            change = affected[artifact_id][0]
            source = change["source"]
            dep_type = str(change["edge"].get("dependency_type") or "")
            decision, reason_code = reason_for_phase(node, source, dep_type)
            upstream_change = source.get("artifact_id")
            previous_sha = change["lineage_sha"]
            current_sha = change["current_sha"]
            blocker_status = reason_code
            if blocker_status.startswith("BLOCKED_"):
                add_blocker(blockers, blocker_status, artifact_id, f"upstream changed: {upstream_change}")
        elif artifact_id in sources:
            decision = "CURRENT"
            reason_code = "SOURCE_CURRENT"
            upstream_change = None
            previous_sha = node.get("sha256")
            current_sha = node.get("sha256")
            if artifact_id in changed_sources:
                decision = "CURRENT"
                reason_code = "SOURCE_HASH_CHANGED_NEW_REVISION"
                upstream_change = artifact_id
                previous_sha = changed_sources[artifact_id]["lineage_sha"]
                current_sha = changed_sources[artifact_id]["current_sha"]
            elif str(node.get("phase")) in {"07_storyboard", "08_kling_scene_packet"}:
                decision = "REUSE_ALLOWED"
                reason_code = "DEPENDENCY_HASHES_MATCH"
        else:
            decision = "REUSE_ALLOWED" if str(node.get("phase")) in {"08_kling_scene_packet", "07_storyboard"} else "CURRENT"
            reason_code = "DEPENDENCY_HASHES_MATCH"
            upstream_change = None
            previous_sha = node.get("sha256")
            current_sha = node.get("sha256")
        decisions.append(
            {
                "artifact_id": artifact_id,
                "path": node.get("path"),
                "previous_sha256": previous_sha,
                "current_dependency_sha256": current_sha,
                "decision": decision,
                "reason_code": reason_code,
                "upstream_change": upstream_change,
            }
        )

    if any(item["decision"] in {"REGENERATE_REQUIRED", "REVALIDATE_REQUIRED"} for item in decisions):
        plan_status = "RESPAWN_PLAN_GENERATED"
    else:
        plan_status = PASS_STATUS
    hard_blockers = [
        blocker
        for blocker in blockers
        if blocker["status"]
        in {
            "BLOCKED_REVISION_MANIFEST_MISSING",
            "BLOCKED_REVISION_MANIFEST_SCHEMA",
            "BLOCKED_DERIVATION_GRAPH_MISSING",
            "BLOCKED_DERIVATION_EDGE_MISSING",
            "BLOCKED_ARTIFACT_PATH_MISSING",
            "BLOCKED_ARTIFACT_HASH_MISSING",
            "BLOCKED_REVIEWER_RECEIPT_MISSING_FOR_ACCEPTED_ARTIFACT",
            "BLOCKED_PROVIDER_LIVE_IN_RESPAWN_CHECK",
            "BLOCKED_PAID_CALL_AUTHORIZED_IN_RESPAWN_CHECK",
            "BLOCKED_MANUAL_DECISION_REQUIRED",
        }
    ]
    if hard_blockers:
        plan_status = BLOCKED_STATUS

    summary: dict[str, list[str]] = {
        "current": [],
        "reuse_allowed": [],
        "revalidate_required": [],
        "regenerate_required": [],
        "review_required": [],
        "blocked_human_decision_required": [],
        "superseded": [],
    }
    for decision in decisions:
        key = decision["decision"].lower()
        summary.setdefault(key, []).append(decision["artifact_id"])

    return {
        "schema": "persona_dream.respawn_plan.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "manifest_path": str(manifest_path),
        "run_id": manifest.get("run_id"),
        "revision_id": manifest.get("revision_id"),
        "parent_revision_id": manifest.get("parent_revision_id"),
        "status": plan_status,
        "provider_live": False,
        "paid_call_authorized": False,
        "summary": summary,
        "decisions": decisions,
        "blockers": blockers,
        "claims": {
            "proves": [
                "current upstream hashes were compared against downstream lineage",
                "stale/reuse/regenerate decisions were computed locally",
            ],
            "does_not_prove": [
                "new artifacts were regenerated",
                "visual quality",
                "manual acceptance",
                "provider readiness",
                "live Kling generation",
            ],
        },
    }


def run_one(manifest_path: Path, output_root: Path) -> dict[str, Any]:
    manifest = read_json(manifest_path)
    plan = build_plan(manifest, manifest_path)
    plan_path = output_root / "respawn_plan.v1.json"
    write_json(plan_path, plan)
    receipt = {
        "schema": "persona_dream.dream_respawn_plan_receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": plan["status"],
        "provider_live": False,
        "paid_call_authorized": False,
        "manifest_path": str(manifest_path),
        "respawn_plan_path": str(plan_path),
        "decision_counts": {key: len(value) for key, value in plan["summary"].items()},
        "observed_decisions": sorted({item["decision"] for item in plan["decisions"]}),
        "observed_blockers": sorted({item["status"] for item in plan["blockers"]}),
        "blockers": plan["blockers"],
        "claims": plan["claims"],
    }
    receipt_path = output_root / "dream_respawn_plan_receipt.v1.json"
    write_json(receipt_path, receipt)
    return {
        "manifest": str(manifest_path),
        "plan": str(plan_path),
        "receipt": str(receipt_path),
        "status": receipt["status"],
        "observed_decisions": receipt["observed_decisions"],
        "observed_blockers": receipt["observed_blockers"],
    }


def expected_for_fixture(fixture_dir: Path) -> dict[str, Any]:
    path = fixture_dir / "expected.json"
    return read_json(path) if path.exists() else {}


def run_fixtures(fixtures_root: Path, receipt_out: Path) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    output_root = receipt_out.parent / "respawn-fixture-results"
    for manifest_path in sorted(fixtures_root.glob("**/dream_revision_manifest.v1.json")):
        fixture_dir = manifest_path.parent
        result_dir = output_root / fixture_dir.relative_to(fixtures_root)
        result = run_one(manifest_path, result_dir)
        expected = expected_for_fixture(fixture_dir)
        errors: list[str] = []
        expected_status = expected.get("status")
        if expected_status and result["status"] != expected_status:
            errors.append(f"status_mismatch:{result['status']}:expected:{expected_status}")
        for decision in expected.get("decisions", []):
            if decision not in result["observed_decisions"]:
                errors.append(f"missing_decision:{decision}")
        for blocker in expected.get("blockers", []):
            if blocker not in result["observed_blockers"]:
                errors.append(f"missing_blocker:{blocker}")
        result["expected"] = expected
        result["errors"] = errors
        results.append(result)

    blockers = [f"{Path(result['manifest']).parent.name}:{error}" for result in results for error in result["errors"]]
    receipt = {
        "schema": "persona_dream.respawn_plan_checker_receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": PASS_STATUS if not blockers else BLOCKED_STATUS,
        "provider_live": False,
        "paid_call_authorized": False,
        "blockers": blockers,
        "fixture_count": len(results),
        "observed_decisions": sorted({decision for result in results for decision in result["observed_decisions"]}),
        "observed_blockers": sorted({blocker for result in results for blocker in result["observed_blockers"]}),
        "results": results,
        "claims": {
            "proves": [
                "respawn checker classified positive and negative fixture lineage",
                "provider_live and paid_call_authorized remained false",
            ],
            "does_not_prove": [
                "artifact regeneration",
                "visual quality",
                "manual acceptance",
                "provider readiness",
                "live Kling generation",
            ],
        },
    }
    write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--revision-manifest", type=Path)
    group.add_argument("--fixtures-root", type=Path)
    parser.add_argument("--receipt-out", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.revision_manifest:
        result = run_one(args.revision_manifest.resolve(), args.receipt_out.resolve().parent)
        receipt = read_json(Path(result["receipt"]))
        write_json(args.receipt_out, receipt)
    else:
        receipt = run_fixtures(args.fixtures_root.resolve(), args.receipt_out.resolve())
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
    return 0 if receipt["status"] in {PASS_STATUS, "RESPAWN_PLAN_GENERATED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
