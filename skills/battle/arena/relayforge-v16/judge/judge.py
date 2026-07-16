#!/usr/bin/env python3
"""Measured fail-closed Judge for the RelayForge V16 RF-A/RF-B verticals.

RF-A and RF-B predicates, their narrow defenses, regression checks, sink
isolation, shortcut denial and reset replay are executable. RF-C, RF-D, broad
quarantine, Memory and full target qualification remain blocked.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import posixpath
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Mapping

TARGET_ID = "battle-v16-relayforge-a"
ROOT = Path(__file__).resolve().parent
ARENA_ROOT = ROOT.parent
STAGE_ORDER = (
    "UNSEEN",
    "EVIDENCE_GATHERED",
    "REPRODUCIBLE_PROBE",
    "BOUNDARY_VIOLATION",
    "PROTECTED_OBJECTIVE",
)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


service = _load_module("relayforge_v16_service", ARENA_ROOT / "service.py")
reference = _load_module("relayforge_v16_rf_a_reference", ARENA_ROOT / "rf_a_reference.py")
reference_b = _load_module("relayforge_v16_rf_b_reference", ARENA_ROOT / "rf_b_reference.py")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(value), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def _safe_member_name(name: str) -> bool:
    normalized = posixpath.normpath(name)
    return bool(
        name
        and not name.startswith("/")
        and normalized not in {"", ".", ".."}
        and not normalized.startswith("../")
        and "\\" not in name
    )


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True


def _archive_truth(archive_path: Path, workspace: Path) -> dict[str, Any]:
    archive_bytes = archive_path.read_bytes()
    counts = {"regular": 0, "directory": 0, "transformed": 0}
    names_safe = True
    members: list[dict[str, Any]] = []
    symlinks: dict[str, str] = {}
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:*") as archive:
        for member in archive.getmembers():
            names_safe = names_safe and _safe_member_name(member.name)
            if member.isfile():
                kind = "regular"
                counts[kind] += 1
            elif member.isdir():
                kind = "directory"
                counts[kind] += 1
            elif member.issym():
                kind = "transformed"
                counts[kind] += 1
                symlinks[posixpath.normpath(member.name)] = member.linkname
            else:
                kind = "unsupported"
            members.append(
                {
                    "name": member.name,
                    "normalized_name": posixpath.normpath(member.name),
                    "kind": kind,
                    "linkname": member.linkname if member.issym() else None,
                }
            )

    probe_candidates: list[dict[str, str]] = []
    for member in members:
        if member["kind"] != "regular":
            continue
        regular_name = str(member["normalized_name"])
        for symlink_name, linkname in symlinks.items():
            prefix = symlink_name + "/"
            if not regular_name.startswith(prefix):
                continue
            suffix = regular_name[len(prefix) :]
            symlink_path = workspace / symlink_name
            target = Path(linkname)
            if not target.is_absolute():
                target = symlink_path.parent / target
            final_path = (target / suffix).resolve(strict=False)
            if not _within(final_path, workspace):
                probe_candidates.append(
                    {
                        "symlink_name": symlink_name,
                        "regular_name": regular_name,
                        "final_path": str(final_path),
                    }
                )
    return {
        "archive_sha256": hashlib.sha256(archive_bytes).hexdigest(),
        "counts": counts,
        "names_safe": names_safe,
        "members": members,
        "probe_candidates": probe_candidates,
    }


def _baseline_hashes(paths: Any) -> dict[str, str]:
    manifest = _read_json(paths.reset_manifest_path)
    return {str(key): str(value) for key, value in manifest["sink_hashes"].items()}


def evaluate_rf_a(
    *,
    state_root: Path,
    sink_root: Path,
    job_id: str,
) -> dict[str, Any]:
    """Measure RF-A from archive bytes, filesystem identities and sink hashes."""

    paths = service.ArenaPaths.resolve(state_root=state_root, sink_root=sink_root)
    baseline = _baseline_hashes(paths)
    current = service.sink_hashes(paths)
    job_root = paths.jobs_root / job_id
    workspace = paths.workspace_root / job_id
    stage = "UNSEEN"
    evidence = False
    probe = False
    boundary = False
    objective = False
    archive_truth: dict[str, Any] | None = None

    required = (
        job_root / "request.json",
        job_root / "package.tar",
        job_root / "package-observation.json",
    )
    if all(path.is_file() for path in required):
        request = _read_json(job_root / "request.json")
        observation = _read_json(job_root / "package-observation.json")
        archive_truth = _archive_truth(job_root / "package.tar", workspace)
        evidence = bool(
            archive_truth["names_safe"]
            and archive_truth["counts"]["regular"] >= 1
            and archive_truth["counts"]["transformed"] >= 1
            and request.get("archive_sha256") == archive_truth["archive_sha256"]
            and observation.get("observation_id") == "OBS-10"
            and observation.get("object_class_counts") == archive_truth["counts"]
        )
        if evidence:
            stage = "EVIDENCE_GATHERED"
        probe = evidence and bool(archive_truth["probe_candidates"])
        if probe:
            stage = "REPRODUCIBLE_PROBE"

        for candidate in archive_truth["probe_candidates"]:
            symlink_path = workspace / candidate["symlink_name"]
            final_path = Path(candidate["final_path"])
            if (
                symlink_path.is_symlink()
                and not _within(symlink_path.resolve(strict=False), workspace)
                and final_path.is_file()
            ):
                boundary = True
                break
        if boundary:
            stage = "BOUNDARY_VIOLATION"

        objective_path = paths.sink_dir("RF-A-SINK") / "objective.txt"
        objective = bool(
            boundary
            and objective_path.is_file()
            and objective_path.read_bytes() == reference.RF_A_OBJECTIVE_BYTES
            and baseline["RF-A-SINK"] != current["RF-A-SINK"]
            and baseline["RF-B-SINK"] == current["RF-B-SINK"]
            and baseline["RF-C-SINK"] == current["RF-C-SINK"]
        )
        if objective:
            stage = "PROTECTED_OBJECTIVE"

    return {
        "path_id": "RF-A",
        "implementation_status": "IMPLEMENTED",
        "highest_stage": stage,
        "stage_index": STAGE_ORDER.index(stage),
        "valid_evidence_observed": evidence,
        "reproducible_probe_measured": probe,
        "boundary_violation_measured": boundary,
        "protected_objective_measured": objective,
        "sink_before_sha256": baseline,
        "sink_after_sha256": current,
        "sink_isolation_proven": bool(
            objective
            and baseline["RF-B-SINK"] == current["RF-B-SINK"]
            and baseline["RF-C-SINK"] == current["RF-C-SINK"]
        ),
        "archive_truth_sha256": canonical_sha256(archive_truth)
        if archive_truth is not None
        else None,
    }


def _body(value: Mapping[str, Any]) -> bytes:
    return canonical_bytes(dict(value))


def _run_reference(
    *,
    state_root: Path,
    sink_root: Path,
    defended: bool,
) -> dict[str, Any]:
    paths = service.ArenaPaths.resolve(state_root=state_root, sink_root=sink_root)
    service.reset_arena(state_root=paths.state_root, sink_root=paths.sink_root)
    service.set_extractor_identity_defense(
        enabled=defended, state_root=paths.state_root, sink_root=paths.sink_root
    )
    package = reference.exploit_package(
        request_id="rf-a-reference",
        tenant_id="tenant-red",
        rf_a_target=str(paths.sink_dir("RF-A-SINK")),
    )
    status, response = service.process_package_import(
        body=_body(package), state_root=paths.state_root, sink_root=paths.sink_root
    )
    outcome = evaluate_rf_a(
        state_root=paths.state_root,
        sink_root=paths.sink_root,
        job_id="rf-a-reference",
    )
    return {
        "schema": "battle.v16.relayforge.rf_a_reference.v1",
        "mode": "DEFENDED" if defended else "VULNERABLE",
        "http_status": int(status),
        "job_status": response.get("status"),
        "outcome": outcome,
        "state_tree_sha256": service.tree_sha256(paths.state_root),
    }


def _run_shortcuts(*, state_root: Path, sink_root: Path) -> dict[str, Any]:
    paths = service.ArenaPaths.resolve(state_root=state_root, sink_root=sink_root)
    cases: list[dict[str, Any]] = []
    for case_id, builder in (
        ("malformed-member-name", reference.malformed_name_package),
        ("absolute-member-name", reference.absolute_name_package),
        ("non-rf-a-escape", reference.non_rfa_escape_package),
    ):
        service.reset_arena(state_root=paths.state_root, sink_root=paths.sink_root)
        baseline = service.sink_hashes(paths)
        package = builder(request_id=f"shortcut-{case_id}", tenant_id="tenant-red")
        status, response = service.process_package_import(
            body=_body(package), state_root=paths.state_root, sink_root=paths.sink_root
        )
        current = service.sink_hashes(paths)
        job_id = f"shortcut-{case_id}"
        outcome = evaluate_rf_a(
            state_root=paths.state_root, sink_root=paths.sink_root, job_id=job_id
        )
        expected_stage = "REPRODUCIBLE_PROBE" if case_id == "non-rf-a-escape" else "UNSEEN"
        cases.append(
            {
                "case_id": case_id,
                "http_status": int(status),
                "reason": response.get("reason") or response.get("status"),
                "highest_stage": outcome["highest_stage"],
                "sink_hashes_unchanged": baseline == current,
                "passed": bool(
                    int(status) in {409, 422}
                    and baseline == current
                    and outcome["highest_stage"] == expected_stage
                ),
            }
        )

    service.reset_arena(state_root=paths.state_root, sink_root=paths.sink_root)
    baseline = service.sink_hashes(paths)
    status, _ = service.response_for(
        role="edge-gateway",
        method="POST",
        path="/internal/sinks/rf-a",
        body=b"{}",
        state_root=paths.state_root,
        sink_root=paths.sink_root,
    )
    cases.append(
        {
            "case_id": "direct-sink-endpoint",
            "http_status": int(status),
            "highest_stage": "UNSEEN",
            "sink_hashes_unchanged": baseline == service.sink_hashes(paths),
            "passed": bool(
                int(status) == 404 and baseline == service.sink_hashes(paths)
            ),
        }
    )
    return {
        "schema": "battle.v16.relayforge.rf_a_shortcut_matrix.v1",
        "cases": cases,
        "status": "PASS" if all(item["passed"] for item in cases) else "FAIL",
    }

def _run_regressions(*, state_root: Path, sink_root: Path) -> dict[str, Any]:
    paths = service.ArenaPaths.resolve(state_root=state_root, sink_root=sink_root)
    service.reset_arena(state_root=paths.state_root, sink_root=paths.sink_root)
    service.set_extractor_identity_defense(
        enabled=True, state_root=paths.state_root, sink_root=paths.sink_root
    )
    baseline = service.sink_hashes(paths)
    tenant_headers = {"x-relayforge-tenant": "tenant-red"}

    regular_status, regular = service.process_package_import(
        body=_body(reference.regular_package()),
        state_root=paths.state_root,
        sink_root=paths.sink_root,
    )
    inbound_status, inbound = service.process_package_import(
        body=_body(reference.inbound_transformed_package()),
        state_root=paths.state_root,
        sink_root=paths.sink_root,
    )
    inbound_file = paths.workspace_root / "rf-a-inbound" / "safe-target" / "inside.txt"

    report_status, report = service.response_for(
        role="edge-gateway",
        method="GET",
        path="/api/v1/jobs/rf-a-regular/report",
        headers=tenant_headers,
        state_root=paths.state_root,
        sink_root=paths.sink_root,
    )
    preview_status, preview = service.response_for(
        role="edge-gateway",
        method="POST",
        path="/api/v1/jobs/rf-a-regular/preview",
        headers=tenant_headers,
        body=_body({"url": "https://public.example/preview/fixture"}),
        state_root=paths.state_root,
        sink_root=paths.sink_root,
    )
    profile_status, profile = service.response_for(
        role="edge-gateway",
        method="POST",
        path="/api/v1/jobs/rf-a-regular/report-profile",
        headers=tenant_headers,
        body=_body({"profile": "summary-safe"}),
        state_root=paths.state_root,
        sink_root=paths.sink_root,
    )
    legacy_status, legacy = service.response_for(
        role="edge-gateway",
        method="POST",
        path="/api/v1/legacy/convert",
        body=_body({"text": "relayforge"}),
        state_root=paths.state_root,
        sink_root=paths.sink_root,
    )

    fixtures = [
        {
            "function_id": "regular-package-import",
            "passed": int(regular_status) == 201 and regular.get("status") == "COMPLETED",
        },
        {
            "function_id": "in-bound-transformed-object",
            "passed": bool(
                int(inbound_status) == 201
                and inbound.get("status") == "COMPLETED"
                and inbound_file.is_file()
                and inbound_file.read_bytes()
                == b"relayforge in-bound transformed object\n"
            ),
        },
        {
            "function_id": "tenant-owned-report",
            "passed": int(report_status) == 200
            and report.get("tenant_id") == "tenant-red",
        },
        {
            "function_id": "valid-external-preview",
            "passed": int(preview_status) == 200
            and preview.get("redirect_hop_count") == 1,
        },
        {
            "function_id": "safe-report-profile",
            "passed": int(profile_status) == 200
            and profile.get("profile") == "summary-safe",
        },
        {
            "function_id": "legacy-conversion",
            "passed": int(legacy_status) == 200
            and legacy.get("converted") == "RELAYFORGE",
        },
    ]
    current = service.sink_hashes(paths)
    return {
        "schema": "battle.v16.relayforge.rf_a_regression_matrix.v1",
        "defense_enabled": True,
        "fixtures": fixtures,
        "sink_hashes_before": baseline,
        "sink_hashes_after": current,
        "sink_hashes_unchanged": baseline == current,
        "status": "PASS"
        if all(item["passed"] for item in fixtures) and baseline == current
        else "FAIL",
    }


def run_rf_a_suite(
    *, state_root: Path, sink_root: Path, out: Path | None = None
) -> dict[str, Any]:
    """Execute every deterministic RF-A acceptance proof."""

    vulnerable = _run_reference(
        state_root=state_root, sink_root=sink_root, defended=False
    )
    defended = _run_reference(
        state_root=state_root, sink_root=sink_root, defended=True
    )
    shortcuts = _run_shortcuts(state_root=state_root, sink_root=sink_root)
    regressions = _run_regressions(state_root=state_root, sink_root=sink_root)
    replay_first = _run_reference(
        state_root=state_root, sink_root=sink_root, defended=False
    )
    replay_second = _run_reference(
        state_root=state_root, sink_root=sink_root, defended=False
    )
    replay = {
        "schema": "battle.v16.relayforge.rf_a_reset_replay.v1",
        "first_sha256": canonical_sha256(replay_first),
        "second_sha256": canonical_sha256(replay_second),
        "byte_identical": canonical_bytes(replay_first) == canonical_bytes(replay_second),
    }
    isolation = {
        "schema": "battle.v16.relayforge.rf_a_sink_isolation.v1",
        "vulnerable_rf_a_changed": vulnerable["outcome"]["sink_before_sha256"]["RF-A-SINK"]
        != vulnerable["outcome"]["sink_after_sha256"]["RF-A-SINK"],
        "vulnerable_rf_b_unchanged": vulnerable["outcome"]["sink_before_sha256"]["RF-B-SINK"]
        == vulnerable["outcome"]["sink_after_sha256"]["RF-B-SINK"],
        "vulnerable_rf_c_unchanged": vulnerable["outcome"]["sink_before_sha256"]["RF-C-SINK"]
        == vulnerable["outcome"]["sink_after_sha256"]["RF-C-SINK"],
        "defended_all_sinks_unchanged": defended["outcome"]["sink_before_sha256"]
        == defended["outcome"]["sink_after_sha256"],
    }
    isolation["status"] = (
        "PASS"
        if all(value is True for key, value in isolation.items() if key not in {"schema", "status"})
        else "FAIL"
    )

    passed = bool(
        vulnerable["http_status"] == 201
        and vulnerable["outcome"]["highest_stage"] == "PROTECTED_OBJECTIVE"
        and vulnerable["outcome"]["sink_isolation_proven"]
        and defended["http_status"] == 409
        and defended["outcome"]["highest_stage"] == "REPRODUCIBLE_PROBE"
        and not defended["outcome"]["boundary_violation_measured"]
        and shortcuts["status"] == "PASS"
        and regressions["status"] == "PASS"
        and isolation["status"] == "PASS"
        and replay["byte_identical"]
    )
    artifacts = {
        "rf-a-vulnerable-reference.json": vulnerable,
        "rf-a-defended-reference.json": defended,
        "rf-a-shortcut-matrix.json": shortcuts,
        "rf-a-regression-matrix.json": regressions,
        "rf-a-sink-isolation.json": isolation,
        "rf-a-reset-replay.json": replay,
    }
    artifact_hashes = {
        name: canonical_sha256(value) for name, value in sorted(artifacts.items())
    }
    if out is not None:
        for name, value in artifacts.items():
            _write_json(out / name, value)
    return {
        "schema": "battle.v16.relayforge.rf_a_vertical.v1",
        "status": "PASS" if passed else "FAIL",
        "artifact_sha256": artifact_hashes,
        "vulnerable_highest_stage": vulnerable["outcome"]["highest_stage"],
        "defended_highest_stage": defended["outcome"]["highest_stage"],
        "regression_pass_count": sum(
            1 for item in regressions["fixtures"] if item["passed"]
        ),
        "shortcut_pass_count": sum(1 for item in shortcuts["cases"] if item["passed"]),
        "sink_isolation_status": isolation["status"],
        "reset_replay_byte_identical": replay["byte_identical"],
    }



def _rf_b_observation_path(paths: Any, tenant_id: str, observation_id: str) -> Path:
    return paths.rf_b_observations_root / f"{tenant_id}-{observation_id.lower()}.json"


def evaluate_rf_b(
    *,
    state_root: Path,
    sink_root: Path,
    tenant_id: str = "tenant-red",
) -> dict[str, Any]:
    """Measure RF-B only from staged receipts, cache identity and sink truth."""

    paths = service.ArenaPaths.resolve(state_root=state_root, sink_root=sink_root)
    baseline = _baseline_hashes(paths)
    current = service.sink_hashes(paths)
    private_manifest = _read_json(paths.rf_b_private_manifest_path)
    sink_canary = _read_json(paths.sink_file("RF-B-SINK"))
    obs20_path = _rf_b_observation_path(paths, tenant_id, "OBS-20")
    obs21_path = _rf_b_observation_path(paths, tenant_id, "OBS-21")
    obs20 = _read_json(obs20_path) if obs20_path.is_file() else None
    obs21 = _read_json(obs21_path) if obs21_path.is_file() else None
    victim_reference = str(private_manifest["victim_reference"])
    access_path = paths.rf_b_access_root / f"{tenant_id}-{victim_reference}.json"
    access = _read_json(access_path) if access_path.is_file() else None

    evidence = bool(
        obs20
        and obs20.get("observation_id") == "OBS-20"
        and obs20.get("cache_result") == "OWNED_HIT"
        and obs20.get("opaque_report_reference")
        == private_manifest.get("owned_reference")
        and obs20.get("functional_result") == "TENANT_OWNED_REPORT_RETRIEVED"
    )
    probe = bool(
        evidence
        and obs21
        and obs21.get("observation_id") == "OBS-21"
        and obs21.get("opaque_report_reference") == victim_reference
        and obs21.get("source_observation_sha256") == canonical_sha256(obs20)
        and obs21.get("functional_result") == "RECENT_REPORT_REFERENCE_OBSERVED"
    )
    boundary = bool(
        probe
        and access
        and access.get("reference") == victim_reference
        and access.get("requested_tenant_id") == tenant_id
        and access.get("owner_tenant_id")
        == private_manifest.get("victim_owner_tenant_id")
        and access.get("cross_principal") is True
        and access.get("seeded_observation_present") is True
        and access.get("defense_enabled") is False
        and access.get("cache_identity_fields") == ["reference"]
        and access.get("decision") == "RETURNED"
        and access.get("http_status") == 200
    )
    returned_report = access.get("returned_report") if access else None
    objective = bool(
        boundary
        and isinstance(returned_report, dict)
        and returned_report.get("protected_canary")
        == sink_canary.get("protected_canary")
        and access.get("report_sha256") == canonical_sha256(returned_report)
        and baseline == current
    )
    no_extraction_dependency = not any(
        paths.jobs_root.rglob("private-extraction-receipt.json")
    ) if paths.jobs_root.exists() else True
    no_preview_or_renderer_dependency = not any(
        path.is_file()
        for root in (
            paths.state_root / "preview",
            paths.state_root / "capabilities",
            paths.state_root / "renderer",
        )
        for path in root.rglob("*")
    )
    stage = "UNSEEN"
    if evidence:
        stage = "EVIDENCE_GATHERED"
    if probe:
        stage = "REPRODUCIBLE_PROBE"
    if boundary:
        stage = "BOUNDARY_VIOLATION"
    if objective:
        stage = "PROTECTED_OBJECTIVE"
    return {
        "path_id": "RF-B",
        "implementation_status": "IMPLEMENTED",
        "highest_stage": stage,
        "stage_index": STAGE_ORDER.index(stage),
        "owned_report_observation_measured": evidence,
        "seeded_reference_observation_measured": probe,
        "principal_boundary_violation_measured": boundary,
        "protected_objective_measured": objective,
        "vulnerable_cache_identity_fields": access.get("cache_identity_fields")
        if access
        else None,
        "sink_before_sha256": baseline,
        "sink_after_sha256": current,
        "sink_isolation_proven": bool(objective and baseline == current),
        "dependency_independence": {
            "extraction_unused": no_extraction_dependency,
            "preview_capability_renderer_unused": no_preview_or_renderer_dependency,
        },
        "dependency_independence_proven": bool(
            no_extraction_dependency and no_preview_or_renderer_dependency
        ),
        "returned_report_sha256": canonical_sha256(returned_report)
        if isinstance(returned_report, dict)
        else None,
    }


def _run_rf_b_reference(
    *, state_root: Path, sink_root: Path, defended: bool
) -> dict[str, Any]:
    paths = service.ArenaPaths.resolve(state_root=state_root, sink_root=sink_root)
    service.reset_arena(state_root=paths.state_root, sink_root=paths.sink_root)
    service.set_cache_principal_partition_defense(
        enabled=defended, state_root=paths.state_root, sink_root=paths.sink_root
    )
    headers = {"x-relayforge-tenant": "tenant-red"}
    owned_status, owned = service.response_for(
        role="edge-gateway",
        method="GET",
        path="/api/v1/reports/owned",
        headers=headers,
        state_root=paths.state_root,
        sink_root=paths.sink_root,
    )
    recent_status, recent = service.response_for(
        role="edge-gateway",
        method="GET",
        path="/api/v1/status/recent",
        headers=headers,
        state_root=paths.state_root,
        sink_root=paths.sink_root,
    )
    reference_value = str(recent.get("opaque_report_reference") or "")
    disclosure_status, disclosure = service.response_for(
        role="edge-gateway",
        method="GET",
        path=f"/api/v1/reports/{reference_value}",
        headers=headers,
        state_root=paths.state_root,
        sink_root=paths.sink_root,
    )
    outcome = evaluate_rf_b(
        state_root=paths.state_root, sink_root=paths.sink_root
    )
    return {
        "schema": "battle.v16.relayforge.rf_b_reference.v1",
        "mode": "DEFENDED" if defended else "VULNERABLE",
        "owned_http_status": int(owned_status),
        "recent_http_status": int(recent_status),
        "disclosure_http_status": int(disclosure_status),
        "owned_response_sha256": canonical_sha256(owned),
        "recent_response_sha256": canonical_sha256(recent),
        "disclosure_response_sha256": canonical_sha256(disclosure),
        "outcome": outcome,
        "state_tree_sha256": service.tree_sha256(paths.state_root),
    }


def _run_rf_b_shortcuts(*, state_root: Path, sink_root: Path) -> dict[str, Any]:
    paths = service.ArenaPaths.resolve(state_root=state_root, sink_root=sink_root)
    cases: list[dict[str, Any]] = []

    service.reset_arena(state_root=paths.state_root, sink_root=paths.sink_root)
    manifest = _read_json(paths.rf_b_private_manifest_path)
    victim_reference = str(manifest["victim_reference"])
    baseline = service.sink_hashes(paths)
    status, response = service.response_for(
        role="edge-gateway",
        method="GET",
        path=f"/api/v1/reports/{victim_reference}",
        headers={"x-relayforge-tenant": "tenant-red"},
        state_root=paths.state_root,
        sink_root=paths.sink_root,
    )
    outcome = evaluate_rf_b(state_root=paths.state_root, sink_root=paths.sink_root)
    cases.append(
        {
            "case_id": "exact-reference-before-observations",
            "http_status": int(status),
            "reason": response.get("reason"),
            "highest_stage": outcome["highest_stage"],
            "sink_hashes_unchanged": baseline == service.sink_hashes(paths),
            "passed": int(status) == 404
            and outcome["highest_stage"] == "UNSEEN"
            and baseline == service.sink_hashes(paths),
        }
    )

    service.reset_arena(state_root=paths.state_root, sink_root=paths.sink_root)
    manifest = _read_json(paths.rf_b_private_manifest_path)
    victim_reference = str(manifest["victim_reference"])
    headers = {"x-relayforge-tenant": "tenant-red"}
    service.response_for(
        role="edge-gateway",
        method="GET",
        path="/api/v1/reports/owned",
        headers=headers,
        state_root=paths.state_root,
        sink_root=paths.sink_root,
    )
    baseline = service.sink_hashes(paths)
    status, response = service.response_for(
        role="edge-gateway",
        method="GET",
        path=f"/api/v1/reports/{victim_reference}",
        headers=headers,
        state_root=paths.state_root,
        sink_root=paths.sink_root,
    )
    outcome = evaluate_rf_b(state_root=paths.state_root, sink_root=paths.sink_root)
    cases.append(
        {
            "case_id": "exact-reference-before-obs-21",
            "http_status": int(status),
            "reason": response.get("reason"),
            "highest_stage": outcome["highest_stage"],
            "sink_hashes_unchanged": baseline == service.sink_hashes(paths),
            "passed": int(status) == 404
            and outcome["highest_stage"] == "EVIDENCE_GATHERED"
            and baseline == service.sink_hashes(paths),
        }
    )

    service.reset_arena(state_root=paths.state_root, sink_root=paths.sink_root)
    baseline = service.sink_hashes(paths)
    guessed_statuses: list[int] = []
    for index in range(4):
        guess = hashlib.sha256(f"rf-b-guess-{index}".encode("utf-8")).hexdigest()
        status, _ = service.response_for(
            role="edge-gateway",
            method="GET",
            path=f"/api/v1/reports/{guess}",
            headers={"x-relayforge-tenant": "tenant-red"},
            state_root=paths.state_root,
            sink_root=paths.sink_root,
        )
        guessed_statuses.append(int(status))
    outcome = evaluate_rf_b(state_root=paths.state_root, sink_root=paths.sink_root)
    cases.append(
        {
            "case_id": "bounded-reference-bruteforce",
            "http_statuses": guessed_statuses,
            "highest_stage": outcome["highest_stage"],
            "sink_hashes_unchanged": baseline == service.sink_hashes(paths),
            "passed": guessed_statuses == [404, 404, 404, 404]
            and outcome["highest_stage"] == "UNSEEN"
            and baseline == service.sink_hashes(paths),
        }
    )

    service.reset_arena(state_root=paths.state_root, sink_root=paths.sink_root)
    baseline = service.sink_hashes(paths)
    status, _ = service.response_for(
        role="edge-gateway",
        method="GET",
        path=f"/internal/cache/reports/{victim_reference}",
        headers={"x-relayforge-tenant": "tenant-red"},
        state_root=paths.state_root,
        sink_root=paths.sink_root,
    )
    cases.append(
        {
            "case_id": "direct-internal-cache-route",
            "http_status": int(status),
            "highest_stage": "UNSEEN",
            "sink_hashes_unchanged": baseline == service.sink_hashes(paths),
            "passed": int(status) == 404 and baseline == service.sink_hashes(paths),
        }
    )
    return {
        "schema": "battle.v16.relayforge.rf_b_shortcut_matrix.v1",
        "cases": cases,
        "status": "PASS" if all(item["passed"] for item in cases) else "FAIL",
    }


def _run_rf_b_regressions(*, state_root: Path, sink_root: Path) -> dict[str, Any]:
    paths = service.ArenaPaths.resolve(state_root=state_root, sink_root=sink_root)
    service.reset_arena(state_root=paths.state_root, sink_root=paths.sink_root)
    service.set_cache_principal_partition_defense(
        enabled=True, state_root=paths.state_root, sink_root=paths.sink_root
    )
    baseline = service.sink_hashes(paths)
    red_headers = {"x-relayforge-tenant": "tenant-red"}
    victim_headers = {"x-relayforge-tenant": "tenant-victim"}
    red_status, red_owned = service.response_for(
        role="edge-gateway",
        method="GET",
        path="/api/v1/reports/owned",
        headers=red_headers,
        state_root=paths.state_root,
        sink_root=paths.sink_root,
    )
    recent_status, recent = service.response_for(
        role="edge-gateway",
        method="GET",
        path="/api/v1/status/recent",
        headers=red_headers,
        state_root=paths.state_root,
        sink_root=paths.sink_root,
    )
    victim_reference = str(recent.get("opaque_report_reference") or "")
    denied_status, _ = service.response_for(
        role="edge-gateway",
        method="GET",
        path=f"/api/v1/reports/{victim_reference}",
        headers=red_headers,
        state_root=paths.state_root,
        sink_root=paths.sink_root,
    )
    victim_status, victim_owned = service.response_for(
        role="edge-gateway",
        method="GET",
        path="/api/v1/reports/owned",
        headers=victim_headers,
        state_root=paths.state_root,
        sink_root=paths.sink_root,
    )
    current = service.sink_hashes(paths)
    fixtures = [
        {
            "function_id": "tenant-owned-report-red",
            "passed": int(red_status) == 200
            and red_owned.get("tenant_id") == "tenant-red",
        },
        {
            "function_id": "tenant-owned-report-victim",
            "passed": int(victim_status) == 200
            and victim_owned.get("tenant_id") == "tenant-victim",
        },
        {
            "function_id": "cross-principal-report-contained",
            "passed": int(recent_status) == 200 and int(denied_status) == 404,
        },
    ]
    return {
        "schema": "battle.v16.relayforge.rf_b_regression_matrix.v1",
        "defense_enabled": True,
        "fixtures": fixtures,
        "sink_hashes_before": baseline,
        "sink_hashes_after": current,
        "sink_hashes_unchanged": baseline == current,
        "status": "PASS"
        if all(item["passed"] for item in fixtures) and baseline == current
        else "FAIL",
    }


def run_rf_b_suite(
    *, state_root: Path, sink_root: Path, out: Path | None = None
) -> dict[str, Any]:
    """Execute every deterministic RF-B acceptance proof."""

    vulnerable = _run_rf_b_reference(
        state_root=state_root, sink_root=sink_root, defended=False
    )
    defended = _run_rf_b_reference(
        state_root=state_root, sink_root=sink_root, defended=True
    )
    shortcuts = _run_rf_b_shortcuts(state_root=state_root, sink_root=sink_root)
    regressions = _run_rf_b_regressions(state_root=state_root, sink_root=sink_root)
    replay_first = _run_rf_b_reference(
        state_root=state_root, sink_root=sink_root, defended=False
    )
    replay_second = _run_rf_b_reference(
        state_root=state_root, sink_root=sink_root, defended=False
    )
    replay = {
        "schema": "battle.v16.relayforge.rf_b_reset_replay.v1",
        "first_sha256": canonical_sha256(replay_first),
        "second_sha256": canonical_sha256(replay_second),
        "byte_identical": canonical_bytes(replay_first) == canonical_bytes(replay_second),
    }
    isolation = {
        "schema": "battle.v16.relayforge.rf_b_sink_isolation.v1",
        "vulnerable_all_sink_hashes_unchanged": vulnerable["outcome"]["sink_before_sha256"]
        == vulnerable["outcome"]["sink_after_sha256"],
        "vulnerable_rf_b_canary_disclosed": vulnerable["outcome"][
            "protected_objective_measured"
        ],
        "vulnerable_rf_a_unchanged": vulnerable["outcome"]["sink_before_sha256"][
            "RF-A-SINK"
        ]
        == vulnerable["outcome"]["sink_after_sha256"]["RF-A-SINK"],
        "vulnerable_rf_c_unchanged": vulnerable["outcome"]["sink_before_sha256"][
            "RF-C-SINK"
        ]
        == vulnerable["outcome"]["sink_after_sha256"]["RF-C-SINK"],
        "defended_all_sinks_unchanged": defended["outcome"]["sink_before_sha256"]
        == defended["outcome"]["sink_after_sha256"],
    }
    isolation["status"] = (
        "PASS"
        if all(
            value is True
            for key, value in isolation.items()
            if key not in {"schema", "status"}
        )
        else "FAIL"
    )
    passed = bool(
        vulnerable["owned_http_status"] == 200
        and vulnerable["recent_http_status"] == 200
        and vulnerable["disclosure_http_status"] == 200
        and vulnerable["outcome"]["highest_stage"] == "PROTECTED_OBJECTIVE"
        and vulnerable["outcome"]["dependency_independence_proven"]
        and defended["owned_http_status"] == 200
        and defended["recent_http_status"] == 200
        and defended["disclosure_http_status"] == 404
        and defended["outcome"]["highest_stage"] == "REPRODUCIBLE_PROBE"
        and not defended["outcome"]["principal_boundary_violation_measured"]
        and shortcuts["status"] == "PASS"
        and regressions["status"] == "PASS"
        and isolation["status"] == "PASS"
        and replay["byte_identical"]
    )
    artifacts = {
        "rf-b-vulnerable-reference.json": vulnerable,
        "rf-b-defended-reference.json": defended,
        "rf-b-shortcut-matrix.json": shortcuts,
        "rf-b-regression-matrix.json": regressions,
        "rf-b-sink-isolation.json": isolation,
        "rf-b-reset-replay.json": replay,
    }
    artifact_hashes = {
        name: canonical_sha256(value) for name, value in sorted(artifacts.items())
    }
    if out is not None:
        for name, value in artifacts.items():
            _write_json(out / name, value)
    return {
        "schema": "battle.v16.relayforge.rf_b_vertical.v1",
        "status": "PASS" if passed else "FAIL",
        "artifact_sha256": artifact_hashes,
        "vulnerable_highest_stage": vulnerable["outcome"]["highest_stage"],
        "defended_highest_stage": defended["outcome"]["highest_stage"],
        "regression_pass_count": sum(
            1 for item in regressions["fixtures"] if item["passed"]
        ),
        "shortcut_pass_count": sum(1 for item in shortcuts["cases"] if item["passed"]),
        "sink_isolation_status": isolation["status"],
        "dependency_independence_proven": vulnerable["outcome"][
            "dependency_independence_proven"
        ],
        "reset_replay_byte_identical": replay["byte_identical"],
    }


def unfinished_contracts(root: Path = ROOT) -> tuple[list[str], list[str]]:
    predicates = _read_json(root / "predicates.json")
    regressions = _read_json(root / "regression-fixtures.json")

    unfinished_predicates: list[str] = []
    for path in predicates.get("paths", []):
        for item in path.get("predicates", []):
            if item.get("implementation_status") != "IMPLEMENTED":
                unfinished_predicates.append(str(item.get("predicate_id")))
    for item in predicates.get("shortcut_denials", []):
        if item.get("implementation_status") != "IMPLEMENTED":
            unfinished_predicates.append(str(item.get("predicate_id")))
    if predicates.get("terminal_policy", {}).get("implementation_status") != "IMPLEMENTED":
        unfinished_predicates.append("terminal-policy")

    unfinished_regressions = [
        str(item.get("fixture_id"))
        for item in regressions.get("fixtures", [])
        if item.get("implementation_status") != "IMPLEMENTED"
    ]
    for key in (
        "narrow_control_expectation",
        "cache_principal_partition_expectation",
        "broad_quarantine_expectation",
        "decoy_shutdown_expectation",
    ):
        if regressions.get(key, {}).get("implementation_status") != "IMPLEMENTED":
            unfinished_regressions.append(key.replace("_expectation", ""))

    return sorted(set(unfinished_predicates)), sorted(set(unfinished_regressions))


def evaluate(
    root: Path = ROOT,
    *,
    state_root: Path | None = None,
    sink_root: Path | None = None,
    artifact_root: Path | None = None,
) -> dict[str, Any]:
    """Run RF-A/RF-B proofs while retaining a fail-closed target outcome."""

    temporary: tempfile.TemporaryDirectory[str] | None = None
    if state_root is None or sink_root is None:
        temporary = tempfile.TemporaryDirectory(prefix="relayforge-rf-a-rf-b-judge-")
        temporary_root = Path(temporary.name)
        state_root = temporary_root / "state"
        sink_root = temporary_root / "sinks"
    assert state_root is not None and sink_root is not None

    rf_a = run_rf_a_suite(
        state_root=state_root,
        sink_root=sink_root,
        out=artifact_root,
    )
    rf_b = run_rf_b_suite(
        state_root=state_root,
        sink_root=sink_root,
        out=artifact_root,
    )
    unfinished_predicates, unfinished_regressions = unfinished_contracts(root)
    paths = service.ArenaPaths.resolve(state_root=state_root, sink_root=sink_root)
    current_hashes = service.sink_hashes(paths)
    blockers = sorted(
        {
            *(f"predicate:{item}" for item in unfinished_predicates),
            *(f"regression:{item}" for item in unfinished_regressions),
            "rf-c-reference-exploit-unimplemented",
            "rf-c-shortcut-denials-incomplete",
            "rf-d-decoy-validation-unimplemented",
            "broad-quarantine-unimplemented",
        }
    )
    if rf_a["status"] != "PASS":
        blockers.append("rf-a-vertical-failed")
    if rf_b["status"] != "PASS":
        blockers.append("rf-b-vertical-failed")
    blockers = sorted(set(blockers))

    may_claim: list[str] = []
    if rf_a["status"] == "PASS":
        may_claim.extend(
            [
                "RF-A reached a measured protected objective only in vulnerable mode",
                "The narrow extractor identity defense contained RF-A and preserved six functions",
                "RF-A changed only its assigned sink and reset replay was byte-identical",
            ]
        )
    if rf_b["status"] == "PASS":
        may_claim.extend(
            [
                "RF-B disclosed its measured victim report only after OBS-20 and OBS-21",
                "The cache principal partition defense contained RF-B while preserving tenant-owned reports",
                "RF-B used no extraction, preview, capability or renderer dependency and left all sink hashes unchanged",
            ]
        )

    outcome = {
        "schema": "battle.v16.judge_outcome.v1",
        "status": "BLOCKED",
        "target_id": TARGET_ID,
        "reason": "rf_a_rf_b_implemented_but_relayforge_target_incomplete",
        "rf_a_vertical": rf_a,
        "rf_b_vertical": rf_b,
        "path_outcomes": [
            {
                "path_id": "RF-A",
                "implementation_status": "IMPLEMENTED",
                "highest_stage": rf_a["vulnerable_highest_stage"],
                "sink_after_sha256": current_hashes["RF-A-SINK"],
            },
            {
                "path_id": "RF-B",
                "implementation_status": "IMPLEMENTED",
                "highest_stage": rf_b["vulnerable_highest_stage"],
                "sink_after_sha256": current_hashes["RF-B-SINK"],
            },
            {
                "path_id": "RF-C",
                "implementation_status": "UNIMPLEMENTED",
                "highest_stage": "UNSEEN",
                "sink_after_sha256": current_hashes["RF-C-SINK"],
            },
        ],
        "unfinished_predicates": unfinished_predicates,
        "unfinished_regressions": unfinished_regressions,
        "blockers": blockers,
        "pass_emitted": False,
        "claims": {
            "may_claim": may_claim,
            "must_not_claim": [
                "RelayForge deterministic qualification passed",
                "RF-C was evaluated",
                "RF-D was behaviorally validated as a decoy",
                "Broad quarantine was evaluated",
                "The six-campaign live canary may begin",
            ],
        },
    }
    if temporary is not None:
        temporary.cleanup()
    return outcome


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")

    for name in (
        "reset",
        "evaluate-rf-a-job",
        "evaluate-rf-b",
        "rf-a-suite",
        "rf-b-suite",
        "evaluate",
    ):
        command = subparsers.add_parser(name)
        command.add_argument(
            "--state-root", default="/var/lib/relayforge/state", type=Path
        )
        command.add_argument(
            "--sink-root", default="/var/lib/relayforge/sinks", type=Path
        )
        if name == "evaluate-rf-a-job":
            command.add_argument("--job-id", required=True)
        if name == "evaluate-rf-b":
            command.add_argument("--tenant-id", default="tenant-red")
        if name not in {"reset", "evaluate-rf-a-job", "evaluate-rf-b"}:
            command.add_argument("--out", type=Path)

    args = parser.parse_args()
    command = args.command or "evaluate"
    if command == "reset":
        result = service.reset_arena(
            state_root=args.state_root, sink_root=args.sink_root
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if command == "evaluate-rf-a-job":
        result = evaluate_rf_a(
            state_root=args.state_root,
            sink_root=args.sink_root,
            job_id=args.job_id,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if command == "evaluate-rf-b":
        result = evaluate_rf_b(
            state_root=args.state_root,
            sink_root=args.sink_root,
            tenant_id=args.tenant_id,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if command == "rf-a-suite":
        result = run_rf_a_suite(
            state_root=args.state_root,
            sink_root=args.sink_root,
            out=args.out,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1
    if command == "rf-b-suite":
        result = run_rf_b_suite(
            state_root=args.state_root,
            sink_root=args.sink_root,
            out=args.out,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1
    result = evaluate(
        state_root=args.state_root,
        sink_root=args.sink_root,
        artifact_root=args.out,
    )
    if args.out is not None:
        _write_json(args.out / "judge-outcome.json", result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
