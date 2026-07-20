#!/usr/bin/env python3
"""Check the live Memory recall boundary for Persona Dream.

This checker exercises the existing generator without fixtures. It writes a
receipt even when live Memory has no usable residue, and it keeps the claim
surface limited to recall wiring, artifact lineage, and the no-write contract.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PASS_STATUS = "PASS_LIVE_MEMORY_RECALL"
NO_RESIDUE_STATUS = "BLOCKED_LIVE_MEMORY_NO_RESIDUE"
UNAVAILABLE_STATUS = "BLOCKED_LIVE_MEMORY_UNAVAILABLE"
INVARIANT_STATUS = "BLOCKED_LIVE_MEMORY_INVARIANT"
MEMORY_SOCKET = "/run/user/1000/embry/memory.sock"
MEMORY_ENDPOINT = "/recall"
EXPECTED_QUERY_COUNT = 5


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str | None:
    if not path.exists() or path.is_symlink() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _tail(text: str, limit: int = 4000) -> str:
    return text.strip()[-limit:]


def _under_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _persona_aliases(persona_id: str) -> set[str]:
    normalized = persona_id.replace("-", "_")
    aliases = {persona_id, normalized}
    if normalized == "horus":
        aliases.add("horus_lupercal")
    if normalized == "embry":
        aliases.add("embry_lawson")
    return aliases


def _artifact(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "is_symlink": path.is_symlink(),
        "under_output_root": _under_root(path, root),
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size if path.exists() and path.is_file() and not path.is_symlink() else None,
    }


def _load_optional_json(path: Path, errors: list[str]) -> dict[str, Any]:
    if not path.exists():
        return {}
    if path.is_symlink():
        errors.append(f"symlink_artifact:{path.name}")
        return {}
    try:
        return _read_json(path)
    except Exception as exc:
        errors.append(f"malformed_json:{path.name}:{exc}")
        return {}


def _recall_stats(residue_links: dict[str, Any], response: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    receipts = residue_links.get("recall_receipts")
    if not isinstance(receipts, list):
        receipts = response.get("recall_receipts") if isinstance(response.get("recall_receipts"), list) else []
    successful = [r for r in receipts if isinstance(r, dict) and r.get("status") == "ok"]
    failed = [r for r in receipts if isinstance(r, dict) and r.get("status") == "error"]
    total_returned = sum(int(r.get("count") or 0) for r in receipts if isinstance(r, dict))
    total_accepted = sum(int(r.get("accepted_count") or 0) for r in receipts if isinstance(r, dict))
    return receipts, {
        "observed_query_count": len(receipts),
        "successful_query_count": len(successful),
        "failed_query_count": len(failed),
        "total_returned_count": total_returned,
        "total_accepted_count": total_accepted,
    }


def _receipt_errors(receipts: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    if len(receipts) != EXPECTED_QUERY_COUNT:
        errors.append(f"query_count:{len(receipts)}:expected:{EXPECTED_QUERY_COUNT}")
    for idx, receipt in enumerate(receipts):
        prefix = f"query_{idx}"
        for key in ("scope", "query", "status", "count", "accepted_count"):
            if key not in receipt:
                errors.append(f"{prefix}_missing:{key}")
        status = receipt.get("status")
        if status not in {"ok", "error"}:
            errors.append(f"{prefix}_status:{status}")
        count = receipt.get("count")
        accepted = receipt.get("accepted_count")
        if not isinstance(count, int) or count < 0:
            errors.append(f"{prefix}_invalid_count:{count}")
        if not isinstance(accepted, int) or accepted < 0:
            errors.append(f"{prefix}_invalid_accepted_count:{accepted}")
        if isinstance(count, int) and isinstance(accepted, int) and count < accepted:
            errors.append(f"{prefix}_count_lt_accepted:{count}:{accepted}")
        discarded = receipt.get("discarded_persona_mismatch_count")
        if discarded is not None and isinstance(count, int) and isinstance(accepted, int):
            if discarded != count - accepted:
                errors.append(f"{prefix}_discarded_mismatch:{discarded}:expected:{count - accepted}")
    return errors


def _validate_artifacts(
    *,
    output_root: Path,
    run_id: str,
    persona_id: str,
    about: str | None,
    limit: int,
    stats: dict[str, int],
    request: dict[str, Any],
    response: dict[str, Any],
    residue_links: dict[str, Any],
    dream_packet: dict[str, Any],
    frame_prompts: dict[str, Any],
    contradiction_report: dict[str, Any],
    memory_write: dict[str, Any],
    manifest: dict[str, Any],
    stage_report: dict[str, Any],
) -> tuple[list[str], dict[str, bool], dict[str, Any]]:
    errors: list[str] = []
    lineage_checks: dict[str, bool] = {}
    writeback_checks: dict[str, bool] = {}
    aliases = _persona_aliases(persona_id)

    lineage_checks["request_non_fixture"] = request.get("fixture") is None
    lineage_checks["request_no_write_memory"] = request.get("write_memory") is False
    lineage_checks["request_static_mode"] = request.get("mode") == "static_dream"
    lineage_checks["request_run_id"] = request.get("run_id") == run_id
    lineage_checks["request_persona"] = (request.get("persona") or {}).get("id") == persona_id
    lineage_checks["request_about"] = request.get("about") == about
    lineage_checks["request_limit"] = request.get("limit") == limit
    lineage_checks["residue_run_id"] = residue_links.get("run_id") == run_id
    lineage_checks["packet_run_id"] = dream_packet.get("run_id") == run_id
    lineage_checks["packet_persona"] = (dream_packet.get("persona") or {}).get("id") == persona_id
    lineage_checks["packet_mode"] = dream_packet.get("mode") == "static_dream"
    lineage_checks["response_ok"] = response.get("status") == "ok"
    lineage_checks["response_run_id"] = response.get("run_id") == run_id

    items = residue_links.get("items") if isinstance(residue_links.get("items"), list) else []
    packet_items = dream_packet.get("residue_items") if isinstance(dream_packet.get("residue_items"), list) else []
    lineage_checks["packet_items_equal_residue_items"] = packet_items == items
    residue_count = len(items)
    source_ids: list[str] = []
    scopes: set[str] = set()
    fixture_markers: list[str] = []
    persona_mismatches: list[str] = []
    duplicate_source_ids: list[str] = []
    source_pairs: set[tuple[str, str]] = set()
    recall_scopes = {str(r.get("scope")) for r in residue_links.get("recall_receipts", []) if isinstance(r, dict)}

    for idx, item in enumerate(items):
        source_id = str(item.get("source_id") or "")
        scope = str(item.get("scope") or "")
        source = str(item.get("source") or "")
        text = str(item.get("text") or "")
        if not source_id:
            errors.append(f"residue_{idx}_missing_source_id")
        if not scope:
            errors.append(f"residue_{idx}_missing_scope")
        if not text:
            errors.append(f"residue_{idx}_missing_text")
        if item.get("synthetic") is not False:
            errors.append(f"residue_{idx}_synthetic_not_false")
        if scope == "fixture" or source == "fixture":
            fixture_markers.append(f"{scope}:{source_id}")
        if scope and scope not in recall_scopes:
            errors.append(f"residue_{idx}_scope_not_recalled:{scope}")
        pair = (scope, source_id)
        if pair in source_pairs:
            duplicate_source_ids.append(f"{scope}:{source_id}")
        source_pairs.add(pair)
        if source_id:
            source_ids.append(source_id)
        if scope:
            scopes.add(scope)
        explicit_ids: set[str] = set()
        if isinstance(item.get("persona_id"), str) and item.get("persona_id"):
            explicit_ids.add(str(item["persona_id"]))
        for value in item.get("persona_ids") or []:
            if isinstance(value, str) and value:
                explicit_ids.add(value)
        if explicit_ids and not (explicit_ids & aliases):
            persona_mismatches.append(source_id or f"item:{idx}")

    frame_source_ids = [
        sid
        for frame in (frame_prompts.get("frames") or [])
        if isinstance(frame, dict)
        for sid in (frame.get("source_ids") or [])
    ]
    unresolved_frame_refs = sorted({str(sid) for sid in frame_source_ids if str(sid) not in set(source_ids)})
    contradiction_refs = [
        ref
        for contradiction in (contradiction_report.get("contradictions") or [])
        if isinstance(contradiction, dict)
        for ref in (contradiction.get("item_a"), contradiction.get("item_b"))
        if ref
    ]
    unresolved_contradiction_refs = sorted({str(ref) for ref in contradiction_refs if str(ref) not in set(source_ids)})
    lineage_checks["frame_sources_resolve"] = not unresolved_frame_refs
    lineage_checks["contradiction_sources_resolve"] = not unresolved_contradiction_refs
    lineage_checks["stage02_recall_receipts_agree"] = False
    for stage in stage_report.get("stages") or []:
        if isinstance(stage, dict) and stage.get("stage_id") == "stage_02_memory_recall":
            lineage_checks["stage02_recall_receipts_agree"] = (
                (stage.get("evidence") or {}).get("recall_receipts") == residue_links.get("recall_receipts")
            )
            break

    lineage_checks["manifest_artifacts_exist"] = True
    manifest_artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), list) else []
    for name in manifest_artifacts:
        path = output_root / str(name)
        if not _under_root(path, output_root) or path.is_symlink() or not path.exists():
            lineage_checks["manifest_artifacts_exist"] = False
            errors.append(f"manifest_artifact_invalid:{name}")

    response_paths = {
        key: value
        for key, value in response.items()
        if key in {"dream_packet", "manifest"} and isinstance(value, str)
    }
    lineage_checks["response_artifact_paths_under_root"] = all(_under_root(Path(value), output_root) for value in response_paths.values())

    writeback_checks["status_skipped"] = memory_write.get("status") == "skipped"
    writeback_checks["reason_write_memory_false"] = memory_write.get("reason") == "write_memory_false"
    writeback_checks["scope_matches"] = memory_write.get("scope") == f"{persona_id}-dream-journals"
    writeback_checks["no_document_key"] = not any(key in memory_write for key in ("_key", "document_key", "memory_key"))
    writeback_checks["no_store_http_status"] = "http_status" not in memory_write

    if fixture_markers:
        errors.append(f"fixture_markers_found:{','.join(sorted(fixture_markers))}")
    if duplicate_source_ids:
        errors.append(f"duplicate_source_ids:{','.join(sorted(duplicate_source_ids))}")
    if persona_mismatches:
        errors.append(f"persona_mismatches:{','.join(sorted(persona_mismatches))}")
    if unresolved_frame_refs:
        errors.append(f"unresolved_frame_refs:{','.join(unresolved_frame_refs)}")
    if unresolved_contradiction_refs:
        errors.append(f"unresolved_contradiction_refs:{','.join(unresolved_contradiction_refs)}")
    for name, passed in lineage_checks.items():
        if not passed:
            errors.append(f"lineage_check_failed:{name}")
    for name, passed in writeback_checks.items():
        if not passed:
            errors.append(f"writeback_check_failed:{name}")

    return errors, lineage_checks, {
        "writeback_checks": writeback_checks,
        "residue_count": residue_count,
        "unique_source_count": len(set(source_pairs)),
        "source_ids": source_ids,
        "scopes": sorted(scopes),
        "duplicate_source_ids": sorted(duplicate_source_ids),
        "fixture_markers_found": sorted(fixture_markers),
        "persona_mismatches": sorted(persona_mismatches),
        "memory_write_status": memory_write.get("status"),
        "manifest_artifact_count": len(manifest_artifacts),
        "stats": stats,
    }


def build_receipt(
    *,
    persona_id: str,
    about: str | None,
    limit: int,
    run_id: str,
    output_root: Path,
    receipt_out: Path,
    timeout_s: int,
) -> dict[str, Any]:
    started = time.monotonic()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    errors: list[str] = []
    observed_blockers: list[str] = []
    preflight_blocked = False

    if output_root.exists() and output_root.is_symlink():
        errors.append("output_root_is_symlink")
        preflight_blocked = True
    elif output_root.exists() and any(output_root.iterdir()):
        errors.append("output_root_exists_nonempty")
        preflight_blocked = True

    command = [
        sys.executable,
        str(SCRIPTS / "persona_dream.py"),
        "generate",
        "--mode",
        "static_dream",
        "--persona",
        persona_id,
        "--limit",
        str(limit),
        "--output-dir",
        str(output_root),
        "--run-id",
        run_id,
        "--no-write-memory",
    ]
    if about is not None:
        command.extend(["--about", about])

    child_exit_code: int | None = None
    stdout = ""
    stderr = ""
    child_duration_s = 0.0
    timed_out = False

    if not preflight_blocked:
        try:
            child_started = time.monotonic()
            proc = subprocess.run(
                command,
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=timeout_s,
                check=False,
            )
            child_duration_s = round(time.monotonic() - child_started, 3)
            child_exit_code = proc.returncode
            stdout = proc.stdout
            stderr = proc.stderr
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            child_duration_s = round(time.monotonic() - child_started, 3)
            child_exit_code = None
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            errors.append("child_timeout")

    required_artifacts = {
        "dream_request": output_root / "dream_request.json",
        "response": output_root / "response.json",
        "residue_links": output_root / "residue_links.json",
        "dream_packet": output_root / "dream_packet.json",
        "frame_prompts": output_root / "frame_prompts.json",
        "contradiction_report": output_root / "contradiction_report.json",
        "memory_write_receipt": output_root / "memory_write_receipt.json",
        "manifest": output_root / "manifest.json",
        "pipeline_stage_report": output_root / "pipeline_stage_report.json",
    }
    artifact_descriptors = {
        name: _artifact(path, output_root)
        for name, path in required_artifacts.items()
    }
    for name, descriptor in artifact_descriptors.items():
        if descriptor["exists"] and (descriptor["is_symlink"] or not descriptor["under_output_root"]):
            errors.append(f"artifact_boundary_invalid:{name}")

    request_errors: list[str] = []
    if preflight_blocked:
        request = {}
        response = {}
        residue_links = {}
        dream_packet = {}
        frame_prompts = {}
        contradiction_report = {}
        memory_write = {}
        manifest = {}
        stage_report = {}
    else:
        request = _load_optional_json(required_artifacts["dream_request"], request_errors)
        response = _load_optional_json(required_artifacts["response"], request_errors)
        residue_links = _load_optional_json(required_artifacts["residue_links"], request_errors)
        dream_packet = _load_optional_json(required_artifacts["dream_packet"], request_errors)
        frame_prompts = _load_optional_json(required_artifacts["frame_prompts"], request_errors)
        contradiction_report = _load_optional_json(required_artifacts["contradiction_report"], request_errors)
        memory_write = _load_optional_json(required_artifacts["memory_write_receipt"], request_errors)
        manifest = _load_optional_json(required_artifacts["manifest"], request_errors)
        stage_report = _load_optional_json(required_artifacts["pipeline_stage_report"], request_errors)
    errors.extend(request_errors)

    receipts, stats = _recall_stats(residue_links, response)
    if not preflight_blocked:
        errors.extend(_receipt_errors(receipts))

    invariant_errors: list[str] = []
    lineage_checks: dict[str, bool] = {}
    derived: dict[str, Any] = {
        "writeback_checks": {},
        "residue_count": 0,
        "unique_source_count": 0,
        "source_ids": [],
        "scopes": [],
        "duplicate_source_ids": [],
        "fixture_markers_found": [],
        "persona_mismatches": [],
        "memory_write_status": None,
        "manifest_artifact_count": 0,
        "stats": stats,
    }
    if child_exit_code == 0:
        for name, path in required_artifacts.items():
            if not path.exists():
                invariant_errors.append(f"missing_required_artifact:{name}")
        if not invariant_errors:
            artifact_errors, lineage_checks, derived = _validate_artifacts(
                output_root=output_root,
                run_id=run_id,
                persona_id=persona_id,
                about=about,
                limit=limit,
                stats=stats,
                request=request,
                response=response,
                residue_links=residue_links,
                dream_packet=dream_packet,
                frame_prompts=frame_prompts,
                contradiction_report=contradiction_report,
                memory_write=memory_write,
                manifest=manifest,
                stage_report=stage_report,
            )
            invariant_errors.extend(artifact_errors)
        if stats["observed_query_count"] == EXPECTED_QUERY_COUNT and stats["failed_query_count"] > 0:
            invariant_errors.append("partial_recall_failure")
        if derived["residue_count"] < 1:
            invariant_errors.append("no_residue_on_success")
    errors.extend(invariant_errors)

    response_blocked_no_dream = response.get("status") == "blocked" and response.get("reason") == "no_dream"
    all_queries_error = stats["observed_query_count"] == EXPECTED_QUERY_COUNT and stats["failed_query_count"] == EXPECTED_QUERY_COUNT
    at_least_one_query_ok = stats["successful_query_count"] >= 1
    accepted_zero = stats["total_accepted_count"] == 0

    if preflight_blocked or timed_out:
        status = INVARIANT_STATUS
    elif child_exit_code == 0 and not errors:
        status = PASS_STATUS
    elif child_exit_code == 3 and response_blocked_no_dream and all_queries_error:
        status = UNAVAILABLE_STATUS
    elif (
        child_exit_code == 3
        and response_blocked_no_dream
        and at_least_one_query_ok
        and stats["failed_query_count"] == 0
        and accepted_zero
        and not request_errors
    ):
        status = NO_RESIDUE_STATUS
    else:
        status = INVARIANT_STATUS

    if status != PASS_STATUS:
        observed_blockers.append(status)
    observed_blockers.extend(errors)

    receipt = {
        "schema": "persona_dream.live_memory_recall_check.v1",
        "created_at": _now_iso(),
        "status": status,
        "run_id": run_id,
        "persona_id": persona_id,
        "about": about,
        "limit": limit,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "command": command,
        "cwd": str(ROOT),
        "python_executable": sys.executable,
        "child_exit_code": child_exit_code,
        "child_duration_s": child_duration_s,
        "processing_time_s": round(time.monotonic() - started, 3),
        "stdout_tail": _tail(stdout),
        "stderr_tail": _tail(stderr),
        "timeout_s": timeout_s,
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "human_content_judgment_required": False,
        "paid_call_authorized": False,
        "provider_live": False,
        "actual_provider_call_attempts": 0,
        "memory_transport": "unix_socket",
        "memory_socket": MEMORY_SOCKET,
        "memory_endpoint": MEMORY_ENDPOINT,
        "expected_query_count": EXPECTED_QUERY_COUNT,
        **stats,
        "request_sha256": artifact_descriptors["dream_request"]["sha256"],
        "response_sha256": artifact_descriptors["response"]["sha256"],
        "residue_links_sha256": artifact_descriptors["residue_links"]["sha256"],
        "dream_packet_sha256": artifact_descriptors["dream_packet"]["sha256"],
        "memory_write_receipt_sha256": artifact_descriptors["memory_write_receipt"]["sha256"],
        "manifest_sha256": artifact_descriptors["manifest"]["sha256"],
        "script_sha256": _sha256(Path(__file__).resolve()),
        "persona_dream_py_sha256": _sha256(SCRIPTS / "persona_dream.py"),
        "run_sh_sha256": _sha256(ROOT / "run.sh"),
        "artifact_descriptors": artifact_descriptors,
        "residue_count": derived["residue_count"],
        "unique_source_count": derived["unique_source_count"],
        "source_ids": derived["source_ids"],
        "scopes": derived["scopes"],
        "duplicate_source_ids": derived["duplicate_source_ids"],
        "fixture_markers_found": derived["fixture_markers_found"],
        "persona_mismatches": derived["persona_mismatches"],
        "lineage_checks": lineage_checks,
        "writeback_checks": derived["writeback_checks"],
        "memory_write_status": derived["memory_write_status"],
        "errors": errors,
        "observed_blockers": sorted(set(observed_blockers)),
        "claims": {
            "proves": [
                "the Persona Dream generator exercised the live Memory /recall client path without fixtures",
                "live recalled residue was normalized into residue_links and preserved into dream_packet lineage",
                "frame prompts and contradiction references resolved to recalled residue source ids",
                "the generator's writeback contract remained skipped under --no-write-memory",
            ]
            if status == PASS_STATUS
            else [
                "the live Memory recall boundary produced an inspectable fail-closed receipt",
            ],
            "does_not_prove": [
                "semantic or psychological quality of the dream",
                "that the recalled memories were the best memories",
                "human preference or acceptance",
                "provider-ready storyboard generation",
                "image, video, voice, or lip-sync generation",
                "paid-provider execution",
                "Memory writeback durability",
                "complete live Phase 01-16 execution",
                "repeatability against an unchanged Memory index",
                "independence from backend mocks not visible to this client",
                "exact raw /recall response-to-item provenance",
            ],
        },
    }
    _write_json(receipt_out, receipt)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--persona", default="embry")
    parser.add_argument("--about")
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--run-id", default=time.strftime("persona-dream-live-memory-%Y%m%dT%H%M%SZ", time.gmtime()))
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--receipt-out", type=Path)
    parser.add_argument("--timeout-s", type=int, default=60)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    output_root = (args.output_root or Path("/tmp") / args.run_id).resolve()
    receipt_out = (args.receipt_out or output_root / "live_memory_recall_receipt.v1.json").resolve()
    receipt = build_receipt(
        persona_id=args.persona,
        about=args.about,
        limit=args.limit,
        run_id=args.run_id,
        output_root=output_root,
        receipt_out=receipt_out,
        timeout_s=args.timeout_s,
    )

    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
