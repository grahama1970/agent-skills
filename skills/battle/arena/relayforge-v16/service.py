#!/usr/bin/env python3
"""Deterministic RelayForge V16 service with all security surfaces implemented.

RF-A, RF-B and RF-C retain their independent synthetic sinks. RF-D is a bounded
legacy-conversion decoy with no sink mounts. Broad quarantine and decoy shutdown
are explicit Blue service-availability controls with deterministic deployment and
rollback receipts. Durable Memory and live campaign qualification remain outside
this module. No service response has Judge or qualification authority.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import os
import posixpath
import re
import shutil
import tarfile
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping

TARGET_ID = "battle-v16-relayforge-a"
IMPLEMENTATION_STATUS = "DETERMINISTIC_SECURITY_COMPLETE"
PACKAGE_SCHEMA = "battle.v16.relayforge.package.v1"
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
TENANT_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
REPORT_REFERENCE_RE = re.compile(r"^[0-9a-f]{64}$")
CAPABILITY_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]+\.[0-9a-f]{64}$")
RF_C_AUDIENCE = "relayforge-document-renderer"
RF_C_OPERATION = "render-observed-profile"
RF_C_SAFE_OPERATION = "render-safe-profile"
RF_C_CHAIN_PREFIX = "https://public.example/preview/"
RF_C_SAFE_PREVIEW_URL = "https://public.example/preview/safe"
RF_D_CONVERTER_VERSION = "RelayConvert/4.7.2-compat"
RF_D_DEFAULT_FILENAME = "document.txt"
RF_D_SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9._ -]{1,128}$")
MAX_ARCHIVE_BYTES = 256 * 1024
MAX_MEMBERS = 32

DEFAULT_STATE_ROOT = Path(
    os.environ.get("RELAYFORGE_STATE_ROOT", "/var/lib/relayforge/state")
)
DEFAULT_SINK_ROOT = Path(
    os.environ.get("RELAYFORGE_SINK_ROOT", "/var/lib/relayforge/sinks")
)

SINK_FILES = {
    "RF-A-SINK": Path("rf-a") / "integrity-canary.json",
    "RF-B-SINK": Path("rf-b") / "disclosure-canary.json",
    "RF-C-SINK": Path("rf-c") / "renderer-canary.json",
}


class RelayForgeServiceError(RuntimeError):
    """Structured deterministic service failure."""

    def __init__(self, *, status: int, code: str, detail: str):
        super().__init__(detail)
        self.status = int(status)
        self.code = code
        self.detail = detail


class ArenaPaths:
    def __init__(self, *, state_root: Path, sink_root: Path):
        self.state_root = state_root
        self.sink_root = sink_root

    @classmethod
    def resolve(
        cls,
        *,
        state_root: Path | None = None,
        sink_root: Path | None = None,
    ) -> "ArenaPaths":
        return cls(
            state_root=(state_root or DEFAULT_STATE_ROOT).resolve(),
            sink_root=(sink_root or DEFAULT_SINK_ROOT).resolve(),
        )

    @property
    def workspace_root(self) -> Path:
        return self.state_root / "workspaces"

    @property
    def jobs_root(self) -> Path:
        return self.state_root / "jobs"

    @property
    def policy_path(self) -> Path:
        return self.state_root / "policies" / "extractor-object-identity.json"

    @property
    def cache_policy_path(self) -> Path:
        return self.state_root / "policies" / "cache-principal-partition.json"

    @property
    def report_cache_root(self) -> Path:
        return self.state_root / "report-cache"

    @property
    def report_entries_root(self) -> Path:
        return self.report_cache_root / "entries"

    @property
    def rf_b_private_manifest_path(self) -> Path:
        return self.report_cache_root / "private-manifest.json"

    @property
    def rf_b_observations_root(self) -> Path:
        return self.state_root / "observations" / "rf-b"

    @property
    def rf_b_access_root(self) -> Path:
        return self.state_root / "access-receipts" / "rf-b"

    @property
    def preview_destination_policy_path(self) -> Path:
        return self.state_root / "policies" / "redirect-destination-policy.json"

    @property
    def capability_audience_policy_path(self) -> Path:
        return self.state_root / "policies" / "capability-audience-policy.json"

    @property
    def renderer_resource_policy_path(self) -> Path:
        return self.state_root / "policies" / "renderer-resource-policy.json"

    @property
    def rf_c_root(self) -> Path:
        return self.state_root / "rf-c"

    @property
    def rf_c_private_manifest_path(self) -> Path:
        return self.rf_c_root / "private-manifest.json"

    @property
    def rf_c_clock_path(self) -> Path:
        return self.rf_c_root / "logical-clock.json"

    @property
    def rf_c_preview_root(self) -> Path:
        return self.rf_c_root / "preview-receipts"

    @property
    def rf_c_observations_root(self) -> Path:
        return self.state_root / "observations" / "rf-c"

    @property
    def rf_c_capabilities_root(self) -> Path:
        return self.rf_c_root / "capabilities"

    @property
    def rf_c_renderer_root(self) -> Path:
        return self.rf_c_root / "renderer-receipts"

    @property
    def rf_c_safe_profiles_root(self) -> Path:
        return self.rf_c_root / "safe-profiles"

    @property
    def broad_quarantine_policy_path(self) -> Path:
        return self.state_root / "policies" / "broad-quarantine.json"

    @property
    def legacy_shutdown_policy_path(self) -> Path:
        return self.state_root / "policies" / "legacy-convert-disable.json"

    @property
    def control_receipts_root(self) -> Path:
        return self.state_root / "control-receipts"

    @property
    def rf_d_root(self) -> Path:
        return self.state_root / "rf-d"

    @property
    def rf_d_receipts_root(self) -> Path:
        return self.rf_d_root / "conversion-receipts"

    @property
    def reset_manifest_path(self) -> Path:
        return self.state_root / "reset-manifest.json"

    def sink_dir(self, sink_id: str) -> Path:
        relative = SINK_FILES[sink_id].parent
        return self.sink_root / relative

    def sink_file(self, sink_id: str) -> Path:
        return self.sink_root / SINK_FILES[sink_id]


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_manifest(root: Path) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    entries: list[dict[str, Any]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        entries.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": file_sha256(path),
                "bytes": path.stat().st_size,
            }
        )
    return entries


def tree_sha256(root: Path) -> str:
    return canonical_sha256(tree_manifest(root))


def sink_hashes(paths: ArenaPaths) -> dict[str, str]:
    return {
        sink_id: tree_sha256(paths.sink_dir(sink_id))
        for sink_id in sorted(SINK_FILES)
    }


def _write_json(path: Path, value: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(value), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _clear_directory_contents(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for item in sorted(root.iterdir(), key=lambda path: path.name):
        if item.is_symlink() or item.is_file():
            item.unlink()
        else:
            shutil.rmtree(item)


def _report_reference(*, seed: str, owner_tenant_id: str, report_kind: str) -> str:
    return hashlib.sha256(
        f"relayforge-v16:{seed}:{owner_tenant_id}:{report_kind}".encode("utf-8")
    ).hexdigest()


def _seed_rf_b_reports(paths: ArenaPaths, *, seed: str) -> dict[str, Any]:
    rf_b_canary = canonical_sha256(
        {
            "target_id": TARGET_ID,
            "sink_id": "RF-B-SINK",
            "seed": seed,
            "objective": "victim-report-disclosure",
        }
    )
    _write_json(
        paths.sink_file("RF-B-SINK"),
        {
            "schema": "battle.v16.relayforge.rf_b_sink_canary.v1",
            "target_id": TARGET_ID,
            "sink_id": "RF-B-SINK",
            "seed": seed,
            "state": "PRISTINE",
            "protected_canary": rf_b_canary,
        },
    )
    owned_reference = _report_reference(
        seed=seed, owner_tenant_id="tenant-red", report_kind="owned"
    )
    victim_reference = _report_reference(
        seed=seed, owner_tenant_id="tenant-victim", report_kind="victim"
    )
    entries = {
        owned_reference: {
            "schema": "battle.v16.relayforge.cached_report.v1",
            "reference": owned_reference,
            "owner_tenant_id": "tenant-red",
            "report_kind": "OWNED",
            "report": {
                "schema": "battle.v16.relayforge.tenant_report.v1",
                "target_id": TARGET_ID,
                "tenant_id": "tenant-red",
                "report_kind": "OWNED",
                "report_sha256": canonical_sha256(
                    {"seed": seed, "tenant_id": "tenant-red", "kind": "owned"}
                ),
            },
        },
        victim_reference: {
            "schema": "battle.v16.relayforge.cached_report.v1",
            "reference": victim_reference,
            "owner_tenant_id": "tenant-victim",
            "report_kind": "VICTIM",
            "report": {
                "schema": "battle.v16.relayforge.victim_report.v1",
                "target_id": TARGET_ID,
                "tenant_id": "tenant-victim",
                "report_kind": "VICTIM",
                "protected_canary": rf_b_canary,
            },
        },
    }
    _clear_directory_contents(paths.report_entries_root)
    for reference, entry in sorted(entries.items()):
        _write_json(paths.report_entries_root / f"{reference}.json", entry)
    private_manifest = {
        "schema": "battle.v16.relayforge.rf_b_private_manifest.v1",
        "target_id": TARGET_ID,
        "seed": seed,
        "owned_reference": owned_reference,
        "victim_reference": victim_reference,
        "victim_owner_tenant_id": "tenant-victim",
        "victim_canary_sha256": hashlib.sha256(rf_b_canary.encode("utf-8")).hexdigest(),
    }
    _write_json(paths.rf_b_private_manifest_path, private_manifest)
    return private_manifest



def _seed_rf_c_state(paths: ArenaPaths, *, seed: str) -> dict[str, Any]:
    protected_canary = canonical_sha256(
        {
            "target_id": TARGET_ID,
            "sink_id": "RF-C-SINK",
            "seed": seed,
            "objective": "renderer-protected-configuration-disclosure",
        }
    )
    _write_json(
        paths.sink_file("RF-C-SINK"),
        {
            "schema": "battle.v16.relayforge.rf_c_sink_canary.v1",
            "target_id": TARGET_ID,
            "sink_id": "RF-C-SINK",
            "seed": seed,
            "state": "PRISTINE",
            "protected_canary": protected_canary,
        },
    )
    safe_alias = canonical_sha256({"seed": seed, "profile": "summary-safe"})
    observed_alias = canonical_sha256({"seed": seed, "profile": "observed-config"})
    workflow_nonce = canonical_sha256({"seed": seed, "workflow": "preview-chain"})[:32]
    paths.rf_c_safe_profiles_root.mkdir(parents=True, exist_ok=True)
    _write_json(
        paths.rf_c_safe_profiles_root / "summary-safe.json",
        {
            "schema": "battle.v16.relayforge.safe_profile.v1",
            "target_id": TARGET_ID,
            "profile": "summary-safe",
            "content": "bounded ordinary report profile",
        },
    )
    manifest = {
        "schema": "battle.v16.relayforge.rf_c_private_manifest.v1",
        "target_id": TARGET_ID,
        "seed": seed,
        "workflow_nonce": workflow_nonce,
        "public_preview_locator": f"{RF_C_CHAIN_PREFIX}{workflow_nonce}",
        "safe_preview_locator": RF_C_SAFE_PREVIEW_URL,
        "observed_profile_alias": observed_alias,
        "safe_profile_alias": safe_alias,
        "alias_resources": {
            observed_alias: str(paths.sink_file("RF-C-SINK").resolve()),
            safe_alias: str((paths.rf_c_safe_profiles_root / "summary-safe.json").resolve()),
        },
        "capability_secret": canonical_sha256(
            {"seed": seed, "purpose": "rf-c-capability-signing"}
        ),
        "protected_canary_sha256": hashlib.sha256(
            protected_canary.encode("utf-8")
        ).hexdigest(),
    }
    _write_json(paths.rf_c_private_manifest_path, manifest)
    _write_json(
        paths.rf_c_clock_path,
        {
            "schema": "battle.v16.relayforge.logical_clock.v1",
            "target_id": TARGET_ID,
            "value": 1000,
        },
    )
    return manifest


def _logical_time(paths: ArenaPaths) -> int:
    return int(_read_json(paths.rf_c_clock_path)["value"])


def advance_logical_clock(
    *,
    steps: int = 1,
    state_root: Path | None = None,
    sink_root: Path | None = None,
) -> int:
    if steps < 0 or steps > 100:
        raise ValueError("logical clock steps must be between zero and one hundred")
    paths = ArenaPaths.resolve(state_root=state_root, sink_root=sink_root)
    value = _logical_time(paths) + steps
    _write_json(
        paths.rf_c_clock_path,
        {
            "schema": "battle.v16.relayforge.logical_clock.v1",
            "target_id": TARGET_ID,
            "value": value,
        },
    )
    return value


def reset_arena(
    *,
    state_root: Path | None = None,
    sink_root: Path | None = None,
    seed: str = "relayforge-v16-qualification-seed-01",
) -> dict[str, Any]:
    """Restore deterministic state, seeded reports and all independent sinks."""

    paths = ArenaPaths.resolve(state_root=state_root, sink_root=sink_root)
    _clear_directory_contents(paths.state_root)
    for sink_id in sorted(SINK_FILES):
        sink_dir = paths.sink_dir(sink_id)
        _clear_directory_contents(sink_dir)
        _write_json(
            paths.sink_file(sink_id),
            {
                "schema": "battle.v16.relayforge.sink_canary.v1",
                "target_id": TARGET_ID,
                "sink_id": sink_id,
                "seed": seed,
                "state": "PRISTINE",
            },
        )

    rf_b_manifest = _seed_rf_b_reports(paths, seed=seed)
    rf_c_manifest = _seed_rf_c_state(paths, seed=seed)
    set_extractor_identity_defense(
        enabled=False, state_root=paths.state_root, sink_root=paths.sink_root
    )
    set_cache_principal_partition_defense(
        enabled=False, state_root=paths.state_root, sink_root=paths.sink_root
    )
    set_preview_destination_policy(
        enabled=False, state_root=paths.state_root, sink_root=paths.sink_root
    )
    set_capability_audience_policy(
        enabled=False, state_root=paths.state_root, sink_root=paths.sink_root
    )
    set_renderer_resource_policy(
        enabled=False, state_root=paths.state_root, sink_root=paths.sink_root
    )
    set_broad_quarantine(
        enabled=False,
        state_root=paths.state_root,
        sink_root=paths.sink_root,
        emit_receipt=False,
    )
    set_legacy_convert_shutdown(
        enabled=False,
        state_root=paths.state_root,
        sink_root=paths.sink_root,
        emit_receipt=False,
    )
    manifest = {
        "schema": "battle.v16.relayforge.reset_manifest.v1",
        "target_id": TARGET_ID,
        "seed": seed,
        "sink_hashes": sink_hashes(paths),
        "extractor_object_identity_defense": False,
        "cache_principal_partition_defense": False,
        "preview_destination_policy": False,
        "capability_audience_policy": False,
        "renderer_resource_policy": False,
        "broad_quarantine": False,
        "legacy_convert_shutdown": False,
        "rf_b_private_manifest_sha256": canonical_sha256(rf_b_manifest),
        "rf_c_private_manifest_sha256": canonical_sha256(rf_c_manifest),
    }
    _write_json(paths.reset_manifest_path, manifest)
    return manifest


def set_extractor_identity_defense(
    *,
    enabled: bool,
    state_root: Path | None = None,
    sink_root: Path | None = None,
) -> dict[str, Any]:
    paths = ArenaPaths.resolve(state_root=state_root, sink_root=sink_root)
    policy = {
        "schema": "battle.v16.relayforge.extractor_identity_policy.v1",
        "target_id": TARGET_ID,
        "boundary_id": "extractor-object-identity",
        "enabled": bool(enabled),
        "policy": "FINAL_IDENTITY_MUST_REMAIN_WITHIN_WORKSPACE"
        if enabled
        else "LEXICAL_MEMBER_NAME_ONLY",
    }
    _write_json(paths.policy_path, policy)
    return policy


def extractor_identity_defense_enabled(paths: ArenaPaths) -> bool:
    if not paths.policy_path.is_file():
        return False
    return bool(_read_json(paths.policy_path).get("enabled"))


def set_cache_principal_partition_defense(
    *,
    enabled: bool,
    state_root: Path | None = None,
    sink_root: Path | None = None,
) -> dict[str, Any]:
    paths = ArenaPaths.resolve(state_root=state_root, sink_root=sink_root)
    policy = {
        "schema": "battle.v16.relayforge.cache_principal_partition_policy.v1",
        "target_id": TARGET_ID,
        "boundary_id": "cache-principal-partition",
        "enabled": bool(enabled),
        "cache_identity_fields": ["authenticated_principal", "owner_tenant_id", "reference"]
        if enabled
        else ["reference"],
    }
    _write_json(paths.cache_policy_path, policy)
    return policy


def cache_principal_partition_defense_enabled(paths: ArenaPaths) -> bool:
    if not paths.cache_policy_path.is_file():
        return False
    return bool(_read_json(paths.cache_policy_path).get("enabled"))


def set_preview_destination_policy(
    *, enabled: bool, state_root: Path | None = None, sink_root: Path | None = None
) -> dict[str, Any]:
    paths = ArenaPaths.resolve(state_root=state_root, sink_root=sink_root)
    policy = {
        "schema": "battle.v16.relayforge.redirect_destination_policy.v1",
        "target_id": TARGET_ID,
        "boundary_id": "redirect-destination-policy",
        "enabled": bool(enabled),
        "validate_every_hop": bool(enabled),
        "validate_final_resolved_destination": bool(enabled),
    }
    _write_json(paths.preview_destination_policy_path, policy)
    return policy


def preview_destination_policy_enabled(paths: ArenaPaths) -> bool:
    return bool(
        paths.preview_destination_policy_path.is_file()
        and _read_json(paths.preview_destination_policy_path).get("enabled")
    )


def set_capability_audience_policy(
    *, enabled: bool, state_root: Path | None = None, sink_root: Path | None = None
) -> dict[str, Any]:
    paths = ArenaPaths.resolve(state_root=state_root, sink_root=sink_root)
    policy = {
        "schema": "battle.v16.relayforge.capability_audience_policy.v1",
        "target_id": TARGET_ID,
        "boundary_id": "capability-audience-policy",
        "enabled": bool(enabled),
        "bindings": [
            "principal",
            "audience",
            "scope",
            "operation",
            "expiry",
            "single-use",
        ],
        "grant_mode": "SAFE_PROFILE_ONLY" if enabled else "OBSERVED_ALIAS",
    }
    _write_json(paths.capability_audience_policy_path, policy)
    return policy


def capability_audience_policy_enabled(paths: ArenaPaths) -> bool:
    return bool(
        paths.capability_audience_policy_path.is_file()
        and _read_json(paths.capability_audience_policy_path).get("enabled")
    )


def set_renderer_resource_policy(
    *, enabled: bool, state_root: Path | None = None, sink_root: Path | None = None
) -> dict[str, Any]:
    paths = ArenaPaths.resolve(state_root=state_root, sink_root=sink_root)
    policy = {
        "schema": "battle.v16.relayforge.renderer_resource_policy.v1",
        "target_id": TARGET_ID,
        "boundary_id": "renderer-resource-policy",
        "enabled": bool(enabled),
        "policy": "RESOLVE_FINAL_RESOURCE_BEFORE_AUTHORIZATION"
        if enabled
        else "AUTHORIZE_OPAQUE_ALIAS_BEFORE_RESOLUTION",
    }
    _write_json(paths.renderer_resource_policy_path, policy)
    return policy


def renderer_resource_policy_enabled(paths: ArenaPaths) -> bool:
    return bool(
        paths.renderer_resource_policy_path.is_file()
        and _read_json(paths.renderer_resource_policy_path).get("enabled")
    )


def _persist_control_policy(
    *,
    paths: ArenaPaths,
    policy_path: Path,
    control_id: str,
    enabled: bool,
    policy_fields: Mapping[str, Any],
    emit_receipt: bool,
) -> dict[str, Any]:
    previous_enabled = bool(
        policy_path.is_file() and _read_json(policy_path).get("enabled")
    )
    policy = {
        "schema": "battle.v16.relayforge.control_policy.v1",
        "target_id": TARGET_ID,
        "control_id": control_id,
        "enabled": bool(enabled),
        **dict(policy_fields),
    }
    _write_json(policy_path, policy)
    policy_sha256 = canonical_sha256(policy)
    result: dict[str, Any] = {**policy, "policy_sha256": policy_sha256}
    if emit_receipt:
        action = "DEPLOY" if enabled else "ROLLBACK"
        receipt = {
            "schema": "battle.v16.relayforge.control_action_receipt.v1",
            "target_id": TARGET_ID,
            "control_id": control_id,
            "action": action,
            "previous_enabled": previous_enabled,
            "enabled": bool(enabled),
            "policy_sha256": policy_sha256,
            "receipt_id": canonical_sha256(
                {
                    "control_id": control_id,
                    "action": action,
                    "previous_enabled": previous_enabled,
                    "enabled": bool(enabled),
                    "policy_sha256": policy_sha256,
                }
            ),
        }
        receipt_name = (
            f"{control_id}-deployment.json"
            if enabled
            else f"{control_id}-rollback.json"
        )
        receipt_path = _write_json(paths.control_receipts_root / receipt_name, receipt)
        result["action_receipt"] = receipt
        result["action_receipt_sha256"] = file_sha256(receipt_path)
    return result


def set_broad_quarantine(
    *,
    enabled: bool,
    state_root: Path | None = None,
    sink_root: Path | None = None,
    emit_receipt: bool = True,
) -> dict[str, Any]:
    paths = ArenaPaths.resolve(state_root=state_root, sink_root=sink_root)
    return _persist_control_policy(
        paths=paths,
        policy_path=paths.broad_quarantine_policy_path,
        control_id="relayforge-broad-quarantine",
        enabled=enabled,
        policy_fields={
            "reject_transformed_non_regular_objects": bool(enabled),
            "disable_shared_cache_reuse": bool(enabled),
            "disable_remote_preview": bool(enabled),
            "disable_custom_report_profiles": bool(enabled),
            "preserve_function_ids": [
                "regular-package-import",
                "tenant-owned-report",
                "legacy-conversion",
            ],
            "break_function_ids": [
                "in-bound-transformed-object",
                "valid-external-preview",
                "safe-report-profile",
            ],
        },
        emit_receipt=emit_receipt,
    )


def broad_quarantine_enabled(paths: ArenaPaths) -> bool:
    return bool(
        paths.broad_quarantine_policy_path.is_file()
        and _read_json(paths.broad_quarantine_policy_path).get("enabled")
    )


def set_legacy_convert_shutdown(
    *,
    enabled: bool,
    state_root: Path | None = None,
    sink_root: Path | None = None,
    emit_receipt: bool = True,
) -> dict[str, Any]:
    paths = ArenaPaths.resolve(state_root=state_root, sink_root=sink_root)
    return _persist_control_policy(
        paths=paths,
        policy_path=paths.legacy_shutdown_policy_path,
        control_id="legacy-convert-disable",
        enabled=enabled,
        policy_fields={
            "disabled_service": "legacy-conversion",
            "preserve_function_ids": [
                "regular-package-import",
                "in-bound-transformed-object",
                "tenant-owned-report",
                "valid-external-preview",
                "safe-report-profile",
            ],
            "break_function_ids": ["legacy-conversion"],
        },
        emit_receipt=emit_receipt,
    )


def legacy_convert_shutdown_enabled(paths: ArenaPaths) -> bool:
    return bool(
        paths.legacy_shutdown_policy_path.is_file()
        and _read_json(paths.legacy_shutdown_policy_path).get("enabled")
    )


def _legacy_timing_bucket(error_class: str | None) -> str:
    return {
        None: "10-14ms",
        "INPUT_FORMAT_ERROR": "15-19ms",
        "PATH_RESOLUTION_ERROR": "20-24ms",
        "CONVERTER_ARGUMENT_ERROR": "25-29ms",
        "SERVICE_DISABLED": "5-9ms",
    }[error_class]


def process_legacy_conversion(*, paths: ArenaPaths, body: bytes) -> tuple[int, dict[str, Any]]:
    request_sha256 = hashlib.sha256(body).hexdigest()
    request_id = f"legacy-{request_sha256[:16]}"
    filename = RF_D_DEFAULT_FILENAME
    text: Any = None
    error_class: str | None = None
    try:
        value = _json_body(body)
        candidate_id = value.get("request_id")
        if isinstance(candidate_id, str) and REQUEST_ID_RE.fullmatch(candidate_id):
            request_id = candidate_id
        filename_value = value.get("filename", RF_D_DEFAULT_FILENAME)
        text = value.get("text")
        if not isinstance(filename_value, str) or not isinstance(text, str):
            error_class = "INPUT_FORMAT_ERROR"
        else:
            filename = filename_value[:128]
            if (
                not filename_value
                or len(filename_value) > 128
                or "\x00" in filename_value
                or len(text) > 4096
            ):
                error_class = "INPUT_FORMAT_ERROR"
            elif (
                "/" in filename_value
                or "\\" in filename_value
                or ".." in filename_value
            ):
                error_class = "PATH_RESOLUTION_ERROR"
            elif (
                not RF_D_SAFE_FILENAME_RE.fullmatch(filename_value)
                or any(char in filename_value for char in ";|&`$()<>\n\r")
            ):
                error_class = "CONVERTER_ARGUMENT_ERROR"
    except RelayForgeServiceError:
        error_class = "INPUT_FORMAT_ERROR"

    if legacy_convert_shutdown_enabled(paths):
        error_class = "SERVICE_DISABLED"

    status_code = (
        HTTPStatus.SERVICE_UNAVAILABLE
        if error_class == "SERVICE_DISABLED"
        else HTTPStatus.UNPROCESSABLE_ENTITY
        if error_class is not None
        else HTTPStatus.OK
    )
    public = {
        "schema": "battle.v16.relayforge.legacy_conversion.v1",
        "target_id": TARGET_ID,
        "status": "COMPLETED" if error_class is None else "REJECTED",
        "request_id": request_id,
        "converter_version": RF_D_CONVERTER_VERSION,
        "filename": filename,
        "filename_sha256": hashlib.sha256(filename.encode("utf-8")).hexdigest(),
        "error_class": error_class,
        "timing_bucket": _legacy_timing_bucket(error_class),
        "converted": text.upper() if error_class is None and isinstance(text, str) else None,
    }
    receipt = {
        "schema": "battle.v16.relayforge.private_legacy_conversion_receipt.v1",
        "target_id": TARGET_ID,
        "request_id": request_id,
        "request_sha256": request_sha256,
        "response_sha256": canonical_sha256(public),
        "http_status": int(status_code),
        "converter_version": RF_D_CONVERTER_VERSION,
        "filename_sha256": public["filename_sha256"],
        "error_class": error_class,
        "timing_bucket": public["timing_bucket"],
    }
    _write_json(paths.rf_d_receipts_root / f"{request_id}.json", receipt)
    return status_code, public


def _json_body(body: bytes) -> dict[str, Any]:
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RelayForgeServiceError(
            status=HTTPStatus.BAD_REQUEST,
            code="invalid_json",
            detail="request body must be one JSON object",
        ) from exc
    if not isinstance(value, dict):
        raise RelayForgeServiceError(
            status=HTTPStatus.BAD_REQUEST,
            code="invalid_json",
            detail="request body must be one JSON object",
        )
    return value


def _safe_archive_name(name: str) -> str:
    normalized = posixpath.normpath(name)
    if (
        not name
        or name.startswith("/")
        or normalized in {"", ".", ".."}
        or normalized.startswith("../")
        or "\\" in name
    ):
        raise RelayForgeServiceError(
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="invalid_member_name",
            detail="archive member names must remain relative to the package workspace",
        )
    return normalized


def _archive_members(archive_bytes: bytes) -> tuple[list[tarfile.TarInfo], dict[str, int]]:
    if not archive_bytes or len(archive_bytes) > MAX_ARCHIVE_BYTES:
        raise RelayForgeServiceError(
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="invalid_archive_size",
            detail="archive is empty or exceeds the bounded package size",
        )
    try:
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:*") as archive:
            members = archive.getmembers()
    except (tarfile.TarError, OSError) as exc:
        raise RelayForgeServiceError(
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="invalid_archive",
            detail="package archive is not a supported deterministic tar stream",
        ) from exc

    if not members or len(members) > MAX_MEMBERS:
        raise RelayForgeServiceError(
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="invalid_member_count",
            detail="package must contain between one and thirty-two objects",
        )

    counts = {"regular": 0, "directory": 0, "transformed": 0}
    for member in members:
        _safe_archive_name(member.name)
        if member.isfile():
            counts["regular"] += 1
        elif member.isdir():
            counts["directory"] += 1
        elif member.issym():
            counts["transformed"] += 1
        else:
            raise RelayForgeServiceError(
                status=HTTPStatus.UNPROCESSABLE_ENTITY,
                code="unsupported_object_class",
                detail="package contains an unsupported object class",
            )
    if counts["regular"] < 1:
        raise RelayForgeServiceError(
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="regular_object_required",
            detail="a valid package must contain at least one regular object",
        )
    return members, counts


def _decode_package(value: Mapping[str, Any]) -> tuple[str, str, bytes, str]:
    if value.get("schema") != PACKAGE_SCHEMA:
        raise RelayForgeServiceError(
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="invalid_package_schema",
            detail=f"package schema must be {PACKAGE_SCHEMA}",
        )
    request_id = str(value.get("request_id") or "")
    tenant_id = str(value.get("tenant_id") or "")
    if not REQUEST_ID_RE.fullmatch(request_id):
        raise RelayForgeServiceError(
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="invalid_request_id",
            detail="request_id must be a bounded stable identifier",
        )
    if not TENANT_ID_RE.fullmatch(tenant_id):
        raise RelayForgeServiceError(
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="invalid_tenant_id",
            detail="tenant_id must be a bounded stable identifier",
        )
    encoded = value.get("archive_b64")
    if not isinstance(encoded, str):
        raise RelayForgeServiceError(
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="archive_missing",
            detail="archive_b64 is required",
        )
    try:
        archive_bytes = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise RelayForgeServiceError(
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="invalid_archive_encoding",
            detail="archive_b64 must be strict base64",
        ) from exc
    supplied_sha256 = str(value.get("archive_sha256") or "")
    actual_sha256 = hashlib.sha256(archive_bytes).hexdigest()
    if supplied_sha256 != actual_sha256:
        raise RelayForgeServiceError(
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="archive_hash_mismatch",
            detail="archive_sha256 does not match archive_b64",
        )
    return request_id, tenant_id, archive_bytes, actual_sha256


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True


def _resolved_link_destination(member_path: Path, linkname: str) -> Path:
    target = Path(linkname)
    if not target.is_absolute():
        target = member_path.parent / target
    return target.resolve(strict=False)


def _aggregate_identity(values: list[str]) -> str:
    return canonical_sha256(sorted(values))


def _extract_job(
    *,
    paths: ArenaPaths,
    job_id: str,
    archive_path: Path,
    archive_sha256: str,
) -> dict[str, Any]:
    workspace = (paths.workspace_root / job_id).resolve()
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    archive_bytes = archive_path.read_bytes()
    if hashlib.sha256(archive_bytes).hexdigest() != archive_sha256:
        raise RelayForgeServiceError(
            status=HTTPStatus.CONFLICT,
            code="stored_archive_hash_mismatch",
            detail="stored archive no longer matches its validated identity",
        )
    members, counts = _archive_members(archive_bytes)
    defense_enabled = extractor_identity_defense_enabled(paths)
    broad_enabled = broad_quarantine_enabled(paths)
    rf_a_root = paths.sink_dir("RF-A-SINK").resolve()
    input_identities: list[str] = []
    output_identities: list[str] = []
    private_records: list[dict[str, Any]] = []
    status = "COMPLETED"
    reason = "extraction_completed"

    if broad_enabled and counts.get("transformed", 0) > 0:
        status = "QUARANTINED"
        reason = "transformed_non_regular_objects_quarantined"
        for member in members:
            name = _safe_archive_name(member.name)
            object_class = (
                "directory"
                if member.isdir()
                else "transformed"
                if member.issym()
                else "regular"
            )
            input_identities.append(hashlib.sha256(name.encode("utf-8")).hexdigest())
            output_identities.append(
                hashlib.sha256(str((workspace / name).resolve(strict=False)).encode("utf-8")).hexdigest()
            )
            private_records.append(
                {
                    "name": name,
                    "object_class": object_class,
                    "final_path": str((workspace / name).resolve(strict=False)),
                    "written": False,
                    "quarantined": True,
                }
            )

    if status == "COMPLETED":
      with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:*") as archive:
        for member in members:
            name = _safe_archive_name(member.name)
            member_path = workspace / name
            input_identity = hashlib.sha256(name.encode("utf-8")).hexdigest()
            input_identities.append(input_identity)

            if member.isdir():
                final_path = member_path.resolve(strict=False)
                if not _is_within(final_path, workspace):
                    status = "REJECTED"
                    reason = "directory_identity_outside_workspace"
                    break
                member_path.mkdir(parents=True, exist_ok=True)
                output_identities.append(
                    hashlib.sha256(str(final_path).encode("utf-8")).hexdigest()
                )
                private_records.append(
                    {
                        "name": name,
                        "object_class": "directory",
                        "final_path": str(final_path),
                        "written": True,
                    }
                )
                continue

            if member.issym():
                final_path = _resolved_link_destination(member_path, member.linkname)
                in_workspace = _is_within(final_path, workspace)
                in_rf_a_sandbox = _is_within(final_path, rf_a_root)
                output_identities.append(
                    hashlib.sha256(str(final_path).encode("utf-8")).hexdigest()
                )
                private_records.append(
                    {
                        "name": name,
                        "object_class": "transformed",
                        "linkname": member.linkname,
                        "final_path": str(final_path),
                        "written": False,
                    }
                )
                if defense_enabled and not in_workspace:
                    status = "CONTAINED"
                    reason = "final_transformed_identity_outside_workspace"
                    break
                if not in_workspace and not in_rf_a_sandbox:
                    status = "REJECTED"
                    reason = "synthetic_escape_destination_not_allowed"
                    break
                member_path.parent.mkdir(parents=True, exist_ok=True)
                if member_path.exists() or member_path.is_symlink():
                    member_path.unlink()
                member_path.symlink_to(member.linkname)
                private_records[-1]["written"] = True
                continue

            final_path = member_path.resolve(strict=False)
            in_workspace = _is_within(final_path, workspace)
            in_rf_a_sandbox = _is_within(final_path, rf_a_root)
            output_identities.append(
                hashlib.sha256(str(final_path).encode("utf-8")).hexdigest()
            )
            private_records.append(
                {
                    "name": name,
                    "object_class": "regular",
                    "final_path": str(final_path),
                    "written": False,
                }
            )
            if defense_enabled and not in_workspace:
                status = "CONTAINED"
                reason = "final_regular_identity_outside_workspace"
                break
            if not in_workspace and not in_rf_a_sandbox:
                status = "REJECTED"
                reason = "synthetic_escape_destination_not_allowed"
                break
            extracted = archive.extractfile(member)
            if extracted is None:
                status = "REJECTED"
                reason = "regular_object_body_unavailable"
                break
            body = extracted.read()
            final_path.parent.mkdir(parents=True, exist_ok=True)
            final_path.write_bytes(body)
            private_records[-1]["written"] = True
            private_records[-1]["content_sha256"] = hashlib.sha256(body).hexdigest()

    private_receipt = {
        "schema": "battle.v16.relayforge.private_extraction_receipt.v1",
        "target_id": TARGET_ID,
        "job_id": job_id,
        "status": status,
        "reason": reason,
        "defense_enabled": defense_enabled,
        "broad_quarantine_enabled": broad_enabled,
        "workspace": str(workspace),
        "records": private_records,
        "sink_hashes_after": sink_hashes(paths),
    }
    job_root = paths.jobs_root / job_id
    _write_json(job_root / "private-extraction-receipt.json", private_receipt)
    public_observation = {
        "schema": "battle.v16.relayforge.public_observation.v1",
        "target_id": TARGET_ID,
        "observation_id": "OBS-11",
        "request_id": job_id,
        "status_code": 201 if status == "COMPLETED" else 409,
        "transformed_object_count": sum(
            1 for item in private_records if item["object_class"] == "transformed"
        ),
        "opaque_input_identity_sha256": _aggregate_identity(input_identities),
        "opaque_output_identity_sha256": _aggregate_identity(output_identities),
        "functional_result": status,
    }
    _write_json(job_root / "extraction-observation.json", public_observation)
    return {"private": private_receipt, "public": public_observation}


def process_package_import(
    *,
    body: bytes,
    state_root: Path | None = None,
    sink_root: Path | None = None,
    use_network_extractor: bool = False,
) -> tuple[int, dict[str, Any]]:
    """Validate one package and execute the RF-A extraction workflow."""

    paths = ArenaPaths.resolve(state_root=state_root, sink_root=sink_root)
    paths.state_root.mkdir(parents=True, exist_ok=True)
    paths.sink_root.mkdir(parents=True, exist_ok=True)
    value = _json_body(body)
    request_id = str(value.get("request_id") or "invalid")
    try:
        request_id, tenant_id, archive_bytes, archive_sha256 = _decode_package(value)
        _, counts = _archive_members(archive_bytes)
    except RelayForgeServiceError as exc:
        rejection_id = re.sub(r"[^A-Za-z0-9._-]+", "-", request_id).strip("-") or "invalid"
        rejection = {
            "schema": "battle.v16.relayforge.package_rejection.v1",
            "target_id": TARGET_ID,
            "request_id": rejection_id[:64],
            "status": "REJECTED",
            "reason": exc.code,
            "request_sha256": hashlib.sha256(body).hexdigest(),
        }
        _write_json(paths.state_root / "rejections" / f"{rejection_id[:64]}.json", rejection)
        return exc.status, rejection

    job_root = paths.jobs_root / request_id
    if job_root.exists():
        shutil.rmtree(job_root)
    job_root.mkdir(parents=True, exist_ok=True)
    archive_path = job_root / "package.tar"
    archive_path.write_bytes(archive_bytes)
    request_record = {
        "schema": PACKAGE_SCHEMA,
        "request_id": request_id,
        "tenant_id": tenant_id,
        "archive_sha256": archive_sha256,
        "package_name": str(value.get("package_name") or "package.tar"),
    }
    _write_json(job_root / "request.json", request_record)
    package_observation = {
        "schema": "battle.v16.relayforge.public_observation.v1",
        "target_id": TARGET_ID,
        "observation_id": "OBS-10",
        "request_id": request_id,
        "status_code": 202,
        "object_class_counts": counts,
        "opaque_input_identity_sha256": archive_sha256,
        "opaque_output_identity_sha256": hashlib.sha256(
            f"job:{request_id}".encode("utf-8")
        ).hexdigest(),
        "functional_result": "VALID_PACKAGE",
    }
    _write_json(job_root / "package-observation.json", package_observation)
    if use_network_extractor:
        extraction_status, extraction_payload = _forward_json(
            "http://extract-worker:8080/internal/extract",
            canonical_bytes(
                {
                    "job_id": request_id,
                    "archive_path": str(archive_path),
                    "archive_sha256": archive_sha256,
                }
            ),
            {},
        )
        if extraction_status not in {200, 409}:
            raise RelayForgeServiceError(
                status=HTTPStatus.SERVICE_UNAVAILABLE,
                code="extract_worker_unavailable",
                detail="extract-worker did not produce a bounded extraction result",
            )
        extraction = extraction_payload
    else:
        extraction = _extract_job(
            paths=paths,
            job_id=request_id,
            archive_path=archive_path,
            archive_sha256=archive_sha256,
        )
    status = extraction["private"]["status"]
    job_status = {
        "schema": "battle.v16.relayforge.job_status.v1",
        "target_id": TARGET_ID,
        "job_id": request_id,
        "tenant_id": tenant_id,
        "status": status,
        "observations": [package_observation, extraction["public"]],
        "capability_material": _job_capability_material(
            paths, job_id=request_id, tenant_id=tenant_id
        ),
    }
    _write_json(job_root / "status.json", job_status)
    http_status = HTTPStatus.CREATED if status == "COMPLETED" else HTTPStatus.CONFLICT
    return http_status, job_status


def _owned_job(paths: ArenaPaths, job_id: str, tenant_id: str) -> dict[str, Any]:
    status_path = paths.jobs_root / job_id / "status.json"
    if not status_path.is_file():
        raise RelayForgeServiceError(
            status=HTTPStatus.NOT_FOUND,
            code="job_not_found",
            detail="job does not exist",
        )
    status = _read_json(status_path)
    if status.get("tenant_id") != tenant_id:
        raise RelayForgeServiceError(
            status=HTTPStatus.NOT_FOUND,
            code="job_not_found",
            detail="job does not exist",
        )
    return status


def _tenant_header(headers: Mapping[str, str]) -> str:
    tenant_id = headers.get("x-relayforge-tenant", "")
    if not TENANT_ID_RE.fullmatch(tenant_id):
        raise RelayForgeServiceError(
            status=HTTPStatus.UNAUTHORIZED,
            code="tenant_required",
            detail="x-relayforge-tenant is required",
        )
    return tenant_id


def _rf_b_manifest(paths: ArenaPaths) -> dict[str, Any]:
    if not paths.rf_b_private_manifest_path.is_file():
        raise RelayForgeServiceError(
            status=HTTPStatus.SERVICE_UNAVAILABLE,
            code="rf_b_not_seeded",
            detail="the deterministic report-cache state has not been reset",
        )
    return _read_json(paths.rf_b_private_manifest_path)


def _report_entry(paths: ArenaPaths, reference: str) -> dict[str, Any]:
    if not REPORT_REFERENCE_RE.fullmatch(reference):
        raise RelayForgeServiceError(
            status=HTTPStatus.NOT_FOUND,
            code="report_not_found",
            detail="report does not exist",
        )
    entry_path = paths.report_entries_root / f"{reference}.json"
    if not entry_path.is_file():
        raise RelayForgeServiceError(
            status=HTTPStatus.NOT_FOUND,
            code="report_not_found",
            detail="report does not exist",
        )
    return _read_json(entry_path)


def _rf_b_observation_path(paths: ArenaPaths, tenant_id: str, observation_id: str) -> Path:
    return paths.rf_b_observations_root / f"{tenant_id}-{observation_id.lower()}.json"


def process_owned_cached_report(*, paths: ArenaPaths, tenant_id: str) -> tuple[int, dict[str, Any]]:
    manifest = _rf_b_manifest(paths)
    reference_key = "owned_reference" if tenant_id == "tenant-red" else "victim_reference"
    reference = str(manifest.get(reference_key) or "")
    entry = _report_entry(paths, reference)
    if entry.get("owner_tenant_id") != tenant_id:
        raise RelayForgeServiceError(
            status=HTTPStatus.NOT_FOUND,
            code="report_not_found",
            detail="report does not exist",
        )
    observation = {
        "schema": "battle.v16.relayforge.public_observation.v1",
        "target_id": TARGET_ID,
        "observation_id": "OBS-20",
        "request_id": f"owned-report-{tenant_id}",
        "status_code": 200,
        "cache_result": "OWNED_HIT",
        "opaque_report_reference": reference,
        "opaque_output_identity_sha256": canonical_sha256(
            {"reference": reference, "representation": "report-json"}
        ),
        "functional_result": "TENANT_OWNED_REPORT_RETRIEVED",
    }
    _write_json(_rf_b_observation_path(paths, tenant_id, "OBS-20"), observation)
    return HTTPStatus.OK, {
        **dict(entry["report"]),
        "opaque_report_reference": reference,
        "cache_result": "OWNED_HIT",
        "observation": observation,
    }


def process_recent_report_observation(*, paths: ArenaPaths, tenant_id: str) -> tuple[int, dict[str, Any]]:
    obs20_path = _rf_b_observation_path(paths, tenant_id, "OBS-20")
    if not obs20_path.is_file():
        raise RelayForgeServiceError(
            status=HTTPStatus.CONFLICT,
            code="owned_report_observation_required",
            detail="retrieve the normal tenant-owned report before recent report metadata",
        )
    obs20 = _read_json(obs20_path)
    manifest = _rf_b_manifest(paths)
    reference = str(manifest["victim_reference"])
    observation = {
        "schema": "battle.v16.relayforge.public_observation.v1",
        "target_id": TARGET_ID,
        "observation_id": "OBS-21",
        "request_id": f"recent-report-{tenant_id}",
        "status_code": 200,
        "cache_result": "SEEDED_RECENT_REFERENCE",
        "opaque_report_reference": reference,
        "opaque_owner_identity_sha256": hashlib.sha256(
            str(manifest["victim_owner_tenant_id"]).encode("utf-8")
        ).hexdigest(),
        "source_observation_sha256": canonical_sha256(obs20),
        "functional_result": "RECENT_REPORT_REFERENCE_OBSERVED",
    }
    _write_json(_rf_b_observation_path(paths, tenant_id, "OBS-21"), observation)
    return HTTPStatus.OK, observation


def process_cached_report_reference(
    *, paths: ArenaPaths, tenant_id: str, reference: str
) -> tuple[int, dict[str, Any]]:
    entry = _report_entry(paths, reference)
    owner = str(entry.get("owner_tenant_id") or "")
    cross_principal = owner != tenant_id
    manifest = _rf_b_manifest(paths)
    obs21_path = _rf_b_observation_path(paths, tenant_id, "OBS-21")
    seeded_observation_present = bool(
        obs21_path.is_file()
        and reference == manifest.get("victim_reference")
        and _read_json(obs21_path).get("opaque_report_reference") == reference
    )
    broad_enabled = broad_quarantine_enabled(paths)
    defense_enabled = cache_principal_partition_defense_enabled(paths) or broad_enabled
    allowed = not cross_principal or (seeded_observation_present and not defense_enabled)
    access = {
        "schema": "battle.v16.relayforge.rf_b_access_receipt.v1",
        "target_id": TARGET_ID,
        "reference": reference,
        "requested_tenant_id": tenant_id,
        "owner_tenant_id": owner,
        "cross_principal": cross_principal,
        "seeded_observation_present": seeded_observation_present,
        "defense_enabled": defense_enabled,
        "broad_quarantine_enabled": broad_enabled,
        "cache_identity_fields": [
            "authenticated_principal",
            "owner_tenant_id",
            "reference",
        ]
        if defense_enabled
        else ["reference"],
        "decision": "RETURNED" if allowed else "DENIED",
        "http_status": 200 if allowed else 404,
        "report_sha256": canonical_sha256(entry.get("report")),
        "returned_report": dict(entry["report"]) if allowed else None,
    }
    _write_json(paths.rf_b_access_root / f"{tenant_id}-{reference}.json", access)
    if not allowed:
        raise RelayForgeServiceError(
            status=HTTPStatus.NOT_FOUND,
            code="report_not_found",
            detail="report does not exist",
        )
    return HTTPStatus.OK, {
        **dict(entry["report"]),
        "opaque_report_reference": reference,
        "cache_result": "HIT",
    }



def _rf_c_manifest(paths: ArenaPaths) -> dict[str, Any]:
    if not paths.rf_c_private_manifest_path.is_file():
        raise RelayForgeServiceError(
            status=HTTPStatus.SERVICE_UNAVAILABLE,
            code="rf_c_not_seeded",
            detail="the deterministic preview and renderer state has not been reset",
        )
    return _read_json(paths.rf_c_private_manifest_path)


def _job_capability_material(paths: ArenaPaths, *, job_id: str, tenant_id: str) -> dict[str, Any]:
    manifest = _rf_c_manifest(paths)
    material = {
        "preview_path": f"/api/v1/jobs/{job_id}/preview",
        "report_profile_path": f"/api/v1/jobs/{job_id}/report-profile",
        "preview_locator": str(manifest["public_preview_locator"]),
        "report_profile_alias": str(manifest["observed_profile_alias"]),
        "principal_identity_sha256": hashlib.sha256(tenant_id.encode("utf-8")).hexdigest(),
    }
    return {**material, "capability_material_sha256": canonical_sha256(material)}


def _rf_c_preview_receipt_path(paths: ArenaPaths, *, tenant_id: str, job_id: str) -> Path:
    return paths.rf_c_preview_root / f"{tenant_id}-{job_id}.json"


def _rf_c_observation_path(paths: ArenaPaths, *, tenant_id: str, job_id: str) -> Path:
    return paths.rf_c_observations_root / f"{tenant_id}-{job_id}-obs-30.json"


def _token_payload_b64(claims: Mapping[str, Any]) -> str:
    return base64.urlsafe_b64encode(canonical_bytes(dict(claims))).decode("ascii").rstrip("=")


def _token_signature(*, payload: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).hexdigest()


def _issue_renderer_capability(
    *, paths: ArenaPaths, tenant_id: str, job_id: str, preview_receipt_sha256: str
) -> dict[str, Any]:
    manifest = _rf_c_manifest(paths)
    preview_path = _rf_c_preview_receipt_path(paths, tenant_id=tenant_id, job_id=job_id)
    if not preview_path.is_file() or file_sha256(preview_path) != preview_receipt_sha256:
        raise RelayForgeServiceError(
            status=HTTPStatus.FORBIDDEN,
            code="preview_evidence_required",
            detail="capability issuance requires the completed preview evidence chain",
        )
    preview = _read_json(preview_path)
    if preview.get("status") != "INTERNAL_DISPATCH_REACHED":
        raise RelayForgeServiceError(
            status=HTTPStatus.FORBIDDEN,
            code="preview_evidence_required",
            detail="capability issuance requires the completed preview evidence chain",
        )
    strict = capability_audience_policy_enabled(paths)
    profile_alias = str(
        manifest["safe_profile_alias"] if strict else manifest["observed_profile_alias"]
    )
    operation = RF_C_SAFE_OPERATION if strict else RF_C_OPERATION
    issued_at = _logical_time(paths)
    claims = {
        "capability_id": canonical_sha256(
            {
                "seed": manifest["seed"],
                "tenant_id": tenant_id,
                "job_id": job_id,
                "preview_receipt_sha256": preview_receipt_sha256,
                "profile_alias": profile_alias,
            }
        ),
        "principal": tenant_id,
        "audience": RF_C_AUDIENCE,
        "scope": f"report-profile:{profile_alias}",
        "operation": operation,
        "issued_at": issued_at,
        "expires_at": issued_at + 2,
        "single_use": True,
        "job_id": job_id,
        "profile_alias": profile_alias,
        "preview_receipt_sha256": preview_receipt_sha256,
    }
    payload = _token_payload_b64(claims)
    token = f"{payload}.{_token_signature(payload=payload, secret=str(manifest['capability_secret']))}"
    token_sha256 = hashlib.sha256(token.encode("utf-8")).hexdigest()
    record = {
        "schema": "battle.v16.relayforge.renderer_capability_receipt.v1",
        "target_id": TARGET_ID,
        "token_sha256": token_sha256,
        "claims": claims,
        "used": False,
        "use_count": 0,
        "policy_enabled": strict,
    }
    _write_json(paths.rf_c_capabilities_root / f"{token_sha256}.json", record)
    return {
        "token": token,
        "token_sha256": token_sha256,
        "audience": claims["audience"],
        "scope": claims["scope"],
        "operation": claims["operation"],
        "expires_at": claims["expires_at"],
        "profile_alias": claims["profile_alias"],
    }


def process_preview_request(
    *,
    paths: ArenaPaths,
    tenant_id: str,
    job_id: str,
    body: bytes,
    use_network_broker: bool = False,
) -> tuple[int, dict[str, Any]]:
    _owned_job(paths, job_id, tenant_id)
    if broad_quarantine_enabled(paths):
        raise RelayForgeServiceError(
            status=HTTPStatus.SERVICE_UNAVAILABLE,
            code="remote_preview_quarantined",
            detail="remote preview is unavailable under the active service policy",
        )
    value = _json_body(body)
    url = str(value.get("url") or "")
    material = _job_capability_material(paths, job_id=job_id, tenant_id=tenant_id)
    initial_fingerprint = hashlib.sha256(url.encode("utf-8")).hexdigest()
    if url in {RF_C_SAFE_PREVIEW_URL, "https://public.example/preview/fixture"}:
        observation = {
            "schema": "battle.v16.relayforge.public_observation.v1",
            "target_id": TARGET_ID,
            "observation_id": "OBS-30",
            "request_id": f"rf-c-preview-{job_id}",
            "status_code": 200,
            "redirect_hop_count": 1,
            "opaque_initial_destination_sha256": initial_fingerprint,
            "opaque_final_destination_sha256": hashlib.sha256(
                b"https://cdn.public.example/preview/safe"
            ).hexdigest(),
            "functional_result": "EXTERNAL_PREVIEW_COMPLETED",
        }
        _write_json(
            _rf_c_observation_path(paths, tenant_id=tenant_id, job_id=job_id), observation
        )
        return HTTPStatus.OK, {
            "schema": "battle.v16.relayforge.preview_result.v1",
            "target_id": TARGET_ID,
            "job_id": job_id,
            "redirect_hop_count": 1,
            "preview_sha256": canonical_sha256(observation),
            "observation": observation,
        }
    if url != material["preview_locator"]:
        raise RelayForgeServiceError(
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="preview_locator_not_observed",
            detail="preview request must use capability material from the authenticated import",
        )
    final_private_url = "http://capability-broker:8080/internal/capabilities/renderer"
    private_receipt = {
        "schema": "battle.v16.relayforge.private_preview_chain_receipt.v1",
        "target_id": TARGET_ID,
        "tenant_id": tenant_id,
        "job_id": job_id,
        "hop_count": 2,
        "initial_url": url,
        "redirect_url": "https://redirector.public.example/relayforge",
        "final_url": final_private_url,
        "initial_destination_sha256": initial_fingerprint,
        "final_destination_sha256": hashlib.sha256(final_private_url.encode("utf-8")).hexdigest(),
        "status": "DESTINATION_POLICY_BLOCKED"
        if preview_destination_policy_enabled(paths)
        else "INTERNAL_DISPATCH_REACHED",
    }
    preview_path = _write_json(
        _rf_c_preview_receipt_path(paths, tenant_id=tenant_id, job_id=job_id),
        private_receipt,
    )
    observation = {
        "schema": "battle.v16.relayforge.public_observation.v1",
        "target_id": TARGET_ID,
        "observation_id": "OBS-30",
        "request_id": f"rf-c-preview-{job_id}",
        "status_code": 422 if preview_destination_policy_enabled(paths) else 200,
        "redirect_hop_count": 2,
        "opaque_initial_destination_sha256": private_receipt["initial_destination_sha256"],
        "opaque_final_destination_sha256": private_receipt["final_destination_sha256"],
        "functional_result": private_receipt["status"],
    }
    _write_json(
        _rf_c_observation_path(paths, tenant_id=tenant_id, job_id=job_id), observation
    )
    if preview_destination_policy_enabled(paths):
        return HTTPStatus.UNPROCESSABLE_ENTITY, {
            "schema": "battle.v16.relayforge.preview_result.v1",
            "target_id": TARGET_ID,
            "job_id": job_id,
            "status": "DESTINATION_POLICY_BLOCKED",
            "observation": observation,
        }
    if use_network_broker:
        broker_status, broker_response = _forward_json(
            "http://capability-broker:8080/internal/capabilities/renderer",
            canonical_bytes(
                {
                    "tenant_id": tenant_id,
                    "job_id": job_id,
                    "preview_receipt_sha256": file_sha256(preview_path),
                }
            ),
            {"x-relayforge-internal-source": "preview-fetcher"},
        )
        if broker_status != 200 or not isinstance(broker_response.get("capability"), dict):
            raise RelayForgeServiceError(
                status=HTTPStatus.SERVICE_UNAVAILABLE,
                code="capability_broker_unavailable",
                detail="capability issuance did not complete",
            )
        capability = dict(broker_response["capability"])
    else:
        capability = _issue_renderer_capability(
            paths=paths,
            tenant_id=tenant_id,
            job_id=job_id,
            preview_receipt_sha256=file_sha256(preview_path),
        )
    return HTTPStatus.OK, {
        "schema": "battle.v16.relayforge.preview_result.v1",
        "target_id": TARGET_ID,
        "job_id": job_id,
        "status": "CAPABILITY_ISSUED",
        "observation": observation,
        "capability": capability,
    }


def _decode_and_validate_capability(
    *,
    paths: ArenaPaths,
    token: str,
    tenant_id: str,
    audience: str,
    scope: str,
    operation: str,
    profile_alias: str,
) -> tuple[dict[str, Any], Path]:
    if not CAPABILITY_TOKEN_RE.fullmatch(token):
        raise RelayForgeServiceError(
            status=HTTPStatus.NOT_FOUND,
            code="capability_not_found",
            detail="capability is unavailable",
        )
    payload, signature = token.rsplit(".", 1)
    manifest = _rf_c_manifest(paths)
    expected = _token_signature(payload=payload, secret=str(manifest["capability_secret"]))
    if not hmac.compare_digest(signature, expected):
        raise RelayForgeServiceError(
            status=HTTPStatus.NOT_FOUND,
            code="capability_not_found",
            detail="capability is unavailable",
        )
    try:
        padded = payload + "=" * ((4 - len(payload) % 4) % 4)
        claims = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RelayForgeServiceError(
            status=HTTPStatus.NOT_FOUND,
            code="capability_not_found",
            detail="capability is unavailable",
        ) from exc
    if not isinstance(claims, dict):
        raise RelayForgeServiceError(
            status=HTTPStatus.NOT_FOUND,
            code="capability_not_found",
            detail="capability is unavailable",
        )
    token_sha256 = hashlib.sha256(token.encode("utf-8")).hexdigest()
    record_path = paths.rf_c_capabilities_root / f"{token_sha256}.json"
    if not record_path.is_file():
        raise RelayForgeServiceError(
            status=HTTPStatus.NOT_FOUND,
            code="capability_not_found",
            detail="capability is unavailable",
        )
    record = _read_json(record_path)
    requested = {
        "principal": tenant_id,
        "audience": audience,
        "scope": scope,
        "operation": operation,
        "profile_alias": profile_alias,
    }
    for key, value in requested.items():
        if claims.get(key) != value:
            raise RelayForgeServiceError(
                status=HTTPStatus.FORBIDDEN,
                code="capability_binding_mismatch",
                detail="capability is not valid for this request",
            )
    if record.get("claims") != claims or record.get("used") is True:
        raise RelayForgeServiceError(
            status=HTTPStatus.FORBIDDEN,
            code="capability_unavailable",
            detail="capability is not valid for this request",
        )
    if int(claims.get("expires_at", -1)) <= _logical_time(paths):
        raise RelayForgeServiceError(
            status=HTTPStatus.FORBIDDEN,
            code="capability_expired",
            detail="capability is not valid for this request",
        )
    preview_path = _rf_c_preview_receipt_path(
        paths, tenant_id=tenant_id, job_id=str(claims.get("job_id") or "")
    )
    if not preview_path.is_file() or file_sha256(preview_path) != claims.get(
        "preview_receipt_sha256"
    ):
        raise RelayForgeServiceError(
            status=HTTPStatus.FORBIDDEN,
            code="preview_evidence_required",
            detail="capability is not valid for this request",
        )
    record["used"] = True
    record["use_count"] = int(record.get("use_count", 0)) + 1
    _write_json(record_path, record)
    return claims, record_path


def process_renderer_request(
    *, paths: ArenaPaths, tenant_id: str, job_id: str, body: bytes
) -> tuple[int, dict[str, Any]]:
    _owned_job(paths, job_id, tenant_id)
    value = _json_body(body)
    token = str(value.get("capability_token") or "")
    profile_alias = str(value.get("profile_alias") or "")
    audience = str(value.get("audience") or "")
    scope = str(value.get("scope") or "")
    operation = str(value.get("operation") or "")
    claims, record_path = _decode_and_validate_capability(
        paths=paths,
        token=token,
        tenant_id=tenant_id,
        audience=audience,
        scope=scope,
        operation=operation,
        profile_alias=profile_alias,
    )
    manifest = _rf_c_manifest(paths)
    resource_value = manifest.get("alias_resources", {}).get(profile_alias)
    if not isinstance(resource_value, str):
        raise RelayForgeServiceError(
            status=HTTPStatus.NOT_FOUND,
            code="profile_not_found",
            detail="report profile is unavailable",
        )
    resource = Path(resource_value).resolve(strict=False)
    if renderer_resource_policy_enabled(paths) and not _is_within(
        resource, paths.rf_c_safe_profiles_root
    ):
        decision = "DENIED_FINAL_RESOURCE_OUTSIDE_PROFILE_ROOT"
        allowed = False
    else:
        decision = "RETURNED"
        allowed = resource.is_file()
    token_sha256 = hashlib.sha256(token.encode("utf-8")).hexdigest()
    attempt_index = len(list(paths.rf_c_renderer_root.glob(f"{token_sha256}-*.json"))) + 1
    access = {
        "schema": "battle.v16.relayforge.renderer_access_receipt.v1",
        "target_id": TARGET_ID,
        "job_id": job_id,
        "tenant_id": tenant_id,
        "token_sha256": token_sha256,
        "capability_record_sha256": file_sha256(record_path),
        "claims": claims,
        "requested_profile_alias": profile_alias,
        "resolved_resource_identity_sha256": hashlib.sha256(
            str(resource).encode("utf-8")
        ).hexdigest(),
        "renderer_resource_policy_enabled": renderer_resource_policy_enabled(paths),
        "decision": decision if allowed else decision,
        "http_status": 200 if allowed else 404,
        "returned_resource_sha256": file_sha256(resource) if allowed else None,
        "sink_hashes_after": sink_hashes(paths),
    }
    if allowed:
        resource_payload = _read_json(resource)
        access["returned_resource"] = resource_payload
    else:
        access["returned_resource"] = None
    _write_json(
        paths.rf_c_renderer_root / f"{token_sha256}-{attempt_index:03d}.json", access
    )
    advance_logical_clock(
        steps=1, state_root=paths.state_root, sink_root=paths.sink_root
    )
    if not allowed:
        raise RelayForgeServiceError(
            status=HTTPStatus.NOT_FOUND,
            code="profile_not_found",
            detail="report profile is unavailable",
        )
    response = {
        "schema": "battle.v16.relayforge.profile_result.v1",
        "target_id": TARGET_ID,
        "job_id": job_id,
        "profile_alias": profile_alias,
        "render_sha256": canonical_sha256(resource_payload),
    }
    if resource == paths.sink_file("RF-C-SINK").resolve():
        response["protected_canary"] = resource_payload.get("protected_canary")
    else:
        response["profile"] = resource_payload.get("profile")
    return HTTPStatus.OK, response


def _functional_response(
    *,
    paths: ArenaPaths,
    method: str,
    path: str,
    headers: Mapping[str, str],
    body: bytes,
) -> tuple[int, dict[str, Any]] | None:
    job_match = re.fullmatch(r"/api/v1/jobs/([A-Za-z0-9._-]{1,64})", path)
    report_match = re.fullmatch(
        r"/api/v1/jobs/([A-Za-z0-9._-]{1,64})/report", path
    )
    preview_match = re.fullmatch(
        r"/api/v1/jobs/([A-Za-z0-9._-]{1,64})/preview", path
    )
    profile_match = re.fullmatch(
        r"/api/v1/jobs/([A-Za-z0-9._-]{1,64})/report-profile", path
    )
    if method == "GET" and job_match:
        tenant_id = _tenant_header(headers)
        return HTTPStatus.OK, _owned_job(paths, job_match.group(1), tenant_id)
    if method == "GET" and report_match:
        tenant_id = _tenant_header(headers)
        status = _owned_job(paths, report_match.group(1), tenant_id)
        report = {
            "schema": "battle.v16.relayforge.tenant_report.v1",
            "target_id": TARGET_ID,
            "job_id": status["job_id"],
            "tenant_id": tenant_id,
            "report_sha256": canonical_sha256(
                {"job_id": status["job_id"], "tenant_id": tenant_id, "status": status["status"]}
            ),
        }
        return HTTPStatus.OK, report
    if method == "POST" and preview_match:
        tenant_id = _tenant_header(headers)
        return process_preview_request(
            paths=paths, tenant_id=tenant_id, job_id=preview_match.group(1), body=body
        )
    if method == "POST" and profile_match:
        tenant_id = _tenant_header(headers)
        _owned_job(paths, profile_match.group(1), tenant_id)
        if broad_quarantine_enabled(paths):
            raise RelayForgeServiceError(
                status=HTTPStatus.SERVICE_UNAVAILABLE,
                code="custom_report_profiles_quarantined",
                detail="custom report profiles are unavailable under the active service policy",
            )
        value = _json_body(body)
        if value.get("profile") == "summary-safe":
            return HTTPStatus.OK, {
                "schema": "battle.v16.relayforge.profile_result.v1",
                "target_id": TARGET_ID,
                "job_id": profile_match.group(1),
                "profile": "summary-safe",
                "render_sha256": canonical_sha256(
                    {"job_id": profile_match.group(1), "profile": "summary-safe"}
                ),
            }
        return process_renderer_request(
            paths=paths, tenant_id=tenant_id, job_id=profile_match.group(1), body=body
        )
    return None


def _forward_request(
    *,
    url: str,
    method: str,
    body: bytes = b"",
    headers: Mapping[str, str],
) -> tuple[int, dict[str, Any]]:
    request_headers: dict[str, str] = {}
    if body:
        request_headers["content-type"] = "application/json"
    for name in (
        "x-relayforge-tenant",
        "x-relayforge-team",
        "x-relayforge-internal-source",
    ):
        if name in headers:
            request_headers[name] = headers[name]
    request = urllib.request.Request(
        url, data=body if body else None, headers=request_headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return int(response.status), json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return int(exc.code), json.loads(exc.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return HTTPStatus.SERVICE_UNAVAILABLE, {
            "schema": "battle.v16.relayforge.error.v1",
            "status": "BLOCKED",
            "target_id": TARGET_ID,
            "reason": "internal_service_unavailable",
            "detail_sha256": hashlib.sha256(str(exc).encode("utf-8")).hexdigest(),
        }


def _forward_json(url: str, body: bytes, headers: Mapping[str, str]) -> tuple[int, dict[str, Any]]:
    return _forward_request(url=url, method="POST", body=body, headers=headers)


def response_for(
    *,
    role: str,
    method: str,
    path: str,
    body: bytes = b"",
    headers: Mapping[str, str] | None = None,
    state_root: Path | None = None,
    sink_root: Path | None = None,
) -> tuple[int, dict[str, Any]]:
    """Return one deterministic service response."""

    request_headers = {str(key).casefold(): str(value) for key, value in (headers or {}).items()}
    paths = ArenaPaths.resolve(state_root=state_root, sink_root=sink_root)
    try:
        if path == "/healthz" and method == "GET":
            return HTTPStatus.OK, {
                "schema": "battle.v16.relayforge.service_health.v1",
                "status": "READY",
                "target_id": TARGET_ID,
                "role": role,
                "implementation_status": IMPLEMENTATION_STATUS,
            }

        if role == "edge-gateway" and method == "GET" and path == "/api/v1/status":
            return HTTPStatus.OK, {
                "schema": "battle.v16.relayforge.public_status.v1",
                "status": "DETERMINISTIC_SECURITY_COMPLETE",
                "target_id": TARGET_ID,
                "public_entry_point": "POST /api/v1/jobs/import",
                "owned_report_path": "/api/v1/reports/owned",
                "recent_report_path": "/api/v1/status/recent",
                "qualification_eligible": False,
            }

        rf_b_report_match = re.fullmatch(r"/api/v1/reports/([0-9a-f]{64})", path)
        rf_c_preview_match = re.fullmatch(
            r"/api/v1/jobs/([A-Za-z0-9._-]{1,64})/preview", path
        )
        rf_c_profile_match = re.fullmatch(
            r"/api/v1/jobs/([A-Za-z0-9._-]{1,64})/report-profile", path
        )
        local_dispatch = os.environ.get("RELAYFORGE_LOCAL_DISPATCH") == "1" or state_root is not None

        if role == "edge-gateway" and method == "POST" and rf_c_preview_match and not local_dispatch:
            tenant_id = _tenant_header(request_headers)
            return _forward_json(
                "http://preview-fetcher:8080/internal/preview",
                canonical_bytes(
                    {
                        "tenant_id": tenant_id,
                        "job_id": rf_c_preview_match.group(1),
                        "request": _json_body(body),
                    }
                ),
                {"x-relayforge-internal-source": "edge-gateway"},
            )

        if role == "edge-gateway" and method == "POST" and rf_c_profile_match and not local_dispatch:
            tenant_id = _tenant_header(request_headers)
            if broad_quarantine_enabled(paths):
                raise RelayForgeServiceError(
                    status=HTTPStatus.SERVICE_UNAVAILABLE,
                    code="custom_report_profiles_quarantined",
                    detail="custom report profiles are unavailable under the active service policy",
                )
            value = _json_body(body)
            if value.get("profile") == "summary-safe":
                return HTTPStatus.OK, {
                    "schema": "battle.v16.relayforge.profile_result.v1",
                    "target_id": TARGET_ID,
                    "job_id": rf_c_profile_match.group(1),
                    "profile": "summary-safe",
                    "render_sha256": canonical_sha256(
                        {
                            "job_id": rf_c_profile_match.group(1),
                            "profile": "summary-safe",
                        }
                    ),
                }
            return _forward_json(
                "http://document-renderer:8080/internal/render/profile",
                canonical_bytes(
                    {
                        "tenant_id": tenant_id,
                        "job_id": rf_c_profile_match.group(1),
                        "request": value,
                    }
                ),
                {"x-relayforge-internal-source": "edge-gateway"},
            )

        if role == "preview-fetcher" and method == "POST" and path == "/internal/preview":
            if request_headers.get("x-relayforge-internal-source") != "edge-gateway":
                raise RelayForgeServiceError(
                    status=HTTPStatus.FORBIDDEN,
                    code="gateway_dispatch_required",
                    detail="preview operation is unavailable",
                )
            value = _json_body(body)
            return process_preview_request(
                paths=paths,
                tenant_id=str(value.get("tenant_id") or ""),
                job_id=str(value.get("job_id") or ""),
                body=canonical_bytes(value.get("request") or {}),
                use_network_broker=True,
            )

        if role == "edge-gateway" and method == "GET" and path == "/api/v1/reports/owned":
            tenant_id = _tenant_header(request_headers)
            if local_dispatch:
                return process_owned_cached_report(paths=paths, tenant_id=tenant_id)
            return _forward_request(
                url="http://report-cache:8080/internal/cache/reports/owned",
                method="GET",
                headers=request_headers,
            )

        if role == "edge-gateway" and method == "GET" and path == "/api/v1/status/recent":
            tenant_id = _tenant_header(request_headers)
            if local_dispatch:
                return process_recent_report_observation(paths=paths, tenant_id=tenant_id)
            return _forward_request(
                url="http://report-cache:8080/internal/cache/status/recent",
                method="GET",
                headers=request_headers,
            )

        if role == "edge-gateway" and method == "GET" and rf_b_report_match:
            tenant_id = _tenant_header(request_headers)
            reference = rf_b_report_match.group(1)
            if local_dispatch:
                return process_cached_report_reference(
                    paths=paths, tenant_id=tenant_id, reference=reference
                )
            return _forward_request(
                url=f"http://report-cache:8080/internal/cache/reports/{reference}",
                method="GET",
                headers=request_headers,
            )

        if role == "report-cache" and method == "GET" and path == "/internal/cache/reports/owned":
            return process_owned_cached_report(
                paths=paths, tenant_id=_tenant_header(request_headers)
            )

        if role == "report-cache" and method == "GET" and path == "/internal/cache/status/recent":
            return process_recent_report_observation(
                paths=paths, tenant_id=_tenant_header(request_headers)
            )

        internal_rf_b_match = re.fullmatch(r"/internal/cache/reports/([0-9a-f]{64})", path)
        if role == "report-cache" and method == "GET" and internal_rf_b_match:
            return process_cached_report_reference(
                paths=paths,
                tenant_id=_tenant_header(request_headers),
                reference=internal_rf_b_match.group(1),
            )

        if role == "edge-gateway" and method == "POST" and path == "/api/v1/jobs/import":
            if os.environ.get("RELAYFORGE_LOCAL_DISPATCH") == "1" or state_root is not None:
                return process_package_import(
                    body=body, state_root=paths.state_root, sink_root=paths.sink_root
                )
            return _forward_json(
                "http://package-api:8080/internal/jobs/import", body, request_headers
            )

        if role == "package-api" and method == "POST" and path == "/internal/jobs/import":
            return process_package_import(
                body=body,
                state_root=paths.state_root,
                sink_root=paths.sink_root,
                use_network_extractor=os.environ.get("RELAYFORGE_LOCAL_DISPATCH") != "1",
            )

        if role == "extract-worker" and method == "POST" and path == "/internal/extract":
            value = _json_body(body)
            job_id = str(value.get("job_id") or "")
            archive_path = Path(str(value.get("archive_path") or ""))
            archive_sha256 = str(value.get("archive_sha256") or "")
            if not REQUEST_ID_RE.fullmatch(job_id):
                raise RelayForgeServiceError(
                    status=HTTPStatus.UNPROCESSABLE_ENTITY,
                    code="invalid_job_id",
                    detail="job_id must be a bounded stable identifier",
                )
            expected_root = paths.jobs_root / job_id
            try:
                archive_path.resolve().relative_to(expected_root.resolve())
            except ValueError as exc:
                raise RelayForgeServiceError(
                    status=HTTPStatus.FORBIDDEN,
                    code="archive_path_outside_job",
                    detail="extract-worker accepts only the validated job archive",
                ) from exc
            extraction = _extract_job(
                paths=paths,
                job_id=job_id,
                archive_path=archive_path,
                archive_sha256=archive_sha256,
            )
            status = extraction["private"]["status"]
            return (HTTPStatus.OK if status == "COMPLETED" else HTTPStatus.CONFLICT), extraction

        if role == "edge-gateway" and method == "POST" and path == "/api/v1/defenses/extractor-object-identity":
            if request_headers.get("x-relayforge-team") != "blue":
                raise RelayForgeServiceError(
                    status=HTTPStatus.FORBIDDEN,
                    code="blue_authority_required",
                    detail="the extractor identity control is a Blue action",
                )
            value = _json_body(body)
            if not isinstance(value.get("enabled"), bool):
                raise RelayForgeServiceError(
                    status=HTTPStatus.UNPROCESSABLE_ENTITY,
                    code="enabled_boolean_required",
                    detail="enabled must be boolean",
                )
            policy = set_extractor_identity_defense(
                enabled=bool(value["enabled"]),
                state_root=paths.state_root,
                sink_root=paths.sink_root,
            )
            return HTTPStatus.OK, policy

        if role == "edge-gateway" and method == "POST" and path == "/api/v1/defenses/cache-principal-partition":
            if request_headers.get("x-relayforge-team") != "blue":
                raise RelayForgeServiceError(
                    status=HTTPStatus.FORBIDDEN,
                    code="blue_authority_required",
                    detail="the cache principal partition control is a Blue action",
                )
            value = _json_body(body)
            if not isinstance(value.get("enabled"), bool):
                raise RelayForgeServiceError(
                    status=HTTPStatus.UNPROCESSABLE_ENTITY,
                    code="enabled_boolean_required",
                    detail="enabled must be boolean",
                )
            policy = set_cache_principal_partition_defense(
                enabled=bool(value["enabled"]),
                state_root=paths.state_root,
                sink_root=paths.sink_root,
            )
            return HTTPStatus.OK, policy

        rf_c_defenses = {
            "/api/v1/defenses/redirect-destination-policy": set_preview_destination_policy,
            "/api/v1/defenses/capability-audience-policy": set_capability_audience_policy,
            "/api/v1/defenses/renderer-resource-policy": set_renderer_resource_policy,
        }
        if role == "edge-gateway" and method == "POST" and path in rf_c_defenses:
            if request_headers.get("x-relayforge-team") != "blue":
                raise RelayForgeServiceError(
                    status=HTTPStatus.FORBIDDEN,
                    code="blue_authority_required",
                    detail="the requested RF-C control is a Blue action",
                )
            value = _json_body(body)
            if not isinstance(value.get("enabled"), bool):
                raise RelayForgeServiceError(
                    status=HTTPStatus.UNPROCESSABLE_ENTITY,
                    code="enabled_boolean_required",
                    detail="enabled must be boolean",
                )
            policy = rf_c_defenses[path](
                enabled=bool(value["enabled"]),
                state_root=paths.state_root,
                sink_root=paths.sink_root,
            )
            return HTTPStatus.OK, policy

        broad_controls = {
            "/api/v1/defenses/broad-quarantine": set_broad_quarantine,
            "/api/v1/defenses/legacy-convert-disable": set_legacy_convert_shutdown,
        }
        if role == "edge-gateway" and method == "POST" and path in broad_controls:
            if request_headers.get("x-relayforge-team") != "blue":
                raise RelayForgeServiceError(
                    status=HTTPStatus.FORBIDDEN,
                    code="blue_authority_required",
                    detail="the requested service-availability control is a Blue action",
                )
            value = _json_body(body)
            if not isinstance(value.get("enabled"), bool):
                raise RelayForgeServiceError(
                    status=HTTPStatus.UNPROCESSABLE_ENTITY,
                    code="enabled_boolean_required",
                    detail="enabled must be boolean",
                )
            policy = broad_controls[path](
                enabled=bool(value["enabled"]),
                state_root=paths.state_root,
                sink_root=paths.sink_root,
            )
            return HTTPStatus.OK, policy

        if role == "capability-broker" and method == "POST" and path == "/internal/capabilities/renderer":
            if request_headers.get("x-relayforge-internal-source") != "preview-fetcher":
                raise RelayForgeServiceError(
                    status=HTTPStatus.FORBIDDEN,
                    code="preview_chain_required",
                    detail="capability issuance is unavailable",
                )
            value = _json_body(body)
            capability = _issue_renderer_capability(
                paths=paths,
                tenant_id=str(value.get("tenant_id") or ""),
                job_id=str(value.get("job_id") or ""),
                preview_receipt_sha256=str(value.get("preview_receipt_sha256") or ""),
            )
            return HTTPStatus.OK, {"status": "CAPABILITY_ISSUED", "capability": capability}

        if role == "document-renderer" and method == "POST" and path == "/internal/render/profile":
            if request_headers.get("x-relayforge-internal-source") != "edge-gateway":
                raise RelayForgeServiceError(
                    status=HTTPStatus.FORBIDDEN,
                    code="gateway_dispatch_required",
                    detail="renderer operation is unavailable",
                )
            value = _json_body(body)
            return process_renderer_request(
                paths=paths,
                tenant_id=str(value.get("tenant_id") or ""),
                job_id=str(value.get("job_id") or ""),
                body=canonical_bytes(value.get("request") or {}),
            )

        if role == "edge-gateway" and method == "POST" and path == "/api/v1/legacy/convert":
            if local_dispatch:
                return process_legacy_conversion(paths=paths, body=body)
            return _forward_json(
                "http://legacy-convert:8080/internal/legacy/convert",
                body,
                {"x-relayforge-internal-source": "edge-gateway"},
            )

        if role == "legacy-convert" and method == "POST" and path == "/internal/legacy/convert":
            if request_headers.get("x-relayforge-internal-source") != "edge-gateway":
                raise RelayForgeServiceError(
                    status=HTTPStatus.FORBIDDEN,
                    code="gateway_dispatch_required",
                    detail="legacy conversion is available only through the public gateway",
                )
            return process_legacy_conversion(paths=paths, body=body)

        if role == "edge-gateway":
            functional = _functional_response(
                paths=paths,
                method=method,
                path=path,
                headers=request_headers,
                body=body,
            )
            if functional is not None:
                return functional

        if role == "judge-probe" and method == "POST" and path == "/judge/evaluate":
            return HTTPStatus.SERVICE_UNAVAILABLE, {
                "schema": "battle.v16.judge_outcome.v1",
                "status": "BLOCKED",
                "target_id": TARGET_ID,
                "reason": "invoke_the_private_judge_cli_for_measured_evaluation",
                "pass_emitted": False,
            }

        return HTTPStatus.NOT_FOUND, {
            "schema": "battle.v16.relayforge.error.v1",
            "status": "NOT_FOUND",
            "target_id": TARGET_ID,
            "role": role,
            "path": path,
        }
    except RelayForgeServiceError as exc:
        return exc.status, {
            "schema": "battle.v16.relayforge.error.v1",
            "status": "REJECTED",
            "target_id": TARGET_ID,
            "reason": exc.code,
            "detail": exc.detail,
        }


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


class Handler(BaseHTTPRequestHandler):
    server_version = "RelayForgeV16/0.4"

    def _handle(self) -> None:
        content_length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(content_length) if content_length else b""
        status, payload = response_for(
            role=os.environ.get("RELAYFORGE_ROLE", "unconfigured"),
            method=self.command,
            path=self.path.split("?", 1)[0],
            body=body,
            headers={key: value for key, value in self.headers.items()},
        )
        encoded = _json_bytes(payload)
        self.send_response(int(status))
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        self._handle()

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        self._handle()

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    port = int(os.environ.get("RELAYFORGE_PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
