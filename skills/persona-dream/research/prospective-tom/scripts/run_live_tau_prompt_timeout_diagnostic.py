#!/usr/bin/env python3
"""Diagnose Persona Dream PCTOM-R Tau prompt timeout boundaries."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
RESEARCH_ROOT = ROOT / "research" / "prospective-tom"
BUILD_CORPUS_SCRIPT = RESEARCH_ROOT / "scripts" / "build_social_episode_corpus.py"
LIVE_CONDITION_SCRIPT = RESEARCH_ROOT / "scripts" / "run_live_tau_condition_comparison.py"
STRICT_SCRIPT = RESEARCH_ROOT / "scripts" / "run_live_tau_strict_inference_prompt_replication.py"
TAU_ADAPTER = ROOT / "scripts" / "tau_text_reasoning_adapter.py"
PASS_STATUS = "PASS_LIVE_TAU_PCTOM_PROMPT_TIMEOUT_DIAGNOSTIC"
BLOCKED_STATUS = "BLOCKED_LIVE_TAU_PCTOM_PROMPT_TIMEOUT_DIAGNOSTIC"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _text_sha256(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot_load_module:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _simple_contract() -> dict[str, Any]:
    return {
        "schema": "persona_dream.research.prospective_tom.prompt_timeout_diagnostic_contract.v1",
        "required_top_level_keys": ["diagnostic_ready", "case_id"],
        "requirements": [
            "Return exactly one JSON object and no prose.",
            "diagnostic_ready must be true when the prompt was processed.",
            "case_id must echo the requested diagnostic case id.",
        ],
    }


def _simple_prompt(case_id: str, body: str) -> str:
    return (
        "You are running a Persona Dream PCTOM-R Tau prompt timeout diagnostic.\n"
        f"Diagnostic case id: {case_id}\n"
        "Read the diagnostic payload only enough to confirm it was received.\n"
        f"Return exactly this JSON shape: {{\"diagnostic_ready\":true,\"case_id\":\"{case_id}\"}}\n"
        "Diagnostic payload follows:\n"
        f"{body}"
    )


def _pad_to_bytes(prefix: str, target_bytes: int) -> str:
    encoded = prefix.encode("utf-8")
    if len(encoded) >= target_bytes:
        return prefix
    return prefix + ("x" * (target_bytes - len(encoded)))


def _diagnostic_error_signature(error: str) -> str | None:
    if "Tau dispatch timed out after" in error:
        return "tau_text_reasoning_timeout"
    if "scillm_http_status_401" in error:
        return "tau_scillm_auth_401"
    if "scillm_api_key_unavailable" in error:
        return "tau_scillm_api_key_unavailable"
    return None


def _boundary_receipt(
    *,
    case_id: str,
    role: str,
    model: str | None,
    prompt: str,
    output_contract: dict[str, Any],
    timeout_s: float,
    elapsed_s: float,
    error: str,
) -> dict[str, Any]:
    return {
        "schema": "persona_dream.research.prospective_tom.tau_prompt_timeout_diagnostic_case_receipt.v1",
        "created_at": _now_iso(),
        "case_id": case_id,
        "role": role,
        "mocked": False,
        "live": False,
        "surface": "tau:persona-dream-text-reasoning",
        "model": model,
        "caller_skill": "persona-dream",
        "prompt_sha256": _text_sha256(prompt),
        "prompt_char_count": len(prompt),
        "prompt_byte_count": len(prompt.encode("utf-8")),
        "output_contract_sha256": _stable_json_sha256(output_contract),
        "timeout_s": timeout_s,
        "elapsed_s": round(elapsed_s, 3),
        "status": "BLOCKED_DISPATCH_ERROR",
        "error": error,
        "systemic_failure_signature": _diagnostic_error_signature(error),
        "live_call_performed": False,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
    }


def _case_defs(live: Any, strict: Any, build: Any, *, split: str, episodes_per_family: int, condition: str) -> list[dict[str, Any]]:
    corpus = build.build_corpus(split, episodes_per_family)
    episode = corpus["episodes"][0]
    actual_prompt = live._prompt(episode, condition)
    strict_prompt = strict._strict_prompt(live, episode, condition)
    simple_contract = _simple_contract()
    preflight_prompt = live._preflight_prompt()
    padded_prefix = _simple_prompt("padded_to_condition_size", "payload:")
    padded_prompt = _pad_to_bytes(padded_prefix, len(actual_prompt.encode("utf-8")))
    domain_payload = {
        "episode_visible_to_agent": live._visible_packet(episode),
        "prediction_targets_without_truth_values": live._prediction_targets(episode),
        "allowed_next_actions": episode.get("allowed_next_actions"),
        "condition_instruction": live.CONDITION_INSTRUCTIONS[condition],
        "required_ids": live._ids(episode["episode_id"], condition),
    }
    domain_prompt = _simple_prompt("domain_payload_simple_response", json.dumps(domain_payload, indent=2, sort_keys=True))
    return [
        {
            "case_id": "preflight_short",
            "prompt": preflight_prompt,
            "output_contract": live._preflight_output_contract(),
            "expected_case_id": None,
        },
        {
            "case_id": "padded_to_condition_size",
            "prompt": padded_prompt,
            "output_contract": simple_contract,
            "expected_case_id": "padded_to_condition_size",
        },
        {
            "case_id": "domain_payload_simple_response",
            "prompt": domain_prompt,
            "output_contract": simple_contract,
            "expected_case_id": "domain_payload_simple_response",
        },
        {
            "case_id": "actual_condition_prompt",
            "prompt": actual_prompt,
            "output_contract": live._output_contract(),
            "expected_case_id": None,
        },
        {
            "case_id": "strict_condition_prompt",
            "prompt": strict_prompt,
            "output_contract": live._output_contract(),
            "expected_case_id": None,
        },
    ]


def run_diagnostic(
    *,
    output_root: Path,
    receipt_out: Path,
    split: str,
    episodes_per_family: int,
    condition: str,
    model: str | None,
    timeout_s: float,
) -> dict[str, Any]:
    started = time.monotonic()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    receipts_root = output_root / "receipts"
    artifacts_root = output_root / "artifacts"
    case_index_path = artifacts_root / "prompt_timeout_diagnostic_case_index.json"
    live = _load_module(LIVE_CONDITION_SCRIPT, "pctom_live_tau_condition_comparison")
    strict = _load_module(STRICT_SCRIPT, "pctom_strict_prompt_replication")
    build = _load_module(BUILD_CORPUS_SCRIPT, "pctom_build_corpus")
    adapter = _load_module(TAU_ADAPTER, "persona_dream_tau_text_adapter")
    errors: list[str] = []
    rows: list[dict[str, Any]] = []

    for case in _case_defs(live, strict, build, split=split, episodes_per_family=episodes_per_family, condition=condition):
        case_id = case["case_id"]
        prompt = case["prompt"]
        output_contract = case["output_contract"]
        role = f"pctom-prompt-timeout-diagnostic-{case_id}"
        case_receipt_path = receipts_root / f"{case_id}.json"
        case_started = time.monotonic()
        parsed: dict[str, Any] | None = None
        tau_receipt: dict[str, Any] | None = None
        case_errors: list[str] = []
        try:
            parsed, tau_receipt = adapter.dispatch_text_reasoning(
                prompt,
                role,
                output_contract=output_contract,
                caller_skill="persona-dream",
                model=model,
                timeout_s=timeout_s,
            )
            tau_receipt["diagnostic_case_id"] = case_id
            tau_receipt["diagnostic_elapsed_s"] = round(time.monotonic() - case_started, 3)
            tau_receipt["prompt_char_count"] = len(prompt)
            tau_receipt["prompt_byte_count"] = len(prompt.encode("utf-8"))
            _write_json(case_receipt_path, tau_receipt)
            if tau_receipt.get("status") != "PASS":
                case_errors.append(f"tau_status:{tau_receipt.get('status')}")
                if tau_receipt.get("error"):
                    case_errors.append(f"tau_error:{tau_receipt.get('error')}")
            expected_case_id = case.get("expected_case_id")
            if expected_case_id is not None and (
                not isinstance(parsed, dict)
                or parsed.get("diagnostic_ready") is not True
                or parsed.get("case_id") != expected_case_id
            ):
                case_errors.append(f"diagnostic_echo_mismatch:{expected_case_id}")
        except Exception as exc:
            error = str(exc)
            case_errors.append(f"tau_dispatch_error:{error}")
            tau_receipt = _boundary_receipt(
                case_id=case_id,
                role=role,
                model=model,
                prompt=prompt,
                output_contract=output_contract,
                timeout_s=timeout_s,
                elapsed_s=time.monotonic() - case_started,
                error=error,
            )
            _write_json(case_receipt_path, tau_receipt)

        rows.append(
            {
                "case_id": case_id,
                "receipt_path": str(case_receipt_path),
                "receipt_sha256": _file_sha256(case_receipt_path),
                "prompt_sha256": _text_sha256(prompt),
                "prompt_char_count": len(prompt),
                "prompt_byte_count": len(prompt.encode("utf-8")),
                "output_contract_sha256": _stable_json_sha256(output_contract),
                "status": tau_receipt.get("status") if isinstance(tau_receipt, dict) else None,
                "live_call_performed": tau_receipt.get("live_call_performed") if isinstance(tau_receipt, dict) else False,
                "http_status": tau_receipt.get("http_status") if isinstance(tau_receipt, dict) else None,
                "elapsed_s": tau_receipt.get("diagnostic_elapsed_s", tau_receipt.get("elapsed_s")) if isinstance(tau_receipt, dict) else None,
                "systemic_failure_signature": tau_receipt.get("systemic_failure_signature") if isinstance(tau_receipt, dict) else None,
                "errors": case_errors,
            }
        )
        errors.extend(f"{case_id}:{error}" for error in case_errors)

    _write_json(case_index_path, rows)
    pass_case_ids = [row["case_id"] for row in rows if row.get("status") == "PASS"]
    blocked_case_ids = [row["case_id"] for row in rows if row.get("status") != "PASS"]
    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.live_tau_prompt_timeout_diagnostic_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "split": split,
        "episodes_per_family": episodes_per_family,
        "condition": condition,
        "timeout_s": timeout_s,
        "model": model,
        "case_index_path": str(case_index_path),
        "case_index_sha256": _file_sha256(case_index_path),
        "mocked": False,
        "live": any(row.get("live_call_performed") is True for row in rows),
        "fixture_backed": False,
        "deterministic_simulator_corpus_fixture_backed": True,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "counts": {
            "cases": len(rows),
            "pass_cases": len(pass_case_ids),
            "blocked_cases": len(blocked_case_ids),
            "prompt_byte_counts": {row["case_id"]: row["prompt_byte_count"] for row in rows},
        },
        "pass_case_ids": pass_case_ids,
        "blocked_case_ids": blocked_case_ids,
        "case_rows": rows,
        "errors": errors,
        "claims": {
            "proves": [
                "Tau/scillm text-reasoning diagnostic prompts were exercised through the sanctioned Persona Dream Tau adapter",
                "each diagnostic case has a hash-bound local receipt with prompt size and timeout metadata",
                "no Memory write, provider call, canonical memory write, identity write, or source-memory write was attempted",
            ]
            if status == PASS_STATUS
            else [
                "the prompt-timeout diagnostic produced inspectable fail-closed receipts for every attempted case",
            ],
            "does_not_prove": [
                "strict-inference prompt quality",
                "M/R/D/CD planning benefit",
                "live Memory recall in the sealed-test loop",
                "complete live Phase 01-16 runtime execution",
                "paid provider execution",
            ],
        },
    }
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--split", default="sealed_test")
    parser.add_argument("--episodes-per-family", type=int, default=24)
    parser.add_argument("--condition", default="M")
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout-s", type=float, default=30.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt_out = args.receipt_out or (args.output_root / "live_tau_prompt_timeout_diagnostic_receipt.v1.json")
    receipt = run_diagnostic(
        output_root=args.output_root,
        receipt_out=receipt_out,
        split=args.split,
        episodes_per_family=args.episodes_per_family,
        condition=args.condition,
        model=args.model,
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
