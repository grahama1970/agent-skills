#!/usr/bin/env python3
"""Validate a constrained loop-run.v1 receipt.

This receipt is intentionally not a project DAG schema. It describes one
artifact completion loop with optional read-only preflight fanout, one
write-capable producer lane, and a fresh read-only verifier.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any


RECEIPT_TYPE = "loop-run.v1"
NODE_MODES = {"read_only", "write"}
NODE_ROLES = {"explorer", "producer", "verifier"}
FINAL_CLAIMS = {"VERIFIER_PASS", "NEEDS_CHANGES", "BLOCKED", "MAX_ATTEMPTS"}
STOP_REASONS = {
    "VERIFIER_PASS",
    "VERIFIER_BLOCKED",
    "MAX_ATTEMPTS",
    "SCOPE_UNCLEAR",
    "VALIDATION_FAILED",
    "HUMAN_DECISION",
}
CLAIM_STOP_REASONS = {
    "VERIFIER_PASS": {"VERIFIER_PASS"},
    "NEEDS_CHANGES": {"VALIDATION_FAILED"},
    "BLOCKED": {"VERIFIER_BLOCKED", "SCOPE_UNCLEAR", "HUMAN_DECISION"},
    "MAX_ATTEMPTS": {"MAX_ATTEMPTS"},
}
REQUIRED_ROOT_KEYS = {
    "receipt_type",
    "loop_id",
    "objective",
    "artifact",
    "max_attempts",
    "attempts_used",
    "nodes",
    "node_receipts",
    "checks_run",
    "final_claim",
    "stop_reason",
    "remaining_risks",
}


def require_type(errors: list[str], obj: Any, key: str, expected: type, ctx: str) -> Any:
    if not isinstance(obj, dict) or key not in obj:
        errors.append(f"{ctx}: missing required key {key!r}")
        return None
    value = obj[key]
    if not isinstance(value, expected):
        errors.append(f"{ctx}.{key}: expected {expected.__name__}, got {type(value).__name__}")
        return None
    return value


def string_list(errors: list[str], obj: dict[str, Any], key: str, ctx: str) -> list[str]:
    value = require_type(errors, obj, key, list, ctx)
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for idx, item in enumerate(value):
        if not isinstance(item, str) or item == "":
            errors.append(f"{ctx}.{key}[{idx}]: expected non-empty string")
        else:
            out.append(item)
    return out


def validate_receipt(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in sorted(REQUIRED_ROOT_KEYS):
        if key not in data:
            errors.append(f"receipt: missing required key {key!r}")

    receipt_type = require_type(errors, data, "receipt_type", str, "receipt")
    loop_id = require_type(errors, data, "loop_id", str, "receipt")
    objective = require_type(errors, data, "objective", str, "receipt")
    artifact = require_type(errors, data, "artifact", dict, "receipt")
    max_attempts = require_type(errors, data, "max_attempts", int, "receipt")
    attempts_used = require_type(errors, data, "attempts_used", int, "receipt")
    nodes = require_type(errors, data, "nodes", list, "receipt")
    node_receipts = require_type(errors, data, "node_receipts", list, "receipt")
    require_type(errors, data, "checks_run", list, "receipt")
    final_claim = require_type(errors, data, "final_claim", str, "receipt")
    stop_reason = require_type(errors, data, "stop_reason", str, "receipt")
    require_type(errors, data, "remaining_risks", list, "receipt")

    if receipt_type != RECEIPT_TYPE:
        errors.append(f"receipt.receipt_type: expected {RECEIPT_TYPE!r}")
    if loop_id == "":
        errors.append("receipt.loop_id: must not be empty")
    if objective == "":
        errors.append("receipt.objective: must not be empty")
    if isinstance(max_attempts, int) and max_attempts < 1:
        errors.append("receipt.max_attempts: must be >= 1")
    if isinstance(attempts_used, int) and attempts_used < 0:
        errors.append("receipt.attempts_used: must be >= 0")
    if isinstance(max_attempts, int) and isinstance(attempts_used, int) and attempts_used > max_attempts:
        errors.append("receipt.attempts_used: must not exceed max_attempts")
    if isinstance(final_claim, str) and final_claim not in FINAL_CLAIMS:
        errors.append(f"receipt.final_claim: must be one of {sorted(FINAL_CLAIMS)}")
    if isinstance(stop_reason, str) and stop_reason not in STOP_REASONS:
        errors.append(f"receipt.stop_reason: must be one of {sorted(STOP_REASONS)}")
    if isinstance(final_claim, str) and isinstance(stop_reason, str):
        allowed = CLAIM_STOP_REASONS.get(final_claim, set())
        if allowed and stop_reason not in allowed:
            errors.append(f"receipt.stop_reason: {final_claim} requires one of {sorted(allowed)}")

    if isinstance(artifact, dict):
        kind = require_type(errors, artifact, "kind", str, "receipt.artifact")
        paths = string_list(errors, artifact, "paths", "receipt.artifact")
        if kind == "":
            errors.append("receipt.artifact.kind: must not be empty")
        if len(paths) == 0:
            errors.append("receipt.artifact.paths: one artifact path is required")
        if len(paths) > 5:
            errors.append("receipt.artifact.paths: loop-run.v1 is limited to one artifact slot, not a project DAG")

    node_by_id: dict[str, dict[str, Any]] = {}
    write_nodes: list[str] = []
    verifier_nodes: list[str] = []
    producer_nodes: list[str] = []
    if isinstance(nodes, list):
        for idx, node in enumerate(nodes):
            ctx = f"receipt.nodes[{idx}]"
            if not isinstance(node, dict):
                errors.append(f"{ctx}: expected object")
                continue
            node_id = require_type(errors, node, "id", str, ctx)
            require_type(errors, node, "agent", str, ctx)
            role = require_type(errors, node, "role", str, ctx)
            mode = require_type(errors, node, "mode", str, ctx)
            depends_on = string_list(errors, node, "depends_on", ctx)
            if isinstance(node_id, str):
                if node_id == "":
                    errors.append(f"{ctx}.id: must not be empty")
                elif node_id in node_by_id:
                    errors.append(f"{ctx}.id: duplicate node id {node_id!r}")
                else:
                    node_by_id[node_id] = node
            if isinstance(role, str) and role not in NODE_ROLES:
                errors.append(f"{ctx}.role: must be one of {sorted(NODE_ROLES)}")
            if isinstance(mode, str) and mode not in NODE_MODES:
                errors.append(f"{ctx}.mode: must be one of {sorted(NODE_MODES)}")
            if role == "verifier":
                verifier_nodes.append(str(node_id))
                if mode != "read_only":
                    errors.append(f"{ctx}.mode: verifier must be read_only")
            if role == "producer":
                producer_nodes.append(str(node_id))
                if mode != "write":
                    errors.append(f"{ctx}.mode: producer must be write")
            if mode == "write":
                write_nodes.append(str(node_id))
            if role == "explorer" and mode != "read_only":
                errors.append(f"{ctx}.mode: explorer must be read_only")
            for dep in depends_on:
                if dep not in node_by_id and isinstance(nodes, list):
                    # Forward references are checked after all nodes are known.
                    pass

    for idx, node in enumerate(nodes if isinstance(nodes, list) else []):
        if not isinstance(node, dict):
            continue
        for dep in node.get("depends_on", []):
            if dep not in node_by_id:
                errors.append(f"receipt.nodes[{idx}].depends_on: unknown node id {dep!r}")
            if dep == node.get("id"):
                errors.append(f"receipt.nodes[{idx}].depends_on: node cannot depend on itself")

    if len(producer_nodes) > 1:
        errors.append("receipt.nodes: loop-run.v1 allows at most one write-capable producer lane")
    if len(write_nodes) > 1:
        errors.append("receipt.nodes: multiple write nodes belong in an outer orchestrator, not $loop")
    if final_claim == "VERIFIER_PASS" and not verifier_nodes:
        errors.append("receipt.nodes: VERIFIER_PASS requires a verifier node")

    receipt_by_node: dict[str, dict[str, Any]] = {}
    if isinstance(node_receipts, list):
        for idx, receipt in enumerate(node_receipts):
            ctx = f"receipt.node_receipts[{idx}]"
            if not isinstance(receipt, dict):
                errors.append(f"{ctx}: expected object")
                continue
            node_id = require_type(errors, receipt, "node_id", str, ctx)
            status = require_type(errors, receipt, "status", str, ctx)
            edited = require_type(errors, receipt, "edited_files", list, ctx)
            if isinstance(node_id, str):
                if node_id not in node_by_id:
                    errors.append(f"{ctx}.node_id: unknown node id {node_id!r}")
                receipt_by_node[node_id] = receipt
            if isinstance(status, str) and status not in {"PASS", "NEEDS_CHANGES", "BLOCKED", "COMPLETED"}:
                errors.append(f"{ctx}.status: invalid status {status!r}")
            if isinstance(edited, list) and not all(isinstance(item, str) for item in edited):
                errors.append(f"{ctx}.edited_files: all entries must be strings")

    for node_id, node in node_by_id.items():
        receipt = receipt_by_node.get(node_id)
        if receipt is None:
            errors.append(f"receipt.node_receipts: missing receipt for node {node_id!r}")
            continue
        if node.get("mode") == "read_only" and receipt.get("edited_files"):
            errors.append(f"receipt.node_receipts[{node_id}].edited_files: read-only nodes must report []")

    if final_claim == "VERIFIER_PASS":
        verifier_pass = False
        for verifier_id in verifier_nodes:
            receipt = receipt_by_node.get(verifier_id, {})
            if receipt.get("status") == "PASS" or receipt.get("verdict") == "PASS":
                verifier_pass = True
        if not verifier_pass:
            errors.append("receipt.final_claim: VERIFIER_PASS requires a verifier node receipt with PASS")

    if final_claim == "MAX_ATTEMPTS" and attempts_used != max_attempts:
        errors.append("receipt.final_claim: MAX_ATTEMPTS requires attempts_used == max_attempts")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a constrained loop-run.v1 receipt JSON file.")
    parser.add_argument("receipt", help="Path to loop-run.v1 receipt JSON")
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    try:
        data = json.loads(open(args.receipt, encoding="utf-8").read())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"LOOP-RUN RECEIPT INVALID: {exc}", file=sys.stderr)
        return 2
    if not isinstance(data, dict):
        print("LOOP-RUN RECEIPT INVALID: root must be a JSON object", file=sys.stderr)
        return 2

    errors = validate_receipt(data)
    if errors:
        print("LOOP-RUN RECEIPT INVALID", file=sys.stderr)
        for err in errors:
            print(f"- {err}", file=sys.stderr)
        return 1

    if args.print_summary:
        print(
            "LOOP-RUN RECEIPT VALID "
            f"loop_id={data['loop_id']} final_claim={data['final_claim']} stop_reason={data['stop_reason']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
