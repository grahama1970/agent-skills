"""Shared configuration for the ask skill."""

from __future__ import annotations
from .env import load_dotenv_once

load_dotenv_once()


import copy
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import yaml

SKILL_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = SKILL_ROOT.parent
DEFAULT_CONFIG_PATH = Path(os.environ.get("ASK_CONFIG", SKILL_ROOT / "ask.config.yml"))
CONFIG_SCHEMA = "ask.config.v1"

DEFAULT_CONFIG: dict[str, Any] = {
    "schema": CONFIG_SCHEMA,
    "profile": "release",
    "services": {
        "memory_run": "../memory/run.sh",
        "scillm_run": "../scillm/run.sh",
        "dogpile_run": "../dogpile/run.sh",
        "interview_run": "../interview/run.sh",
        "subagent_runner": "../subagent-runner/run.sh",
        "scillm_base_url": "http://127.0.0.1:4001",
    },
    "storage": {
        "run_output_dir": ".ask_artifacts/runs",
        "subagent_output_dir": "/tmp/ask-oracle-subagents",
    },
    "docker": {
        "compose_project": "ask-release",
        "network_mode": "host",
        "memory_repo": "../../../memory",
        "scillm_repo": "../../../scillm",
        "storage_root": "/mnt/storage12tb",
    },
    "release": {
        "require_config_file": True,
        "require_live_services": True,
        "require_oauth_credentials": True,
        "require_expensive_routes": True,
        "required_credentials": [
            "~/.codex/auth.json",
            "~/.claude/.credentials.json",
            "~/.gemini",
        ],
    },
}
READINESS_SCHEMA = "ask.setup_readiness.v1"
CONFIG_DOCTOR_SCHEMA = "ask.config_doctor.v1"
SAFE_DEFAULT = "do_not_claim_release_ready"
REPAIR_COMMANDS: dict[str, str] = {
    "docker": "Install Docker Engine/Desktop and ensure the docker CLI is on PATH.",
    "arangodb": "Start/bootstrap ArangoDB using the memory service setup instructions; do not start it from config doctor.",
    "qdrant": "Start/bootstrap Qdrant or the configured vector store using the memory service setup instructions.",
    "embedder": "Configure and verify the embedding provider/model required by memory before release readiness.",
    "memory": "Install/configure the memory skill, then run its bootstrap or doctor command outside config doctor.",
    "scillm": "Install/configure the scillm skill and start its service outside config doctor.",
    "provider_auth": "Authenticate required model providers (for example Codex/Claude/Gemini), then re-run config doctor.",
    "ask_config": "Run ./run.sh config init, review ask.config.yml, then re-run ./run.sh config doctor --json.",
}

DEFAULT_ORACLE_MODEL = os.environ.get("ASK_ORACLE_MODEL", "gpt-5.5")
DEFAULT_ORACLE_REASONING = os.environ.get("ASK_ORACLE_REASONING", "high")
DEFAULT_ORACLE_TIMEOUT = float(os.environ.get("ASK_ORACLE_TIMEOUT", "300"))
DEFAULT_ORACLE_IDLE_TIMEOUT = float(os.environ.get("ASK_ORACLE_IDLE_TIMEOUT", "300"))
DEFAULT_ORACLE_HEARTBEAT_INTERVAL = float(os.environ.get("ASK_ORACLE_HEARTBEAT_INTERVAL", "30"))
DEFAULT_ORACLE_BACKEND = os.environ.get("ASK_ORACLE_BACKEND", "auto")
SCILLM_BASE_URL = os.environ.get("SCILLM_BASE_URL", "http://localhost:4001")
SCILLM_API_KEY = os.environ.get("SCILLM_API_KEY", "sk-dev-proxy-123")
SUBAGENT_RUNNER = os.environ.get(
    "ASK_SUBAGENT_RUNNER",
    str(SKILLS_DIR / "subagent-runner" / "run.sh"),
)
SUBAGENT_OUTPUT_DIR = os.environ.get(
    "ASK_SUBAGENT_OUTPUT_DIR",
    str(Path(tempfile.gettempdir()) / "ask-oracle-subagents"),
)
MEMORY_RUN = os.environ.get(
    "ASK_MEMORY_RUN",
    str(SKILLS_DIR / "memory" / "run.sh"),
)
SCILLM_RUN = os.environ.get(
    "ASK_SCILLM_RUN",
    str(SKILLS_DIR / "scillm" / "run.sh"),
)
DOGPILE_RUN = os.environ.get(
    "ASK_DOGPILE_RUN",
    str(SKILLS_DIR / "dogpile" / "run.sh"),
)
MONITOR_PERSONAS_RUN = os.environ.get(
    "ASK_MONITOR_PERSONAS_RUN",
    str(SKILLS_DIR / "monitor-personas" / "run.sh"),
)
SURF_RUN = os.environ.get(
    "ASK_SURF_RUN",
    str(SKILLS_DIR / "surf" / "run.sh"),
)
WEBGPT_DEFAULT_TIMEOUT = float(os.environ.get("ASK_WEBGPT_TIMEOUT", "900"))
WEBGPT_STABLE_POLLS = int(os.environ.get("ASK_WEBGPT_STABLE_POLLS", "3"))

