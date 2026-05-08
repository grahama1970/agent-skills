"""Evolutionary greybox hardening campaigns for /hack.

The core helpers are deterministic and side-effect-light. Docker execution is
only performed by the CLI wrapper after target scope and artifact paths are
validated.
"""

from __future__ import annotations

import json
import re
import random
import shutil
import subprocess
import textwrap
import time
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Iterable

import typer
from rich.console import Console

from hack.chaos_campaign import is_local_or_private_target, summarize_seed_file
from hack.self_improve_loop import ARTIFACT_ROOT
from hack.session_audit import safe_slug

console = Console()

LANE_IDS = (
    "api_protocol",
    "stateful_workflow",
    "auth_session",
    "websocket_control",
    "filesystem_path",
    "child_process_tool",
    "parser_dependency",
    "native_binary",
    "wasm",
    "electron_webkit",
    "language_runtime",
    "dependency_supply_chain",
)
HTTP_CAPABLE_LANES = {
    "api_protocol",
    "stateful_workflow",
    "auth_session",
    "websocket_control",
    "filesystem_path",
    "child_process_tool",
    "parser_dependency",
    "language_runtime",
    "dependency_supply_chain",
}
LOW_LEVEL_LANES = {"native_binary", "wasm", "electron_webkit"}
TARGET_SOURCE_TYPES = {"artifact_path", "repository_file", "symbol_reference", "code_analysis", "runtime_observation"}
SEED_VALIDATOR_VERSION = "hack.seed-validator.v1"
DEFAULT_VALIDATION_MAX_AGE_SECONDS = 3600
REQUIRED_SEED_KEYS = {
    "target_profile",
    "seedStrategySet",
    "recommended_fuzzing_lanes",
    "excluded_lanes",
    "seed_population_plan",
    "campaign_safety_constraints",
    "human_interview_questions",
    "source_urls",
    "artifact_paths",
    "code_analysis_sources",
    "research_confidence",
}
LANE_EVIDENCE_KEYWORDS = {
    "api_protocol": ("api", "http", "route", "gateway", "/v1", "runtime api"),
    "stateful_workflow": ("state", "workflow", "session", "job", "lifecycle", "sequence", "history"),
    "auth_session": ("auth", "authorization", "token", "session", "identity", "privileged", "bearer"),
    "websocket_control": ("websocket", "upgrade", "socket", "hook", "control channel"),
    "filesystem_path": ("file", "path", "filesystem", "workspace", "archive", "symlink", "upload", "download"),
    "child_process_tool": ("child process", "process", "spawn", "subprocess", "command", "tool", "cli"),
    "parser_dependency": ("parser", "parse", "json", "yaml", "toml", "xml", "markdown", "document"),
    "native_binary": ("native", "binary", "compiled", "c++", "rust", "go", "sanitizer"),
    "wasm": ("wasm", "wasm-pack", "emscripten"),
    "electron_webkit": ("electron", "webkit", "preload", "ipc", "desktop"),
    "language_runtime": ("eval", "dynamic import", "sandbox", "plugin", "interpreter", "template", "untrusted code"),
    "dependency_supply_chain": ("package", "lockfile", "dependency", "supply chain", "manifest", "sca"),
}


@dataclass(frozen=True)
class EvolutionConfig:
    target_url: str
    artifact_dir: Path
    max_attempts: int = 100
    max_generations: int = 4
    population_size: int = 16
    seed: int = 0
    duration_seconds: int = 60
    slow_ms: int = 3_000
    anomaly_gate: int = 1
    allow_nonlocal: bool = False


@dataclass(frozen=True)
class SeedEvidence:
    last_plan_summary: str = "not provided"
    dogpile_summary: str = "not provided"
    scanner_findings_summary: str = "not provided"
    research_summary: str = (
        "Evolutionary greybox fuzzing should prioritize seeds by runtime feedback, "
        "combine distance-like route focus with value-flow-influencing payloads, "
        "preserve diversity through mutation, and use selective instrumentation so "
        "the campaign spends budget on critical API surfaces instead of blind scans."
    )


@dataclass(frozen=True)
class StrategyGene:
    gene_id: str
    method: str
    path: str
    header_variant: str
    body_variant: str
    transport: str
    mutation: str
    source: str
    risk_boundary: str
    energy: float = 1.0
    lineage: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class StrategyGenome:
    generation: int
    genes: tuple[StrategyGene, ...]
    evidence: SeedEvidence


@dataclass(frozen=True)
class AttemptRecord:
    attempt: int
    generation: int
    gene: StrategyGene
    result: dict[str, Any]
    score: float
    anomaly: str | None = None


@dataclass(frozen=True)
class AnomalyRecord:
    attempt: int
    generation: int
    gene_id: str
    reason: str
    score: float
    evidence_path: str
    classification: str = "retained_anomaly"
    promotion_ready: bool = False
    gate_decision: str = "retain"


@dataclass(frozen=True)
class GenerationSummary:
    generation: int
    attempts: int
    anomalies: int
    best_score: float
    selected_gene_ids: tuple[str, ...]


@dataclass(frozen=True)
class PromotionTask:
    task_id: str
    anomaly_evidence_path: str
    objective: str
    blue_team_patch_hypothesis: str
    suggested_runner: str = "code-runner"
    patch_status: str = "proposed"
    verification_contract: dict[str, Any] = field(default_factory=dict)


def baseline_genes() -> tuple[StrategyGene, ...]:
    boundary = "Docker-contained, authorized local/private hardening probe; raw request details stay in artifacts."
    rows = [
        ("GET", "/healthz", "none", "empty", "http", "plain", "built_in_baseline"),
        ("GET", "/readyz", "none", "empty", "http", "plain", "built_in_baseline"),
        ("GET", "/api/diagnostics/prometheus", "none", "empty", "http", "plain", "scanner"),
        ("GET", "/v1/models", "invalid-bearer", "empty", "http", "query-cache-bust", "built_in_baseline"),
        ("POST", "/v1/chat/completions", "json-content-type", "json-tool", "http", "plain", "dogpile"),
        ("POST", "/v1/responses", "json-content-type", "json-command-tokens", "http", "plain", "dogpile"),
        ("POST", "/tools/invoke", "invalid-bearer", "json-tool", "http", "plain", "last_plan"),
        ("POST", "/tools/invoke", "spoof-loopback-forwarded-for", "json-path-traversal", "http", "dotdot", "dogpile"),
        ("GET", "/sessions/main/history", "invalid-bearer", "empty", "http", "case-flip", "last_plan"),
        ("DELETE", "/sessions/main/kill", "invalid-bearer", "empty", "http", "query-token", "last_plan"),
        ("GET", "/hooks/wake", "evil-origin", "empty", "websocket-handshake", "plain", "dogpile"),
        ("GET", "/hooks/agent", "null-origin", "empty", "websocket-handshake", "encoded-slash", "dogpile"),
        ("GET", "/__openclaw/control-ui-config.json", "none", "empty", "http", "query-cache-bust", "scanner"),
        ("GET", "/__openclaw/media/%2e%2e/%2e%2e/etc/passwd", "none", "empty", "http", "dotdot", "scanner"),
        ("POST", "/v1/embeddings", "oversized-header", "oversized-json", "http", "plain", "runtime_anomaly"),
        ("POST", "/v1/chat/completions", "spoof-private-forwarded-for", "malformed-json", "http", "double-slash", "runtime_anomaly"),
    ]
    return tuple(
        StrategyGene(
            gene_id=f"g0-{idx:03d}",
            method=method,
            path=path,
            header_variant=header,
            body_variant=body,
            transport=transport,
            mutation=mutation,
            source=source,
            risk_boundary=boundary,
        )
        for idx, (method, path, header, body, transport, mutation, source) in enumerate(rows)
    )


def build_initial_genome(seed_evidence: SeedEvidence, seed_payload: dict[str, Any] | None = None) -> StrategyGenome:
    """Build generation zero, including chaos-style uncommon combinations."""

    genes = genes_from_seed_payload(seed_payload) if seed_payload else baseline_genes()
    return StrategyGenome(generation=0, genes=genes, evidence=seed_evidence)


def genes_from_seed_payload(seed_payload: dict[str, Any] | None) -> tuple[StrategyGene, ...]:
    if not isinstance(seed_payload, dict):
        return tuple()
    strategy_set = seed_payload.get("seedStrategySet")
    strategies = strategy_set.get("lane_seed_strategies", []) if isinstance(strategy_set, dict) else []
    genes: list[StrategyGene] = []
    for strategy in strategies if isinstance(strategies, list) else []:
        if not isinstance(strategy, dict) or strategy.get("enabled") is not True:
            continue
        lane_id = str(strategy.get("lane_id") or "")
        for seed_index, seed_gene in enumerate(strategy.get("starting_genes", []) if isinstance(strategy.get("starting_genes"), list) else []):
            if not isinstance(seed_gene, dict):
                continue
            genes.append(_strategy_gene_from_seed(lane_id, seed_gene, len(genes), seed_index))
    return tuple(genes)


def _strategy_gene_from_seed(lane_id: str, seed_gene: dict[str, Any], index: int, seed_index: int) -> StrategyGene:
    seed_type = str(seed_gene.get("seed_type") or "")
    seed_value = str(seed_gene.get("seed_value") or "")
    path = seed_value if seed_type == "route" and seed_value.startswith("/") else _default_path_for_lane(lane_id)
    method = "POST" if lane_id in {"child_process_tool", "parser_dependency"} else "GET"
    transport = "websocket-handshake" if lane_id == "websocket_control" else "http"
    return StrategyGene(
        gene_id=f"seed-{index:03d}-{safe_slug(lane_id)}-{seed_index}",
        method=method,
        path=path,
        header_variant="invalid-bearer" if lane_id in {"api_protocol", "auth_session", "stateful_workflow"} else "none",
        body_variant="json-empty" if method == "POST" else "empty",
        transport=transport,
        mutation="plain",
        source=f"validated_seed:{lane_id}",
        risk_boundary="Docker-contained, authorized local/private hardening probe derived from validated seed research.",
    )


def _default_path_for_lane(lane_id: str) -> str:
    defaults = {
        "api_protocol": "/v1/models",
        "stateful_workflow": "/sessions/main/history",
        "auth_session": "/v1/models",
        "websocket_control": "/hooks/wake",
        "filesystem_path": "/__openclaw/control-ui-config.json",
        "child_process_tool": "/tools/invoke",
        "parser_dependency": "/v1/chat/completions",
        "language_runtime": "/v1/responses",
        "dependency_supply_chain": "/__openclaw/control-ui-config.json",
    }
    return defaults.get(lane_id, "/")


def _content_type(result: dict[str, Any]) -> str:
    headers = result.get("headers")
    if not isinstance(headers, dict):
        return ""
    for header, value in headers.items():
        if str(header).lower() == "content-type":
            return str(value).lower()
    return ""


def _is_spa_shell_fallback(result: dict[str, Any]) -> bool:
    content_type = _content_type(result)
    body = str(result.get("body", "")).lstrip().lower()
    if "text/html" not in content_type:
        return False
    return body.startswith("<!doctype html") or body.startswith("<html") or "<title>openclaw control</title>" in body


