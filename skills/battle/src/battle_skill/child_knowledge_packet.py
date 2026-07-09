"""Child knowledge packet construction for fixture-backed spawn architect proof."""

from __future__ import annotations

from pathlib import Path
from typing import Any


CHILD_KNOWLEDGE_PACKET_SCHEMA = "battle.child_knowledge_packet.v1"


def build_child_knowledge_packet(*, battle_id: str, parent_combiner_receipt: dict[str, Any]) -> dict[str, Any]:
    scenario_id = str(parent_combiner_receipt.get("scenario_id") or "arena-zip-slip-import-001")
    failed_specimens = []
    inherited_methods: set[str] = set()
    observations = {"stdout_summaries": [], "stderr_summaries": [], "http_observations": [], "packet_summaries": []}

    for attempt in parent_combiner_receipt.get("attempts", []):
        if not isinstance(attempt, dict):
            continue
        specimen = attempt.get("specimen") if isinstance(attempt.get("specimen"), dict) else {}
        run_receipt = attempt.get("run_receipt") if isinstance(attempt.get("run_receipt"), dict) else {}
        inherited_methods.update(str(method) for method in specimen.get("chosen_method_ids", []))
        status = str(run_receipt.get("status") or "")
        if status and status != "SPECIMEN_RUNNABLE_UNPROVEN":
            failed_specimens.append(
                {
                    "specimen_id": str(specimen.get("specimen_id") or run_receipt.get("specimen_id") or "unknown"),
                    "status": status,
                    "stderr_summary": _stderr_summary(status=status),
                    "lesson": _lesson_for_status(status=status),
                }
            )
        for observation in run_receipt.get("http_observations", []):
            if isinstance(observation, dict):
                observations["http_observations"].append(observation)
        packet_capture = run_receipt.get("packet_capture") if isinstance(run_receipt.get("packet_capture"), dict) else {}
        observations["packet_summaries"].append(
            {
                "status": packet_capture.get("status", "not_enabled_in_v1"),
                "does_not_prove": packet_capture.get("does_not_prove", ["packet-level detection"]),
            }
        )

    return {
        "schema": CHILD_KNOWLEDGE_PACKET_SCHEMA,
        "battle_id": battle_id,
        "scenario_id": scenario_id,
        "parent_lane_id": "payload-857-combiner",
        "child_lane_id": "payload-857-child-dag-001",
        "arena_public_context_refs": [
            "arena/team-public/scenario-brief.json",
            "arena/team-public/target/app.py",
            "scenario.json",
            "method-menu.json",
        ],
        "forbidden_context_refs": [
            "arena/private/**",
            "hidden-ground-truth.json",
            "hidden-vulnerability-ledger.json",
            "judge/oracle/**",
        ],
        "inherited_methods": sorted(inherited_methods),
        "parent_specimens": failed_specimens,
        "observations": observations,
        "hypotheses": [
            "Parent specimen evolution reached the local BATTLE-004 target surface but has not proven exploit impact.",
            "Child should start from simpler archive import/path handling before adding high-complexity staging ideas.",
        ],
        "blocked_ideas": [
            "Do not claim exploit success without Judge replay.",
            "Do not claim Blue detection, block, kill, or containment from PR1 combiner receipts.",
            "Do not read private Arena, hidden ground truth, hidden vulnerability ledger, or Judge oracle paths.",
        ],
        "next_research_questions": [
            "Which public archive import edge cases are relevant to the /api/import-zip entrypoint?",
            "Which inherited method combinations should be simplified before code authoring?",
            "What compile/runtime failure patterns should trigger a research refresh?",
        ],
        "claims": {
            "proves": ["Spawn Architect can preserve parent specimen evidence as child planning context."],
            "does_not_prove": ["A child exploit ran.", "Tau executed research.", "Exploit success."],
        },
    }


def load_parent_combiner_receipt(parent_combiner_proof: Path) -> dict[str, Any]:
    import json

    path = parent_combiner_proof
    if path.is_dir():
        path = path / "run-receipt.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _stderr_summary(*, status: str) -> str:
    if status == "SPECIMEN_COMPILE_FAILED":
        return "Fixture specimen failed Python compilation."
    if status == "SPECIMEN_RUNTIME_FAILED":
        return "Fixture specimen failed at runtime after compile."
    return "No stderr summary available."


def _lesson_for_status(*, status: str) -> str:
    if status == "SPECIMEN_COMPILE_FAILED":
        return "Syntax-invalid generated code is retained as negative genetic material."
    if status == "SPECIMEN_RUNTIME_FAILED":
        return "Syntactically valid generated code still needs runtime observation and repair."
    return "Parent observation retained for child planning only."
