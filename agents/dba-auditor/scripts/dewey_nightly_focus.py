#!/usr/bin/env python3
"""Dewey nightly focus directives in subagent_memory.

Humans steer overnight monitor-sparta / Dewey work via /ask, then persist focus here
so the next overnight run recalls it from /memory.

Usage:
  store --objective "Focus on EMB3D ingestion" --lanes qra_generation,framework_ingestion
  active
  complete --key dba_auditor:nightly_focus:...
  from-ask --ask-run-id <id> --objective "..." 
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx

MEMORY_URL = os.environ.get("MEMORY_URL", "http://127.0.0.1:8601")
SUBAGENT_ID = "dba_auditor"
PROJECT = "sparta"
SCOPE = "sparta"
LANE = "monitor-sparta"
RECORD_TYPE = "nightly_focus_directive"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H%M%SZ", time.gmtime())


def _slug(text: str, max_len: int = 48) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (s[:max_len] or "focus").strip("-")


def _client() -> httpx.Client:
    return httpx.Client(base_url=MEMORY_URL, timeout=httpx.Timeout(30.0, connect=3.0))


def _list_active(client: httpx.Client) -> list[dict[str, Any]]:
    resp = client.post(
        "/list",
        json={
            "collection": "subagent_memory",
            "filters": {"subagent_id": SUBAGENT_ID, "record_type": RECORD_TYPE, "status": "active"},
            "limit": 20,
        },
    )
    resp.raise_for_status()
    return list(resp.json().get("documents") or [])


def _supersede_active(client: httpx.Client) -> list[str]:
    superseded: list[str] = []
    for doc in _list_active(client):
        key = doc.get("_key")
        if not key:
            continue
        doc = {**doc, "status": "superseded", "superseded_at": _now(), "updated_at": _now()}
        client.post("/store", json={"collection": "subagent_memory", "document": doc}).raise_for_status()
        superseded.append(str(key))
    return superseded


def build_document(
    *,
    objective: str,
    title: str | None = None,
    lanes: list[str] | None = None,
    health_dimensions: list[str] | None = None,
    acceptance_checks: list[str] | None = None,
    ask_run_id: str | None = None,
    ask_artifact_path: str | None = None,
    valid_hours: int = 72,
) -> dict[str, Any]:
    ts = _now()
    key = f"{SUBAGENT_ID}:nightly_focus:{ts}"
    title = title or objective[:120]
    lanes = lanes or []
    dims = health_dimensions or []
    checks = acceptance_checks or []
    retrieval = " ".join(
        part
        for part in [
            "Dewey nightly focus",
            objective,
            "monitor-sparta",
            *lanes,
            *dims,
        ]
        if part
    )
    tags = [
        f"subagent:{SUBAGENT_ID}",
        f"project:{PROJECT}",
        f"lane:{LANE}",
        "nightly_focus",
        "status:active",
    ]
    for lane in lanes:
        tags.append(f"monitor_lane:{lane}")
    return {
        "_key": key,
        "record_type": RECORD_TYPE,
        "subagent_id": SUBAGENT_ID,
        "project": PROJECT,
        "scope": SCOPE,
        "lane": LANE,
        "status": "active",
        "focus_title": title,
        "focus_objective": objective,
        "monitor_sparta_lanes": lanes,
        "monitor_health_dimensions": dims,
        "acceptance_checks": checks,
        "problem": f"Human requested overnight focus: {objective}",
        "solution": "Prioritize this focus in nightly monitor-sparta observation, opportunity ranking, and morning report.",
        "retrieval_text": retrieval,
        "source": "human_ask" if ask_run_id or ask_artifact_path else "human_cli",
        "ask_run_id": ask_run_id,
        "ask_artifact_path": ask_artifact_path,
        "valid_until": time.strftime(
            "%Y-%m-%dT%H%M%SZ", time.gmtime(time.time() + valid_hours * 3600)
        ),
        "created_at": ts,
        "updated_at": ts,
        "tags": tags,
        "artifacts": [p for p in [ask_artifact_path] if p],
    }


def cmd_store(args: argparse.Namespace) -> int:
    lanes = [x.strip() for x in (args.lanes or "").split(",") if x.strip()]
    dims = [x.strip() for x in (args.health_dimensions or "").split(",") if x.strip()]
    checks = [x.strip() for x in (args.acceptance or "").split("|") if x.strip()]
    doc = build_document(
        objective=args.objective,
        title=args.title,
        lanes=lanes,
        health_dimensions=dims,
        acceptance_checks=checks,
        ask_run_id=args.ask_run_id,
        ask_artifact_path=args.ask_artifact_path,
        valid_hours=args.valid_hours,
    )
    with _client() as client:
        superseded = _supersede_active(client) if not args.no_supersede else []
        resp = client.post("/store", json={"collection": "subagent_memory", "document": doc})
        resp.raise_for_status()
    out = {"stored": doc["_key"], "superseded": superseded, "document": doc}
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


def cmd_active(args: argparse.Namespace) -> int:
    with _client() as client:
        active = _list_active(client)
        if args.recall:
            resp = client.post(
                "/recall",
                json={
                    "q": args.recall,
                    "k": 5,
                    "collections": ["subagent_memory"],
                    "tags": [f"subagent:{SUBAGENT_ID}", "nightly_focus"],
                },
            )
            resp.raise_for_status()
            recall = resp.json()
        else:
            recall = None
    # newest active by created_at
    active.sort(key=lambda d: str(d.get("created_at") or ""), reverse=True)
    current = active[0] if active else None
    print(json.dumps({"active": current, "active_count": len(active), "recall": recall}, indent=2, sort_keys=True))
    return 0 if current else 1


def cmd_complete(args: argparse.Namespace) -> int:
    with _client() as client:
        resp = client.post(
            "/list",
            json={"collection": "subagent_memory", "filters": {"_key": args.key}, "limit": 1},
        )
        resp.raise_for_status()
        docs = resp.json().get("documents") or []
        if not docs:
            print(json.dumps({"error": f"not found: {args.key}"}), file=sys.stderr)
            return 1
        doc = docs[0]
        doc["status"] = "completed"
        doc["completed_at"] = _now()
        doc["updated_at"] = _now()
        tags = [t for t in (doc.get("tags") or []) if t != "status:active"]
        tags.append("status:completed")
        doc["tags"] = tags
        client.post("/store", json={"collection": "subagent_memory", "document": doc}).raise_for_status()
    print(json.dumps({"completed": args.key}, indent=2))
    return 0


def cmd_from_ask(args: argparse.Namespace) -> int:
    ask_root = Path(
        args.ask_artifacts
        or os.environ.get("ASK_ARTIFACTS_ROOT", "/mnt/storage12tb/skills/ask/outputs")
    )
    run_dir = ask_root / "runs" / args.ask_run_id
    if not run_dir.is_dir():
        run_dir = Path(args.ask_run_id)
    if not run_dir.is_dir():
        print(json.dumps({"error": f"ask run dir not found: {run_dir}"}), file=sys.stderr)
        return 1
    objective = args.objective
    if not objective:
        for name in ("response.json", "review.json"):
            p = run_dir / name
            if p.is_file():
                data = json.loads(p.read_text(encoding="utf-8"))
                objective = (
                    data.get("focus_objective")
                    or data.get("recommendation")
                    or data.get("answer")
                    or data.get("summary")
                )
                if objective:
                    break
        req = run_dir / f"{args.ask_run_id}.request.json"
        if not objective and req.is_file():
            reqdata = json.loads(req.read_text(encoding="utf-8"))
            objective = reqdata.get("q") or reqdata.get("question")
    if not objective:
        print(json.dumps({"error": "could not derive objective; pass --objective"}), file=sys.stderr)
        return 1
    store_args = argparse.Namespace(
        objective=str(objective).strip(),
        title=args.title,
        lanes=args.lanes or "",
        health_dimensions=args.health_dimensions or "",
        acceptance=args.acceptance or "",
        ask_run_id=args.ask_run_id,
        ask_artifact_path=str(run_dir),
        valid_hours=args.valid_hours,
        no_supersede=False,
    )
    return cmd_store(store_args)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_store = sub.add_parser("store", help="store active nightly focus in subagent_memory")
    p_store.add_argument("--objective", required=True)
    p_store.add_argument("--title")
    p_store.add_argument("--lanes", help="comma-separated monitor-sparta lanes")
    p_store.add_argument("--health-dimensions", help="comma-separated monitor health dimensions")
    p_store.add_argument("--acceptance", help="pipe-separated acceptance checks")
    p_store.add_argument("--ask-run-id")
    p_store.add_argument("--ask-artifact-path")
    p_store.add_argument("--valid-hours", type=int, default=72)
    p_store.add_argument("--no-supersede", action="store_true")

    p_active = sub.add_parser("active", help="show active nightly focus")
    p_active.add_argument("--recall", help="optional recall query to show memory hits")

    p_done = sub.add_parser("complete", help="mark focus completed")
    p_done.add_argument("--key", required=True)

    p_ask = sub.add_parser("from-ask", help="store focus from /ask run artifacts")
    p_ask.add_argument("--ask-run-id", required=True)
    p_ask.add_argument("--objective")
    p_ask.add_argument("--title")
    p_ask.add_argument("--lanes", default="")
    p_ask.add_argument("--health-dimensions", default="")
    p_ask.add_argument("--acceptance", default="")
    p_ask.add_argument("--ask-artifacts")
    p_ask.add_argument("--valid-hours", type=int, default=72)

    args = parser.parse_args()
    handlers = {"store": cmd_store, "active": cmd_active, "complete": cmd_complete, "from-ask": cmd_from_ask}
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
