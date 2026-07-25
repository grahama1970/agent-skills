#!/usr/bin/env python3
"""Normalize WebGPT transport artifacts and deterministic recovery commands."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCHEMA = "surf.webgpt_transport_summary.v1"
SUMMARY_NAME = "webgpt_transport_summary.json"

PREFERRED_META_NAMES = (
    "02_response.meta.json",
    "02_roundtrip_response.meta.json",
    "response.md.meta.json",
    "response.meta.json",
    "roundtrip-preflight.json",
)
PREFERRED_RAW_NAMES = (
    "02_response.raw.md",
    "02_roundtrip_response.raw.md",
    "response.md.raw.md",
    "response.raw.md",
)
PREFERRED_RECEIPT_NAMES = (
    "02_response.receipt.json",
    "02_roundtrip_response.md.receipt.json",
    "response.md.receipt.json",
    "response.receipt.json",
)
PREFERRED_SUBMITTED_NAMES = (
    "submitted.md",
    "02_response.submitted.md",
    "02_roundtrip_response.submitted.md",
    "response.md.submitted.md",
    "response.submitted.md",
)
PREFERRED_INFLIGHT_NAMES = (
    "webgpt_inflight.json",
)


def _read_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _first_existing(directory: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        candidate = directory / name
        if candidate.exists():
            return candidate
    return None


def _resolve_path(directory: Path, value: str | None, fallbacks: tuple[str, ...]) -> Path | None:
    if value:
        path = Path(value)
        if not path.is_absolute():
            path = directory / path
        if path.exists():
            return path
    return _first_existing(directory, fallbacks)


def discover_artifacts(directory: Path) -> dict[str, Path | None]:
    directory = directory.resolve()
    meta = _first_existing(directory, PREFERRED_META_NAMES)
    meta_data = _read_json(meta)
    inflight = _first_existing(directory, PREFERRED_INFLIGHT_NAMES)
    raw = _resolve_path(
        directory,
        str(meta_data.get("raw_output") or ""),
        PREFERRED_RAW_NAMES,
    )
    receipt = _resolve_path(
        directory,
        str(meta_data.get("receipt_output") or ""),
        PREFERRED_RECEIPT_NAMES,
    )
    submitted = _resolve_path(
        directory,
        str(meta_data.get("submitted_output") or ""),
        PREFERRED_SUBMITTED_NAMES,
    )
    return {
        "directory": directory,
        "meta": meta,
        "raw": raw,
        "receipt": receipt,
        "submitted": submitted,
        "inflight": inflight,
    }


def _submitted_to_chatgpt(meta: dict[str, Any], receipt: dict[str, Any], raw_path: Path | None) -> bool:
    if receipt.get("submitted_to_chatgpt") or meta.get("submitted_to_chatgpt"):
        return True
    status = str(meta.get("status") or "")
    if status in {"missing_sentinel", "completed", "recovered_focus_changed", "failed"} and raw_path and raw_path.exists():
        return True
    return False


def _raw_contains_sentinel(meta: dict[str, Any], receipt: dict[str, Any], raw_path: Path | None) -> bool:
    if meta.get("raw_contains_sentinel") is True:
        return True
    sentinel = str(meta.get("sentinel") or receipt.get("sentinel") or "")
    if not sentinel or raw_path is None or not raw_path.exists():
        return False
    try:
        return sentinel in raw_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def _identity_verified_requested_tab(meta: dict[str, Any]) -> bool:
    identity = meta.get("tab_identity_preflight")
    if not isinstance(identity, dict) or identity.get("ok") is not True:
        return False
    requested_tab = str(meta.get("requested_tab_id") or "").strip()
    if not requested_tab:
        return False
    tab = identity.get("tab")
    if not isinstance(tab, dict):
        tab = {}
    identity_tab = str(identity.get("tab_id") or tab.get("id") or "").strip()
    return identity_tab == requested_tab


def _degraded_focus_response_available(
    meta: dict[str, Any],
    receipt: dict[str, Any],
    raw_path: Path | None,
) -> bool:
    failure = str(meta.get("failure") or "")
    if failure not in {"focus_stolen_mid_submit", "focus_stolen_despite_no_activate"}:
        return False
    if meta.get("focus_invariant_ok") is not False:
        return False
    if not _identity_verified_requested_tab(meta):
        return False
    if not _raw_contains_sentinel(meta, receipt, raw_path):
        return False
    if meta.get("clean_contains_sentinel") is True:
        return False
    if meta.get("clean_contamination_markers"):
        return False
    return True


def _transport_state(meta: dict[str, Any], receipt: dict[str, Any], raw_path: Path | None, meta_path: Path | None) -> str:
    status = str(meta.get("status") or "")
    failure = str(meta.get("failure") or "")
    submitted = _submitted_to_chatgpt(meta, receipt, raw_path)
    receipt_status = str(receipt.get("status") or "")
    raw_has_sentinel = _raw_contains_sentinel(meta, receipt, raw_path)

    if status == "missing_sentinel" or failure == "missing_sentinel":
        return "missing_sentinel"
    if not submitted and (
        receipt_status == "prepared_prompt"
        or (receipt_status and receipt_status != "submitted_to_chatgpt")
    ):
        return "prepared_prompt_only"
    if status == "recovered_focus_changed" and not raw_has_sentinel:
        return "missing_sentinel"
    if status == "recovered_focus_changed":
        return "completed_with_focus_drift"
    if status == "completed" and not raw_has_sentinel:
        return "missing_sentinel"
    if status == "completed" and meta.get("focus_changed"):
        return "completed_with_focus_drift"
    if status == "completed":
        return "completed"
    if submitted and meta_path is None:
        return "missing_response_artifacts"
    if submitted and meta.get("response_timed_out") and raw_path is None:
        return "missing_response_artifacts"
    if submitted and _degraded_focus_response_available(meta, receipt, raw_path):
        return "completed_with_focus_drift"
    if submitted and not raw_has_sentinel and status not in {"completed", "recovered_focus_changed"}:
        return "submitted_only"
    if status:
        return status
    if submitted:
        return "submitted_only"
    return "unknown"


def _needs_attention_code(state: str, meta: dict[str, Any], raw_path: Path | None, meta_path: Path | None) -> str | None:
    if state == "missing_response_artifacts":
        return "NEEDS_ATTENTION: missing_webgpt_transport_artifacts"
    if state == "missing_sentinel" and (raw_path is None or meta_path is None):
        return "NEEDS_ATTENTION: missing_webgpt_transport_artifacts"
    if state == "unknown" and not meta:
        return "NEEDS_ATTENTION: missing_webgpt_transport_artifacts"
    if meta.get("response_timed_out") and state in {"submitted_only", "missing_sentinel"}:
        return "NEEDS_ATTENTION: webgpt_response_timeout"
    return None


def build_recovery(
    *,
    directory: Path,
    meta: dict[str, Any],
    receipt: dict[str, Any],
    raw_path: Path | None,
    meta_path: Path | None,
    submitted_path: Path | None,
) -> dict[str, Any]:
    state = _transport_state(meta, receipt, raw_path, meta_path)
    sentinel = str(meta.get("sentinel") or receipt.get("sentinel") or "")
    requested_tab_id = str(
        meta.get("requested_tab_id")
        or receipt.get("requested_tab_id")
        or meta.get("controlled_tab_id")
        or ""
    ).strip()
    requested_url = str(meta.get("requested_url") or receipt.get("requested_url") or "").strip()
    raw_has_sentinel = _raw_contains_sentinel(meta, receipt, raw_path)
    failure = str(meta.get("failure") or "")
    needs_attention = _needs_attention_code(state, meta, raw_path, meta_path)
    output_path = Path(str(meta.get("output") or receipt.get("output") or directory / "02_response.md"))
    raw_output_path = Path(str(meta.get("raw_output") or receipt.get("raw_output") or directory / "02_response.raw.md"))
    meta_output_path = Path(str(meta.get("meta_output") or receipt.get("meta_output") or directory / "02_response.meta.json"))
    if not output_path.is_absolute():
        output_path = directory / output_path
    if not raw_output_path.is_absolute():
        raw_output_path = directory / raw_output_path
    if not meta_output_path.is_absolute():
        meta_output_path = directory / meta_output_path
    claim_available = bool(
        requested_tab_id
        and sentinel
        and state in {"submitted_only", "missing_sentinel", "missing_response_artifacts"}
    )
    claim = {
        "available": claim_available,
        "tab_id": requested_tab_id or None,
        "sentinel": sentinel or None,
        "output": str(output_path),
        "raw_output": str(raw_output_path),
        "meta_output": str(meta_output_path),
        "wait": True,
        "stable_polls": 3,
    }

    reason = str(meta.get("agent_diagnosis") or "")
    next_command = ""
    do_not_do: list[str] = []

    if state == "completed":
        reason = reason or "Transport completed with current sentinel-bearing response."
        next_command = f"surf webgpt.recover --artifact-dir {directory} --audit"
    elif state == "completed_with_focus_drift":
        reason = reason or "Transport completed with focus drift; preserve degraded evidence and audit artifacts."
        next_command = f"surf webgpt.recover --artifact-dir {directory} --audit"
        do_not_do.append("do_not_treat_focus_drift_as_transport_failure_when_sentinel_matches")
    elif state == "prepared_prompt_only":
        reason = reason or "Prompt was prepared but not submitted to ChatGPT."
        tab_args = f"--tab-id {requested_tab_id}" if requested_tab_id else (
            f"--url {requested_url}" if requested_url else "--create-tab"
        )
        next_command = (
            f"surf webgpt.preflight {tab_args} && "
            f"surf webgpt.submit --input {submitted_path or directory / 'submitted.md'} "
            f"--output {directory / '02_response.md'}"
        )
        do_not_do.append("do_not_treat_prepared_prompt_as_completion_proof")
    elif state == "submitted_only":
        reason = reason or "Prompt was submitted but response transport proof is not available yet."
        if claim_available:
            next_command = (
                f"surf webgpt.extract --tab-id {requested_tab_id} "
                f"--output {output_path} "
                f"--raw-output {raw_output_path} "
                f"--meta-output {meta_output_path} "
                f"--sentinel '{sentinel}'"
            )
        else:
            next_command = f"surf webgpt.recover --artifact-dir {directory}"
        do_not_do.extend(["do_not_claim_completion", "do_not_retry_submit_until_timeout"])
    elif state == "missing_sentinel":
        reason = reason or "Response text exists but current sentinel is missing or stale."
        if requested_tab_id and sentinel and raw_path and raw_path.exists():
            next_command = (
                f"surf webgpt.extract --tab-id {requested_tab_id} "
                f"--output {directory / '02_response.md'} "
                f"--raw-output {directory / '02_response.raw.md'} "
                f"--meta-output {directory / '02_response.meta.json'} "
                f"--sentinel '{sentinel}'"
            )
            do_not_do.append("do_not_accept_stale_sentinel_as_current_turn_proof")
        elif needs_attention:
            next_command = needs_attention
            do_not_do.append("do_not_mark_pass_without_current_sentinel")
        else:
            tab_args = f"--tab-id {requested_tab_id}" if requested_tab_id else (
                f"--url {requested_url}" if requested_url else "--create-tab"
            )
            next_command = (
                f"surf webgpt.preflight {tab_args} && "
                f"surf webgpt.submit --input {submitted_path or directory / 'submitted.md'} "
                f"--output {directory / '02_response.md'}"
            )
    elif state == "missing_response_artifacts" and claim_available:
        reason = reason or "Prompt was submitted and the submit process left no response artifacts; recover by claiming the controlled tab DOM."
        next_command = (
            f"surf webgpt.extract --tab-id {requested_tab_id} "
            f"--output {output_path} "
            f"--raw-output {raw_output_path} "
            f"--meta-output {meta_output_path} "
            f"--sentinel '{sentinel}'"
        )
        needs_attention = None
        do_not_do.extend(["do_not_claim_completion_before_extract", "do_not_retry_submit_blindly"])
    elif state == "missing_response_artifacts" or needs_attention:
        reason = reason or "Submitted run is missing raw/meta transport artifacts."
        next_command = needs_attention or "NEEDS_ATTENTION: missing_webgpt_transport_artifacts"
        do_not_do.extend(["do_not_claim_completion", "do_not_retry_submit_blindly"])
    elif failure in {"tab_identity_preflight_failed", "controlled_tab_id_mismatch"}:
        reason = reason or "Tab identity proof failed for the requested reviewer tab."
        tab_args = f"--url {requested_url}" if requested_url else "--create-tab"
        next_command = f"surf webgpt.preflight {tab_args} && surf tab.list"
        do_not_do.append("do_not_submit_to_foreground_or_newest_chatgpt_tab")
    elif failure in {"roundtrip_preflight_failed", "create_tab_navigation_failed", "submit_failed"}:
        reason = reason or "Submit path failed before producing transport proof."
        tab_args = f"--tab-id {requested_tab_id}" if requested_tab_id else (
            f"--url {requested_url}" if requested_url else "--create-tab"
        )
        next_command = f"surf webgpt.preflight {tab_args}"
        if requested_tab_id and sentinel and not raw_has_sentinel:
            next_command = (
                f"surf webgpt.extract --tab-id {requested_tab_id} "
                f"--output {directory / '02_response.md'} "
                f"--sentinel '{sentinel}'"
            )
        do_not_do.append("do_not_retry_submit_without_preflight")
    else:
        reason = reason or "Transport state is not mapped to a known recovery branch."
        next_command = f"surf webgpt.recover --artifact-dir {directory}"
        do_not_do.append("do_not_infer_completion_from_submitted_markers")

    return {
        "state": state,
        "reason": reason,
        "next_command": next_command,
        "do_not_do": do_not_do,
        "needs_attention": needs_attention,
        "claim": claim,
    }


def build_transport_summary(
    directory: Path,
    *,
    meta_path: Path | None = None,
    receipt_path: Path | None = None,
    raw_path: Path | None = None,
    submitted_path: Path | None = None,
) -> dict[str, Any]:
    directory = directory.resolve()
    discovered = discover_artifacts(directory)
    meta_file = meta_path or discovered["meta"]
    receipt_file = receipt_path or discovered["receipt"]
    raw_file = raw_path or discovered["raw"]
    submitted_file = submitted_path or discovered["submitted"]

    meta = _read_json(meta_file)
    receipt = _read_json(receipt_file)
    inflight = _read_json(discovered["inflight"])
    if inflight:
        for key in (
            "sentinel",
            "requested_tab_id",
            "requested_url",
            "output",
            "raw_output",
            "meta_output",
            "submitted_output",
        ):
            if not meta.get(key) and inflight.get(key):
                meta[key] = inflight[key]
            if not receipt.get(key) and inflight.get(key):
                receipt[key] = inflight[key]
        if inflight.get("submitted_to_chatgpt") and not receipt.get("submitted_to_chatgpt"):
            receipt["submitted_to_chatgpt"] = True
            receipt["status"] = receipt.get("status") or "submitted_to_chatgpt"

    if raw_file is None and meta.get("raw_output"):
        candidate = directory / str(meta["raw_output"])
        raw_file = candidate if candidate.exists() else raw_file
    if submitted_file is None and meta.get("submitted_output"):
        candidate = directory / str(meta["submitted_output"])
        submitted_file = candidate if candidate.exists() else submitted_file

    recovery = build_recovery(
        directory=directory,
        meta=meta,
        receipt=receipt,
        raw_path=raw_file,
        meta_path=meta_file,
        submitted_path=submitted_file,
    )
    sentinel = str(meta.get("sentinel") or receipt.get("sentinel") or "")
    submitted = _submitted_to_chatgpt(meta, receipt, raw_file)
    receipt_status = str(receipt.get("status") or "")

    return {
        "schema": SCHEMA,
        "artifact_dir": str(directory),
        "requested_tab_id": meta.get("requested_tab_id") or receipt.get("requested_tab_id"),
        "requested_url": meta.get("requested_url") or receipt.get("requested_url"),
        "controlled_tab_id": meta.get("controlled_tab_id"),
        "submit_receipt_status": receipt_status or None,
        "submitted_to_chatgpt": submitted,
        "prepared_prompt_is_transport_proof": False,
        "response_raw_path": str(raw_file) if raw_file else None,
        "response_meta_path": str(meta_file) if meta_file else None,
        "response_receipt_path": str(receipt_file) if receipt_file else None,
        "submitted_path": str(submitted_file) if submitted_file else None,
        "sentinel": sentinel or None,
        "raw_sentinel_present": _raw_contains_sentinel(meta, receipt, raw_file),
        "focus_changed": meta.get("focus_changed"),
        "transport_degraded": bool(meta.get("transport_degraded")),
        "raw_response_advisory": bool(meta.get("raw_response_advisory")),
        "final_transport_state": recovery["state"],
        "proof_status": meta.get("proof_status"),
        "agent_diagnosis": meta.get("agent_diagnosis"),
        "agent_action": meta.get("agent_action"),
        "next_command": recovery["next_command"],
        "do_not_do": recovery["do_not_do"],
        "needs_attention": recovery["needs_attention"],
        "claim": recovery["claim"],
    }


def write_transport_summary(
    directory: Path,
    *,
    meta_path: Path | None = None,
    receipt_path: Path | None = None,
    raw_path: Path | None = None,
    submitted_path: Path | None = None,
) -> Path:
    summary = build_transport_summary(
        directory,
        meta_path=meta_path,
        receipt_path=receipt_path,
        raw_path=raw_path,
        submitted_path=submitted_path,
    )
    out_path = directory.resolve() / SUMMARY_NAME
    out_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return out_path


def recover(directory: Path) -> dict[str, Any]:
    discovered = discover_artifacts(directory)
    meta = _read_json(discovered["meta"])
    receipt = _read_json(discovered["receipt"])
    inflight = _read_json(discovered["inflight"])
    if inflight:
        for key in (
            "sentinel",
            "requested_tab_id",
            "requested_url",
            "output",
            "raw_output",
            "meta_output",
            "submitted_output",
        ):
            if not meta.get(key) and inflight.get(key):
                meta[key] = inflight[key]
            if not receipt.get(key) and inflight.get(key):
                receipt[key] = inflight[key]
        if inflight.get("submitted_to_chatgpt") and not receipt.get("submitted_to_chatgpt"):
            receipt["submitted_to_chatgpt"] = True
            receipt["status"] = receipt.get("status") or "submitted_to_chatgpt"
    recovery = build_recovery(
        directory=directory.resolve(),
        meta=meta,
        receipt=receipt,
        raw_path=discovered["raw"],
        meta_path=discovered["meta"],
        submitted_path=discovered["submitted"],
    )
    recovery["schema"] = "surf.webgpt_recover.v1"
    recovery["artifact_dir"] = str(directory.resolve())
    recovery["response_raw_path"] = str(discovered["raw"]) if discovered["raw"] else None
    recovery["response_meta_path"] = str(discovered["meta"]) if discovered["meta"] else None
    return recovery


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="WebGPT transport summary and recovery helpers")
    sub = parser.add_subparsers(dest="command", required=True)

    write_p = sub.add_parser("write-summary", help="Write webgpt_transport_summary.json")
    write_p.add_argument("--artifact-dir", required=True)
    write_p.add_argument("--meta", default="")
    write_p.add_argument("--receipt", default="")
    write_p.add_argument("--raw", default="")
    write_p.add_argument("--submitted", default="")

    recover_p = sub.add_parser("recover", help="Emit deterministic recovery JSON")
    recover_p.add_argument("--artifact-dir", required=True)

    args = parser.parse_args(argv)
    artifact_dir = Path(args.artifact_dir)

    if args.command == "write-summary":
        path = write_transport_summary(
            artifact_dir,
            meta_path=Path(args.meta) if args.meta else None,
            receipt_path=Path(args.receipt) if args.receipt else None,
            raw_path=Path(args.raw) if args.raw else None,
            submitted_path=Path(args.submitted) if args.submitted else None,
        )
        print(str(path))
        return 0

    if args.command == "recover":
        payload = recover(artifact_dir)
        print(json.dumps(payload, indent=2))
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
