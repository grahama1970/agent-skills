#!/usr/bin/env python3
"""Emit Surf's versioned capability contract as JSON."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
REPO_DIR = SKILL_DIR.parents[1]
DEFAULT_SURF_CLI_PATH = SKILL_DIR / "vendor" / "surf-cli"
SOCKET_PATH = Path(os.environ.get("SURF_SOCKET", "/tmp/surf.sock"))


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def sha256_file(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def git_head(path: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None


def vendor_status(vendor_path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "path": str(vendor_path),
        "package_name": None,
        "package_version": None,
        "lock_present": False,
        "lock": None,
        "fork_metadata": None,
        "dist_present": (vendor_path / "dist").exists(),
        "dist_fresh": None,
        "content_identity_matches": None,
    }

    package_json = read_json(vendor_path / "package.json")
    if package_json:
        payload["package_name"] = package_json.get("name")
        payload["package_version"] = package_json.get("version")

    lock = read_json(vendor_path / "VENDOR.lock.json")
    if lock is not None:
        payload["lock_present"] = True
        payload["lock"] = lock

    fork_json = read_json(SKILL_DIR / "vendor" / "fork.json")
    if fork_json is not None:
        payload["fork_metadata"] = {
            "repo": fork_json.get("repo"),
            "default_ref": fork_json.get("default_ref"),
            "rsync_excludes": fork_json.get("rsync_excludes"),
        }

    src_sw = vendor_path / "src" / "service-worker" / "index.ts"
    dist_sw = vendor_path / "dist" / "service-worker" / "index.js"
    if dist_sw.exists():
        payload["dist_fresh"] = not (src_sw.exists() and src_sw.stat().st_mtime > dist_sw.stat().st_mtime)
    else:
        payload["dist_fresh"] = False

    if lock and (lock.get("content_identity") or {}).get("sha256"):
        payload["content_identity_matches"] = compute_content_identity(vendor_path, lock)

    return payload


def compute_content_identity(vendor_path: Path, lock: dict[str, Any]) -> bool | None:
    identity = lock.get("content_identity") or {}
    expected = identity.get("sha256")
    if not expected:
        return None

    excludes = set(identity.get("excludes") or ["VENDOR.lock.json"])
    fork_json = read_json(SKILL_DIR / "vendor" / "fork.json") or {}
    excludes.update(fork_json.get("rsync_excludes") or [])

    def is_excluded(path: Path) -> bool:
        rel = path.relative_to(vendor_path).as_posix()
        for item in excludes:
            item = str(item).strip().rstrip("/")
            if rel == item or rel.startswith(item + "/"):
                return True
        return False

    try:
        files = sorted(path for path in vendor_path.rglob("*") if path.is_file() and not is_excluded(path))
        digest = hashlib.sha256()
        for path in files:
            data = path.read_bytes()
            digest.update(path.relative_to(vendor_path).as_posix().encode())
            digest.update(b"\0")
            digest.update(str(len(data)).encode())
            digest.update(b"\0")
            digest.update(data)
        return digest.hexdigest() == expected
    except OSError:
        return None


def socket_present(path: Path) -> bool:
    try:
        return path.exists() and stat.S_ISSOCK(path.stat().st_mode)
    except OSError:
        return False


def build_payload() -> dict[str, Any]:
    vendor_path = Path(os.environ.get("SURF_CLI_PATH", str(DEFAULT_SURF_CLI_PATH))).resolve()
    skill_md = SKILL_DIR / "SKILL.md"
    engine = vendor_status(vendor_path)
    skill_commit = git_head(REPO_DIR)

    return {
        "schema": "surf.capabilities.v1",
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "skill": {
            "name": "surf",
            "path": str(SKILL_DIR),
            "skill_md": str(skill_md),
            "skill_md_sha256": sha256_file(skill_md),
            "repo_commit": skill_commit,
            "contract_references": [
                "references/capabilities.schema.json",
                "references/provider-result.schema.json",
                "references/immutable-submit-contract.md",
                "references/vendor-update-gate.md",
            ],
        },
        "engine": {
            "kind": "vendored_surf_cli",
            "package_name": engine.get("package_name"),
            "package_version": engine.get("package_version"),
            "path": engine.get("path"),
            "dist_present": engine.get("dist_present"),
            "dist_fresh": engine.get("dist_fresh"),
            "lock_present": engine.get("lock_present"),
            "lock": engine.get("lock"),
            "fork_metadata": engine.get("fork_metadata"),
            "content_identity_matches": engine.get("content_identity_matches"),
        },
        "transport": {
            "extension_socket_path": str(SOCKET_PATH),
            "extension_socket_present": socket_present(SOCKET_PATH),
            "cdp_fallback": True,
            "cdp_port": int(os.environ.get("CDP_PORT", "9222")),
            "cdp_user_data_dir": os.environ.get("CHROME_USER_DATA", "/tmp/chrome-cdp-profile"),
        },
        "commands": {
            "diagnostics": ["setup", "sanity", "doctor", "capabilities", "vendor.status", "extension.fresh"],
            "provider_submits": ["webgpt.submit", "claude.submit", "gemini.submit", "kimi.submit", "grok.submit"],
            "provider_extracts": ["webgpt.extract", "gemini.extract", "grok.extract"],
            "provider_result_tools": ["meta.normalize"],
            "browser_core": ["tab.list", "tab.new", "go", "read", "text", "click", "type", "key", "snap", "scroll"],
        },
        "providers": provider_contracts(),
        "lock_behavior": {
            "browser_lock_required_for_provider_submits": True,
            "no_lock_forbidden_for": ["webgpt.submit", "claude.submit", "gemini.submit", "kimi.submit", "grok.submit"],
            "diagnostic_fields": ["owner_pid", "owner_socket", "owner_created_at", "lock_dir", "wait_seconds"],
            "stale_lock_recovery": "bounded_cleanup_with_receipt",
        },
        "recovery_features": recovery_features(),
        "contracts": {
            "capabilities_schema": "surf.capabilities.v1",
            "provider_result_schema": "surf.provider_result.v1",
            "immutable_submit_schema": "surf.immutable_submit.v1",
            "vendor_update_gate": "surf.vendor_update_gate.v1",
        },
        "proof_commands": {
            "offline": [
                "python3 scripts/surf_capabilities.py --json",
                "python3 scripts/surf_meta_normalize.py --meta <response.meta.json> --json --strict",
                "pytest -q tests/test_capabilities_contract.py tests/test_provider_result_normalize.py",
            ],
            "live_optional": [
                "./run.sh webgpt.e2e-sanity --json",
                "./run.sh webgpt.live-sanity --profile release",
            ],
        },
    }


def provider_contracts() -> dict[str, Any]:
    common = {
        "result_schema": "surf.provider_result.v1",
        "immutable_snapshot_required": True,
        "records": [
            "proof_status",
            "requested_tab_id",
            "controlled_tab_id_or_view_id",
            "requested_url",
            "actual_url",
            "input",
            "submitted_output",
            "output",
            "raw_output",
            "stderr_log",
            "retryability",
            "bounded_error",
        ],
    }
    return {
        "webgpt": {
            **common,
            "command": "webgpt.submit",
            "state_env": "SURF_WEBGPT_TAB_STATE",
            "supports": {
                "sentinel_completion": True,
                "provider_specific_extract": True,
                "no_activate": True,
                "auto_download": True,
                "conversation_max_length_rollover": True,
                "too_many_requests_cooldown": True,
                "stale_binding_repair": True,
            },
        },
        "claude": {
            **common,
            "command": "claude.submit",
            "state_env": "SURF_CLAUDE_TAB_STATE",
            "supports": {
                "sentinel_completion": True,
                "provider_specific_extract": False,
                "stale_binding_repair": True,
                "browser_oracle_rebind": True,
            },
        },
        "gemini": {
            **common,
            "command": "gemini.submit",
            "state_env": "SURF_GEMINI_TAB_STATE",
            "supports": {
                "sentinel_completion": True,
                "provider_specific_extract": True,
                "stale_binding_repair": True,
                "model_selection": True,
            },
        },
        "kimi": {
            **common,
            "command": "kimi.submit",
            "state_env": "SURF_KIMI_TAB_STATE",
            "default_model": "Instant",
            "default_reasoning": "High",
            "supports": {
                "sentinel_completion": True,
                "provider_specific_extract": False,
                "stale_binding_repair": True,
                "reasoning_selection": True,
                "provider_capacity_detection": True,
            },
        },
        "grok": {
            **common,
            "command": "grok.submit",
            "state_env": "SURF_GROK_TAB_STATE",
            "supports": {
                "sentinel_completion": True,
                "provider_specific_extract": True,
                "stale_binding_repair": True,
                "provider_backend": True,
            },
        },
    }


def recovery_features() -> dict[str, list[str]]:
    common = ["exact_tab_preflight", "stale_binding_detection", "bounded_error_metadata", "immutable_request_snapshot"]
    return {
        "webgpt": common
        + [
            "conversation_max_length_rollover",
            "too_many_requests_cooldown",
            "duplicate_tab_cleanup",
            "kde_desktop_auto_switch",
            "stale_cdp_composer_recovery",
            "browser_oracle_create_missing",
            "download_artifact_verification",
        ],
        "claude": common + ["browser_oracle_rebind", "read_timeout_classification"],
        "gemini": common + ["browser_oracle_rebind", "invalid_tab_rebind"],
        "kimi": common + ["instant_high_default", "capacity_backoff_classification"],
        "grok": common + ["provider_backend_presence_check", "provider_specific_extract"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON; currently the default output")
    args = parser.parse_args()
    payload = build_payload()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
