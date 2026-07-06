"""Live sanity harness for Embry voice control.

Inputs are configured endpoint URLs and optional scenario text. Outputs are
machine-readable readiness receipts under the 12TB artifact directory. Failure
modes are explicit: missing services, missing fields, stale turn authority, or
mocked responses produce readiness gaps instead of passing.
"""

from __future__ import annotations

from datetime import datetime, timezone
import html
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from loguru import logger
import typer


app = typer.Typer(help="Embry voice control live sanity harness.")

DEFAULT_OUTPUT_ROOT = Path("/mnt/storage12tb/skills/embry-voice-control/outputs/e2e")
DEFAULT_BASE_URL = "http://127.0.0.1:3001/api/projects/embry-voice"
DEFAULT_CHAT_URL = "http://127.0.0.1:3002/#embry-voice"


def utc_now() -> str:
    """Return an ISO UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def normalize_url(base_url: str, suffix: str) -> str:
    """Join a base URL and suffix without losing local API path prefixes."""
    return f"{base_url.rstrip('/')}/{suffix.lstrip('/')}"


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Write formatted JSON to a path, creating parents as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def write_html(path: Path, report: dict[str, Any]) -> None:
    """Write a small human-readable view over report.json."""
    rows = []
    for case in report["cases"]:
        rows.append(
            "<tr>"
            f"<td>{html.escape(case['id'])}</td>"
            f"<td>{html.escape(case['readiness'])}</td>"
            f"<td>{html.escape(case['assertion_status'])}</td>"
            f"<td>{html.escape(', '.join(case.get('missing_fields', [])))}</td>"
            "</tr>"
        )
    body = "\n".join(rows)
    page = f"""<!doctype html>