CURSOR_BROWSER_DEFAULT_TIMEOUT = float(os.environ.get("ASK_CURSOR_BROWSER_TIMEOUT", "900"))
CURSOR_BROWSER_STABLE_POLLS = int(os.environ.get("ASK_CURSOR_BROWSER_STABLE_POLLS", "3"))

GEMINI_DEFAULT_TIMEOUT = float(os.environ.get("ASK_GEMINI_TIMEOUT", "300"))
GEMINI_STABLE_POLLS = int(os.environ.get("ASK_GEMINI_STABLE_POLLS", "3"))

KIMI_DEFAULT_TIMEOUT = float(os.environ.get("ASK_KIMI_TIMEOUT", "300"))
KIMI_STABLE_POLLS = int(os.environ.get("ASK_KIMI_STABLE_POLLS", "3"))

PERPLEXITY_DEFAULT_TIMEOUT = float(os.environ.get("ASK_PERPLEXITY_TIMEOUT", "120"))
ORACLE_BACKENDS = frozenset({
    "auto", "scillm", "subagent-runner", "webgpt", "webgemini", "webkimi", "webperplexity", "cursor-browser",
})


def default_config() -> dict[str, Any]:
    return copy.deepcopy(DEFAULT_CONFIG)


def config_path(path: str | Path | None = None) -> Path:
    return Path(path).expanduser() if path else DEFAULT_CONFIG_PATH.expanduser()


def resolve_config_path(value: str | None) -> Path | None:
    if not value:
        return None
    expanded = Path(value).expanduser()
    if expanded.is_absolute():
        return expanded
    return (SKILL_ROOT / expanded).resolve()


def load_config(path: str | Path | None = None) -> tuple[dict[str, Any], Path, bool]:
    resolved = config_path(path)
    if not resolved.exists():
        return default_config(), resolved, False
    data = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{resolved} must contain a YAML mapping")
    config = default_config()
    deep_update(config, data)
    return config, resolved, True


def deep_update(base: dict[str, Any], override: dict[str, Any]) -> None:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_update(base[key], value)
        else:
            base[key] = value


def write_default_config(path: str | Path | None = None, *, force: bool = False) -> Path:
    resolved = config_path(path)
    if resolved.exists() and not force:
        raise FileExistsError(f"{resolved} already exists; pass --force to replace it")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(yaml.safe_dump(default_config(), sort_keys=False), encoding="utf-8")
    return resolved


