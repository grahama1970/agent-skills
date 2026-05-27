#!/usr/bin/env python3
"""package_phase_review - scripts.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

from phase_status import (
    compute_phase_subject_sha256,
    compute_progress_context_sha256,
    compute_skill_context_sha256,
    default_status,
    load_status,
    save_status,
    status_path,
    validate_status,
)
from continuation_guard import evaluate as evaluate_continuation_guard


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
TEMPLATE_DIR = SKILL_DIR / "templates"


def now_stamp() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def slug(value: str) -> str:
    return "".join(character if character.isalnum() or character in {"-", "_"} else "-" for character in value.strip()).strip("-") or "reviewer"


def plan_id_from_graph(graph: dict[str, Any], fallback_graph_id: str) -> str:
    plan_id = graph.get("plan_id")
    if isinstance(plan_id, str) and plan_id.strip():
        return plan_id.strip()
    return fallback_graph_id.strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@contextlib.contextmanager
def status_update_lock(target_dir: Path) -> Any:
    target_dir.mkdir(parents=True, exist_ok=True)
    lock_path = target_dir / ".PHASE_STATUS.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def phase_dir(root: Path, phase: str) -> Path:
    return root / phase


def _root_relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _upsert_plan_phase_entry(entries: list[dict[str, Any]], entry: dict[str, Any]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    replaced = False
    for existing in entries:
        if isinstance(existing, dict) and existing.get("phase_id") == entry["phase_id"]:
            updated = dict(existing)
            updated.update(entry)
            merged.append(updated)
            replaced = True
        else:
            merged.append(existing)
    if not replaced:
        merged.append(entry)
    return merged


def update_plan_index(
    root: Path,
    target_dir: Path,
    status: dict[str, Any],
    graph_entry: dict[str, Any],
    graph: dict[str, Any],
    recorded_at: str,
) -> None:
    plan_id = str(graph_entry["plan_id"])
    plan_dir = root / "plans" / slug(plan_id)
    plan_dir.mkdir(parents=True, exist_ok=True)
    phase_id = str(status.get("phase_id") or target_dir.name)
    ledger_path = target_dir / "PHASE_STATUS.json"
    phase_entry = {
        "phase_id": phase_id,
        "ledger": _root_relative(ledger_path, root),
        "status": status.get("status", "unknown"),
        "active_plan_graph_artifact": status.get("active_plan_graph_artifact", ""),
        "latest_graph_artifact": _root_relative(target_dir / str(graph_entry["path"]), root),
        "graph_id": graph_entry.get("graph_id", ""),
        "graph_goal": graph.get("graph_goal", ""),
        "updated_at": recorded_at,
    }

    status_path = plan_dir / "PLAN_STATUS.json"
    if status_path.exists():
        try:
            plan_status = json.loads(status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            plan_status = {}
    else:
        plan_status = {}
    if not isinstance(plan_status, dict):
        plan_status = {}
    phases = plan_status.get("phases", [])
    if not isinstance(phases, list):
        phases = []
    phases = _upsert_plan_phase_entry(phases, phase_entry)
    plan_status.update(
        {
            "schema": "plan_iterate.plan_status.v1",
            "plan_id": plan_id,
            "created_at": plan_status.get("created_at") or recorded_at,
            "updated_at": recorded_at,
            "graph_goal": graph.get("graph_goal", plan_status.get("graph_goal", "")),
            "active_phase_id": phase_id,
            "phase_count": len([phase for phase in phases if isinstance(phase, dict)]),
            "phases": phases,
        }
    )
    status_path.write_text(json.dumps(plan_status, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    phases_path = plan_dir / "phases.json"
    phases_payload = {
        "schema": "plan_iterate.plan_phases.v1",
        "plan_id": plan_id,
        "updated_at": recorded_at,
        "phases": phases,
    }
    phases_path.write_text(json.dumps(phases_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_template(name: str) -> str:
    return (TEMPLATE_DIR / name).read_text(encoding="utf-8")


def cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.root)
    target_dir = phase_dir(root, args.phase)
    target_dir.mkdir(parents=True, exist_ok=True)

    status_file = target_dir / "PHASE_STATUS.json"
    if status_file.exists() and not args.force:
        print(f"exists: {status_file}", file=sys.stderr)
        return 2

    status = default_status(args.phase)
    save_status(status_file, status)

    review_file = target_dir / "PHASE_REVIEW_REQUEST.md"
    if args.force or not review_file.exists():
        review_file.write_text(read_template("PHASE_REVIEW_REQUEST.md").replace("__PHASE_ID__", args.phase), encoding="utf-8")

    (target_dir / "validation-logs").mkdir(exist_ok=True)
    (target_dir / "evidence-artifacts").mkdir(exist_ok=True)
    (target_dir / "progress-context").mkdir(exist_ok=True)
    (target_dir / "skill-context").mkdir(exist_ok=True)
    (target_dir / "plan-graphs").mkdir(exist_ok=True)
    (target_dir / "domain-review-loops").mkdir(exist_ok=True)
    (target_dir / "reviews").mkdir(exist_ok=True)
    print(target_dir)
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    target_dir = phase_dir(Path(args.root), args.phase)
    status = load_status(target_dir / "PHASE_STATUS.json")
    errors = validate_status(status, target_dir, Path(args.repo_root))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("valid")
    return 0


def _git_diff_for_files(files: list[Any], repo_root: Path) -> tuple[str, list[str]]:
    diff_parts: list[str] = []
    errors: list[str] = []
    for entry in files:
        if isinstance(entry, str):
            path = entry
        elif isinstance(entry, dict) and isinstance(entry.get("path"), str):
            path = entry["path"]
        else:
            continue
        full_path = repo_root / path
        path_value = Path(path)
        if path_value.is_absolute() or ".." in path_value.parts:
            errors.append(f"changed_files path must be repo-relative and must not contain '..': {path}")
            continue
        tracked = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "--error-unmatch", "--", path],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if tracked.returncode == 0:
            command = ["git", "-C", str(repo_root), "diff", "HEAD", "--", path]
        elif full_path.is_file():
            command = ["git", "diff", "--no-index", "--", "/dev/null", str(full_path)]
        else:
            errors.append(f"changed file not found or not a regular file: {path}")
            continue
        result = subprocess.run(command, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode not in {0, 1}:
            errors.append(f"{' '.join(command)} failed with exit {result.returncode}\n{result.stderr}")
        else:
            diff_parts.append(result.stdout)
    return "\n".join(part for part in diff_parts if part), errors


def _safe_archive_name(artifact_name: str) -> str:
    path = Path(artifact_name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"artifact path must be phase-relative and must not contain '..': {artifact_name}")
    return str(path)


def _artifact_source(phase_root: Path, artifact: Any) -> tuple[Path, str]:
    if isinstance(artifact, str):
        artifact_path = artifact
    elif isinstance(artifact, dict) and isinstance(artifact.get("path"), str):
        artifact_path = artifact["path"]
    else:
        raise ValueError("invalid artifact entry")
    source = Path(artifact_path)
    if not source.is_absolute():
        source = phase_root / artifact_path
    return source, artifact_path


def _zip_add_file(bundle: zipfile.ZipFile, source: Path, arcname: str, entries: list[dict[str, Any]]) -> None:
    if any(entry["path"] == arcname for entry in entries):
        return
    bundle.write(source, arcname)
    entries.append({"path": arcname, "sha256": sha256_file(source), "bytes": source.stat().st_size})


def _unique_artifact_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 1000):
        candidate = path.with_name(f"{path.stem}-{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"could not allocate unique artifact path for {path}")


def cmd_package(args: argparse.Namespace) -> int:
    root = Path(args.root)
    target_dir = phase_dir(root, args.phase)
    status_file = target_dir / "PHASE_STATUS.json"
    status = load_status(status_file)
    errors = validate_status(status, target_dir, Path(args.repo_root))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    diff_text, diff_errors = _git_diff_for_files(status.get("changed_files", []), Path(args.repo_root))
    if diff_errors:
        for error in diff_errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if status.get("changed_files") and not diff_text.strip():
        print("ERROR: changed_files is non-empty but changed-files.diff would be empty", file=sys.stderr)
        return 1
    diff_path = target_dir / "changed-files.diff"
    diff_path.write_text(diff_text, encoding="utf-8")

    manifest_path = target_dir / "manifest.json"
    entries: list[dict[str, Any]] = []

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for source, arcname in [
            (status_file, "PHASE_STATUS.json"),
            (target_dir / "PHASE_REVIEW_REQUEST.md", "PHASE_REVIEW_REQUEST.md"),
            (diff_path, "changed-files.diff"),
        ]:
            if source.exists():
                _zip_add_file(bundle, source, arcname, entries)

        for folder_name in ["validation-logs", "reviews"]:
            folder = target_dir / folder_name
            if folder.exists():
                for source in sorted(path for path in folder.rglob("*") if path.is_file()):
                    _zip_add_file(bundle, source, str(source.relative_to(target_dir)), entries)

        for artifact_key in ["evidence_artifacts", "progress_context_artifacts", "skill_context_artifacts", "plan_graph_artifacts", "review_artifacts"]:
            for artifact in status.get(artifact_key, []):
                source, artifact_name = _artifact_source(target_dir, artifact)
                if source.is_file():
                    arcname = _safe_archive_name(artifact_name)
                    _zip_add_file(bundle, source, arcname, entries)
                if artifact_key == "plan_graph_artifacts" and isinstance(artifact, dict):
                    for sibling_key in ["runtime_readiness_artifact", "plan_ascii_artifact"]:
                        sibling_artifact = artifact.get(sibling_key)
                        if isinstance(sibling_artifact, str) and sibling_artifact.strip():
                            sibling_source = target_dir / sibling_artifact
                            if sibling_source.is_file():
                                _zip_add_file(
                                    bundle,
                                    sibling_source,
                                    _safe_archive_name(sibling_artifact),
                                    entries,
                                )
                    readiness_artifact = artifact.get("runtime_readiness_artifact")
                    if isinstance(readiness_artifact, str) and readiness_artifact.strip():
                        readiness_source = target_dir / readiness_artifact
                        if readiness_source.is_file() and not any(entry["path"] == _safe_archive_name(readiness_artifact) for entry in entries):
                            _zip_add_file(
                                bundle,
                                readiness_source,
                                _safe_archive_name(readiness_artifact),
                                entries,
                            )

        plan_id = status.get("plan_id")
        if isinstance(plan_id, str) and plan_id.strip():
            plan_index_dir = Path(args.root) / "plans" / slug(plan_id)
            for source_name in ["PLAN_STATUS.json", "phases.json"]:
                source = plan_index_dir / source_name
                if source.is_file():
                    _zip_add_file(bundle, source, f"plans/{slug(plan_id)}/{source_name}", entries)

        manifest = {
            "schema": "plan_iterate.review_bundle_manifest.v1",
            "phase_id": args.phase,
            "plan_id": plan_id if isinstance(plan_id, str) else "",
            "created_at": now_stamp(),
            "status_sha256": sha256_file(status_file),
            "entries": entries,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _zip_add_file(bundle, manifest_path, "manifest.json", entries)

    print(output)
    return 0


def cmd_record_review(args: argparse.Namespace) -> int:
    root = Path(args.root)
    target_dir = phase_dir(root, args.phase)
    status_file = target_dir / "PHASE_STATUS.json"
    status = load_status(status_file)
    normalized_verdict = "pass" if args.verdict == "passed" else args.verdict
    review_status = "passed" if normalized_verdict == "pass" else normalized_verdict

    review_source = Path(args.review)
    if not review_source.exists():
        print(f"review file missing: {review_source}", file=sys.stderr)
        return 1
    review_request = Path(args.review_request)
    if not review_request.exists():
        print(f"review request file missing: {review_request}", file=sys.stderr)
        return 1
    review_bundle = Path(args.review_bundle)
    if not review_bundle.exists():
        print(f"review bundle file missing: {review_bundle}", file=sys.stderr)
        return 1
    invocation_receipt = Path(args.invocation_receipt)
    if not invocation_receipt.exists():
        print(f"invocation receipt file missing: {invocation_receipt}", file=sys.stderr)
        return 1
    try:
        source_receipt = json.loads(invocation_receipt.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"invocation receipt must be JSON: {exc}", file=sys.stderr)
        return 1
    if not isinstance(source_receipt, dict):
        print("invocation receipt must contain a JSON object", file=sys.stderr)
        return 1

    reviews_dir = target_dir / "reviews"
    reviews_dir.mkdir(exist_ok=True)
    recorded_at = now_stamp()
    reviewer_id = slug(args.reviewer)
    copied_review = _unique_artifact_path(reviews_dir / f"{recorded_at}-{reviewer_id}-response.md")
    copied_request = _unique_artifact_path(reviews_dir / f"{recorded_at}-{reviewer_id}-request{review_request.suffix or '.txt'}")
    copied_bundle = _unique_artifact_path(reviews_dir / f"{recorded_at}-{reviewer_id}-bundle{review_bundle.suffix or '.zip'}")
    copied_receipt = _unique_artifact_path(reviews_dir / f"{recorded_at}-{reviewer_id}-invocation{invocation_receipt.suffix or '.json'}")
    shutil.copyfile(review_source, copied_review)
    shutil.copyfile(review_request, copied_request)
    shutil.copyfile(review_bundle, copied_bundle)
    response_sha256 = sha256_file(copied_review)
    request_sha256 = sha256_file(copied_request)
    bundle_sha256 = sha256_file(copied_bundle)
    phase_subject_sha256 = compute_phase_subject_sha256(status)
    progress_context_sha256 = compute_progress_context_sha256(status, target_dir)
    skill_context_sha256 = compute_skill_context_sha256(status, target_dir)
    if skill_context_sha256 is None:
        print(
            "skill context missing: reviews require skill_context_artifacts with the headless skill contract",
            file=sys.stderr,
        )
        return 1
    if status.get("review_results") and progress_context_sha256 is None:
        print(
            "progress context missing: non-first reviews require progress_context_artifacts or memory_context.keys",
            file=sys.stderr,
        )
        return 1
    expected_receipt_bindings = {
        "reviewer_id": args.reviewer,
        "adjudicator_kind": args.adjudicator_kind,
        "request_sha256": request_sha256,
        "response_sha256": response_sha256,
        "review_bundle_sha256": bundle_sha256,
        "phase_subject_sha256": phase_subject_sha256,
        "skill_context_sha256": skill_context_sha256,
    }
    if progress_context_sha256 is not None:
        expected_receipt_bindings["progress_context_sha256"] = progress_context_sha256
    mismatches = [
        f"{key}={source_receipt.get(key)!r} expected {expected_value!r}"
        for key, expected_value in expected_receipt_bindings.items()
        if source_receipt.get(key) != expected_value
    ]
    if mismatches:
        print("invocation receipt binding mismatch:", file=sys.stderr)
        for mismatch in mismatches:
            print(f"ERROR: {mismatch}", file=sys.stderr)
        return 1
    shutil.copyfile(invocation_receipt, copied_receipt)

    candidate_status = json.loads(json.dumps(status))
    candidate_status["review_status"] = review_status
    reviewer_policy = candidate_status.setdefault(
        "reviewer_policy",
        {
            "required": True,
            "comparison_required": False,
            "closure_rule": "deterministic_validation_and_external_review",
        },
    )
    if normalized_verdict in {"blocked", "needs_changes", "conditional_pass", "insufficient_evidence", "malformed", "no_verdict"}:
        candidate_status["status"] = "external_review_blocked"
    elif normalized_verdict == "pass" and not reviewer_policy.get("comparison_required", False):
        candidate_status["status"] = "external_review_passed"

    candidate_status.setdefault("review_artifacts", [])
    relative_review = str(copied_review.relative_to(target_dir))
    relative_request = str(copied_request.relative_to(target_dir))
    relative_bundle = str(copied_bundle.relative_to(target_dir))
    relative_receipt = str(copied_receipt.relative_to(target_dir))
    for review_artifact in [relative_review, relative_request, relative_bundle, relative_receipt]:
        if review_artifact not in candidate_status["review_artifacts"]:
            candidate_status["review_artifacts"].append(review_artifact)

    candidate_status.setdefault("review_results", [])
    if normalized_verdict == "pass":
        for prior_result in candidate_status["review_results"]:
            if not isinstance(prior_result, dict):
                continue
            if prior_result.get("verdict") in {"blocked", "needs_changes", "conditional_pass", "insufficient_evidence", "malformed", "no_verdict"} and prior_result.get("resolution_status") is None:
                prior_result["resolution_status"] = "resolved_by_later_pass"
                prior_result["resolved_by_reviewer_id"] = args.reviewer
                prior_result["resolved_by_recorded_at"] = recorded_at
            elif prior_result.get("verdict") == "pass" and prior_result.get("resolution_status") is None:
                prior_result["resolution_status"] = "superseded_by_later_pass"
                prior_result["resolved_by_reviewer_id"] = args.reviewer
                prior_result["resolved_by_recorded_at"] = recorded_at
    candidate_status["review_results"].append(
        {
            "reviewer_id": args.reviewer,
            "adjudicator_kind": args.adjudicator_kind,
            "verdict": normalized_verdict,
            "artifact": relative_review,
            "artifact_sha256": response_sha256,
            "source_review_path": str(review_source),
            "source_review_sha256": sha256_file(review_source),
            "review_request_artifact": relative_request,
            "review_request_sha256": request_sha256,
            "review_bundle_artifact": relative_bundle,
            "review_bundle_sha256": bundle_sha256,
            "phase_subject_sha256": phase_subject_sha256,
            "skill_context_sha256": skill_context_sha256,
            **({"progress_context_sha256": progress_context_sha256} if progress_context_sha256 is not None else {}),
            "invocation": {
                "tool": args.adjudicator_kind,
                "command_or_run_id": args.invocation_command,
                "receipt_artifact": relative_receipt,
                "receipt_sha256": sha256_file(copied_receipt),
                "model": args.model,
            },
            "recorded_at": recorded_at,
        }
    )

    if not reviewer_policy.get("comparison_required", False):
        candidate_status["review_comparison"] = {
            "agreement": "agree" if normalized_verdict == "pass" else "disagree",
            "closure_allowed": normalized_verdict == "pass",
            "reason": "single external reviewer recorded; accepted still requires deterministic validation",
        }
    else:
        candidate_status.setdefault(
            "review_comparison",
            {
                "agreement": "pending",
                "closure_allowed": False,
                "reason": "comparison_required=true; record an explicit reviewer comparison before accepting",
            },
        )

    errors = validate_status(candidate_status, target_dir, Path(args.repo_root))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    save_status(status_file, candidate_status)
    print(copied_review)
    return 0


def _upsert_memory_context(collection: str, document: dict[str, Any]) -> None:
    try:
        import httpx  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("httpx is required for --memory-upsert") from exc

    transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
    with httpx.Client(transport=transport, base_url="http://localhost", timeout=10.0) as client:
        response = client.post("/upsert", json={"collection": collection, "documents": [document]})
        response.raise_for_status()


def cmd_record_context(args: argparse.Namespace) -> int:
    root = Path(args.root)
    target_dir = phase_dir(root, args.phase)
    status_file = target_dir / "PHASE_STATUS.json"
    status = load_status(status_file)

    source = Path(args.context)
    if not source.exists():
        print(f"context file missing: {source}", file=sys.stderr)
        return 1

    progress_dir = target_dir / "progress-context"
    progress_dir.mkdir(exist_ok=True)
    recorded_at = now_stamp()
    copied_context = progress_dir / f"{recorded_at}-progress-context{source.suffix or '.md'}"
    shutil.copyfile(source, copied_context)
    relative_context = str(copied_context.relative_to(target_dir))
    context_sha256 = sha256_file(copied_context)

    candidate_status = json.loads(json.dumps(status))
    candidate_status.setdefault("progress_context_artifacts", [])
    context_entry = {"path": relative_context, "sha256": context_sha256}
    if context_entry not in candidate_status["progress_context_artifacts"]:
        candidate_status["progress_context_artifacts"].append(context_entry)

    memory_key = args.memory_key or f"{args.phase}-{recorded_at}"
    memory_context = candidate_status.setdefault(
        "memory_context",
        {"collection": args.memory_collection, "keys": []},
    )
    memory_context["collection"] = args.memory_collection
    memory_context.setdefault("keys", [])
    if memory_key not in memory_context["keys"]:
        memory_context["keys"].append(memory_key)

    if not args.skip_memory_upsert:
        document = {
            "_key": memory_key,
            "schema": "plan_iterate.phase_context.v1",
            "phase_id": args.phase,
            "created_at": recorded_at,
            "context_sha256": context_sha256,
            "source_artifact": relative_context,
            "context": copied_context.read_text(encoding="utf-8"),
            "tags": ["plan-iterate", "scillm", "phase-context"],
        }
        try:
            _upsert_memory_context(args.memory_collection, document)
        except Exception as exc:
            print(f"memory upsert failed: {exc}", file=sys.stderr)
            return 1

    errors = validate_status(candidate_status, target_dir, Path(args.repo_root))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    save_status(status_file, candidate_status)
    print(copied_context)
    return 0


def cmd_record_skill_context(args: argparse.Namespace) -> int:
    root = Path(args.root)
    target_dir = phase_dir(root, args.phase)
    status_file = target_dir / "PHASE_STATUS.json"
    status = load_status(status_file)

    source = Path(args.context)
    if not source.exists():
        print(f"skill context file missing: {source}", file=sys.stderr)
        return 1

    skill_dir = target_dir / "skill-context"
    skill_dir.mkdir(exist_ok=True)
    recorded_at = now_stamp()
    copied_context = skill_dir / f"{recorded_at}-headless-skill-context{source.suffix or '.md'}"
    shutil.copyfile(source, copied_context)
    relative_context = str(copied_context.relative_to(target_dir))
    context_sha256 = sha256_file(copied_context)

    candidate_status = json.loads(json.dumps(status))
    candidate_status.setdefault("skill_context_artifacts", [])
    context_entry = {"path": relative_context, "sha256": context_sha256}
    if context_entry not in candidate_status["skill_context_artifacts"]:
        candidate_status["skill_context_artifacts"].append(context_entry)

    errors = validate_status(candidate_status, target_dir, Path(args.repo_root))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    save_status(status_file, candidate_status)
    print(copied_context)
    return 0


def _phase_relative_copy(target_dir: Path, source_value: str, loop_dir: Path) -> str:
    source = Path(source_value)
    if not source.is_absolute():
        phase_candidate = target_dir / source
        if phase_candidate.exists() and phase_candidate.is_file():
            _safe_archive_name(str(source))
            return str(source)
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"domain loop artifact missing: {source_value}")
    loop_dir.mkdir(parents=True, exist_ok=True)
    target = loop_dir / source.name
    if source.resolve() != target.resolve():
        shutil.copyfile(source, target)
    return str(target.relative_to(target_dir))


def _append_unique_path(paths: list[Any], path_value: str) -> None:
    for path in paths:
        if path == path_value:
            return
        if isinstance(path, dict) and path.get("path") == path_value:
            return
    paths.append(path_value)


def _validate_plan_graph_payload(graph: Any) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    metrics = {
        "plan_id": "",
        "graph_id": "",
        "node_count": 0,
        "review_scope_count": 0,
        "review_node_count": 0,
        "self_improvement_iterations": 0,
        "review_fanout_limits": {},
        "review_iteration_limits": {},
    }
    if not isinstance(graph, dict):
        return ["plan graph must contain a JSON object"], metrics

    graph_id = graph.get("graph_id")
    if not isinstance(graph_id, str) or not graph_id.strip():
        errors.append("plan graph graph_id must be non-empty")
    else:
        metrics["graph_id"] = graph_id
        metrics["plan_id"] = plan_id_from_graph(graph, graph_id)

    if graph.get("plan_id", "") not in {"", None} and (not isinstance(graph.get("plan_id"), str) or not str(graph.get("plan_id")).strip()):
        errors.append("plan graph plan_id must be non-empty when set")

    if not isinstance(graph.get("exec_graph_version"), str) or not str(graph.get("exec_graph_version")).strip():
        errors.append("plan graph exec_graph_version must be non-empty")
    if not isinstance(graph.get("graph_goal"), str) or not str(graph.get("graph_goal")).strip():
        errors.append("plan graph graph_goal must be non-empty")

    iterations = graph.get("self_improvement_iterations")
    if not isinstance(iterations, int) or iterations < 1:
        errors.append("plan graph self_improvement_iterations must be a positive integer")
    else:
        metrics["self_improvement_iterations"] = iterations

    iteration_limits = graph.get("review_iteration_limits")
    if iteration_limits is None:
        iteration_limits = {}
    if not isinstance(iteration_limits, dict):
        errors.append("plan graph review_iteration_limits must be an object when set")
        iteration_limits = {}
    normalized_iteration_limits: dict[str, int] = {}
    for key in ["review_code", "review_design", "review_prompt"]:
        value = iteration_limits.get(key, iterations if isinstance(iterations, int) and iterations > 0 else None)
        if not isinstance(value, int) or value < 0:
            errors.append(f"plan graph review_iteration_limits.{key} must be a non-negative integer")
        else:
            normalized_iteration_limits[key] = value
    metrics["review_iteration_limits"] = normalized_iteration_limits

    fanout_limits = graph.get("review_fanout_limits")
    if not isinstance(fanout_limits, dict):
        errors.append("plan graph review_fanout_limits must be an object")
        fanout_limits = {}
    normalized_limits: dict[str, int] = {}
    for key in ["review_code", "review_design", "review_prompt"]:
        value = fanout_limits.get(key)
        if not isinstance(value, int) or value < 0:
            errors.append(f"plan graph review_fanout_limits.{key} must be a non-negative integer")
        else:
            normalized_limits[key] = value
    metrics["review_fanout_limits"] = normalized_limits

    nodes = graph.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return [*errors, "plan graph nodes must be a non-empty list"], metrics
    metrics["node_count"] = len(nodes)

    ids: set[str] = set()
    deps_by_id: dict[str, list[str]] = {}
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            errors.append(f"plan graph nodes[{index}] must be an object")
            continue
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id.strip():
            errors.append(f"plan graph nodes[{index}].id must be non-empty")
            continue
        if node_id in ids:
            errors.append(f"plan graph duplicate node id: {node_id}")
        ids.add(node_id)
        if not isinstance(node.get("type"), str) or not str(node.get("type")).strip():
            errors.append(f"plan graph node {node_id}.type must be non-empty")
        if not isinstance(node.get("node_goal"), str) or not str(node.get("node_goal")).strip():
            errors.append(f"plan graph node {node_id}.node_goal must be non-empty")
        depends_on = node.get("depends_on", [])
        if depends_on is None:
            depends_on = []
        if not isinstance(depends_on, list):
            errors.append(f"plan graph node {node_id}.depends_on must be a list when set")
            depends_on = []
        clean_deps: list[str] = []
        for dep_index, dependency in enumerate(depends_on):
            if not isinstance(dependency, str) or not dependency.strip():
                errors.append(f"plan graph node {node_id}.depends_on[{dep_index}] must be non-empty")
                continue
            if dependency == node_id:
                errors.append(f"plan graph node {node_id} cannot depend on itself")
            clean_deps.append(dependency)
        deps_by_id[node_id] = clean_deps

        review_like = "review-code" in str(node.get("type", "")) or "review-code" in node_id
        review_scopes = node.get("review_scopes", [])
        if review_scopes is None:
            review_scopes = []
        if review_like:
            metrics["review_node_count"] += 1
            if not isinstance(review_scopes, list) or not review_scopes:
                errors.append(f"plan graph review-code node {node_id} must include review_scopes")
        if review_scopes:
            if not isinstance(review_scopes, list):
                errors.append(f"plan graph node {node_id}.review_scopes must be a list")
                continue
            for scope_index, scope in enumerate(review_scopes):
                if not isinstance(scope, dict):
                    errors.append(f"plan graph node {node_id}.review_scopes[{scope_index}] must be an object")
                    continue
                metrics["review_scope_count"] += 1
                for key in ["scope", "model", "agent", "contract", "review_level", "proof_level"]:
                    if not isinstance(scope.get(key), str) or not str(scope.get(key)).strip():
                        errors.append(f"plan graph node {node_id}.review_scopes[{scope_index}].{key} must be non-empty")
                best_practice_skills = scope.get("best_practice_skills")
                if not isinstance(best_practice_skills, list) or not best_practice_skills:
                    errors.append(f"plan graph node {node_id}.review_scopes[{scope_index}].best_practice_skills must be a non-empty list")
                else:
                    for skill_index, skill_name in enumerate(best_practice_skills):
                        if not isinstance(skill_name, str) or not skill_name.strip():
                            errors.append(f"plan graph node {node_id}.review_scopes[{scope_index}].best_practice_skills[{skill_index}] must be non-empty")
                        elif not skill_name.startswith("best-practices-"):
                            errors.append(f"plan graph node {node_id}.review_scopes[{scope_index}].best_practice_skills[{skill_index}] must name a best-practices-* skill")

    for node_id, dependencies in deps_by_id.items():
        for dependency in dependencies:
            if dependency not in ids:
                errors.append(f"plan graph node {node_id} depends on missing node: {dependency}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str, stack: list[str]) -> None:
        if node_id in visited:
            return
        if node_id in visiting:
            errors.append(f"plan graph contains cycle: {' -> '.join([*stack, node_id])}")
            return
        visiting.add(node_id)
        for dependency in deps_by_id.get(node_id, []):
            if dependency in ids:
                visit(dependency, [*stack, node_id])
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in sorted(ids):
        visit(node_id, [])

    return errors, metrics


RUNTIME_NODE_TYPES = {
    "local_command",
    "deterministic_render",
    "deterministic_verifier",
    "scillm_call",
    "scillm_batch",
    "codex_exec",
    "claude_print",
}


def _node_value(node: dict[str, Any], key: str) -> Any:
    if key in node:
        return node.get(key)
    for container_key in ["runtime", "input", "inputs", "metadata"]:
        container = node.get(container_key)
        if isinstance(container, dict) and key in container:
            return container.get(key)
    return None


def _node_text_value(node: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = _node_value(node, key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _has_value(node: dict[str, Any], *keys: str) -> bool:
    for key in keys:
        value = _node_value(node, key)
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, list) and value:
            return True
        if isinstance(value, dict) and value:
            return True
        if isinstance(value, bool):
            return True
        if isinstance(value, int):
            return True
    return False


def _changed_file_paths(status: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    changed_files = status.get("changed_files", [])
    if not isinstance(changed_files, list):
        return paths
    for changed_file in changed_files:
        if isinstance(changed_file, str) and changed_file.strip():
            paths.append(changed_file)
        elif isinstance(changed_file, dict) and isinstance(changed_file.get("path"), str) and changed_file["path"].strip():
            paths.append(changed_file["path"])
    return paths


def _scope_missing_fields(scope: Any, prefix: str) -> list[str]:
    missing: list[str] = []
    if not isinstance(scope, dict):
        return [prefix]
    for key in ["scope", "model", "agent", "contract", "review_level", "proof_level"]:
        value = scope.get(key)
        if not isinstance(value, str) or not value.strip():
            missing.append(f"{prefix}.{key}")
    best_practice_skills = scope.get("best_practice_skills")
    if not isinstance(best_practice_skills, list) or not best_practice_skills:
        missing.append(f"{prefix}.best_practice_skills")
    return missing


def _analyze_node_runtime_readiness(node: dict[str, Any], status: dict[str, Any]) -> dict[str, Any]:
    node_id = str(node.get("id", ""))
    node_type = str(node.get("type", ""))
    required_fields: list[str] = []
    present_fields: list[str] = []
    missing_fields: list[str] = []
    inferred_fields: list[dict[str, Any]] = []
    missing_artifacts: list[str] = []
    adapter = "semantic:unmapped"
    status_value = "blocked_missing_fields"
    next_action = "add an explicit runtime adapter or handoff contract"

    def require(field: str, *aliases: str) -> None:
        names = (field, *aliases)
        required_fields.append(field if not aliases else f"{field} ({', '.join(aliases)})")
        if _has_value(node, *names):
            present_fields.append(field)
        else:
            missing_fields.append(field)

    if node_type in RUNTIME_NODE_TYPES:
        adapter = f"scillm_exec:{node_type}"
        if node_type in {"local_command", "deterministic_render", "deterministic_verifier"}:
            require("command")
        elif node_type == "scillm_call":
            require("model")
            require("prompt", "messages", "prompt_path")
        elif node_type == "scillm_batch":
            require("model", "model_pool")
            require("items", "manifest_path")
        elif node_type in {"codex_exec", "claude_print"}:
            require("prompt", "prompt_path", "instruction")
        next_action = "compile or submit this runtime node after required fields are present"
    elif node_type == "review-code":
        adapter = "review-code:one-shot"
        require("context", "context_file", "review_bundle", "review_bundle_artifact")
        required_fields.append("files (review_files, files, target_files, or phase changed_files)")
        if _has_value(node, "review_files", "files", "target_files"):
            present_fields.append("files")
        else:
            changed_paths = _changed_file_paths(status)
            if changed_paths:
                present_fields.append("files")
                inferred_fields.append(
                    {
                        "field": "files",
                        "source": "PHASE_STATUS.changed_files",
                        "value": changed_paths,
                    }
                )
            else:
                missing_fields.append("files")
        review_scopes = node.get("review_scopes")
        required_fields.append("review_scopes[].scope/model/agent/contract/review_level/proof_level/best_practice_skills")
        if isinstance(review_scopes, list) and review_scopes:
            present_fields.append("review_scopes")
            for scope_index, scope in enumerate(review_scopes):
                missing_fields.extend(_scope_missing_fields(scope, f"review_scopes[{scope_index}]"))
        else:
            missing_fields.append("review_scopes")
        next_action = "provide review context and files, then run review-code fanout"
    elif node_type == "test-interactions":
        adapter = "test-interactions:run-or-full"
        required_fields.append("manifest or url")
        if _has_value(node, "manifest", "manifest_path"):
            present_fields.append("manifest")
        elif _has_value(node, "url", "base_url"):
            present_fields.append("url")
            required_fields.append("persona")
            if _has_value(node, "persona", "persona_file"):
                present_fields.append("persona")
            else:
                missing_fields.append("persona")
        else:
            missing_fields.append("manifest_or_url")
        require("output_dir", "output", "artifact_dir")
        next_action = "supply a test-interactions manifest or URL/persona pair"
    elif node_type == "review-design":
        adapter = "review-design:iterate-or-review"
        require("persona", "persona_file")
        required_fields.append("manifest or screenshots")
        if _has_value(node, "manifest", "manifest_path"):
            present_fields.append("manifest")
        elif _has_value(node, "screenshots", "screenshot", "screenshot_dir"):
            present_fields.append("screenshots")
        else:
            missing_fields.append("manifest_or_screenshots")
        require("output_dir", "output", "artifact_dir")
        next_action = "provide persona plus screenshots or a test-interactions manifest"
    elif node_type == "review-prompt":
        adapter = "review-prompt:review"
        require("template", "template_path", "prompt", "prompt_path")
        require("context", "context_file", "fixture", "fixture_path")
        require("expected_response", "expected_response_path", "expected_output")
        require("validator_or_smoke", "validator", "validator_command", "smoke_command")
        require("consumer_or_schema", "consumer", "consumer_code", "schema", "schema_path")
        next_action = "complete the prompt-review bundle before reviewer calls"
    elif node_type == "plan-iterate":
        adapter = "plan-iterate:ledger"
        required_fields.append("phase")
        if _has_value(node, "phase", "phase_id"):
            present_fields.append("phase")
        else:
            present_fields.append("phase")
            inferred_fields.append({"field": "phase", "source": "CLI --phase", "value": status.get("phase_id", "")})
        action = _node_value(node, "action")
        if isinstance(action, str) and action.strip():
            present_fields.append("action")
        status_value = "runtime_ready"
        next_action = "plan-iterate can validate or package the current phase ledger"
    elif node_type == "project-agent":
        adapter = "project-agent:manual"
        required_fields.extend(["command_or_handoff", "acceptance_evidence"])
        has_runtime_command = _has_value(node, "command")
        if _has_value(node, "command", "handoff", "prompt", "task"):
            present_fields.append("command_or_handoff")
        else:
            missing_fields.append("command_or_handoff")
        if _has_value(node, "acceptance_evidence", "evidence_artifacts", "expected_artifacts"):
            present_fields.append("acceptance_evidence")
        else:
            missing_fields.append("acceptance_evidence")
        if not missing_fields and has_runtime_command:
            adapter = "project-agent:local_command"
            status_value = "runtime_ready"
            next_action = "compile the explicit project-agent command into the runtime graph"
        else:
            status_value = "manual_action_required"
            next_action = "make the project-agent work item explicit before compiling this DAG"
    else:
        required_fields.append("runtime.type or adapter")
        if _has_value(node, "runtime", "adapter", "command"):
            present_fields.append("runtime.type or adapter")
            status_value = "runtime_ready"
            next_action = "adapter is present; compiler must map it explicitly"
        else:
            missing_fields.append("runtime.type_or_adapter")

    if node_type != "project-agent":
        status_value = "runtime_ready" if not missing_fields and not missing_artifacts else "blocked_missing_fields"

    return {
        "node_id": node_id,
        "type": node_type,
        "adapter": adapter,
        "status": status_value,
        "required_fields": required_fields,
        "present_fields": sorted(set(present_fields)),
        "missing_fields": sorted(set(missing_fields)),
        "inferred_fields": inferred_fields,
        "missing_artifacts": missing_artifacts,
        "next_action": next_action,
    }


SEMANTIC_COMPILE_NODE_TYPES = {
    "project-agent": "project-agent:local_command",
    "review-code": "review-code:local_command",
    "review-design": "review-design:local_command",
    "review-prompt": "review-prompt:local_command",
    "test-interactions": "test-interactions:local_command",
}


def _copy_runtime_fields(node: dict[str, Any]) -> dict[str, Any]:
    compiled: dict[str, Any] = {}
    for key in [
        "id",
        "type",
        "depends_on",
        "graph_goal",
        "node_goal",
        "persona_ref",
        "persona_text",
        "protocol_role",
        "forbidden_decisions",
        "model",
        "model_pool",
        "reasoning_effort",
        "cwd",
        "sandbox",
        "worktree",
        "env",
        "messages",
        "prompt",
        "prompt_path",
        "command",
        "review_scopes",
        "items",
        "manifest_path",
        "concurrency",
        "output_schema",
        "output_schema_path",
        "timeout_s",
        "idle_timeout_s",
        "retry_policy",
        "allow_failure",
        "template_id",
        "template_version",
        "template_sha256",
        "catalog_id",
        "catalog_version",
        "catalog_sha256",
        "inline_overrides",
        "metadata",
    ]:
        if key in node:
            compiled[key] = node[key]
    return compiled


def compile_plan_graph_to_exec_graph(graph: dict[str, Any], status: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    """Compile a plan-iterate semantic DAG into a scillm exec runtime DAG.

    The compiler is intentionally conservative. Runtime node types pass through.
    Semantic review/project-agent nodes compile only when their plan-iterate
    readiness fields are present and the node includes an explicit command that
    can be audited and executed by scillm exec as a local_command.
    """

    graph_errors, _metrics = _validate_plan_graph_payload(graph)
    if graph_errors:
        return None, graph_errors

    readiness = analyze_plan_graph_runtime_readiness(graph, status)
    missing_by_node = readiness.get("summary", {}).get("missing_fields_by_node", {})
    errors: list[str] = []
    if isinstance(missing_by_node, dict):
        for node_id, missing_fields in sorted(missing_by_node.items()):
            if missing_fields:
                errors.append(f"node {node_id} is not runtime-ready: missing {', '.join(str(item) for item in missing_fields)}")

    compiled_nodes: list[dict[str, Any]] = []
    for node in graph.get("nodes", []):
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id", ""))
        node_type = str(node.get("type", ""))
        if node_type in RUNTIME_NODE_TYPES:
            compiled_nodes.append(_copy_runtime_fields(node))
            continue

        if node_type == "plan-iterate":
            action = _node_text_value(node, "action") or "validate"
            phase_id = _node_text_value(node, "phase", "phase_id") or str(status.get("phase_id", ""))
            raw_command = _node_value(node, "command")
            if isinstance(raw_command, list) and raw_command:
                command: str | list[str] = raw_command
            elif isinstance(raw_command, str) and raw_command.strip():
                command = raw_command.strip()
            else:
                errors.append(
                    f"node {node_id} cannot compile: plan-iterate action {action!r} for phase {phase_id!r} requires an explicit container-safe command"
                )
                continue
            compiled = _copy_runtime_fields(node)
            compiled.update(
                {
                    "type": "local_command",
                    "command": command,
                    "metadata": {
                        **(node.get("metadata") if isinstance(node.get("metadata"), dict) else {}),
                        "semantic_type": node_type,
                        "compiled_adapter": "plan-iterate:local_command",
                    },
                }
            )
            compiled_nodes.append(compiled)
            continue

        adapter = SEMANTIC_COMPILE_NODE_TYPES.get(node_type)
        if adapter is None:
            errors.append(f"node {node_id} has no plan-iterate compiler adapter for type {node_type!r}")
            continue

        command = _node_value(node, "command")
        if isinstance(command, list) and command:
            command_value: str | list[str] = command
        elif isinstance(command, str) and command.strip():
            command_value = command.strip()
        else:
            errors.append(f"node {node_id} cannot compile: semantic type {node_type!r} requires an explicit command")
            continue

        compiled = _copy_runtime_fields(node)
        compiled.update(
            {
                "type": "local_command",
                "command": command_value,
                "metadata": {
                    **(node.get("metadata") if isinstance(node.get("metadata"), dict) else {}),
                    "semantic_type": node_type,
                    "compiled_adapter": adapter,
                },
            }
        )
        compiled_nodes.append(compiled)

    if errors:
        return None, errors

    runtime_graph = {
        "exec_graph_version": "scillm.exec.graph.v1",
        "graph_id": f"{graph.get('graph_id', status.get('phase_id', 'plan'))}-runtime",
        "graph_goal": graph.get("graph_goal", ""),
        "cwd": graph.get("cwd"),
        "model": graph.get("model"),
        "sandbox": graph.get("sandbox", "read-only"),
        "max_concurrency": graph.get("max_concurrency", 4),
        "stream": graph.get("stream", False),
        "self_improvement_iterations": graph.get("self_improvement_iterations"),
        "review_fanout_limits": graph.get("review_fanout_limits", {}),
        "review_iteration_limits": graph.get("review_iteration_limits", {}),
        "metadata": {
            **(graph.get("metadata") if isinstance(graph.get("metadata"), dict) else {}),
            "source_graph_id": graph.get("graph_id", ""),
            "source_phase_id": status.get("phase_id", ""),
            "compiled_by": "plan-iterate.compile-plan-graph",
        },
        "personas": graph.get("personas", {}),
        "nodes": compiled_nodes,
    }
    return {key: value for key, value in runtime_graph.items() if value is not None}, []


def analyze_plan_graph_runtime_readiness(graph: dict[str, Any], status: dict[str, Any]) -> dict[str, Any]:
    nodes = graph.get("nodes", [])
    node_reports: list[dict[str, Any]] = []
    if isinstance(nodes, list):
        for node in nodes:
            if isinstance(node, dict):
                node_reports.append(_analyze_node_runtime_readiness(node, status))
    blocked_nodes = [
        report["node_id"]
        for report in node_reports
        if report.get("status") == "blocked_missing_fields"
    ]
    manual_nodes = [
        report["node_id"]
        for report in node_reports
        if report.get("status") == "manual_action_required"
    ]
    ready_nodes = [
        report["node_id"]
        for report in node_reports
        if report.get("status") == "runtime_ready"
    ]
    missing_fields_by_node = {
        str(report["node_id"]): report.get("missing_fields", [])
        for report in node_reports
        if report.get("missing_fields")
    }
    return {
        "schema": "plan_iterate.graph_runtime_readiness.v1",
        "graph_id": graph.get("graph_id", ""),
        "graph_goal": graph.get("graph_goal", ""),
        "phase_id": status.get("phase_id", ""),
        "created_at": now_stamp(),
        "can_execute_runtime": not blocked_nodes and not manual_nodes,
        "summary": {
            "node_count": len(node_reports),
            "runtime_ready_node_count": len(ready_nodes),
            "blocked_node_count": len(blocked_nodes),
            "manual_node_count": len(manual_nodes),
            "blocked_nodes": blocked_nodes,
            "manual_nodes": manual_nodes,
            "missing_fields_by_node": missing_fields_by_node,
        },
        "nodes": node_reports,
    }


def _node_dependencies(node: dict[str, Any]) -> list[str]:
    depends_on = node.get("depends_on", [])
    if depends_on is None:
        return []
    if not isinstance(depends_on, list):
        return []
    return [dependency for dependency in depends_on if isinstance(dependency, str) and dependency.strip()]


def _node_completion_state(node: dict[str, Any], status: dict[str, Any]) -> str:
    node_id = str(node.get("id", ""))
    explicit_state = node.get("completion_status", node.get("phase_status", node.get("state", "")))
    if isinstance(explicit_state, str):
        normalized = explicit_state.strip().lower()
        if normalized in {"accepted", "complete", "completed"}:
            return "completed"
        if normalized in {"blocked", "failed", "local_validation_failed", "external_review_blocked"}:
            return "blocked"
        if normalized in {"implementing", "running", "in_progress", "ready_for_review", "external_review_passed"}:
            return "active"
        if normalized in {"planned", "pending", "not_started"}:
            return "pending"
    completed_nodes = status.get("completed_plan_nodes", [])
    if isinstance(completed_nodes, list) and node_id in completed_nodes:
        return "completed"
    active_phase_id = str(status.get("phase_id", ""))
    active_phase_state = str(status.get("status", ""))
    if node_id == active_phase_id:
        if active_phase_state == "accepted":
            return "completed"
        if active_phase_state in {"local_validation_failed", "external_review_blocked"}:
            return "blocked"
        if active_phase_state in {"implementing", "ready_for_review", "external_review_passed"}:
            return "active"
    return "pending"


def _plan_graph_layers(graph: dict[str, Any]) -> list[list[str]]:
    nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict) and isinstance(node.get("id"), str)]
    ids = {str(node["id"]) for node in nodes}
    deps_by_id = {str(node["id"]): [dependency for dependency in _node_dependencies(node) if dependency in ids] for node in nodes}
    remaining = set(ids)
    completed_layers: list[list[str]] = []
    while remaining:
        ready = sorted(node_id for node_id in remaining if all(dependency not in remaining for dependency in deps_by_id.get(node_id, [])))
        if not ready:
            completed_layers.append(sorted(remaining))
            break
        completed_layers.append(ready)
        remaining.difference_update(ready)
    return completed_layers


def render_plan_ascii(graph: dict[str, Any], status: dict[str, Any], readiness: dict[str, Any]) -> str:
    nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
    node_by_id = {str(node.get("id", "")): node for node in nodes if str(node.get("id", "")).strip()}
    readiness_by_id = {
        str(node_report.get("node_id", "")): node_report
        for node_report in readiness.get("nodes", [])
        if isinstance(node_report, dict)
    }
    layers = _plan_graph_layers(graph)
    lines = [
        "# Plan ASCII",
        "",
        "```text",
        f"Graph: {graph.get('graph_id', '')}",
        f"Goal: {graph.get('graph_goal', '')}",
        f"Phase ledger: {status.get('phase_id', '')} [{status.get('status', 'unknown')}]",
        "",
        "Legend: [DONE]=completed, [ACTIVE]=in progress, [PENDING]=not yet completed, [BLOCKED]=blocked, [MANUAL]=manual action required, [READY]=runtime-ready.",
        "Sequential order is top to bottom. Nodes in the same lane are concurrent after prior lanes complete.",
        "",
    ]
    if not layers:
        lines.append("(no plan nodes)")
    for layer_index, layer in enumerate(layers, start=1):
        if len(layer) > 1:
            lines.append(f"Lane {layer_index} (concurrent):")
        else:
            lines.append(f"Lane {layer_index} (sequential):")
        for node_id in layer:
            node = node_by_id.get(node_id, {})
            report = readiness_by_id.get(node_id, {})
            completion = _node_completion_state(node, status)
            runtime_status = str(report.get("status", "") or "")
            badges: list[str] = []
            if completion == "completed":
                badges.append("DONE")
            elif completion == "blocked":
                badges.append("BLOCKED")
            elif completion == "active":
                badges.append("ACTIVE")
            else:
                badges.append("PENDING")
            if runtime_status == "runtime_ready":
                badges.append("READY")
            elif runtime_status == "manual_action_required":
                badges.append("MANUAL")
            elif runtime_status == "blocked_missing_fields":
                badges.append("BLOCKED")
            title = node.get("title") or node.get("node_goal") or node_id
            deps = _node_dependencies(node)
            dep_text = f" after {', '.join(deps)}" if deps else ""
            badge_text = " ".join(f"[{badge}]" for badge in dict.fromkeys(badges))
            lines.append(f"  {badge_text} {node_id}{dep_text}")
            lines.append(f"       {title}")
            missing_fields = report.get("missing_fields", [])
            if missing_fields:
                lines.append(f"       missing: {', '.join(str(field) for field in missing_fields)}")
            next_action = report.get("next_action")
            if isinstance(next_action, str) and next_action.strip():
                lines.append(f"       next: {next_action.strip()}")
        if layer_index < len(layers):
            lines.append("       |")
            lines.append("       v")
    lines.extend(["```", ""])
    return "\n".join(lines)


def cmd_record_plan_graph(args: argparse.Namespace) -> int:
    root = Path(args.root)
    target_dir = phase_dir(root, args.phase)
    status_file = target_dir / "PHASE_STATUS.json"
    status = load_status(status_file)

    source = Path(args.graph)
    if not source.exists() or not source.is_file():
        print(f"plan graph file missing: {source}", file=sys.stderr)
        return 1
    try:
        graph = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"plan graph must be JSON: {exc}", file=sys.stderr)
        return 1

    graph_errors, metrics = _validate_plan_graph_payload(graph)
    if graph_errors:
        for error in graph_errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    graph_dir = target_dir / "plan-graphs"
    graph_dir.mkdir(exist_ok=True)
    recorded_at = now_stamp()
    graph_id = slug(str(metrics["graph_id"]))
    suffix = source.suffix if source.suffix else ".json"
    copied_graph = graph_dir / f"{recorded_at}-{graph_id}{suffix}"
    graph = json.loads(json.dumps(graph))
    graph["plan_id"] = metrics["plan_id"]
    copied_graph.write_text(json.dumps(graph, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    relative_graph = str(copied_graph.relative_to(target_dir))
    graph_sha256 = sha256_file(copied_graph)
    readiness = analyze_plan_graph_runtime_readiness(graph, status)
    readiness_path = graph_dir / f"{recorded_at}-{graph_id}-runtime-readiness.json"
    readiness_path.write_text(json.dumps(readiness, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    relative_readiness = str(readiness_path.relative_to(target_dir))
    readiness_sha256 = sha256_file(readiness_path)
    ascii_path = graph_dir / f"{recorded_at}-{graph_id}-plan-ascii.md"
    ascii_path.write_text(render_plan_ascii(graph, status, readiness), encoding="utf-8")
    relative_ascii = str(ascii_path.relative_to(target_dir))
    ascii_sha256 = sha256_file(ascii_path)

    candidate_status = json.loads(json.dumps(status))
    candidate_status["plan_id"] = metrics["plan_id"]
    graph_entry = {
        "path": relative_graph,
        "sha256": graph_sha256,
        "plan_id": metrics["plan_id"],
        "graph_id": metrics["graph_id"],
        "node_count": metrics["node_count"],
        "review_scope_count": metrics["review_scope_count"],
        "review_node_count": metrics["review_node_count"],
        "self_improvement_iterations": metrics["self_improvement_iterations"],
        "review_fanout_limits": metrics["review_fanout_limits"],
        "review_iteration_limits": metrics["review_iteration_limits"],
        "runtime_readiness_artifact": relative_readiness,
        "runtime_readiness_sha256": readiness_sha256,
        "runtime_readiness": readiness["summary"],
        "plan_ascii_artifact": relative_ascii,
        "plan_ascii_sha256": ascii_sha256,
    }
    candidate_status.setdefault("plan_graph_artifacts", [])
    candidate_status["plan_graph_artifacts"].append(graph_entry)
    candidate_status["active_plan_graph_artifact"] = relative_graph

    errors = validate_status(candidate_status, target_dir, Path(args.repo_root))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    save_status(status_file, candidate_status)
    update_plan_index(root, target_dir, candidate_status, graph_entry, graph, recorded_at)
    print(copied_graph)
    return 0


def cmd_inspect_plan_graph(args: argparse.Namespace) -> int:
    root = Path(args.root)
    target_dir = phase_dir(root, args.phase)
    status_file = target_dir / "PHASE_STATUS.json"
    status = load_status(status_file)
    source = Path(args.graph)
    if not source.exists() or not source.is_file():
        print(f"plan graph file missing: {source}", file=sys.stderr)
        return 1
    try:
        graph = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"plan graph must be JSON: {exc}", file=sys.stderr)
        return 1
    graph_errors, _metrics = _validate_plan_graph_payload(graph)
    if graph_errors:
        for error in graph_errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    readiness = analyze_plan_graph_runtime_readiness(graph, status)
    print(json.dumps(readiness, indent=2, sort_keys=True))
    return 0


def cmd_compile_plan_graph(args: argparse.Namespace) -> int:
    root = Path(args.root)
    target_dir = phase_dir(root, args.phase)
    status_file = target_dir / "PHASE_STATUS.json"
    status = load_status(status_file)
    source = Path(args.graph)
    if not source.exists() or not source.is_file():
        print(f"plan graph file missing: {source}", file=sys.stderr)
        return 1
    try:
        graph = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"plan graph must be JSON: {exc}", file=sys.stderr)
        return 1

    runtime_graph, errors = compile_plan_graph_to_exec_graph(graph, status)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    assert runtime_graph is not None

    output_path = Path(args.output) if args.output else target_dir / "plan-graphs" / f"{now_stamp()}-{slug(str(graph.get('graph_id') or args.phase))}-runtime-graph.json"
    if not output_path.is_absolute():
        if ".." in output_path.parts:
            print(f"output path must be phase-relative without '..': {args.output}", file=sys.stderr)
            return 1
        output_path = target_dir / output_path
    try:
        output_path.relative_to(target_dir)
    except ValueError:
        print(f"output path must stay inside the phase directory: {args.output}", file=sys.stderr)
        return 1
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(runtime_graph, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    relative_output = str(output_path.relative_to(target_dir))
    candidate_status = json.loads(json.dumps(status))
    candidate_status.setdefault("evidence_artifacts", [])
    _append_unique_path(candidate_status["evidence_artifacts"], relative_output)
    errors = validate_status(candidate_status, target_dir, Path(args.repo_root))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    save_status(status_file, candidate_status)
    print(output_path)
    return 0


def cmd_record_domain_loop(args: argparse.Namespace) -> int:
    root = Path(args.root)
    target_dir = phase_dir(root, args.phase)
    status_file = target_dir / "PHASE_STATUS.json"

    loop_id = slug(args.loop_id or f"{args.skill}-{args.persona}")
    loop_dir = target_dir / "domain-review-loops" / loop_id
    try:
        context_artifact = _phase_relative_copy(target_dir, args.context_artifact, loop_dir)
        state_artifact = _phase_relative_copy(target_dir, args.state_artifact, loop_dir)
        events_artifact = _phase_relative_copy(target_dir, args.events_artifact, loop_dir)
        aggregate_artifact = _phase_relative_copy(target_dir, args.aggregate_artifact, loop_dir)
        matrix_artifact = _phase_relative_copy(target_dir, args.matrix_artifact, loop_dir)
        implementation_plan_artifact = _phase_relative_copy(target_dir, args.implementation_plan, loop_dir)
        validation_plan_artifact = _phase_relative_copy(target_dir, args.validation_plan, loop_dir)
        review_plan_artifact = _phase_relative_copy(target_dir, args.review_plan, loop_dir)
        model_fanout_artifact = (
            _phase_relative_copy(target_dir, args.model_fanout_artifact, loop_dir)
            if args.model_fanout_artifact
            else None
        )
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    plan_entry = {
        "round": args.round,
        "implementation_plan_artifact": implementation_plan_artifact,
        "validation_plan_artifact": validation_plan_artifact,
        "review_plan_artifact": review_plan_artifact,
    }
    loop_entry = {
        "loop_id": loop_id,
        "skill": args.skill,
        "persona": args.persona,
        "immutable_goal": args.immutable_goal,
        "context_artifact": context_artifact,
        "best_practice_skills": args.best_practice_skill,
        "state_artifact": state_artifact,
        "events_artifact": events_artifact,
        "aggregate_artifact": aggregate_artifact,
        "matrix_artifact": matrix_artifact,
        "iteration_plans": [plan_entry],
        "end_state": args.end_state,
        "mutates_production": False,
    }
    if model_fanout_artifact:
        loop_entry["model_fanout_artifact"] = model_fanout_artifact

    with status_update_lock(target_dir):
        status = load_status(status_file)
        candidate_status = json.loads(json.dumps(status))
        candidate_status.setdefault("review_artifacts", [])
        for artifact_path in [
            context_artifact,
            state_artifact,
            events_artifact,
            aggregate_artifact,
            matrix_artifact,
            implementation_plan_artifact,
            validation_plan_artifact,
            review_plan_artifact,
            *( [model_fanout_artifact] if model_fanout_artifact else [] ),
        ]:
            _append_unique_path(candidate_status["review_artifacts"], artifact_path)

        candidate_status.setdefault("domain_review_loops", [])
        loops = candidate_status["domain_review_loops"]
        if not isinstance(loops, list):
            print("domain_review_loops must be a list", file=sys.stderr)
            return 1

        replaced = False
        for index, existing in enumerate(loops):
            if isinstance(existing, dict) and existing.get("loop_id") == loop_id:
                merged = dict(existing)
                merged.update({key: value for key, value in loop_entry.items() if key != "iteration_plans"})
                existing_plans = merged.get("iteration_plans")
                if not isinstance(existing_plans, list):
                    existing_plans = []
                existing_plans = [
                    plan for plan in existing_plans
                    if not (isinstance(plan, dict) and plan.get("round") == args.round)
                ]
                existing_plans.append(plan_entry)
                existing_plans.sort(key=lambda item: item.get("round", 0) if isinstance(item, dict) else 0)
                merged["iteration_plans"] = existing_plans
                loops[index] = merged
                replaced = True
                break
        if not replaced:
            loops.append(loop_entry)

        errors = validate_status(candidate_status, target_dir, Path(args.repo_root))
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 1
        save_status(status_file, candidate_status)
    print(status_file)
    return 0


def cmd_record_comparison(args: argparse.Namespace) -> int:
    root = Path(args.root)
    target_dir = phase_dir(root, args.phase)
    status_file = target_dir / "PHASE_STATUS.json"
    status = load_status(status_file)
    candidate_status = json.loads(json.dumps(status))
    candidate_status["review_comparison"] = {
        "agreement": args.agreement,
        "closure_allowed": bool(args.closure_allowed),
        "reason": args.reason,
    }
    if args.closure_allowed and args.agreement == "agree":
        candidate_status["review_status"] = "passed"
        candidate_status["status"] = "external_review_passed"
    elif args.agreement in {"disagree", "insufficient"}:
        candidate_status["review_status"] = "blocked"
        candidate_status["status"] = "external_review_blocked"
    elif args.agreement == "partial":
        candidate_status["review_status"] = "conditional_pass"
        candidate_status["status"] = "external_review_blocked"

    errors = validate_status(candidate_status, target_dir, Path(args.repo_root))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    save_status(status_file, candidate_status)
    print(status_file)
    return 0


def _phase_sort_key(phase_id: str) -> list[Any]:
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", phase_id)]


def _load_phase_rows(root: Path, repo_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for phase_status_file in sorted(root.glob("*/PHASE_STATUS.json")):
        status = load_status(phase_status_file)
        phase_id = str(status.get("phase_id") or phase_status_file.parent.name)
        rows.append(
            {
                "phase_id": phase_id,
                "phase_dir": phase_status_file.parent,
                "status": status,
                "state": status.get("status", "unknown"),
                "errors": validate_status(status, phase_status_file.parent, repo_root),
                "sort_key": _phase_sort_key(phase_id),
            }
        )
    rows.sort(key=lambda row: row["sort_key"])
    return rows


def _active_runtime_readiness(status: dict[str, Any]) -> dict[str, Any] | None:
    plan_graph_artifacts = status.get("plan_graph_artifacts")
    if not isinstance(plan_graph_artifacts, list):
        return None
    active_path = status.get("active_plan_graph_artifact")
    selected: dict[str, Any] | None = None
    for artifact in plan_graph_artifacts:
        if not isinstance(artifact, dict):
            continue
        if active_path and artifact.get("path") == active_path:
            selected = artifact
            break
        selected = artifact
    if not selected:
        return None
    readiness = selected.get("runtime_readiness")
    return readiness if isinstance(readiness, dict) else None


def _phase_runtime_ready(status: dict[str, Any]) -> tuple[bool, str]:
    readiness = _active_runtime_readiness(status)
    if readiness is None:
        return False, "missing_runtime_readiness"
    if readiness.get("can_execute_runtime") is False:
        return False, "runtime_readiness_cannot_execute_runtime"
    if readiness.get("blocked_node_count", 0):
        return False, "runtime_readiness_has_blocked_nodes"
    if readiness.get("manual_node_count", 0):
        return False, "runtime_readiness_has_manual_nodes"
    if not readiness.get("node_count", 0):
        return False, "runtime_readiness_has_no_nodes"
    return True, "runtime_ready"


def _active_blockers(status: dict[str, Any]) -> list[dict[str, Any]]:
    blockers = status.get("blockers")
    if not isinstance(blockers, list):
        return []
    active: list[dict[str, Any]] = []
    for blocker in blockers:
        if not isinstance(blocker, dict):
            active.append({"description": str(blocker), "status": "unknown"})
            continue
        blocker_status = str(blocker.get("status") or blocker.get("state") or "open").lower()
        if blocker_status in {"resolved", "closed", "fixed", "accepted"}:
            continue
        active.append(blocker)
    return active


def _blocker_occurrences(blocker: dict[str, Any]) -> int:
    try:
        return int(blocker.get("occurrences") or 1)
    except (TypeError, ValueError):
        return 1


def _is_escalated(blocker: dict[str, Any]) -> bool:
    return bool(blocker.get("escalated"))


def _has_dogpile_stop_proof(blocker: dict[str, Any]) -> bool:
    return bool(
        blocker.get("dogpile_evaluated")
        or blocker.get("dogpile_not_applicable_rationale")
        or blocker.get("dogpile_report_artifact")
    )


def _has_human_dependency(blocker: dict[str, Any]) -> bool:
    return bool(
        str(blocker.get("human_dependency_type") or "").strip()
        and str(blocker.get("human_dependency_detail") or "").strip()
    )


def _has_hard_stop_proof(blocker: dict[str, Any]) -> bool:
    return (
        _blocker_occurrences(blocker) >= 2
        and _is_escalated(blocker)
        and _has_dogpile_stop_proof(blocker)
        and _has_human_dependency(blocker)
    )


def _is_actionable_blocking_status(status: dict[str, Any]) -> bool:
    blockers = _active_blockers(status)
    if not blockers:
        return True
    return any(not _has_hard_stop_proof(blocker) for blocker in blockers)


def _blocked_stop_evidence(status: dict[str, Any]) -> dict[str, Any]:
    blockers = _active_blockers(status)
    return {
        "active_blockers": blockers,
        "active_blocker_count": len(blockers),
        "all_blockers_repeated_and_escalated": bool(blockers)
        and all(_blocker_occurrences(blocker) >= 2 and _is_escalated(blocker) for blocker in blockers),
        "all_blockers_have_dogpile_stop_proof": bool(blockers)
        and all(_has_dogpile_stop_proof(blocker) for blocker in blockers),
        "all_blockers_have_human_dependency": bool(blockers)
        and all(_has_human_dependency(blocker) for blocker in blockers),
        "all_blockers_have_hard_stop_proof": bool(blockers)
        and all(_has_hard_stop_proof(blocker) for blocker in blockers),
    }


def _find_next_runtime_ready_phase(rows: list[dict[str, Any]], current_row: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    blocked_candidates: list[dict[str, Any]] = []
    for row in rows:
        if row["sort_key"] <= current_row["sort_key"]:
            continue
        if row["state"] not in {"planned", "implementing", "ready_for_review", "external_review_passed"}:
            continue
        runtime_ready, reason = _phase_runtime_ready(row["status"])
        if runtime_ready:
            return row, blocked_candidates
        blocked_candidates.append({"phase_id": row["phase_id"], "reason": reason, "state": row["state"]})
    return None, blocked_candidates


def _find_later_actionable_blocking_phase(rows: list[dict[str, Any]], current_row: dict[str, Any]) -> dict[str, Any] | None:
    for row in rows:
        if row["sort_key"] <= current_row["sort_key"]:
            continue
        if row["state"] in {"local_validation_failed", "external_review_blocked"} and _is_actionable_blocking_status(row["status"]):
            return row
    return None


def _active_plan_graph_path(row: dict[str, Any]) -> Path | None:
    active_path = row["status"].get("active_plan_graph_artifact")
    if not isinstance(active_path, str) or not active_path.strip():
        return None
    if ".." in Path(active_path).parts:
        return None
    candidate = row["phase_dir"] / active_path
    return candidate if candidate.is_file() else None


def _active_graph_uncompleted_nodes(row: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    graph_path = _active_plan_graph_path(row)
    if graph_path is None:
        return [], []
    try:
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], [
            {
                "graph_artifact": str(graph_path),
                "reason": "active_plan_graph_unreadable",
            }
        ]
    readiness = analyze_plan_graph_runtime_readiness(graph, row["status"])
    node_by_id = {
        str(node.get("id", "")): node
        for node in graph.get("nodes", [])
        if isinstance(node, dict) and str(node.get("id", "")).strip()
    }
    readiness_by_id = {
        str(report.get("node_id", "")): report
        for report in readiness.get("nodes", [])
        if isinstance(report, dict)
    }
    runtime_ready: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for layer in _plan_graph_layers(graph):
        for node_id in layer:
            node = node_by_id.get(node_id, {})
            if _node_completion_state(node, row["status"]) == "completed":
                continue
            report = readiness_by_id.get(node_id, {})
            entry = {
                "node_id": node_id,
                "node_goal": node.get("node_goal") or node.get("title") or "",
                "runtime_status": report.get("status", "unknown"),
                "missing_fields": report.get("missing_fields", []),
            }
            if report.get("status") == "runtime_ready":
                runtime_ready.append(entry)
            else:
                blocked.append(entry)
        if runtime_ready:
            break
    return runtime_ready, blocked


def _select_controller_row(rows: list[dict[str, Any]], requested_phase: str | None) -> dict[str, Any] | None:
    if requested_phase:
        for row in rows:
            if row["phase_id"] == requested_phase:
                return row
        return None
    for state_group in [
        {"local_validation_failed", "external_review_blocked"},
        {"implementing", "ready_for_review", "external_review_passed", "planned"},
    ]:
        candidates = [row for row in rows if row["state"] in state_group]
        if candidates:
            return candidates[-1]
    accepted = [row for row in rows if row["state"] == "accepted"]
    return accepted[-1] if accepted else (rows[-1] if rows else None)


PROJECT_KNOWLEDGE_AGENT_EXECUTABLE_MARKERS = (
    "next agent-executable candidate",
    "next agent executable candidate",
    "next agent-executable phase",
    "next agent executable phase",
)

PROJECT_KNOWLEDGE_UNMET_GOAL_MARKERS = (
    "current blocker",
    "still blocked",
    "remaining blocker",
    "remaining issue",
    "do not claim full",
    "missing_source",
    "completeness_gate.passing=false",
    "project still blocked",
    "not complete",
)


def _project_knowledge_continuation(repo_root: Path) -> dict[str, Any] | None:
    knowledge_path = repo_root / "PROJECT_KNOWLEDGE.md"
    if not knowledge_path.exists():
        return None
    try:
        lines = knowledge_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    matches: list[dict[str, Any]] = []
    agent_executable = False
    for line_number, line in enumerate(lines, 1):
        normalized = line.lower()
        executable_match = any(marker in normalized for marker in PROJECT_KNOWLEDGE_AGENT_EXECUTABLE_MARKERS)
        unmet_match = any(marker in normalized for marker in PROJECT_KNOWLEDGE_UNMET_GOAL_MARKERS)
        if not executable_match and not unmet_match:
            continue
        if executable_match:
            agent_executable = True
        matches.append(
            {
                "path": str(knowledge_path),
                "line": line_number,
                "text": line.strip(),
                "agent_executable": executable_match,
            }
        )

    if not matches:
        return None
    return {
        "path": str(knowledge_path),
        "agent_executable": agent_executable,
        "matches": matches[:12],
    }


def _global_continue_candidate(
    rows: list[dict[str, Any]],
    current_row: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any] | None:
    for row in rows:
        if row is current_row:
            continue
        if row["state"] in {"implementing", "ready_for_review", "external_review_passed", "planned"}:
            return {
                "type": "resume_fixable_phase",
                "phase_id": row["phase_id"],
                "state": row["state"],
                "reason": "another phase remains agent-actionable; terminal stop is not allowed",
            }
        if row["state"] in {"local_validation_failed", "external_review_blocked"} and _is_actionable_blocking_status(row["status"]):
            return {
                "type": "resume_actionable_blocking_phase",
                "phase_id": row["phase_id"],
                "state": row["state"],
                "reason": "another blocking phase remains agent-actionable; terminal stop is not allowed",
            }
    for row in rows:
        ready_nodes, blocked_nodes = _active_graph_uncompleted_nodes(row)
        if ready_nodes:
            next_node = ready_nodes[0]
            return {
                "type": "start_next_runtime_ready_plan_node",
                "phase_id": row["phase_id"],
                "state": row["state"],
                "node_id": next_node["node_id"],
                "reason": "an accepted active graph still has runtime-ready work; terminal stop is not allowed",
            }
        if blocked_nodes and row is not current_row:
            return {
                "type": "inspect_blocked_plan_graph",
                "phase_id": row["phase_id"],
                "state": row["state"],
                "reason": "an accepted active graph still has unresolved work; terminal stop is not allowed",
            }
    project_knowledge_continuation = _project_knowledge_continuation(repo_root)
    if project_knowledge_continuation and project_knowledge_continuation["agent_executable"]:
        return {
            "type": "create_next_phase_from_project_knowledge",
            "phase_id": "",
            "state": "project_knowledge",
            "reason": "PROJECT_KNOWLEDGE.md names agent-executable remaining work; terminal stop is not allowed",
            "project_knowledge_continuation": project_knowledge_continuation,
        }
    return None


def _controller_decision(
    root: Path,
    repo_root: Path,
    rows: list[dict[str, Any]],
    current_row: dict[str, Any] | None,
    requested_phase: str | None,
) -> tuple[dict[str, Any], int]:
    if current_row is None:
        decision = {
            "schema": "plan_iterate.continue_decision.v1",
            "controller_terminal_state": "HUMAN_REQUIRED",
            "decision": "HUMAN_REQUIRED",
            "stop": True,
            "should_continue": False,
            "reason": f"requested phase not found: {requested_phase}" if requested_phase else "no phases found",
            "next_action": {
                "type": "interview",
                "reason": "phase selection is ambiguous or missing",
            },
        }
        return decision, 2

    state = current_row["state"]
    phase_id = current_row["phase_id"]
    base: dict[str, Any] = {
        "schema": "plan_iterate.continue_decision.v1",
        "root": str(root),
        "active_phase": phase_id,
        "active_status": state,
        "active_valid": not current_row["errors"],
        "active_errors": current_row["errors"],
    }
    if state in {"local_validation_failed", "external_review_blocked"}:
        stop_evidence = _blocked_stop_evidence(current_row["status"])
        if _is_actionable_blocking_status(current_row["status"]):
            decision = {
                **base,
                "controller_terminal_state": "PASS",
                "decision": "CONTINUE",
                "stop": False,
                "should_continue": True,
                "blockers": current_row["status"].get("blockers", []),
                "stop_evidence": stop_evidence,
                "next_action": {
                    "type": "resume_actionable_blocking_phase",
                    "phase_id": phase_id,
                    "reason": "blocking ledger state has no repeated escalated stop proof; fixable work is not a stop",
                },
            }
            return decision, 0
        global_candidate = _global_continue_candidate(rows, current_row, repo_root)
        if global_candidate is not None:
            decision = {
                **base,
                "controller_terminal_state": "PASS",
                "decision": "CONTINUE",
                "stop": False,
                "should_continue": True,
                "blockers": current_row["status"].get("blockers", []),
                "stop_evidence": stop_evidence,
                "next_phase": global_candidate.get("phase_id") or None,
                "next_status": global_candidate.get("state"),
                "project_knowledge_continuation": global_candidate.get("project_knowledge_continuation"),
                "next_action": global_candidate,
            }
            return decision, 0
        decision = {
            **base,
            "controller_terminal_state": "BLOCKED",
            "decision": "BLOCKED",
            "stop": True,
            "should_continue": False,
            "blockers": current_row["status"].get("blockers", []),
            "stop_evidence": stop_evidence,
            "next_action": {
                "type": "interview",
                "phase_id": phase_id,
                "reason": "current phase has repeated escalated blockers and no remaining agent-actionable recovery path recorded",
            },
        }
        return decision, 2

    if state == "accepted":
        next_row, blocked_candidates = _find_next_runtime_ready_phase(rows, current_row)
        if next_row is not None:
            decision = {
                **base,
                "controller_terminal_state": "PASS",
                "decision": "CONTINUE",
                "stop": False,
                "should_continue": True,
                "next_phase": next_row["phase_id"],
                "next_status": next_row["state"],
                "next_action": {
                    "type": "start_next_runtime_ready_phase",
                    "phase_id": next_row["phase_id"],
                    "reason": "accepted is terminal only for the current phase",
                },
            }
            return decision, 0
        active_graph_ready_nodes, active_graph_blocked_nodes = _active_graph_uncompleted_nodes(current_row)
        if active_graph_ready_nodes:
            next_node = active_graph_ready_nodes[0]
            decision = {
                **base,
                "controller_terminal_state": "PASS",
                "decision": "CONTINUE",
                "stop": False,
                "should_continue": True,
                "active_plan_graph_next_nodes": active_graph_ready_nodes,
                "next_action": {
                    "type": "start_next_runtime_ready_plan_node",
                    "phase_id": phase_id,
                    "node_id": next_node["node_id"],
                    "reason": "accepted phase still has uncompleted runtime-ready nodes in its active plan graph",
                },
            }
            return decision, 0
        actionable_blocking_row = _find_later_actionable_blocking_phase(rows, current_row)
        if actionable_blocking_row is not None:
            decision = {
                **base,
                "controller_terminal_state": "PASS",
                "decision": "CONTINUE",
                "stop": False,
                "should_continue": True,
                "next_phase": actionable_blocking_row["phase_id"],
                "next_status": actionable_blocking_row["state"],
                "next_action": {
                    "type": "resume_actionable_blocking_phase",
                    "phase_id": actionable_blocking_row["phase_id"],
                    "reason": "later blocking ledger state is agent-actionable until repeated escalated stop proof exists",
                },
            }
            return decision, 0
        project_knowledge_continuation = _project_knowledge_continuation(repo_root)
        if project_knowledge_continuation is not None:
            if project_knowledge_continuation["agent_executable"]:
                decision = {
                    **base,
                    "controller_terminal_state": "PASS",
                    "decision": "PROJECT_GOALS_REMAIN",
                    "stop": False,
                    "should_continue": True,
                    "project_knowledge_continuation": project_knowledge_continuation,
                    "next_action": {
                        "type": "create_next_phase_from_project_knowledge",
                        "reason": "PROJECT_KNOWLEDGE.md names agent-executable remaining work; accepted is terminal only for the current phase",
                        "source": str(repo_root / "PROJECT_KNOWLEDGE.md"),
                    },
                }
                return decision, 0
            decision = {
                **base,
                "controller_terminal_state": "HUMAN_REQUIRED",
                "decision": "HUMAN_REQUIRED",
                "stop": True,
                "should_continue": False,
                "project_knowledge_continuation": project_knowledge_continuation,
                "next_action": {
                    "type": "interview",
                    "reason": "PROJECT_KNOWLEDGE.md names unmet goals or blockers but no agent-executable next phase",
                    "source": str(repo_root / "PROJECT_KNOWLEDGE.md"),
                },
            }
            return decision, 2
        later_unaccepted = [
            {"phase_id": row["phase_id"], "state": row["state"]}
            for row in rows
            if row["sort_key"] > current_row["sort_key"] and row["state"] != "accepted"
        ]
        if later_unaccepted or blocked_candidates or active_graph_blocked_nodes:
            non_actionable_blocked = [
                {
                    "phase_id": row["phase_id"],
                    "state": row["state"],
                    "stop_evidence": _blocked_stop_evidence(row["status"]),
                }
                for row in rows
                if row["sort_key"] > current_row["sort_key"]
                and row["state"] in {"local_validation_failed", "external_review_blocked"}
                and not _is_actionable_blocking_status(row["status"])
            ]
            decision = {
                **base,
                "controller_terminal_state": "BLOCKED" if non_actionable_blocked else "HUMAN_REQUIRED",
                "decision": "BLOCKED" if non_actionable_blocked else "HUMAN_REQUIRED",
                "stop": True,
                "should_continue": False,
                "blocked_candidates": blocked_candidates,
                "active_plan_graph_blocked_nodes": active_graph_blocked_nodes,
                "later_unaccepted_phases": later_unaccepted,
                "non_actionable_blocked_phases": non_actionable_blocked,
                "next_action": {
                    "type": "interview",
                    "reason": "remaining phases exist but no later runtime-ready or agent-actionable blocked phase is selectable",
                },
            }
            return decision, 2
        decision = {
            **base,
            "controller_terminal_state": "PASS",
            "decision": "OVERALL_COMPLETE",
            "stop": False,
            "should_continue": False,
            "next_action": {
                "type": "none",
                "reason": "no later unaccepted phase found",
            },
        }
        return decision, 0

    if state in {"planned", "implementing", "ready_for_review", "external_review_passed"}:
        runtime_ready, readiness_reason = _phase_runtime_ready(current_row["status"])
        if state == "planned" and not runtime_ready:
            decision = {
                **base,
                "controller_terminal_state": "HUMAN_REQUIRED",
                "decision": "HUMAN_REQUIRED",
                "stop": True,
                "should_continue": False,
                "next_action": {
                    "type": "interview",
                    "phase_id": phase_id,
                    "reason": readiness_reason,
                },
            }
            return decision, 2
        decision = {
            **base,
            "controller_terminal_state": "PASS",
            "decision": "CONTINUE",
            "stop": False,
            "should_continue": True,
            "next_action": {
                "type": "continue_current_phase",
                "phase_id": phase_id,
                "reason": f"current phase status is {state}",
            },
        }
        return decision, 0

    decision = {
        **base,
        "controller_terminal_state": "HUMAN_REQUIRED",
        "decision": "HUMAN_REQUIRED",
        "stop": True,
        "should_continue": False,
        "next_action": {
            "type": "interview",
            "phase_id": phase_id,
            "reason": f"unsupported or ambiguous phase status: {state}",
        },
    }
    return decision, 2


def cmd_continue(args: argparse.Namespace) -> int:
    root = Path(args.root)
    repo_root = Path(args.repo_root)
    rows = _load_phase_rows(root, repo_root) if root.exists() else []
    current_row = _select_controller_row(rows, args.phase)
    decision, exit_code = _controller_decision(root, repo_root, rows, current_row, args.phase)
    print(json.dumps(decision, indent=2, sort_keys=True))
    return exit_code


def cmd_guard_final(args: argparse.Namespace) -> int:
    message = ""
    if args.message_file:
        message = Path(args.message_file).read_text(encoding="utf-8")
    elif args.message:
        message = args.message
    result = evaluate_continuation_guard(Path(args.repo_root).resolve(), Path(args.root), message)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if result["block_final"] else 0


def cmd_status(args: argparse.Namespace) -> int:
    root = Path(args.root)
    if not root.exists():
        print(f"{root} missing")
        return 0
    rows: list[tuple[str, str, str]] = []
    for status_file in sorted(root.glob("*/PHASE_STATUS.json")):
        status = load_status(status_file)
        errors = validate_status(status, status_file.parent, Path(args.repo_root))
        rows.append((status.get("phase_id", status_file.parent.name), status.get("status", "unknown"), "valid" if not errors else f"errors={len(errors)}"))
    for phase, state, validity in rows:
        print(f"{phase}\t{state}\t{validity}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evidence-gated phase iteration helper")
    parser.add_argument("--root", default=".plan-iterate", help="phase state root")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--phase", required=True)
    init_parser.add_argument("--force", action="store_true")
    init_parser.set_defaults(func=cmd_init)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--phase", required=True)
    validate_parser.add_argument("--repo-root", default=".")
    validate_parser.set_defaults(func=cmd_validate)

    package_parser = subparsers.add_parser("package")
    package_parser.add_argument("--phase", required=True)
    package_parser.add_argument("--output", required=True)
    package_parser.add_argument("--repo-root", default=".")
    package_parser.set_defaults(func=cmd_package)

    review_parser = subparsers.add_parser("record-review")
    review_parser.add_argument("--phase", required=True)
    review_parser.add_argument(
        "--verdict",
        required=True,
        choices=["pass", "passed", "conditional_pass", "needs_changes", "blocked", "insufficient_evidence", "malformed", "no_verdict"],
    )
    review_parser.add_argument("--review", required=True)
    review_parser.add_argument("--review-request", required=True)
    review_parser.add_argument("--review-bundle", required=True)
    review_parser.add_argument("--invocation-command", required=True)
    review_parser.add_argument("--invocation-receipt", required=True)
    review_parser.add_argument("--model")
    review_parser.add_argument("--reviewer", default="scillm-gpt55-high")
    review_parser.add_argument("--repo-root", default=".")
    review_parser.add_argument(
        "--adjudicator-kind",
        default="scillm",
        choices=["webgpt", "scillm", "human", "deterministic_verifier"],
    )
    review_parser.set_defaults(func=cmd_record_review)

    context_parser = subparsers.add_parser("record-context")
    context_parser.add_argument("--phase", required=True)
    context_parser.add_argument("--context", required=True)
    context_parser.add_argument("--memory-collection", default="plan_iterate_phase_context")
    context_parser.add_argument("--memory-key")
    context_parser.add_argument("--memory-upsert", action="store_false", dest="skip_memory_upsert", default=False, help=argparse.SUPPRESS)
    context_parser.add_argument("--skip-memory-upsert", action="store_true")
    context_parser.add_argument("--repo-root", default=".")
    context_parser.set_defaults(func=cmd_record_context)

    skill_context_parser = subparsers.add_parser("record-skill-context")
    skill_context_parser.add_argument("--phase", required=True)
    skill_context_parser.add_argument("--context", required=True)
    skill_context_parser.add_argument("--repo-root", default=".")
    skill_context_parser.set_defaults(func=cmd_record_skill_context)

    plan_graph_parser = subparsers.add_parser("record-plan-graph")
    plan_graph_parser.add_argument("--phase", required=True)
    plan_graph_parser.add_argument("--graph", required=True)
    plan_graph_parser.add_argument("--repo-root", default=".")
    plan_graph_parser.set_defaults(func=cmd_record_plan_graph)

    inspect_graph_parser = subparsers.add_parser("inspect-plan-graph")
    inspect_graph_parser.add_argument("--phase", required=True)
    inspect_graph_parser.add_argument("--graph", required=True)
    inspect_graph_parser.add_argument("--repo-root", default=".")
    inspect_graph_parser.set_defaults(func=cmd_inspect_plan_graph)

    compile_graph_parser = subparsers.add_parser("compile-plan-graph")
    compile_graph_parser.add_argument("--phase", required=True)
    compile_graph_parser.add_argument("--graph", required=True)
    compile_graph_parser.add_argument("--output")
    compile_graph_parser.add_argument("--repo-root", default=".")
    compile_graph_parser.set_defaults(func=cmd_compile_plan_graph)

    domain_loop_parser = subparsers.add_parser("record-domain-loop")
    domain_loop_parser.add_argument("--phase", required=True)
    domain_loop_parser.add_argument("--loop-id")
    domain_loop_parser.add_argument("--skill", required=True)
    domain_loop_parser.add_argument("--persona", required=True)
    domain_loop_parser.add_argument("--immutable-goal", required=True)
    domain_loop_parser.add_argument("--context-artifact", required=True)
    domain_loop_parser.add_argument("--state-artifact", required=True)
    domain_loop_parser.add_argument("--events-artifact", required=True)
    domain_loop_parser.add_argument("--aggregate-artifact", required=True)
    domain_loop_parser.add_argument("--matrix-artifact", required=True)
    domain_loop_parser.add_argument("--implementation-plan", required=True)
    domain_loop_parser.add_argument("--validation-plan", required=True)
    domain_loop_parser.add_argument("--review-plan", required=True)
    domain_loop_parser.add_argument("--model-fanout-artifact")
    domain_loop_parser.add_argument("--best-practice-skill", action="append", required=True)
    domain_loop_parser.add_argument("--round", type=int, required=True)
    domain_loop_parser.add_argument(
        "--end-state",
        required=True,
        choices=["needs_patch", "verified", "blocked", "failed", "skipped"],
    )
    domain_loop_parser.add_argument("--repo-root", default=".")
    domain_loop_parser.set_defaults(func=cmd_record_domain_loop)

    comparison_parser = subparsers.add_parser("record-comparison")
    comparison_parser.add_argument("--phase", required=True)
    comparison_parser.add_argument("--agreement", required=True, choices=["agree", "partial", "disagree", "insufficient"])
    comparison_parser.add_argument("--closure-allowed", action="store_true")
    comparison_parser.add_argument("--reason", required=True)
    comparison_parser.add_argument("--repo-root", default=".")
    comparison_parser.set_defaults(func=cmd_record_comparison)

    continue_parser = subparsers.add_parser("continue")
    continue_parser.add_argument("--phase", help="current phase to advance from; defaults to the highest-priority active phase")
    continue_parser.add_argument("--repo-root", default=".")
    continue_parser.set_defaults(func=cmd_continue)

    guard_parser = subparsers.add_parser("guard-final")
    guard_parser.add_argument("--repo-root", default=".")
    guard_parser.add_argument("--message", default="")
    guard_parser.add_argument("--message-file")
    guard_parser.set_defaults(func=cmd_guard_final)

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--repo-root", default=".")
    status_parser.set_defaults(func=cmd_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
