"""Compute threat deltas by re-evaluating existing evidence cases.

Usage:
    uv run python tools/compute_threat_delta.py [--control-ids ID1,ID2] [--all-recent] [--dry-run]
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import typer
from loguru import logger

app = typer.Typer(no_args_is_help=True)

MEMORY_SOCKET = "/run/user/1000/embry/memory.sock"
MEMORY_BASE_URL = "http://localhost"
MEMORY_TIMEOUT_SECONDS = 30.0
DEFAULT_LIST_LIMIT = 500

SKILL_DIR = Path(__file__).resolve().parent.parent
RUN_SCRIPT = SKILL_DIR / "run.sh"


@dataclass(slots=True)
class ControlCase:
    control_id: str
    question: str
    old_verdict: str
    source_key: str
    source_timestamp: str


@dataclass(slots=True)
class DeltaRecord:
    control_id: str
    old_verdict: str
    new_verdict: str
    reason: str
    timestamp: str


def _memory_client() -> httpx.Client:
    transport = httpx.HTTPTransport(uds=MEMORY_SOCKET)
    return httpx.Client(
        transport=transport,
        base_url=MEMORY_BASE_URL,
        timeout=MEMORY_TIMEOUT_SECONDS,
    )


def _memory_post(client: httpx.Client, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    resp = client.post(path, json=payload)
    resp.raise_for_status()
    body = resp.json()
    if not isinstance(body, dict):
        raise ValueError(f"Unexpected memory daemon response type for {path}: {type(body)}")
    return body


def _parse_control_ids(raw: str | None) -> list[str]:
    if not raw:
        return []
    ids = [part.strip() for part in raw.split(",") if part.strip()]
    deduped: list[str] = []
    seen: set[str] = set()
    for control_id in ids:
        if control_id not in seen:
            deduped.append(control_id)
            seen.add(control_id)
    return deduped


def _extract_question(doc: dict[str, Any]) -> str:
    value = doc.get("question")
    if isinstance(value, str) and value.strip():
        return value.strip()

    claim = doc.get("claim")
    if isinstance(claim, dict):
        text = claim.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()

    return ""


def _extract_verdict(doc: dict[str, Any]) -> str:
    value = doc.get("verdict")
    if isinstance(value, str) and value.strip():
        return value.strip().lower()
    if isinstance(value, dict):
        state = value.get("state")
        if isinstance(state, str) and state.strip():
            return state.strip().lower()

    claim = doc.get("claim")
    if isinstance(claim, dict):
        claim_verdict = claim.get("verdict")
        if isinstance(claim_verdict, str) and claim_verdict.strip():
            return claim_verdict.strip().lower()

    return "unknown"


def _extract_control_ids(doc: dict[str, Any]) -> list[str]:
    raw = doc.get("control_ids")
    if isinstance(raw, list):
        ids = [item.strip() for item in raw if isinstance(item, str) and item.strip()]
        if ids:
            return ids

    claim = doc.get("claim")
    if isinstance(claim, dict):
        claim_ids = claim.get("control_ids")
        if isinstance(claim_ids, list):
            ids = [item.strip() for item in claim_ids if isinstance(item, str) and item.strip()]
            if ids:
                return ids

    control_id = doc.get("control_id")
    if isinstance(control_id, str) and control_id.strip():
        return [control_id.strip()]

    return []


def _extract_timestamp(doc: dict[str, Any]) -> str:
    for key in ("updated_at", "created_at", "timestamp"):
        value = doc.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _fetch_evidence_cases(client: httpx.Client, limit: int = DEFAULT_LIST_LIMIT) -> list[dict[str, Any]]:
    payload: dict[str, Any] = {
        "collection": "evidence_cases",
        "limit": limit,
    }
    body = _memory_post(client, "/list", payload)
    docs = body.get("documents", [])
    if not isinstance(docs, list):
        return []
    typed_docs: list[dict[str, Any]] = [doc for doc in docs if isinstance(doc, dict)]
    return typed_docs


def _build_control_cases(
    docs: list[dict[str, Any]],
    control_filter: set[str],
) -> dict[str, ControlCase]:
    selected: dict[str, ControlCase] = {}
    for doc in docs:
        if doc.get("type") == "threat-delta":
            continue

        question = _extract_question(doc)
        if not question:
            continue

        old_verdict = _extract_verdict(doc)
        source_key = str(doc.get("_key", ""))
        timestamp = _extract_timestamp(doc)

        for control_id in _extract_control_ids(doc):
            if control_filter and control_id not in control_filter:
                continue

            existing = selected.get(control_id)
            if existing is None or (timestamp and timestamp > existing.source_timestamp):
                selected[control_id] = ControlCase(
                    control_id=control_id,
                    question=question,
                    old_verdict=old_verdict,
                    source_key=source_key,
                    source_timestamp=timestamp,
                )

    return selected


def _run_create_evidence_case(question: str) -> dict[str, Any]:
    cmd = [str(RUN_SCRIPT), "create", question, "--json"]
    env = {**os.environ, "SCILLM_MODEL": "text"}
    proc = subprocess.run(
        cmd,
        cwd=str(SKILL_DIR),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        raise RuntimeError(f"create command failed ({proc.returncode}): {stderr}")

    stdout = proc.stdout.strip()
    if not stdout:
        raise RuntimeError("create command returned empty JSON output")

    # run.sh mixes log lines with JSON on stdout — extract the last JSON object
    brace_idx = stdout.rfind("\n{")
    if brace_idx >= 0:
        stdout = stdout[brace_idx + 1:]

    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"create command returned invalid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise RuntimeError("create command JSON output is not an object")

    return parsed


def _extract_new_verdict(result: dict[str, Any]) -> str:
    verdict = result.get("verdict")
    if isinstance(verdict, str) and verdict.strip():
        return verdict.strip().lower()
    if isinstance(verdict, dict):
        state = verdict.get("state")
        if isinstance(state, str) and state.strip():
            return state.strip().lower()
    return "unknown"


def _build_delta(control: ControlCase, new_verdict: str) -> DeltaRecord | None:
    old_verdict = control.old_verdict
    if old_verdict == new_verdict:
        return None

    timestamp = datetime.now(UTC).isoformat()
    reason = (
        f"Verdict changed for control {control.control_id} using stored question "
        f"from evidence case {control.source_key}."
    )
    return DeltaRecord(
        control_id=control.control_id,
        old_verdict=old_verdict,
        new_verdict=new_verdict,
        reason=reason,
        timestamp=timestamp,
    )


def _delta_to_document(delta: DeltaRecord) -> dict[str, Any]:
    key_source = "|".join(
        [
            "threat-delta",
            delta.control_id,
            delta.old_verdict,
            delta.new_verdict,
            delta.timestamp,
        ]
    )
    key = hashlib.sha256(key_source.encode("utf-8")).hexdigest()
    return {
        "_key": key,
        "type": "threat-delta",
        "control_id": delta.control_id,
        "old_verdict": delta.old_verdict,
        "new_verdict": delta.new_verdict,
        "reason": delta.reason,
        "timestamp": delta.timestamp,
    }


def _store_deltas(client: httpx.Client, deltas: list[DeltaRecord]) -> tuple[int, int]:
    if not deltas:
        return (0, 0)

    docs = [_delta_to_document(delta) for delta in deltas]
    body = _memory_post(
        client,
        "/upsert",
        {
            "collection": "evidence_cases",
            "documents": docs,
        },
    )
    inserted = int(body.get("inserted", 0))
    updated = int(body.get("updated", 0))
    return (inserted, updated)


def _print_summary(
    compared: int,
    comparisons: list[tuple[str, str, str, bool]],
    deltas: list[DeltaRecord],
    no_previous_ids: list[str],
    dry_run: bool,
) -> None:
    print(f"compared_controls={compared}")
    print(f"delta_count={len(deltas)}")
    print(f"mode={'dry-run' if dry_run else 'write'}")

    if no_previous_ids:
        for control_id in no_previous_ids:
            print(f"control_id={control_id} no previous evidence case")

    for control_id, old_verdict, new_verdict, changed in comparisons:
        print(
            f"control_id={control_id} old_verdict={old_verdict} "
            f"new_verdict={new_verdict} changed={str(changed).lower()}"
        )

    if not deltas:
        print("no verdict changes")
        return

    for delta in deltas:
        print(
            f"control_id={delta.control_id} old_verdict={delta.old_verdict} "
            f"new_verdict={delta.new_verdict} timestamp={delta.timestamp}"
        )


@app.command()
def main(
    control_ids: str | None = typer.Option(
        None,
        "--control-ids",
        help="Comma-separated control IDs (e.g. DE-0007,CM0028)",
    ),
    all_recent: bool = typer.Option(
        False,
        "--all-recent",
        help="Evaluate all recent controls from evidence_cases",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Compute deltas without persisting to evidence_cases",
    ),
) -> None:
    requested_controls = _parse_control_ids(control_ids)
    if not requested_controls and not all_recent:
        raise typer.BadParameter("Provide --control-ids or --all-recent")

    logger.info("Loading existing evidence cases from memory daemon")
    with _memory_client() as client:
        docs = _fetch_evidence_cases(client)

        control_filter = set(requested_controls)
        control_cases = _build_control_cases(docs, control_filter)

        targets: list[str]
        if requested_controls:
            targets = requested_controls
        else:
            targets = sorted(control_cases.keys())

        no_previous = [control_id for control_id in targets if control_id not in control_cases]

        deltas: list[DeltaRecord] = []
        comparisons: list[tuple[str, str, str, bool]] = []
        compared = 0
        for control_id in targets:
            case = control_cases.get(control_id)
            if case is None:
                continue

            compared += 1
            logger.info("Re-evaluating control {}", control_id)
            result = _run_create_evidence_case(case.question)
            new_verdict = _extract_new_verdict(result)
            changed = case.old_verdict != new_verdict
            comparisons.append((control_id, case.old_verdict, new_verdict, changed))
            delta = _build_delta(case, new_verdict)
            if delta is not None:
                deltas.append(delta)

        if not dry_run:
            inserted, updated = _store_deltas(client, deltas)
            logger.info("Stored deltas: inserted={}, updated={}", inserted, updated)

    _print_summary(
        compared=compared,
        comparisons=comparisons,
        deltas=deltas,
        no_previous_ids=no_previous,
        dry_run=dry_run,
    )


if __name__ == "__main__":
    app()