def run_config_doctor(path: str | Path | None = None, *, profile: str = "release") -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    needs_attention: list[dict[str, Any]] = []
    service_paths: dict[str, Path | None] = {}

    try:
        config, resolved, exists = load_config(path)
    except Exception as exc:
        checks.append(
            {
                "name": "config_parse",
                "ok": False,
                "severity": "error",
                "detail": str(exc),
                "state": "configured",
                "repair_command": REPAIR_COMMANDS["ask_config"],
            }
        )
        return build_config_doctor_result(
            profile=profile,
            config_path_value=str(config_path(path)),
            config_exists=False,
            checks=checks,
            needs_attention=[
                {
                    "name": "config_parse",
                    "severity": "error",
                    "reason": "ask_config_invalid",
                    "detail": str(exc),
                    "repair_command": REPAIR_COMMANDS["ask_config"],
                }
            ],
        )

    require_config = bool(config.get("release", {}).get("require_config_file", True))
    config_missing_is_error = profile == "release" and require_config
    add_check(
        checks,
        needs_attention,
        "config_file",
        exists,
        str(resolved),
        "error" if config_missing_is_error else "warning",
        reason="ask_config_missing",
        state="configured",
        repair_command=REPAIR_COMMANDS["ask_config"],
    )
    add_check(
        checks,
        needs_attention,
        "schema",
        config.get("schema") == CONFIG_SCHEMA,
        str(config.get("schema")),
        "error",
        reason="ask_config_schema_mismatch",
        state="configured",
        repair_command=REPAIR_COMMANDS["ask_config"],
    )

    services = config.get("services", {})
    service_repairs = {
        "memory_run": REPAIR_COMMANDS["memory"],
        "scillm_run": REPAIR_COMMANDS["scillm"],
        "dogpile_run": REPAIR_COMMANDS["ask_config"],
        "interview_run": REPAIR_COMMANDS["ask_config"],
        "subagent_runner": REPAIR_COMMANDS["ask_config"],
    }
    for key in ("memory_run", "scillm_run", "dogpile_run", "interview_run", "subagent_runner"):
        candidate = resolve_config_path(str(services.get(key) or ""))
        service_paths[key] = candidate
        add_check(
            checks,
            needs_attention,
            f"service:{key}",
            bool(candidate and candidate.exists() and os.access(candidate, os.X_OK)),
            str(candidate) if candidate else "not configured",
            "error" if key in {"memory_run", "scillm_run", "interview_run"} else "warning",
            reason=f"ask_config_missing_{key}",
            state="installed",
            repair_command=service_repairs[key],
        )

    scillm_base_url = str(services.get("scillm_base_url") or "")
    add_check(
        checks,
        needs_attention,
        "service:scillm_base_url",
        scillm_base_url.startswith(("http://", "https://")),
        scillm_base_url or "not configured",
        "error",
        reason="ask_config_missing_scillm_base_url",
        state="configured",
        repair_command=REPAIR_COMMANDS["scillm"],
    )

    docker_available = shutil.which("docker") is not None
    add_check(
        checks,
        needs_attention,
        "docker:cli",
        docker_available,
        shutil.which("docker") or "not found",
        "error" if profile == "release" else "warning",
        reason="ask_release_docker_missing",
        state="installed",
        repair_command=REPAIR_COMMANDS["docker"],
    )

    storage_root = Path(str(config.get("docker", {}).get("storage_root") or "/mnt/storage12tb")).expanduser()
    add_check(
        checks,
        needs_attention,
        "docker:storage_root",
        storage_root.exists(),
        str(storage_root),
        "warning",
        reason="ask_release_storage_root_missing",
        state="configured",
        repair_command=REPAIR_COMMANDS["docker"],
    )

    # Read-only service readiness contract: no containers are started here.
    require_live = bool(config.get("release", {}).get("require_live_services", True))
    live_severity = "error" if profile == "release" and require_live else "warning"
    readiness_probes = (
        probe_release_readiness(
            memory_run=service_paths.get("memory_run"),
            scillm_run=service_paths.get("scillm_run"),
        )
        if exists and profile == "release" and require_live
        else {}
    )
    for name, repair_key in (
        ("arangodb", "arangodb"),
        ("qdrant", "qdrant"),
        ("vector_store", "qdrant"),
        ("embedder", "embedder"),
        ("memory", "memory"),
        ("scillm", "scillm"),
    ):
        probe = readiness_probes.get(name, {})
        add_check(
            checks,
            needs_attention,
            f"readiness:{name}",
            bool(probe.get("ok", False)),
            str(probe.get("detail") or "not verified by config doctor; run the service-specific doctor/bootstrap outside config doctor"),
            live_severity,
            reason=f"ask_release_{name}_not_verified",
            state="services_reachable" if name in {"memory", "scillm"} else "databases_bootstrapped",
            repair_command=REPAIR_COMMANDS[repair_key],
        )

    if profile == "release" and config.get("release", {}).get("require_oauth_credentials", True):
        for credential in config.get("release", {}).get("required_credentials", []):
            credential_path = Path(str(credential)).expanduser()
            add_check(
                checks,
                needs_attention,
                f"credential:{credential}",
                credential_path.exists(),
                str(credential_path),
                "error",
                reason="ask_release_credential_missing",
                state="configured",
                repair_command=REPAIR_COMMANDS["provider_auth"],
            )

    return build_config_doctor_result(
        profile=profile,
        config_path_value=str(resolved),
        config_exists=exists,
        checks=checks,
        needs_attention=needs_attention,
    )


