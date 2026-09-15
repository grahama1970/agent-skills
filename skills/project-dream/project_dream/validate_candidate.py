from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import (
    ACTIONS,
    AUTHORITY_RANK,
    SCHEMA_CANDIDATE,
    SCHEMA_PACKET,
    SCHEMA_VALIDATION,
    contains_secret,
    digest_object,
    load_json,
    sha256_text,
    write_json,
)

DESTRUCTIVE_ACTIONS = {"REVISE_CANDIDATE", "SUPERSEDE_WITH_REPLACEMENT", "DEPRECATE_WITH_REPLACEMENT"}
ABSENCE_WORDS = ("absent", "absence", "no ", "none", "does not exist", "remove", "delete")
MUTATION_WORDS = ("rewrite project_knowledge.md", "direct database", "arangodb", "qdrant", "aql", "promote active")


def _evidence_index(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(src.get("id")): src for src in packet.get("evidence_refs", []) if src.get("id")}


def _proposal_text(proposal: dict[str, Any]) -> str:
    parts = [proposal.get("title", ""), proposal.get("text", ""), proposal.get("retrieval_text", ""), proposal.get("rationale", "")]
    for claim in proposal.get("claims", []) or []:
        parts.append(claim.get("text", ""))
        parts.append(claim.get("rationale", ""))
    return "\n".join(str(p) for p in parts if p).lower()


