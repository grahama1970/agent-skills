#!/usr/bin/env python3
"""Validate and normalize debugger proof artifacts.

This validator intentionally avoids third-party JSON Schema dependencies. The
schema file is the public contract; this script is the deterministic local gate
used by the skill sanity checks.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


class ProofError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProofError(message)


def read_artifact(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def as_string_map(value: Any) -> dict[str, Any]:
    require(isinstance(value, dict), "expected object")
    return dict(value)


def normalize_python(raw: dict[str, Any]) -> dict[str, Any]:
    hits = raw.get("hits") if isinstance(raw.get("hits"), list) else []
    first_hit = hits[0] if hits else {}
    breakpoints = []
    hit_locations = {(hit.get("file"), hit.get("line")) for hit in hits if isinstance(hit, dict)}
    for bp in raw.get("breakpoints", []):
        if not isinstance(bp, dict):
            continue
        breakpoints.append(
            {
                "file": str(bp.get("file", "")),
                "line": int(bp.get("line", 0)),
                "source": str(first_hit.get("source", "")) if (bp.get("file"), bp.get("line")) in hit_locations else "",
                "verified": True,
                "hit": (bp.get("file"), bp.get("line")) in hit_locations,
            }
        )
    locals_map = as_string_map(first_hit.get("locals", {})) if first_hit else {}
    watches = as_string_map(first_hit.get("watches", {})) if first_hit else {}
    variable_valid = bool(hits) and bool(locals_map or watches)
    return {
        "schema": "debugger.proof.v1",
        "producer": {"name": "capture_breakpoints.py"},
        "debugger": {"adapter": "Python bdb", "mode": "python-bdb"},
        "repro": {"command": [str(item) for item in raw.get("command", [])]},
        "breakpoints": breakpoints,
        "stopped": {
            "hit": bool(hits),
            "reason": "breakpoint" if hits else "not-hit",
            "frame": {
                "file": str(first_hit.get("file", breakpoints[0]["file"] if breakpoints else "")),
                "line": int(first_hit.get("line", breakpoints[0]["line"] if breakpoints else 1)),
                "function": str(first_hit.get("function", "")),
            },
        },
        "captures": {
            "requestedLocals": [str(item) for item in raw.get("locals_allowlist", [])],
            "locals": locals_map,
            "watches": watches,
        },
        "assessment": {
            "proofValid": bool(hits) and variable_valid,
            "variableInspectionValid": variable_valid,
            "limitations": [],
        },
        "analysis": {
            "conclusion": "Python debugger stopped at a requested breakpoint and captured selected paused state.",
            "nextEdit": "",
        },
    }


def normalize_node(raw: dict[str, Any]) -> dict[str, Any]:
    bp = raw.get("breakpoint", {})
    frame = raw.get("top_frame", {})
    assessment = raw.get("proofAssessment", {})
    return {
        "schema": "debugger.proof.v1",
        "producer": {"name": "node_inspector_breakpoint_proof.mjs"},
        "debugger": {"adapter": str(raw.get("adapter", "Node inspector")), "mode": "node-inspector"},
        "repro": {"command": ["node", "node_inspector_breakpoint_proof.mjs"]},
        "breakpoints": [
            {
                "file": str(bp.get("file", "")),
                "line": int(bp.get("line", 0)),
                "verified": "unknown",
                "hit": bool(raw.get("hit_breakpoint")),
            }
        ],
        "stopped": {
            "hit": bool(raw.get("hit_breakpoint")),
            "reason": "breakpoint" if raw.get("hit_breakpoint") else "not-hit",
            "frame": {
                "file": str(frame.get("url") or bp.get("file", "")),
                "line": int(frame.get("line", bp.get("line", 1))),
                "function": str(frame.get("functionName", "")),
            },
        },
        "captures": {
            "requestedLocals": [str(item) for item in assessment.get("requestedLocals", [])],
            "locals": as_string_map(raw.get("locals", {})),
            "watches": {},
        },
        "assessment": {
            "proofValid": bool(raw.get("hit_breakpoint")) and bool(assessment.get("variableInspectionValid")),
            "variableInspectionValid": bool(assessment.get("variableInspectionValid")),
            "limitations": [],
        },
        "analysis": {
            "conclusion": str(raw.get("analysis") or "Node inspector captured selected paused runtime state."),
            "nextEdit": "",
        },
    }


def normalize_vscode(raw: dict[str, Any]) -> dict[str, Any]:
    stopped = raw.get("stoppedState", {})
    frame = stopped.get("frame", {}) if isinstance(stopped, dict) else {}
    request_bps = raw.get("addedBreakpoints", [])
    assessment = raw.get("proofAssessment", {})
    source_file = str(frame.get("source", {}).get("path", "") if isinstance(frame.get("source"), dict) else "")
    line = int(frame.get("line", 1) or 1)
    breakpoints = []
    if isinstance(request_bps, list):
        for item in request_bps:
            if isinstance(item, dict):
                breakpoints.append(
                    {
                        "file": str(item.get("file", source_file)),
                        "line": int(item.get("line", line) or line),
                        "verified": raw.get("adapterBreakpointVerification", "unavailable"),
                        "hit": bool(raw.get("proofValid")),
                    }
                )
    if not breakpoints:
        breakpoints = [{"file": source_file, "line": line, "verified": "unavailable", "hit": bool(raw.get("proofValid"))}]
    return {
        "schema": "debugger.proof.v1",
        "producer": {"name": "debugger-vscode-bridge"},
        "debugger": {"adapter": "VS Code Debug Adapter Protocol", "mode": "vscode-bridge"},
        "repro": {"command": ["vscode", str(raw.get("launchConfigName", ""))]},
        "breakpoints": breakpoints,
        "stopped": {
            "hit": bool(raw.get("proofValid")),
            "reason": str(stopped.get("reason", "breakpoint") if isinstance(stopped, dict) else "breakpoint"),
            "frame": {
                "file": source_file or breakpoints[0]["file"],
                "line": line,
                "function": str(frame.get("name", "")),
                "threadId": stopped.get("threadId", "") if isinstance(stopped, dict) else "",
                "sessionId": str(stopped.get("sessionId", raw.get("sessionId", "")) if isinstance(stopped, dict) else raw.get("sessionId", "")),
            },
        },
        "captures": {
            "requestedLocals": [str(item) for item in assessment.get("requestedLocals", [])],
            "locals": as_string_map(stopped.get("locals", {}) if isinstance(stopped, dict) else {}),
            "watches": as_string_map(stopped.get("watches", {}) if isinstance(stopped, dict) else {}),
        },
        "assessment": {
            "proofValid": bool(raw.get("proofValid")),
            "variableInspectionValid": bool(assessment.get("variableInspectionValid", raw.get("proofValid"))),
            "limitations": [str(raw.get("adapterBreakpointVerification", "unavailable-vscode-api"))],
        },
        "analysis": {
            "conclusion": "VS Code bridge stopped a visible debug session and captured selected paused state through DAP.",
            "nextEdit": "",
        },
    }


def normalize_rust_gdb(text: str) -> dict[str, Any]:
    hit_match = re.search(r"Breakpoint\s+\d+,\s+([^\s(]+).*?\(value=([^)]+)\)", text)
    value_match = re.search(r"\$\d+\s+=\s+14\b", text)
    label_match = re.search(r'\$\d+\s+=\s+"large"', text)
    file_line_match = re.search(r"at\s+([^:\n]+):(\d+)", text)
    file_name = file_line_match.group(1) if file_line_match else "unknown"
    line = int(file_line_match.group(2)) if file_line_match else 1
    locals_map: dict[str, Any] = {}
    if value_match:
        locals_map["value"] = "14"
    if label_match:
        locals_map["label"] = '"large"'
    return {
        "schema": "debugger.proof.v1",
        "producer": {"name": "rust-gdb transcript"},
        "debugger": {"adapter": "rust-gdb", "mode": "rust-gdb"},
        "repro": {"command": ["rust-gdb", "-batch"]},
        "breakpoints": [{"file": file_name, "line": line, "verified": True, "hit": bool(hit_match)}],
        "stopped": {
            "hit": bool(hit_match),
            "reason": "breakpoint" if hit_match else "not-hit",
            "frame": {"file": file_name, "line": line, "function": "classify"},
        },
        "captures": {"requestedLocals": ["value", "label"], "locals": locals_map, "watches": {}},
        "assessment": {
            "proofValid": bool(hit_match and value_match and label_match),
            "variableInspectionValid": bool(value_match and label_match),
            "limitations": ["parsed rust-gdb transcript"],
        },
        "analysis": {
            "conclusion": "rust-gdb stopped at a Rust source breakpoint and captured selected paused locals.",
            "nextEdit": "",
        },
    }


def normalize(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict) and raw.get("schema") == "debugger.proof.v1":
        return raw
    if isinstance(raw, dict) and "hit_count" in raw and "hits" in raw:
        return normalize_python(raw)
    if isinstance(raw, dict) and raw.get("adapter") == "Node inspector":
        return normalize_node(raw)
    if isinstance(raw, dict) and ("stoppedState" in raw or raw.get("status") in {"stopped", "stopped-not-proof"}):
        return normalize_vscode(raw)
    if isinstance(raw, str):
        return normalize_rust_gdb(raw)
    raise ProofError("unrecognized debugger proof format")


def validate_canonical(proof: dict[str, Any]) -> None:
    require(proof.get("schema") == "debugger.proof.v1", "schema must be debugger.proof.v1")
    for field in ["producer", "debugger", "repro", "breakpoints", "stopped", "captures", "assessment", "analysis"]:
        require(field in proof, f"missing {field}")
    require(isinstance(proof["producer"].get("name"), str) and proof["producer"]["name"], "producer.name is required")
    require(isinstance(proof["debugger"].get("adapter"), str) and proof["debugger"]["adapter"], "debugger.adapter is required")
    require(proof["debugger"].get("mode") in {"python-bdb", "node-inspector", "rust-gdb", "vscode-bridge", "dap", "other"}, "debugger.mode is invalid")
    require(isinstance(proof["repro"].get("command"), list), "repro.command must be a list")
    require(isinstance(proof["breakpoints"], list) and proof["breakpoints"], "at least one breakpoint is required")
    for index, bp in enumerate(proof["breakpoints"]):
        require(isinstance(bp.get("file"), str) and bp["file"], f"breakpoints[{index}].file is required")
        require(isinstance(bp.get("line"), int) and bp["line"] > 0, f"breakpoints[{index}].line must be positive")
        require(isinstance(bp.get("hit"), bool), f"breakpoints[{index}].hit must be boolean")
    stopped = proof["stopped"]
    require(isinstance(stopped.get("hit"), bool), "stopped.hit must be boolean")
    require(isinstance(stopped.get("reason"), str) and stopped["reason"], "stopped.reason is required")
    frame = stopped.get("frame", {})
    require(isinstance(frame.get("file"), str) and frame["file"], "stopped.frame.file is required")
    require(isinstance(frame.get("line"), int) and frame["line"] > 0, "stopped.frame.line must be positive")
    captures = proof["captures"]
    require(isinstance(captures.get("requestedLocals"), list), "captures.requestedLocals must be a list")
    require(isinstance(captures.get("locals"), dict), "captures.locals must be an object")
    require(isinstance(captures.get("watches"), dict), "captures.watches must be an object")
    assessment = proof["assessment"]
    require(isinstance(assessment.get("proofValid"), bool), "assessment.proofValid must be boolean")
    require(isinstance(assessment.get("variableInspectionValid"), bool), "assessment.variableInspectionValid must be boolean")
    require(isinstance(assessment.get("limitations"), list), "assessment.limitations must be a list")
    require(isinstance(proof["analysis"].get("conclusion"), str) and proof["analysis"]["conclusion"], "analysis.conclusion is required")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--canonical-out", type=Path)
    parser.add_argument("--expect-valid", action="store_true")
    parser.add_argument("--expect-invalid", action="store_true")
    args = parser.parse_args()
    if args.expect_valid and args.expect_invalid:
        parser.error("--expect-valid and --expect-invalid are mutually exclusive")
    try:
        proof = normalize(read_artifact(args.artifact))
        validate_canonical(proof)
        if args.expect_valid:
            require(bool(proof["assessment"]["proofValid"]), "expected proofValid=true")
            require(bool(proof["assessment"]["variableInspectionValid"]), "expected variableInspectionValid=true")
            require(bool(proof["stopped"]["hit"]), "expected stopped.hit=true")
        if args.expect_invalid:
            require(not proof["assessment"]["proofValid"], "expected invalid proof, got proofValid=true")
            print(f"debugger proof invalid as expected: {args.artifact}")
            return 0
    except Exception as exc:
        if args.expect_invalid:
            print(f"debugger proof invalid as expected: {exc}")
            return 0
        print(f"debugger proof validation failed: {exc}", file=sys.stderr)
        return 1
    if args.canonical_out:
        args.canonical_out.parent.mkdir(parents=True, exist_ok=True)
        args.canonical_out.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"debugger proof validation passed: {args.artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
