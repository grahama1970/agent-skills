#!/usr/bin/env python3
"""Normalize provider submit metadata into Surf's provider-result contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROVIDER_KEYS = {
    "webgpt": ("submitted_to_chatgpt", "chatgpt_model", "chatgpt_reasoning"),
    "claude": ("submitted_to_claude", "claude_model", "claude_reasoning"),
    "gemini": ("submitted_to_gemini", "gemini_model", "gemini_reasoning"),
    "kimi": ("submitted_to_kimi", "kimi_model", "kimi_reasoning"),
    "grok": ("submitted_to_grok", "grok_model", "grok_reasoning"),
}

RETRYABLE_FAILURES = {
    "browser_handler_killed",
    "browser_handler_timeout",
    "too_many_requests",
    "provider_capacity",
    "provider_rate_limited",
    "read_timeout",
    "stalled_before_submit",
    "browser_tab_identity_rebind_required",
    "conversation_max_length",
    "response_not_finished",
}

NONTERMINAL_STATUSES = {
    "delivery_pending",
    "pending",
    "prepared_prompt",
    "running",
}


def read_text_arg(value: str | None, file_value: str | None) -> str:
    if file_value:
        try:
            return Path(file_value).expanduser().read_text(errors="replace")
        except OSError:
            return ""
    return value or ""


def triage_classify(text: str, layer: str = "surf") -> dict[str, Any] | None:
    """Delegate to /triage-error to canonicalize a raw failure signal.

    Fail-open: any import/lookup problem returns None so meta finalization is
    never blocked. Composes triage-error (best-practices-skills error policy).
    """
    try:
        import sys

        te_dir = Path(__file__).resolve().parents[2] / "triage-error"
        if str(te_dir) not in sys.path:
            sys.path.insert(0, str(te_dir))
        import classifier  # type: ignore

        return classifier.classify(text, layer)
    except Exception:  # noqa: BLE001 -- best-effort enrichment, never fatal
        return None


def command_returncode_kind(returncode: int | None, stderr_text: str) -> str | None:
    if returncode is None:
        return None
    lowered = stderr_text.lower()
    if returncode == 124 or "timed out" in lowered or "killed process group" in lowered:
        return "browser_handler_timeout"
    if returncode in {-9, 137}:
        return "browser_handler_killed"
    if returncode in {-15, 143}:
        return "browser_handler_interrupted"
    if returncode != 0:
        return "browser_handler_failed"
    return None


def unproven_proof_status(meta: dict[str, Any], failure_code: str) -> str:
    if failure_code == "not_submitted":
        return "not_submitted"
    if bool(
        first_present(
            meta,
            "submitted_to_chatgpt",
            "submitted_to_claude",
            "submitted_to_gemini",
            "submitted_to_kimi",
            "submitted_to_grok",
            "submitted_to_provider",
        )
    ):
        return "submitted_no_response_proof"
    return "delivery_not_proven"


def finalize_nonterminal_meta(
    meta: dict[str, Any],
    *,
    returncode: int | None,
    stderr_text: str,
    stdout_text: str,
    duration_seconds: float | None,
) -> dict[str, Any]:
    """Convert stale submit metadata into a terminal record using caller context.

    A provider wrapper cannot handle SIGKILL. The parent process is therefore the
    only reliable witness for killed or externally timed-out lanes.
    """
    status = str(meta.get("status") or "").lower()
    proof_status = str(meta.get("proof_status") or "").lower()
    should_finalize = (
        returncode is not None
        and returncode != 0
        and (status in NONTERMINAL_STATUSES or proof_status in NONTERMINAL_STATUSES or not status)
    )
    if not should_finalize:
        return meta

    failure_code = command_returncode_kind(returncode, stderr_text) or "browser_handler_failed"
    if status == "prepared_prompt" and not bool(first_present(meta, "submitted_to_chatgpt", "submitted_to_provider")):
        failure_code = "not_submitted"

    finished = dict(meta)
    finished["source_meta_status"] = meta.get("status")
    finished["source_meta_proof_status"] = meta.get("proof_status")
    finished["source_meta_finalized"] = True
    finished["status"] = {
        "browser_handler_timeout": "timeout",
        "browser_handler_killed": "killed",
        "browser_handler_interrupted": "interrupted",
        "not_submitted": "failed",
    }.get(failure_code, "failed")
    finished["failure"] = failure_code
    finished["blocker"] = {
        "browser_handler_timeout": "BROWSER_HANDLER_TIMEOUT",
        "browser_handler_killed": "BROWSER_HANDLER_KILLED",
        "browser_handler_interrupted": "BROWSER_HANDLER_INTERRUPTED",
        "not_submitted": "BROWSER_SUBMIT_NOT_ACCEPTED",
    }.get(failure_code, "BROWSER_HANDLER_FAILED")
    finished["proof_status"] = unproven_proof_status(meta, failure_code)
    # Canonicalize the failure via /triage-error: when the catalog has a more
    # specific code than the generic browser_handler_* one, attach it so
    # diagnosis is unambiguous (e.g. an attach-preflight rejection is not a
    # generic timeout). Best-effort; never overrides the primary failure field.
    _triage = triage_classify(f"{failure_code}\n{stderr_text}", "surf")
    if _triage and not _triage.get("ambiguous") and _triage.get("code") != failure_code:
        finished["triage"] = {
            "code": _triage["code"],
            "cause": _triage.get("cause"),
            "next_command": _triage.get("next_command"),
        }
    finished["returncode"] = returncode
    finished["exit_code"] = returncode
    if duration_seconds is not None:
        finished["command_duration_seconds"] = duration_seconds
    if stderr_text:
        finished["command_stderr_tail"] = stderr_text[-4000:]
    if stdout_text:
        finished["command_stdout_tail"] = stdout_text[-4000:]
    for key in (
        "submitted_to_chatgpt",
        "submitted_to_claude",
        "submitted_to_gemini",
        "submitted_to_kimi",
        "submitted_to_grok",
    ):
        if key in finished and finished[key] is None:
            finished[key] = False
    if finished.get("attach_file") and "attachment_delivery_proven" not in finished:
        finished["attachment_delivery_proven"] = False
    return finished

NON_RETRYABLE_FAILURES = {
    "prompt_too_large",
    "input_missing",
    "invalid_arguments",
    "tab_identity_mismatch",
    "controlled_tab_id_mismatch",
}


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        raise SystemExit(f"failed_to_read_meta_json:{path}:{exc}") from exc


def sha256_file(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def resolve_artifact(meta_path: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (meta_path.parent / path).resolve()
    return path


def infer_provider(meta: dict[str, Any], explicit: str | None) -> str:
    if explicit:
        return explicit
    provider = meta.get("provider") or meta.get("seat") or meta.get("handler")
    if isinstance(provider, str):
        lowered = provider.lower()
        for known in PROVIDER_KEYS:
            if known in lowered:
                return known
    for known, keys in PROVIDER_KEYS.items():
        if any(key in meta for key in keys):
            return known
    if "submitted_to_chatgpt" in meta or "sentinel" in meta:
        return "webgpt"
    return "unknown"


def first_present(meta: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = meta.get(key)
        if value not in (None, ""):
            return value
    return None


def artifact_record(meta_path: Path, meta: dict[str, Any], *keys: str) -> dict[str, Any]:
    value = first_present(meta, *keys)
    path = resolve_artifact(meta_path, value)
    return {
        "path": str(path) if path else None,
        "present": bool(path and path.exists()),
        "sha256": sha256_file(path) if path and path.exists() else None,
    }


def normalize_failure(meta: dict[str, Any], stderr_record: dict[str, Any]) -> dict[str, Any]:
    failure = first_present(
        meta,
        "failure",
        "failure_code",
        "error_code",
        "blocker",
        "reason",
        "recovery_reason",
        "exit_reason",
    )
    stderr_tail = None
    stderr_path = stderr_record.get("path")
    if stderr_path:
        try:
            stderr_tail = Path(stderr_path).read_text(errors="replace")[-4000:]
        except OSError:
            stderr_tail = None
    return {
        "code": failure,
        "message": first_present(meta, "error", "message", "details", "command_stderr_tail"),
        "exit_code": first_present(meta, "exit_code", "returncode"),
        "stderr_tail": first_present(meta, "command_stderr_tail") or stderr_tail,
    }


def retryability(meta: dict[str, Any], failure: dict[str, Any]) -> dict[str, Any]:
    if isinstance(meta.get("retryable"), bool):
        return {"retryable": meta["retryable"], "reason": meta.get("retry_reason") or "source_meta_retryable"}
    repair = first_present(meta, "auto_retry", "recovery_action", "next_action")
    code = str(failure.get("code") or "").lower()
    text = " ".join(str(value).lower() for value in [failure.get("message"), failure.get("stderr_tail")] if value)
    haystack = " ".join([code, text])
    if any(item in haystack for item in NON_RETRYABLE_FAILURES):
        return {"retryable": False, "reason": "non_retryable_failure_class"}
    if any(item in haystack for item in RETRYABLE_FAILURES):
        return {"retryable": True, "reason": "retryable_failure_class"}
    if repair:
        return {"retryable": True, "reason": f"repair_available:{repair}"}
    if meta.get("status") in {"completed", "ok"} or meta.get("proof_status") == "response_proven":
        return {"retryable": False, "reason": "successful_result"}
    return {"retryable": None, "reason": "unclassified"}


def normalize(meta_path: Path, meta: dict[str, Any], provider: str) -> dict[str, Any]:
    input_artifact = artifact_record(meta_path, meta, "input", "input_path", "request_path")
    submitted_artifact = artifact_record(meta_path, meta, "submitted_output", "submitted_prompt", "submitted_prompt_path")
    output_artifact = artifact_record(meta_path, meta, "output", "output_path", "clean_output")
    raw_artifact = artifact_record(meta_path, meta, "raw_output", "raw_output_path", "raw")
    stderr_artifact = artifact_record(meta_path, meta, "stderr_log", "stderr", "stderr_path")
    receipt_artifact = artifact_record(meta_path, meta, "receipt", "receipt_output", "receipt_path")
    failure = normalize_failure(meta, stderr_artifact)
    proof_status = first_present(meta, "proof_status", "status", "phase") or "unknown"
    controlled_id = first_present(meta, "controlled_tab_id", "controlled_view_id", "actual_tab_id", "tab_id")
    requested_id = first_present(meta, "requested_tab_id", "requested_view_id", "tab_id")
    raw_contains_sentinel = meta.get("raw_contains_sentinel")
    sentinel = meta.get("sentinel") or meta.get("marker")
    delivery_submitted = bool(
        first_present(
            meta,
            "submitted_to_chatgpt",
            "submitted_to_claude",
            "submitted_to_gemini",
            "submitted_to_kimi",
            "submitted_to_grok",
            "submitted_to_provider",
        )
    )
    success = proof_status == "response_proven" or (
        meta.get("status") in {"completed", "ok"}
        and (raw_contains_sentinel is not False)
        and (controlled_id is None or requested_id is None or str(controlled_id) == str(requested_id))
    )
    retry = retryability(meta, failure)

    return {
        "schema": "surf.provider_result.v1",
        "schema_version": "1.0.0",
        "normalized_at": datetime.now(timezone.utc).isoformat(),
        "source_meta": str(meta_path),
        "provider": provider,
        "status": meta.get("status"),
        "phase": meta.get("phase"),
        "proof_status": proof_status,
        "success": bool(success),
        "delivery": {
            "submitted": delivery_submitted,
            "delivery_proven": delivery_submitted or raw_contains_sentinel is True,
            "sentinel": sentinel,
            "raw_contains_sentinel": raw_contains_sentinel,
        },
        "target": {
            "requested_tab_id": requested_id,
            "controlled_tab_id": meta.get("controlled_tab_id"),
            "requested_view_id": meta.get("requested_view_id"),
            "controlled_view_id": meta.get("controlled_view_id"),
            "requested_url": first_present(meta, "requested_url", "expect_url", "expected_url"),
            "actual_url": first_present(meta, "actual_url", "current_url", "conversation_url", "url"),
            "controlled_tab_id_mismatch": meta.get("controlled_tab_id_mismatch"),
        },
        "model": {
            "requested": first_present(meta, "model", "requested_model", f"{provider}_model"),
            "observed": first_present(meta, "observed_model", "selected_model"),
            "reasoning": first_present(meta, "reasoning", "requested_reasoning", "selected_reasoning", f"{provider}_reasoning"),
            "selection_proven": meta.get("model_selection_proven") or meta.get("reasoning_selection_proven"),
        },
        "artifacts": {
            "input": input_artifact,
            "submitted_output": submitted_artifact,
            "output": output_artifact,
            "raw_output": raw_artifact,
            "stderr_log": stderr_artifact,
            "receipt": receipt_artifact,
            "meta": {
                "path": str(meta_path),
                "present": meta_path.exists(),
                "sha256": sha256_file(meta_path),
            },
        },
        "attachments": {
            "requested": bool(first_present(meta, "attach_file", "attachment_path")),
            "path": first_present(meta, "attach_file", "attachment_path"),
            "metadata": meta.get("attachment"),
            "delivery_proven": meta.get("attachment_delivery_proven"),
            "missing": meta.get("attachment_missing"),
        },
        "immutable_request_snapshot": {
            "required": True,
            "present": input_artifact["present"] and submitted_artifact["present"],
            "input_sha256": input_artifact["sha256"],
            "submitted_sha256": submitted_artifact["sha256"],
        },
        "retryability": retry,
        "stale_binding_repair": {
            "detected": bool(first_present(meta, "stale_binding_detected", "browser_tab_identity_mismatch")),
            "repair_attempted": bool(first_present(meta, "stale_binding_repair_attempted", "browser_oracle_rebind_attempted")),
            "repair_result": first_present(meta, "stale_binding_repair_result", "browser_oracle_rebind_result"),
            "new_tab_id": first_present(meta, "new_tab_id", "rebound_tab_id"),
            "new_url": first_present(meta, "new_url", "rebound_url"),
        },
        "bounded_error": failure,
    }


def strict_errors(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    artifacts = payload["artifacts"]
    for key in ("input", "submitted_output", "output", "raw_output"):
        if not artifacts[key]["present"]:
            errors.append(f"missing_artifact:{key}")
    if not payload["immutable_request_snapshot"]["present"]:
        errors.append("missing_immutable_request_snapshot")
    target = payload["target"]
    if not (target.get("controlled_tab_id") or target.get("controlled_view_id")):
        errors.append("missing_controlled_tab_or_view")
    if payload["delivery"]["sentinel"] and payload["delivery"]["raw_contains_sentinel"] is False:
        errors.append("sentinel_not_found_in_raw_output")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meta", required=True, help="provider response meta JSON")
    parser.add_argument("--provider", choices=sorted(PROVIDER_KEYS) + ["unknown"])
    parser.add_argument("--json", action="store_true", help="emit JSON; currently the default output")
    parser.add_argument("--strict", action="store_true", help="exit nonzero if immutable/proof artifacts are incomplete")
    parser.add_argument("--return-code", type=int, help="provider submit command return code from the parent")
    parser.add_argument("--duration-seconds", type=float, help="provider submit command duration from the parent")
    parser.add_argument("--command-stderr", help="provider submit command stderr text from the parent")
    parser.add_argument("--command-stderr-file", help="file containing provider submit command stderr text")
    parser.add_argument("--command-stdout", help="provider submit command stdout text from the parent")
    parser.add_argument("--command-stdout-file", help="file containing provider submit command stdout text")
    args = parser.parse_args()

    meta_path = Path(args.meta).expanduser().resolve()
    meta = load_json(meta_path)
    meta = finalize_nonterminal_meta(
        meta,
        returncode=args.return_code,
        stderr_text=read_text_arg(args.command_stderr, args.command_stderr_file),
        stdout_text=read_text_arg(args.command_stdout, args.command_stdout_file),
        duration_seconds=args.duration_seconds,
    )
    provider = infer_provider(meta, args.provider)
    payload = normalize(meta_path, meta, provider)
    errors = strict_errors(payload) if args.strict else []
    payload["strict_ok"] = not errors
    payload["strict_errors"] = errors
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
