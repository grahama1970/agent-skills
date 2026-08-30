#!/usr/bin/env python3
"""Compile DriveWealth mock interviews into Memory-shaped oracle graph docs."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import httpx


SKILL = Path(__file__).resolve().parents[1]
DEFAULT_MEMORY_URL = "http://127.0.0.1:8601"
DEFAULT_MEMORY_TIMEOUT_S = 60.0
DEFAULT_MEMORY_BATCH_SIZE = 500
LIVE_EVIDENCE_SCOPE = "live-evidence"
LIVE_EVIDENCE_COLLECTIONS = {
    "mock_interviews": "live_evidence_mock_interviews",
    "questions": "live_evidence_questions",
    "answers": "live_evidence_answers",
    "skill_chains": "live_evidence_skill_chains",
    "source_context": "live_evidence_source_context",
    "edges": "live_evidence_edges",
}
STOP_WORDS = {
    "a",
    "about",
    "after",
    "an",
    "and",
    "are",
    "as",
    "be",
    "by",
    "for",
    "from",
    "give",
    "how",
    "in",
    "is",
    "it",
    "me",
    "of",
    "or",
    "the",
    "then",
    "to",
    "what",
    "when",
    "where",
    "why",
    "with",
    "you",
    "your",
}


def key(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")


def words(value: str) -> set[str]:
    return {
        item
        for item in re.findall(r"[a-z0-9]+", value.lower())
        if len(item) > 2 and item not in STOP_WORDS
    }


def classify_skill_chain(text: str) -> tuple[str, list[str], str, str]:
    lower = text.lower()
    if "live coding" in lower or "implement" in lower or "python" in lower:
        return (
            "coding_interview_question",
            ["memory", "ask", "ripgrep"],
            "Produce a compact implementation strategy or code answer grounded in the provided repo/API context, with fail-closed behavior and testable constraints.",
            "compact_code_or_implementation_plan",
        )
    if any(term in lower for term in ("graph", "topology", "draw", "whiteboard", "architecture")):
        return (
            "architecture_or_topology_question",
            ["memory", "create-figure"],
            "Produce a graph/topology answer with node responsibilities, state, edges, gates, and terminal outcomes grounded in the DriveWealth bridge.",
            "topology_or_system_boundary_explanation",
        )
    if any(term in lower for term in ("observability", "metric", "trace", "latency", "cost", "threshold", "scorecard")):
        return (
            "observability_or_evaluation_question",
            ["memory", "analytics"],
            "Produce a receipt-first diagnostic or measurement plan with traces, metrics, dimensions, thresholds, and rollback or escalation evidence.",
            "diagnostic_plan_with_metrics_and_reversible_mitigation",
        )
    if any(term in lower for term in ("api documentation", "w-8", "871", "1446", "tax", "current")):
        return (
            "api_docs_or_external_context_question",
            ["memory", "brave-search"],
            "Use stored DriveWealth/API context first and route externally only for current or missing API/site facts; do not invent unsupported brokerage facts.",
            "source_checked_api_or_policy_answer",
        )
    return (
        "brokerage_agent_system_question",
        ["memory"],
        "Answer from the DriveWealth bridge and stored project experience, preserving auditability, tenant isolation, fail-closed gates, and source-bound claims.",
        "source_bound_system_design_answer",
    )


def publication_gates(chain: list[str]) -> list[str]:
    gates = [
        "live_question_revision_current",
        "transcript_span_resolves",
        "expected_answer_reviewed",
        "drivewealth_or_repo_evidence_resolves",
        "unsupported_claims_fail_closed",
    ]
    if "brave-search" in chain:
        gates.append("current_external_fact_checked_or_answer_held")
    if "ripgrep" in chain:
        gates.append("current_checkout_source_verified_or_answer_held")
    if "analytics" in chain:
        gates.append("metric_or_trace_claims_cited_or_answer_held")
    if "create-figure" in chain:
        gates.append("topology_nodes_edges_and_terminal_states_present")
    return gates


def answer_review(
    *,
    source: dict[str, Any],
    turn: dict[str, Any],
    chain: list[str],
    category: str,
    expected_response_shape: str,
) -> dict[str, Any]:
    approval = source.get("coverage_approval", {})
    return {
        "schema": "live_evidence.answer_review.v1",
        "status": "reviewed",
        "review_scope": "corpus_and_answer_contract",
        "reviewer": approval.get("reviewer", "fixture-author"),
        "review_run_dir": approval.get("run_dir"),
        "coverage_verdict": approval.get("verdict"),
        "question_key": key(turn["id"]),
        "category": category,
        "expected_response_shape": expected_response_shape,
        "required_skill_chain": chain,
        "quality_bar": [
            "answers the heard question, not an adjacent setup statement",
            "uses the required skill chain or records why a lane is unavailable",
            "names evidence and avoids unsupported brokerage or compliance claims",
            "stays compact enough for live interview card use",
            "fails closed when current source, transcript, or external facts are missing",
        ],
        "publication_gates": publication_gates(chain),
        "fail_closed_conditions": [
            "no resolvable transcript span",
            "answer not tied to current question revision",
            "required source_context, repo, or web reference missing",
            "similar prior question retrieved but actual heard wording changes the answer",
            "answer would surface after the useful focus window",
        ],
    }


def add_similarity_edges(
    *,
    collections: dict[str, list[dict[str, Any]]],
    question_index: list[dict[str, Any]],
) -> int:
    created = 0
    edges = collections[LIVE_EVIDENCE_COLLECTIONS["edges"]]
    for question in question_index:
        candidates: list[tuple[float, dict[str, Any]]] = []
        q_words = question["words"]
        for other in question_index:
            if other["key"] == question["key"]:
                continue
            if other["interview_id"] == question["interview_id"]:
                continue
            if other["category"] != question["category"] and other["chain_key"] != question["chain_key"]:
                continue
            overlap = len(q_words & other["words"])
            union = len(q_words | other["words"]) or 1
            score = round(overlap / union, 3)
            if overlap >= 3 or (question["category"] == other["category"] and score >= 0.08):
                candidates.append((score, other))
        candidates.sort(key=lambda item: (-item[0], item[1]["key"]))
        for score, other in candidates[:2]:
            edge_key = f"{question['key']}_similar_to_{other['key']}"
            edges.append({
                "_key": edge_key,
                "_from": f"{LIVE_EVIDENCE_COLLECTIONS['questions']}/{question['key']}",
                "_to": f"{LIVE_EVIDENCE_COLLECTIONS['questions']}/{other['key']}",
                "kind": "similar_question",
                "edge_type": "similar_question",
                "relationship_type": "similar_question",
                "from_key": question["key"],
                "to_key": other["key"],
                "similarity_score": score,
                "category": question["category"],
                "retrieval_text": (
                    f"{question['turn_id']} is similar to {other['turn_id']} for "
                    f"{question['category']} and may provide a prior, not publication authority."
                ),
                "scope": LIVE_EVIDENCE_SCOPE,
                "tags": ["live-evidence", "drivewealth", "edge", "similar-question"],
            })
            created += 1
    return created


def compile_pack(root: Path, *, limit: int) -> dict[str, Any]:
    source = json.loads((root / "fixtures" / "mock_interviews_drivewealth.json").read_text(encoding="utf-8"))
    bridge = (root / "fixtures" / "drivewealth_bridge.md").read_text(encoding="utf-8")
    interviews = source["interviews"][:limit]
    collections: dict[str, list[dict[str, Any]]] = {
        LIVE_EVIDENCE_COLLECTIONS["mock_interviews"]: [],
        LIVE_EVIDENCE_COLLECTIONS["questions"]: [],
        LIVE_EVIDENCE_COLLECTIONS["answers"]: [],
        LIVE_EVIDENCE_COLLECTIONS["skill_chains"]: [],
        LIVE_EVIDENCE_COLLECTIONS["source_context"]: [],
        LIVE_EVIDENCE_COLLECTIONS["edges"]: [],
    }
    bridge_key = "drivewealth_bridge"
    collections[LIVE_EVIDENCE_COLLECTIONS["source_context"]].append({
        "_key": bridge_key,
        "schema": "live_evidence.source_context.v1",
        "kind": "source_context",
        "title": "DriveWealth bridge",
        "source_path": "skills/live-evidence/fixtures/drivewealth_bridge.md",
        "retrieval_text": bridge[:4000],
        "scope": LIVE_EVIDENCE_SCOPE,
        "tags": ["live-evidence", "drivewealth", "source-context"],
    })
    seen_chains: set[str] = set()
    compiled_interviews: list[dict[str, Any]] = []
    question_index: list[dict[str, Any]] = []
    for interview in interviews:
        interview_key = key(interview["interview_id"])
        collections[LIVE_EVIDENCE_COLLECTIONS["mock_interviews"]].append({
            "_key": interview_key,
            "schema": "live_evidence.mock_interview.v1",
            "kind": "mock_interview_pack",
            "company": "DriveWealth",
            "interview_id": interview["interview_id"],
            "difficulty": interview.get("difficulty"),
            "duration_minutes": interview.get("duration_minutes"),
            "focus": interview.get("focus"),
            "source_fixture": "skills/live-evidence/fixtures/mock_interviews_drivewealth.json",
            "retrieval_text": f"DriveWealth mock interview {interview['interview_id']}: {interview.get('focus', '')}",
            "scope": LIVE_EVIDENCE_SCOPE,
            "tags": ["live-evidence", "drivewealth", "mock-interview", f"interview:{interview['interview_id']}"],
        })
        compiled_questions: list[dict[str, Any]] = []
        previous_question_key: str | None = None
        for index, turn in enumerate(interview["turns"]):
            category, chain, solution, expected_response_shape = classify_skill_chain(turn["text"])
            question_key = key(turn["id"])
            solution_key = f"{question_key}_solution"
            chain_key = key("__".join(chain))
            if chain_key not in seen_chains:
                seen_chains.add(chain_key)
                collections[LIVE_EVIDENCE_COLLECTIONS["skill_chains"]].append({
                    "_key": chain_key,
                    "schema": "live_evidence.skill_chain.v1",
                    "kind": "expected_skill_chain",
                    "skill_chain": chain,
                    "review_contract": {
                        "schema": "live_evidence.skill_chain_review.v1",
                        "status": "required",
                        "pre_answer_gate": "question must be sufficiently formed before this chain runs",
                        "post_answer_gate": "answer must cite the chain evidence before publication",
                    },
                    "retrieval_text": " -> ".join(chain),
                    "scope": LIVE_EVIDENCE_SCOPE,
                    "tags": ["live-evidence", "drivewealth", "skill-chain", f"skill-chain:{chain_key}"],
                })
            timecode = {
                "kind": "script_turn",
                "turn_index": index,
                "start_s": int(index * float(turn.get("pause_seconds") or 60)),
                "end_s": int((index + 1) * float(turn.get("pause_seconds") or 60)),
            }
            collections[LIVE_EVIDENCE_COLLECTIONS["questions"]].append({
                "_key": question_key,
                "schema": "live_evidence.question.v1",
                "kind": "mock_interview_question",
                "company": "DriveWealth",
                "interview_id": interview["interview_id"],
                "turn_id": turn["id"],
                "question": turn["text"],
                "category": category,
                "timecode": timecode,
                "expected_stems": turn.get("expected_stems"),
                "skill_chain": chain,
                "route_plan": {
                    "schema": "live_evidence.question_route_plan.v1",
                    "category": category,
                    "required_skill_chain": chain,
                    "expected_response_shape": expected_response_shape,
                    "pre_answer_gate": "schedule only after transcript span is stable and answerable",
                    "post_answer_gate": "publish only after answer review and source provenance pass",
                },
                "publication_gates": publication_gates(chain),
                "retrieval_text": (
                    f"{turn['text']} Expected skills: {' -> '.join(chain)}. "
                    f"Expected response shape: {expected_response_shape}."
                ),
                "scope": LIVE_EVIDENCE_SCOPE,
                "tags": [
                    "live-evidence",
                    "drivewealth",
                    "question",
                    f"interview:{interview['interview_id']}",
                    f"category:{category}",
                    f"turn:{turn['id']}",
                ],
            })
            collections[LIVE_EVIDENCE_COLLECTIONS["answers"]].append({
                "_key": solution_key,
                "schema": "live_evidence.answer.v1",
                "kind": "expected_interview_solution",
                "question_key": question_key,
                "expected_solution": solution,
                "review": answer_review(
                    source=source,
                    turn=turn,
                    chain=chain,
                    category=category,
                    expected_response_shape=expected_response_shape,
                ),
                "required_evidence_refs": [
                    f"{LIVE_EVIDENCE_COLLECTIONS['questions']}/{question_key}",
                    f"{LIVE_EVIDENCE_COLLECTIONS['source_context']}/{bridge_key}",
                    f"{LIVE_EVIDENCE_COLLECTIONS['skill_chains']}/{chain_key}",
                ],
                "retrieval_text": (
                    f"Reviewed solution: {solution}. "
                    f"Skill chain: {' -> '.join(chain)}. "
                    f"Question: {turn['text']} "
                    f"Review gates: {', '.join(publication_gates(chain))}."
                ),
                "scope": LIVE_EVIDENCE_SCOPE,
                "tags": ["live-evidence", "drivewealth", "expected-answer", "reviewed-answer", f"question:{question_key}"],
            })
            edge_prefix = f"{question_key}"
            collections[LIVE_EVIDENCE_COLLECTIONS["edges"]].extend([
                {
                    "_key": f"{edge_prefix}_contained_by_{interview_key}",
                    "_from": f"{LIVE_EVIDENCE_COLLECTIONS['mock_interviews']}/{interview_key}",
                    "_to": f"{LIVE_EVIDENCE_COLLECTIONS['questions']}/{question_key}",
                    "kind": "contains_question",
                    "edge_type": "contains_question",
                    "relationship_type": "contains_question",
                    "from_key": interview_key,
                    "to_key": question_key,
                    "retrieval_text": f"{interview['interview_id']} contains {turn['id']}",
                    "scope": LIVE_EVIDENCE_SCOPE,
                    "tags": ["live-evidence", "drivewealth", "edge", "contains-question"],
                },
                {
                    "_key": f"{edge_prefix}_answered_by",
                    "_from": f"{LIVE_EVIDENCE_COLLECTIONS['questions']}/{question_key}",
                    "_to": f"{LIVE_EVIDENCE_COLLECTIONS['answers']}/{solution_key}",
                    "kind": "answered_by",
                    "edge_type": "answered_by",
                    "relationship_type": "answered_by",
                    "from_key": question_key,
                    "to_key": solution_key,
                    "retrieval_text": f"{turn['id']} answered by expected solution",
                    "scope": LIVE_EVIDENCE_SCOPE,
                    "tags": ["live-evidence", "drivewealth", "edge", "answered-by"],
                },
                {
                    "_key": f"{edge_prefix}_requires_{chain_key}",
                    "_from": f"{LIVE_EVIDENCE_COLLECTIONS['questions']}/{question_key}",
                    "_to": f"{LIVE_EVIDENCE_COLLECTIONS['skill_chains']}/{chain_key}",
                    "kind": "requires_skill_chain",
                    "edge_type": "requires_skill_chain",
                    "relationship_type": "requires_skill_chain",
                    "from_key": question_key,
                    "to_key": chain_key,
                    "retrieval_text": f"{turn['id']} requires {' -> '.join(chain)}",
                    "scope": LIVE_EVIDENCE_SCOPE,
                    "tags": ["live-evidence", "drivewealth", "edge", "requires-skill-chain"],
                },
                {
                    "_key": f"{edge_prefix}_supported_by_bridge",
                    "_from": f"{LIVE_EVIDENCE_COLLECTIONS['questions']}/{question_key}",
                    "_to": f"{LIVE_EVIDENCE_COLLECTIONS['source_context']}/{bridge_key}",
                    "kind": "supported_by_source_context",
                    "edge_type": "supported_by_source_context",
                    "relationship_type": "supported_by_source_context",
                    "from_key": question_key,
                    "to_key": bridge_key,
                    "retrieval_text": f"{turn['id']} is grounded by the DriveWealth bridge. Question: {turn['text']}",
                    "scope": LIVE_EVIDENCE_SCOPE,
                    "tags": ["live-evidence", "drivewealth", "edge", "supported-by-source-context"],
                },
            ])
            if previous_question_key:
                collections[LIVE_EVIDENCE_COLLECTIONS["edges"]].append({
                    "_key": f"{previous_question_key}_next_{question_key}",
                    "_from": f"{LIVE_EVIDENCE_COLLECTIONS['questions']}/{previous_question_key}",
                    "_to": f"{LIVE_EVIDENCE_COLLECTIONS['questions']}/{question_key}",
                    "kind": "next_question",
                    "edge_type": "next_question",
                    "relationship_type": "next_question",
                    "from_key": previous_question_key,
                    "to_key": question_key,
                    "retrieval_text": f"{previous_question_key} precedes {question_key}",
                    "scope": LIVE_EVIDENCE_SCOPE,
                    "tags": ["live-evidence", "drivewealth", "edge", "next-question"],
                })
            previous_question_key = question_key
            compiled_questions.append({
                "id": turn["id"],
                "timecode": timecode,
                "category": category,
                "skill_chain": chain,
                "expected_solution": solution,
                "expected_response_shape": expected_response_shape,
                "review_status": "reviewed",
                "publication_gates": publication_gates(chain),
            })
            question_index.append({
                "key": question_key,
                "turn_id": turn["id"],
                "interview_id": interview["interview_id"],
                "category": category,
                "chain_key": chain_key,
                "words": words(f"{turn['text']} {turn.get('expected_stems', '')}"),
            })
        compiled_interviews.append({
            "interview_id": interview["interview_id"],
            "duration_minutes": interview.get("duration_minutes"),
            "questions": compiled_questions,
        })
    similarity_edge_count = add_similarity_edges(collections=collections, question_index=question_index)
    return {
        "schema": "live_evidence.drivewealth_oracle_memory_graph.v1",
        "company": "DriveWealth",
        "source_fixture": "fixtures/mock_interviews_drivewealth.json",
        "interview_count": len(interviews),
        "question_count": sum(len(item["questions"]) for item in compiled_interviews),
        "target_question_count": {
            "minimum": 100,
            "preferred_range": [100, 200],
            "current_compiled": sum(len(item["questions"]) for item in compiled_interviews),
            "status": "needs_more_generation" if sum(len(item["questions"]) for item in compiled_interviews) < 100 else "sufficient",
        },
        "oracle_contract": {
            "schema": "live_evidence.oracle_contract.v1",
            "requires_reviewed_answers": True,
            "requires_skill_chains": True,
            "requires_publication_gates": True,
            "requires_similarity_edges": True,
            "similarity_edge_count": similarity_edge_count,
            "known_or_similar_question_policy": (
                "retrieved oracle nodes are priors for live ranking and answer shaping; "
                "they do not bypass transcript revision, source provenance, or publication gates"
            ),
        },
        "compiled_interviews": compiled_interviews,
        "memory_upserts": collections,
        "memory_store_policy": "Use Memory /live-evidence/oracle-pack, then verify through /memory recall. Do not write raw AQL or vectors from live-evidence.",
        "recall_examples": [
            "What DriveWealth questions require analytics in the mock interviews?",
            "Show the expected skill chain and solution for DW-AI-04-T03.",
            "Which DriveWealth interview questions are supported by the bridge and involve out-of-order SQS events?",
        ],
    }


def stable_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def chunks(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[index:index + size] for index in range(0, len(items), size)]


def upsert_memory(
    client: httpx.Client,
    receipt: dict[str, Any],
    *,
    skip_embedding: bool = False,
) -> dict[str, Any]:
    resp = client.post(
        "/live-evidence/oracle-pack",
        json={
            "schema": receipt["schema"],
            "memory_upserts": receipt["memory_upserts"],
            "skip_embedding": skip_embedding,
        },
    )
    payload = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"body": resp.text}
    out = {
        "endpoint": "/live-evidence/oracle-pack",
        "status_code": resp.status_code,
        "response_sha256": stable_hash(payload),
        "response": payload,
    }
    resp.raise_for_status()
    return out


def recall_probe(client: httpx.Client, *, q: str, collections: list[str], expected_keys: list[str]) -> dict[str, Any]:
    resp = client.post("/recall", json={"q": q, "collections": collections, "k": 20})
    payload = resp.json()
    keys = [item.get("_key") for item in payload.get("items", [])]
    missing = [item for item in expected_keys if item not in keys]
    return {
        "q": q,
        "collections": collections,
        "status_code": resp.status_code,
        "found": bool(payload.get("found")),
        "confidence": payload.get("confidence"),
        "returned_keys": keys,
        "expected_keys": expected_keys,
        "missing_expected_keys": missing,
        "ok": resp.status_code == 200 and not missing,
    }


def write_and_verify_memory(
    receipt: dict[str, Any],
    *,
    base_url: str,
    timeout_s: float,
    batch_size: int,
) -> dict[str, Any]:
    timeout = httpx.Timeout(timeout_s, connect=2.0)
    started_at = datetime.now(UTC).isoformat()
    with httpx.Client(base_url=base_url, timeout=timeout) as client:
        upserts = upsert_memory(client, receipt)
        probes = [
            recall_probe(
                client,
                q="Show the expected skill chain and solution for DW-AI-04-T03.",
                collections=[
                    LIVE_EVIDENCE_COLLECTIONS["questions"],
                    LIVE_EVIDENCE_COLLECTIONS["answers"],
                    LIVE_EVIDENCE_COLLECTIONS["skill_chains"],
                    LIVE_EVIDENCE_COLLECTIONS["edges"],
                ],
                expected_keys=["dw_ai_04_t03", "dw_ai_04_t03_solution"],
            ),
            recall_probe(
                client,
                q="Which DriveWealth mock interview question says p95 latency and cost nearly double after a tool-package release?",
                collections=[
                    LIVE_EVIDENCE_COLLECTIONS["questions"],
                    LIVE_EVIDENCE_COLLECTIONS["skill_chains"],
                    LIVE_EVIDENCE_COLLECTIONS["edges"],
                ],
                expected_keys=["dw_ai_02_t05"],
            ),
            recall_probe(
                client,
                q="Which DriveWealth interview question asks about SQS events arriving out of order with an older KYC-approved event after a newer restricted event?",
                collections=[
                    LIVE_EVIDENCE_COLLECTIONS["questions"],
                    LIVE_EVIDENCE_COLLECTIONS["source_context"],
                    LIVE_EVIDENCE_COLLECTIONS["edges"],
                ],
                expected_keys=["dw_ai_01_t07", "dw_ai_01_t07_supported_by_bridge"],
            ),
        ]
    return {
        "schema": "live_evidence.memory_write_receipt.v1",
        "base_url": base_url,
        "timeout_s": timeout_s,
        "batch_size": batch_size,
        "started_at": started_at,
        "ended_at": datetime.now(UTC).isoformat(),
        "upserts": upserts,
        "upsert_batch_count": upserts.get("response", {}).get("upsert_batch_count", 0),
        "upsert_document_count": upserts.get("response", {}).get("upsert_document_count", 0),
        "recall_probes": probes,
        "ok": upserts["status_code"] == 200 and all(item["ok"] for item in probes),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=SKILL)
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--memory-url", default=DEFAULT_MEMORY_URL)
    parser.add_argument("--memory-timeout-s", type=float, default=DEFAULT_MEMORY_TIMEOUT_S)
    parser.add_argument("--memory-batch-size", type=int, default=DEFAULT_MEMORY_BATCH_SIZE)
    parser.add_argument("--write-memory", action="store_true")
    parser.add_argument("--verify-recall", action="store_true")
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args()
    receipt = compile_pack(Path(args.root).resolve(), limit=args.limit)
    if args.verify_recall and not args.write_memory:
        parser.error("--verify-recall requires --write-memory")
    if args.write_memory:
        try:
            receipt["memory_write"] = write_and_verify_memory(
                receipt,
                base_url=args.memory_url,
                timeout_s=args.memory_timeout_s,
                batch_size=args.memory_batch_size,
            )
        except Exception as exc:  # noqa: BLE001 - receipt must preserve external daemon failure.
            receipt["memory_write"] = {
                "schema": "live_evidence.memory_write_receipt.v1",
                "base_url": args.memory_url,
                "timeout_s": args.memory_timeout_s,
                "batch_size": args.memory_batch_size,
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    if args.summary_only:
        summary = {
            "schema": receipt["schema"],
            "company": receipt["company"],
            "interview_count": receipt["interview_count"],
            "question_count": receipt["question_count"],
            "memory_collections": sorted(receipt["memory_upserts"].keys()),
            "memory_write": receipt.get("memory_write"),
        }
        print(json.dumps(summary, indent=2))
    else:
        print(json.dumps(receipt, indent=2))
    if args.write_memory and not receipt.get("memory_write", {}).get("ok"):
        print("drivewealth oracle memory graph: MEMORY_WRITE_FAILED")
        return 1
    print("drivewealth oracle memory graph: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
