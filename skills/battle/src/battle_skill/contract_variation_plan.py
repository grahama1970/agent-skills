"""Acceptance-contract to Dogpile variation-family plan.

This module is intentionally generic: it does not know any project name or
privacy-specific matcher. Battle uses the plan as research input, then freezes
useful families into deterministic generators, Docker/Judge campaigns, and
retained agentic evals.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

PLAN_SCHEMA = "battle.contract_variation_plan.v1"
BUNDLE_SCHEMA = "acceptance_contract.bundle.v1"
DOGPILE_SOURCES = {
    "brave-search",
    "brave-questions",
    "github-search",
    "arxiv",
    "youtube",
    "feeds",
    "wayback",
    "context7",
}

VARIATION_FAMILIES = [
    {
        "id": "representation-equivalence",
        "prompt": "Equivalent values represented as different primitive or domain types.",
        "deterministic_case_hint": "Generate scalar/type variants and prove canonical equivalence before judging.",
    },
    {
        "id": "encoding-normalization",
        "prompt": "Escaping, Unicode normalization, character set, compression, or wrapping differences.",
        "deterministic_case_hint": "Generate encoded/normalized fixtures and one-layer declared decoder cases only.",
    },
    {
        "id": "parser-differentials",
        "prompt": "Different parsers, dialects, coercions, duplicate handling, or schema interpretations.",
        "deterministic_case_hint": "Generate fixtures across every accepted file/API/storage format and parser edge.",
    },
    {
        "id": "surface-boundaries",
        "prompt": "Values appearing outside the obvious body path: keys, names, metadata, logs, reports, paths, headers, indexes, defaults, or stderr/stdout.",
        "deterministic_case_hint": "Generate one case per release surface and make the Judge inspect each surface.",
    },
    {
        "id": "lossy-conversion",
        "prompt": "Leading zeros, precision loss, truncation, rounding, timezone, locale, ordering, or serialization loss.",
        "deterministic_case_hint": "Generate before/after fixtures that fail closed unless the contract defines safe canonicalization.",
    },
    {
        "id": "composition-split",
        "prompt": "A required or forbidden fact split across fields, records, files, chunks, requests, or time.",
        "deterministic_case_hint": "Generate multi-part fixtures and require record-local or declared-scope reconstruction checks.",
    },
    {
        "id": "boundary-cardinality-scale",
        "prompt": "Empty, singleton, duplicate, many, huge, streamed, chunk-boundary, and ordering-sensitive inputs.",
        "deterministic_case_hint": "Generate small boundary cases plus a bounded scale canary.",
    },
    {
        "id": "state-retry-concurrency",
        "prompt": "Retries, partial writes, stale state, concurrent runs, cache reuse, and idempotency failures.",
        "deterministic_case_hint": "Generate repeated-run and interrupted-run receipts with artifact readback.",
    },
    {
        "id": "authorization-trust-boundary",
        "prompt": "Caller identity, path traversal, confused deputy, stale authorization, or unchecked trust-boundary inputs.",
        "deterministic_case_hint": "Generate denied/expired/mismatched authority cases before target execution.",
    },
    {
        "id": "failure-leak-boundary",
        "prompt": "Safe rejection that still leaks data, secrets, stack traces, paths, or intermediate artifacts.",
        "deterministic_case_hint": "Judge stdout, stderr, reports, temp files, and rejected outputs, not only accepted outputs.",
    },
]

AGENTIC_EVAL_CLASSES = [
    "contract-floor-mapping",
    "dogpile-source-bearing-research",
    "variation-family-selection",
    "deterministic-generator-materialization",
    "fixture-precheck-fail-closed",
    "docker-target-execution",
    "judge-independent-replay",
    "functional-judge-non-vacuousness",
    "representation-equivalence-regression",
    "encoding-normalization-regression",
    "parser-differential-regression",
    "surface-boundary-regression",
    "lossy-conversion-regression",
    "composition-split-regression",
    "scale-boundary-regression",
    "state-retry-concurrency-regression",
    "authorization-boundary-regression",
    "failure-leak-regression",
    "adaptive-red-win-lineage",
    "blue-fix-replay-lineage",
    "campaign-aggregate-gate",
    "offline-verifier-tamper-check",
    "create-report-exploits-table",
    "project-state-release-context",
]


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _short(text: str, limit: int = 260) -> str:
    one_line = " ".join(str(text or "").split())
    return one_line if len(one_line) <= limit else one_line[: limit - 1] + "…"


def load_acceptance_bundle(path: Path) -> dict[str, Any]:
    bundle = json.loads(path.read_text(encoding="utf-8"))
    _require(bundle.get("schema") == BUNDLE_SCHEMA, f"bundle schema must be {BUNDLE_SCHEMA}")
    _require(isinstance(bundle.get("requirements"), list), "bundle requirements must be a list")
    _require(isinstance(bundle.get("acceptance_cases"), list), "bundle acceptance_cases must be a list")
    return bundle


def _requirement_index(bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item.get("id")): item for item in bundle.get("requirements", []) if item.get("id")}


def _normalize_dogpile_sources(sources: list[str] | None) -> list[str]:
    if not sources:
        return []
    normalized: list[str] = []
    for source in sources:
        key = str(source).strip().lower().replace("_", "-")
        if key == "brave":
            key = "brave-search"
        if key == "github":
            key = "github-search"
        if key == "brave-questions":
            key = "brave-questions"
        _require(key in DOGPILE_SOURCES, f"unknown Dogpile source filter: {source}")
        if key not in normalized:
            normalized.append(key)
    return normalized


def _dogpile_lanes(case: dict[str, Any], requirement: dict[str, Any], dogpile_sources: list[str] | None = None) -> list[dict[str, Any]]:
    case_id = str(case.get("id") or "unknown-case")
    req_id = str(case.get("requirement_id") or requirement.get("id") or "unknown-requirement")
    contract_text = _short(case.get("predicate") or requirement.get("statement") or case.get("deterministic_check") or "")
    base_context = (
        "Battle is researching variation families for one frozen acceptance-contract item. "
        "Dogpile output is design input only; Battle must later freeze cases and prove them with Docker/Judge receipts. "
        f"Contract item {case_id} / {req_id}: {contract_text}"
    )
    queries = [
        f"meaningful adversarial variation families for this software acceptance requirement: {contract_text}",
        f"real-world bug classes and exploit patterns for requirement edge cases: {contract_text}",
        f"deterministic test generation strategies for proving this invariant across input representations and failure surfaces: {contract_text}",
    ]
    source_args = [arg for source in _normalize_dogpile_sources(dogpile_sources) for arg in ("--source", source)]
    return [
        {
            "id": f"{case_id}-dogpile-{idx}",
            "acceptance_case_id": case_id,
            "requirement_id": req_id,
            "purpose": purpose,
            "query": query,
            "dogpile_sources": _normalize_dogpile_sources(dogpile_sources),
            "command": [
                "../dogpile/run.sh",
                "search",
                query,
                *source_args,
                "--persona",
                "battle-red",
                "--rationale",
                "Find meaningful variation families to convert into deterministic Battle cases.",
                "--context",
                base_context,
            ],
        }
        for idx, (purpose, query) in enumerate(
            [
                ("exploit-family-scouting", queries[0]),
                ("known-failure-patterns", queries[1]),
                ("deterministic-case-design", queries[2]),
            ],
            start=1,
        )
    ]


def build_plan(
    bundle_path: Path,
    *,
    execute_dogpile: bool = False,
    dogpile_limit: int = 0,
    dogpile_sources: list[str] | None = None,
) -> dict[str, Any]:
    bundle_path = bundle_path.resolve()
    bundle = load_acceptance_bundle(bundle_path)
    requirements = _requirement_index(bundle)
    open_questions = bundle.get("open_questions") or []
    cases = bundle.get("acceptance_cases") or []
    status = "READY" if not open_questions and cases else "BLOCKED"
    dogpile_lanes: list[dict[str, Any]] = []
    contract_items: list[dict[str, Any]] = []
    for case in cases:
        requirement = requirements.get(str(case.get("requirement_id")), {})
        lanes = _dogpile_lanes(case, requirement, dogpile_sources=dogpile_sources)
        dogpile_lanes.extend(lanes)
        contract_items.append(
            {
                "acceptance_case_id": case.get("id"),
                "requirement_id": case.get("requirement_id"),
                "predicate": _short(case.get("predicate") or requirement.get("statement") or ""),
                "variation_families": VARIATION_FAMILIES,
                "dogpile_lane_ids": [lane["id"] for lane in lanes],
                "minimum_deterministic_case_slots": len(VARIATION_FAMILIES) * 3,
            }
        )

    plan: dict[str, Any] = {
        "schema": PLAN_SCHEMA,
        "status": status,
        "acceptance_bundle": {
            "path": str(bundle_path),
            "sha256": sha256_file(bundle_path),
            "project_name": bundle.get("project_name"),
            "requirements": len(bundle.get("requirements") or []),
            "acceptance_cases": len(cases),
            "open_questions": len(open_questions),
        },
        "dogpile_role": "research_input_only",
        "dogpile_source_filter": _normalize_dogpile_sources(dogpile_sources),
        "battle_role": "freeze_selected_families_into_deterministic_generators_and_prove_with_Docker_Judge_receipts",
        "contract_items": contract_items,
        "dogpile_lanes": dogpile_lanes,
        "deterministic_case_floor": sum(item["minimum_deterministic_case_slots"] for item in contract_items),
        "agentic_eval_plan": [
            {
                "id": f"battle.{name}",
                "evidence_class": "adversarial_live_e2e" if any(word in name for word in ("docker", "judge", "adaptive", "replay")) else "deterministic",
                "retained": True,
            }
            for name in AGENTIC_EVAL_CLASSES
        ],
        "release_gate": {
            "must_run_dogpile_or_attach_source_bearing_research": True,
            "must_freeze_selected_families_before_target_execution": True,
            "must_emit_case_receipts": "battle.case_receipt.v1",
            "must_emit_aggregate": "battle.campaign_aggregate.v1",
            "red_win_blocks_release": True,
        },
    }
    if execute_dogpile:
        plan["dogpile_execution"] = _execute_dogpile_lanes(dogpile_lanes, limit=dogpile_limit)
    return plan


def _execute_dogpile_lanes(lanes: list[dict[str, Any]], *, limit: int = 0) -> dict[str, Any]:
    selected = lanes[:limit] if limit and limit > 0 else lanes
    results = []
    for lane in selected:
        proc = subprocess.run(
            lane["command"],
            cwd=Path(__file__).resolve().parents[2],
            text=True,
            capture_output=True,
            check=False,
            timeout=900,
        )
        results.append(
            {
                "lane_id": lane["id"],
                "returncode": proc.returncode,
                "stdout": proc.stdout[-4000:],
                "stderr": proc.stderr[-4000:],
            }
        )
    return {
        "schema": "battle.contract_variation_dogpile_execution.v1",
        "attempted": len(results),
        "passed": sum(1 for item in results if item["returncode"] == 0),
        "failed": sum(1 for item in results if item["returncode"] != 0),
        "results": results,
    }


def write_plan(
    bundle_path: Path,
    out: Path,
    *,
    execute_dogpile: bool = False,
    dogpile_limit: int = 0,
    dogpile_sources: list[str] | None = None,
) -> dict[str, Any]:
    plan = build_plan(
        bundle_path,
        execute_dogpile=execute_dogpile,
        dogpile_limit=dogpile_limit,
        dogpile_sources=dogpile_sources,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return plan
