#!/usr/bin/env python3
"""Live persona sanity checks for ask and direct scillm paths.

This script is opt-in: it makes real runtime/model calls and writes a JSON
evidence report. It is intentionally outside the default pytest suite.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import typer


ASK_ROOT = Path(__file__).resolve().parents[1]
SRC = ASK_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ask.env import load_dotenv_once

load_dotenv_once()

REPO_ROOT = ASK_ROOT.parents[1]
DEFAULT_SCILLM_BASE = os.environ.get("SCILLM_BASE_URL", "http://localhost:4001").rstrip("/")
DEFAULT_SCILLM_KEY = os.environ.get("SCILLM_API_KEY", "sk-dev-proxy-123")
app = typer.Typer(add_completion=False, help="Run real ask/scillm persona sanity checks.")


@app.command()
def main(
    persona_id: str = typer.Option("Brandon", "--persona-id"),
    model: str = typer.Option(os.environ.get("ASK_PERSONA_E2E_MODEL", "gpt-5.5"), "--model"),
    output_dir: str = typer.Option("/tmp/ask-persona-delegate-e2e", "--output-dir"),
    timeout: float = typer.Option(360.0, "--timeout"),
    scillm_base_url: str = typer.Option(DEFAULT_SCILLM_BASE, "--scillm-base-url"),
    scillm_api_key: str = typer.Option(DEFAULT_SCILLM_KEY, "--scillm-api-key"),
    skip_ask: bool = typer.Option(False, "--skip-ask"),
    skip_scillm: bool = typer.Option(False, "--skip-scillm"),
) -> None:
    args = SimpleNamespace(
        persona_id=persona_id,
        model=model,
        output_dir=output_dir,
        timeout=timeout,
        scillm_base_url=scillm_base_url,
        scillm_api_key=scillm_api_key,
        skip_ask=skip_ask,
        skip_scillm=skip_scillm,
    )
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc).isoformat()
    checks: list[dict[str, Any]] = []

    if not args.skip_ask:
        checks.append(run_ask_persona(args, output_dir))
    if not args.skip_scillm:
        checks.append(run_scillm_persona(args, output_dir))

    checks.append(cross_check(args, checks))
    ok = all(check.get("ok") for check in checks)
    report = {
        "schema": "ask.persona_delegate_e2e.v1",
        "ok": ok,
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "persona_id": args.persona_id,
        "model": args.model,
        "output_dir": str(output_dir),
        "checks": checks,
    }
    report_path = output_dir / "persona-delegate-e2e-report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    raise typer.Exit(0 if ok else 1)


def run_ask_persona(args: SimpleNamespace, output_dir: Path) -> dict[str, Any]:
    ask_id = "persona-delegate-ask-live"
    ask_runs = output_dir / "ask-runs"
    prompt = "Critique whether a retry loop fails closed when a downstream service stays unavailable. Keep it under 120 words."
    command = [
        str(ASK_ROOT / "run.sh"),
        "ask",
        prompt,
        "--oracle",
        "--oracle-backend",
        "scillm",
        "--oracle-model",
        args.model,
        "--oracle-persona",
        args.persona_id,
        "--oracle-timeout",
        str(int(args.timeout)),
        "--ask-id",
        ask_id,
        "--run-output-root",
        str(ask_runs),
        "--overwrite",
        "--json",
    ]
    started = time.time()
    completed = subprocess.run(
        command,
        cwd=str(ASK_ROOT),
        capture_output=True,
        text=True,
        timeout=args.timeout + 30,
        env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
    )
    stdout_path = output_dir / "ask-persona.stdout.json"
    stderr_path = output_dir / "ask-persona.stderr.log"
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    run_dir = ask_runs / ask_id
    request_path = run_dir / f"{ask_id}.request.json"
    status_path = run_dir / f"{ask_id}.status.json"
    events_path = run_dir / f"{ask_id}.events.jsonl"
    errors = []
    payload = _load_json_from_stdout(completed.stdout, errors)
    request = _load_json_file(request_path, errors, "ask request")
    status = _load_json_file(status_path, errors, "ask status")
    if completed.returncode != 0:
        errors.append(f"ask command returned {completed.returncode}")
    if request.get("oracle_persona") != args.persona_id:
        errors.append("ask request did not preserve oracle_persona")
    if request.get("oracle_backend") != "scillm":
        errors.append("ask request did not use scillm backend")
    if status.get("state") not in {"answered", "completed"}:
        errors.append(f"ask status was not answered/completed: {status.get('state')}")
    answer = str(payload.get("answer") or "")
    if len(answer.strip()) < 20:
        errors.append("ask answer was empty or too short")
    return {
        "name": "ask_persona",
        "ok": not errors,
        "errors": errors,
        "seconds": round(time.time() - started, 3),
        "command": command,
        "artifacts": {
            "stdout": str(stdout_path),
            "stderr": str(stderr_path),
            "request": str(request_path),
            "status": str(status_path),
            "events": str(events_path),
            "run_dir": str(run_dir),
        },
        "observed": {
            "returncode": completed.returncode,
            "state": status.get("state"),
            "oracle_persona": request.get("oracle_persona"),
            "oracle_backend": request.get("oracle_backend"),
            "answer_chars": len(answer),
        },
    }


def run_scillm_persona(args: SimpleNamespace, output_dir: Path) -> dict[str, Any]:
    started = time.time()
    request_path = output_dir / "scillm-persona.request.json"
    response_path = output_dir / "scillm-persona.response.json"
    health_path = output_dir / "scillm-health.json"
    persona_id = str(args.persona_id)
    request_payload = {
        "model": args.model,
        "messages": [
            {
                "role": "system",
                "content": (
                    f"You are acting under persona_id={persona_id}. "
                    "Answer from that persona contract. Do not claim a different identity."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Critique whether a retry loop fails closed when a downstream service "
                    "stays unavailable. Keep it under 120 words."
                ),
            },
        ],
        "scillm_metadata": {
            "caller": "ask-persona-delegate-e2e",
            "persona_id": persona_id,
            "actor_kind": "persona",
            "contract_source": "agent_skills.delegate.v1",
        },
    }
    request_path.write_text(json.dumps(request_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    errors = []
    headers = {
        "Authorization": f"Bearer {args.scillm_api_key}",
        "X-Caller-Skill": "ask-persona-delegate-e2e",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(base_url=args.scillm_base_url, headers=headers, timeout=args.timeout) as client:
            health_response = client.get("/health/liveliness")
            health_path.write_text(health_response.text, encoding="utf-8")
            health_response.raise_for_status()
            response = client.post("/v1/chat/completions", json=request_payload)
            response.raise_for_status()
            response_payload = response.json()
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
        response_payload = {}
    response_path.write_text(json.dumps(response_payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    answer = _extract_chat_answer(response_payload)
    metadata_preserved = request_payload["scillm_metadata"]["persona_id"] == persona_id
    if not metadata_preserved:
        errors.append("scillm request metadata did not preserve persona_id")
    if len(answer.strip()) < 20:
        errors.append("scillm answer was empty or too short")
    return {
        "name": "scillm_persona",
        "ok": not errors,
        "errors": errors,
        "seconds": round(time.time() - started, 3),
        "artifacts": {
            "health": str(health_path),
            "request": str(request_path),
            "response": str(response_path),
        },
        "observed": {
            "persona_id": persona_id,
            "model": args.model,
            "answer_chars": len(answer),
            "metadata_preserved_in_request": metadata_preserved,
        },
    }


def cross_check(args: SimpleNamespace, checks: list[dict[str, Any]]) -> dict[str, Any]:
    by_name = {check["name"]: check for check in checks}
    errors = []
    ask_check = by_name.get("ask_persona")
    scillm_check = by_name.get("scillm_persona")
    if ask_check and not ask_check.get("ok"):
        errors.append("ask persona check did not pass")
    if scillm_check and not scillm_check.get("ok"):
        errors.append("scillm persona check did not pass")
    if ask_check and ask_check.get("observed", {}).get("oracle_persona") != args.persona_id:
        errors.append("ask persona id does not match requested persona")
    if scillm_check and scillm_check.get("observed", {}).get("persona_id") != args.persona_id:
        errors.append("scillm persona id does not match requested persona")
    return {
        "name": "persona_cross_check",
        "ok": not errors,
        "errors": errors,
        "observed": {
            "persona_id": args.persona_id,
            "ask_checked": bool(ask_check),
            "scillm_checked": bool(scillm_check),
        },
    }


def _load_json_from_stdout(stdout: str, errors: list[str]) -> dict[str, Any]:
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        errors.append(f"stdout was not JSON: {exc}")
        return {}


def _load_json_file(path: Path, errors: list[str], label: str) -> dict[str, Any]:
    if not path.exists():
        errors.append(f"{label} missing: {path}")
        return {}
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        errors.append(f"{label} invalid JSON: {exc}")
        return {}
    return payload if isinstance(payload, dict) else {}


def _extract_chat_answer(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    message = choices[0].get("message") if isinstance(choices[0], dict) else {}
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return content if isinstance(content, str) else ""


if __name__ == "__main__":
    app()
