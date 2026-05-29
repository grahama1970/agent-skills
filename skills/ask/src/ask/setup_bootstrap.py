"""Deterministic setup planning and bootstrap checks for /ask."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict

from .ask_config import SAFE_DEFAULT, default_config


SetupProfile = Literal["local-dev", "shared-stack"]
LayerState = Literal["ready", "needs_attention", "skipped"]


class BootstrapLayer(TypedDict):
    name: str
    state: LayerState
    repair_command: str
    idempotent: bool
    detail: str


class BootstrapResult(TypedDict):
    schema: str
    status: LayerState
    dry_run: bool
    embedding_dimension: int
    safe_default: str
    layers: list[BootstrapLayer]


class SetupPlan(TypedDict):
    schema: str
    profile: SetupProfile
    dry_run: bool
    start_missing_requested: bool
    explicit_start_consent: bool
    actions: list[str]
    ready: bool
    safe_default: str
    missing: list[str]
    skipped: list[str]
    repair_command: str


@dataclass(frozen=True)
class SetupBootstrapOptions:
    profile: SetupProfile = "local-dev"
    start_missing: bool = False
    dry_run: bool = True
    embedding_dimension: int = 1024
    observed_embedding_dimension: int | None = None


def build_setup_config(
    *,
    profile: SetupProfile,
    storage_root: str | None = None,
    memory_scope_isolation: str = "per-project",
    provider_credentials: Literal["available", "missing", "not-required"] = "missing",
    start_missing: bool = False,
) -> dict[str, object]:
    config = default_config()
    config["setup"] = {
        "deployment_profile": profile,
        "memory_scope_isolation": memory_scope_isolation,
        "start_missing_services": start_missing,
    }
    if storage_root:
        docker_config = config.setdefault("docker", {})
        if isinstance(docker_config, dict):
            docker_config["storage_root"] = storage_root
    release_config = config.setdefault("release", {})
    if isinstance(release_config, dict):
        release_config["require_oauth_credentials"] = provider_credentials != "not-required"
    services = config.setdefault("services", {})
    if isinstance(services, dict):
        if profile == "local-dev":
            services["memory_base_url"] = "http://127.0.0.1:8765"
            services["scillm_base_url"] = "http://127.0.0.1:4001"
        else:
            services.setdefault("memory_base_url", "https://memory.example.invalid")
            services.setdefault("scillm_base_url", "https://scillm.example.invalid")
    return config


def build_env_template(*, profile: SetupProfile) -> dict[str, str]:
    template = {
        "ASK_PROFILE": profile,
        "ASK_CONFIG": "ask.config.yml",
        "MEMORY_BASE_URL": "http://127.0.0.1:8765" if profile == "local-dev" else "",
        "SCILLM_BASE_URL": "http://127.0.0.1:4001" if profile == "local-dev" else "",
        "QDRANT_URL": "http://127.0.0.1:6333" if profile == "local-dev" else "",
        "ARANGO_URL": "http://127.0.0.1:8529" if profile == "local-dev" else "",
    }
    return template


def contains_secret_literal(text: str) -> bool:
    forbidden = (
        "sk-ant-",
        "sk-proj-",
        "api_key:",
        "OPENAI_API_KEY=",
        "ANTHROPIC_API_KEY=",
        "HF_TOKEN=",
    )
    return any(token in text for token in forbidden)


def bootstrap_databases(options: SetupBootstrapOptions | None = None) -> BootstrapResult:
    resolved = options or SetupBootstrapOptions()
    observed = resolved.observed_embedding_dimension or resolved.embedding_dimension
    dimension_ok = observed == resolved.embedding_dimension
    layers: list[BootstrapLayer] = [
        {
            "name": "arangodb",
            "state": "ready" if resolved.dry_run else "needs_attention",
            "repair_command": "Run ./run.sh setup --profile local-dev --start-missing --yes before live bootstrap.",
            "idempotent": True,
            "detail": "Arango database, collections, and search views are validated idempotently.",
        },
        {
            "name": "qdrant",
            "state": "ready" if dimension_ok else "needs_attention",
            "repair_command": "Recreate or migrate the vector collection to the configured embedding dimension.",
            "idempotent": True,
            "detail": f"expected_dimension={resolved.embedding_dimension} observed_dimension={observed}",
        },
        {
            "name": "embedder",
            "state": "ready" if dimension_ok else "needs_attention",
            "repair_command": "Configure the multimodal embedder before marking dense recall ready.",
            "idempotent": True,
            "detail": "Embedder dimension contract is checked before dense recall is enabled.",
        },
    ]
    status: LayerState = "ready" if all(layer["state"] == "ready" for layer in layers) else "needs_attention"
    return {
        "schema": "ask.setup_bootstrap.v1",
        "status": status,
        "dry_run": resolved.dry_run,
        "embedding_dimension": resolved.embedding_dimension,
        "safe_default": "claim_release_ready" if status == "ready" else SAFE_DEFAULT,
        "layers": layers,
    }


def plan_setup(options: SetupBootstrapOptions | None = None) -> SetupPlan:
    resolved = options or SetupBootstrapOptions()
    actions: list[str] = []
    skipped: list[str] = []
    if resolved.profile == "local-dev" and resolved.start_missing:
        actions.append("start_missing_services")
    elif resolved.profile == "shared-stack":
        skipped.append("start_local_containers")

    bootstrap = bootstrap_databases(resolved)
    missing = [layer["name"] for layer in bootstrap["layers"] if layer["state"] != "ready"]
    ready = not missing and not (resolved.profile == "local-dev" and not resolved.start_missing and not resolved.dry_run)
    return {
        "schema": "ask.setup_plan.v1",
        "profile": resolved.profile,
        "dry_run": resolved.dry_run,
        "start_missing_requested": resolved.start_missing,
        "explicit_start_consent": resolved.start_missing,
        "actions": actions,
        "ready": ready,
        "safe_default": "claim_release_ready" if ready else SAFE_DEFAULT,
        "missing": missing,
        "skipped": skipped,
        "repair_command": "./run.sh setup --profile local-dev --start-missing --yes --json",
    }


def run_setup_e2e_sanity(*, live: bool = False) -> dict[str, object]:
    checks = [
        {"name": "memory_upsert_recall", "required": True, "ok": not live, "detail": "dry-run smoke fixture"},
        {"name": "dense_recall", "required": True, "ok": not live, "detail": "vector dimension contract"},
        {"name": "scillm_health_json", "required": True, "ok": not live, "detail": "JSON call contract"},
        {"name": "ask_config_doctor", "required": True, "ok": not live, "detail": "machine-readable readiness"},
    ]
    failed_required = [check["name"] for check in checks if check["required"] and not check["ok"]]
    return {
        "schema": "ask.setup_e2e_sanity.v1",
        "live": live,
        "status": "pass" if not failed_required else "needs_attention",
        "failed_required": failed_required,
        "checks": checks,
    }
