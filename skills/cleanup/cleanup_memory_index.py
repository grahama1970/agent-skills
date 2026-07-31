"""Cleanup-selected lane for running ingest-code and preserving local receipts."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from cleanup_evidence import scan_cleanup_evidence_artifact, scan_ingest_code_evidence
from cleanup_memory_gate import evaluate_memory_mutation_gate


DEFAULT_MEMORY_INDEX_RECEIPT = "artifacts/cleanup/memory-index-receipt.json"
DEFAULT_PHASE_RECEIPT = "artifacts/cleanup/cleanup_receipt.json"


def update_phase_receipt_for_memory_index(
    lane_receipt: Dict[str, Any],
    phase_receipt_path: str | Path = DEFAULT_PHASE_RECEIPT,
) -> Path:
    """Record the memory-index lane outcome in the resumable phase receipt.

    Merges into an existing receipt when present so the lane never clobbers
    assessment state; the gate's cited backup/health receipt paths land here.
    """
    path = Path(phase_receipt_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    receipt: Dict[str, Any] = {}
    if path.exists():
        try:
            receipt = json.loads(path.read_text())
        except Exception:
            receipt = {}
    receipt.setdefault("contract", "cleanup.phase_receipt.v1")
    receipt.setdefault("repository_path", str(Path.cwd().resolve()))
    receipt.setdefault("phases", {})
    status = lane_receipt.get("status")
    receipt["phases"]["memory_indexing"] = (
        "complete" if status == "passed" else "blocked" if status == "blocked" else "unknown"
    )
    gate = lane_receipt.get("memory_mutation_gate", {})
    receipt["memory_index"] = {
        "status": status,
        "receipt_path": lane_receipt.get("receipt_path"),
        "blockers": lane_receipt.get("blockers", []),
        "backup_receipt_path": (gate.get("backup") or {}).get("receipt_path"),
        "health_receipt_path": (gate.get("health") or {}).get("receipt_path"),
    }
    receipt["generated_at"] = datetime.now().isoformat()
    path.write_text(json.dumps(receipt, indent=2, default=str))
    return path


def find_ingest_code_runner() -> Path | None:
    """Find the local ingest-code runner without assuming a Memory service path."""
    skill_dir = Path(__file__).resolve().parent
    candidates = [
        Path.cwd() / ".pi" / "skills" / "ingest-code" / "run.sh",
        skill_dir.parent / "ingest-code" / "run.sh",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def build_ingest_code_command(runner: Path, repo: Path, *, dry_run: bool) -> List[str]:
    """Build the canonical code-indexing command used by cleanup."""
    command = ["bash", str(runner), "scan", str(repo), "--treesitter"]
    if dry_run:
        command.append("--dry-run")
    return command


def _tail(text: str, limit: int = 6000) -> str:
    return text[-limit:] if len(text) > limit else text


def memory_index_receipt_path(output: str) -> Path:
    """Resolve receipt path, keeping CLEANUP_PLAN.md from becoming JSON."""
    if output and output != "CLEANUP_PLAN.md":
        return Path(output)
    return Path(DEFAULT_MEMORY_INDEX_RECEIPT)


def run_memory_indexing(*, dry_run: bool, output: str, timeout_seconds: int = 1800) -> Dict[str, Any]:
    """Run ingest-code for Memory-backed search and local fallback artifacts."""
    repo = Path.cwd().resolve()
    runner = find_ingest_code_runner()
    receipt_path = memory_index_receipt_path(output)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    started = datetime.now().isoformat()

    # Pre-mutation gate (#1125): consume the ops-arango backup receipt and the
    # owning monitor's health receipt before any memory-mutating run. Enforced
    # only for non-dry runs; dry runs record the gate verdict as evidence.
    gate = evaluate_memory_mutation_gate()
    if not dry_run and not gate["allowed"]:
        receipt = {
            "schema": "cleanup.memory_index.v1",
            "status": "blocked",
            "memory_indexing": "blocked",
            "started_at": started,
            "completed_at": datetime.now().isoformat(),
            "repository_path": str(repo),
            "blockers": gate["blockers"],
            "memory_mutation_gate": gate,
            "ingest_invoked": False,
            "mutation": "no_cleanup_mutations",
        }
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        result = {**receipt, "receipt_path": str(receipt_path)}
        update_phase_receipt_for_memory_index(result)
        return result

    if runner is None:
        receipt = {
            "schema": "cleanup.memory_index.v1",
            "status": "blocked",
            "started_at": started,
            "completed_at": datetime.now().isoformat(),
            "repository_path": str(repo),
            "error": "ingest-code runner not found",
            "mutation": "no_cleanup_mutations",
            "memory_mutation_gate": gate,
            "ingest_invoked": False,
        }
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        result = {**receipt, "receipt_path": str(receipt_path)}
        update_phase_receipt_for_memory_index(result)
        return result

    command = build_ingest_code_command(runner, repo, dry_run=dry_run)
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        status = "passed" if result.returncode == 0 else "failed"
        error = ""
    except subprocess.TimeoutExpired as exc:
        result = exc
        status = "failed"
        error = "ingest-code command timed out"

    marker = scan_ingest_code_evidence()
    cleanup_evidence = scan_cleanup_evidence_artifact()
    receipt = {
        "schema": "cleanup.memory_index.v1",
        "status": status,
        "started_at": started,
        "completed_at": datetime.now().isoformat(),
        "repository_path": str(repo),
        "command": command,
        "dry_run": dry_run,
        "exit_code": getattr(result, "returncode", None),
        "stdout_tail": _tail(getattr(result, "stdout", "") or ""),
        "stderr_tail": _tail(getattr(result, "stderr", "") or ""),
        "error": error,
        "ingest_marker": marker,
        "cleanup_evidence_artifact": cleanup_evidence,
        "local_artifacts": {
            "ingest_marker": marker.get("marker_path"),
            "cleanup_evidence": cleanup_evidence.get("artifact_path"),
            "code_symbols_jsonl": (
                marker.get("local_artifacts", {}).get("code_symbols_jsonl")
                if isinstance(marker.get("local_artifacts"), dict) else None
            ),
        },
        "mutation": "no_cleanup_mutations",
        "memory_mutation_gate": gate,
        "ingest_invoked": True,
        "non_claims": [
            "This receipt does not prove any cleanup candidate is unused.",
            "Dry-run receipts do not prove Memory writes or code-symbol upserts.",
        ],
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    result = {**receipt, "receipt_path": str(receipt_path)}
    update_phase_receipt_for_memory_index(result)
    return result
