"""Maintenance-event log API for the skills ecosystem.

Implements the maintenance-log contract in references/maintenance_log_contract.md:
- emit:  append a typed maintenance event to the shared `skill_maintenance_events`
         collection in the memory daemon (the ONLY sanctioned ArangoDB path).
- query: exact-match retrieval by skill_id for foreign agents debugging a skill.

Policy (how often to maintain, what checks mean "maintained") lives in each
skill's MAINTENANCE.md; this API owns the mutable event history only.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
import pydantic
import typer

MEMORY_BASE = "http://127.0.0.1:8601"
COLLECTION = "skill_maintenance_events"

EventType = Literal[
    "maintenance.completed",
    "file.pruned",
    "skill.renamed",
    "decision.recorded",
    "config.changed",
]


class MaintenanceEvent(pydantic.BaseModel):
    """agent-skills.skill_maintenance_event.v1 — one durable maintenance fact."""

    model_config = pydantic.ConfigDict(extra="forbid")

    schema_: str = pydantic.Field(
        default="agent-skills.skill_maintenance_event.v1", alias="schema"
    )
    skill_id: str = pydantic.Field(min_length=3, pattern=r"^[a-z0-9_.-]+:[a-z0-9_.-]+$")  # stable id, e.g. "agent-skills:ops-workstation"
    repo: str = pydantic.Field(min_length=1)
    event_type: EventType
    summary: str = pydantic.Field(min_length=8)
    changed_paths: list[str] = []
    proof_receipt: str | None = None  # local path or receipt id backing the claim
    actor: str = "project-agent"
    tags: list[str] = []
    observed_at: str = pydantic.Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def deterministic_key(self) -> str:
        material = "|".join(
            [self.repo, self.skill_id, self.event_type, self.observed_at, self.summary]
        )
        return "me_" + hashlib.sha256(material.encode()).hexdigest()[:32]


def _client() -> httpx.Client:
    return httpx.Client(base_url=MEMORY_BASE, timeout=httpx.Timeout(10.0, connect=2.0))


def emit(
    skill_id: str = typer.Option(..., help="Stable skill id, e.g. agent-skills:ask"),
    repo: str = typer.Option(..., help="Repository the skill lives in"),
    event_type: EventType = typer.Option(...),
    summary: str = typer.Option(..., help="One-line plain statement of what was done"),
    changed_path: list[str] = typer.Option(
        [], help="Repo-relative path touched (repeatable)"
    ),
    proof_receipt: str = typer.Option(
        None, help="Local receipt/artifact path backing the claim"
    ),
    actor: str = typer.Option("project-agent"),
    tag: list[str] = typer.Option([]),
) -> None:
    """Append one maintenance event; verify by immediate read-back."""
    try:
        event = MaintenanceEvent(
            skill_id=skill_id,
            repo=repo,
            event_type=event_type,
            summary=summary,
            changed_paths=changed_path,
            proof_receipt=proof_receipt,
            actor=actor,
            tags=tag,
        )
    except pydantic.ValidationError as exc:
        errors = [
            {"type": e["type"], "loc": e["loc"], "msg": e["msg"]}
            for e in exc.errors(include_url=False)
        ]
        typer.echo(json.dumps({"ok": False, "validation_errors": errors}))
        raise typer.Exit(code=2)

    doc = event.model_dump(by_alias=True)
    doc["_key"] = event.deterministic_key()
    with _client() as client:
        store = client.post("/store", json={"document": doc, "collection": COLLECTION})
        store.raise_for_status()
        back = client.post(
            "/list",
            json={"collection": COLLECTION, "filters": {"_key": doc["_key"]}, "limit": 1},
        )
        back.raise_for_status()
        rows = back.json().get("documents") or back.json().get("items") or []
    ok = any(r.get("_key") == doc["_key"] for r in rows)
    typer.echo(
        json.dumps({"ok": ok, "key": doc["_key"], "readback": len(rows), "collection": COLLECTION})
    )
    if not ok:
        raise typer.Exit(code=3)


def query(
    skill_id: str = typer.Option(..., help="Stable skill id to inspect"),
    limit: int = typer.Option(20),
) -> None:
    """Exact-match event history for one skill (for foreign debugging agents)."""
    with _client() as client:
        resp = client.post(
            "/list",
            json={"collection": COLLECTION, "filters": {"skill_id": skill_id}, "limit": limit},
        )
        resp.raise_for_status()
        rows = resp.json().get("documents") or resp.json().get("items") or []
    rows.sort(key=lambda r: r.get("observed_at", ""), reverse=True)
    typer.echo(json.dumps({"skill_id": skill_id, "count": len(rows), "events": rows}, indent=2))


app = typer.Typer(help=__doc__)
app.command()(emit)
app.command()(query)


if __name__ == "__main__":
    app()
