"""Memory and taxonomy integration for training datalake ingestion."""

from __future__ import annotations
import os

import json
import subprocess
import time
from pathlib import Path
from typing import Any, Dict

import typer

from datalake_config import MEMORY_DIR, MEMORY_SCOPE_PREFIX, TAXONOMY_DIR
from datalake_utils import _append_jsonl, _extract_json_object, _run


def _taxonomy_extract(summary_text: str, taxonomy_collection: str) -> Dict[str, Any]:
    if not TAXONOMY_DIR.exists():
        return {"status": "failed", "error": "taxonomy_skill_missing"}
    cmd = (
        f"cd {TAXONOMY_DIR} && "
        f"./run.sh extract --text {json.dumps(summary_text)} "
        f"--collection \"{taxonomy_collection}\" --fast"
    )
    proc = _run(cmd, timeout=120)
    parsed = _extract_json_object(proc.stdout)
    if proc.returncode != 0 or parsed is None:
        return {
            "status": "failed",
            "returncode": proc.returncode,
            "stdout_tail": "\n".join(proc.stdout.splitlines()[-20:]),
            "stderr_tail": "\n".join(proc.stderr.splitlines()[-20:]),
        }
    return {"status": "ok", "result": parsed}


def _memory_learn_event(
    *,
    event_type: str,
    memory_scope: str,
    taxonomy_collection: str,
    taxonomy: Dict[str, Any],
    payload: Dict[str, Any],
    memory_events_path: Path,
) -> Dict[str, Any]:
    event = {
        "event_type": event_type,
        "timestamp": int(time.time()),
        "scope": memory_scope,
        "taxonomy_collection": taxonomy_collection,
        "taxonomy": taxonomy,
        "payload": payload,
    }
    _append_jsonl(memory_events_path, event)

    if not MEMORY_DIR.exists():
        return {
            "status": "failed",
            "error": "memory_skill_missing",
            "memory_events_path": str(memory_events_path),
        }

    problem = (
        f"ingest-training-datalake event={event_type} "
        f"selected_urls={payload.get('selected_urls', 0)} "
        f"gap_total={payload.get('gap_total_after', payload.get('gap_total', -1))}"
    )
    solution = json.dumps(payload, ensure_ascii=True)
    cmd = [
        "./run.sh",
        "learn",
        "--problem",
        problem,
        "--solution",
        solution,
        "--scope",
        memory_scope,
        "--tag",
        "ingest-training-datalake",
        "--tag",
        event_type,
        "--tag",
        f"collection:{taxonomy_collection}",
    ]
    maybe_tags = taxonomy.get("result", {}).get("bridge_tags", []) if taxonomy.get("status") == "ok" else []
    if isinstance(maybe_tags, list):
        for tag in maybe_tags[:6]:
            normalized = str(tag).strip().lower().replace(" ", "_")
            if normalized:
                cmd.extend(["--tag", f"bridge:{normalized}"])

    proc = subprocess.run(
        cmd,
        cwd=MEMORY_DIR,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )
    return {
        "status": "ok" if proc.returncode == 0 else "failed",
        "returncode": proc.returncode,
        "memory_events_path": str(memory_events_path),
        "stdout_tail": "\n".join(proc.stdout.splitlines()[-20:]),
        "stderr_tail": "\n".join(proc.stderr.splitlines()[-20:]),
    }


def _store_report_to_memory(
    *,
    event_type: str,
    summary_text: str,
    payload: Dict[str, Any],
    taxonomy_collection: str,
    store_memory: bool,
    require_memory_store: bool,
    memory_scope: str,
    memory_events_path: Path,
) -> Dict[str, Any]:
    if not memory_scope.startswith(MEMORY_SCOPE_PREFIX):
        raise typer.BadParameter(
            f"memory_scope must start with '{MEMORY_SCOPE_PREFIX}', got '{memory_scope}'"
        )
    taxonomy = _taxonomy_extract(summary_text, taxonomy_collection)
    store_result: Dict[str, Any] = {"status": "skipped"}
    if store_memory:
        store_result = _memory_learn_event(
            event_type=event_type,
            memory_scope=memory_scope,
            taxonomy_collection=taxonomy_collection,
            taxonomy=taxonomy,
            payload=payload,
            memory_events_path=memory_events_path,
        )
        if require_memory_store and store_result.get("status") != "ok":
            raise typer.Exit(code=1)
    return {"taxonomy": taxonomy, "memory_store": store_result}
