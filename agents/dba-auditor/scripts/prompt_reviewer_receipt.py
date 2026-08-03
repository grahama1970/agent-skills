#!/usr/bin/env python3
from __future__ import annotations
"""Prompt-reviewer receipt gate for Dewey QRA repair.

This module is intentionally standalone: it has no database imports and no
network behavior.  It validates the local receipt contract that must be proven
before Dewey or monitor-sparta may launch create-qras for QRA coverage repair.
"""

import argparse
import dataclasses
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_REQUEST_V1 = "dewey.prompt-review.request.v1"
SCHEMA_RECEIPT_V1 = "dewey.prompt-review.receipt.v1"
PASS_VERDICT = "PASS"
VALID_VERDICTS = {"PASS", "NEEDS_CHANGES", "BLOCKED"}
INLINE_EMBEDDING_KEYS = {
    "embedding",
    "embeddings",
    "vector",
    "vectors",
    "dense_embedding",
    "dense_vector",
    "sparse_embedding",
    "sparse_vector",
    "qdrant_vector",
}
DEFAULT_PROMPT_REVIEWER_TIMEOUT_S = 7_200
DEFAULT_PROMPT_REVIEWER_AGENT = "prompt-reviewer"
DEFAULT_PROMPT_REVIEWER_TEMPLATE = (
    "ask.ask --agent prompt-reviewer --question-file {request_markdown} --receipt {receipt_json}"
)


class PromptReviewerGateError(RuntimeError):
    """Raised when a prompt-reviewer request or receipt violates contract."""


