"""Jev adapter: typed judgment calls through TypeSafe's System One API.

House contract: egress gate before transmission, fail-closed abstention on
low confidence or transport failure, hash-bound receipts, execution_runs
telemetry. See skills/jev/SKILL.md.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Literal

import httpx
import typer
from loguru import logger
from pydantic import BaseModel, Field, ValidationError

app = typer.Typer(add_completion=False, help="Jev typed-judgment adapter")

SKILL_DIR = Path(__file__).resolve().parent.parent
QUESTIONS_DIR = SKILL_DIR / "questions"
API_URL = "https://api.typesafe.ai/v1/systemone"
# House rule: all /memory calls go through the Docker service on 127.0.0.1:8601.
# MEMORY_SERVICE_URL may hold a unix:// wrapper in some shells; ignore non-http values.
_env_memory = os.getenv("MEMORY_SERVICE_URL", "")
MEMORY_URL = _env_memory if _env_memory.startswith("http") else "http://127.0.0.1:8601"

# Restricted-content markers that must never egress. Machine-syntax markers
# (markings and banner labels), not intent classification.
BLOCKED_MARKERS = (
    "CUI//", "controlled unclassified", "SPARTA//", "ITAR",
    "export-controlled",
)
BLOCKED_MARKERS += tuple(
    t.strip() for t in os.getenv("JEV_EGRESS_BLOCKED_TERMS", "").split(",") if t.strip()
)

RECEIPT_SCHEMA = "jev.receipt.v1"


class JevAnswer(BaseModel):
    """Typed boundary model for one Jev answer (LLM-IO validation gate)."""

    type: Literal["choice", "score", "noul"]
    choice: str | None = None
    noul: float | None = Field(default=None, ge=0.0, le=1.0)
    score: float | None = None
    probabilities: dict[str, float] | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    def model_post_init(self, __context: Any) -> None:
        if self.type == "noul" and self.noul is None:
            raise ValueError("noul answer missing noul value")
        if self.type == "choice" and (self.choice is None or self.probabilities is None):
            raise ValueError("choice answer missing choice/probabilities")
        if self.type == "score" and (self.score is None or self.probabilities is None):
            raise ValueError("score answer missing score/probabilities")


class JevResponse(BaseModel):
    """Typed boundary model for the full /v1/systemone response."""

    model: str
    answers: dict[str, JevAnswer]
    usage: dict[str, int] | None = None


def _sha256(data: Any) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def _load_state(state: str) -> Any:
    if state.startswith("@"):
        return json.loads(Path(state[1:]).read_text())
    return json.loads(state)


def _load_questions(questions: str | None, preset: str | None) -> dict[str, Any]:
    if preset:
        path = QUESTIONS_DIR / f"{preset}.json"
        if not path.exists():
            logger.error("unknown preset '{}'; run `tasks` to list", preset)
            raise typer.Exit(2)
        loaded = json.loads(path.read_text())
        return {k: v for k, v in loaded.items() if k != "_meta"}
    if questions:
        raw = json.loads(Path(questions[1:]).read_text() if questions.startswith("@") else questions)
        return {k: v for k, v in (raw.get("questions", raw) or {}).items() if k != "_meta"}
    logger.error("need --preset or --questions")
    raise typer.Exit(2)


def egress_blocked(state: Any) -> str | None:
    """Return the blocking reason if state may not egress, else None."""
    text = json.dumps(state).lower()
    for marker in BLOCKED_MARKERS:
        if marker.lower() in text:
            return f"restricted marker in state: {marker!r}"
    return None


def _decision(answers: dict[str, Any], accept_conf: float, accept_noul: float) -> tuple[str, str]:
    """accept | abstain, with reason. All questions must clear the bar."""
    for qid, ans in answers.items():
        kind = ans.get("type")
        if kind == "noul":
            p = float(ans.get("noul", 0.5))
            if not (p >= accept_noul or p <= 1 - accept_noul):
                return "abstain", f"{qid}: noul {p:.3f} inside undecided band"
        else:
            conf = float(ans.get("confidence", 0.0))
            if conf < accept_conf:
                return "abstain", f"{qid}: confidence {conf:.3f} < {accept_conf}"
    return "accept", "all questions cleared thresholds"


def _telemetry(task: str, took_ms: int, status: str) -> None:
    """Best-effort duration log to memory /execution-runs."""
    try:
        httpx.post(
            f"{MEMORY_URL}/execution-runs",
            json={
                "request_id": f"jev-{int(time.time())}",
                "executor_type": "skill",
                "executor_name": "jev",
                "tool_name": task,
                "duration_ms": took_ms,
                "status": status,
                "tags": ["jev", "typesafe"],
            },
            timeout=3.0,
        )
    except Exception as exc:  # telemetry is non-fatal but failures must be visible
        logger.error("execution-runs telemetry failed: {}", exc)


@app.command()
def tasks() -> None:
    """List available question presets."""
    for p in sorted(QUESTIONS_DIR.glob("*.json")):
        meta = json.loads(p.read_text()).get("_meta", {})
        print(f"{p.stem:16} {meta.get('for', '')}")


@app.command()
def gate(state: str = typer.Option(..., help="State JSON or @file")) -> None:
    """Egress-gate check only. No API call, no transmission."""
    st = _load_state(state)
    reason = egress_blocked(st)
    if reason:
        print(json.dumps({"egress": "blocked", "reason": reason}))
        raise typer.Exit(1)
    policy = os.getenv("JEV_EGRESS_POLICY", "").lower()
    print(json.dumps({
        "egress": "allowed" if policy == "allow" else "requires --allow-egress or JEV_EGRESS_POLICY=allow",
        "restricted_markers": "none",
    }))
    raise typer.Exit(0)


@app.command()
def ask(
    state: str = typer.Option(..., help="State JSON or @file"),
    preset: str = typer.Option(None, help="Named preset from questions/"),
    questions: str = typer.Option(None, help="Questions JSON or @file (overrides --preset)"),
    allow_egress: bool = typer.Option(False, help="Authorize transmission of the complete payload"),
    out: Path = typer.Option(None, help="Write receipt to file instead of stdout"),
    timeout_s: float = typer.Option(None, help="Request timeout (default JEV_TIMEOUT_S=10)"),
) -> None:
    """Ask Jev; emit jev.receipt.v1. Fail closed on any doubt."""
    t0 = time.time()
    accept_conf = float(os.getenv("JEV_ACCEPT_CONFIDENCE", "0.98"))
    accept_noul = float(os.getenv("JEV_ACCEPT_NOUL", "0.98"))
    model = os.getenv("JEV_MODEL", "jev-latest")
    timeout = timeout_s or float(os.getenv("JEV_TIMEOUT_S", "10"))

    st = _load_state(state)
    qs = _load_questions(questions, preset)
    task = preset or "ad-hoc"

    if not allow_egress and os.getenv("JEV_EGRESS_POLICY", "").lower() != "allow":
        print(json.dumps({"egress": "blocked", "reason": "no explicit egress authorization"}))
        raise typer.Exit(2)
    blocked = egress_blocked(st)
    if blocked:
        print(json.dumps({"egress": "blocked", "reason": blocked}))
        raise typer.Exit(2)

    api_key = os.getenv("JEV_API_KEY")
    if not api_key:
        print(json.dumps({"error": "JEV_API_KEY not set"}))
        raise typer.Exit(2)

    body = {"state": st, "model": model, "questions": qs}
    try:
        resp = httpx.post(
            API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=body,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.TimeoutException:
        print(json.dumps({"decision": "abstain", "reason": f"timeout after {timeout}s"}))
        raise typer.Exit(3)
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        print(json.dumps({"decision": "abstain", "reason": f"HTTP {code} (429/529 => back off; caller escalates)"}))
        raise typer.Exit(3)
    except httpx.HTTPError as exc:
        print(json.dumps({"decision": "abstain", "reason": f"transport: {exc}"}))
        raise typer.Exit(3)

    try:
        parsed = JevResponse.model_validate(data)
    except ValidationError as exc:
        print(json.dumps({
            "decision": "abstain",
            "reason": f"response failed typed validation: {exc.errors()[:3]}",
        }))
        raise typer.Exit(3)

    answers = {qid: ans.model_dump(exclude_none=True) for qid, ans in parsed.answers.items()}
    missing = [q for q in qs if q not in answers]
    if missing:
        print(json.dumps({"decision": "abstain", "reason": f"missing answers: {missing}"}))
        raise typer.Exit(3)

    decision, reason = _decision(answers, accept_conf, accept_noul)
    took_ms = int((time.time() - t0) * 1000)
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "task": task,
        "decision": decision,
        "reason": reason,
        "answers": answers,
        "bindings": {
            "state_sha256": _sha256(st),
            "questions_sha256": _sha256(qs),
            "model": data.get("model", model),
            "thresholds": {"accept_confidence": accept_conf, "accept_noul": accept_noul},
        },
        "usage": data.get("usage"),
        "took_ms": took_ms,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _telemetry(task, took_ms, "ok" if decision == "accept" else "abstain")
    rendered = json.dumps(receipt, indent=2)
    if out:
        out.write_text(rendered)
        print(json.dumps({"decision": decision, "receipt": str(out), "took_ms": took_ms}))
    else:
        print(rendered)
    if decision != "accept":
        raise typer.Exit(3)


if __name__ == "__main__":
    app()
