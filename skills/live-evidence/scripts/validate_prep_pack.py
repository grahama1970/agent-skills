#!/usr/bin/env python3
"""Validate a self-contained Live Evidence client/employer/topic prep pack."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REQUIRED_COLLECTIONS = {
    "live_evidence_mock_interviews",
    "live_evidence_questions",
    "live_evidence_answers",
    "live_evidence_skill_chains",
    "live_evidence_source_context",
    "live_evidence_edges",
}


def _fail(errors: list[str], where: str, message: str) -> None:
    errors.append(f"{where}: {message}")


def _validate_briefing_pack(errors: list[str], pack: dict[str, Any]) -> None:
    if pack.get("schema") != "live_evidence.briefing_pack.v1":
        _fail(errors, "briefing_pack", "schema must be live_evidence.briefing_pack.v1")
    points = pack.get("points")
    if not isinstance(points, list) or not points:
        _fail(errors, "briefing_pack", "points must be a non-empty list")
        return
    for index, point in enumerate(points):
        where = f"briefing_pack.points[{index}]"
        if not point.get("point_id"):
            _fail(errors, where, "missing point_id")
        if not point.get("opening_triggers"):
            _fail(errors, where, "missing opening_triggers")
        if not point.get("hook"):
            _fail(errors, where, "missing hook")
        if not point.get("story"):
            _fail(errors, where, "missing story")


def _validate_question_oracles(errors: list[str], items: Any) -> None:
    if not isinstance(items, list) or not items:
        _fail(errors, "question_oracles", "must be a non-empty list")
        return
    for index, item in enumerate(items):
        where = f"question_oracles[{index}]"
        if not item.get("question_id"):
            _fail(errors, where, "missing question_id")
        if not item.get("canonical_question"):
            _fail(errors, where, "missing canonical_question")
        chain = item.get("skill_chain")
        if not isinstance(chain, list) or not chain or chain[0] != "memory":
            _fail(errors, where, "skill_chain must be a non-empty list starting with memory")
        reviewed = item.get("reviewed_answer")
        if not isinstance(reviewed, dict) or reviewed.get("review_status") != "reviewed":
            _fail(errors, where, "reviewed_answer.review_status must be reviewed")
        elif not reviewed.get("quality_bar"):
            _fail(errors, where, "reviewed_answer must include quality_bar")
        keys = item.get("memory_keys")
        if not isinstance(keys, list) or len(keys) < 2:
            _fail(errors, where, "memory_keys must identify retrievable question/answer graph nodes")


def validate(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if payload.get("schema") != "live_evidence.prep_pack.v1":
        _fail(errors, "root", "schema must be live_evidence.prep_pack.v1")
    target = payload.get("target")
    if not isinstance(target, dict) or not target.get("name") or not target.get("topic"):
        _fail(errors, "target", "must include name and topic")
    chain = payload.get("research_chain")
    if not isinstance(chain, list) or not chain:
        _fail(errors, "research_chain", "must be a non-empty list")
    else:
        skills = {item.get("skill") for item in chain if isinstance(item, dict)}
        for required in ("curate-client", "brave-search", "dogpile", "ask", "memory"):
            if required not in skills:
                _fail(errors, "research_chain", f"missing required prep skill {required}")
    sources = payload.get("source_context")
    if not isinstance(sources, list) or not sources:
        _fail(errors, "source_context", "must be a non-empty list")
    else:
        for index, source in enumerate(sources):
            if not source.get("source_id") or not (source.get("url") or source.get("path")):
                _fail(errors, f"source_context[{index}]", "must include source_id and url/path")
    _validate_briefing_pack(errors, payload.get("briefing_pack") or {})
    _validate_question_oracles(errors, payload.get("question_oracles"))
    memory_exports = payload.get("memory_exports") or {}
    collections = set(memory_exports.get("collections") or [])
    missing = sorted(REQUIRED_COLLECTIONS - collections)
    if missing:
        _fail(errors, "memory_exports.collections", f"missing {missing}")
    live_use = payload.get("live_use") or {}
    for phase in ("before_call", "during_call", "after_call"):
        if not live_use.get(phase):
            _fail(errors, f"live_use.{phase}", "must be non-empty")
    return {
        "schema": "live_evidence.prep_pack_validation.v1",
        "path": str(path),
        "pack_id": payload.get("pack_id"),
        "target": target,
        "question_oracle_count": len(payload.get("question_oracles") or []),
        "briefing_point_count": len((payload.get("briefing_pack") or {}).get("points") or []),
        "required_collections_present": not missing,
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--pack", default="fixtures/prep_pack_drivewealth.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    pack_path = Path(args.pack)
    if not pack_path.is_absolute():
        pack_path = root / pack_path
    receipt = validate(pack_path)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    print(f"prep pack: {receipt['status']}")
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