def _response_shape(result: dict[str, Any]) -> str:
    body = str(result.get("body", "")).lstrip()
    content_type = _content_type(result)
    if "application/json" in content_type or body.startswith(("{", "[")):
        return "json"
    if "text/html" in content_type or body.lower().startswith(("<!doctype html", "<html")):
        return "html"
    if body:
        return "text"
    return "empty"


def _expected_response_shape(gene: StrategyGene) -> str:
    if gene.path.startswith("/v1/") or gene.path.startswith("/tools/"):
        return "json"
    if gene.path == "/api/diagnostics/prometheus":
        return "text"
    if gene.path.endswith(".json"):
        return "json"
    return "any"


def _has_sensitive_disclosure(result: dict[str, Any]) -> bool:
    body = str(result.get("body", "")).lower()
    return any(token in body for token in ("secret", "token", "traceback", "exception", "stack"))


def build_signal_profile(record: AttemptRecord) -> dict[str, Any]:
    """Return the real-signal gate profile for one attempt."""

    status = record.result.get("status")
    response_shape = _response_shape(record.result)
    expected_shape = _expected_response_shape(record.gene)
    source_lineage = [record.gene.source, *record.gene.lineage]
    negative_filters: list[str] = []
    positive_signals: list[str] = []

    if _is_spa_shell_fallback(record.result):
        negative_filters.append("html_app_shell_fallback")
    if status in {404, 405}:
        negative_filters.append("normal_missing_or_method_response")
    if record.gene.path in {"/", "/healthz", "/readyz"}:
        negative_filters.append("normal_health_or_root_response")
    if status == 200:
        positive_signals.append("http_200")
    if expected_shape != "any" and response_shape == expected_shape:
        positive_signals.append(f"expected_{expected_shape}_shape")
    if _has_sensitive_disclosure(record.result):
        positive_signals.append("sensitive_disclosure_token")
    if record.gene.source not in {"built_in_baseline"} or record.gene.lineage:
        positive_signals.append("source_lineage")

    auth_expectation = (
        "unauthenticated_or_invalid_auth_should_not_succeed"
        if record.gene.header_variant in {"none", "invalid-bearer", "query-token"}
        else "explicit_auth_variant"
    )
    route_validity = "candidate_route" if record.gene.path.startswith("/") else "invalid_route"
    shape_ok = expected_shape == "any" or response_shape == expected_shape
    real_signal = (
        isinstance(status, int)
        and status == 200
        and not negative_filters
        and (shape_ok or _has_sensitive_disclosure(record.result))
        and route_validity == "candidate_route"
    )

    return {
        "content_type": _content_type(record.result),
        "response_shape": response_shape,
        "expected_response_shape": expected_shape,
        "response_shape_ok": shape_ok,
        "auth_expectation": auth_expectation,
        "route_validity": route_validity,
        "source_lineage": source_lineage,
        "positive_signals": positive_signals,
        "negative_filters": negative_filters,
        "real_signal": real_signal,
    }


def _is_unexpected_success(record: AttemptRecord) -> bool:
    status = record.result.get("status")
    if not isinstance(status, int) or status != 200:
        return False
    return bool(build_signal_profile(record)["real_signal"])


def score_attempt(record: AttemptRecord) -> float:
    result = record.result
    score = 0.0
    status = result.get("status")
    status_line = str(result.get("status_line", ""))
    elapsed = float(result.get("elapsed_ms", 0) or 0)
    if isinstance(status, int) and status >= 500:
        score += 10.0
    if _is_unexpected_success(record):
        score += 7.0
    if "101" in status_line:
        score += 9.0
    if result.get("error") in {"ConnectionResetError", "RemoteDisconnected", "ConnectionAbortedError"}:
        score += 6.0
    if elapsed > 3_000:
        score += 3.0
    if _has_sensitive_disclosure(result):
        score += 5.0
    if record.gene.source in {"dogpile", "runtime_anomaly"}:
        score += 0.5
    return round(score, 3)


def classify_anomaly(record: AttemptRecord) -> AnomalyRecord | None:
    result = record.result
    reason = record.anomaly
    status = result.get("status")
    status_line = str(result.get("status_line", ""))
    signal_profile = build_signal_profile(record)
    if reason is None and isinstance(status, int) and status >= 500:
        reason = "server-error"
    if reason is None and _is_unexpected_success(record):
        reason = "unexpected-unauthenticated-200"
    if reason is None and "101" in status_line:
        reason = "unauthenticated-websocket-upgrade"
    if reason is None and result.get("error") in {"ConnectionResetError", "RemoteDisconnected", "ConnectionAbortedError"}:
        reason = "connection-reset"
    if reason is None and float(result.get("elapsed_ms", 0) or 0) > 3_000:
        reason = "slow-response"
    if reason is None:
        return None
    classification = classify_attempt(record, reason, signal_profile)
    promotion_ready = classification == "proof_candidate" and is_reproducible_result(result)
    return AnomalyRecord(
        attempt=record.attempt,
        generation=record.generation,
        gene_id=record.gene.gene_id,
        reason=reason,
        score=record.score,
        evidence_path="attempts.jsonl",
        classification=classification,
        promotion_ready=promotion_ready,
        gate_decision="promote" if promotion_ready else "retain",
    )


def classify_attempt(
    record: AttemptRecord,
    reason: str | None = None,
    signal_profile: dict[str, Any] | None = None,
) -> str:
    profile = signal_profile or build_signal_profile(record)
    if profile["negative_filters"]:
        return "false_positive"
    if reason is None and record.score <= 0:
        return "dead_end"
    if reason in {"server-error", "connection-reset", "slow-response"}:
        return "partial_signal"
    if reason in {"unexpected-unauthenticated-200", "unauthenticated-websocket-upgrade"}:
        return "proof_candidate" if profile["real_signal"] else "promising_parent"
    if record.score > 0:
        return "promising_parent"
    return "dead_end"


def is_reproducible_result(result: dict[str, Any]) -> bool:
    if result.get("reproduced") is True:
        return True
    repeat_count = result.get("repeat_count")
    return isinstance(repeat_count, int) and repeat_count >= 2


def select_parent_genes(genome: StrategyGenome, attempts: list[AttemptRecord], limit: int) -> list[StrategyGene]:
    if limit <= 0:
        return []
    scored = sorted(attempts, key=lambda item: (-item.score, item.attempt))
    selected: list[StrategyGene] = []
    seen: set[str] = set()
    for attempt in scored:
        if attempt.gene.gene_id not in seen:
            selected.append(attempt.gene)
            seen.add(attempt.gene.gene_id)
        if len(selected) >= limit:
            return selected
    for gene in genome.genes:
        if gene.gene_id not in seen:
            selected.append(gene)
            seen.add(gene.gene_id)
        if len(selected) >= limit:
            break
    return selected


def mutate_gene(gene: StrategyGene, seed: int) -> StrategyGene:
    rng = random.Random(seed)
    methods = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    headers = [
        "none",
        "invalid-bearer",
        "query-token",
        "spoof-loopback-forwarded-for",
        "spoof-private-forwarded-for",
        "json-content-type",
        "oversized-header",
        "evil-origin",
        "null-origin",
    ]
    bodies = ["empty", "json-empty", "json-tool", "json-path-traversal", "json-command-tokens", "oversized-json", "malformed-json"]
    mutations = ["plain", "double-slash", "encoded-slash", "dotdot", "case-flip", "query-cache-bust", "query-token", "double-encoded-dotdot"]
    axis = rng.choice(["method", "header", "body", "mutation", "energy"])
    updates: dict[str, Any] = {
        "gene_id": f"{gene.gene_id}.m{seed % 100000:05d}",
        "source": "runtime_anomaly",
        "lineage": gene.lineage + (gene.gene_id,),
    }
    if axis == "method":
        updates["method"] = rng.choice(methods)
    elif axis == "header":
        updates["header_variant"] = rng.choice(headers)
    elif axis == "body":
        updates["body_variant"] = rng.choice(bodies)
    elif axis == "mutation":
        updates["mutation"] = rng.choice(mutations)
    else:
        updates["energy"] = round(min(gene.energy + 0.25, 3.0), 2)
    return replace(gene, **updates)


def build_generation_summary(generation: int, attempts: list[AttemptRecord], selected: Iterable[StrategyGene]) -> GenerationSummary:
    return GenerationSummary(
        generation=generation,
        attempts=len(attempts),
        anomalies=sum(1 for attempt in attempts if attempt.anomaly),
        best_score=max((attempt.score for attempt in attempts), default=0.0),
        selected_gene_ids=tuple(gene.gene_id for gene in selected),
    )


def build_promotion_task(anomaly: AnomalyRecord) -> PromotionTask:
    return PromotionTask(
        task_id=f"promote-{anomaly.gene_id}-{anomaly.attempt}",
        anomaly_evidence_path=anomaly.evidence_path,
        objective=f"Reproduce and minimize `{anomaly.reason}` from evolutionary campaign artifacts.",
        blue_team_patch_hypothesis="Add or tighten central auth/rate/normalization/error-handling gate for the affected route family.",
        verification_contract={
            "implementation_path": "/plan -> /review-plan -> /orchestrate -> /code-runner",
            "hack_role": "rerun Docker proof and record verification evidence; do not apply patches directly",
            "required_patch_status_values": [
                "proposed",
                "implementation_requested",
                "implemented_unverified",
                "verified",
                "deferred",
                "rejected",
            ],
            "verified_requires": ["patch_applied_by_downstream", "tests_run", "hack_docker_proof_rerun_artifact"],
        },
    )