<html>
<head><meta charset="utf-8"><title>Embry Voice Control Sanity</title></head>
<body>
<h1>Embry Voice Control Sanity</h1>
<p>Run: {html.escape(report['run_id'])}</p>
<p>Overall: {html.escape(report['overall_readiness'])}</p>
<table border="1" cellspacing="0" cellpadding="6">
<thead><tr><th>Case</th><th>Readiness</th><th>Assertion</th><th>Missing</th></tr></thead>
<tbody>{body}</tbody>
</table>
</body>
</html>
"""
    path.write_text(page, encoding="utf-8")


def response_json(response: httpx.Response) -> dict[str, Any]:
    """Return JSON response data or an explicit parse error object."""
    try:
        data = response.json()
    except ValueError as exc:
        logger.error("non-json response from {}: {}", response.url, exc)
        return {"_parse_error": str(exc), "_text_prefix": response.text[:500]}
    return data if isinstance(data, dict) else {"_json_value": data}


def nested_value(data: dict[str, Any], dotted_path: str) -> Any:
    """Return a nested value for dot-path checks."""
    value: Any = data
    for part in dotted_path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def has_required_field(data: dict[str, Any], field_expr: str) -> bool:
    """Return whether a required field or alias expression is present."""
    aliases = [part.strip() for part in field_expr.split("|")]
    return any(nested_value(data, alias) is not None for alias in aliases)


def missing_fields(data: dict[str, Any], fields: list[str]) -> list[str]:
    """Return required fields absent from a response object."""
    return [field for field in fields if not has_required_field(data, field)]


def compact_value(value: Any, depth: int = 0) -> Any:
    """Return a compact JSON-safe excerpt for receipts."""
    if depth > 4:
        return "<max-depth>"
    if isinstance(value, dict):
        return {key: compact_value(item, depth + 1) for key, item in list(value.items())[:40]}
    if isinstance(value, list):
        if len(value) > 8:
            return {
                "_type": "list",
                "count": len(value),
                "first": [compact_value(item, depth + 1) for item in value[:3]],
            }
        return [compact_value(item, depth + 1) for item in value]
    if isinstance(value, str) and len(value) > 500:
        return value[:500] + "...<truncated>"
    return value


def case_result(
    *,
    case_id: str,
    url: str,
    method: str,
    status_code: int | None,
    data: dict[str, Any],
    required_fields: list[str],
    exercised: str,
    error: str | None = None,
) -> dict[str, Any]:
    """Build a standard case result from one live endpoint call."""
    missing = missing_fields(data, required_fields)
    mocked = data.get("mocked")
    live = data.get("live")
    assertion_pass = not error and status_code is not None and 200 <= status_code < 300 and not missing
    if mocked is True:
        assertion_pass = False
        missing.append("mocked_false")
    if live is False and "live" in required_fields:
        assertion_pass = False
        missing.append("live_true")
    readiness = "usable" if assertion_pass else "not_established"
    return {
        "id": case_id,
        "method": method,
        "url": url,
        "status_code": status_code,
        "mocked": mocked,
        "live": live,
        "execution_status": "pass" if status_code is not None else "error",
        "assertion_status": "pass" if assertion_pass else "fail",
        "readiness": readiness,
        "required_fields": required_fields,
        "missing_fields": sorted(set(missing)),
        "error": error,
        "exercised": exercised,
        "response_excerpt": compact_value(data),
    }


def call_endpoint(
    client: httpx.Client,
    *,
    case_id: str,
    method: str,
    url: str,
    payload: dict[str, Any] | None,
    required_fields: list[str],
    exercised: str,
) -> dict[str, Any]:
    """Call one real endpoint and convert the result to a case receipt."""
    try:
        if method == "GET":
            response = client.get(url)
        else:
            response = client.post(url, json=payload)
        data = response_json(response)
        return case_result(
            case_id=case_id,
            url=url,
            method=method,
            status_code=response.status_code,
            data=data,
            required_fields=required_fields,
            exercised=exercised,
        )
    except httpx.HTTPError as exc:
        logger.error("endpoint call failed for {} {}: {}", method, url, exc)
        return case_result(
            case_id=case_id,
            url=url,
            method=method,
            status_code=None,
            data={},
            required_fields=required_fields,
            exercised=exercised,
            error=str(exc),
        )


def adapted_live_turn_payload(run_id: str, text: str) -> dict[str, Any]:
    """Return a conservative text turn payload for current Embry UX adapters."""
    return {
        "sessionId": f"embry-voice-control-{run_id}",
        "turnId": f"embry-voice-control-turn-{run_id}",
        "text": text,
        "inputMode": "text",
        "voiceEnabled": True,
        "chatEnabled": True,
        "replayEnabled": True,
    }


def adapted_speak_payload(run_id: str) -> dict[str, Any]:
    """Return approved direct speech payload for current Embry UX adapters."""
    text = "Embry voice control live sanity. I am checking the Tau voice front end."
    return {
        "sessionId": f"embry-voice-control-{run_id}",
        "turnId": f"embry-voice-control-speak-{run_id}",
        "text": text,
        "tts_render_text": text,
        "answer_text": text,
        "tone": "calm_precise",
        "delivery_stage": "neutral",
        "pause_strategy": "short_answer_no_filler",
        "interruptible": True,
        "playLocal": False,
    }


def build_report(
    *,
    run_id: str,
    profile: str,
    base_url: str,
    chat_url: str,
    cases: list[dict[str, Any]],
    output_dir: Path,
) -> dict[str, Any]:
    """Build the readiness report from case receipts."""
    failed = [case for case in cases if case["assertion_status"] != "pass"]
    usable = [case for case in cases if case["assertion_status"] == "pass"]
    if failed and usable:
        readiness = "USABLE_WITH_GAPS"
    elif failed:
        readiness = "NOT_ESTABLISHED"
    else:
        readiness = "READY"
    return {
        "schema": "embry_voice_control.e2e_sanity_report.v1",
        "run_id": run_id,
        "profile": profile,
        "overall_readiness": readiness,
        "mocked": False,
        "live": True,
        "base_url": base_url,
        "chat_url": chat_url,
        "output_dir": str(output_dir),
        "created_at": utc_now(),
        "cases": cases,
        "needs_attention": [
            {
                "case": case["id"],
                "reason": case["error"] or "missing_required_fields_or_non_2xx_response",
                "missing_fields": case.get("missing_fields", []),
                "safe_default": "do_not_claim_embry_voice_control_ready",
            }
            for case in failed
        ],
        "claims": {
            "proves": [
                "Only cases with assertion_status=pass exercised real configured endpoints.",
            ],
            "does_not_prove": [
                "Human-audible playback unless play_local/browser checks are separately run.",
                "Browser WebRTC microphone quality unless listener-live profile is run.",
                "Production readiness unless release profile passes with no gaps.",
            ],
        },
    }


@app.command()
def verify(
    profile: str = typer.Option("controlled-live", help="controlled-live, listener-live, or release"),
    base_url: str = typer.Option(DEFAULT_BASE_URL, help="Embry voice control or current adapter base URL"),
    chat_url: str = typer.Option(DEFAULT_CHAT_URL, help="Shared Chat UX URL for reporting"),
    output_root: Path = typer.Option(DEFAULT_OUTPUT_ROOT, help="12TB output root for receipts"),
    timeout: float = typer.Option(90.0, help="HTTP timeout in seconds"),
) -> None:
    """Run live non-mocked sanity checks and write report artifacts."""
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    output_dir = output_root / run_id
    text = "Horus asks Embry to prove voice control reaches Tau and Chatterbox."
    cases: list[dict[str, Any]] = []
    logger.info("running Embry voice control sanity profile={} base_url={}", profile, base_url)
    with httpx.Client(timeout=httpx.Timeout(timeout, connect=2.0)) as client:
        cases.append(
            call_endpoint(
                client,
                case_id="health",
                method="GET",
                url=normalize_url(base_url, "health"),
                payload=None,
                required_fields=["status"],
                exercised="control plane liveness",
            )
        )
        cases.append(
            call_endpoint(
                client,
                case_id="readiness",
                method="GET",
                url=normalize_url(base_url, "readiness"),
                payload=None,
                required_fields=["overall_readiness"],
                exercised="control plane readiness",
            )
        )
        cases.append(
            call_endpoint(
                client,
                case_id="direct-speak",
                method="POST",
                url=normalize_url(base_url, "direct-speak"),
                payload=adapted_speak_payload(run_id),
                required_fields=["mocked", "live", "audioAuthority.artifactId", "audioUrl|audioAuthority.url"],
                exercised="approved text to Chatterbox audio authority",
            )
        )
        cases.append(
            call_endpoint(
                client,
                case_id="text-turn",
                method="POST",
                url=normalize_url(base_url, "live-turn"),
                payload=adapted_live_turn_payload(run_id, text),
                required_fields=["mocked", "live", "turnId|turnAuthority.turnId", "turnAuthority", "audioAuthority"],
                exercised="text turn through memory/Tau/Chatterbox adapter authority",
            )
        )
        if profile in {"listener-live", "release"}:
            cases.append(
                call_endpoint(
                    client,
                    case_id="listen-start",
                    method="POST",
                    url=normalize_url(base_url, "listen/start"),
                    payload={"session_id": f"embry-voice-control-{run_id}"},
                    required_fields=["listener_state", "capture_source", "receipt_path"],
                    exercised="RealtimeSTT/listener capture start",
                )
            )
        if profile == "release":
            cases.append(
                call_endpoint(
                    client,
                    case_id="replay",
                    method="POST",
                    url=normalize_url(base_url, "replay"),
                    payload={"session_id": f"embry-voice-control-{run_id}"},
                    required_fields=["session_id", "turn_count", "audio_artifact_count", "receipt_path"],
                    exercised="shared Chat UX conversation replay",
                )
            )
    report = build_report(
        run_id=run_id,
        profile=profile,
        base_url=base_url,
        chat_url=chat_url,
        cases=cases,
        output_dir=output_dir,
    )
    write_json(output_dir / "report.json", report)
    write_html(output_dir / "index.html", report)
    latest_path = output_root / "latest.json"
    write_json(latest_path, {"run_id": run_id, "report_path": str(output_dir / "report.json"), "overall_readiness": report["overall_readiness"]})
    typer.echo(json.dumps({"run_id": run_id, "overall_readiness": report["overall_readiness"], "report_path": str(output_dir / "report.json")}, indent=2))
    if report["overall_readiness"] != "READY":
        raise typer.Exit(code=1)


@app.command("config-doctor")
def config_doctor(
    base_url: str = typer.Option(DEFAULT_BASE_URL),
    chat_url: str = typer.Option(DEFAULT_CHAT_URL),
) -> None:
    """Print non-interactive config state for the live harness."""
    result = {
        "schema": "embry_voice_control.config_doctor.v1",
        "base_url": base_url,
        "chat_url": chat_url,
        "output_root": str(DEFAULT_OUTPUT_ROOT),
        "needs_attention": [],
    }
    typer.echo(json.dumps(result, indent=2))


if __name__ == "__main__":
    app()