@dataclasses.dataclass(frozen=True)
class PromptReviewerGateResult:
    ok: bool
    verdict: str
    reason: str
    request_path: str | None = None
    receipt_path: str | None = None
    request_sha256: str | None = None
    mocked: bool = False
    live: bool = False
    command: list[str] | None = None
    returncode: int | None = None
    duration_s: float | None = None
    stdout_tail: str = ""
    stderr_tail: str = ""

    def to_json(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_json(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - error becomes explicit gate reason
        raise PromptReviewerGateError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PromptReviewerGateError(f"JSON document must be an object: {path}")
    return value


def write_json(path: Path, value: Mapping[str, Any]) -> Path:
    assert_no_inline_embedding_fields(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def find_inline_embedding_fields(value: Any, *, _path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_s = str(key)
            child_path = f"{_path}.{key_s}"
            if key_s in INLINE_EMBEDDING_KEYS:
                hits.append(child_path)
            hits.extend(find_inline_embedding_fields(child, _path=child_path))
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            hits.extend(find_inline_embedding_fields(child, _path=f"{_path}[{idx}]"))
    return hits


def assert_no_inline_embedding_fields(value: Mapping[str, Any]) -> None:
    hits = find_inline_embedding_fields(value)
    if hits:
        raise PromptReviewerGateError(
            "inline embedding/vector fields are forbidden in Dewey status/receipt artifacts: " + ", ".join(hits)
        )


def validate_prompt_review_request(request: Mapping[str, Any]) -> None:
    assert_no_inline_embedding_fields(request)
    required = [
        "schema_version",
        "request_id",
        "created_at",
        "task",
        "qra_generation_contract",
        "expected_response_contract",
        "qra_gap_context",
        "honesty",
    ]
    missing = [name for name in required if name not in request]
    if missing:
        raise PromptReviewerGateError(f"prompt-review request missing required fields: {', '.join(missing)}")
    if request.get("schema_version") != SCHEMA_REQUEST_V1:
        raise PromptReviewerGateError(f"unsupported prompt-review request schema_version={request.get('schema_version')!r}")
    if request.get("task") != "review_qra_generation_prompt_contract":
        raise PromptReviewerGateError("prompt-review request task must be review_qra_generation_prompt_contract")
    honesty = request.get("honesty")
    if not isinstance(honesty, Mapping):
        raise PromptReviewerGateError("prompt-review request honesty must be an object")
    for key in ("mocked", "live", "database_mutation_allowed"):
        if key not in honesty:
            raise PromptReviewerGateError(f"prompt-review request honesty missing {key}")
    if honesty.get("database_mutation_allowed") is not False:
        raise PromptReviewerGateError("prompt-review request must be a no-database-mutation artifact")
    for key in ("prompt_contract_ok_requirements", "required_output_fields", "disallowed_output_fields"):
        if key not in request.get("qra_generation_contract", {}):
            raise PromptReviewerGateError(f"qra_generation_contract missing {key}")
    for key in ("valid_verdicts", "receipt_path", "pass_requirements"):
        if key not in request.get("expected_response_contract", {}):
            raise PromptReviewerGateError(f"expected_response_contract missing {key}")


def make_prompt_review_request(
    *,
    request_id: str,
    failed_dimensions: Sequence[str],
    qra_missing_count: int | None,
    model_pool: str,
    receipt_path: Path,
    live: bool = False,
    mocked: bool = False,
    source_health_path: str | None = None,
) -> dict[str, Any]:
    request = {
        "schema_version": SCHEMA_REQUEST_V1,
        "request_id": request_id,
        "created_at": utc_now(),
        "task": "review_qra_generation_prompt_contract",
        "failed_dimensions": sorted(str(x) for x in failed_dimensions),
        "qra_gap_context": {
            "qra_missing_generation_required": qra_missing_count,
            "repair_owner": "Dewey DBA auditor",
            "repair_lane": "monitor-sparta create-qras backfill",
            "source_health_path": source_health_path,
        },
        "model_pool": model_pool,
        "qra_generation_contract": {
            "prompt_contract_ok_requirements": [
                "Prompt identifies exact SPARTA control/source/QRA gap inputs.",
                "Prompt requires structured JSON output only.",
                "Prompt forbids invented controls, sources, citations, or reviewed status.",
                "Prompt requires candidate trust state unless an external human review receipt is supplied.",
                "Prompt preserves source/provenance IDs and corpus/profile scope.",
            ],
            "required_output_fields": [
                "control_id",
                "question",
                "rationale",
                "answer_type",
                "source_refs",
                "trust_state",
                "generated_by",
                "generated_at",
            ],
            "disallowed_output_fields": [
                "embedding",
                "embeddings",
                "vector",
                "vectors",
                "expert_blessed",
                "human_reviewed",
            ],
            "database_write_policy": "candidate_only_no_inline_embeddings",
        },
        "expected_response_contract": {
            "valid_verdicts": sorted(VALID_VERDICTS),
            "receipt_path": str(receipt_path),
            "pass_requirements": [
                "verdict == PASS",
                "prompt_contract_ok == true",
                "response_contract_ok == true",
                "approved_for_qra_generation == true",
                "blocking_findings is empty",
                "receipt request_sha256 matches the request JSON",
            ],
        },
        "honesty": {
            "mocked": mocked,
            "live": live,
            "database_mutation_allowed": False,
            "does_not_prove": [
                "Dewey readiness",
                "QRA generation success",
                "monitor-sparta green",
                "human QRA review",
            ],
        },
    }
    validate_prompt_review_request(request)
    return request


def render_prompt_review_markdown(request: Mapping[str, Any], *, request_sha256: str) -> str:
    validate_prompt_review_request(request)
    receipt_path = request["expected_response_contract"]["receipt_path"]
    return "\n".join(
        [
            "# Prompt-reviewer QRA generation contract review",
            "",
            "You are the prompt-reviewer expert. Review this request only.",
            "",
            "## Required action",
            f"Write one JSON receipt to `{receipt_path}`.",
            "Do not mutate the database. Do not run create-qras. Do not add embeddings.",
            "",
            "## Required receipt fields",
            "- schema_version: dewey.prompt-review.receipt.v1",
            f"- request_sha256: {request_sha256}",
            "- verdict: PASS | NEEDS_CHANGES | BLOCKED",
            "- prompt_contract_ok: boolean",
            "- response_contract_ok: boolean",
            "- approved_for_qra_generation: boolean",
            "- blocking_findings: array",
            "- findings: array",
            "- honesty: { mocked, live, database_mutation_allowed }",
            "",
            "PASS is allowed only if the prompt and expected response contract are safe for candidate QRA generation.",
            "NEEDS_CHANGES or BLOCKED must explain the exact contract defect.",
            "",
            "## Request JSON",
            "```json",
            json.dumps(request, indent=2, sort_keys=True),
            "```",
            "",
        ]
    )


def write_prompt_review_bundle(
    out_dir: Path,
    *,
    request_id: str,
    failed_dimensions: Sequence[str],
    qra_missing_count: int | None,
    model_pool: str,
    live: bool = False,
    mocked: bool = False,
    source_health_path: str | None = None,
) -> tuple[Path, Path, Path, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = out_dir / "prompt-reviewer-receipt.json"
    request = make_prompt_review_request(
        request_id=request_id,
        failed_dimensions=failed_dimensions,
        qra_missing_count=qra_missing_count,
        model_pool=model_pool,
        receipt_path=receipt_path,
        live=live,
        mocked=mocked,
        source_health_path=source_health_path,
    )
    request_path = write_json(out_dir / "prompt-review-request.json", request)
    request_sha = sha256_file(request_path)
    markdown_path = out_dir / "prompt-review-request.md"
    markdown_path.write_text(render_prompt_review_markdown(request, request_sha256=request_sha), encoding="utf-8")
    return request_path, markdown_path, receipt_path, request_sha


def validate_prompt_reviewer_receipt(
    receipt: Mapping[str, Any],
    *,
    request: Mapping[str, Any] | None = None,
    request_sha256: str | None = None,
    allow_mock: bool = False,
    require_pass: bool = True,
) -> PromptReviewerGateResult:
    try:
        assert_no_inline_embedding_fields(receipt)
        if receipt.get("schema_version") != SCHEMA_RECEIPT_V1:
            raise PromptReviewerGateError(f"unsupported receipt schema_version={receipt.get('schema_version')!r}")
        verdict = str(receipt.get("verdict") or "").strip().upper()
        if verdict not in VALID_VERDICTS:
            raise PromptReviewerGateError(f"invalid prompt-reviewer verdict={verdict!r}")
        honesty = receipt.get("honesty")
        if not isinstance(honesty, Mapping):
            raise PromptReviewerGateError("receipt honesty must be an object")
        mocked = bool(honesty.get("mocked"))
        live = bool(honesty.get("live"))
        if mocked and not allow_mock:
            raise PromptReviewerGateError("mock prompt-reviewer receipt is not allowed")
        if honesty.get("database_mutation_allowed") is not False:
            raise PromptReviewerGateError("prompt-reviewer receipt must not allow database mutation")
        if request is not None:
            validate_prompt_review_request(request)
        if request_sha256 is not None and receipt.get("request_sha256") != request_sha256:
            raise PromptReviewerGateError(
                f"receipt request_sha256 mismatch: expected {request_sha256}, got {receipt.get('request_sha256')}"
            )
        if require_pass and verdict != PASS_VERDICT:
            raise PromptReviewerGateError(f"prompt-reviewer verdict is {verdict}, not PASS")
        if verdict == PASS_VERDICT:
            for key in ("prompt_contract_ok", "response_contract_ok", "approved_for_qra_generation"):
                if receipt.get(key) is not True:
                    raise PromptReviewerGateError(f"PASS receipt requires {key}=true")
            blocking = receipt.get("blocking_findings")
            if blocking not in ([], None):
                raise PromptReviewerGateError("PASS receipt requires empty blocking_findings")
        return PromptReviewerGateResult(
            ok=True,
            verdict=verdict,
            reason="prompt-reviewer receipt accepted",
            request_sha256=request_sha256,
            mocked=mocked,
            live=live,
        )
    except PromptReviewerGateError as exc:
        verdict = str(receipt.get("verdict") or "INVALID").strip().upper() if isinstance(receipt, Mapping) else "INVALID"
        honesty = receipt.get("honesty") if isinstance(receipt, Mapping) else {}
        return PromptReviewerGateResult(
            ok=False,
            verdict=verdict or "INVALID",
            reason=str(exc),
            request_sha256=request_sha256,
            mocked=bool(honesty.get("mocked")) if isinstance(honesty, Mapping) else False,
            live=bool(honesty.get("live")) if isinstance(honesty, Mapping) else False,
        )


def validate_receipt_file(
    receipt_path: Path,
    *,
    request_path: Path | None = None,
    allow_mock: bool = False,
    require_pass: bool = True,
) -> PromptReviewerGateResult:
    try:
        request = load_json(request_path) if request_path else None
        request_sha = sha256_file(request_path) if request_path else None
        receipt = load_json(receipt_path)
        result = validate_prompt_reviewer_receipt(
            receipt,
            request=request,
            request_sha256=request_sha,
            allow_mock=allow_mock,
            require_pass=require_pass,
        )
        return dataclasses.replace(result, request_path=str(request_path) if request_path else None, receipt_path=str(receipt_path))
    except PromptReviewerGateError as exc:
        return PromptReviewerGateResult(
            ok=False,
            verdict="INVALID",
            reason=str(exc),
            request_path=str(request_path) if request_path else None,
            receipt_path=str(receipt_path),
        )


def build_prompt_reviewer_command(
    *,
    request_markdown: Path,
    receipt_json: Path,
    request_json: Path,
    template: str | None = None,
) -> list[str]:
    template = template or os.environ.get("DEWEY_PROMPT_REVIEWER_COMMAND_TEMPLATE") or DEFAULT_PROMPT_REVIEWER_TEMPLATE
    rendered = template.format(
        request_markdown=shlex.quote(str(request_markdown)),
        request_json=shlex.quote(str(request_json)),
        receipt_json=shlex.quote(str(receipt_json)),
        receipt=shlex.quote(str(receipt_json)),
    )
    return shlex.split(rendered)


def tail_text(value: str | bytes | None, limit: int = 8_000) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[-limit:]


def run_prompt_reviewer_command(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout_s: int = DEFAULT_PROMPT_REVIEWER_TIMEOUT_S,
) -> PromptReviewerGateResult:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            list(command),
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=timeout_s,
        )
        duration = round(time.monotonic() - started, 3)
        return PromptReviewerGateResult(
            ok=proc.returncode == 0,
            verdict="COMMAND_OK" if proc.returncode == 0 else "COMMAND_FAILED",
            reason="prompt-reviewer command completed" if proc.returncode == 0 else "prompt-reviewer command failed",
            command=list(command),
            returncode=proc.returncode,
            duration_s=duration,
            stdout_tail=tail_text(proc.stdout),
            stderr_tail=tail_text(proc.stderr),
            live=True,
        )
    except subprocess.TimeoutExpired as exc:
        duration = round(time.monotonic() - started, 3)
        return PromptReviewerGateResult(
            ok=False,
            verdict="COMMAND_TIMEOUT",
            reason=f"prompt-reviewer command timed out after {exc.timeout}s",
            command=list(command),
            returncode=None,
            duration_s=duration,
            stdout_tail=tail_text(exc.stdout),
            stderr_tail=tail_text(exc.stderr),
            live=True,
        )


def sample_pass_receipt(*, request_sha256: str, live: bool = False, mocked: bool = True) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_RECEIPT_V1,
        "created_at": utc_now(),
        "reviewer_agent": DEFAULT_PROMPT_REVIEWER_AGENT,
        "request_sha256": request_sha256,
        "verdict": "PASS",
        "prompt_contract_ok": True,
        "response_contract_ok": True,
        "approved_for_qra_generation": True,
        "blocking_findings": [],
        "findings": [
            {
                "severity": "info",
                "message": "Fixture receipt for isolated validation only; not live closure proof.",
            }
        ],
        "honesty": {
            "mocked": mocked,
            "live": live,
            "database_mutation_allowed": False,
            "does_not_prove": ["live prompt-reviewer execution", "QRA generation success", "monitor-sparta green"],
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dewey prompt-reviewer receipt helper")
    sub = parser.add_subparsers(dest="command", required=True)

    mk = sub.add_parser("make-request")
    mk.add_argument("--out-dir", required=True)
    mk.add_argument("--request-id", default="dewey-prompt-review-smoke")
    mk.add_argument("--failed-dimension", action="append", default=["qra_coverage_per_control"])
    mk.add_argument("--qra-missing-count", type=int, default=None)
    mk.add_argument("--model-pool", default="qra-deepseek-pool")
    mk.add_argument("--live", action="store_true")
    mk.add_argument("--mocked", action="store_true")

    val = sub.add_parser("validate")
    val.add_argument("--receipt", required=True)
    val.add_argument("--request")
    val.add_argument("--allow-mock", action="store_true")
    val.add_argument("--allow-non-pass", action="store_true")
    val.add_argument("--json", action="store_true")

    sp = sub.add_parser("sample-pass")
    sp.add_argument("--request", required=True)
    sp.add_argument("--out", required=True)
    sp.add_argument("--live", action="store_true")
    sp.add_argument("--mocked", action="store_true", default=True)

    cmd = sub.add_parser("command")
    cmd.add_argument("--request-markdown", required=True)
    cmd.add_argument("--request-json", required=True)
    cmd.add_argument("--receipt-json", required=True)
    cmd.add_argument("--template")
    cmd.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "make-request":
        req, md, receipt, sha = write_prompt_review_bundle(
            Path(args.out_dir),
            request_id=args.request_id,
            failed_dimensions=args.failed_dimension,
            qra_missing_count=args.qra_missing_count,
            model_pool=args.model_pool,
            live=args.live,
            mocked=args.mocked,
        )
        print(json.dumps({"request_json": str(req), "request_markdown": str(md), "receipt_json": str(receipt), "request_sha256": sha}, sort_keys=True))
        return 0
    if args.command == "validate":
        result = validate_receipt_file(
            Path(args.receipt),
            request_path=Path(args.request) if args.request else None,
            allow_mock=args.allow_mock,
            require_pass=not args.allow_non_pass,
        )
        if args.json:
            print(json.dumps(result.to_json(), sort_keys=True))
        else:
            print(f"ok={result.ok} verdict={result.verdict} reason={result.reason}")
        return 0 if result.ok else 12
    if args.command == "sample-pass":
        request_path = Path(args.request)
        request = load_json(request_path)
        validate_prompt_review_request(request)
        receipt = sample_pass_receipt(request_sha256=sha256_file(request_path), live=args.live, mocked=args.mocked)
        write_json(Path(args.out), receipt)
        print(str(args.out))
        return 0
    if args.command == "command":
        command = build_prompt_reviewer_command(
            request_markdown=Path(args.request_markdown),
            receipt_json=Path(args.receipt_json),
            request_json=Path(args.request_json),
            template=args.template,
        )
        if args.json:
            print(json.dumps({"command": command}, sort_keys=True))
        else:
            print(shlex.join(command))
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
