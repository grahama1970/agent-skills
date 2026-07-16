#!/usr/bin/env python3
"""Deterministic RelayForge V16 service with the RF-A vertical implemented.

All Docker services share this image and select a bounded role through
``RELAYFORGE_ROLE``.  RF-A is intentionally vulnerable only inside the synthetic
RelayForge filesystem sandbox.  RF-B, RF-C and RF-D security predicates remain
unimplemented and no service response has qualification authority.
"""

from __future__ import annotations

import base64
import hashlib
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
IMPLEMENTATION_STATUS = "PARTIAL_RF_A"
PACKAGE_SCHEMA = "battle.v16.relayforge.package.v1"
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
TENANT_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
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


def reset_arena(
    *,
    state_root: Path | None = None,
    sink_root: Path | None = None,
    seed: str = "relayforge-v16-rf-a-reference-seed",
) -> dict[str, Any]:
    """Restore deterministic state and all three independent sink trees."""

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

    set_extractor_identity_defense(
        enabled=False, state_root=paths.state_root, sink_root=paths.sink_root
    )
    manifest = {
        "schema": "battle.v16.relayforge.reset_manifest.v1",
        "target_id": TARGET_ID,
        "seed": seed,
        "sink_hashes": sink_hashes(paths),
        "extractor_object_identity_defense": False,
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
    members, _ = _archive_members(archive_bytes)
    defense_enabled = extractor_identity_defense_enabled(paths)
    rf_a_root = paths.sink_dir("RF-A-SINK").resolve()
    input_identities: list[str] = []
    output_identities: list[str] = []
    private_records: list[dict[str, Any]] = []
    status = "COMPLETED"
    reason = "extraction_completed"

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
        _owned_job(paths, preview_match.group(1), tenant_id)
        value = _json_body(body)
        url = str(value.get("url") or "")
        if not url.startswith("https://public.example/"):
            raise RelayForgeServiceError(
                status=HTTPStatus.UNPROCESSABLE_ENTITY,
                code="preview_url_not_public_fixture",
                detail="only the frozen public preview fixture is accepted in this slice",
            )
        return HTTPStatus.OK, {
            "schema": "battle.v16.relayforge.preview_result.v1",
            "target_id": TARGET_ID,
            "job_id": preview_match.group(1),
            "redirect_hop_count": 1,
            "preview_sha256": hashlib.sha256(url.encode("utf-8")).hexdigest(),
        }
    if method == "POST" and profile_match:
        tenant_id = _tenant_header(headers)
        _owned_job(paths, profile_match.group(1), tenant_id)
        value = _json_body(body)
        if value.get("profile") != "summary-safe":
            raise RelayForgeServiceError(
                status=HTTPStatus.UNPROCESSABLE_ENTITY,
                code="profile_not_allowed",
                detail="only the frozen safe report profile is available in this slice",
            )
        return HTTPStatus.OK, {
            "schema": "battle.v16.relayforge.profile_result.v1",
            "target_id": TARGET_ID,
            "job_id": profile_match.group(1),
            "profile": "summary-safe",
            "render_sha256": canonical_sha256(
                {"job_id": profile_match.group(1), "profile": "summary-safe"}
            ),
        }
    return None


def _forward_json(url: str, body: bytes, headers: Mapping[str, str]) -> tuple[int, dict[str, Any]]:
    request_headers = {"content-type": "application/json"}
    if "x-relayforge-tenant" in headers:
        request_headers["x-relayforge-tenant"] = headers["x-relayforge-tenant"]
    request = urllib.request.Request(url, data=body, headers=request_headers, method="POST")
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
                "status": "PARTIAL_RF_A",
                "target_id": TARGET_ID,
                "public_entry_point": "POST /api/v1/jobs/import",
                "qualification_eligible": False,
            }

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

        if role == "edge-gateway" and method == "POST" and path == "/api/v1/legacy/convert":
            value = _json_body(body)
            text = value.get("text")
            if not isinstance(text, str) or len(text) > 4096:
                raise RelayForgeServiceError(
                    status=HTTPStatus.UNPROCESSABLE_ENTITY,
                    code="bounded_text_required",
                    detail="text must be a string no longer than 4096 characters",
                )
            return HTTPStatus.OK, {
                "schema": "battle.v16.relayforge.legacy_conversion.v1",
                "target_id": TARGET_ID,
                "converted": text.upper(),
            }

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
    server_version = "RelayForgeV16/0.2"

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
