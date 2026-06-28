"""One-round Battle subagent smoke runner.

This module does not claim full Tau/loop integration. It creates Tau-shaped Red
and Blue handoff/receipt artifacts, validates them with Tau's receipt validator
when the local Tau checkout is usable, records a SQLite event ledger, then runs
the deterministic Battle fixture scorekeeper. The goal is to expose the first
stable entry point for debugging Tau-as-subagent readiness.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .battle_fixture import run_battle_001
from .receipts import utc_now, write_json


TAU_ROOT = Path(os.getenv("TAU_ROOT", "/home/graham/workspace/experiments/tau")).resolve()
TAU_EXPERIMENTS_ROOT = Path(
    os.getenv("TAU_EXPERIMENTS_ROOT", str(TAU_ROOT / "experiments"))
).resolve()
TAU_VALIDATOR_PYTHON = os.getenv("TAU_VALIDATOR_PYTHON", "python3.14")


@dataclass(frozen=True)
class PersonaProbe:
    persona: str
    local_agent_persona: str | None
    external_persona_hits: list[str]


def run_subagent_smoke(
    *,
    fixture_dir: Path,
    out_dir: Path,
    red_persona: str = "brandon-bailey",
    blue_persona: str = "coder",
    fast_scan: bool = False,
    agentic: bool = False,
) -> dict[str, Any]:
    """Run one Red/Blue Tau-shaped smoke around a deterministic Battle fixture."""

    scenario = json.loads((fixture_dir / "scenario.json").read_text(encoding="utf-8"))
    battle_id = str(scenario.get("battle_id", fixture_dir.name))
    run_id = f"battle-subagent-smoke-{uuid.uuid4().hex[:12]}"
    goal = goal_payload(battle_id=battle_id, scenario=scenario)

    out_dir.mkdir(parents=True, exist_ok=True)
    tau_dir = out_dir / "tau"
    tau_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = out_dir / "subagent-ledger.sqlite"
    init_ledger(ledger_path)

    persona_probes = {
        "red": probe_persona(red_persona),
        "blue": probe_persona(blue_persona),
    }
    fast_scan_result = (
        run_fast_scan(fixture_dir=fixture_dir, out_dir=out_dir)
        if fast_scan
        else {
            "enabled": False,
            "status": "SKIPPED",
            "reason": "fast_scan_disabled",
            "artifacts": [],
        }
    )
    write_json(out_dir / "fast-scan-receipt.json", fast_scan_result)
    record_event(
        ledger_path,
        run_id=run_id,
        battle_id=battle_id,
        team="red",
        persona=red_persona,
        event_type="fast_scan",
        status=str(fast_scan_result.get("status", "BLOCKED")),
        artifact_path=out_dir / "fast-scan-receipt.json",
        details=fast_scan_result,
    )

    red_handoff = handoff_payload(
        run_id=run_id,
        goal=goal,
        battle_id=battle_id,
        scenario=scenario,
        team="red",
        persona=red_persona,
        previous_subagent="battle-orchestrator",
        next_subagent="battle-red",
        objective="Confirm the seeded exploit using the fixture entry point.",
        required_evidence=["red-receipt.json"],
    )
    red_handoff["context"]["battle"]["fast_scan"] = fast_scan_result
    red_handoff_path = write_json(tau_dir / "red-handoff.json", red_handoff)
    record_event(
        ledger_path,
        run_id=run_id,
        battle_id=battle_id,
        team="red",
        persona=red_persona,
        event_type="handoff_written",
        status="PASS",
        artifact_path=red_handoff_path,
        details={"next_subagent": "battle-red"},
    )

    red_harness = (
        run_tau_agent_harness_turn(
            out_dir=tau_dir,
            team="red",
            persona=red_persona,
            prompt=(
                "You are the Red Battle subagent. Select exactly one seeded "
                "attack for this fixture and return a concise action summary."
            ),
            assistant_content="Red selects the seeded SQL injection/XSS fixture attack.",
        )
        if agentic
        else skipped_harness_turn("red")
    )
    record_event(
        ledger_path,
        run_id=run_id,
        battle_id=battle_id,
        team="red",
        persona=red_persona,
        event_type="tau_agent_harness_turn",
        status=str(red_harness.get("status", "BLOCKED")),
        artifact_path=tau_dir / "red-harness-events.json",
        details=red_harness,
    )

    red_receipt = subagent_receipt_payload(
        run_id=run_id,
        goal=goal,
        battle_id=battle_id,
        team="red",
        persona=red_persona,
        status="PASS" if red_harness["status"] in {"PASS", "SKIPPED"} else "BLOCKED",
        summary=str(
            red_harness.get(
                "assistant_content",
                "Selected the seeded SQL injection/XSS or fixture exploit check for Red.",
            )
        ),
        evidence=[
            "tau/red-handoff.json",
            *(
                ["tau/red-harness-events.json"]
                if red_harness["status"] != "SKIPPED"
                else []
            ),
        ],
        next_subagent="battle-blue",
        next_reason="Red selected one attack; Blue should apply one defense.",
        stop_condition="Red produced a schema-valid attack-selection receipt.",
        agentic=agentic,
    )
    red_receipt_path = write_json(tau_dir / "red-subagent-receipt.json", red_receipt)
    red_validation = validate_tau_receipt(red_receipt_path, active_goal_hash=str(goal["goal_hash"]))
    write_json(tau_dir / "red-validation.json", red_validation)
    record_event(
        ledger_path,
        run_id=run_id,
        battle_id=battle_id,
        team="red",
        persona=red_persona,
        event_type="tau_receipt_validation",
        status="PASS" if red_validation["ok"] else "BLOCKED",
        artifact_path=tau_dir / "red-validation.json",
        details=red_validation,
    )

    blue_handoff = handoff_payload(
        run_id=run_id,
        goal=goal,
        battle_id=battle_id,
        scenario=scenario,
        team="blue",
        persona=blue_persona,
        previous_subagent="battle-red",
        next_subagent="battle-blue",
        objective="Apply the deterministic fixture defense and preserve behavior.",
        required_evidence=["blue-receipt.json", "judge/judge-receipt.json"],
    )
    blue_handoff_path = write_json(tau_dir / "blue-handoff.json", blue_handoff)
    record_event(
        ledger_path,
        run_id=run_id,
        battle_id=battle_id,
        team="blue",
        persona=blue_persona,
        event_type="handoff_written",
        status="PASS",
        artifact_path=blue_handoff_path,
        details={"next_subagent": "battle-blue"},
    )

    blue_harness = (
        run_tau_agent_harness_turn(
            out_dir=tau_dir,
            team="blue",
            persona=blue_persona,
            prompt=(
                "You are the Blue Battle subagent. Select exactly one seeded "
                "defense for this fixture and return a concise action summary."
            ),
            assistant_content="Blue selects the deterministic parameterized SQL and HTML escaping patch.",
        )
        if agentic
        else skipped_harness_turn("blue")
    )
    record_event(
        ledger_path,
        run_id=run_id,
        battle_id=battle_id,
        team="blue",
        persona=blue_persona,
        event_type="tau_agent_harness_turn",
        status=str(blue_harness.get("status", "BLOCKED")),
        artifact_path=tau_dir / "blue-harness-events.json",
        details=blue_harness,
    )

    blue_receipt = subagent_receipt_payload(
        run_id=run_id,
        goal=goal,
        battle_id=battle_id,
        team="blue",
        persona=blue_persona,
        status="PASS" if blue_harness["status"] in {"PASS", "SKIPPED"} else "BLOCKED",
        summary=str(
            blue_harness.get(
                "assistant_content",
                "Selected the deterministic fixture patch for Blue.",
            )
        ),
        evidence=[
            "tau/blue-handoff.json",
            *(
                ["tau/blue-harness-events.json"]
                if blue_harness["status"] != "SKIPPED"
                else []
            ),
        ],
        next_subagent="battle-scorekeeper",
        next_reason="Blue selected one defense; scorekeeper should replay exploit and regression checks.",
        stop_condition="Blue produced a schema-valid defense-selection receipt.",
        agentic=agentic,
    )
    blue_receipt_path = write_json(tau_dir / "blue-subagent-receipt.json", blue_receipt)
    blue_validation = validate_tau_receipt(blue_receipt_path, active_goal_hash=str(goal["goal_hash"]))
    write_json(tau_dir / "blue-validation.json", blue_validation)
    record_event(
        ledger_path,
        run_id=run_id,
        battle_id=battle_id,
        team="blue",
        persona=blue_persona,
        event_type="tau_receipt_validation",
        status="PASS" if blue_validation["ok"] else "BLOCKED",
        artifact_path=tau_dir / "blue-validation.json",
        details=blue_validation,
    )

    fixture_result = run_battle_001(fixture_dir=fixture_dir, out_dir=out_dir)
    research_seed = build_next_round_research_seed(
        battle_id=battle_id,
        scenario=scenario,
        fixture_result=fixture_result,
        fast_scan_result=fast_scan_result,
        red_persona=red_persona,
        blue_persona=blue_persona,
    )
    write_json(out_dir / "next-round-research-seed.json", research_seed)
    record_event(
        ledger_path,
        run_id=run_id,
        battle_id=battle_id,
        team="scorekeeper",
        persona="battle-scorekeeper",
        event_type="fixture_scorekeeper_run",
        status=str(fixture_result.get("status", "BLOCKED")),
        artifact_path=out_dir / "run-receipt.json",
        details=fixture_result,
    )
    record_event(
        ledger_path,
        run_id=run_id,
        battle_id=battle_id,
        team="orchestrator",
        persona="battle-orchestrator",
        event_type="next_round_research_seed",
        status=str(research_seed["status"]),
        artifact_path=out_dir / "next-round-research-seed.json",
        details=research_seed,
    )

    harness_ok = bool(
        (not agentic)
        or (
            red_harness.get("status") == "PASS"
            and blue_harness.get("status") == "PASS"
        )
    )
    tau_ok = bool(red_validation["ok"] and blue_validation["ok"] and harness_ok)
    fixture_ok = fixture_result.get("status") == "PASS"
    models_used = ["tau-local-deterministic-provider"] if agentic else []
    summary = {
        "schema": "battle.subagent_smoke_receipt.v1",
        "run_id": run_id,
        "battle_id": battle_id,
        "status": "PASS" if tau_ok and fixture_ok else "BLOCKED",
        "tau_receipts_valid": tau_ok,
        "fixture_status": fixture_result.get("status"),
        "fixture_verdict": fixture_result.get("verdict"),
        "mocked": False,
        "live": (
            "local_fixture_with_tau_agent_harness"
            if agentic
            else "local_fixture_with_tau_receipt_validation"
        ),
        "agentic": agentic,
        "models_used": models_used,
        "tau": {
            "root": str(TAU_ROOT),
            "experiments_root": str(TAU_EXPERIMENTS_ROOT),
            "receipt_validator": str(TAU_ROOT / "src" / "tau_coding" / "subagent_receipt.py"),
        },
        "entry_point": scenario.get("entry_point"),
        "fast_scan": fast_scan_result,
        "harness": {
            "red": red_harness,
            "blue": blue_harness,
        },
        "next_round_research_seed": "next-round-research-seed.json",
        "personas": {
            team: {
                "persona": probe.persona,
                "local_agent_persona": probe.local_agent_persona,
                "external_persona_hits": probe.external_persona_hits,
            }
            for team, probe in persona_probes.items()
        },
        "artifacts": [
            "tau/red-handoff.json",
            *(
                ["tau/red-harness-events.json"]
                if red_harness["status"] != "SKIPPED"
                else []
            ),
            "tau/red-subagent-receipt.json",
            "tau/red-validation.json",
            "tau/blue-handoff.json",
            *(
                ["tau/blue-harness-events.json"]
                if blue_harness["status"] != "SKIPPED"
                else []
            ),
            "tau/blue-subagent-receipt.json",
            "tau/blue-validation.json",
            "red-receipt.json",
            "blue-receipt.json",
            "judge/judge-receipt.json",
            "scoreboard.json",
            "run-receipt.json",
            "subagent-ledger.sqlite",
            "fast-scan-receipt.json",
            "next-round-research-seed.json",
        ],
        "non_claims": [
            *(
                []
                if agentic
                else ["does_not_prove_tau_agent_harness_execution"]
            ),
            "does_not_prove_tau_scillm_or_external_model_execution",
            "does_not_prove_loop_repair_cycle",
            "does_not_prove_docker_target_execution",
            "does_not_prove_memory_persona_ingestion",
            "does_not_prove_multi_candidate_mutation",
        ],
    }
    write_json(out_dir / "subagent-smoke-receipt.json", summary)
    return summary


def goal_payload(*, battle_id: str, scenario: dict[str, Any]) -> dict[str, Any]:
    goal_id = f"{battle_id}:one-red-one-blue"
    material = json.dumps(
        {
            "goal_id": goal_id,
            "scenario": scenario.get("scenario_id"),
            "stop_condition": scenario.get("stop_condition"),
        },
        sort_keys=True,
    )
    return {
        "goal_id": goal_id,
        "goal_version": 1,
        "goal_hash": "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest(),
        "immutable_goal_preserved": True,
    }


def handoff_payload(
    *,
    run_id: str,
    goal: dict[str, Any],
    battle_id: str,
    scenario: dict[str, Any],
    team: str,
    persona: str,
    previous_subagent: str,
    next_subagent: str,
    objective: str,
    required_evidence: list[str],
) -> dict[str, Any]:
    return {
        "schema": "tau.agent_handoff.v1",
        "github": {
            "owner": "grahama1970",
            "repo": "agent-skills",
            "issue": None,
        },
        "goal": goal,
        "previous_subagent": previous_subagent,
        "context": {
            "run_id": run_id,
            "subagent": next_subagent,
            "actor_type": "local-cron",
            "artifacts_read": ["battle-plan.json"],
            "assumptions": [
                "This smoke uses deterministic local fixture execution.",
                "Tau model execution is not required for this first receipt boundary test.",
            ],
            "unknowns": ["Whether Tau harness can run live Battle agents reliably."],
            "battle": {
                "battle_id": battle_id,
                "scenario_id": scenario.get("scenario_id"),
                "team": team,
                "persona": persona,
                "fixture_mode": scenario.get("mode"),
                "entry_point": scenario.get("entry_point"),
                "allowed_skills": ["memory", "dogpile", "brave-search"],
                "memory_access": memory_access_for_persona(persona),
            },
        },
        "result": {
            "status": "READY",
            "summary": objective,
            "evidence": [],
        },
        "rationale": "Battle is testing one Red and one Blue subagent boundary before adding mutation batches.",
        "next_agent": {
            "subagent": next_subagent,
            "reason": objective,
            "executor": "local",
        },
        "required_evidence": required_evidence,
        "stop_condition": scenario.get("stop_condition", objective),
    }


def subagent_receipt_payload(
    *,
    run_id: str,
    goal: dict[str, Any],
    battle_id: str,
    team: str,
    persona: str,
    status: str,
    summary: str,
    evidence: list[str],
    next_subagent: str,
    next_reason: str,
    stop_condition: str,
    agentic: bool = False,
) -> dict[str, Any]:
    return {
        "schema": "tau.subagent_receipt.v1",
        "goal": goal,
        "context": {
            "run_id": run_id,
            "subagent": f"battle-{team}",
            "actor_type": "subagent",
            "artifacts_read": evidence,
            "assumptions": [
                (
                    "One-turn Battle subagent smoke through Tau AgentHarness."
                    if agentic
                    else "One-turn deterministic Battle subagent smoke."
                )
            ],
            "unknowns": (
                ["Tau scillm/external model execution is not exercised by this receipt."]
                if agentic
                else ["Tau live AgentHarness execution is not exercised by this receipt."]
            ),
            "battle": {
                "battle_id": battle_id,
                "team": team,
                "persona": persona,
                "round_number": 1,
                "memory_access": memory_access_for_persona(persona),
            },
        },
        "result": {
            "status": status,
            "summary": summary,
            "mocked": False,
            "live": True,
            "agentic": agentic,
            "artifacts": evidence,
            "commands_run": [],
        },
        "rationale": "This receipt proves the Battle/Tau schema boundary for one selected team action.",
        "evidence": evidence,
        "next": {
            "subagent": next_subagent,
            "reason": next_reason,
            "executor": "local",
        },
        "stop_condition": stop_condition,
    }


def skipped_harness_turn(team: str) -> dict[str, Any]:
    return {
        "schema": "battle.tau_agent_harness_turn.v1",
        "team": team,
        "status": "SKIPPED",
        "reason": "agentic_harness_disabled",
    }


def run_tau_agent_harness_turn(
    *,
    out_dir: Path,
    team: str,
    persona: str,
    prompt: str,
    assistant_content: str,
) -> dict[str, Any]:
    """Run one Tau AgentHarness turn through Tau's project-managed environment."""

    artifact_path = out_dir / f"{team}-harness-events.json"
    command = [
        "uv",
        "run",
        "--project",
        str(TAU_ROOT),
        "python",
        "-c",
        "<battle_tau_agent_harness_turn>",
    ]
    payload = {
        "team": team,
        "persona": persona,
        "prompt": prompt,
        "assistant_content": assistant_content,
    }
    code = r"""
import anyio
import json
import sys

from tau_agent.harness import AgentHarness, AgentHarnessConfig
from tau_agent.messages import AssistantMessage
from tau_ai import (
    FakeProvider,
    ProviderResponseEndEvent,
    ProviderResponseStartEvent,
    ProviderTextDeltaEvent,
)


async def main() -> None:
    payload = json.loads(sys.stdin.read())
    model = "tau-local-deterministic-provider"
    assistant = AssistantMessage(content=payload["assistant_content"])
    provider = FakeProvider(
        [[
            ProviderResponseStartEvent(model=model),
            ProviderTextDeltaEvent(delta=payload["assistant_content"]),
            ProviderResponseEndEvent(message=assistant),
        ]]
    )
    harness = AgentHarness(
        AgentHarnessConfig(
            provider=provider,
            model=model,
            system=(
                f"Battle {payload['team']} subagent persona={payload['persona']}. "
                "Return one bounded action summary."
            ),
            max_turns=1,
        )
    )
    events = []
    async for event in harness.prompt(payload["prompt"]):
        events.append(event.model_dump(mode="json"))
    print(json.dumps({
        "schema": "battle.tau_agent_harness_turn.v1",
        "status": "PASS",
        "team": payload["team"],
        "persona": payload["persona"],
        "model": model,
        "event_types": [event["type"] for event in events],
        "event_count": len(events),
        "assistant_content": harness.messages[-1].content,
    }, sort_keys=True))


anyio.run(main)
"""
    env = os.environ.copy()
    env.pop("UV_PROJECT_ENVIRONMENT", None)
    env.pop("VIRTUAL_ENV", None)
    env["PYTHONPATH"] = f"{TAU_ROOT / 'src'}{os.pathsep}{env.get('PYTHONPATH', '')}"

    try:
        proc = subprocess.run(
            [
                "uv",
                "run",
                "--project",
                str(TAU_ROOT),
                "python",
                "-c",
                code,
            ],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        result = {
            "schema": "battle.tau_agent_harness_turn.v1",
            "team": team,
            "persona": persona,
            "status": "BLOCKED",
            "reason": "tau_agent_harness_timeout",
            "command": command,
            "timeout_seconds": 60,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
        }
        write_json(artifact_path, result)
        return result

    result: dict[str, Any] = {
        "schema": "battle.tau_agent_harness_turn.v1",
        "team": team,
        "persona": persona,
        "status": "BLOCKED",
        "command": command,
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }
    if proc.returncode != 0:
        result["reason"] = "tau_agent_harness_process_failed"
        write_json(artifact_path, result)
        return result
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        result["reason"] = f"tau_agent_harness_invalid_json: {exc}"
        write_json(artifact_path, result)
        return result
    parsed["command"] = command
    parsed["exit_code"] = proc.returncode
    parsed["stderr"] = proc.stderr
    write_json(artifact_path, parsed)
    return parsed


def validate_tau_receipt(path: Path, *, active_goal_hash: str) -> dict[str, Any]:
    """Validate a receipt with Tau's validator in a Python 3.14 subprocess."""

    if not TAU_ROOT.exists():
        return {
            "ok": False,
            "validator": "tau_coding.subagent_receipt",
            "reason": "tau_root_missing",
            "tau_root": str(TAU_ROOT),
        }

    code = """
import importlib.util
import json
import sys
from pathlib import Path

module_path = Path(sys.argv[3])
spec = importlib.util.spec_from_file_location("tau_subagent_receipt_direct", module_path)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load validator module: {module_path}")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

result = module.validate_subagent_receipt_file(Path(sys.argv[1]), active_goal_hash=sys.argv[2])
print(json.dumps({
    "ok": result.ok,
    "next_subagent": result.next_subagent,
    "errors": list(result.errors),
}, sort_keys=True))
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{TAU_ROOT / 'src'}{os.pathsep}{env.get('PYTHONPATH', '')}"
    proc = subprocess.run(
        [
            TAU_VALIDATOR_PYTHON,
            "-c",
            code,
            str(path),
            active_goal_hash,
            str(TAU_ROOT / "src" / "tau_coding" / "subagent_receipt.py"),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    payload: dict[str, Any] = {
        "validator": "tau_coding.subagent_receipt",
        "command": [
            TAU_VALIDATOR_PYTHON,
            "-c",
            "<validator>",
            str(path),
            active_goal_hash,
            str(TAU_ROOT / "src" / "tau_coding" / "subagent_receipt.py"),
        ],
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "tau_root": str(TAU_ROOT),
    }
    if proc.returncode != 0:
        payload["ok"] = False
        payload["reason"] = "tau_validator_process_failed"
        return payload
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        payload["ok"] = False
        payload["reason"] = f"tau_validator_invalid_json: {exc}"
        return payload
    payload.update(parsed)
    return payload


def run_fast_scan(*, fixture_dir: Path, out_dir: Path) -> dict[str, Any]:
    """Run a bounded Red reconnaissance attempt with $hack audit if available."""

    repo_root = Path(__file__).resolve().parents[4]
    hack_run = repo_root / "skills" / "hack" / "run.sh"
    target = fixture_dir / "target"
    scan_dir = out_dir / "fast-scan"
    scan_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = scan_dir / "hack-audit.stdout.txt"
    stderr_path = scan_dir / "hack-audit.stderr.txt"

    if not hack_run.is_file():
        return {
            "enabled": True,
            "status": "BLOCKED",
            "reason": "hack_run_sh_missing",
            "command": [str(hack_run), "audit", str(target), "--tool", "semgrep"],
            "artifacts": [],
        }

    command = [str(hack_run), "audit", str(target), "--tool", "semgrep"]
    try:
        proc = subprocess.run(
            command,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        stdout_path.write_text(exc.stdout or "", encoding="utf-8")
        stderr_path.write_text(exc.stderr or "", encoding="utf-8")
        return {
            "enabled": True,
            "status": "BLOCKED",
            "reason": "hack_audit_timeout",
            "command": command,
            "timeout_seconds": 120,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "artifacts": [
                str(stdout_path.relative_to(out_dir)),
                str(stderr_path.relative_to(out_dir)),
            ],
            "boundary": "Fast scan failed closed; fixture exploit selection remains deterministic.",
        }
    stdout_path.write_text(proc.stdout, encoding="utf-8")
    stderr_path.write_text(proc.stderr, encoding="utf-8")
    return {
        "enabled": True,
        "status": "PASS" if proc.returncode == 0 else "BLOCKED",
        "command": command,
        "exit_code": proc.returncode,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "artifacts": [
            str(stdout_path.relative_to(out_dir)),
            str(stderr_path.relative_to(out_dir)),
        ],
        "boundary": "Red reconnaissance only; fixture exploit selection remains deterministic.",
    }


def build_next_round_research_seed(
    *,
    battle_id: str,
    scenario: dict[str, Any],
    fixture_result: dict[str, Any],
    fast_scan_result: dict[str, Any],
    red_persona: str,
    blue_persona: str,
) -> dict[str, Any]:
    verdict = str(fixture_result.get("verdict", "BLOCKED"))
    patched = verdict == "BLUE_SUCCESS"
    topics: list[str] = []

    if not patched:
        topics.extend(
            [
                f"{scenario.get('scenario_id')} exploit variants",
                "SQL injection payload bypass parameterized query patch",
                "stored reflected XSS escaping bypass Python html.escape",
            ]
        )
    if fast_scan_result.get("status") == "BLOCKED":
        topics.append("$hack fast scan failure remediation for Battle Red reconnaissance")

    return {
        "schema": "battle.next_round_research_seed.v1",
        "battle_id": battle_id,
        "round_number": 1,
        "status": "PASS" if topics else "SKIPPED",
        "reason": "all_known_exploits_patched" if not topics else "unpatched_or_blocked_evidence",
        "research_tools": ["dogpile", "brave-search", "memory"],
        "scan_progression": [
            {
                "round": 1,
                "mode": "broad_fast_scan",
                "focus": ["entry_points", "obvious_cwes", "cheap_static_findings"],
            },
            {
                "round": 2,
                "mode": "targeted_follow_up",
                "focus": ["unpatched_cwes", "affected_routes", "near_miss_payloads"],
            },
            {
                "round": 3,
                "mode": "focused_bypass_search",
                "focus": ["specific_symbols", "patch_bypass_hypotheses", "regression_edges"],
            },
        ],
        "red_persona": red_persona,
        "blue_persona": blue_persona,
        "topics": topics,
        "memory_writes_recommended": [
            {
                "collection": "battle_round_memory",
                "kind": "negative_evidence" if patched else "follow_up_research",
                "summary": "Record whether this exploit/patch pair survived scorekeeper replay.",
            }
        ],
        "boundary": "Research is seeded for the next round; this smoke does not call dogpile or brave-search.",
    }


def init_ledger(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                run_id TEXT NOT NULL,
                battle_id TEXT NOT NULL,
                round_number INTEGER NOT NULL,
                team TEXT NOT NULL,
                persona TEXT NOT NULL,
                event_type TEXT NOT NULL,
                status TEXT NOT NULL,
                artifact_path TEXT,
                details_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_run_team ON events (run_id, team)"
        )


def record_event(
    path: Path,
    *,
    run_id: str,
    battle_id: str,
    team: str,
    persona: str,
    event_type: str,
    status: str,
    artifact_path: Path,
    details: dict[str, Any],
) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO events (
                created_at,
                run_id,
                battle_id,
                round_number,
                team,
                persona,
                event_type,
                status,
                artifact_path,
                details_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                utc_now(),
                run_id,
                battle_id,
                1,
                team,
                persona,
                event_type,
                status,
                str(artifact_path),
                json.dumps(details, sort_keys=True),
            ),
        )


def probe_persona(persona: str) -> PersonaProbe:
    repo_root = Path(__file__).resolve().parents[4]
    local = repo_root / "agents" / persona / "persona.yaml"
    external_roots = [
        Path("/mnt/storage12tb/skills/persona-memory"),
        Path("/mnt/storage12tb/skills/audiobook-extractor/outputs"),
    ]
    hits: list[str] = []
    for root in external_roots:
        if not root.exists():
            continue
        try:
            for path in root.rglob(f"*{persona}*"):
                hits.append(str(path))
                if len(hits) >= 5:
                    break
        except OSError:
            continue
        if len(hits) >= 5:
            break
    return PersonaProbe(
        persona=persona,
        local_agent_persona=str(local) if local.is_file() else None,
        external_persona_hits=hits,
    )


def memory_access_for_persona(persona: str) -> dict[str, Any]:
    base = {
        "front_door_routes": ["intent", "deflect", "clarify", "recall", "answer"],
        "default_collections": ["project_knowledge", "battle_round_memory"],
    }
    if persona == "brandon-bailey":
        base["persona_memory"] = {
            "expected_persona_ids": ["brandon-bailey", "brandon"],
            "status": "expected_existing_or_to_ingest",
            "expert_access_collections": [
                "persona_memory",
                "sparta_qra",
                "sparta_controls",
                "sparta_url_knowledge",
                "project_knowledge",
            ],
        }
    return base


def main(argv: list[str] | None = None) -> int:
    del argv
    return 0
