#!/usr/bin/env python3
"""Deterministic eval for Shame's typed escalation ladder."""
from __future__ import annotations

import json
import hashlib
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "shame/scripts/agent_status_schema.py"
COMPILER = ROOT.parents[0] / "extensions/pi/lazy-report-shame-shame-shame/compile-status-command.mjs"
GOAL_HASH = "sha256:" + hashlib.sha256(b"shame escalation parent lineage").hexdigest()


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def base(state: str) -> dict:
    return {
        "schema": "pi.agent_status.v1",
        "goal": "prove deterministic escalation ladder",
        "goal_hash": GOAL_HASH,
        "state": state,
        "changed": ["skills/shame/scripts/agent_status_schema.py"],
    }


def envelope_ref(ref: dict) -> dict:
    return {
        "receipt_id": ref["receipt_id"],
        "expected_schema": ref["expected_schema"],
        "expected_producer": ref["expected_producer"],
        "digest": ref["digest"],
    }


def write_envelope(
    work: Path,
    *,
    receipt_id: str,
    producer: str,
    payload_schema: str,
    goal_hash: str = GOAL_HASH,
    parent_refs: list[dict] | None = None,
) -> dict:
    path = work / f"{receipt_id}.json"
    payload = {
        "schema": "pi.receipt_envelope.v1",
        "receipt_id": receipt_id,
        "payload_schema": payload_schema,
        "producer": producer,
        "emitted_at": "2026-09-07T00:00:00+00:00",
        "goal_hash": goal_hash,
        "parent_refs": parent_refs or [],
        "payload": {"schema": payload_schema, "status": "PASS"},
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "receipt_id": receipt_id,
        "receipt_path": str(path),
        "expected_schema": payload_schema,
        "expected_producer": producer,
        "digest": digest(path),
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


def assert_compiles(name: str, payload: dict, snippets: list[str], excludes: list[str] | None = None) -> None:
    result = validate(payload)
    assert result["exit_code"] == 0, (name, result)
    compiled = compile_status(payload)
    assert compiled["exit_code"] == 0, (name, compiled)
    command = compiled.get("command") or ""
    for snippet in snippets:
        assert snippet in command, (name, snippet, command)
    for snippet in excludes or []:
        assert snippet not in command, (name, snippet, command)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="shame-escalation-parent-lineage-") as raw:
        work = Path(raw)
        needs_brave = base("needs_brave_search")
        needs_brave["needs_brave_search"] = {"queries": ["first brave query", "second brave query"]}
        assert_compiles(
            "brave_all_queries",
            needs_brave,
            [
                "skills/brave-search/run.sh web 'first brave query' --count 5",
                "skills/brave-search/run.sh web 'second brave query' --count 5",
            ],
        )
        unbound_brave = base("needs_brave_search")
        unbound_brave.pop("goal_hash")
        unbound_brave["needs_brave_search"] = {"queries": ["unbound brave query"]}
        assert_rejects("brave_without_goal_hash", unbound_brave, "escalation_requires_goal_hash")

        brave_ref = write_envelope(
            work,
            receipt_id="brave-1",
            producer="brave-search",
            payload_schema="brave_search.web_results.v1",
        )
        brave_ref_2 = write_envelope(
            work,
            receipt_id="brave-2",
            producer="brave-search",
            payload_schema="brave_search.web_results.v1",
        )
        ask_ref = write_envelope(
            work,
            receipt_id="ask-1",
            producer="ask",
            payload_schema="tau.agent_handoff.v1",
            parent_refs=[envelope_ref(brave_ref)],
        )
        foreign_ask_ref = write_envelope(
            work,
            receipt_id="ask-foreign",
            producer="ask",
            payload_schema="tau.agent_handoff.v1",
            parent_refs=[],
        )
        wrong_goal_ref = write_envelope(
            work,
            receipt_id="brave-wrong-goal",
            producer="brave-search",
            payload_schema="brave_search.web_results.v1",
            goal_hash="sha256:" + "1" * 64,
        )
        wrong_brave_schema_ref = write_envelope(
            work,
            receipt_id="brave-wrong-schema",
            producer="brave-search",
            payload_schema="lazy_report_shame.not_brave_results.v1",
        )
        wrong_ask_schema_ref = write_envelope(
            work,
            receipt_id="ask-wrong-schema",
            producer="ask",
            payload_schema="lazy_report_shame.not_ask_handoff.v1",
            parent_refs=[envelope_ref(brave_ref)],
        )

        needs_agent = base("needs_agent")
        needs_agent["needs_agent"] = {
            "project_agent_family": "openai",
            "handler": "gpt-5.5-high",
            "question": "what next?",
            "parent_refs": [brave_ref],
        }
        assert_rejects("openai_same_family", needs_agent, "needs_agent_requires_cross_family_handler")

        no_brave = base("needs_agent")
        no_brave["needs_agent"] = {
            "project_agent_family": "openai",
            "handler": "claude-fable-low",
            "question": "what next?",
            "parent_refs": [ask_ref],
        }
        assert_rejects("agent_without_brave", no_brave, "needs_agent_requires_brave_parent")

        forged_producer = {
            **ask_ref,
            "expected_producer": "brave-search",
        }
        producer_forged = base("needs_agent")
        producer_forged["needs_agent"] = {
            "project_agent_family": "openai",
            "handler": "claude-fable-low",
            "question": "what next?",
            "parent_refs": [forged_producer],
        }
        assert_rejects("declared_producer_is_not_authority", producer_forged, "parent_ref_producer_mismatch")

        forged_schema = {
            **ask_ref,
            "expected_schema": "brave_search.web_results.v1",
        }
        schema_forged = base("needs_agent")
        schema_forged["needs_agent"] = {
            "project_agent_family": "openai",
            "handler": "claude-fable-low",
            "question": "what next?",
            "parent_refs": [forged_schema],
        }
        assert_rejects("declared_schema_is_not_authority", schema_forged, "parent_ref_schema_mismatch")

        wrong_resolved_brave_schema = base("needs_agent")
        wrong_resolved_brave_schema["needs_agent"] = {
            "project_agent_family": "openai",
            "handler": "claude-fable-low",
            "question": "what next?",
            "parent_refs": [wrong_brave_schema_ref],
        }
        assert_rejects(
            "resolved_brave_schema_must_be_web_results",
            wrong_resolved_brave_schema,
            "needs_agent_requires_brave_parent",
        )

        wrong_receipt_id = {**brave_ref, "receipt_id": "brave-forged"}
        receipt_id_forged = base("needs_agent")
        receipt_id_forged["needs_agent"] = {
            "project_agent_family": "openai",
            "handler": "claude-fable-low",
            "question": "what next?",
            "parent_refs": [wrong_receipt_id],
        }
        assert_rejects("receipt_id_mismatch", receipt_id_forged, "parent_ref_receipt_id_mismatch")

        wrong_digest = {**brave_ref, "digest": "sha256:" + "0" * 64}
        digest_forged = base("needs_agent")
        digest_forged["needs_agent"] = {
            "project_agent_family": "openai",
            "handler": "claude-fable-low",
            "question": "what next?",
            "parent_refs": [wrong_digest],
        }
        assert_rejects("digest_mismatch", digest_forged, "parent_ref_digest_mismatch")

        wrong_goal = base("needs_agent")
        wrong_goal["needs_agent"] = {
            "project_agent_family": "openai",
            "handler": "claude-fable-low",
            "question": "what next?",
            "parent_refs": [wrong_goal_ref],
        }
        assert_rejects("goal_lineage_mismatch", wrong_goal, "parent_ref_goal_hash_mismatch")

        unbound_goal = base("needs_agent")
        unbound_goal.pop("goal_hash")
        unbound_goal["needs_agent"] = {
            "project_agent_family": "openai",
            "handler": "claude-fable-low",
            "question": "what next?",
            "parent_refs": [brave_ref],
        }
        assert_rejects("agent_without_goal_hash", unbound_goal, "escalation_requires_goal_hash")

        valid_claude = base("needs_agent")
        valid_claude["needs_agent"] = {
            "project_agent_family": "openai",
            "handler": "claude-fable-low",
            "question": "what next?",
            "parent_refs": [brave_ref],
        }
        assert_compiles("openai_to_claude", valid_claude, ["skills/ask/run.sh tau-dag", "--handler 'claude-fable-low'"])

        valid_gpt = base("needs_agent")
        valid_gpt["needs_agent"] = {
            "project_agent_family": "claude",
            "handler": "gpt-5.5-high",
            "question": "what next?",
            "parent_refs": [brave_ref],
        }
        assert_compiles("claude_to_gpt", valid_gpt, ["skills/ask/run.sh tau-dag", "--handler 'gpt-5.5-high'"])

        webgpt_no_ask = base("needs_webgpt")
        webgpt_no_ask["needs_webgpt"] = {"question": "browser review?", "parent_refs": [brave_ref, brave_ref_2]}
        assert_rejects("webgpt_without_ask", webgpt_no_ask, "needs_webgpt_requires_ask_parent")

        webgpt_foreign_ask = base("needs_webgpt")
        webgpt_foreign_ask["needs_webgpt"] = {"question": "browser review?", "parent_refs": [brave_ref, foreign_ask_ref]}
        assert_rejects(
            "webgpt_ask_not_descended_from_brave",
            webgpt_foreign_ask,
            "needs_webgpt_requires_ask_descended_from_brave",
        )

        webgpt_wrong_ask_schema = base("needs_webgpt")
        webgpt_wrong_ask_schema["needs_webgpt"] = {
            "question": "browser review?",
            "parent_refs": [brave_ref, wrong_ask_schema_ref],
        }
        assert_rejects(
            "webgpt_ask_schema_must_be_handoff",
            webgpt_wrong_ask_schema,
            "needs_webgpt_requires_ask_parent",
        )

        webgpt_wrong_brave_schema = base("needs_webgpt")
        webgpt_wrong_brave_schema["needs_webgpt"] = {
            "question": "browser review?",
            "parent_refs": [wrong_brave_schema_ref, ask_ref],
        }
        assert_rejects(
            "webgpt_brave_schema_must_be_web_results",
            webgpt_wrong_brave_schema,
            "needs_webgpt_requires_brave_parent",
        )

        valid_webgpt = base("needs_webgpt")
        valid_webgpt["needs_webgpt"] = {"question": "browser review?", "parent_refs": [brave_ref, ask_ref]}
        assert_compiles(
            "webgpt_after_parents",
            valid_webgpt,
            ["skills/ask/run.sh tau-dag", "--handler 'webgpt'", "--attach-file"],
            excludes=["Prior typed parent refs"],
        )

    print(json.dumps({
        "schema": "lazy_report_shame.escalation_ladder_eval.v1",
        "status": "PASS",
        "checked": [
            "needs_agent resolves parent_ref receipts before accepting brave-search lineage",
            "declared parent_ref producer/schema strings are not authority",
            "parent_ref producer mismatches are rejected",
            "parent_ref receipt_id mismatches are rejected",
            "parent_ref digest mismatches are rejected",
            "parent_ref goal_hash mismatches are rejected",
            "resolved brave-search parents must use brave_search.web_results.v1",
            "resolved ask parents must use tau.agent_handoff.v1",
            "escalation commands require an active goal_hash",
            "needs_brave_search compiles every requested Brave query",
            "needs_agent rejects same-family first Ask handler",
            "needs_agent compiles cross-family claude-fable-low/gpt-5.5-high commands",
            "needs_webgpt requires a resolved Ask receipt descended from the Brave evidence",
            "needs_webgpt preserves typed parent_refs as structured attachment data, not prompt prose",
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
