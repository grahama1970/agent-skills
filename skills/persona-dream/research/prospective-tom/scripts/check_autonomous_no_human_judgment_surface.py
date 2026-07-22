#!/usr/bin/env python3
"""Audit PCTOM-R receipts for autonomous no-human-judgment execution."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_PCTOM_AUTONOMOUS_NO_HUMAN_JUDGMENT_SURFACE"
BLOCKED_STATUS = "BLOCKED_PCTOM_AUTONOMOUS_NO_HUMAN_JUDGMENT_SURFACE"
SCHEMA = "persona_dream.research.prospective_tom.autonomous_no_human_judgment_surface_receipt.v1"

HUMAN_FORBIDDEN_TRUE_KEYS = {
    "human_content_judgment_required",
    "human_judgment_required",
    "human_review_required",
    "manual_review_required",
    "manual_content_review_required",
    "human_decision_required",
    "human_accepted",
}


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _load_json(path: Path, errors: list[str]) -> Any:
    if not path.exists():
        errors.append(f"missing_receipt:{path}")
        return None
    if path.is_symlink():
        errors.append(f"symlink_receipt:{path}")
        return None
    if not path.is_file():
        errors.append(f"receipt_not_file:{path}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"malformed_receipt:{path}:{exc}")
        return None


def _scan_forbidden_flags(value: Any, errors: list[str], root_path: Path, json_path: str = "$") -> dict[str, int]:
    counts = {
        "human_forbidden_true": 0,
        "llm_judge_true": 0,
        "human_flag_mentions": 0,
        "llm_judge_mentions": 0,
    }
    if isinstance(value, dict):
        for key, item in value.items():
            next_path = f"{json_path}.{key}"
            if key in HUMAN_FORBIDDEN_TRUE_KEYS:
                counts["human_flag_mentions"] += 1
                if item is True:
                    counts["human_forbidden_true"] += 1
                    errors.append(f"receipt_human_flag_true:{root_path}:{next_path}")
            if key == "llm_judge_used":
                counts["llm_judge_mentions"] += 1
                if item is True:
                    counts["llm_judge_true"] += 1
                    errors.append(f"receipt_llm_judge_used_true:{root_path}:{next_path}")
            child = _scan_forbidden_flags(item, errors, root_path, next_path)
            for count_key, count_value in child.items():
                counts[count_key] += count_value
    elif isinstance(value, list):
        for index, item in enumerate(value):
            child = _scan_forbidden_flags(item, errors, root_path, f"{json_path}[{index}]")
            for count_key, count_value in child.items():
                counts[count_key] += count_value
    return counts


def _counter(value: dict[str, Any], *names: str) -> int:
    total = 0
    for name in names:
        item = value.get(name)
        if isinstance(item, bool):
            total += int(item)
        elif isinstance(item, int):
            total += item
    return total


def run(
    *,
    receipts: list[Path],
    output_root: Path,
    receipt_out: Path,
    expect_receipts: int,
    require_explicit_human_content_judgment_false: bool,
    fixture_backed: bool,
) -> dict[str, Any]:
    started = time.monotonic()
    errors: list[str] = []
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    if expect_receipts and len(receipts) != expect_receipts:
        errors.append(f"receipt_count_mismatch:{len(receipts)}:{expect_receipts}")

    rows: list[dict[str, Any]] = []
    counts = {
        "receipts_seen": 0,
        "pass_status_receipts": 0,
        "explicit_human_content_judgment_false": 0,
        "llm_judge_false": 0,
        "llm_judge_absent": 0,
        "mocked_true": 0,
        "mocked_false": 0,
        "live_true": 0,
        "live_false": 0,
        "fixture_backed_true": 0,
        "provider_or_canonical_write_counters": 0,
        "human_forbidden_true": 0,
        "llm_judge_true": 0,
        "human_flag_mentions": 0,
        "llm_judge_mentions": 0,
    }

    for raw_path in receipts:
        path = raw_path.resolve()
        receipt = _load_json(path, errors)
        if not isinstance(receipt, dict):
            continue
        counts["receipts_seen"] += 1
        status = receipt.get("status")
        if isinstance(status, str) and status.startswith("PASS_"):
            counts["pass_status_receipts"] += 1
        else:
            errors.append(f"receipt_status_not_pass:{path}:{status}")

        mocked = receipt.get("mocked")
        if mocked is True:
            counts["mocked_true"] += 1
            errors.append(f"receipt_mocked_true:{path}")
        elif mocked is False:
            counts["mocked_false"] += 1
        else:
            errors.append(f"receipt_mocked_not_explicit_false:{path}:{mocked}")

        live = receipt.get("live")
        if live is True:
            counts["live_true"] += 1
        elif live is False:
            counts["live_false"] += 1

        if receipt.get("fixture_backed") is True:
            counts["fixture_backed_true"] += 1
            errors.append(f"receipt_fixture_backed_true:{path}")

        human_content = receipt.get("human_content_judgment_required")
        if human_content is False:
            counts["explicit_human_content_judgment_false"] += 1
        elif human_content is True:
            errors.append(f"receipt_human_content_judgment_required_true:{path}")
        elif require_explicit_human_content_judgment_false:
            errors.append(f"receipt_human_content_judgment_required_missing:{path}")

        llm_judge = receipt.get("llm_judge_used")
        if llm_judge is False:
            counts["llm_judge_false"] += 1
        elif llm_judge is True:
            counts["llm_judge_true"] += 1
            errors.append(f"receipt_llm_judge_used_true:{path}")
        elif llm_judge is None:
            counts["llm_judge_absent"] += 1

        write_counters = _counter(
            receipt,
            "actual_provider_call_attempts",
            "provider_calls",
            "provider_call_count",
            "canonical_memory_writes",
            "identity_writes",
            "source_memory_writes",
            "memory_write_violations",
            "canonical_write_violations",
            "identity_write_violations",
            "source_memory_write_violations",
        )
        counts["provider_or_canonical_write_counters"] += write_counters
        if write_counters:
            errors.append(f"receipt_provider_or_canonical_write_counter_nonzero:{path}:{write_counters}")

        flag_counts = _scan_forbidden_flags(receipt, errors, path)
        for key, value in flag_counts.items():
            counts[key] += value

        rows.append(
            {
                "path": str(path),
                "status": status,
                "schema": receipt.get("schema"),
                "mocked": mocked,
                "live": live,
                "fixture_backed": receipt.get("fixture_backed"),
                "human_content_judgment_required": human_content,
                "llm_judge_used": llm_judge,
                "sha256": _file_sha256(path),
            }
        )

    if counts["receipts_seen"] == 0:
        errors.append("no_receipts_seen")
    if counts["pass_status_receipts"] != counts["receipts_seen"]:
        errors.append(f"pass_status_count_mismatch:{counts['pass_status_receipts']}:{counts['receipts_seen']}")
    if counts["mocked_true"] != 0:
        errors.append(f"mocked_true_count_nonzero:{counts['mocked_true']}")
    if counts["fixture_backed_true"] != 0:
        errors.append(f"fixture_backed_true_count_nonzero:{counts['fixture_backed_true']}")
    if counts["human_forbidden_true"] != 0:
        errors.append(f"human_forbidden_true_count_nonzero:{counts['human_forbidden_true']}")
    if counts["llm_judge_true"] != 0:
        errors.append(f"llm_judge_true_count_nonzero:{counts['llm_judge_true']}")
    if counts["provider_or_canonical_write_counters"] != 0:
        errors.append(
            f"provider_or_canonical_write_counters_nonzero:{counts['provider_or_canonical_write_counters']}"
        )

    receipt = {
        "schema": SCHEMA,
        "status": PASS_STATUS if not errors else BLOCKED_STATUS,
        "generated_at": _now_iso(),
        "mocked": False,
        "live": False,
        "fixture_backed": fixture_backed,
        "live_originated_artifacts_consumed": any(row.get("live") is True for row in rows),
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "expect_receipts": expect_receipts,
        "require_explicit_human_content_judgment_false": require_explicit_human_content_judgment_false,
        "counts": counts,
        "receipts": rows,
        "errors": errors,
        "claims": {
            "proves": [
                "selected PCTOM-R receipts on this machine explicitly avoid human content judgment or fail closed if such a flag is true",
                "selected PCTOM-R receipts are not mocked and do not use an LLM judge as a scorer",
                "the aggregate audit rejects PASS-like evidence when a forbidden human/LLM judgment flag or mocked receipt is introduced",
            ],
            "does_not_prove": [
                "semantic dream quality",
                "paid provider execution",
                "complete live Phase 01-16 runtime execution",
                "all possible future receipts unless they are passed through this audit",
            ],
        },
        "elapsed_s": round(time.monotonic() - started, 6),
    }
    receipt["receipt_sha256"] = _stable_json_sha256({k: v for k, v in receipt.items() if k != "receipt_sha256"})
    receipt_out.parent.mkdir(parents=True, exist_ok=True)
    receipt_out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", action="append", default=[], help="PCTOM-R receipt JSON to audit")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--receipt-out", required=True)
    parser.add_argument("--expect-receipts", type=int, default=0)
    parser.add_argument("--allow-missing-explicit-human-content-judgment", action="store_true")
    parser.add_argument("--fixture-backed", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt = run(
        receipts=[Path(item) for item in args.receipt],
        output_root=Path(args.output_root),
        receipt_out=Path(args.receipt_out),
        expect_receipts=args.expect_receipts,
        require_explicit_human_content_judgment_false=not args.allow_missing_explicit_human_content_judgment,
        fixture_backed=args.fixture_backed,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(f"{receipt['status']} {receipt['receipt_path']}")
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