def probe_release_readiness(*, memory_run: Path | None, scillm_run: Path | None) -> dict[str, dict[str, Any]]:
    """Run read-only release probes without starting or mutating services."""
    probes: dict[str, dict[str, Any]] = {}

    memory_status = run_json_probe(
        [str(memory_run), "status"] if memory_run else [],
        timeout=15,
    )
    memory_payload = memory_status.get("payload", {})
    memory_ok = bool(
        memory_status["ok"]
        and isinstance(memory_payload, dict)
        and (memory_payload.get("ok") is True or memory_payload.get("status") == "ok")
    )
    arango_ok = bool(memory_ok and memory_payload.get("memory_db_connected") is True)
    probes["memory"] = {
        "ok": memory_ok,
        "detail": memory_status["detail"],
    }
    probes["arangodb"] = {
        "ok": arango_ok,
        "detail": f"memory status: {memory_status['detail']}",
    }

    memory_recall = run_json_probe(
        [str(memory_run), "recall", "--q", "ask release readiness probe", "--k", "1"] if memory_run else [],
        timeout=30,
    )
    recall_payload = memory_recall.get("payload", {})
    recall_meta = recall_payload.get("meta", {}) if isinstance(recall_payload, dict) else {}
    recall_items = recall_payload.get("items", []) if isinstance(recall_payload, dict) else []
    used_dense = bool(recall_meta.get("used_dense"))
    has_qdrant_item = any(
        isinstance(item, dict) and (item.get("qdrant_collection") or item.get("_qdrant_score") is not None)
        for item in recall_items
    )
    has_embedding_model = any(
        isinstance(item, dict) and item.get("embedding_model")
        for item in recall_items
    )
    dense_detail = (
        f"{memory_recall['detail']}; used_dense={used_dense}; "
        f"qdrant_item={has_qdrant_item}; embedding_model={has_embedding_model}"
    )
    vector_ok = bool(memory_recall["ok"] and used_dense)
    probes["qdrant"] = {
        "ok": bool(vector_ok and has_qdrant_item),
        "detail": dense_detail,
    }
    probes["vector_store"] = {
        "ok": vector_ok,
        "detail": dense_detail,
    }
    probes["embedder"] = {
        "ok": bool(vector_ok and has_embedding_model),
        "detail": dense_detail,
    }

    scillm_status = run_json_probe(
        [str(scillm_run), "warm-check", "--json"] if scillm_run else [],
        timeout=30,
    )
    scillm_payload = scillm_status.get("payload", {})
    probes["scillm"] = {
        "ok": bool(scillm_status["ok"] and isinstance(scillm_payload, dict) and scillm_payload.get("model")),
        "detail": scillm_status["detail"],
    }
    return probes


def run_json_probe(command: list[str], *, timeout: int) -> dict[str, Any]:
    if not command:
        return {"ok": False, "detail": "probe command not configured", "payload": {}}
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={key: value for key, value in os.environ.items() if key != "VIRTUAL_ENV"},
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "detail": f"timed out after {timeout}s", "payload": {}}
    except OSError as exc:
        return {"ok": False, "detail": str(exc), "payload": {}}

    detail = f"exit={result.returncode}"
    if result.stderr:
        detail += f" stderr={result.stderr.strip()[:160]}"
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        return {"ok": False, "detail": f"{detail}; invalid json: {exc}", "payload": {}}
    return {"ok": result.returncode == 0, "detail": detail, "payload": payload}


def add_check(
    checks: list[dict[str, Any]],
    needs_attention: list[dict[str, Any]],
    name: str,
    ok: bool,
    detail: str,
    severity: str,
    *,
    reason: str,
    state: str,
    repair_command: str,
) -> None:
    check = {
        "name": name,
        "ok": ok,
        "severity": severity,
        "detail": detail,
        "state": state,
        "repair_command": repair_command,
    }
    checks.append(check)
    if not ok:
        needs_attention.append(
            {
                "name": name,
                "severity": severity,
                "reason": reason,
                "detail": detail,
                "state": state,
                "repair_command": repair_command,
            }
        )


def build_config_doctor_result(
    *,
    profile: str,
    config_path_value: str,
    config_exists: bool,
    checks: list[dict[str, Any]],
    needs_attention: list[dict[str, Any]],
) -> dict[str, Any]:
    error_count = sum(1 for check in checks if not check["ok"] and check["severity"] == "error")
    warning_count = sum(1 for check in checks if not check["ok"] and check["severity"] == "warning")
    release_ready = error_count == 0 and all(check["ok"] for check in checks if check["state"] != "installed")
    readiness = {
        "schema": READINESS_SCHEMA,
        "installed": state_ready(checks, "installed"),
        "configured": state_ready(checks, "configured"),
        "services_reachable": state_ready(checks, "services_reachable"),
        "databases_bootstrapped": state_ready(checks, "databases_bootstrapped"),
        "release_ready": release_ready,
        "safe_default": "claim_release_ready" if release_ready else SAFE_DEFAULT,
        "mutation_policy": "report_only_never_start_containers",
    }
    result: dict[str, Any] = {
        "schema": CONFIG_DOCTOR_SCHEMA,
        "status": "pass" if release_ready else "needs_attention",
        "profile": profile,
        "config_path": config_path_value,
        "config_exists": config_exists,
        "error_count": error_count,
        "warning_count": warning_count,
        "readiness": readiness,
        "checks": checks,
    }
    if needs_attention:
        result["needs_attention"] = {
            "reason": "ask_release_config_incomplete",
            "question": "Run repair commands for each item, then re-run release readiness.",
            "safe_default": SAFE_DEFAULT,
            "resume_hint": "./run.sh config doctor --json",
            "items": needs_attention,
            "suggested_skills": ["/interview"],
        }
    return result


def state_ready(checks: list[dict[str, Any]], state: str) -> bool:
    state_checks = [check for check in checks if check.get("state") == state and check.get("severity") != "info"]
    return bool(state_checks) and all(bool(check.get("ok")) for check in state_checks)
