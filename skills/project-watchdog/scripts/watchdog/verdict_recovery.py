"""Deterministic verdict recovery for seat_verdict=None terminal runs (#1643).

When a terminal handler node reports seat_verdict=None, Tau's alert evidence
sometimes missed a VERDICT line that IS present in the handler's response bytes
(observed handler-claude-fable-5 / handler-codex, 2026-09-10). Discarding the
whole DAG run for a parser miss burned full runs.

This module performs the recovery deterministically and idempotently:

- read the exact handler response bytes and hash them (response_sha256);
- extract the verdict with the current parser (no LLM judge, no PASS inference
  from prose -- the original handler must have stated VERDICT: ...);
- emit a derived recovery receipt keyed by
  (tau_run_id, node_id, response_sha256, parser_version). The original node
  receipt is never rewritten;
- the key makes replay a no-op: a crash between persistence and receipt write
  is healed on the next pass without a second retry;
- multiple distinct VERDICT lines in one response are AMBIGUOUS and never
  recovered -- the run stays BLOCKED;
- when no VERDICT line exists at all (genuinely absent/truncated), recovery
  returns retry_eligible=True so the caller may retry that one handler node
  exactly once; the recovery layer itself never re-invokes a provider.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

PARSER_VERSION = "verdict-recovery.v1"
RECOVERY_SCHEMA = "agent_skills.project_watchdog.verdict_recovery.v1"
_VERDICT_RE = re.compile(r"VERDICT[:\s]+(PASS|FAIL|NEEDS_ATTENTION)", re.IGNORECASE)


def extract_verdicts(text: str) -> list[str]:
    """Every distinct VERDICT token the handler stated, in order of appearance."""
    seen: list[str] = []
    for match in _VERDICT_RE.finditer(text or ""):
        token = match.group(1).upper()
        if token not in seen:
            seen.append(token)
    return seen


def _tau_run_id(ask_run_dir: Path) -> str:
    for receipt in sorted(ask_run_dir.glob("**/tau-receipts/dag-receipt.json")):
        try:
            data = json.loads(receipt.read_text())
        except (OSError, ValueError):
            continue
        run = data.get("run_id") or data.get("plan_id")
        if run:
            return str(run)
    return ask_run_dir.name


def recover(ask_run_dir: Path) -> dict[str, Any]:
    """Recover seat verdicts from handler response bytes, idempotently.

    Returns a report with per-node recovery decisions. Writing the derived
    receipt is keyed, so calling recover twice produces the same receipt and
    no second action.
    """
    ask_run_dir = Path(ask_run_dir)
    run_id = _tau_run_id(ask_run_dir)
    out_dir = ask_run_dir / "verdict-recovery"
    report: dict[str, Any] = {
        "schema": RECOVERY_SCHEMA,
        "parser_version": PARSER_VERSION,
        "tau_run_id": run_id,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "nodes": [],
    }
    for response in sorted(ask_run_dir.glob("**/node-artifacts/*/response.md")):
        node_id = response.parent.name
        if node_id == "join":
            continue
        try:
            raw = response.read_bytes()
        except OSError:
            continue
        response_sha256 = hashlib.sha256(raw).hexdigest()
        verdicts = extract_verdicts(raw.decode("utf-8", errors="replace"))
        node: dict[str, Any] = {
            "node_id": node_id,
            "response_sha256": response_sha256,
            "response_path": str(response),
            "verdicts": verdicts,
        }
        if len(verdicts) > 1:
            node["outcome"] = "AMBIGUOUS"
            node["retry_eligible"] = False
        elif len(verdicts) == 1:
            node["outcome"] = "RECOVERED"
            node["recovered_verdict"] = verdicts[0]
            node["retry_eligible"] = False
            key = f"{run_id}:{node_id}:{response_sha256}:{PARSER_VERSION}"
            node["recovery_key"] = key
            node["recovery_receipt"] = _write_recovery_receipt(out_dir, key, node)
        else:
            node["outcome"] = "ABSENT"
            node["retry_eligible"] = True
        report["nodes"].append(node)
    report["ambiguous"] = any(n["outcome"] == "AMBIGUOUS" for n in report["nodes"])
    report["recovered"] = [n for n in report["nodes"] if n["outcome"] == "RECOVERED"]
    report["retry_eligible_nodes"] = [n["node_id"] for n in report["nodes"] if n.get("retry_eligible")]
    return report


def _write_recovery_receipt(out_dir: Path, key: str, node: dict[str, Any]) -> str:
    out_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(key.encode()).hexdigest()[:24]
    path = out_dir / f"{node['node_id']}-{digest}.json"
    if path.is_file():
        # Idempotent: the derived receipt for this exact key already exists.
        return str(path)
    path.write_text(json.dumps({
        "schema": RECOVERY_SCHEMA,
        "parser_version": PARSER_VERSION,
        "recovery_key": key,
        "node_id": node["node_id"],
        "response_sha256": node["response_sha256"],
        "recovered_verdict": node["recovered_verdict"],
        "note": "derived from handler response bytes; original node receipt not modified",
    }, indent=2, sort_keys=True) + "\n")
    return str(path)
