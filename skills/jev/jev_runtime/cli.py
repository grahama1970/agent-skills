"""Thin, legacy-compatible CLI over the native Jev decision client.

Presets remain repository-owned questions/*.json. Gate/ask never read shell startup
files. All paths emit structured data; restricted payloads and failures exit nonzero.
"""
from __future__ import annotations

import asyncio
import json
import hashlib
from datetime import datetime, timezone
import os
from pathlib import Path
import typer
from .core import Jev, Policy, Request, egress_reason

app = typer.Typer(add_completion=False)
QUESTIONS = Path(os.getenv("JEV_QUESTIONS_DIR", str(Path(__file__).resolve().parent.parent / "questions")))


def load(value: str):
    return json.loads(Path(value[1:]).read_text() if value.startswith("@") else value)


def question_map(preset: str | None, questions: str | None):
    if questions:
        raw = load(questions)
        raw = raw.get("questions", raw)
    elif preset and preset.isidentifier():
        raw = json.loads((QUESTIONS / f"{preset}.json").read_text())
    else:
        raise ValueError("questions_required")
    return {k: v for k, v in raw.items() if k != "_meta"}


@app.command()
def tasks():
    """List repository-owned question presets without contacting a service."""
    for path in sorted(QUESTIONS.glob("*.json")):
        print(path.stem)


@app.command()
def gate(state: str = typer.Option(...), questions: str | None = None):
    """Check complete supplied state/questions locally; not an egress authorization."""
    try:
        body = {"state": load(state), "questions": load(questions) if questions else {}}
        reason = egress_reason(body, Policy(allow_egress=True, data_class="approved_internal"))
    except Exception:
        print(json.dumps({"egress": "blocked", "reason": "invalid_input"}))
        raise typer.Exit(2)
    print(json.dumps({"egress": "blocked" if reason else "requires_explicit_authorization", "reason": reason}))
    if reason:
        raise typer.Exit(1)


@app.command()
def ask(state: str = typer.Option(...), preset: str | None = None, questions: str | None = None,
        allow_egress: bool = False, out: Path | None = None, timeout_s: float | None = None):
    """Emit jev.receipt.v1 with the new typed decision embedded; no fallback or execution."""
    try:
        authorized = allow_egress or os.getenv("JEV_EGRESS_POLICY", "").lower() == "allow"
        policy = Policy(allow_egress=authorized, data_class="approved_internal" if authorized else "unknown",
                        threshold=float(os.getenv("JEV_ACCEPT_CONFIDENCE", "0.98")),
                        timeout_ms=int((timeout_s if timeout_s is not None else float(os.getenv("JEV_TIMEOUT_S", "1.5"))) * 1000),
                        blocked_terms=[x.strip() for x in os.getenv("JEV_EGRESS_BLOCKED_TERMS", "").split(",") if x.strip()])
        # One conservative bar covers all primitives; a higher legacy NOUL bar is preserved.
        noul_threshold = float(os.getenv("JEV_ACCEPT_NOUL", str(policy.threshold)))
        policy = Policy(**{**policy.model_dump(), "threshold": max(policy.threshold, noul_threshold)})
        req = Request(task=preset or "ad-hoc", state=load(state), questions=question_map(preset, questions), model=os.getenv("JEV_MODEL", "jev-latest"))
        async def execute():
            async with Jev(policy) as client:
                return await client.ask(req)
        decision = asyncio.run(execute())
    except (ValueError, OSError, TypeError):
        print(json.dumps({"schema": "jev.receipt.v1", "decision": "error", "reason": "invalid_input"}))
        raise typer.Exit(2)
    rendered = {"schema": "jev.receipt.v1", "decision": "accept" if decision.status == "accepted" else "abstain",
                "reason": decision.reason, "answers": decision.answers, "usage": decision.usage,
                "bindings": {"state_sha256": hashlib.sha256(json.dumps(req.state,sort_keys=True).encode()).hexdigest(),
                             "questions_sha256": hashlib.sha256(json.dumps(req.questions,sort_keys=True).encode()).hexdigest(),
                             "model": decision.resolved_model or req.model,
                             "thresholds": {"accept_confidence": policy.threshold,"accept_noul":policy.threshold}},
                "took_ms": decision.duration_ms,"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    if decision.status == "blocked":
        rendered["egress"] = "blocked"
    text = json.dumps(rendered, indent=2)
    if out:
        out.write_text(text + "\n")
    print(text)
    if decision.status != "accepted":
        raise typer.Exit(2 if decision.status == "blocked" else 3)


if __name__ == "__main__":
    app()
