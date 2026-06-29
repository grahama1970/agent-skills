#!/usr/bin/env python3
"""Validate generated Battle v1 multi-round artifacts.

This checker is artifact-only. It inspects receipts from a prior
``battle-v1-multiround`` run and does not execute target, probe, patch, or
regression code on the host.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


def load_json(root: Path, rel: str) -> dict[str, Any]:
    path = root / rel
    if not path.is_file():
        raise AssertionError(f"missing required artifact: {rel}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AssertionError(f"artifact is not a JSON object: {rel}")
    return data


def docker_command_count(value: Any) -> int:
    count = 0
    if isinstance(value, dict):
        command = value.get("command")
        if isinstance(command, list) and command[:2] == ["docker", "run"]:
            count += 1
        for child in value.values():
            count += docker_command_count(child)
    elif isinstance(value, list):
        for child in value:
            count += docker_command_count(child)
    return count


def assert_no_host_target_execution(value: Any) -> None:
    if isinstance(value, dict):
        command = value.get("command")
        if isinstance(command, list) and command:
            joined = " ".join(str(part) for part in command)
            static_code_context = "treesitter/run.sh symbols" in joined
            target_execution = "exploit_check.py" in joined or "unittest" in joined
            if target_execution and command[:2] != ["docker", "run"] and not static_code_context:
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


def validate_operational_round(
    *,
    root: Path,
    rel: str,
    min_red_workers: int,
    min_blue_workers: int,
) -> dict[str, Any]:
    run = load_json(root, f"{rel}/run-receipt.json")
    red = load_json(root, f"{rel}/red/team-receipt.json")
    blue = load_json(root, f"{rel}/blue/team-receipt.json")
    scorekeeper = load_json(root, f"{rel}/scorekeeper/scorekeeper-receipt.json")
    warm_pond = load_json(root, f"{rel}/context/warm-pond-receipt.json")
    research = load_json(root, f"{rel}/context/research-broker-receipt.json")
    tau_context = load_json(root, f"{rel}/context/tau-battle-context-bundle.json")

    assert run["schema"] == "battle.run_receipt.v1", run
    assert run["status"] == "PASS", run
    assert run["verdict"] == "BLUE_SUCCESS", run
    assert run["execution"]["docker_only"] is True, run
    assert red["status"] == "PASS", red
    assert blue["status"] == "PASS", blue
    assert red["worker_count"] >= min_red_workers, red
    assert blue["worker_count"] >= min_blue_workers, blue
    assert red["overlap_evidence"]["overlap_detected"] is True, red
    assert blue["overlap_evidence"]["overlap_detected"] is True, blue

    red_workers = [load_json(root, f"{rel}/{worker_rel}") for worker_rel in red["worker_receipts"]]
    blue_workers = [load_json(root, f"{rel}/{worker_rel}") for worker_rel in blue["worker_receipts"]]
    assert any(intervals_overlap(r, b) for r in red_workers for b in blue_workers), "no async worker overlap"

    assert scorekeeper["status"] == "PASS", scorekeeper
    assert scorekeeper["arena_team_is_judge"] is False, scorekeeper
    assert scorekeeper["target_container_network"] == "none", scorekeeper
    assert scorekeeper["objective_replay"] is True, scorekeeper
    assert scorekeeper["attempt_count"] >= 1, scorekeeper
    assert scorekeeper["passed_attempt_count"] == scorekeeper["attempt_count"], scorekeeper
    assert warm_pond["status"] == "PASS", warm_pond
    assert research["status"] == "PASS", research
    assert research["mode"] == "threadpool_as_completed", research
    assert research["passed_lane_count"] >= 1, research
    assert tau_context["schema"] == "tau.battle_context_bundle.v1", tau_context

    docker_commands = docker_command_count(scorekeeper)
    for attempt_rel in scorekeeper["attempt_receipts"]:
        docker_commands += docker_command_count(load_json(root, f"{rel}/{attempt_rel}"))
    assert docker_commands >= 4, "scorekeeper did not record docker commands"

    ledger_path = root / rel / "subagent-ledger.sqlite"
    if not ledger_path.is_file():
        raise AssertionError(f"missing ledger: {rel}/subagent-ledger.sqlite")
    with sqlite3.connect(ledger_path) as conn:
        event_count = conn.execute("select count(*) from events").fetchone()[0]
    assert event_count >= 6, f"subagent ledger event count too small: {event_count}"

    return {
        "run": run,
        "red": red,
        "blue": blue,
        "scorekeeper": scorekeeper,
        "warm_pond": warm_pond,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_dir", type=Path)
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--min-red-workers", type=int, default=2)
    parser.add_argument("--min-blue-workers", type=int, default=2)
    args = parser.parse_args()

    root = args.artifact_dir.resolve()
    run = load_json(root, "run-receipt.json")
    multi = load_json(root, "multi-round-receipt.json")
    monitor = load_json(root, "monitor-index.json")

    assert run["schema"] == "battle.multiround_run_receipt.v1", run
    assert multi["schema"] == "battle.multiround_run_receipt.v1", multi
    assert run["status"] == "PASS", run
    assert run["verdict"] == "BLUE_SUCCESS", run
    assert run["execution"]["live"] == "docker_multiround_memory_feedback", run
    assert run["execution"]["multi_round"] is True, run
    assert run["execution"]["memory_feedback"] is True, run
    assert run["round_count"] == args.rounds, run
    assert len(run["rounds"]) == args.rounds, run
    assert run["true_recall_ok"] is True, run
    assert run["memory_influenced_round_count"] >= 1, run
    assert run["negative_evidence_count"] >= 1, run

    round_artifacts = []
    for index in range(1, args.rounds + 1):
        rel = f"rounds/round-{index:03d}"
        round_summary = load_json(root, f"rounds/round-{index:03d}-summary.json")
        assert round_summary["status"] == "PASS", round_summary
        assert round_summary["promoted_combination_ids"], round_summary
        assert round_summary["negative_combination_ids"], round_summary
        round_artifacts.append(
            validate_operational_round(
                root=root,
                rel=rel,
                min_red_workers=args.min_red_workers,
                min_blue_workers=args.min_blue_workers,
            )
        )

    recall = load_json(root, "round-feedback/round-002-memory-recall-receipt.json")
    negative = load_json(root, "round-feedback/negative-evidence-receipt.json")
    assert recall["schema"] == "battle.round_feedback_recall_receipt.v1", recall
    assert recall["status"] == "PASS", recall
    assert recall["endpoint"] == "/recall", recall
    assert recall["collection"] == "lessons", recall
    assert recall["found"] is True, recall
    assert recall["exact_token_match"] is True, recall
    assert recall["matching_item_count"] >= 1, recall
    assert recall["item_count"] >= 1, recall
    assert "fallback" not in recall, recall
    assert recall["feedback"]["promoted_combination_ids"], recall
    assert recall["feedback"]["negative_combination_ids"], recall
    assert negative["schema"] == "battle.negative_evidence_receipt.v1", negative
    assert negative["status"] == "PASS", negative
    assert negative["negative_evidence_count"] == run["negative_evidence_count"], negative
    assert negative["records"], negative

    round_two_warm_pond = round_artifacts[1]["warm_pond"]
    assert round_two_warm_pond["previous_round_feedback"]["provided"] is True, round_two_warm_pond
    assert round_two_warm_pond["previous_round_memory_weighted_combination_count"] >= 1, round_two_warm_pond
    assert any(
        item.get("previous_round_memory_influenced")
        for item in round_two_warm_pond["combinations"]
    ), round_two_warm_pond

    store_one = load_json(root, "round-feedback/round-001-memory-store-receipt.json")
    store_two = load_json(root, "round-feedback/round-002-memory-store-receipt.json")
    assert store_one["status"] == "PASS", store_one
    assert store_two["status"] == "PASS", store_two
    assert store_one["collection"] == "lessons", store_one
    assert store_two["collection"] == "lessons", store_two

    assert monitor["schema"] == "battle.monitor_index.v1", monitor
    assert monitor["status"] == "PASS", monitor
    assert monitor["scoreboard"] == "run-receipt.json", monitor

    for json_path in root.rglob("*.json"):
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            if json_path.name.endswith(".stdout.json"):
                continue
            raise
        assert_no_host_target_execution(payload)

    print("BATTLE_V1_MULTIRound_ACCEPTANCE_PASS".upper())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