def _write_jsonl(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def validate_config(config: EvolutionConfig, evidence: SeedEvidence) -> str | None:
    if config.max_attempts <= 0 or config.max_generations <= 0:
        return "max_attempts and max_generations must be positive"
    if config.population_size <= 0:
        return "population_size must be positive"
    if not config.allow_nonlocal and not is_local_or_private_target(config.target_url):
        return "target must be loopback/private unless --allow-nonlocal is explicit"
    if not config.artifact_dir.exists() or not config.artifact_dir.is_dir():
        return "artifact directory must exist"
    if not any(
        value and value != "not provided"
        for value in (
            evidence.last_plan_summary,
            evidence.dogpile_summary,
            evidence.scanner_findings_summary,
            evidence.research_summary,
        )
    ):
        return "seed evidence is empty"
    return None


def validate_seed_research_payload(payload: Any, *, verify_paths: bool = False) -> list[str]:
    """Validate Dogpile seed research before it feeds /plan or /hack."""
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["payload must be a JSON object"]

    missing_keys = sorted(REQUIRED_SEED_KEYS - set(payload))
    if missing_keys:
        errors.append("seed payload missing required keys: " + ", ".join(missing_keys))

    target_url = seed_target_url(payload)
    target_profile = payload.get("target_profile")
    if not isinstance(target_profile, dict):
        errors.append("target_profile must be an object")
    elif not target_url:
        errors.append("target_profile.target_url is required")
    elif not is_local_or_private_target(target_url):
        errors.append("target_profile.target_url must be loopback/private for /hack evolve-campaign")

    recommended = payload.get("recommended_fuzzing_lanes")
    excluded = payload.get("excluded_lanes")
    strategy_set = payload.get("seedStrategySet")
    recommended_items = recommended if isinstance(recommended, list) else []
    excluded_items = excluded if isinstance(excluded, list) else []
    strategies = strategy_set.get("lane_seed_strategies") if isinstance(strategy_set, dict) else None
    strategy_items = strategies if isinstance(strategies, list) else []

    if not recommended_items:
        errors.append("recommended_fuzzing_lanes must be a non-empty array")
    if not isinstance(strategy_set, dict):
        errors.append("seedStrategySet must be an object")
    elif strategy_set.get("schema_version") != "hack.evolution.seedStrategySet.v1":
        errors.append("seedStrategySet.schema_version must equal hack.evolution.seedStrategySet.v1")

    recommended_lanes = _lane_ids(recommended_items, "recommended_fuzzing_lanes", errors)
    excluded_lanes = _lane_ids(excluded_items, "excluded_lanes", errors)
    strategy_lanes = _lane_ids(strategy_items, "seedStrategySet.lane_seed_strategies", errors)
    all_decided = recommended_lanes + excluded_lanes
    duplicate_decisions = sorted({lane for lane in all_decided if all_decided.count(lane) > 1})
    for lane in duplicate_decisions:
        errors.append(f"lane {lane} appears more than once across recommended_fuzzing_lanes and excluded_lanes")
    missing_lanes = sorted(set(LANE_IDS) - set(all_decided))
    extra_lanes = sorted(set(all_decided) - set(LANE_IDS))
    if missing_lanes:
        errors.append("every lane must be decided exactly once; missing: " + ", ".join(missing_lanes))
    if extra_lanes:
        errors.append("unknown lane IDs: " + ", ".join(extra_lanes))
    for lane in sorted(set(recommended_lanes) & set(excluded_lanes)):
        errors.append(f"lane {lane} appears in both recommended_fuzzing_lanes and excluded_lanes")

    for item in recommended_items:
        if not isinstance(item, dict):
            continue
        lane = str(item.get("lane_id") or "")
        sources = item.get("supporting_sources")
        source_items = sources if isinstance(sources, list) else []
        if not source_items:
            errors.append(f"recommended lane {lane or '<missing>'} must include supporting_sources")
        if source_items and not _has_target_source(source_items):
            errors.append(f"recommended lane {lane or '<missing>'} has no target-specific supporting source")
        if lane and source_items and not _lane_source_supports(lane, source_items):
            errors.append(f"recommended lane {lane} lacks lane-specific supporting evidence")
        for source_error in _source_errors(source_items, f"recommended lane {lane or '<missing>'}", verify_paths=verify_paths):
            errors.append(source_error)
        if lane in HTTP_CAPABLE_LANES and not _contains_spa_filter(item.get("false_positive_filters")):
            errors.append(f"recommended HTTP-capable lane {lane} must include SPA HTML fallback filter")

    for item in excluded_items:
        if not isinstance(item, dict):
            continue
        lane = str(item.get("lane_id") or "")
        missing_evidence = item.get("missing_evidence")
        if not isinstance(missing_evidence, list) or not missing_evidence:
            errors.append(f"excluded lane {lane or '<missing>'} must include missing_evidence")

    for lane in LOW_LEVEL_LANES:
        if lane in recommended_lanes:
            item = next((entry for entry in recommended_items if isinstance(entry, dict) and entry.get("lane_id") == lane), {})
            if not _has_target_source(item.get("supporting_sources") if isinstance(item, dict) else None):
                errors.append(f"{lane} must be excluded unless concrete target evidence supports it")
        elif lane not in excluded_lanes:
            errors.append(f"{lane} must be excluded unless concrete target evidence supports it")

    recommended_set = set(recommended_lanes)
    excluded_set = set(excluded_lanes)
    for strategy in strategy_items:
        if not isinstance(strategy, dict):
            continue
        lane = str(strategy.get("lane_id") or "")
        enabled = strategy.get("enabled")
        gate = strategy.get("evidence_gate")
        gate_status = gate.get("status") if isinstance(gate, dict) else None
        if enabled is True:
            if lane not in recommended_set:
                errors.append(f"enabled strategy lane {lane or '<missing>'} must also be recommended")
            if not strategy.get("starting_genes"):
                errors.append(f"enabled strategy lane {lane or '<missing>'} must include starting_genes")
            if not strategy.get("fitness_signals"):
                errors.append(f"enabled strategy lane {lane or '<missing>'} must include fitness_signals")
            promotion_gate = strategy.get("promotion_gate")
            if not isinstance(promotion_gate, dict):
                errors.append(f"enabled strategy lane {lane or '<missing>'} must include promotion_gate")
            elif lane in HTTP_CAPABLE_LANES and not _contains_spa_filter(promotion_gate.get("negative_filters")):
                errors.append(f"enabled HTTP-capable strategy lane {lane} must include SPA HTML fallback negative filter")
        if lane in excluded_set and (enabled is not False or gate_status != "blocked"):
            errors.append(f"excluded lane {lane} strategy must be disabled with evidence_gate.status blocked")

    for lane in sorted(recommended_set - set(strategy_lanes)):
        errors.append(f"recommended lane {lane} must have a lane_seed_strategy")

    questions = payload.get("human_interview_questions")
    if not isinstance(questions, list) or not 3 <= len(questions) <= 7:
        errors.append("human_interview_questions must contain between 3 and 7 questions")
    source_urls = payload.get("source_urls")
    if not isinstance(source_urls, list) or not source_urls:
        errors.append("source_urls must contain at least one paper or implementation URL")
    artifact_paths = payload.get("artifact_paths")
    has_hack_artifact = isinstance(artifact_paths, list) and any("/mnt/storage12tb/artifacts/agent-skills/hack/" in str(path) for path in artifact_paths)
    if verify_paths and isinstance(artifact_paths, list):
        has_hack_artifact = has_hack_artifact or any(str(path).startswith("/") and Path(str(path)).exists() for path in artifact_paths)
    if not has_hack_artifact:
        errors.append("artifact_paths must include at least one /mnt/storage12tb/artifacts/agent-skills/hack/ path")
    for path_error in _artifact_path_errors(artifact_paths, verify_paths=verify_paths):
        errors.append(path_error)
    code_sources = payload.get("code_analysis_sources")
    if not isinstance(code_sources, list) or not any(_is_internal_code_source(source) for source in code_sources):
        errors.append("code_analysis_sources must cite an internal code-analysis source or source_type unavailable")
    for source_error in _source_errors(code_sources if isinstance(code_sources, list) else [], "code_analysis_sources", verify_paths=verify_paths):
        errors.append(source_error)

    plan = payload.get("seed_population_plan")
    if isinstance(plan, dict) and not isinstance(plan.get("minimum_seed_count"), int):
        errors.append("seed_population_plan.minimum_seed_count must be a JSON number")
    for group in plan.get("seed_groups", []) if isinstance(plan, dict) else []:
        if isinstance(group, dict) and not isinstance(group.get("max_initial_attempts"), int):
            errors.append("seed_population_plan.seed_groups[].max_initial_attempts must be JSON numbers")

    constraints = payload.get("campaign_safety_constraints")
    if not isinstance(constraints, dict):
        errors.append("campaign_safety_constraints must be an object")
    elif not isinstance(constraints.get("promotion_requires_reproduction"), bool):
        errors.append("campaign_safety_constraints.promotion_requires_reproduction must be a JSON boolean")
    if isinstance(constraints, dict):
        allowed_targets = constraints.get("allowed_targets")
        if not isinstance(allowed_targets, list) or not allowed_targets:
            errors.append("campaign_safety_constraints.allowed_targets must be a non-empty array")
        elif target_url and target_url not in {str(item) for item in allowed_targets}:
            errors.append("campaign_safety_constraints.allowed_targets must include target_profile.target_url")
    for strategy in strategy_items:
        if not isinstance(strategy, dict):
            continue
        if "enabled" in strategy and not isinstance(strategy.get("enabled"), bool):
            errors.append(f"strategy {strategy.get('lane_id') or '<missing>'} enabled must be a JSON boolean")
        gate = strategy.get("promotion_gate")
        if isinstance(gate, dict) and "requires_reproduction" in gate and not isinstance(gate.get("requires_reproduction"), bool):
            errors.append(f"strategy {strategy.get('lane_id') or '<missing>'} promotion_gate.requires_reproduction must be a JSON boolean")

    raw_probe_errors = _raw_probe_string_errors(payload)
    errors.extend(raw_probe_errors)

    return errors


def seed_payload_sha256(seed_json: Path) -> str:
    return sha256(seed_json.read_bytes()).hexdigest()


def seed_target_url(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    target_profile = payload.get("target_profile")
    if isinstance(target_profile, dict) and target_profile.get("target_url"):
        return str(target_profile["target_url"])
    strategy_set = payload.get("seedStrategySet")
    if isinstance(strategy_set, dict) and strategy_set.get("target_url"):
        return str(strategy_set["target_url"])
    constraints = payload.get("campaign_safety_constraints")
    allowed_targets = constraints.get("allowed_targets") if isinstance(constraints, dict) else None
    if isinstance(allowed_targets, list) and allowed_targets:
        return str(allowed_targets[0])
    return None


def validate_seed_file(
    seed_json: Path,
    *,
    result_output: Path | None = None,
    verify_paths: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "valid": False,
        "errors": [],
        "path": str(seed_json.resolve()),
        "seed_sha256": None,
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "validator_version": SEED_VALIDATOR_VERSION,
        "verify_paths": verify_paths,
        "target_url": None,
    }
    try:
        result["seed_sha256"] = seed_payload_sha256(seed_json)
        payload = json.loads(seed_json.read_text())
    except Exception as exc:
        result["errors"] = [f"{type(exc).__name__}: {exc}"]
        _write_validation_result(result, result_output)
        return result

    errors = validate_seed_research_payload(payload, verify_paths=verify_paths)
    result.update(
        {
            "valid": not errors,
            "errors": errors,
            "target_url": seed_target_url(payload),
        }
    )
    _write_validation_result(result, result_output)
    return result


def load_validated_seed(
    seed_json: Path,
    validation_result: Path,
    *,
    target_url: str,
    max_age_seconds: int = DEFAULT_VALIDATION_MAX_AGE_SECONDS,
    require_verified_paths: bool = True,
) -> tuple[dict[str, Any] | None, list[str], dict[str, Any] | None]:
    errors: list[str] = []
    if not seed_json.exists():
        errors.append(f"seed JSON does not exist: {seed_json}")
    if not validation_result.exists():
        errors.append(f"seed validation result does not exist: {validation_result}")
    if errors:
        return None, errors, None

    try:
        payload = json.loads(seed_json.read_text())
    except Exception as exc:
        return None, [f"seed JSON cannot be parsed: {type(exc).__name__}: {exc}"], None
    try:
        result = json.loads(validation_result.read_text())
    except Exception as exc:
        return None, [f"seed validation result cannot be parsed: {type(exc).__name__}: {exc}"], None

    current_hash = seed_payload_sha256(seed_json)
    if result.get("valid") is not True:
        errors.append("seed validation result is not valid")
    if result.get("validator_version") != SEED_VALIDATOR_VERSION:
        errors.append("seed validation result validator_version is stale or unknown")
    if str(seed_json.resolve()) != str(result.get("path")):
        errors.append("seed validation result path does not match --seed-json")
    if current_hash != result.get("seed_sha256"):
        errors.append("seed validation result hash does not match current seed JSON")
    result_target = result.get("target_url")
    payload_target = seed_target_url(payload)
    if target_url != result_target or target_url != payload_target:
        errors.append("seed validation target_url does not match evolve-campaign target")
    if require_verified_paths and result.get("verify_paths") is not True:
        errors.append("seed validation result must be produced with --verify-paths")

    validated_at = str(result.get("validated_at") or "")
    try:
        validated_dt = datetime.fromisoformat(validated_at)
        if validated_dt.tzinfo is None:
            validated_dt = validated_dt.replace(tzinfo=timezone.utc)
        age_seconds = (datetime.now(timezone.utc) - validated_dt.astimezone(timezone.utc)).total_seconds()
        if age_seconds > max_age_seconds:
            errors.append("seed validation result is stale")
    except ValueError:
        errors.append("seed validation result has invalid validated_at timestamp")

    rerun_errors = validate_seed_research_payload(payload, verify_paths=require_verified_paths or bool(result.get("verify_paths")))
    if rerun_errors:
        errors.append("seed validation result no longer validates current seed JSON: " + "; ".join(rerun_errors))
    if errors:
        return None, errors, result
    return payload, [], result


def _write_validation_result(result: dict[str, Any], result_output: Path | None) -> None:
    if result_output is None:
        return
    result_output.parent.mkdir(parents=True, exist_ok=True)
    result_output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


def create_validate_seed_command() -> Callable[..., None]:
    def validate_seed(
        seed_json: Path = typer.Argument(..., help="Dogpile seed research JSON artifact to validate."),
        json_output: bool = typer.Option(False, "--json", help="Emit machine-readable validation result."),
        result_output: Path | None = typer.Option(None, "--result-output", help="Persist validation result JSON for /plan or /hack handoff."),
        verify_paths: bool = typer.Option(False, "--verify-paths", help="Require concrete artifact/file paths to exist when cited."),
    ) -> None:
        result = validate_seed_file(seed_json, result_output=result_output, verify_paths=verify_paths)
        errors = list(result.get("errors") if isinstance(result.get("errors"), list) else [])
        if json_output:
            console.print(json.dumps(result, indent=2, sort_keys=True))
        elif errors:
            console.print("[red]Seed research validation failed[/red]")
            for error in errors:
                console.print(f"- {error}")
        else:
            console.print("[green]Seed research validation passed[/green]")
        if errors:
            raise typer.Exit(2)

    return validate_seed


def _lane_ids(items: list[Any], label: str, errors: list[str]) -> list[str]:
    lanes: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"{label}[{index}] must be an object")
            continue
        lane = str(item.get("lane_id") or "")
        if not lane:
            errors.append(f"{label}[{index}].lane_id is required")
            continue
        lanes.append(lane)
        if lane not in LANE_IDS:
            errors.append(f"{label}[{index}].lane_id has unknown lane {lane}")
    return lanes


def _has_target_source(sources: Any) -> bool:
    if not isinstance(sources, list):
        return False
    for source in sources:
        if not isinstance(source, dict):
            continue
        source_type = str(source.get("source_type") or "")
        source_value = str(source.get("source") or "")
        quote_or_fact = str(source.get("quote_or_fact") or "")
        if source_type in TARGET_SOURCE_TYPES and quote_or_fact.strip():
            return True
        if source_type == "dogpile_result" and any(marker in source_value for marker in ("/mnt/storage12tb/artifacts/agent-skills/hack/", ".json", ".md")):
            return True
    return False


def _lane_source_supports(lane: str, sources: list[Any]) -> bool:
    keywords = LANE_EVIDENCE_KEYWORDS.get(lane, ())
    if not keywords:
        return False
    for source in sources:
        if not isinstance(source, dict):
            continue
        text = " ".join(
            str(source.get(field) or "")
            for field in ("source_type", "source", "quote_or_fact")
        ).lower()
        if any(keyword in text for keyword in keywords):
            return True
    return False


def _source_errors(sources: list[Any], label: str, *, verify_paths: bool) -> list[str]:
    errors: list[str] = []
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            continue
        source_type = str(source.get("source_type") or "")
        source_value = str(source.get("source") or "")
        quote_or_fact = str(source.get("quote_or_fact") or "")
        if _is_generic_instruction_source(source_value, quote_or_fact):
            errors.append(f"{label} supporting source {index} restates source-class instructions instead of concrete evidence")
        if verify_paths and source_type in {"artifact_path", "repository_file", "code_analysis", "semgrep", "ingest_code", "treesitter"}:
            if source_value.startswith("/") and not Path(source_value).exists():
                errors.append(f"{label} source path does not exist: {source_value}")
    return errors


def _artifact_path_errors(paths: Any, *, verify_paths: bool) -> list[str]:
    if not isinstance(paths, list):
        return []
    errors: list[str] = []
    for index, item in enumerate(paths):
        path = str(item)
        if verify_paths and path.startswith("/") and not Path(path).exists():
            errors.append(f"artifact_paths[{index}] path does not exist: {path}")
    return errors


def _contains_spa_filter(value: Any) -> bool:
    text = json.dumps(value, sort_keys=True).lower() if value is not None else ""
    return (
        ("spa" in text or "app-shell" in text or "app shell" in text)
        and ("text/html" in text or "html" in text)
        and ("fallback" in text or "http 200" in text or "200" in text)
    )


def _is_internal_code_source(source: Any) -> bool:
    if not isinstance(source, dict):
        return False
    source_type = str(source.get("source_type") or "")
    source_value = str(source.get("source") or "")
    quote_or_fact = str(source.get("quote_or_fact") or "")
    if source_type == "unavailable":
        return bool(quote_or_fact.strip())
    if source_type in {"ingest_code", "treesitter", "semgrep", "repository_file", "symbol_reference"}:
        return bool(source_value.strip() and quote_or_fact.strip())
    return False


def _is_generic_instruction_source(source_value: str, quote_or_fact: str) -> bool:
    text = f"{source_value} {quote_or_fact}".lower()
    generic_markers = (
        "use prior /ingest-code analysis",
        "prior /ingest-code analysis exists",
        "prior symbol/source analysis exists",
        "required_use",
        "source class",
        "source classes",
    )
    return any(marker in text for marker in generic_markers)


def _raw_probe_string_errors(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    strategy_set = payload.get("seedStrategySet")
    strategies = strategy_set.get("lane_seed_strategies", []) if isinstance(strategy_set, dict) else []
    for strategy in strategies if isinstance(strategies, list) else []:
        if not isinstance(strategy, dict):
            continue
        lane = str(strategy.get("lane_id") or "<missing>")
        for index, gene in enumerate(strategy.get("starting_genes", []) if isinstance(strategy.get("starting_genes"), list) else []):
            if not isinstance(gene, dict):
                continue
            for field in ("seed_value", "mutation_axes"):
                value = gene.get(field)
                if _contains_raw_probe_string(value):
                    errors.append(f"strategy {lane} starting_genes[{index}].{field} contains raw probe or payload string")
        promotion_gate = strategy.get("promotion_gate")
        if isinstance(promotion_gate, dict):
            for field in ("positive_signals", "negative_filters", "artifact_requirements"):
                if _contains_raw_probe_string(promotion_gate.get(field)):
                    errors.append(f"strategy {lane} promotion_gate.{field} contains raw probe or payload string")
    for index, lane in enumerate(payload.get("recommended_fuzzing_lanes", []) if isinstance(payload.get("recommended_fuzzing_lanes"), list) else []):
        if not isinstance(lane, dict):
            continue
        lane_id = str(lane.get("lane_id") or "<missing>")
        for field in ("starting_seed_inputs", "mutation_axes", "promotion_criteria"):
            if _contains_raw_probe_string(lane.get(field)):
                errors.append(f"recommended lane {lane_id} {field} contains raw probe or payload string")
    return errors


def _contains_raw_probe_string(value: Any) -> bool:
    if value is None:
        return False
    text = json.dumps(value, sort_keys=True).lower() if not isinstance(value, str) else value.lower()
    patterns = (
        r"\.\./",
        r"%2e%2e",
        r"%252e",
        r"/etc/passwd",
        r"\$\(",
        r"`[^`]+`",
        r";\s*(?:id|sh|bash|curl|wget|nc|python|perl|ruby)\\b",
        r"\b(?:curl|wget|nc|ncat|bash -c|sh -c)\b",
    )
    return any(re.search(pattern, text) for pattern in patterns)


def run_generation_loop(
    config: EvolutionConfig,
    seed_evidence: SeedEvidence,
    executor: Callable[[StrategyGene, int], dict[str, Any]],
    *,
    seed_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    preflight_error = validate_config(config, seed_evidence)
    if preflight_error:
        summary = {"stop_reason": "preflight_failed", "error": preflight_error, "attempts": 0, "anomalies": 0}
        (config.artifact_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        return summary

    rng = random.Random(config.seed)
    genome = build_initial_genome(seed_evidence, seed_payload)
    attempts_path = config.artifact_dir / "attempts.jsonl"
    anomalies_path = config.artifact_dir / "anomalies.jsonl"
    promotion_dir = config.artifact_dir / "promotion-tasks"
    promotion_dir.mkdir(exist_ok=True)
    attempts_path.touch(exist_ok=True)
    anomalies_path.touch(exist_ok=True)
    started = time.time()
    total_attempts = 0
    total_anomalies = 0
    stop_reason = "max_generations"

    for generation in range(config.max_generations):
        generation_attempts: list[AttemptRecord] = []
        genes = list(genome.genes)
        rng.shuffle(genes)
        budget = min(config.population_size, config.max_attempts - total_attempts)
        for gene in genes[:budget]:
            if total_attempts >= config.max_attempts:
                stop_reason = "max_attempts"
                break
            if time.time() - started > config.duration_seconds:
                stop_reason = "duration"
                break
            try:
                result = executor(gene, total_attempts)
            except Exception as exc:
                summary = {
                    "stop_reason": "executor_failed",
                    "error": f"{type(exc).__name__}: {exc}",
                    "attempts": total_attempts,
                    "anomalies": total_anomalies,
                }
                (config.artifact_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
                return summary
            record = AttemptRecord(total_attempts, generation, gene, result, 0.0)
            score = score_attempt(record)
            anomaly = classify_anomaly(replace(record, score=score))
            record = replace(record, score=score, anomaly=anomaly.reason if anomaly else None)
            generation_attempts.append(record)
            _write_jsonl(attempts_path, _jsonable_attempt(record))
            if anomaly:
                total_anomalies += 1
                anomaly = replace(anomaly, evidence_path=str(attempts_path))
                _write_jsonl(anomalies_path, asdict(anomaly))
                if anomaly.promotion_ready:
                    promotion = build_promotion_task(anomaly)
                    (promotion_dir / f"{promotion.task_id}.json").write_text(json.dumps(asdict(promotion), indent=2) + "\n")
            total_attempts += 1
            if total_anomalies >= config.anomaly_gate:
                stop_reason = "gate_passed"
        selected = select_parent_genes(genome, generation_attempts, max(1, config.population_size // 2))
        summary = build_generation_summary(generation, generation_attempts, selected)
        (config.artifact_dir / f"generation-{generation:03d}.json").write_text(json.dumps(asdict(summary), indent=2) + "\n")
        if stop_reason in {"gate_passed", "max_attempts", "duration"}:
            break
        mutated = tuple(mutate_gene(gene, config.seed + generation * 10_000 + idx) for idx, gene in enumerate(selected))
        genome = StrategyGenome(generation=generation + 1, genes=tuple(selected) + mutated, evidence=seed_evidence)

    final_summary = {
        "target": config.target_url,
        "seed": config.seed,
        "attempts": total_attempts,
        "anomalies": total_anomalies,
        "duration_seconds": round(time.time() - started, 2),
        "stop_reason": stop_reason,
        "next_step": "Promote anomalies into focused proof probes and blue-team patch tasks.",
    }
    (config.artifact_dir / "summary.json").write_text(json.dumps(final_summary, indent=2) + "\n")
    write_adaptive_report_view(config.artifact_dir)
    return final_summary


def _jsonable_attempt(record: AttemptRecord) -> dict[str, Any]:
    signal_profile = build_signal_profile(record)
    return {
        "attempt": record.attempt,
        "generation": record.generation,
        "gene": asdict(record.gene),
        "result": record.result,
        "score": record.score,
        "anomaly": record.anomaly,
        "signal_profile": signal_profile,
        "classification": classify_attempt(record, record.anomaly, signal_profile),
        "gate_decision": "promote" if record.anomaly and is_reproducible_result(record.result) and signal_profile["real_signal"] else "retain" if record.anomaly else "record",
    }


def dry_run_executor(gene: StrategyGene, attempt: int) -> dict[str, Any]:
    status = 404
    if gene.path in {"/healthz", "/readyz", "/__openclaw/control-ui-config.json"}:
        status = 200
    if gene.path == "/api/diagnostics/prometheus" and gene.header_variant == "none":
        status = 200
    headers = {"Content-Type": "text/plain"}
    body = "dry-run synthetic response"
    if gene.path.startswith("/v1/") and status == 200:
        headers = {"Content-Type": "application/json"}
        body = '{"object":"list","data":[]}'
    return {"status": status, "headers": headers, "elapsed_ms": 10 + attempt, "body": body}


def _status_from_seed_validation(seed_validation_result: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize seed validation evidence for preflight without re-reading files."""

    if not isinstance(seed_validation_result, dict):
        return {
            "status": "blocked_human_review_required",
            "truth_label": "contract_evidence",
            "source_label": "missing_seed_validation_artifact",
            "valid": False,
            "reason": "validated seed artifact is required unless an explicit development fallback is recorded",
        }
    normalized = dict(seed_validation_result)
    if normalized.get("valid") is True:
        status = "passed"
        truth_label = "implemented_evidence"
        source_label = "seed_validation_artifact"
    elif normalized.get("mode") == "built_in_dev_fallback":
        status = "human_review_required"
        truth_label = "intended_contract"
        source_label = "explicit_allow_builtin_seed_flag"
    else:
        status = "blocked_human_review_required"
        truth_label = "contract_evidence"
        source_label = "seed_validation_artifact"
    normalized.update(
        {
            "status": status,
            "truth_label": truth_label,
            "source_label": source_label,
            "missing_fields_are_success": False,
        }
    )
    return normalized


def build_common_preflight_checks(
    config: EvolutionConfig,
    *,
    dry_run: bool,
    docker_image: str,
    seed_validation_result: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build pure, deterministic common preflight evidence for adaptive/evolve.

    This helper intentionally does not perform live network reachability checks
    or Docker probing; callers that execute Docker record that runtime evidence
    separately in the normal campaign logs.
    """

    local_or_private = is_local_or_private_target(config.target_url)
    authorized = local_or_private or config.allow_nonlocal
    artifact_exists = config.artifact_dir.exists() and config.artifact_dir.is_dir()
    seed_status = _status_from_seed_validation(seed_validation_result)
    blocking: list[str] = []
    if not authorized:
        blocking.append("target_not_local_private_and_allow_nonlocal_false")
    if not artifact_exists:
        blocking.append("artifact_root_missing")
    if seed_status["status"] == "blocked_human_review_required":
        blocking.append("seed_validation_not_passed")

    return {
        "authorized_target": {
            "required": True,
            "status": "authorized" if authorized else "human_review_required",
            "truth_label": "implemented_evidence" if authorized else "contract_evidence",
            "source_label": "local_private_guard_or_explicit_allow_nonlocal",
        },
        "local_private_target_guard": {
            "local_or_private_target": local_or_private,
            "allow_nonlocal": config.allow_nonlocal,
            "enforced": not config.allow_nonlocal,
            "status": "pass" if local_or_private else "explicitly_bypassed" if config.allow_nonlocal else "blocked_human_review_required",
            "truth_label": "implemented_evidence",
            "source_label": "hack.chaos_campaign.is_local_or_private_target",
        },
        "artifact_root": {
            "path": str(config.artifact_dir),
            "exists": artifact_exists,
            "status": "ready" if artifact_exists else "blocked_human_review_required",
            "truth_label": "implemented_evidence",
            "source_label": "filesystem_path_check_no_network",
        },
        "docker_requirement_intent": {
            "image": docker_image,
            "required_for_live_run": not dry_run,
            "intent": "not_executed_for_dry_run" if dry_run else "required_before_live_probe_execution",
            "live_check_performed_by_pure_helper": False,
            "status": "contract_only_dry_run" if dry_run else "required_checked_by_cli_before_contract_write",
            "truth_label": "contract_evidence" if dry_run else "implemented_evidence",
            "source_label": "evolve_campaign_cli_options",
        },
        "seed_validation": seed_status,
        "target_reachability": {
            "state": "not_checked_by_pure_helper",
            "live_network_call_performed": False,
            "status": "human_review_required" if not dry_run else "contract_not_evidence",
            "truth_label": "contract_evidence",
            "source_label": "pure_preflight_contract",
            "required_before_interpreting_live_anomalies": True,
        },
        "contract_decision": {
            "status": "blocked_human_review_required" if blocking else "ready_with_recorded_contract_gaps",
            "blocking_reasons": blocking,
            "missing_fields_are_success": False,
        },
    }


def build_preflight_artifact(
    config: EvolutionConfig,
    *,
    dry_run: bool,
    docker_image: str,
    seed_validation_result: dict[str, Any] | None,
) -> dict[str, Any]:
    checks = build_common_preflight_checks(
        config,
        dry_run=dry_run,
        docker_image=docker_image,
        seed_validation_result=seed_validation_result,
    )
    return {
        "schema": "hack.evolve.preflight.v1",
        "target_url": config.target_url,
        "truth_label": "implemented_evidence_and_contract",
        "source_label": "build_common_preflight_checks",
        "common_preflight": checks,
        # Backward-compatible top-level views used by existing report readers.
        "scope": {
            "authorized_target_required": checks["authorized_target"]["required"],
            "local_or_private_target": checks["local_private_target_guard"]["local_or_private_target"],
            "allow_nonlocal": checks["local_private_target_guard"]["allow_nonlocal"],
            "status": "pass" if checks["authorized_target"]["status"] == "authorized" else "human_review_required",
            "truth_label": checks["authorized_target"]["truth_label"],
            "source_label": checks["authorized_target"]["source_label"],
        },
        "artifact_root": checks["artifact_root"],
        "docker": checks["docker_requirement_intent"],
        "seed_validation": checks["seed_validation"],
        "target_reachability": checks["target_reachability"],
        "contract_decision": checks["contract_decision"],
    }


def _lane_id_for_gene(gene: StrategyGene) -> str:
    if gene.source.startswith("validated_seed:"):
        lane = gene.source.split(":", 1)[1]
        if lane in LANE_IDS:
            return lane
    if gene.transport == "websocket-handshake" or gene.path.startswith("/hooks/"):
        return "websocket_control"
    if gene.path.startswith("/sessions/"):
        return "stateful_workflow"
    if gene.path.startswith("/tools/"):
        return "child_process_tool"
    if gene.path.startswith("/v1/chat") or gene.body_variant in {"malformed-json", "json-tool", "json-command-tokens"}:
        return "parser_dependency"
    if gene.path.startswith("/v1/") or "bearer" in gene.header_variant:
        return "auth_session" if "bearer" in gene.header_variant else "api_protocol"
    if ".." in gene.path or "%2e" in gene.path.lower() or "media" in gene.path or gene.path.endswith(".json"):
        return "filesystem_path"
    return "api_protocol"


def _expected_content_type(gene: StrategyGene) -> str:
    if gene.transport == "websocket-handshake":
        return "websocket-upgrade-or-http-error"
    if gene.path.startswith("/v1/") or gene.path.startswith("/tools/") or gene.path.endswith(".json"):
        return "application/json"
    if gene.path == "/api/diagnostics/prometheus":
        return "text/plain"
    if gene.path in {"/healthz", "/readyz"}:
        return "text/plain-or-empty"
    return "route-specific"


def _auth_state_names_for_gene(gene: StrategyGene, lane_id: str) -> tuple[str, ...]:
    names = ["unauthenticated", "stale_invalid_auth"]
    if lane_id in {"api_protocol", "stateful_workflow", "auth_session", "child_process_tool", "parser_dependency", "websocket_control"}:
        names.append("normal_user")
    if gene.method in {"DELETE", "PUT", "PATCH"} or "kill" in gene.path or lane_id == "auth_session":
        names.append("privileged_user")
    return tuple(dict.fromkeys(names))


def build_lane_baseline_contract(
    lane_id: str,
    genes: Iterable[StrategyGene],
    auth_sessions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a lane-specific baseline contract without live requests."""

    lane_genes = sorted(list(genes), key=lambda gene: (gene.path, gene.method, gene.gene_id))
    state_rows = auth_sessions.get("states", []) if isinstance(auth_sessions, dict) else []
    state_status = {str(row.get("name")): str(row.get("status", "unknown")) for row in state_rows if isinstance(row, dict)}
    routes: list[dict[str, Any]] = []
    blocked: list[str] = []
    if not lane_genes:
        blocked.append("no_seeded_route_or_behavior_contract_for_lane")
    for gene in lane_genes:
        auth_states = [
            {
                "name": name,
                "status": state_status.get(name, "blocked_human_review_required"),
                "missing_state_is_success": False,
            }
            for name in _auth_state_names_for_gene(gene, lane_id)
        ]
        if any(state["status"] in {"blocked_human_review_required", "unknown"} for state in auth_states):
            blocked.append(f"auth_session_contract_gap:{gene.path}")
        routes.append(
            {
                "gene_id": gene.gene_id,
                "method": gene.method,
                "path": gene.path,
                "transport": gene.transport,
                "route_behavior": "baseline_contract_not_live_evidence",
                "expected_content_type": _expected_content_type(gene),
                "expected_response_shape": _expected_response_shape(gene),
                "auth_session_states": auth_states,
                "frontend_app_shell_fallback_detection": {
                    "enabled": True,
                    "truth_label": "implemented_evidence",
                    "source_label": "_is_spa_shell_fallback",
                    "markers": ["text/html", "<!doctype html", "<html", "<title>openclaw control</title>"],
                    "classification": "negative_filter_not_api_security_evidence",
                },
                "truth_label": "contract_evidence",
                "source_label": gene.source,
            }
        )
    return {
        "lane_id": lane_id,
        "status": "blocked_human_review_required" if blocked else "ready_with_contract_evidence",
        "blocking_reasons": sorted(set(blocked)),
        "routes": routes,
        "missing_contract_fields_are_success": False,
        "truth_label": "contract_evidence",
        "source_label": "build_lane_baseline_contract",
    }


def build_baseline_artifact(config: EvolutionConfig, genome: StrategyGenome, auth_sessions: dict[str, Any] | None = None) -> dict[str, Any]:
    auth_sessions = auth_sessions or build_auth_sessions_artifact()
    routes = sorted({gene.path for gene in genome.genes})
    genes_by_lane = {lane_id: [gene for gene in genome.genes if _lane_id_for_gene(gene) == lane_id] for lane_id in LANE_IDS}
    lane_contracts = [build_lane_baseline_contract(lane_id, genes_by_lane[lane_id], auth_sessions) for lane_id in LANE_IDS]
    blocking = sorted({reason for lane in lane_contracts for reason in lane["blocking_reasons"]})
    return {
        "schema": "hack.evolve.baseline.v1",
        "target_url": config.target_url,
        "truth_label": "contract_plus_seeded_routes",
        "source_label": "build_baseline_artifact",
        "contract_decision": {
            "status": "blocked_human_review_required" if blocking else "ready_with_contract_evidence",
            "blocking_reasons": blocking,
            "missing_fields_are_success": False,
        },
        "lane_baselines": lane_contracts,
        "route_behavior": [
            {
                "path": path,
                "expected_content_type": _expected_content_type(next(gene for gene in genome.genes if gene.path == path)),
                "expected_response_shape": _expected_response_shape(next(gene for gene in genome.genes if gene.path == path)),
                "auth_session_states": sorted({name for gene in genome.genes if gene.path == path for name in _auth_state_names_for_gene(gene, _lane_id_for_gene(gene))}),
                "frontend_app_shell_fallback_detection": "enabled_negative_filter",
                "missing_route_may_return_app_shell": True,
                "truth_label": "contract_evidence",
            }
            for path in routes
        ],
        "negative_filters": [
            "text/html SPA/app-shell fallback is not API/security proof",
            "HTTP 200 alone is not proof",
            "404/405 and health/readiness responses are normal baseline behavior",
        ],
    }


_AUTH_STATE_ORDER = {
    "unauthenticated": 0,
    "stale_invalid_auth": 1,
    "invalid_or_stale_auth": 1,
    "normal_user": 2,
    "privileged_user": 3,
}
_ALLOWED_TRUTH_LABELS = {"implemented_evidence", "contract_evidence", "intended_contract", "artifact_derived"}


def _fixture_state_name(fixture: dict[str, Any]) -> str:
    raw = str(fixture.get("name") or fixture.get("state") or fixture.get("role") or "seed_fixture").strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
    if normalized in {"invalid_or_stale_auth", "stale", "invalid", "stale_auth", "invalid_auth"}:
        return "stale_invalid_auth"
    if normalized in {"user", "normal", "normal_user"}:
        return "normal_user"
    if normalized in {"admin", "privileged", "privileged_user"}:
        return "privileged_user"
    if normalized in {"anonymous", "anon", "unauthenticated"}:
        return "unauthenticated"
    return normalized or "seed_fixture"


def _redacted_seed_fixture(fixture: dict[str, Any]) -> dict[str, Any]:
    name = _fixture_state_name(fixture)
    truth_label = str(fixture.get("truth_label") or "contract_evidence")
    if truth_label not in _ALLOWED_TRUTH_LABELS:
        truth_label = "contract_evidence"
    material_ref = fixture.get("material_ref") or fixture.get("fixture_ref") or fixture.get("source") or "seed_payload"
    return {
        "name": name,
        "provided": True,
        "status": "fixture_contract_provided",
        "truth_label": truth_label,
        "source_label": "seed_payload.auth_session_fixtures",
        "material_ref": str(material_ref),
        "credential_value_recorded": False,
        "credential_source": "external_fixture_reference_not_generated_by_hack",
    }


def build_auth_sessions_artifact(seed_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    provided_fixtures: list[dict[str, Any]] = []
    if isinstance(seed_payload, dict):
        fixtures = seed_payload.get("auth_session_fixtures")
        if isinstance(fixtures, list):
            provided_fixtures = [_redacted_seed_fixture(item) for item in fixtures if isinstance(item, dict)]
    by_name = {fixture["name"]: fixture for fixture in provided_fixtures}

    states = [
        {
            "name": "unauthenticated",
            "provided": True,
            "status": "implemented_no_credentials",
            "truth_label": "implemented_evidence",
            "source_label": "built_in_negative_control",
            "credential_source": "none",
            "credential_value_recorded": False,
        },
        {
            "name": "stale_invalid_auth",
            "provided": True,
            "status": "implemented_negative_control",
            "truth_label": "implemented_evidence",
            "source_label": "built_in_invalid_auth_negative_control",
            "credential_source": "generated_invalid_marker_not_a_credential_source",
            "credential_value_recorded": False,
        },
    ]
    for name in ("normal_user", "privileged_user"):
        if name in by_name:
            states.append({**by_name[name], "status": "fixture_contract_provided"})
        else:
            states.append(
                {
                    "name": name,
                    "provided": False,
                    "status": "blocked_human_review_required",
                    "truth_label": "contract_evidence",
                    "source_label": "operator_or_seed_fixture_required",
                    "credential_source": "not_provided_by_hack",
                    "credential_value_recorded": False,
                }
            )
    for fixture in provided_fixtures:
        if fixture["name"] not in {"unauthenticated", "stale_invalid_auth", "normal_user", "privileged_user"}:
            states.append(fixture)
    states = sorted(states, key=lambda row: (_AUTH_STATE_ORDER.get(row["name"], 100), row["name"], row.get("material_ref", "")))
    blocking = [row["name"] for row in states if row["status"] == "blocked_human_review_required"]
    return {
        "schema": "hack.evolve.auth-sessions.v1",
        "truth_label": "implemented_evidence_and_contract",
        "source_label": "build_auth_sessions_artifact",
        "states": states,
        "seed_fixtures": sorted(provided_fixtures, key=lambda row: (row["name"], row.get("material_ref", ""))),
        "contract_decision": {
            "status": "human_review_required" if blocking else "ready_with_fixture_contracts",
            "blocking_states": blocking,
            "missing_fields_are_success": False,
        },
        "rule": "auth/session setup is a contract artifact, not a fake credential source; missing credentials never imply success",
    }


def write_adaptive_report_view(campaign_dir: Path) -> Path:
    summary = _read_json_file(campaign_dir / "summary.json")
    attempts = _read_jsonl_file(campaign_dir / "attempts.jsonl")
    anomalies = _read_jsonl_file(campaign_dir / "anomalies.jsonl")
    promotions = sorted((campaign_dir / "promotion-tasks").glob("*.json")) if (campaign_dir / "promotion-tasks").exists() else []
    rejected_false_positives = [
        item for item in attempts
        if item.get("classification") == "false_positive"
        or "html_app_shell_fallback" in item.get("signal_profile", {}).get("negative_filters", [])
    ]
    failed_attempts = [item for item in attempts if not item.get("anomaly")]
    future_seed = {
        "schema": "hack.evolve.next-dogpile-seed.v1",
        "source_campaign": str(campaign_dir),
        "attempts": len(attempts),
        "failed_attempt_classes": sorted({item.get("classification", "unknown") for item in failed_attempts}),
        "retained_anomalies": len([item for item in anomalies if item.get("gate_decision") != "promote"]),
        "promotion_tasks": [str(path) for path in promotions],
        "research_question": "Given retained anomalies, false positives, and failed combinations, which exploit lanes should the next campaign mutate or prune?",
    }
    (campaign_dir / "next-dogpile-seed.json").write_text(json.dumps(future_seed, indent=2, sort_keys=True) + "\n")

    lines = [
        "# /hack Adaptive/Evolve Compiled Report View",
        "",
        "This is an artifact-derived report view, not a first-class exploit ledger.",
        "",
        "## Working Exploits",
        f"- Confirmed promotion tasks: `{len(promotions)}`",
        "- Proof artifacts: see `promotion-tasks/*.json` and Docker logs when present.",
        "",
        "## Affected Surface",
        f"- Target: `{summary.get('target', 'unknown')}`",
        f"- Attempts recorded: `{len(attempts)}`",
        f"- Anomalies recorded: `{len(anomalies)}`",
        "",
        "## Severity / Confidence",
        "- Confidence is artifact-derived from score, signal profile, source lineage, and reproducibility gate decisions.",
        "",
        "## Patch Status",
        "- Default status: `proposed` for promotion tasks; `verified` requires a downstream patch plus /hack Docker proof rerun artifact.",
        "",
        "## Hardening Recommendations",
        "- Tighten auth, route allowlists, response-shape checks, parser limits, and central error handling for promoted route families.",
        "",
        "## Regression Gates",
        "- Add regression tests for every promoted proof objective and every rejected false-positive class.",
        "",
        "## Failed Attempts Summary",
        f"- Non-anomalous attempts retained as negative evidence: `{len(failed_attempts)}`",
        "",
        "## Rejected False Positives",
        f"- False-positive or fallback-filtered attempts: `{len(rejected_false_positives)}`",
        "",
        "## Deferred Human-Review Items",
        f"- Retained anomalies not promotion-ready: `{len([item for item in anomalies if item.get('gate_decision') != 'promote'])}`",
        "",
        "## Future Campaign Seed",
        "- See `next-dogpile-seed.json`.",
        "",
        "## Memory / Project-Knowledge Update",
        "- Store distilled lessons, next seed, and artifact paths. Do not embed raw replay payloads in memory.",
        "",
    ]
    report = campaign_dir / "HACK_EVOLVE_REPORT.md"
    report.write_text("\n".join(lines))
    return report


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_jsonl_file(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def create_evolve_campaign_command() -> Callable[..., None]:
    def evolve_campaign(
        target_url: str = typer.Argument(..., help="Authorized local/private target base URL"),
        output_root: str = typer.Option(ARTIFACT_ROOT, help="Artifact root for evolve-campaign-* directories"),
        duration_minutes: int = typer.Option(10, "--duration-minutes", help="Maximum campaign duration."),
        max_attempts: int = typer.Option(100, "--max-attempts", help="Maximum bounded probe attempts."),
        max_generations: int = typer.Option(4, "--max-generations", help="Maximum evolutionary generations."),
        population_size: int = typer.Option(16, "--population-size", help="Genes attempted per generation."),
        seed: int = typer.Option(1234, "--seed", help="Deterministic campaign seed."),
        docker_image: str = typer.Option("python:3.11-slim", "--docker-image", help="Docker image for live probe execution."),
        last_plan: str | None = typer.Option(None, "--last-plan", help="Prior /hack report or plan artifact."),
        dogpile_report: str | None = typer.Option(None, "--dogpile-report", help="Research synthesis artifact."),
        scanner_findings: str | None = typer.Option(None, "--scanner-findings", help="Scanner findings artifact."),
        seed_json: Path | None = typer.Option(None, "--seed-json", help="Validated Dogpile seed research JSON artifact."),
        seed_validation: Path | None = typer.Option(None, "--seed-validation", help="validate-seed result JSON bound to --seed-json."),
        validation_max_age_seconds: int = typer.Option(DEFAULT_VALIDATION_MAX_AGE_SECONDS, "--validation-max-age-seconds", help="Maximum accepted seed validation age."),
        allow_builtin_seed: bool = typer.Option(False, "--allow-built-in-seed", help="Developer fallback; bypass validated seed artifact."),
        allow_unverified_seed_paths: bool = typer.Option(False, "--allow-unverified-seed-paths", help="Accept validation results not produced with --verify-paths."),
        allow_nonlocal: bool = typer.Option(False, "--allow-nonlocal", help="Allow explicitly authorized nonlocal targets."),
        dry_run: bool = typer.Option(False, "--dry-run", help="Do not send network probes; write deterministic synthetic artifacts."),
    ) -> None:
        campaign_dir = run_evolutionary_campaign(
            target_url=target_url,
            output_root=Path(output_root),
            duration_minutes=duration_minutes,
            max_attempts=max_attempts,
            max_generations=max_generations,
            population_size=population_size,
            seed=seed,
            docker_image=docker_image,
            last_plan=Path(last_plan) if last_plan else None,
            dogpile_report=Path(dogpile_report) if dogpile_report else None,
            scanner_findings=Path(scanner_findings) if scanner_findings else None,
            seed_json=seed_json,
            seed_validation=seed_validation,
            validation_max_age_seconds=validation_max_age_seconds,
            allow_builtin_seed=allow_builtin_seed,
            require_verified_seed_paths=not allow_unverified_seed_paths,
            allow_nonlocal=allow_nonlocal,
            dry_run=dry_run,
        )
        console.print(f"[green]Evolutionary campaign artifacts:[/green] {campaign_dir}")

    return evolve_campaign


def run_evolutionary_campaign(
    *,
    target_url: str,
    output_root: Path,
    duration_minutes: int,
    max_attempts: int,
    max_generations: int,
    population_size: int,
    seed: int,
    docker_image: str,
    last_plan: Path | None = None,
    dogpile_report: Path | None = None,
    scanner_findings: Path | None = None,
    seed_json: Path | None = None,
    seed_validation: Path | None = None,
    validation_max_age_seconds: int = DEFAULT_VALIDATION_MAX_AGE_SECONDS,
    allow_builtin_seed: bool = False,
    require_verified_seed_paths: bool = True,
    allow_nonlocal: bool = False,
    dry_run: bool = False,
) -> Path:
    if not dry_run and not shutil.which("docker"):
        raise RuntimeError("Docker is required for live /hack evolve-campaign")
    if not allow_nonlocal and not is_local_or_private_target(target_url):
        raise ValueError("evolve-campaign targets loopback/private hosts by default; pass --allow-nonlocal only for authorized nonlocal systems")
    campaign_id = "evolve-campaign-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + safe_slug(target_url)
    campaign_dir = output_root / campaign_id
    campaign_dir.mkdir(parents=True, exist_ok=True)
    seed_payload: dict[str, Any] | None = None
    seed_validation_result: dict[str, Any] | None = None
    if allow_builtin_seed:
        seed_validation_result = {"mode": "built_in_dev_fallback", "validation_required": False}
    elif seed_json is None or seed_validation is None:
        errors = ["evolve-campaign requires --seed-json and --seed-validation unless --allow-built-in-seed is explicit"]
        _write_evolve_preflight_failure(campaign_dir, target_url, errors)
        raise ValueError("; ".join(errors))
    else:
        seed_payload, seed_errors, seed_validation_result = load_validated_seed(
            seed_json,
            seed_validation,
            target_url=target_url,
            max_age_seconds=validation_max_age_seconds,
            require_verified_paths=require_verified_seed_paths,
        )
        if seed_errors:
            _write_evolve_preflight_failure(campaign_dir, target_url, seed_errors, validation_result=seed_validation_result)
            raise ValueError("; ".join(seed_errors))
    evidence = SeedEvidence(
        last_plan_summary=summarize_seed_file(last_plan),
        dogpile_summary=summarize_seed_file(dogpile_report),
        scanner_findings_summary=summarize_seed_file(scanner_findings),
    )
    config = EvolutionConfig(
        target_url=target_url,
        artifact_dir=campaign_dir,
        max_attempts=max_attempts,
        max_generations=max_generations,
        population_size=population_size,
        seed=seed,
        duration_seconds=duration_minutes * 60,
        allow_nonlocal=allow_nonlocal,
    )
    _write_campaign_contract(
        campaign_dir,
        config,
        evidence,
        dry_run=dry_run,
        docker_image=docker_image,
        seed_payload=seed_payload,
        seed_validation_result=seed_validation_result,
    )
    if dry_run:
        run_generation_loop(config, evidence, dry_run_executor, seed_payload=seed_payload)
        return campaign_dir
    script_path = campaign_dir / "evolutionary_probe.py"
    script_path.write_text(build_evolutionary_probe_script())
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network=host",
            "-v",
            f"{campaign_dir}:/campaign:rw",
            "-e",
            f"HACK_EVOLVE_TARGET_URL={target_url}",
            "-e",
            f"HACK_EVOLVE_DURATION_SECONDS={duration_minutes * 60}",
            "-e",
            f"HACK_EVOLVE_MAX_ATTEMPTS={max_attempts}",
            "-e",
            f"HACK_EVOLVE_MAX_GENERATIONS={max_generations}",
            "-e",
            f"HACK_EVOLVE_POPULATION_SIZE={population_size}",
            "-e",
            f"HACK_EVOLVE_SEED={seed}",
            docker_image,
            "python",
            "/campaign/evolutionary_probe.py",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    (campaign_dir / "evolution-docker.stdout.log").write_text(result.stdout)
    (campaign_dir / "evolution-docker.stderr.log").write_text(result.stderr)
    (campaign_dir / "evolution-docker.exit-code").write_text(f"{result.returncode}\n")
    if result.returncode not in {0, 2}:
        raise RuntimeError(f"evolutionary campaign failed; see {campaign_dir}")
    write_adaptive_report_view(campaign_dir)
    return campaign_dir


def _write_evolve_preflight_failure(
    campaign_dir: Path,
    target_url: str,
    errors: list[str],
    *,
    validation_result: dict[str, Any] | None = None,
) -> None:
    payload = {
        "target": target_url,
        "stop_reason": "preflight_failed",
        "errors": errors,
        "attempts": 0,
        "anomalies": 0,
        "validation_result": validation_result,
    }
    (campaign_dir / "seed-validation-preflight.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    (campaign_dir / "summary.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _write_campaign_contract(
    campaign_dir: Path,
    config: EvolutionConfig,
    evidence: SeedEvidence,
    *,
    dry_run: bool,
    docker_image: str,
    seed_payload: dict[str, Any] | None,
    seed_validation_result: dict[str, Any] | None,
) -> None:
    genome = build_initial_genome(evidence, seed_payload)
    (campaign_dir / "preflight.json").write_text(
        json.dumps(
            build_preflight_artifact(
                config,
                dry_run=dry_run,
                docker_image=docker_image,
                seed_validation_result=seed_validation_result,
            ),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    (campaign_dir / "baseline.json").write_text(
        json.dumps(build_baseline_artifact(config, genome), indent=2, sort_keys=True) + "\n"
    )
    (campaign_dir / "auth-sessions.json").write_text(
        json.dumps(build_auth_sessions_artifact(seed_payload), indent=2, sort_keys=True) + "\n"
    )
    (campaign_dir / "strategies.seed.json").write_text(
        json.dumps(
            {
                "target_url": config.target_url,
                "seed": config.seed,
                "max_attempts": config.max_attempts,
                "max_generations": config.max_generations,
                "population_size": config.population_size,
                "docker_image": docker_image,
                "dry_run": dry_run,
                "seed_source": "validated_seed" if seed_payload else "built_in_dev_fallback",
                "seed_validation": seed_validation_result,
                "safety_boundary": "Docker-contained probes against authorized local/private targets only",
                "lifecycle_stage": "generation_zero_broad_exploration_then_feedback_guided_evolution",
                "mode_contract": "evolve-campaign owns chaos-style broad exploration, scoring, mutation, reproducibility gating, promotion, and Dogpile reseeding",
                "compatibility_entrypoint": "chaos-campaign remains a hidden/backward-compatible broad-exploration entrypoint, not a third top-level /hack mode",
                "research_insights": [
                    "Control-flow distance maps to route sensitivity and target proximity.",
                    "Value-flow influence maps to payloads that affect tools, sessions, paths, providers, and auth decisions.",
                    "Slice coverage maps to focused route families instead of blind whole-service scanning.",
                    "Selective instrumentation maps to cheap observable feedback: status, timing, resets, disclosure tokens, and websocket upgrades.",
                ],
                "genes": [asdict(gene) for gene in genome.genes],
                "evidence": asdict(evidence),
            },
            indent=2,
        )
        + "\n"
    )
    (campaign_dir / "loop-contract.json").write_text(
        json.dumps(
            {
                "loop": "preflight -> baseline/auth fixtures -> genome -> attempt -> score -> real-signal gate -> reproducibility gate -> select -> mutate -> promote/retain -> report view -> next Dogpile seed",
                "top_level_hack_mode": "evolve-campaign",
                "generation_zero": "chaos-style broad uncommon-combination exploration is the first population inside evolve-campaign",
                "safety": "authorized hardening only; raw probe evidence stays in artifacts",
                "artifacts": [
                    "preflight.json",
                    "baseline.json",
                    "auth-sessions.json",
                    "strategies.seed.json",
                    "attempts.jsonl",
                    "anomalies.jsonl",
                    "generation-*.json",
                    "promotion-tasks/",
                    "summary.json",
                    "HACK_EVOLVE_REPORT.md",
                    "next-dogpile-seed.json",
                ],
            },
            indent=2,
        )
        + "\n"
    )


def build_evolutionary_probe_script() -> str:
    return textwrap.dedent(
        r'''
        from __future__ import annotations
        import json, os, random, socket, time, urllib.error, urllib.parse, urllib.request
        from pathlib import Path

        TARGET = os.environ["HACK_EVOLVE_TARGET_URL"].rstrip("/")
        MAX_ATTEMPTS = int(os.environ["HACK_EVOLVE_MAX_ATTEMPTS"])
        MAX_GENERATIONS = int(os.environ["HACK_EVOLVE_MAX_GENERATIONS"])
        POPULATION_SIZE = int(os.environ["HACK_EVOLVE_POPULATION_SIZE"])
        DURATION_SECONDS = int(os.environ["HACK_EVOLVE_DURATION_SECONDS"])
        SEED = int(os.environ["HACK_EVOLVE_SEED"])
        OUT = Path("/campaign")
        RNG = random.Random(SEED)
        SEED_DATA = json.loads((OUT / "strategies.seed.json").read_text())
        GENES = SEED_DATA["genes"]

        def mutate_path(path, mutation):
            if mutation == "double-slash": return "//" + path.lstrip("/")
            if mutation == "encoded-slash": return path.replace("/", "%2f", 1) if path != "/" else "/%2f"
            if mutation == "double-encoded-dotdot": return "/%252e%252e/%252e%252e" + path
            if mutation == "dotdot": return "/safe/../.." + path
            if mutation == "case-flip": return "".join(ch.upper() if idx % 2 else ch.lower() for idx, ch in enumerate(path))
            if mutation == "query-cache-bust": return path + ("&" if "?" in path else "?") + f"cb={RNG.randrange(1_000_000)}"
            if mutation == "query-token": return path + ("&" if "?" in path else "?") + "token=invalid"
            return path

        def headers_for(variant, attempt):
            headers = {}
            if variant == "invalid-bearer": headers["Authorization"] = f"Bearer evolve-{attempt}"
            elif variant == "query-token": headers["X-OpenClaw-Token"] = f"evolve-{attempt}"
            elif variant == "spoof-loopback-forwarded-for":
                headers["X-Forwarded-For"] = "127.0.0.1"; headers["X-Real-IP"] = "127.0.0.1"
            elif variant == "spoof-private-forwarded-for": headers["X-Forwarded-For"] = "10.0.0.9"
            elif variant == "json-content-type": headers["Content-Type"] = "application/json"
            elif variant == "oversized-header": headers["X-Evolve"] = "A" * 8192
            elif variant == "evil-origin": headers["Origin"] = "http://evil.invalid"
            elif variant == "null-origin": headers["Origin"] = "null"
            return headers

        def body_for(variant):
            if variant == "json-empty": return b"{}"
            if variant == "json-tool": return json.dumps({"tool":"gateway.status","arguments":{}}).encode()
            if variant == "json-path-traversal": return json.dumps({"path":"../../etc/passwd","sessionId":"../main"}).encode()
            if variant == "json-command-tokens": return json.dumps({"command":"id; uname -a","args":[";id","$(id)"]}).encode()
            if variant == "oversized-json": return json.dumps({"data":"A"*250000}).encode()
            if variant == "malformed-json": return b'{"unterminated":'
            return None

        def http_probe(gene, attempt):
            path = mutate_path(gene["path"], gene["mutation"])
            body = body_for(gene["body_variant"])
            headers = headers_for(gene["header_variant"], attempt)
            if body is not None and "Content-Type" not in headers: headers["Content-Type"] = "application/json"
            req = urllib.request.Request(TARGET + path, data=body, method=gene["method"], headers=headers)
            started = time.time()
            try:
                with urllib.request.urlopen(req, timeout=4) as res:
                    raw = res.read(2048)
                    return {"status": res.status, "headers": dict(res.headers), "body": raw.decode("utf-8", "replace")[:300], "elapsed_ms": round((time.time()-started)*1000, 2)}
            except urllib.error.HTTPError as exc:
                raw = exc.read(2048)
                return {"status": exc.code, "headers": dict(exc.headers), "body": raw.decode("utf-8", "replace")[:300], "elapsed_ms": round((time.time()-started)*1000, 2)}
            except Exception as exc:
                return {"error": type(exc).__name__, "message": str(exc)[:300], "elapsed_ms": round((time.time()-started)*1000, 2)}

        def websocket_probe(gene, attempt):
            url = urllib.parse.urlparse(TARGET)
            host = url.hostname or "127.0.0.1"; port = url.port or (443 if url.scheme == "https" else 80)
            path = mutate_path(gene["path"], gene["mutation"])
            extra = headers_for(gene["header_variant"], attempt)
            started = time.time()
            try:
                with socket.create_connection((host, port), timeout=4) as sock:
                    sock.settimeout(4)
                    lines = [f"GET {path} HTTP/1.1", f"Host: {host}:{port}", "Upgrade: websocket", "Connection: Upgrade", "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==", "Sec-WebSocket-Version: 13"]
                    lines.extend(f"{k}: {v}" for k, v in extra.items())
                    sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("ascii", "ignore"))
                    raw = sock.recv(2048)
                text = raw.decode("utf-8", "replace")
                return {"status_line": text.splitlines()[0] if text else "", "body": text[:300], "elapsed_ms": round((time.time()-started)*1000, 2)}
            except Exception as exc:
                return {"error": type(exc).__name__, "message": str(exc)[:300], "elapsed_ms": round((time.time()-started)*1000, 2)}

        def content_type(result):
            headers = result.get("headers")
            if not isinstance(headers, dict): return ""
            for key, value in headers.items():
                if str(key).lower() == "content-type": return str(value).lower()
            return ""

        def is_spa_shell_fallback(result):
            ctype = content_type(result)
            body = str(result.get("body", "")).lstrip().lower()
            if "text/html" not in ctype: return False
            return body.startswith("<!doctype html") or body.startswith("<html") or "<title>openclaw control</title>" in body

        def is_unexpected_success(gene, result):
            status = result.get("status")
            if not isinstance(status, int) or status != 200: return False
            if gene["path"] in ["/", "/healthz", "/readyz"]: return False
            return not is_spa_shell_fallback(result)

        def score(gene, result):
            s = 0.0; status = result.get("status"); line = result.get("status_line", ""); body = str(result.get("body", "")).lower()
            if isinstance(status, int) and status >= 500: s += 10
            if is_unexpected_success(gene, result): s += 7
            if "101" in line: s += 9
            if result.get("error") in ["ConnectionResetError", "RemoteDisconnected", "ConnectionAbortedError"]: s += 6
            if result.get("elapsed_ms", 0) > 3000: s += 3
            if any(t in body for t in ["secret", "token", "traceback", "exception", "stack"]): s += 5
            if gene.get("source") in ["dogpile", "runtime_anomaly"]: s += 0.5
            return round(s, 3)

        def anomaly_reason(gene, result):
            status = result.get("status"); line = result.get("status_line", "")
            if isinstance(status, int) and status >= 500: return "server-error"
            if is_unexpected_success(gene, result): return "unexpected-unauthenticated-200"
            if "101" in line: return "unauthenticated-websocket-upgrade"
            if result.get("error") in ["ConnectionResetError", "RemoteDisconnected", "ConnectionAbortedError"]: return "connection-reset"
            if result.get("elapsed_ms", 0) > 3000: return "slow-response"
            return None

        def mutate_gene(gene, generation, idx):
            child = dict(gene)
            child["gene_id"] = f"{gene['gene_id']}.m{generation:02d}{idx:03d}"
            child["source"] = "runtime_anomaly"
            axis = RNG.choice(["method", "header_variant", "body_variant", "mutation"])
            choices = {
                "method": ["GET","HEAD","POST","PUT","PATCH","DELETE","OPTIONS"],
                "header_variant": ["none","invalid-bearer","query-token","spoof-loopback-forwarded-for","spoof-private-forwarded-for","json-content-type","oversized-header","evil-origin","null-origin"],
                "body_variant": ["empty","json-empty","json-tool","json-path-traversal","json-command-tokens","oversized-json","malformed-json"],
                "mutation": ["plain","double-slash","encoded-slash","dotdot","case-flip","query-cache-bust","query-token","double-encoded-dotdot"],
            }
            child[axis] = RNG.choice(choices[axis])
            child["lineage"] = list(gene.get("lineage", [])) + [gene["gene_id"]]
            return child

        attempts_path = OUT / "attempts.jsonl"; anomalies_path = OUT / "anomalies.jsonl"; promo = OUT / "promotion-tasks"; promo.mkdir(exist_ok=True)
        started = time.time(); attempts = 0; anomalies = 0; population = list(GENES); stop = "max_generations"
        for generation in range(MAX_GENERATIONS):
            RNG.shuffle(population); generation_records = []
            for gene in population[:POPULATION_SIZE]:
                if attempts >= MAX_ATTEMPTS: stop = "max_attempts"; break
                if time.time() - started > DURATION_SECONDS: stop = "duration"; break
                result = websocket_probe(gene, attempts) if gene["transport"] == "websocket-handshake" else http_probe(gene, attempts)
                sc = score(gene, result); reason = anomaly_reason(gene, result)
                record = {"attempt": attempts, "generation": generation, "gene": gene, "result": result, "score": sc, "anomaly": reason}
                attempts_path.open("a").write(json.dumps(record, sort_keys=True) + "\n")
                generation_records.append(record)
                if reason:
                    anomalies += 1
                    anomalies_path.open("a").write(json.dumps(record, sort_keys=True) + "\n")
                    task = {
                        "task_id": f"promote-{gene['gene_id']}-{attempts}",
                        "anomaly_evidence_path": str(attempts_path),
                        "objective": f"Reproduce and minimize `{reason}` from evolutionary campaign artifacts.",
                        "blue_team_patch_hypothesis": "Add or tighten central auth/rate/normalization/error-handling gate for the affected route family.",
                        "suggested_runner": "code-runner",
                        "patch_status": "proposed",
                        "verification_contract": {
                            "implementation_path": "/plan -> /review-plan -> /orchestrate -> /code-runner",
                            "hack_role": "rerun Docker proof and record verification evidence; do not apply patches directly",
                            "required_patch_status_values": ["proposed", "implementation_requested", "implemented_unverified", "verified", "deferred", "rejected"],
                            "verified_requires": ["patch_applied_by_downstream", "tests_run", "hack_docker_proof_rerun_artifact"],
                        },
                    }
                    (promo / f"{task['task_id']}.json").write_text(json.dumps(task, indent=2) + "\n")
                    stop = "gate_passed"
                attempts += 1
            selected = sorted(generation_records, key=lambda r: (-r["score"], r["attempt"]))[:max(1, POPULATION_SIZE // 2)]
            (OUT / f"generation-{generation:03d}.json").write_text(json.dumps({"generation": generation, "attempts": len(generation_records), "anomalies": sum(1 for r in generation_records if r["anomaly"]), "best_score": max([r["score"] for r in generation_records] or [0]), "selected_gene_ids": [r["gene"]["gene_id"] for r in selected]}, indent=2) + "\n")
            if stop in ["gate_passed", "max_attempts", "duration"]: break
            population = [r["gene"] for r in selected] + [mutate_gene(r["gene"], generation, i) for i, r in enumerate(selected)]
        summary = {"target": TARGET, "seed": SEED, "attempts": attempts, "anomalies": anomalies, "duration_seconds": round(time.time()-started, 2), "stop_reason": stop, "next_step": "Promote anomalies into focused proof probes and blue-team patch tasks."}
        (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps(summary, indent=2))
        raise SystemExit(2 if anomalies else 0)
        '''
    ).lstrip()


__all__ = [
    "AnomalyRecord",
    "AttemptRecord",
    "EvolutionConfig",
    "GenerationSummary",
    "PromotionTask",
    "SeedEvidence",
    "StrategyGene",
    "StrategyGenome",
    "baseline_genes",
    "build_evolutionary_probe_script",
    "build_generation_summary",
    "build_initial_genome",
    "build_promotion_task",
    "classify_anomaly",
    "create_evolve_campaign_command",
    "create_validate_seed_command",
    "dry_run_executor",
    "genes_from_seed_payload",
    "load_validated_seed",
    "mutate_gene",
    "run_evolutionary_campaign",
    "run_generation_loop",
    "score_attempt",
    "select_parent_genes",
    "seed_payload_sha256",
    "seed_target_url",
    "validate_seed_file",
    "validate_seed_research_payload",
]
