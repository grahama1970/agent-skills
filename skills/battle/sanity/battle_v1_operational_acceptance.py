#!/usr/bin/env python3
"""Validate generated Battle v1 operational artifacts.

This checker is intentionally artifact-only. It does not execute target,
probe, patch, or regression code on the host. Run the Battle v1 CLI first,
then point this checker at the generated artifact directory.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any


REQUIRED = [
    "arena-receipt.json",
    "red/team-receipt.json",
    "blue/team-receipt.json",
    "scorekeeper/scorekeeper-receipt.json",
    "context/memory-recall-receipt.json",
    "context/research-broker-receipt.json",
    "context/warm-pond-receipt.json",
    "context/memory-promotion-receipt.json",
    "context/context-receipt.json",
    "scoreboard.json",
    "monitor-index.json",
    "run-receipt.json",
    "subagent-ledger.sqlite",
    "graph/battle-v1-force-graph.json",
]


def load_json(root: Path, rel: str) -> dict[str, Any]:
    path = root / rel
    if not path.is_file():
        raise AssertionError(f"missing required artifact: {rel}")
    return json.loads(path.read_text(encoding="utf-8"))


def docker_command_count(value: Any) -> int:
    count = 0
    if isinstance(value, dict):
        if isinstance(value.get("command"), list) and value["command"][:2] == ["docker", "run"]:
            count += 1
        for child in value.values():
            count += docker_command_count(child)
    elif isinstance(value, list):
        for child in value:
            count += docker_command_count(child)
    return count


def assert_no_host_target_execution(value: Any) -> None:
    if isinstance(value, dict):
        cmd = value.get("command")
        if isinstance(cmd, list) and cmd:
            joined = " ".join(str(part) for part in cmd)
            static_code_context = "treesitter/run.sh symbols" in joined
            target_execution = "exploit_check.py" in joined or "unittest" in joined
            if target_execution and cmd[:2] != ["docker", "run"] and not static_code_context:
                raise AssertionError(f"target/probe/test command is not docker run: {joined}")
        for child in value.values():
            assert_no_host_target_execution(child)
    elif isinstance(value, list):
        for child in value:
            assert_no_host_target_execution(child)


def intervals_overlap(a: dict[str, Any], b: dict[str, Any]) -> bool:
    at = a.get("async_timing", {})
    bt = b.get("async_timing", {})
    return (
        float(at.get("started_at_seconds", 0.0)) < float(bt.get("finished_at_seconds", 0.0))
        and float(bt.get("started_at_seconds", 0.0)) < float(at.get("finished_at_seconds", 0.0))
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_dir", type=Path)
    parser.add_argument("--require-recall-found", action="store_true")
    parser.add_argument("--allow-first-recall-empty", action="store_true")
    parser.add_argument("--min-red-workers", type=int, default=2)
    parser.add_argument("--min-blue-workers", type=int, default=2)
    args = parser.parse_args()

    root = args.artifact_dir.resolve()
    missing = [rel for rel in REQUIRED if not (root / rel).is_file()]
    if missing:
        raise AssertionError(f"missing required artifacts: {missing}")

    run = load_json(root, "run-receipt.json")
    scoreboard = load_json(root, "scoreboard.json")
    arena = load_json(root, "arena-receipt.json")
    red = load_json(root, "red/team-receipt.json")
    blue = load_json(root, "blue/team-receipt.json")
    scorekeeper = load_json(root, "scorekeeper/scorekeeper-receipt.json")
    memory_recall = load_json(root, "context/memory-recall-receipt.json")
    research = load_json(root, "context/research-broker-receipt.json")
    warm_pond = load_json(root, "context/warm-pond-receipt.json")
    memory_promotion = load_json(root, "context/memory-promotion-receipt.json")
    graph = load_json(root, "graph/battle-v1-force-graph.json")
    monitor = load_json(root, "monitor-index.json")

    assert run["schema"] == "battle.run_receipt.v1"
    assert run["status"] == "PASS", run
    assert run["verdict"] == "BLUE_SUCCESS", run
    assert run["execution"]["live"] == "docker_four_party_operational", run
    assert run["execution"]["docker_only"] is True, run

    assert arena["status"] == "PASS", arena
    assert red["status"] == "PASS", red
    assert blue["status"] == "PASS", blue
    assert scorekeeper["status"] == "PASS", scorekeeper
    assert scorekeeper["arena_team_is_judge"] is False, scorekeeper
    assert scorekeeper["objective_replay"] is True, scorekeeper
    assert scorekeeper["target_container_network"] == "none", scorekeeper

    assert scoreboard["operational"]["four_party"] is True, scoreboard
    assert scoreboard["operational"]["red_blue_async"] is True, scoreboard
    assert scoreboard["operational"]["scorekeeper_objective_replay"] is True, scoreboard
    assert scoreboard["context"]["memory_promotion_status"] == "PASS", scoreboard
    assert scoreboard["context"]["research_broker_status"] == "PASS", scoreboard
    assert scoreboard["context"]["research_passed_lane_count"] >= 1, scoreboard

    assert red["worker_count"] >= args.min_red_workers, red
    assert blue["worker_count"] >= args.min_blue_workers, blue
    assert red["overlap_evidence"]["overlap_detected"] is True, red
    assert blue["overlap_evidence"]["overlap_detected"] is True, blue

    red_workers = [load_json(root, rel) for rel in red["worker_receipts"]]
    blue_workers = [load_json(root, rel) for rel in blue["worker_receipts"]]
    assert any(intervals_overlap(r, b) for r in red_workers for b in blue_workers), "no worker timestamp overlap"
    for receipt in [*red_workers, *blue_workers]:
        dispatch = receipt.get("research_dispatch", {})
        assert dispatch.get("first_research_lane"), receipt
        assert float(dispatch.get("research_boost", 0.0)) > 0.0, receipt
        assert dispatch.get("research_sources"), receipt

    assert memory_promotion["status"] == "PASS", memory_promotion
    assert memory_promotion["document_count"] >= 1, memory_promotion
    assert memory_promotion["winner_count"] >= 1, memory_promotion
    if args.require_recall_found:
        assert memory_recall["status"] == "PASS", memory_recall
        assert memory_recall["found"] is True, memory_recall
    elif not args.allow_first_recall_empty:
        assert memory_recall["status"] == "PASS", memory_recall
    assert research["status"] == "PASS", research
    assert research["mocked"] is False, research
    assert research["live"] is True, research
    assert research["mode"] == "threadpool_as_completed", research
    assert research["passed_lane_count"] >= 1, research
    assert len(research["completion_order"]) >= 1, research
    assert warm_pond["status"] == "PASS", warm_pond
    assert "research-adjusted affinity" in warm_pond["selection_rule"], warm_pond
    assert warm_pond["research_weighted_candidate_count"] >= 1, warm_pond
    assert warm_pond["research_weighted_combination_count"] >= 1, warm_pond
    assert warm_pond["research_signal_summary"]["passed_lane_count"] >= 1, warm_pond

    assert monitor["schema"] == "battle.monitor_index.v1", monitor
    assert monitor["graph"] == "graph/battle-v1-force-graph.json", monitor
    assert graph["schema"] == "battle.force_graph.v1", graph
    node_ids = {node["id"] for node in graph["nodes"]}
    for expected in [
        "team:arena",
        "team:red",
        "team:blue",
        "scorekeeper",
        "signal:research-broker",
        "signal:memory-promotion",
        "signal:async-overlap",
    ]:
        assert expected in node_ids, f"missing graph node {expected}"

    for json_path in root.rglob("*.json"):
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            if json_path.name.endswith(".stdout.json"):
                continue
            raise
        assert_no_host_target_execution(payload)
    scorekeeper_docker_commands = docker_command_count(scorekeeper)
    for attempt_rel in scorekeeper["attempt_receipts"]:
        scorekeeper_docker_commands += docker_command_count(load_json(root, attempt_rel))
    assert scorekeeper_docker_commands >= 4, "scorekeeper did not record docker commands"

    with sqlite3.connect(root / "subagent-ledger.sqlite") as conn:
        count = conn.execute("select count(*) from events").fetchone()[0]
    assert count >= 6, f"subagent ledger event count too small: {count}"

    print("BATTLE_V1_OPERATIONAL_ACCEPTANCE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
