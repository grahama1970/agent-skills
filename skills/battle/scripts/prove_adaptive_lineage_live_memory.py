from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

import httpx

from battle_skill.adaptive_lineage_engine import (
    AdaptiveLineageEngine,
    GenerationRequest,
    canonical_sha256,
    json_safe,
)
from battle_skill.adaptive_lineage_memory import (
    MEMORY_COLLECTION,
    MEMORY_NODE_SCHEMA,
    MemoryBackend,
    RoleMemoryScope,
)
from battle_skill.adaptive_lineage_verified_primitives import (
    PrimitiveBackedOracle,
    VerifiedPopulationHooks,
    load_verified_primitive_bundle,
)


def _write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(json_safe(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _now_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _request(
    *,
    battle_id: str,
    lineage_id: str,
    run_id: str,
    role: str,
    generation: int,
    out_dir: Path,
    population_size: int,
    docker_image: str,
    recall_query: str | None = None,
) -> GenerationRequest:
    context = {"docker_image": docker_image}
    if recall_query:
        context["recall_query"] = recall_query
    return GenerationRequest(
        battle_id=battle_id,
        lineage_id=lineage_id,
        run_id=run_id,
        role=role,
        generation=generation,
        population_size=population_size,
        max_generations=2,
        max_recall_hops=3,
        recall_k=64,
        out_dir=out_dir,
        subgraph_scope={},
        context=context,
    )


def _health(base_url: str, timeout_s: float) -> dict[str, Any]:
    try:
        with httpx.Client(timeout=timeout_s) as client:
            response = client.get(f"{base_url.rstrip('/')}/health")
        body: Any
        try:
            body = response.json()
        except Exception:
            body = response.text
        return {
            "status_code": response.status_code,
            "ok": response.is_success,
            "body": json_safe(body),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _private_marker_document(
    *,
    battle_id: str,
    lineage_id: str,
    role: str,
    run_id: str,
    generation: int,
) -> dict[str, Any]:
    scope = RoleMemoryScope(battle_id=battle_id, lineage_id=lineage_id, role=role)
    key_material = {
        "battle_id": battle_id,
        "lineage_id": lineage_id,
        "role": role,
        "run_id": run_id,
        "generation": generation,
        "kind": "proof-upsert-marker",
    }
    return {
        "_key": f"battle-lineage-proof-{canonical_sha256(key_material)[:24]}",
        "schema": MEMORY_NODE_SCHEMA,
        "collection": MEMORY_COLLECTION,
        "battle_id": battle_id,
        "lineage_id": lineage_id,
        "run_id": run_id,
        "generation": generation,
        "role": role,
        "owner_role": role,
        "scope": scope.private_scope,
        "node_kind": "proof_upsert_marker",
        "text": f"{role} issue 1065 live upsert marker.",
        "tags": [
            *scope.base_tags,
            f"role:{role}",
            f"access:{role}",
            "visibility:role-only",
            "kind:proof-upsert-marker",
        ],
        "graph_edges_raw": [],
        "qdrant": {"sync": "memory-daemon-owned", "vector_inline": False},
    }


def _role_run(
    *,
    role: str,
    battle_id: str,
    lineage_id: str,
    root: Path,
    memory: MemoryBackend,
    docker_image: str,
    population_size: int,
    recall_attempts: int,
    recall_sleep_s: float,
) -> dict[str, Any]:
    bundle = load_verified_primitive_bundle()
    engine = AdaptiveLineageEngine(
        population_hooks=VerifiedPopulationHooks(bundle),
        oracle=PrimitiveBackedOracle(bundle),
        memory_hooks=memory,
    )
    role_dir = root / role
    first = engine.run_generation(
        _request(
            battle_id=battle_id,
            lineage_id=lineage_id,
            run_id=f"{role}-g1",
            role=role,
            generation=1,
            out_dir=role_dir,
            population_size=population_size,
            docker_image=docker_image,
        )
    )
    survivor_id = str(first["oracle"]["survivor_id"])
    survivor_key = str(first["reproduction"]["survivor_key"])
    exact_survivor_query = (
        f"{role} lineage survivor {survivor_id} {survivor_key} "
        f"{battle_id} {lineage_id}"
    )
    second_recall, recall_attempt_receipts = _recall_until_survivor(
        memory=memory,
        request=_request(
            battle_id=battle_id,
            lineage_id=lineage_id,
            run_id=f"{role}-g2-recall",
            role=role,
            generation=2,
            out_dir=role_dir,
            population_size=population_size,
            docker_image=docker_image,
            recall_query=exact_survivor_query,
        ),
        role=role,
        survivor_id=survivor_id,
        attempts=recall_attempts,
        sleep_s=recall_sleep_s,
    )
    second = engine.run_generation(
        _request(
            battle_id=battle_id,
            lineage_id=lineage_id,
            run_id=f"{role}-g2",
            role=role,
            generation=2,
            out_dir=role_dir,
            population_size=population_size,
            docker_image=docker_image,
            recall_query=exact_survivor_query,
        )
    )
    marker = _private_marker_document(
        battle_id=battle_id,
        lineage_id=lineage_id,
        role=role,
        run_id=f"{role}-upsert",
        generation=2,
    )
    upsert_ack = memory.upsert_documents(
        collection=memory.collection,
        documents=[marker],
    )
    return {
        "role": role,
        "run_dir": str(role_dir),
        "generation_1": first,
        "generation_2_recall": second_recall.as_context(),
        "generation_2_recall_attempts": recall_attempt_receipts,
        "generation_2": second,
        "proof_marker_upsert_ack": json_safe(upsert_ack),
    }


def _recall_until_survivor(
    *,
    memory: MemoryBackend,
    request: GenerationRequest,
    role: str,
    survivor_id: str,
    attempts: int,
    sleep_s: float,
):
    receipts: list[dict[str, Any]] = []
    last = None
    for attempt in range(1, attempts + 1):
        recall = memory.recall(request=request)
        context = recall.as_context()
        context["attempt"] = attempt
        receipts.append(context)
        if any(
            item.get("node_kind") == "survivor"
            and item.get("owner_role") == role
            and item.get("candidate_id") == survivor_id
            for item in recall.documents
        ):
            return recall, receipts
        last = recall
        if attempt < attempts:
            time.sleep(sleep_s)
    return last, receipts


def _negative_recall(
    *,
    role: str,
    battle_id: str,
    lineage_id: str,
    root: Path,
    memory: MemoryBackend,
    docker_image: str,
    recall_query: str,
) -> dict[str, Any]:
    recall = memory.recall(
        request=_request(
            battle_id=battle_id,
            lineage_id=lineage_id,
            run_id=f"negative-{role}",
            role=role,
            generation=2,
            out_dir=root / "negative-controls" / role,
            population_size=1,
            docker_image=docker_image,
            recall_query=recall_query,
        )
    )
    return recall.as_context()


def run(arguments: argparse.Namespace) -> dict[str, Any]:
    out_dir = arguments.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = arguments.run_id or f"issue-1065-{_now_id()}"
    battle_id = arguments.battle_id or run_id
    lineage_id = arguments.lineage_id
    memory = MemoryBackend(
        base_url=arguments.memory_url,
        collection=arguments.memory_collection,
        connect_timeout_s=arguments.timeout_s,
        read_timeout_s=arguments.timeout_s,
        write_timeout_s=arguments.timeout_s,
        pool_timeout_s=arguments.timeout_s,
    )
    health = _health(arguments.memory_url, arguments.timeout_s)
    _write_json(out_dir / "memory-health.json", health)

    red = _role_run(
        role="red",
        battle_id=battle_id,
        lineage_id=lineage_id,
        root=out_dir,
        memory=memory,
        docker_image=arguments.docker_image,
        population_size=arguments.population_size,
        recall_attempts=arguments.recall_attempts,
        recall_sleep_s=arguments.recall_sleep_s,
    )
    blue = _role_run(
        role="blue",
        battle_id=battle_id,
        lineage_id=lineage_id,
        root=out_dir,
        memory=memory,
        docker_image=arguments.docker_image,
        population_size=arguments.population_size,
        recall_attempts=arguments.recall_attempts,
        recall_sleep_s=arguments.recall_sleep_s,
    )
    red_as_blue = _negative_recall(
        role="blue",
        battle_id=battle_id,
        lineage_id=lineage_id,
        root=out_dir,
        memory=memory,
        docker_image=arguments.docker_image,
        recall_query=(
            f"red lineage survivor {red['generation_1']['oracle']['survivor_id']} "
            f"{red['generation_1']['reproduction']['survivor_key']} {battle_id} {lineage_id}"
        ),
    )
    blue_as_red = _negative_recall(
        role="red",
        battle_id=battle_id,
        lineage_id=lineage_id,
        root=out_dir,
        memory=memory,
        docker_image=arguments.docker_image,
        recall_query=(
            f"blue lineage survivor {blue['generation_1']['oracle']['survivor_id']} "
            f"{blue['generation_1']['reproduction']['survivor_key']} {battle_id} {lineage_id}"
        ),
    )

    def survivor_ids(recall_context: Mapping[str, Any], role: str) -> list[str]:
        return [
            str(item.get("candidate_id"))
            for item in recall_context.get("documents", [])
            if item.get("node_kind") == "survivor" and item.get("owner_role") == role
        ]

    red_inherited = survivor_ids(red["generation_2_recall"], "red")
    blue_inherited = survivor_ids(blue["generation_2_recall"], "blue")
    red_leaked_to_blue = survivor_ids(red_as_blue, "red")
    blue_leaked_to_red = survivor_ids(blue_as_red, "blue")
    pass_checks = {
        "health_ok": bool(health.get("ok")),
        "red_survivor_written": red["generation_1"]["survivor"] is not None,
        "blue_survivor_written": blue["generation_1"]["survivor"] is not None,
        "red_second_generation_recall_contains_owning_survivor": bool(red_inherited),
        "blue_second_generation_recall_contains_owning_survivor": bool(blue_inherited),
        "red_not_visible_to_blue": not red_leaked_to_blue,
        "blue_not_visible_to_red": not blue_leaked_to_red,
        "red_store_ack_present": bool(red["generation_1"].get("reproduction")),
        "blue_store_ack_present": bool(blue["generation_1"].get("reproduction")),
        "red_upsert_ack_present": bool(red["proof_marker_upsert_ack"]),
        "blue_upsert_ack_present": bool(blue["proof_marker_upsert_ack"]),
    }
    summary = {
        "schema": "battle.issue_1065_live_lineage_memory_proof.v1",
        "status": "PASS" if all(pass_checks.values()) else "FAIL",
        "mocked": False,
        "live": True,
        "battle_id": battle_id,
        "lineage_id": lineage_id,
        "memory_url": arguments.memory_url,
        "memory_collection": arguments.memory_collection,
        "docker_image": arguments.docker_image,
        "population_size": arguments.population_size,
        "pass_checks": pass_checks,
        "roles": {"red": red, "blue": blue},
        "negative_controls": {
            "red_as_blue": red_as_blue,
            "blue_as_red": blue_as_red,
            "red_leaked_to_blue": red_leaked_to_blue,
            "blue_leaked_to_red": blue_leaked_to_red,
        },
        "claims": {
            "proves": [
                "Red and Blue ran recall, population, review, Docker Judge, oracle selection, bad-material, survivor write, and next-generation Memory recall against the live daemon.",
                "Real Memory /store and /upsert acknowledgement shapes were read back.",
                "Opponent role negative-control recalls did not receive the other role's survivor.",
            ],
            "does_not_prove": [
                "A thousand-specimen lineage run.",
                "New fitness metrics.",
                "Spectator UI behavior.",
            ],
        },
    }
    _write_json(out_dir / "proof-summary.json", summary)
    if summary["status"] != "PASS":
        raise SystemExit(json.dumps(summary["pass_checks"], indent=2, sort_keys=True))
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--battle-id")
    parser.add_argument("--lineage-id", default="issue-1065-lineage")
    parser.add_argument("--memory-url", default="http://127.0.0.1:8601")
    parser.add_argument("--memory-collection", default=MEMORY_COLLECTION)
    parser.add_argument("--docker-image", default="python:3.12-slim")
    parser.add_argument("--population-size", type=int, default=2)
    parser.add_argument("--recall-attempts", type=int, default=8)
    parser.add_argument("--recall-sleep-s", type=float, default=5.0)
    parser.add_argument("--timeout-s", type=float, default=60.0)
    return parser


def main() -> int:
    summary = run(build_parser().parse_args())
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
