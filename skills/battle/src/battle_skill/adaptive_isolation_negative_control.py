"""Isolation negative control for the adaptive Red/Blue co-evolution gate.

Roundtable finding (webclaude, 2026-07-23): `visibility-validation.leaks:[]` proves the
checker found nothing, NOT that isolation holds. This harness taints a real run's
artifacts and asserts the REAL `_visibility_validation` gate flips PASS -> FAIL for both
channels — arena-private answer-key leakage AND Red<->Blue cross-team knowledge leakage
(the co-evolution amendment's core guarantee). It is deterministic (no live run): it drives
the shipping validator over clean and deliberately-poisoned copies of a passing generation.

    ./run.sh adaptive-isolation-negative-control <run_dir> --generation 1 --out <receipt.json>
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .arena_live_battle_proof import _visibility_validation

SCHEMA = "battle.adaptive_isolation_negative_control.v1"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_gate(gen_dir: Path) -> dict[str, Any]:
    manifest = _read_json(gen_dir / "tau-live" / "manifest.json")
    return _visibility_validation(out_dir=gen_dir, tau_manifest=manifest)


def _clone(gen_dir: Path, tmp: Path, tag: str) -> Path:
    dest = tmp / tag
    shutil.copytree(gen_dir, dest)
    return dest


def run_isolation_negative_control(*, run_dir: Path, generation: int) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    gen_dir = run_dir / f"generation-{generation}"
    if not (gen_dir / "tau-live" / "manifest.json").exists():
        raise FileNotFoundError(f"no tau-live manifest under {gen_dir}")

    blue_genome = _read_json(gen_dir / "genomes" / "blue-team-genome.json")
    blue_private = str(blue_genome.get("provider_response_sha256") or "")
    if not blue_private:
        raise ValueError("blue genome missing provider_response_sha256 marker")

    red_handoff_rel = Path("tau-live") / "red" / "handoff.json"
    cases: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory() as raw_tmp:
        tmp = Path(raw_tmp)

        # Case 0 — CLEAN: the real gate must PASS with no leaks.
        clean = _run_gate(_clone(gen_dir, tmp, "clean"))
        cases.append({
            "case": "clean_run",
            "expect": "PASS",
            "status": clean["status"],
            "leaks": clean["private_input_leaks"],
            "held": clean["status"] == "PASS" and not clean["private_input_leaks"],
        })

        # Case 1 — ARENA-PRIVATE TAINT: inject the hidden answer-key marker into Red's
        # public handoff. The gate must flip to FAIL.
        arena_dir = _clone(gen_dir, tmp, "arena")
        p = arena_dir / red_handoff_rel
        p.write_text(p.read_text(encoding="utf-8").rstrip().rstrip("}") + ', "POISON": "arena/private hidden-vulnerability-ledger"}', encoding="utf-8")
        arena = _run_gate(arena_dir)
        cases.append({
            "case": "arena_private_taint",
            "expect": "FAIL",
            "status": arena["status"],
            "leaks": arena["private_input_leaks"],
            "held": arena["status"] == "FAIL" and any("arena/private" in x or "hidden-vulnerability-ledger" in x for x in arena["private_input_leaks"]),
        })

        # Case 2 — CROSS-TEAM TAINT: inject Blue's private authored-content fingerprint
        # into Red's public handoff. The gate must flip to FAIL with a cross_team_leak.
        cross_dir = _clone(gen_dir, tmp, "cross")
        p = cross_dir / red_handoff_rel
        p.write_text(p.read_text(encoding="utf-8").rstrip().rstrip("}") + f', "POISON": "leaked blue fingerprint {blue_private}"}}', encoding="utf-8")
        cross = _run_gate(cross_dir)
        cases.append({
            "case": "cross_team_taint",
            "expect": "FAIL",
            "status": cross["status"],
            "leaks": cross["private_input_leaks"],
            "held": cross["status"] == "FAIL" and any("cross_team_leak" in x for x in cross["private_input_leaks"]),
        })

    all_held = all(c["held"] for c in cases)
    return {
        "schema": SCHEMA,
        "status": "PASS" if all_held else "FAIL",
        "run_dir": str(run_dir),
        "generation": generation,
        "proves": [
            "The isolation gate PASSes a clean run AND flips to FAIL when an arena-private "
            "answer-key marker OR an opponent-team private fingerprint is injected — i.e. it "
            "provably catches dirt, not merely reports clean.",
        ],
        "inspected_channels": clean.get("inspected_channels"),
        "cases": cases,
    }
