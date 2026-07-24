"""Live-runnable one-generation entry for the universal lineage engine.

Normal execution returns exit code 0 for both survivor and the common valid
``no_survivor`` terminal. ``--materialize-only`` recalls context and materializes
exactly N specimens, then skips review, Judge, oracle selection, and write-back.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from .adaptive_lineage_engine import AdaptiveLineageEngine, GenerationRequest
from .adaptive_lineage_memory import MemoryBackend
from .adaptive_lineage_verified_primitives import (
    PrimitiveBackedOracle,
    VerifiedPopulationHooks,
    load_verified_primitive_bundle,
)


def _read_json_object(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"context JSON must be an object: {path}")
    return value


def _load_oracle(spec: str | None, default_oracle: Any) -> Any:
    if not spec:
        return default_oracle
    module_name, separator, attribute = spec.partition(":")
    if not separator or not module_name or not attribute:
        raise ValueError("--oracle-factory must be module:attribute")
    value = getattr(importlib.import_module(module_name), attribute)
    oracle = value() if isinstance(value, type) else value
    if callable(oracle) and not hasattr(oracle, "select"):
        oracle = oracle()
    if not hasattr(oracle, "select"):
        raise TypeError(f"oracle factory {spec!r} did not produce a select() oracle")
    return oracle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one universal oracle-parameterized Battle lineage generation."
    )
    parser.add_argument("--battle-id", required=True)
    parser.add_argument("--lineage-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--generation", type=int, required=True)
    parser.add_argument("--population-size", type=int, required=True)
    parser.add_argument("--max-generations", type=int, required=True)
    parser.add_argument(
        "--max-recall-hops",
        type=int,
        default=3,
        help="Lineage contract metadata; actual multihop traversal is daemon-owned.",
    )
    parser.add_argument("--recall-k", type=int, default=64)
    parser.add_argument("--materialize-only", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--context-json", type=Path)
    parser.add_argument(
        "--memory-url",
        default=os.environ.get("MEMORY_BASE_URL", "http://127.0.0.1:8601"),
    )
    parser.add_argument(
        "--memory-collection",
        default=os.environ.get(
            "BATTLE_LINEAGE_MEMORY_COLLECTION", "battle_lineage_graph"
        ),
    )
    parser.add_argument("--memory-connect-timeout", type=float, default=5.0)
    parser.add_argument("--memory-read-timeout", type=float, default=30.0)
    parser.add_argument("--memory-write-timeout", type=float, default=30.0)
    parser.add_argument("--memory-pool-timeout", type=float, default=5.0)
    parser.add_argument(
        "--primitive-module",
        default="battle_skill.adaptive_red_blue_lineage_canary",
    )
    parser.add_argument(
        "--oracle-factory",
        help=(
            "Optional module:attribute returning a FitnessOracle; defaults to "
            "PrimitiveBackedOracle over the verified _select_survivor helper."
        ),
    )
    return parser


def run_single_generation(arguments: argparse.Namespace) -> Mapping[str, Any]:
    context = _read_json_object(arguments.context_json)
    scope_overrides = context.pop("subgraph_scope", {})
    if not isinstance(scope_overrides, Mapping):
        raise ValueError("context subgraph_scope must be an object")

    request = GenerationRequest(
        battle_id=arguments.battle_id,
        lineage_id=arguments.lineage_id,
        run_id=arguments.run_id,
        role=arguments.role,
        generation=arguments.generation,
        population_size=arguments.population_size,
        max_generations=arguments.max_generations,
        max_recall_hops=arguments.max_recall_hops,
        recall_k=arguments.recall_k,
        materialize_only=arguments.materialize_only,
        out_dir=arguments.out,
        subgraph_scope=dict(scope_overrides),
        context=context,
    )
    bundle = load_verified_primitive_bundle(arguments.primitive_module)
    population_hooks = VerifiedPopulationHooks(bundle)
    default_oracle = PrimitiveBackedOracle(bundle)
    oracle = _load_oracle(arguments.oracle_factory, default_oracle)
    memory_hooks = MemoryBackend(
        base_url=arguments.memory_url,
        collection=arguments.memory_collection,
        connect_timeout_s=arguments.memory_connect_timeout,
        read_timeout_s=arguments.memory_read_timeout,
        write_timeout_s=arguments.memory_write_timeout,
        pool_timeout_s=arguments.memory_pool_timeout,
    )
    engine = AdaptiveLineageEngine(
        population_hooks=population_hooks,
        oracle=oracle,
        memory_hooks=memory_hooks,
    )
    return engine.run_generation(request)


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    receipt = run_single_generation(arguments)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
