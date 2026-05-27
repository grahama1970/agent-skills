#!/usr/bin/env python3
"""Distill debugger proof into a redacted advisory lesson.

Inputs are canonical `debugger.proof.v1` JSON artifacts. Output is a
`debugger.lesson.v1` JSON artifact that preserves breakpoint/frame/capture shape
but removes raw paused values, secrets, and machine-local paths. Invalid proof
or leaked sensitive content fails closed.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import typer
from loguru import logger


app = typer.Typer(add_completion=False)

SENSITIVE_KEY_RE = re.compile(
    r"(token|secret|password|passwd|api[_-]?key|authorization|cookie|session|credential|private[_-]?key|refresh|bearer|jwt)",
    re.IGNORECASE,
)
SENSITIVE_VALUE_RE = re.compile(
    r"(Bearer\s+[A-Za-z0-9._~+/=-]+|sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,}|xox[baprs]-[A-Za-z0-9-]{12,}|eyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{8,})",
    re.IGNORECASE,
)
LOCAL_PATH_RE = re.compile(r"(/(?:home|tmp|var|mnt|workspace|Users)/[^\s\"']+)")


class LessonError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise LessonError(message)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    require(isinstance(data, dict), "proof must be a JSON object")
    return data, sha256_bytes(raw)


def value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def redact_text(text: str) -> str:
    text = SENSITIVE_VALUE_RE.sub("<redacted-secret>", text)
    text = LOCAL_PATH_RE.sub("<redacted-path>", text)
    return text


def summarize_capture_map(values: dict[str, Any]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for key in sorted(values):
        sensitive_key = bool(SENSITIVE_KEY_RE.search(key))
        value = values[key]
        item: dict[str, Any] = {
            "name": key,
            "type": value_type(value),
            "redacted": True,
        }
        if sensitive_key:
            item["reason"] = "sensitive-key"
        elif isinstance(value, (str, int, float, bool)) or value is None:
            item["reason"] = "raw-paused-value"
        elif isinstance(value, dict):
            item["reason"] = "object-shape-only"
            item["keys"] = sorted(str(inner_key) for inner_key in value.keys())[:25]
        elif isinstance(value, list):
            item["reason"] = "array-shape-only"
            item["length"] = len(value)
        else:
            item["reason"] = "unsupported-value"
        summary.append(item)
    return summary


def relative_location(path_text: str) -> str:
    text = redact_text(path_text)
    if text == "<redacted-path>":
        return text
    return Path(path_text).name if path_text.startswith("/") else path_text


def distill(proof: dict[str, Any], source_sha256: str) -> dict[str, Any]:
    require(proof.get("schema") == "debugger.proof.v1", "proof schema must be debugger.proof.v1")
    assessment = proof.get("assessment", {})
    require(bool(assessment.get("proofValid")), "cannot distill lesson from invalid debugger proof")
    require(bool(assessment.get("variableInspectionValid")), "cannot distill lesson without variable inspection proof")

    stopped = proof.get("stopped", {})
    frame = stopped.get("frame", {}) if isinstance(stopped, dict) else {}
    captures = proof.get("captures", {})
    locals_map = captures.get("locals", {}) if isinstance(captures, dict) else {}
    watches_map = captures.get("watches", {}) if isinstance(captures, dict) else {}
    require(isinstance(locals_map, dict), "captures.locals must be an object")
    require(isinstance(watches_map, dict), "captures.watches must be an object")

    breakpoints = []
    for bp in proof.get("breakpoints", []):
        if isinstance(bp, dict):
            breakpoints.append(
                {
                    "file": relative_location(str(bp.get("file", ""))),
                    "line": bp.get("line"),
                    "hit": bool(bp.get("hit")),
                    "verified": bp.get("verified", "unknown"),
                }
            )

    return {
        "schema": "debugger.lesson.v1",
        "source": {
            "proof_schema": "debugger.proof.v1",
            "proof_sha256": source_sha256,
            "producer": proof.get("producer", {}),
            "debugger": proof.get("debugger", {}),
        },
        "runtime_state": {
            "breakpoints": breakpoints,
            "stopped": {
                "hit": bool(stopped.get("hit")),
                "reason": redact_text(str(stopped.get("reason", ""))),
                "frame": {
                    "file": relative_location(str(frame.get("file", ""))),
                    "line": frame.get("line"),
                    "function": redact_text(str(frame.get("function", ""))),
                },
            },
            "captures": {
                "requested_locals": [str(item) for item in captures.get("requestedLocals", [])],
                "locals": summarize_capture_map(locals_map),
                "watches": summarize_capture_map(watches_map),
            },
        },
        "lesson": {
            "conclusion": redact_text(str(proof.get("analysis", {}).get("conclusion", ""))),
            "next_edit": redact_text(str(proof.get("analysis", {}).get("nextEdit", ""))),
            "limitations": [redact_text(str(item)) for item in assessment.get("limitations", [])],
        },
        "memory_safety": {
            "evidence_class": "redacted_debugger_lesson",
            "raw_locals_stored": False,
            "raw_watches_stored": False,
            "fresh_debugger_proof": False,
            "can_satisfy_debugger_proof": False,
        },
    }


def assert_no_secret_strings(lesson: dict[str, Any]) -> None:
    text = json.dumps(lesson, sort_keys=True)
    require(not SENSITIVE_VALUE_RE.search(text), "distilled lesson still contains a sensitive token pattern")
    require("/home/" not in text and "/tmp/" not in text and "/mnt/" not in text, "distilled lesson still contains local absolute paths")


@app.command()
def main(
    proof: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    out: Path = typer.Option(..., "--out", dir_okay=False, help="Path for the redacted debugger.lesson.v1 JSON artifact."),
) -> None:
    try:
        proof_data, source_sha256 = load_json(proof)
        lesson = distill(proof_data, source_sha256)
        assert_no_secret_strings(lesson)
    except Exception as exc:
        logger.error("debugger lesson distillation failed: {}", exc)
        raise typer.Exit(1) from exc

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(lesson, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    typer.echo(f"debugger lesson distillation passed: {out}")


if __name__ == "__main__":
    app()