def validate_packet(packet: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if packet.get("schema_version") != SCHEMA_PACKET:
        errors.append("packet schema_version must be project_dream_evidence_packet.v1")
    for field in ("project_id", "run_id", "input_digest", "input_head", "evidence_refs"):
        if field not in packet:
            errors.append(f"packet missing {field}")
    if isinstance(packet.get("evidence_refs"), list):
        for src in packet["evidence_refs"]:
            if src.get("authority") not in AUTHORITY_RANK:
                errors.append(f"unsupported source authority: {src.get('id')}")
            if src.get("project_id") != packet.get("project_id"):
                errors.append(f"cross-project evidence in packet: {src.get('id')}")
    return errors


def validate_candidate(packet: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    errors.extend(validate_packet(packet))

    if candidate.get("schema_version") != SCHEMA_CANDIDATE:
        errors.append("candidate schema_version must be project_dream_candidate.v1")
    for field in ("project_id", "run_id", "input_digest", "input_head", "model", "prompt", "policy", "proposals"):
        if field not in candidate:
            errors.append(f"candidate missing {field}")
    for field in ("project_id", "run_id", "input_digest", "input_head"):
        if packet.get(field) != candidate.get(field):
            errors.append(f"candidate {field} does not match packet")

    if candidate.get("policy", {}).get("exclude_from_learning") is not True:
        errors.append("candidate policy.exclude_from_learning must be true")
    if candidate.get("policy", {}).get("dream_run_id") != packet.get("run_id"):
        errors.append("candidate policy.dream_run_id must match packet run_id")
    if "promotion_result" in candidate or candidate.get("approval_receipt"):
        errors.append("candidate cannot contain approval receipts or promotion results")
    if contains_secret(candidate):
        errors.append("candidate contains secret-like content")

    sources = _evidence_index(packet)
    active_topics = {t.get("topic_id"): t for t in packet.get("active_topics", []) if isinstance(t, dict)}
    changed = 0

    proposals = candidate.get("proposals") or []
    if not isinstance(proposals, list) or not proposals:
        errors.append("candidate must contain at least one proposal")
        proposals = []

    for idx, proposal in enumerate(proposals):
        prefix = f"proposal[{idx}]"
        action = proposal.get("action")
        if action not in ACTIONS:
            errors.append(f"{prefix} unsupported action {action!r}")
        if proposal.get("status") == "active":
            errors.append(f"{prefix} cannot emit active status")
        for field in ("topic_id", "topic_kind", "title", "text", "retrieval_text", "claims", "expected_head"):
            if field not in proposal:
                errors.append(f"{prefix} missing {field}")
        if action not in {"NO_CHANGE", "NEEDS_HUMAN_REVIEW"}:
            changed += 1
        if action in DESTRUCTIVE_ACTIONS and not proposal.get("expected_head"):
            errors.append(f"{prefix} missing rollback/input-head expected_head")
        if proposal.get("expected_head") and proposal.get("expected_head") != packet.get("input_head"):
            errors.append(f"{prefix} expected_head does not match packet input_head")
        if action == "DEPRECATE_WITH_REPLACEMENT" and not (proposal.get("replacement_topic_id") and proposal.get("replacement_evidence_policy")):
            errors.append(f"{prefix} deprecation requires replacement_topic_id and replacement_evidence_policy")
        if action == "MARK_FRESHNESS_STALE":
            warnings.append(f"{prefix} freshness warning staged without deletion")
        if any(word in _proposal_text(proposal) for word in MUTATION_WORDS):
            errors.append(f"{prefix} requests forbidden project-file rewrite or database mutation")

        topic = active_topics.get(proposal.get("topic_id"), {})
        topic_authority = topic.get("authority")
        topic_rank = AUTHORITY_RANK.get(topic_authority, 99)
        seen_claim_refs = False
        for cidx, claim in enumerate(proposal.get("claims") or []):
            cpfx = f"{prefix}.claim[{cidx}]"
            authority = claim.get("authority")
            if authority not in AUTHORITY_RANK:
                errors.append(f"{cpfx} unsupported authority {authority!r}")
                continue
            if action in DESTRUCTIVE_ACTIONS and AUTHORITY_RANK[authority] > topic_rank and action != "NEEDS_HUMAN_REVIEW":
                errors.append(f"{cpfx} lower-authority claim cannot override current higher-authority topic")
            refs = claim.get("evidence_refs") or []
            if not refs:
                errors.append(f"{cpfx} missing evidence_refs")
            for ref in refs:
                ref_id = ref.get("id")
                if str(ref_id).startswith(("candidate:", "dream-output:", "model-output:")):
                    errors.append(f"{cpfx} recursively cites dream worker output")
                    continue
                src = sources.get(str(ref_id))
                if not src:
                    errors.append(f"{cpfx} unresolved evidence ref {ref_id!r}")
                    continue
                seen_claim_refs = True
                if src.get("kind") in {"model_output", "dream_worker_output"}:
                    errors.append(f"{cpfx} recursively cites model output evidence {ref_id!r}")
                if src.get("project_id") != packet.get("project_id"):
                    errors.append(f"{cpfx} crosses project boundary via {ref_id!r}")
                if src.get("visibility") == "private" and src.get("project_id") != candidate.get("project_id"):
                    errors.append(f"{cpfx} violates private visibility boundary via {ref_id!r}")
                if ref.get("sha256") and ref.get("sha256") != src.get("sha256"):
                    errors.append(f"{cpfx} hash mismatch for {ref_id!r}")
                span = ref.get("span") or {}
                text = src.get("text", "")
                if span:
                    start, end = span.get("start"), span.get("end")
                    if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end > len(text) or start >= end:
                        errors.append(f"{cpfx} invalid source span for {ref_id!r}")
                    elif ref.get("span_sha256") and ref["span_sha256"] != sha256_text(text[start:end]):
                        errors.append(f"{cpfx} source span hash mismatch for {ref_id!r}")
                if src.get("stale") is True and src.get("kind") in {"git", "project_state", "code_ingest"}:
                    errors.append(f"{cpfx} cites stale {src.get('kind')} evidence {ref_id!r}")
                if action == "DEPRECATE_WITH_REPLACEMENT" and any(w in _proposal_text(proposal) for w in ABSENCE_WORDS):
                    if src.get("kind") in {"code", "code_ingest"} and (src.get("coverage_scope") == "incremental" or not src.get("reconciliation_eligible", False)):
                        errors.append(f"{cpfx} incremental code evidence cannot support repository-wide absence/deprecation")
        if action != "NEEDS_HUMAN_REVIEW":
            for conflict in packet.get("contradictions", []) or []:
                if conflict.get("topic_id") == proposal.get("topic_id") and conflict.get("authority") in AUTHORITY_RANK:
                    errors.append(f"{prefix} same-authority contradiction must route to NEEDS_HUMAN_REVIEW")
        if not seen_claim_refs and action not in {"NO_CHANGE", "NEEDS_HUMAN_REVIEW"}:
            errors.append(f"{prefix} has no resolved claim evidence")

    budget = packet.get("policy", {}).get("mutation_budget", {})
    max_changed = budget.get("max_changed_topics")
    if isinstance(max_changed, int) and changed > max_changed:
        errors.append(f"mutation budget exceeded: {changed} > {max_changed}")
    max_pct = budget.get("max_changed_percent")
    active_count = max(1, len(active_topics))
    if isinstance(max_pct, (int, float)) and (changed / active_count * 100) > max_pct:
        errors.append(f"mutation percent exceeded: {changed}/{active_count} > {max_pct}%")

    status = "blocked" if errors else "accepted"
    return {
        "schema_version": SCHEMA_VALIDATION,
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "project_id": packet.get("project_id"),
        "run_id": packet.get("run_id"),
        "input_digest": packet.get("input_digest"),
        "packet_digest": digest_object(packet),
        "candidate_digest": digest_object(candidate),
        "shadow_only": True,
        "active_head_unchanged": True,
    }


def validate_candidate_files(packet_path: Path, candidate_path: Path, output_path: Path | None) -> dict[str, Any]:
    receipt = validate_candidate(load_json(packet_path), load_json(candidate_path))
    if output_path:
        write_json(output_path, receipt)
    return receipt
