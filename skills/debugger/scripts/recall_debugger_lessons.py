#!/usr/bin/env python3
"""Normalize memory recall for debugger lessons as advisory context.

Inputs are either a saved memory `/recall` JSON response or a live memory daemon
call over its Unix socket using httpx. Output is a
`debugger.memory_recall.v1` artifact that is explicitly advisory and cannot
satisfy fresh debugger proof for the current bug.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import typer
from loguru import logger


app = typer.Typer(add_completion=False)


class RecallError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RecallError(message)


def post_recall(query: str, socket_path: Path, k: int) -> dict[str, Any]:
    require(socket_path.exists(), f"memory socket not found: {socket_path}")
    payload = {
        "q": query,
        "k": k,
        "recall_profile": "procedural_memory",
        "collections": ["lessons"],
    }
    transport = httpx.HTTPTransport(uds=str(socket_path))
    with httpx.Client(transport=transport, base_url="http://localhost", timeout=httpx.Timeout(10.0, connect=2.0)) as client:
        resp = client.post("/recall", json=payload)
        require(resp.is_success, f"memory recall failed with HTTP {resp.status_code}: {resp.text[:500]}")
        parsed = resp.json()
    require(isinstance(parsed, dict), "memory recall response must be an object")
    return parsed


def load_recall(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(data, dict), "recall JSON must be an object")
    return data


def item_summary(item: dict[str, Any]) -> dict[str, Any]:
    summary = str(item.get("solution") or item.get("summary") or item.get("problem") or item.get("text") or "")
    return {
        "_key": str(item.get("_key", "")),
        "problem": str(item.get("problem", "")),
        "summary": summary[:1000],
        "tags": [str(tag) for tag in item.get("tags", []) if isinstance(tag, str)],
        "score": item.get("score", item.get("confidence", item.get("scores", {}))),
        "advisory": True,
    }


def normalize_recall(query: str, recall: dict[str, Any]) -> dict[str, Any]:
    items = recall.get("items", [])
    require(isinstance(items, list), "memory recall response must use items, not results")
    lessons = [item_summary(item) for item in items if isinstance(item, dict)]
    return {
        "schema": "debugger.memory_recall.v1",
        "query": query,
        "memory": {
            "found": bool(recall.get("found")),
            "confidence": recall.get("confidence"),
            "should_scan": bool(recall.get("should_scan", False)),
            "item_count": len(lessons),
        },
        "lessons": lessons,
        "safety": {
            "evidence_class": "memory_recall_advisory",
            "fresh_debugger_proof": False,
            "can_satisfy_debugger_proof": False,
            "requires_new_breakpoint_proof_before_patch": True,
        },
    }


@app.command()
def main(
    query: str = typer.Option(..., "--query", help="Debugger-state question or bug pattern for memory recall."),
    recall_json: Path | None = typer.Option(None, "--recall-json", exists=True, dir_okay=False, readable=True, help="Saved memory /recall response JSON."),
    live: bool = typer.Option(False, "--live", help="Call the memory daemon /recall endpoint over its Unix socket."),
    socket_path: Path = typer.Option(Path("/run/user/1000/embry/memory.sock"), "--socket", help="Memory daemon Unix socket."),
    k: int = typer.Option(5, "-k", min=1, max=25, help="Maximum memory items to request."),
    out: Path = typer.Option(..., "--out", dir_okay=False, help="Path for the advisory recall JSON artifact."),
) -> None:
    try:
        if live == bool(recall_json):
            raise RecallError("choose exactly one of --live or --recall-json")
        recall = post_recall(query, socket_path, k) if live else load_recall(recall_json)
        normalized = normalize_recall(query, recall)
    except Exception as exc:
        logger.error("debugger memory recall failed: {}", exc)
        raise typer.Exit(1) from exc

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    typer.echo(f"debugger memory recall advisory written: {out}")


if __name__ == "__main__":
    app()
