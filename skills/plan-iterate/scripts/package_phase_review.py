#!/usr/bin/env python3
"""package_phase_review - scripts.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
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


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
TEMPLATE_DIR = SKILL_DIR / "templates"


def now_stamp() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def slug(value: str) -> str:
    return "".join(character if character.isalnum() or character in {"-", "_"} else "-" for character in value.strip()).strip("-") or "reviewer"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def phase_dir(root: Path, phase: str) -> Path:
    return root / phase


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
    (target_dir / "skill-context").mkdir(exist_ok=True)
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

        for artifact_key in ["evidence_artifacts", "progress_context_artifacts", "skill_context_artifacts"]:
            for artifact in status.get(artifact_key, []):
                source, artifact_name = _artifact_source(target_dir, artifact)
                if source.is_file():
                    arcname = _safe_archive_name(artifact_name)
                    _zip_add_file(bundle, source, arcname, entries)

        manifest = {
            "schema": "plan_iterate.review_bundle_manifest.v1",
            "phase_id": args.phase,
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
    copied_review = reviews_dir / f"{recorded_at}-{reviewer_id}-response.md"
    copied_request = reviews_dir / f"{recorded_at}-{reviewer_id}-request{review_request.suffix or '.txt'}"
    copied_bundle = reviews_dir / f"{recorded_at}-{reviewer_id}-bundle{review_bundle.suffix or '.zip'}"
    copied_receipt = reviews_dir / f"{recorded_at}-{reviewer_id}-invocation{invocation_receipt.suffix or '.json'}"
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
    candidate_status["review_status"] = args.verdict
    reviewer_policy = candidate_status.setdefault(
        "reviewer_policy",
        {
            "required": True,
            "comparison_required": False,
            "closure_rule": "deterministic_validation_and_external_review",
        },
    )
    if args.verdict in {"blocked", "needs_changes", "conditional_pass"}:
        candidate_status["status"] = "external_review_blocked"
    elif args.verdict == "passed" and not reviewer_policy.get("comparison_required", False):
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
    candidate_status["review_results"].append(
        {
            "reviewer_id": args.reviewer,
            "adjudicator_kind": args.adjudicator_kind,
            "verdict": args.verdict,
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
            "agreement": "agree" if args.verdict == "passed" else "disagree",
            "closure_allowed": args.verdict == "passed",
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
    review_parser.add_argument("--verdict", required=True, choices=["passed", "conditional_pass", "needs_changes", "blocked"])
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

    comparison_parser = subparsers.add_parser("record-comparison")
    comparison_parser.add_argument("--phase", required=True)
    comparison_parser.add_argument("--agreement", required=True, choices=["agree", "partial", "disagree", "insufficient"])
    comparison_parser.add_argument("--closure-allowed", action="store_true")
    comparison_parser.add_argument("--reason", required=True)
    comparison_parser.add_argument("--repo-root", default=".")
    comparison_parser.set_defaults(func=cmd_record_comparison)

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
