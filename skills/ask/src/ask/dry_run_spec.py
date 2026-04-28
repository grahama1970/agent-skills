"""Deterministic dry-run execution specs for /ask commands."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def build_execution_spec(
    *,
    command: str,
    subject: str,
    options: dict[str, Any],
    planned_steps: list[str],
    external_calls: list[str],
    filesystem_writes: list[str],
    memory_writes: list[str],
    risk_notes: list[str],
) -> dict[str, Any]:
    return {
        "dry_run": True,
        "spec_protocol_version": "ask.dry_run.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "command": command,
        "subject": subject,
        "options": options,
        "planned_steps": planned_steps,
        "risk_analysis": {
            "external_calls": external_calls,
            "filesystem_writes": filesystem_writes,
            "memory_writes": memory_writes,
            "notes": risk_notes,
        },
        "mutation_policy": "no runtime artifacts, memory writes, subprocess mutations, or oracle calls are performed in dry-run",
    }


def build_ask_dry_run_spec(request: dict[str, Any]) -> dict[str, Any]:
    external_calls = ["memory recall"]
    filesystem_writes: list[str] = []
    memory_writes: list[str] = []
    risk_notes = ["ordinary ask dry-run exits before request/status/events artifacts are written"]
    if request.get("auto_learn"):
        external_calls.extend(["dogpile discovery", "ingest-youtube", "fetcher", "extractor"])
        memory_writes.append("learned QRA/persona items")
    if request.get("oracle"):
        external_calls.append(f"oracle backend: {request.get('oracle_backend')}")
    if request.get("deep_review"):
        external_calls.append("deep-review reviewers")
        filesystem_writes.append(str(request.get("deep_review_output_root") or ".ask_artifacts/deep-review"))
        risk_notes.append("deep review is integrity-sensitive and requires runtime artifacts during real execution")
    if request.get("parallel_review"):
        external_calls.append("parallel reviewer fanout")
    if request.get("dogpile_mode") == "force":
        external_calls.append("dogpile forced freshness search")
    return build_execution_spec(
        command="ask",
        subject=str(request.get("question", "")),
        options=request,
        planned_steps=[
            "route natural language options",
            "write runtime request/status/events artifacts",
            "recall memory",
            "optionally traverse bridges or build evidence case",
            "optionally auto-learn, dogpile, oracle, parallel-review, or deep-review",
            "synthesize answer",
            "finish runtime status",
        ],
        external_calls=external_calls,
        filesystem_writes=filesystem_writes,
        memory_writes=memory_writes,
        risk_notes=risk_notes,
    )


def build_learn_dry_run_spec(request: dict[str, Any]) -> dict[str, Any]:
    return build_execution_spec(
        command="learn",
        subject=str(request.get("topic", "")),
        options=request,
        planned_steps=[
            "detect persona/topic",
            "check existing memory",
            "discover sources through dogpile/discover-books/feed/arxiv",
            "ingest selected videos/books/web pages",
            "extract QRA triples",
            "store learned items",
        ],
        external_calls=["memory recall", "dogpile", "discover-books", "ingest-youtube", "fetcher", "extractor"],
        filesystem_writes=["session transcript", "task-monitor state", "runtime request/status/events artifacts"],
        memory_writes=["persona profile", "QRA triples", "learning session summary"],
        risk_notes=["real learn may run multi-minute external discovery and ingestion"],
    )


def build_nightly_dry_run_spec(request: dict[str, Any]) -> dict[str, Any]:
    return build_execution_spec(
        command="nightly",
        subject=str(request.get("persona") or request.get("scope", "")),
        options=request,
        planned_steps=[
            "discover persona profiles",
            "search for new persona content",
            "ingest new items",
            "optionally refresh OS knowledge",
            "store updates",
        ],
        external_calls=["memory recall", "ingest-youtube search", "arxiv search"],
        filesystem_writes=["runtime request/status/events artifacts"],
        memory_writes=["new persona QRA items", "updated persona profile"],
        risk_notes=["real nightly may touch many personas unless --persona narrows scope"],
    )


def build_os_learn_dry_run_spec(request: dict[str, Any]) -> dict[str, Any]:
    return build_execution_spec(
        command="os learn",
        subject=str(request.get("depth", "")),
        options=request,
        planned_steps=[
            "crawl skill manifests",
            "crawl packages and configuration",
            "build capability graph",
            "generate OS QRA triples",
            "store OS knowledge",
        ],
        external_calls=["memory learn during real execution"],
        filesystem_writes=["runtime request/status/events artifacts"],
        memory_writes=["scope=os QRA triples"],
        risk_notes=["real os learn reads local repo files and writes memory records"],
    )


def print_execution_spec(spec: dict[str, Any], as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(spec, indent=2, sort_keys=True, default=str))
        return
    print(json.dumps(spec, indent=2, sort_keys=True, default=str))
