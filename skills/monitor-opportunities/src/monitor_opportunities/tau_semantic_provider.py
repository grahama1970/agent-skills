"""Provider-live semantic addendum sidecar for prepared Tau inputs."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from .contracts import validate_tau_semantic_input
from .util import read_json, sha256_json, utc_now, write_json

VERDICTS = {"KEEP", "ADJACENT", "REJECT", "NEEDS_REVIEW"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-") or "opportunity"


def _extract_json_object(text: str) -> dict[str, Any]:
    fence = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        return json.loads(fence.group(1))
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("provider_response_json_missing")
    return json.loads(text[start : end + 1])


def _validate_addendum(addendum: dict[str, Any], opportunity_id: str) -> list[str]:
    errors: list[str] = []
    if addendum.get("schema") != "monitor_opportunities.semantic_addendum.v1":
        errors.append("schema_invalid")
    if addendum.get("opportunity_id") != opportunity_id:
        errors.append("opportunity_id_mismatch")
    if addendum.get("verdict") not in VERDICTS:
        errors.append("verdict_invalid")
    for field in ("semantic_summary", "tailoring_guidance"):
        if not isinstance(addendum.get(field), str) or not addendum[field].strip():
            errors.append(f"{field}_missing")
    for field in ("talking_points", "interview_questions", "evidence_refs", "non_claims"):
        value = addendum.get(field)
        if not isinstance(value, list) or not value or not all(isinstance(item, str) and item.strip() for item in value):
            errors.append(f"{field}_invalid")
    if addendum.get("external_effects") is not False:
        errors.append("external_effects_not_false")
    return errors


def _build_prompt(payload: dict[str, Any]) -> str:
    return (
        "You are evaluating one monitor-opportunities semantic input as a provider-live sidecar.\n"
        "Return exactly one JSON object, with no markdown except an optional json fence.\n"
        "Do not browse, apply, message, RSVP, email, submit forms, or infer private facts.\n"
        "Meetup evidence is supplemental only. Do not promote Meetup into primary opportunity evidence.\n"
        "Relationship evidence may only be used when present in relationship_evidence.\n"
        "Use only the approved claim ledger and source IDs in the input.\n\n"
        "Required JSON schema:\n"
        "{\n"
        '  "schema": "monitor_opportunities.semantic_addendum.v1",\n'
        '  "opportunity_id": "<same id>",\n'
        '  "verdict": "KEEP|ADJACENT|REJECT|NEEDS_REVIEW",\n'
        '  "semantic_summary": "<one concise paragraph>",\n'
        '  "tailoring_guidance": "<claim-bound resume/interview guidance>",\n'
        '  "talking_points": ["<source-bound point>"],\n'
        '  "interview_questions": ["<question to prepare for>"],\n'
        '  "evidence_refs": ["<input source receipt id or artifact hash>"],\n'
        '  "non_claims": ["<what this addendum does not prove>"],\n'
        '  "external_effects": false\n'
        "}\n\n"
        "Semantic input JSON:\n"
        + json.dumps(payload, indent=2, sort_keys=True)
        + "\n"
    )


def run_provider_semantic_eval(
    *,
    input_path: Path,
    out_dir: Path,
    handler: str = "webgpt",
    execute: bool = False,
    timeout_seconds: int = 3600,
    browser_lock_timeout: int = 1800,
) -> dict[str, Any]:
    """Run one provider-live semantic addendum through /ask Tau DAG."""

    raw = read_json(input_path)
    payload = validate_tau_semantic_input(raw).model_dump(by_alias=True, mode="json")
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = out_dir / "provider-prompt.md"
    write_json(out_dir / "validated-input.json", payload)
    prompt_path.write_text(_build_prompt(payload), encoding="utf-8")

    if not execute:
        receipt = {
            "schema": "monitor_opportunities.tau_semantic_provider_receipt.v1",
            "status": "EXECUTE_REQUIRED",
            "opportunity_id": payload["opportunity_id"],
            "provider_live": False,
            "mocked": False,
            "live": False,
            "external_effects": False,
            "prompt": str(prompt_path),
            "input": str(input_path),
            "reason": "Pass --execute to call the provider through /ask Tau DAG.",
        }
        write_json(out_dir / "tau-semantic-provider-receipt.json", receipt)
        return receipt

    repo_root = _repo_root()
    ask_run = repo_root / "skills" / "ask" / "run.sh"
    ask_id = f"monitor-opportunities-semantic-{_safe_id(payload['opportunity_id'])}-{handler}"
    ask_root = out_dir / "ask-runs"
    request = (
        "Evaluate the attached monitor-opportunities semantic input and return exactly the required JSON semantic addendum."
    )
    command = [
        str(ask_run),
        "tau-dag",
        request,
        "--repo",
        "grahama1970/agent-skills",
        "--target",
        f"monitor-opportunities/semantic/{payload['opportunity_id']}",
        "--immutable-goal",
        "Produce one provider-live semantic addendum from a validated monitor-opportunities input without external effects.",
        "--dag-template",
        "single-call",
        "--handler",
        handler,
        "--attach-file",
        str(prompt_path),
        "--ask-id",
        ask_id,
        "--run-output-root",
        str(ask_root),
        "--browser-lock-timeout",
        str(browser_lock_timeout),
        "--poll-timeout-seconds",
        str(timeout_seconds),
        "--execute",
        "--json",
    ]
    started_at = utc_now()
    proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds + 120)
    process_receipt = {
        "command": command,
        "exit_code": proc.returncode,
        "stdout": proc.stdout[-12000:],
        "stderr": proc.stderr[-12000:],
        "started_at": started_at,
        "completed_at": utc_now(),
    }
    write_json(out_dir / "provider-process.json", process_receipt)

    run_dir = ask_root / ask_id
    node_dir = run_dir / "node-artifacts" / f"handler-{handler}"
    node_receipt_path = node_dir / "node-receipt.json"
    response_path = node_dir / "response.md"
    provider_result_path = node_dir / "response.provider_result.json"
    node_receipt = read_json(node_receipt_path) if node_receipt_path.exists() else {}
    provider_result = read_json(provider_result_path) if provider_result_path.exists() else {}

    parse_errors: list[str] = []
    addendum: dict[str, Any] | None = None
    if response_path.exists():
        try:
            addendum = _extract_json_object(response_path.read_text(encoding="utf-8"))
            parse_errors.extend(_validate_addendum(addendum, payload["opportunity_id"]))
        except (json.JSONDecodeError, ValueError) as exc:
            parse_errors.append(str(exc))
    else:
        parse_errors.append("response_path_missing")

    provider_live = (
        node_receipt.get("provider_live") is True
        and provider_result.get("success") is True
        and provider_result.get("proof_status") == "response_proven"
    )
    status = "PASS" if proc.returncode == 0 and provider_live and not parse_errors else "FAIL"
    if addendum is not None and not parse_errors:
        write_json(out_dir / "semantic-addendum.json", addendum)
    receipt = {
        "schema": "monitor_opportunities.tau_semantic_provider_receipt.v1",
        "status": status,
        "opportunity_id": payload["opportunity_id"],
        "handler": handler,
        "ask_id": ask_id,
        "ask_run_dir": str(run_dir),
        "node_receipt": str(node_receipt_path) if node_receipt_path.exists() else None,
        "provider_result": str(provider_result_path) if provider_result_path.exists() else None,
        "response": str(response_path) if response_path.exists() else None,
        "semantic_addendum": str(out_dir / "semantic-addendum.json") if addendum is not None and not parse_errors else None,
        "process_receipt": str(out_dir / "provider-process.json"),
        "input_sha256": "sha256:" + sha256_json(raw),
        "prompt_sha256": "sha256:" + sha256_json({"prompt": prompt_path.read_text(encoding="utf-8")}),
        "parse_errors": parse_errors,
        "mocked": False,
        "live": proc.returncode == 0,
        "provider_live": provider_live,
        "external_effects": False,
        "non_claims": [
            "This sidecar does not mutate the report, rerank opportunities, send outreach, submit ATS forms, or RSVP to Meetup.",
            "Provider output is admitted only as a semantic addendum after closed-schema parsing.",
        ],
    }
    write_json(out_dir / "tau-semantic-provider-receipt.json", receipt)
    return receipt
