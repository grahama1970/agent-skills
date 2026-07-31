"""Cleanup-selected lane for running ingest-code and preserving local receipts."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from cleanup_evidence import scan_cleanup_evidence_artifact, scan_ingest_code_evidence


DEFAULT_MEMORY_INDEX_RECEIPT = "artifacts/cleanup/memory-index-receipt.json"


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

    if runner is None:
        receipt = {
            "schema": "cleanup.memory_index.v1",
            "status": "blocked",
            "started_at": started,
            "completed_at": datetime.now().isoformat(),
            "repository_path": str(repo),
            "error": "ingest-code runner not found",
            "mutation": "no_cleanup_mutations",
        }
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        return {**receipt, "receipt_path": str(receipt_path)}

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
        "non_claims": [
            "This receipt does not prove any cleanup candidate is unused.",
            "Dry-run receipts do not prove Memory writes or code-symbol upserts.",
        ],
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return {**receipt, "receipt_path": str(receipt_path)}
