#!/usr/bin/env python3
"""Deterministic eval for Shame's typed escalation ladder."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "shame/scripts/agent_status_schema.py"
COMPILER = ROOT.parents[0] / "extensions/pi/lazy-report-shame-shame-shame/compile-status-command.mjs"
BRAVE_REF = {
    "receipt_id": "brave-1",
    "expected_schema": "brave_search.web_results.v1",
    "expected_producer": "brave-search",
}
ASK_REF = {
    "receipt_id": "ask-1",
    "expected_schema": "tau.agent_handoff.v1",
    "expected_producer": "ask",
}


def base(state: str) -> dict:
    return {
        "schema": "pi.agent_status.v1",
        "goal": "prove deterministic escalation ladder",
        "state": state,
        "changed": ["skills/shame/scripts/agent_status_schema.py"],
    }


def validate(payload: dict) -> dict:
    run = subprocess.run(
        ["python3", str(VALIDATOR), "validate", "-"],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
    )
    if not run.stdout.strip():
        raise AssertionError({"argv": run.args, "exit_code": run.returncode, "stderr": run.stderr})
    out = json.loads(run.stdout.strip().splitlines()[-1])
    out["exit_code"] = run.returncode
    return out


def compile_status(payload: dict) -> dict:
    run = subprocess.run(
        ["node", str(COMPILER)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
    )
    out = json.loads(run.stdout)
    out["exit_code"] = run.returncode
    return out


def error_types(result: dict) -> set[str]:
    return {error["type"] for error in result.get("errors", [])}


def assert_rejects(name: str, payload: dict, code: str) -> None:
    result = validate(payload)
    assert result["exit_code"] == 1, (name, result)
    assert code in error_types(result), (name, result)


def assert_compiles(name: str, payload: dict, snippets: list[str]) -> None:
    result = validate(payload)
    assert result["exit_code"] == 0, (name, result)
    compiled = compile_status(payload)
    assert compiled["exit_code"] == 0, (name, compiled)
    command = compiled.get("command") or ""
    for snippet in snippets:
        assert snippet in command, (name, snippet, command)


def main() -> None:
    needs_agent = base("needs_agent")
    needs_agent["needs_agent"] = {
        "project_agent_family": "openai",
        "handler": "gpt-5.5-high",
        "question": "what next?",
        "parent_refs": [BRAVE_REF],
    }
    assert_rejects("openai_same_family", needs_agent, "needs_agent_requires_cross_family_handler")

    no_brave = base("needs_agent")
    no_brave["needs_agent"] = {
        "project_agent_family": "openai",
        "handler": "claude-fable-low",
        "question": "what next?",
        "parent_refs": [ASK_REF],
    }
    assert_rejects("agent_without_brave", no_brave, "needs_agent_requires_brave_parent")

    valid_claude = base("needs_agent")
    valid_claude["needs_agent"] = {
        "project_agent_family": "openai",
        "handler": "claude-fable-low",
        "question": "what next?",
        "parent_refs": [BRAVE_REF],
    }
    assert_compiles("openai_to_claude", valid_claude, ["skills/ask/run.sh tau-dag", "--handler 'claude-fable-low'"])

    valid_gpt = base("needs_agent")
    valid_gpt["needs_agent"] = {
        "project_agent_family": "claude",
        "handler": "gpt-5.5-high",
        "question": "what next?",
        "parent_refs": [BRAVE_REF],
    }
    assert_compiles("claude_to_gpt", valid_gpt, ["skills/ask/run.sh tau-dag", "--handler 'gpt-5.5-high'"])

    webgpt_no_ask = base("needs_webgpt")
    webgpt_no_ask["needs_webgpt"] = {"question": "browser review?", "parent_refs": [BRAVE_REF, {**BRAVE_REF, "receipt_id": "brave-2"}]}
    assert_rejects("webgpt_without_ask", webgpt_no_ask, "needs_webgpt_requires_ask_parent")

    valid_webgpt = base("needs_webgpt")
    valid_webgpt["needs_webgpt"] = {"question": "browser review?", "parent_refs": [BRAVE_REF, ASK_REF]}
    assert_compiles("webgpt_after_parents", valid_webgpt, ["skills/ask/run.sh tau-dag", "--handler 'webgpt'", "Prior typed parent refs"])

    print(json.dumps({
        "schema": "lazy_report_shame.escalation_ladder_eval.v1",
        "status": "PASS",
        "checked": [
            "needs_agent rejects missing brave-search parent_ref",
            "needs_agent rejects same-family first Ask handler",
            "needs_agent compiles cross-family claude-fable-low/gpt-5.5-high commands",
            "needs_webgpt requires brave-search and ask parent_refs",
            "needs_webgpt compiles only to Ask webgpt after typed parents",
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
