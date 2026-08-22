#!/usr/bin/env python3
"""Run a five-cycle Persona Dream live-chain reliability pilot.

The unit under test is the joined live-chain receipt runner:

accepted synthetic dream -> Watch binding -> journal -> ledger append
-> pre-turn session mood -> live Chatterbox -> speaker-recognition receipt.

This script does not generate new provider/video media. It repeats the accepted
live-chain contract with unique cycle ids, preserves every terminal cycle
receipt, and writes an aggregate that binds each receipt by SHA-256.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
import time
import traceback
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent.parent
DEFAULT_OUT_DIR = ROOT / "reports/goal_v5/continuity/reliability"
DEFAULT_PREFLIGHT_RECEIPT = DEFAULT_OUT_DIR / "soak35/PREFLIGHT_RECEIPT.json"
DEFAULT_CYCLES = 5
SYSTEMIC_FAILURE_LIMIT = 3


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


live_chain_receipt = _load("live_chain_receipt")
validate_soak35_preflight = _load("validate_soak35_preflight")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def compact_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ").lower()


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path)


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def sha_obj(obj: Any) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def get_json(url: str, timeout: float = 10.0) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read())


def service_availability() -> dict[str, Any]:
    rows: dict[str, Any] = {}
    endpoints = {
        "memory": f"{live_chain_receipt.GMO}/health",
        "chatterbox": f"{live_chain_receipt.session_mood_chatterbox_live.CHATTERBOX}/health",
    }
    for name, url in endpoints.items():
        started = time.time()
        try:
            body = get_json(url)
            rows[name] = {
                "available": True,
                "elapsed_seconds": round(time.time() - started, 3),
                "body": body,
            }
        except Exception as exc:  # noqa: BLE001 - availability is evidence
            rows[name] = {
                "available": False,
                "elapsed_seconds": round(time.time() - started, 3),
                "error": f"{type(exc).__name__}: {exc}",
            }
    return rows


def accepted_source_input_manifest(source_cycle: Path, cycle_id: str) -> dict[str, Any]:
    source = live_chain_receipt.accepted_source_bundle(source_cycle)
    manifest = {
        "schema": "persona_dream.live_chain_reliability.input_manifest.v1",
        "cycle_id": cycle_id,
        "source_cycle_dir": source["source_cycle_dir"],
        "source_cycle_id": source["source_cycle_id"],
        "source_dream_node_key": source["source_dream_node_key"],
        "source_artifact_sha256": {
            name: row["sha256"] for name, row in sorted(source["artifacts"].items())
        },
        "source_roots": source["roots"],
        "watch_observation_ids": source["watch_observation_ids"],
        "tom_candidate_ids": source["tom_candidate_ids"],
    }
    manifest["manifest_sha256"] = sha_obj(manifest)
    return manifest


def classify_exception(exc: BaseException) -> tuple[str, str]:
    message = str(exc)
    for token in (
        "BLOCKED_MEMORY_EXACT_REREAD_MISMATCH",
        "BLOCKED_DUPLICATE_ACCEPTED_CANONICAL_WRITE",
        "BLOCKED_ACCEPTED_SOURCE_MISSING",
        "BLOCKED_SOURCE_DREAM_NOT_ACCEPTED",
        "BLOCKED_SOURCE_TOM_NOT_ACCEPTED",
        "BLOCKED_SOURCE_PERSISTENCE_REREAD_MISMATCH",
        "BLOCKED_JOURNAL",
        "BLOCKED_LEDGER",
        "BLOCKED_RECOGNITION",
        "BLOCKED_RENDER_ARTIFACT_HASHES",
        "BLOCKED_CHATTERBOX",
        "URLError",
        "TimeoutError",
        "ConnectionRefusedError",
    ):
        if token in message:
            return token, message
    return f"{type(exc).__name__}", message


def memory_count(collection: str, key: str) -> int | None:
    try:
        return len(live_chain_receipt.memory_list(collection, key))
    except Exception:  # noqa: BLE001 - post-failure count is diagnostic only
        return None


def accepted_effect_counts(cycle_id: str) -> dict[str, Any]:
    checks = {
        "accepted_dream_memory": ("persona_memory", f"dream_{cycle_id}"),
        "watch_evidence": ("persona_dream_watch_evidence", f"watch_{cycle_id}"),
        "journal_memory": ("persona_journal", f"journal_{cycle_id}"),
    }
    counts = {
        name: memory_count(collection, key)
        for name, (collection, key) in checks.items()
    }
    total_known = sum(count for count in counts.values() if isinstance(count, int))
    duplicate_count = sum(max(0, count - 1) for count in counts.values() if isinstance(count, int))
    return {
        "exact_key_counts": counts,
        "known_accepted_effect_count": total_known,
        "duplicate_accepted_effect_count": duplicate_count,
    }


def stage_counts(receipt: dict[str, Any]) -> dict[str, int]:
    counts = {"PASS": 0, "FAIL": 0, "BLOCKED": 0, "ERROR": 0, "OTHER": 0}
    for stage in receipt.get("stages") or []:
        status = str(stage.get("status") or "")
        if status == "PASS" or status.startswith("PASS_"):
            counts["PASS"] += 1
        elif status.startswith("BLOCKED"):
            counts["BLOCKED"] += 1
        elif status.startswith("ERROR"):
            counts["ERROR"] += 1
        elif status.startswith("FAIL"):
            counts["FAIL"] += 1
        else:
            counts["OTHER"] += 1
    return counts


def first_divergent_gate(receipt: dict[str, Any]) -> dict[str, Any] | None:
    for stage in receipt.get("stages") or []:
        status = str(stage.get("status") or "")
        if not (status == "PASS" or status.startswith("PASS_")):
            return {"stage": stage.get("name"), "status": status}
    if receipt.get("status") != "PASS_PERSONA_DREAM_LIVE_CHAIN":
        return {"stage": "cycle_status", "status": receipt.get("status")}
    return None


def terminal_cycle_receipt(
    *,
    cycle_index: int,
    cycle_id: str,
    cycle_dir: Path,
    status: str,
    started_at: str,
    ended_at: str,
    elapsed_seconds: float,
    input_manifest: dict[str, Any],
    services_before: dict[str, Any],
    services_after: dict[str, Any] | None = None,
    blocked_reason: str | None = None,
    failure_signature: str | None = None,
    traceback_text: str | None = None,
) -> dict[str, Any]:
    receipt = {
        "schema": "persona_dream.live_chain_reliability_cycle.v1",
        "created_at": utc_now(),
        "status": status,
        "mocked": False,
        "live": True,
        "cycle_index": cycle_index,
        "dream_cycle_id": cycle_id,
        "started_at": started_at,
        "ended_at": ended_at,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "input_manifest": input_manifest,
        "services_before": services_before,
        "services_after": services_after,
        "first_divergent_gate": {
            "stage": failure_signature or status,
            "status": status,
            "artifact": rel(cycle_dir / "RECEIPT.json"),
        },
        "blocked_reason": blocked_reason,
        "traceback_tail": traceback_text[-4000:] if traceback_text else None,
        "side_effect_counters": accepted_effect_counts(cycle_id),
        "claims": {
            "proves": [],
            "does_not_prove": [
                "a successful live-chain cycle",
                "repeated dream-pipeline reliability",
            ],
        },
    }
    write_json(cycle_dir / "RECEIPT.json", receipt)
    return receipt


def run_one_cycle(
    *,
    index: int,
    cycle_id: str,
    cycle_dir: Path,
    source_cycle: Path,
    recognition_python: Path,
) -> dict[str, Any]:
    started = time.time()
    started_at = utc_now()
    services_before = service_availability()
    input_manifest = accepted_source_input_manifest(source_cycle, cycle_id)
    write_json(cycle_dir / "INPUT_MANIFEST.json", input_manifest)
    try:
        args = SimpleNamespace(
            source_cycle=source_cycle,
            out_dir=cycle_dir,
            dream_cycle_id=cycle_id,
            recognition_python=recognition_python,
        )
        receipt = live_chain_receipt.run_chain(args)
        ended_at = utc_now()
        services_after = service_availability()
        elapsed = time.time() - started
        receipt_path = cycle_dir / "RECEIPT.json"
        reread = load_json(receipt_path)
        if reread.get("dream_cycle_id") != cycle_id:
            raise ValueError("BLOCKED_RELIABILITY_CYCLE_REREAD_ID_MISMATCH")
        receipt["reliability_cycle"] = {
            "cycle_index": index,
            "started_at": started_at,
            "ended_at": ended_at,
            "elapsed_seconds": round(elapsed, 3),
            "input_manifest": input_manifest,
            "input_manifest_path": rel(cycle_dir / "INPUT_MANIFEST.json"),
            "input_manifest_sha256": sha_file(cycle_dir / "INPUT_MANIFEST.json"),
            "services_before": services_before,
            "services_after": services_after,
            "first_divergent_gate": first_divergent_gate(receipt),
            "stage_counts": stage_counts(receipt),
            "accepted_effect_counts": accepted_effect_counts(cycle_id),
        }
        write_json(receipt_path, receipt)
        return receipt
    except Exception as exc:  # noqa: BLE001 - terminal cycle receipts are required
        ended_at = utc_now()
        signature, reason = classify_exception(exc)
        return terminal_cycle_receipt(
            cycle_index=index,
            cycle_id=cycle_id,
            cycle_dir=cycle_dir,
            status="BLOCKED_LIVE_CHAIN_CYCLE" if reason.startswith("BLOCKED") else "ERROR_LIVE_CHAIN_CYCLE",
            started_at=started_at,
            ended_at=ended_at,
            elapsed_seconds=time.time() - started,
            input_manifest=input_manifest,
            services_before=services_before,
            services_after=service_availability(),
            blocked_reason=reason,
            failure_signature=signature,
            traceback_text=traceback.format_exc(),
        )


def wilson_interval(successes: int, n: int, z: float = 1.96) -> dict[str, float | int]:
    if n <= 0:
        return {"n": n, "successes": successes, "lower": 0.0, "upper": 0.0}
    phat = successes / n
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    half = z * math.sqrt((phat * (1 - phat) + z * z / (4 * n)) / n) / denom
    return {
        "n": n,
        "successes": successes,
        "proportion": round(phat, 6),
        "lower": round(max(0.0, center - half), 6),
        "upper": round(min(1.0, center + half), 6),
        "method": "Wilson score interval, 95%, N=5 pilot if cycles=5",
    }


def aggregate(
    cycle_receipts: list[dict[str, Any]],
    out_dir: Path,
    *,
    campaign_id: str,
    preflight_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cycle_rows: list[dict[str, Any]] = []
    gate_counts: dict[str, dict[str, int]] = {}
    seen_ids: set[str] = set()
    duplicate_ids: list[str] = []
    duplicate_effect_count = 0
    all_classified = True

    for receipt in cycle_receipts:
        cycle_path = out_dir / f"cycle_{receipt['cycle_index']:03d}" / "RECEIPT.json"
        cycle_sha = sha_file(cycle_path)
        if receipt.get("dream_cycle_id") in seen_ids:
            duplicate_ids.append(receipt.get("dream_cycle_id"))
        seen_ids.add(receipt.get("dream_cycle_id"))
        per_stage = stage_counts(receipt)
        for key, value in per_stage.items():
            gate_counts.setdefault("all_stages", {}).setdefault(key, 0)
            gate_counts["all_stages"][key] += value
        effects = (
            receipt.get("reliability_cycle", {}).get("accepted_effect_counts")
            or receipt.get("side_effect_counters")
            or {}
        )
        duplicate_effect_count += int(effects.get("duplicate_accepted_effect_count") or 0)
        divergent = (
            receipt.get("reliability_cycle", {}).get("first_divergent_gate")
            or receipt.get("first_divergent_gate")
            or first_divergent_gate(receipt)
        )
        if receipt.get("status") != "PASS_PERSONA_DREAM_LIVE_CHAIN" and not divergent:
            all_classified = False
        cycle_rows.append(
            {
                "cycle_index": receipt["cycle_index"],
                "dream_cycle_id": receipt.get("dream_cycle_id"),
                "status": receipt.get("status"),
                "receipt": rel(cycle_path),
                "receipt_sha256": cycle_sha,
                "input_manifest_sha256": (
                    receipt.get("reliability_cycle", {}).get("input_manifest_sha256")
                    or sha_obj(receipt.get("input_manifest") or {})
                ),
                "first_divergent_gate": divergent,
                "retry_count": 0,
                "retry_reasons": [],
                "side_effect_counters": effects,
                "stage_counts": per_stage,
                "elapsed_seconds": receipt.get("reliability_cycle", {}).get("elapsed_seconds")
                or receipt.get("elapsed_seconds"),
                "service_availability": {
                    "before": receipt.get("reliability_cycle", {}).get("services_before")
                    or receipt.get("services_before"),
                    "after": receipt.get("reliability_cycle", {}).get("services_after")
                    or receipt.get("services_after"),
                },
                "recognition": recognition_summary(receipt),
                "content_invariance": content_summary(receipt),
            }
        )

    passed = sum(1 for row in cycle_rows if row["status"] == "PASS_PERSONA_DREAM_LIVE_CHAIN")
    blocked = sum(1 for row in cycle_rows if str(row["status"]).startswith("BLOCKED"))
    errored = sum(1 for row in cycle_rows if str(row["status"]).startswith("ERROR"))
    completed = passed + blocked + errored
    aggregate_doc = {
        "schema": "persona_dream.live_chain_reliability_aggregate.v1",
        "created_at": utc_now(),
        "campaign_id": campaign_id,
        "status": "PASS_LIVE_CHAIN_RELIABILITY_PILOT" if passed == len(cycle_rows) else "BLOCKED_LIVE_CHAIN_RELIABILITY_PILOT",
        "mocked": False,
        "live": True,
        "counts": {
            "attempted": len(cycle_rows),
            "completed": completed,
            "passed": passed,
            "blocked": blocked,
            "errored": errored,
            "blocked_by_systemic_failure": sum(
                1 for row in cycle_rows if row["status"] == "BLOCKED_BY_SYSTEMIC_FAILURE"
            ),
            "not_run": 0,
        },
        "unique_dream_cycle_ids": sorted(seen_ids),
        "duplicate_dream_cycle_ids": duplicate_ids,
        "input_manifest_hashes": [row["input_manifest_sha256"] for row in cycle_rows],
        "per_gate_counts": gate_counts,
        "cycles": cycle_rows,
        "duplicate_accepted_effect_count": duplicate_effect_count,
        "success_interval": wilson_interval(passed, len(cycle_rows)),
        "every_failure_deterministically_classified": all_classified,
        "receipt_hash_readback": {
            "all_cycle_receipts_recomputed": True,
            "cycle_receipt_count": len(cycle_rows),
        },
        "source_transition_preflight": preflight_receipt,
        "claims": {
            "proves": [
                "N=5 pilot outcomes are preserved without hiding failed cycles",
                "every cycle receipt is bound by recomputed SHA-256",
                "raw pilot success proportion and Wilson interval are reported",
            ],
            "does_not_prove": [
                "production reliability",
                "perceived emotion or naturalness",
                "PCTOM-R planning benefit",
                "paid provider/video repeatability",
            ],
        },
    }
    write_json(out_dir / "AGGREGATE_RECEIPT.json", aggregate_doc)
    return validate_aggregate(out_dir / "AGGREGATE_RECEIPT.json")


def recognition_summary(receipt: dict[str, Any]) -> dict[str, Any] | None:
    for stage in receipt.get("stages") or []:
        if stage.get("name") == "embry_voice_recognition":
            rec = stage.get("receipt") or {}
            return {"status": rec.get("status"), "sha256": rec.get("sha256"), "path": rec.get("path")}
    return None


def content_summary(receipt: dict[str, Any]) -> dict[str, Any] | None:
    for stage in receipt.get("stages") or []:
        if stage.get("name") == "session_mood_live_chatterbox":
            turns = stage.get("turns") or []
            return {
                "turn_count": len(turns),
                "asr_ok_count": sum(1 for turn in turns if (turn.get("asr_gate") or {}).get("ok") is True),
                "engines": sorted({turn.get("engine") for turn in turns}),
            }
    return None


def validate_aggregate(path: Path) -> dict[str, Any]:
    doc = load_json(path)
    failures: list[str] = []
    cycles = doc.get("cycles") or []
    if len(cycles) != doc.get("counts", {}).get("attempted"):
        failures.append("cycle_count_mismatch")
    for row in cycles:
        cycle_path = REPO_ROOT / row["receipt"]
        if not cycle_path.is_file():
            failures.append(f"cycle_receipt_missing:{row['receipt']}")
            continue
        if sha_file(cycle_path) != row.get("receipt_sha256"):
            failures.append(f"cycle_receipt_hash_mismatch:{row['receipt']}")
    if doc.get("duplicate_dream_cycle_ids"):
        failures.append("duplicate_dream_cycle_ids")
    if doc.get("duplicate_accepted_effect_count") != 0:
        failures.append("duplicate_accepted_effect_count")
    if doc.get("every_failure_deterministically_classified") is not True:
        failures.append("unclassified_failure")
    preflight = doc.get("source_transition_preflight")
    if preflight:
        receipt_path = REPO_ROOT / preflight.get("receipt", DEFAULT_PREFLIGHT_RECEIPT)
        try:
            validate_soak35_preflight.validate_preflight_receipt(receipt_path)
        except Exception as exc:  # noqa: BLE001 - fail closed with concrete reason
            failures.append(f"source_transition_preflight_invalid:{type(exc).__name__}:{exc}")
    if failures:
        doc["status"] = "BLOCKED_LIVE_CHAIN_RELIABILITY_PILOT"
        doc["validation_failures"] = failures
        write_json(path, doc)
    return doc


def run_campaign(args: argparse.Namespace) -> dict[str, Any]:
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    campaign_id = args.campaign_id or f"live_chain_reliability_{compact_ts()}"
    preflight_receipt = None
    if args.require_preflight or args.cycles >= 35:
        preflight_receipt = validate_soak35_preflight.validate_preflight_receipt(args.preflight_receipt)
        preflight_receipt = {
            "status": preflight_receipt["status"],
            "receipt": rel(args.preflight_receipt),
            "manifest": preflight_receipt["manifest"],
            "manifest_sha256": preflight_receipt["manifest_sha256"],
            "policy": preflight_receipt["policy"],
            "policy_sha256": preflight_receipt["policy_sha256"],
            "counts": preflight_receipt["counts"],
            "claims": preflight_receipt["claims"],
        }
    receipts: list[dict[str, Any]] = []
    failure_signatures: dict[str, int] = {}
    systemic_block_active: str | None = None

    for index in range(1, args.cycles + 1):
        cycle_id = f"live_chain_reliability_{campaign_id}_cycle_{index:03d}"
        cycle_dir = out_dir / f"cycle_{index:03d}"
        if systemic_block_active:
            input_manifest = accepted_source_input_manifest(args.source_cycle, cycle_id)
            receipt = terminal_cycle_receipt(
                cycle_index=index,
                cycle_id=cycle_id,
                cycle_dir=cycle_dir,
                status="BLOCKED_BY_SYSTEMIC_FAILURE",
                started_at=utc_now(),
                ended_at=utc_now(),
                elapsed_seconds=0.0,
                input_manifest=input_manifest,
                services_before=service_availability(),
                blocked_reason=f"systemic failure after {SYSTEMIC_FAILURE_LIMIT} matching cycles: {systemic_block_active}",
                failure_signature=systemic_block_active,
            )
            receipts.append(receipt)
            continue

        receipt = run_one_cycle(
            index=index,
            cycle_id=cycle_id,
            cycle_dir=cycle_dir,
            source_cycle=args.source_cycle,
            recognition_python=args.recognition_python,
        )
        receipt["cycle_index"] = index
        write_json(cycle_dir / "RECEIPT.json", receipt)
        receipts.append(receipt)

        divergent = (
            receipt.get("reliability_cycle", {}).get("first_divergent_gate")
            or receipt.get("first_divergent_gate")
        )
        if receipt.get("status") != "PASS_PERSONA_DREAM_LIVE_CHAIN" and divergent:
            signature = f"{divergent.get('stage')}:{divergent.get('status')}"
            failure_signatures[signature] = failure_signatures.get(signature, 0) + 1
            if failure_signatures[signature] >= SYSTEMIC_FAILURE_LIMIT:
                systemic_block_active = signature

    aggregate_doc = aggregate(receipts, out_dir, campaign_id=campaign_id, preflight_receipt=preflight_receipt)
    (out_dir / "SHA256SUMS.txt").write_text(
        "".join(
            f"{sha_file(out_dir / f'cycle_{row['cycle_index']:03d}' / 'RECEIPT.json').removeprefix('sha256:')}  cycle_{row['cycle_index']:03d}/RECEIPT.json\n"
            for row in aggregate_doc["cycles"]
        )
        + f"{sha_file(out_dir / 'AGGREGATE_RECEIPT.json').removeprefix('sha256:')}  AGGREGATE_RECEIPT.json\n",
        encoding="utf-8",
    )
    return validate_aggregate(out_dir / "AGGREGATE_RECEIPT.json")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--source-cycle", type=Path, default=live_chain_receipt.DEFAULT_SOURCE_CYCLE)
    parser.add_argument("--recognition-python", type=Path, default=live_chain_receipt.DEFAULT_RECOGNITION_PYTHON)
    parser.add_argument("--cycles", type=int, default=DEFAULT_CYCLES)
    parser.add_argument("--campaign-id")
    parser.add_argument("--preflight-receipt", type=Path, default=DEFAULT_PREFLIGHT_RECEIPT)
    parser.add_argument("--require-preflight", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.cycles <= 0:
        raise SystemExit("cycles must be positive")
    doc = run_campaign(args)
    summary = {
        "status": doc["status"],
        "campaign_id": doc["campaign_id"],
        "aggregate": rel(args.out_dir / "AGGREGATE_RECEIPT.json"),
        "counts": doc["counts"],
        "success_interval": doc["success_interval"],
    }
    print(json.dumps(summary if args.json else summary, indent=2, sort_keys=True))
    return 0 if doc["status"] == "PASS_LIVE_CHAIN_RELIABILITY_PILOT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
