#!/usr/bin/env python3
"""Deterministic BATTLE backend eval.

Answers one legible question: **is the BATTLE backend working as expected right
now?** — without the live Tau / Docker / browser pipeline and without touching
the disputed UX-acceptance gate.

It runs the REAL backend validators (through the CLI, reading back the produced
or committed artifact) and groups the results into a few plain-language
channels. Every case states what a PASS *proves* and, just as importantly, what
it *does not prove*. Modeled on the dogpile `feature_channel_eval.py` pattern.

What it does NOT do: run live SciLLM, Docker Judge, Tau, or a browser; it makes
no claim about exploit success, Blue detection, or visible UX readiness.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
RUN_SH = SKILL_DIR / "run.sh"
FIXTURE_ROOT = SKILL_DIR / "spectator" / "public" / "battle-fixtures"
LINEAGE_FIXTURES = SKILL_DIR / "spectator" / "src" / "lineage" / "__fixtures__"


def _utc_stamp() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def _run_cli(args: list[str], timeout: int = 240) -> tuple[int, dict[str, Any] | None, str]:
    """Run `run.sh <args>` and return (returncode, trailing_json_or_None, tail)."""
    proc = subprocess.run(
        ["bash", str(RUN_SH), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    out = proc.stdout
    parsed: dict[str, Any] | None = None
    # Validators print a trailing JSON object; recover it if present.
    brace = out.rfind("\n{")
    start = 0 if out.lstrip().startswith("{") else (brace + 1 if brace != -1 else -1)
    if start != -1:
        try:
            parsed = json.loads(out[start:])
        except json.JSONDecodeError:
            parsed = None
    tail = (out or proc.stderr).strip().splitlines()[-3:]
    return proc.returncode, parsed, "\n".join(tail)


def _case(name: str, channel: str, passed: bool, proves: str, does_not_prove: str,
          details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "channel": channel,
        "status": "passed" if passed else "failed",
        "proves": proves,
        "does_not_prove": does_not_prove,
        "details": details or {},
    }


def _fixture_schema(path: Path) -> tuple[str, bool]:
    data = json.loads(path.read_text())
    return data.get("schema", ""), "genetic_lifecycle" in data


# schema (+ genetic flag) -> validator subcommand
def _validator_for(schema: str, genetic: bool) -> str | None:
    if schema == "battle.normalized_adaptive_lineage_fixture.v1":
        return "validate-adaptive-lineage-fixture"
    if schema == "battle.normalized_ux_fixture.v1" and genetic:
        return "validate-genetic-pixi-fixture"
    if schema == "battle.normalized_ux_fixture.v1":
        return "validate-ux-contract"
    return None


CHANNEL_FOR_VALIDATOR = {
    "validate-ux-contract": "race_replay_fixtures",
    "validate-genetic-pixi-fixture": "genetic_lifecycle_fixtures",
    "validate-adaptive-lineage-fixture": "adaptive_lineage_fixtures",
}


def run_eval(out_dir: Path) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    work = out_dir / "_artifacts"
    work.mkdir(parents=True, exist_ok=True)

    # --- Channel 1: deterministic contracts (export -> validate round trip) ---
    som = work / "semantic-outcome-matrix.json"
    rc, _, _ = _run_cli(["export-semantic-outcome-matrix", "--out", str(som)])
    rc2, parsed, tail = _run_cli(["validate-semantic-outcome-matrix", str(som)])
    cases.append(_case(
        "semantic_outcome_matrix_roundtrips",
        "deterministic_contracts",
        rc == 0 and rc2 == 0 and som.exists(),
        "The exploit outcome-scoring matrix exports and re-validates deterministically (mocked=false).",
        "That any live exploit actually achieved these outcomes against a target.",
        {"outcome_cases": (parsed or {}).get("outcome_case_count"), "tail": tail},
    ))

    dag = work / "exploit-lifecycle-dag.json"
    rc, _, _ = _run_cli(["export-exploit-lifecycle-dag", "--out", str(dag)])
    rc2, parsed, tail = _run_cli(["validate-exploit-lifecycle-dag", str(dag)])
    cases.append(_case(
        "exploit_lifecycle_dag_roundtrips",
        "deterministic_contracts",
        rc == 0 and rc2 == 0 and dag.exists(),
        "The exploit lifecycle DAG (states + legal transitions) exports and re-validates deterministically.",
        "That a live specimen traversed these states, or that any transition was receipt-backed in a live run.",
        {"tail": tail},
    ))

    # --- Channel 2/3/4: every committed fixture through its CORRECT validator ---
    fixtures = sorted(FIXTURE_ROOT.glob("*/battle.normalized_ux_fixture.json"))
    for fx in fixtures:
        rel = fx.relative_to(FIXTURE_ROOT).parts[0]
        try:
            schema, genetic = _fixture_schema(fx)
        except (OSError, json.JSONDecodeError) as exc:
            cases.append(_case(
                f"fixture_readable::{rel}", "fixture_integrity", False,
                "The committed fixture is valid JSON declaring a known schema.",
                "Renderer or live behavior for the fixture.",
                {"error": str(exc)},
            ))
            continue
        validator = _validator_for(schema, genetic)
        if validator is None:
            cases.append(_case(
                f"fixture_schema_known::{rel}", "fixture_integrity", False,
                "The committed fixture declares a schema this eval knows how to validate.",
                "Renderer or live behavior for the fixture.",
                {"schema": schema, "genetic": genetic},
            ))
            continue
        rc, parsed, tail = _run_cli([validator, str(fx)])
        channel = CHANNEL_FOR_VALIDATOR[validator]
        cases.append(_case(
            f"fixture_valid::{rel}",
            channel,
            rc == 0,
            f"The committed `{rel}` fixture satisfies its declared contract ({schema}) via `{validator}`.",
            "That the spectator actually renders it, or that its receipts reflect a live exploit outcome.",
            {"schema": schema, "validator": validator, "tail": tail if rc != 0 else None},
        ))

    # --- Channel 5: committed live adaptive-lineage fixture is data_source=live ---
    live_fx = LINEAGE_FIXTURES / "adaptive-lineage-live.json"
    if live_fx.exists():
        rc, parsed, tail = _run_cli(["validate-adaptive-lineage-fixture", str(live_fx)])
        is_live = bool(parsed) and parsed.get("data_source") == "live" and parsed.get("status") == "PASS"
        cases.append(_case(
            "adaptive_lineage_live_fixture_is_live",
            "adaptive_lineage_fixtures",
            rc == 0 and is_live,
            "The committed adaptive-lineage fixture validates and is honestly tagged data_source=live (G0->{G1-A,G1-B}->G2, 4 nodes / 3 edges).",
            "That the live badge renders, or that the lineage improved exploit performance (improvement_claimed stays false).",
            {"data_source": (parsed or {}).get("data_source"), "node_count": (parsed or {}).get("node_count")},
        ))

    # --- Channel 6: live transport contract (contract-only) ---
    lt = FIXTURE_ROOT / "battle-004-pr8-live-transport" / "battle.live_transport_contract.json"
    if lt.exists():
        rc, parsed, tail = _run_cli(["validate-live-transport-contract", str(lt)])
        cases.append(_case(
            "live_transport_contract_valid",
            "live_transport",
            rc == 0,
            "The published SSE/snapshot transport contract validates and forbids raw-path leakage.",
            "That an SSE server is running or that live genetic events were emitted (live=contract_only).",
            {"tail": tail if rc != 0 else None},
        ))

    passed = [c for c in cases if c["status"] == "passed"]
    failed = [c for c in cases if c["status"] == "failed"]
    return {
        "schema": "battle.backend_eval.v1",
        "mocked": False,
        "live": False,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scope": "deterministic backend contracts + committed fixture integrity; no live Tau/Docker/browser",
        "summary": {
            "passed": len(passed),
            "failed": len(failed),
            "total": len(cases),
            "channels": sorted({c["channel"] for c in cases}),
            "failed_cases": [c["name"] for c in failed],
        },
        "cases": cases,
        "status": "passed" if not failed else "failed",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the deterministic BATTLE backend eval")
    parser.add_argument("--out-dir", type=Path,
                        default=SKILL_DIR / "reports" / f"backend-eval-{_utc_stamp()}")
    args = parser.parse_args()

    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    receipt = run_eval(out_dir)
    receipt_path = out_dir / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")

    print(json.dumps({
        "status": receipt["status"],
        "receipt_path": str(receipt_path),
        "summary": receipt["summary"],
    }, indent=2))
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
