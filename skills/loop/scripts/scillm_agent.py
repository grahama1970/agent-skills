#!/usr/bin/env python3
"""Scillm-backed worker adapter for the loop harness.

The loop harness talks to workers through a deliberately small contract:
JSON prompt on stdin, JSON result on stdout, repository changes as side effects.
This adapter maps that contract to Scillm exec or OpenCode serve calls.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "http://localhost:4001"
DEFAULT_API_KEY = "sk-dev-proxy-123"
EXEC_PROFILE_TYPES = {
    "codex-gpt-5.5": "codex_exec",
    "codex-vision": "codex_exec",
    "kimi-k2.6": "kimi_exec",
    "kimi-k2.5": "kimi_exec",
    "kimi": "kimi_exec",
    "pi-chutes-kimi": "pi_exec",
    "pi-opencode-kimi": "pi_exec",
    "oc-chutes-deepseek": "opencode_exec",
}
SUCCESS_STATUSES = {"completed", "success", "succeeded", "ok"}
REVIEWER_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdict", "findings"],
    "properties": {
        "verdict": {"type": "string", "enum": ["PASS", "NEEDS_CHANGES", "BLOCKED"]},
        "findings": {"type": "array", "items": {"type": "string"}},
    },
}


def parse_stdin() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {"prompt_text": raw}
    return value if isinstance(value, dict) else {"prompt": value}


def first_json_object(text: str) -> Any | None:
    decoder = json.JSONDecoder()
    for idx, char in enumerate(text):
        if char != "{":
            continue
        try:
            obj, _end = decoder.raw_decode(text[idx:])
        except json.JSONDecodeError:
            continue
        return obj
    return None


def fenced_json_object(text: str) -> Any | None:
    stripped = text.strip()
    match = re.fullmatch(r"```(?:json)?\s*\n?(.*?)\n?```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if not match:
        return None
    try:
        return json.loads(match.group(1).strip())
    except json.JSONDecodeError:
        return None


def parse_jsonish(value: Any, *, allow_embedded: bool = True) -> Any | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            fenced = fenced_json_object(value)
            if fenced is not None:
                return fenced
            if allow_embedded:
                return first_json_object(value)
    return None


def http_post(base_url: str, path: str, api_key: str, caller_skill: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = base_url.rstrip("/") + path
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "X-Caller-Skill": caller_skill,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=max(10, int(payload.get("timeout_s", 300)) + 30)) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{path} HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{path} request failed: {exc.reason}") from exc


def base_worker_prompt(role: str, loop_prompt: dict[str, Any]) -> str:
    return (
        "You are a loop harness worker. Read the JSON task below and return JSON only.\n"
        f"Role: {role}\n"
        "Rules:\n"
        "- Do not infer final loop success; the harness decides from checks and receipts.\n"
        "- Stay within allowed_globs.\n"
        "- Do not reference or modify .loop artifacts.\n"
        "- code-reviewer must be read-only and must return {\"verdict\":\"PASS|NEEDS_CHANGES|BLOCKED\",\"findings\":[...]}.\n\n"
        "Loop task JSON:\n"
        + json.dumps(loop_prompt, indent=2, sort_keys=True)
    )


def extract_exec_result(body: dict[str, Any], *, allow_embedded_json: bool = True) -> Any | None:
    result = body.get("result")
    candidates: list[Any] = []
    if isinstance(result, dict):
        nested = result.get("result")
        if isinstance(nested, dict):
            candidates.extend([nested.get("content"), nested.get("stdout"), nested.get("final")])
        candidates.extend(
            [
                result.get("content"),
                result.get("stdout"),
                result.get("final"),
                result.get("result"),
            ]
        )
    candidates.extend([body.get("assistant_text"), body.get("content"), body.get("stdout")])
    for candidate in candidates:
        parsed = parse_jsonish(candidate, allow_embedded=allow_embedded_json)
        if parsed is not None:
            return parsed
    return None


def valid_reviewer_payload(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    verdict = value.get("verdict")
    if "findings" not in value:
        return None
    findings = value.get("findings")
    if verdict not in {"PASS", "NEEDS_CHANGES", "BLOCKED"}:
        return None
    if not isinstance(findings, list) or not all(isinstance(item, str) for item in findings):
        return None
    return {"verdict": verdict, "findings": findings}


def run_exec(args: argparse.Namespace, loop_prompt: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    node_id = f"loop-{args.role}-{os.getpid()}"
    payload: dict[str, Any] = {
        "id": node_id,
        "type": args.exec_type or EXEC_PROFILE_TYPES.get(args.exec_profile, "codex_exec"),
        "model": args.exec_profile,
        "sandbox": args.sandbox,
        "cwd": str(Path(os.environ.get("LOOP_REPO", os.getcwd())).resolve()),
        "node_goal": f"loop {args.role}",
        "prompt": base_worker_prompt(args.role, loop_prompt),
        "timeout_s": args.timeout,
        "idle_timeout_s": args.idle_timeout,
        "metadata": {
            "caller": "loop.scillm_agent",
            "loop_role": args.role,
            "loop_attempt": os.environ.get("LOOP_ATTEMPT", ""),
        },
    }
    if args.role == "code-reviewer":
        payload["output_schema"] = REVIEWER_OUTPUT_SCHEMA
    if args.reasoning_effort:
        payload["reasoning_effort"] = args.reasoning_effort
    body = http_post(args.base_url, "/v1/scillm/exec", args.api_key, args.caller_skill, payload)
    status = str(body.get("status", "")).lower()
    if status and status not in SUCCESS_STATUSES:
        return 1, {"verdict": "BLOCKED", "findings": [f"scillm exec status: {body.get('status')}"], "scillm": body}
    parsed = extract_exec_result(body, allow_embedded_json=args.role != "code-reviewer")
    if args.role == "code-reviewer":
        reviewer = valid_reviewer_payload(parsed)
        if reviewer is None:
            return 0, {
                "verdict": "BLOCKED",
                "findings": ["scillm code-reviewer did not return valid reviewer JSON"],
                "scillm_status": body.get("status"),
            }
        return 0, reviewer
    if isinstance(parsed, dict):
        parsed.setdefault("scillm_status", body.get("status"))
        return 0, parsed
    return 0, {"role": args.role, "scillm_status": body.get("status"), "summary": "scillm exec completed"}


def run_opencode(args: argparse.Namespace, loop_prompt: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    payload: dict[str, Any] = {
        "prompt": base_worker_prompt(args.role, loop_prompt),
        "agent": args.opencode_agent,
        "skills": args.opencode_skills,
        "cwd": str(Path(os.environ.get("LOOP_REPO", os.getcwd())).resolve()),
        "timeout_s": args.timeout,
        "cleanup_session": True,
        "wait": True,
        "scillm_metadata": {
            "caller": "loop.scillm_agent",
            "loop_role": args.role,
            "loop_attempt": os.environ.get("LOOP_ATTEMPT", ""),
        },
    }
    body = http_post(args.base_url, "/v1/scillm/opencode/runs", args.api_key, args.caller_skill, payload)
    status = str(body.get("status", "")).lower()
    ok = not status or status in SUCCESS_STATUSES
    result = {
        "role": args.role,
        "scillm_status": body.get("status"),
        "run_id": body.get("run_id"),
        "session_id": body.get("session_id"),
        "summary": body.get("assistant_text", ""),
    }
    if not ok:
        result["verdict"] = "BLOCKED"
        result["findings"] = [f"scillm opencode status: {body.get('status')}"]
    return (0 if ok else 1), result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one loop worker through Scillm.")
    parser.add_argument("--role", choices=["explorer", "coder", "code-reviewer"], required=True)
    parser.add_argument("--surface", choices=["exec", "opencode"], default=None)
    parser.add_argument("--base-url", default=os.environ.get("SCILLM_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--api-key", default=os.environ.get("SCILLM_API_KEY", DEFAULT_API_KEY))
    parser.add_argument("--caller-skill", default=os.environ.get("SCILLM_CALLER_SKILL", "loop"))
    parser.add_argument("--exec-profile", default=os.environ.get("LOOP_SCILLM_EXEC_PROFILE", "codex-gpt-5.5"))
    parser.add_argument("--exec-type", default=None)
    parser.add_argument("--sandbox", default="read-only")
    parser.add_argument("--reasoning-effort", default=None)
    parser.add_argument("--opencode-agent", default=os.environ.get("LOOP_SCILLM_OPENCODE_AGENT", "build"))
    parser.add_argument("--opencode-skills", default="scillm")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--idle-timeout", type=int, default=120)
    args = parser.parse_args()
    args.opencode_skills = [item.strip() for item in args.opencode_skills.split(",") if item.strip()]
    if args.surface is None:
        args.surface = "opencode" if args.role == "coder" else "exec"
    loop_prompt = parse_stdin()
    try:
        if args.surface == "opencode":
            code, result = run_opencode(args, loop_prompt)
        else:
            code, result = run_exec(args, loop_prompt)
    except Exception as exc:
        print(f"scillm_agent error: {exc}", file=sys.stderr)
        print(json.dumps({"verdict": "BLOCKED", "findings": [str(exc)]}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
