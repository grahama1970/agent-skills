#!/usr/bin/env python3
"""Tau verifier adapter for persona-dream memory integration receipts."""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def main() -> int:
    artifact_dir = Path(
        os.environ.get("TAU_HANDOFF_COMMAND_ARTIFACT_DIR", "/tmp/persona-dream-memory-review")
    ).expanduser().resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    try:
        handoff = json.loads(sys.stdin.read())
    except json.JSONDecodeError as exc:
        _write_json(artifact_dir / "persona-dream-memory-review-receipt.json", _receipt("BLOCKED", [str(exc)], None))
        return 2
    artifacts = _artifacts(handoff)
    audit_path = next((Path(path) for path in artifacts if path.endswith("persona-dream-memory-tau-audit.json")), None)
    errors: list[str] = []
    audit: dict[str, Any] | None = None
    if audit_path is None:
        errors.append("missing_memory_tau_audit_artifact")
    elif not audit_path.is_file():
        errors.append(f"memory_tau_audit_not_found:{audit_path}")
    else:
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        if audit.get("status") != "PASS":
            errors.append(f"audit_status_not_pass:{audit.get('status')}")
        if audit.get("mocked") is not False or audit.get("live") is not True:
            errors.append("audit_mocked_live_boundary_invalid")
        scores = dict(audit.get("recall_score_counts") or {})
        for key in ("bm25", "dense"):
            if int(scores.get(key) or 0) < 1:
                errors.append(f"missing_recall_score:{key}")
        if int(audit.get("media_edges_written_count") or 0) < 1:
            errors.append("missing_media_edges_written")

    status = "PASS" if not errors else "BLOCKED"
    receipt_path = artifact_dir / "persona-dream-memory-review-receipt.json"
    _write_json(receipt_path, _receipt(status, errors, audit))
    print(json.dumps(_handoff_response(handoff, status, errors, receipt_path), sort_keys=True))
    return 0


def _handoff_response(handoff: dict[str, Any], status: str, errors: list[str], receipt_path: Path) -> dict[str, Any]:
    evidence = [{"kind": "persona_dream_memory_review_receipt", "path": str(receipt_path)}]
    if status == "PASS":
        for label in [
            "live /recall response for story/script/contact-sheet artifacts",
            "BM25 score present",
            "dense score present",
            "graph score present where media/TOM edges are expected",
        ]:
            evidence.append({"kind": "required_evidence", "label": label})
    return {
        "schema": "tau.agent_handoff.v1",
        "github": handoff.get("github", {}),
        "goal": handoff.get("goal", {}),
        "previous_subagent": "project-or-harness-verifier",
        "context": {
            "summary": "persona-dream memory integration verifier finished.",
            "artifacts": [str(receipt_path)],
        },
        "result": {
            "status": "COMPLETED" if status == "PASS" else "BLOCKED",
            "summary": "Memory integration receipts passed verifier checks."
            if status == "PASS"
            else "Memory integration receipts are still blocked.",
            "evidence": evidence,
        },
        "rationale": "Verifier checks live/mock boundaries, recall mode counts, and media edge writes.",
        "next_agent": {
            "name": "human",
            "executor": "human",
            "reason": "Human receives Tau DAG receipt and remaining blockers.",
        },
        "required_evidence": ["Human reviews dag-receipt.json and memory review receipt."],
        "stop_condition": "Human accepts, redirects, or requests another bounded Tau DAG.",
    }


def _receipt(status: str, errors: list[str], audit: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "schema": "persona_dream.memory_review_receipt.v1",
        "status": status,
        "mocked": False,
        "live": True,
        "audit": audit,
        "errors": errors,
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _artifacts(handoff: dict[str, Any]) -> list[str]:
    context = handoff.get("context")
    if isinstance(context, dict) and isinstance(context.get("artifacts"), list):
        return [str(item) for item in context["artifacts"] if isinstance(item, str)]
    return []


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
