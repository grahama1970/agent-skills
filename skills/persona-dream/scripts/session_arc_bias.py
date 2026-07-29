#!/usr/bin/env python3
"""Publish a Persona Dream session arc-bias artifact for downstream consumers.

Persona Dream owns the lineage and slow arc state. It does not own the
conversation service's per-turn tone classifier. This runner therefore emits
bounded numeric deltas only:

continuity ledger latest accepted arc delta -> session_arc_bias.v1

No tone category is emitted. Consumers compose these deltas with their own
per-turn intent classification.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent.parent
DEFAULT_OUT_DIR = ROOT / "reports/goal_v5/continuity/session_arc_bias"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


continuity_ledger = _load("continuity_ledger")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha_obj(obj: Any) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode()
    ).hexdigest()


def sha_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path)


def clamp(value: float, lo: float, hi: float) -> float:
    return round(max(lo, min(hi, value)), 3)


def load_required_ledger(persona_id: str, path: Path | None = None) -> dict:
    ledger_path = path or continuity_ledger.ledger_path(persona_id)
    if not ledger_path.is_file():
        raise ValueError(f"BLOCKED_SESSION_ARC_BIAS_LEDGER_MISSING:{ledger_path}")
    return continuity_ledger.validate_ledger(
        json.loads(ledger_path.read_text(encoding="utf-8")),
        persona_id,
    )


def latest_arc_delta(ledger: dict) -> dict:
    deltas = ((ledger.get("arc_state") or {}).get("recent_arc_deltas") or [])
    if not deltas:
        raise ValueError("BLOCKED_SESSION_ARC_BIAS_NO_ARC_DELTA")
    delta = deltas[-1]
    if not delta.get("arc_delta_id") or not delta.get("idempotency_key"):
        raise ValueError("BLOCKED_SESSION_ARC_BIAS_ARC_DELTA_UNBOUND")
    return delta


def latest_source_id(ledger: dict, key: str) -> str:
    values = (ledger.get("provenance") or {}).get(key) or []
    if not values:
        raise ValueError(f"BLOCKED_SESSION_ARC_BIAS_SOURCE_MISSING:{key}")
    return values[-1]


def derive_deltas(delta: dict) -> dict:
    text = " ".join(str(delta.get(key) or "") for key in (
        "now",
        "still_true",
        "open_tension",
        "possible_expression",
    )).lower()
    boundary_terms = ("boundary", "privacy", "protect", "resist", "distance", "withholding")
    wanting_terms = ("yearning", "want", "witness", "understood", "contact", "known", "plea")
    pressure_terms = ("fear", "surrender", "intrusion", "capture", "pay for")
    warmth_terms = ("soft", "ache", "contact", "trust")

    boundary = sum(1 for term in boundary_terms if term in text)
    wanting = sum(1 for term in wanting_terms if term in text)
    pressure = sum(1 for term in pressure_terms if term in text)
    warmth = sum(1 for term in warmth_terms if term in text)

    intensity_delta = clamp(0.02 + 0.025 * boundary + 0.025 * wanting + 0.015 * pressure, 0.0, 0.18)
    valence_delta = clamp(0.025 * warmth - 0.035 * boundary - 0.04 * pressure, -0.18, 0.12)
    return {
        "intensity_delta": intensity_delta,
        "valence_delta": valence_delta,
        "bounds": {
            "intensity_delta": [0.0, 0.18],
            "valence_delta": [-0.18, 0.12],
        },
        "feature_counts": {
            "boundary": boundary,
            "wanting": wanting,
            "pressure": pressure,
            "warmth": warmth,
        },
        "derivation": "deterministic lexical arc-bias v1; deltas only, no tone category",
    }


def build_arc_bias(
    persona_id: str,
    *,
    ledger_path: Path | None = None,
    expected_epoch: int | None = None,
    expected_ledger_sha256: str | None = None,
) -> dict:
    ledger = load_required_ledger(persona_id, ledger_path)
    ledger_sha = sha_obj(ledger)
    if expected_epoch is not None and ledger["epoch"] != expected_epoch:
        raise ValueError(f"BLOCKED_SESSION_ARC_BIAS_STALE_LEDGER_EPOCH:{ledger['epoch']}!={expected_epoch}")
    if expected_ledger_sha256 is not None and ledger_sha != expected_ledger_sha256:
        raise ValueError(
            "BLOCKED_SESSION_ARC_BIAS_STALE_LEDGER_HASH:"
            f"{ledger_sha}!={expected_ledger_sha256}"
        )
    delta = latest_arc_delta(ledger)
    source_dream_cycle_id = latest_source_id(ledger, "source_dream_ids")
    source_journal_id = latest_source_id(ledger, "source_journal_ids")
    if not str(source_dream_cycle_id).startswith("live_chain_"):
        raise ValueError(f"BLOCKED_SESSION_ARC_BIAS_SOURCE_NOT_LIVE_CHAIN:{source_dream_cycle_id}")
    bias = {
        "schema": "persona_dream.session_arc_bias.v1",
        "created_at": utc_now(),
        "persona_id": persona_id,
        "status": "PASS_SESSION_ARC_BIAS_PUBLISHED",
        "mocked": False,
        "live": False,
        "source": {
            "ledger_path": rel(ledger_path or continuity_ledger.ledger_path(persona_id)),
            "ledger_epoch": ledger["epoch"],
            "ledger_sha256": ledger_sha,
            "identity_core_sha256": ledger["identity_core_sha256"],
            "source_dream_cycle_id": source_dream_cycle_id,
            "source_journal_id": source_journal_id,
            "arc_delta_id": delta["arc_delta_id"],
            "arc_delta_idempotency_key": delta["idempotency_key"],
        },
        "bias": derive_deltas(delta),
        "consumer_contract": {
            "tone_category_owner": "per_turn_intent_classifier",
            "emits_tone": False,
            "allowed_to_modify": ["intensity", "valence"],
            "must_not_modify": ["canonical_answer_text", "identity_core", "tone_category"],
            "neutral_fallback_rule": "if this artifact is missing or blocked, consumer must record neutral fallback as unproven arc influence",
        },
        "claims": {
            "proves": [
                "Persona Dream publishes bounded numeric arc deltas with ledger provenance",
                "the artifact emits no tone category and cannot replace per-turn intent classification",
            ],
            "does_not_prove": [
                "production SPARTA consumption",
                "live Chatterbox rendering",
                "perceived emotion",
                "repeated pipeline reliability",
            ],
        },
    }
    bias["artifact_sha256"] = sha_obj({k: v for k, v in bias.items() if k != "artifact_sha256"})
    return bias


def artifact(path: Path) -> dict[str, Any]:
    return {
        "path": rel(path),
        "exists": path.is_file(),
        "bytes": path.stat().st_size if path.is_file() else 0,
        "sha256": sha_file(path) if path.is_file() else None,
    }


def negative_controls(persona_id: str, ledger: dict) -> list[dict]:
    rows: list[dict] = []

    def expect(name: str, fn, token: str) -> None:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - receipt must show exact fail-closed reason
            msg = str(exc)
            rows.append({
                "name": name,
                "status": "PASS_NEGATIVE_BLOCKED" if token in msg else "FAIL_WRONG_BLOCK",
                "blocked_reason": msg,
                "expected_token": token,
            })
            return
        rows.append({"name": name, "status": "FAIL_NEGATIVE_ALLOWED", "expected_token": token})

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / "ledger.json"
        missing_path = Path(tmp) / "missing.json"
        tmp_path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
        expect(
            "missing_ledger_blocks",
            lambda: build_arc_bias(persona_id, ledger_path=missing_path),
            "BLOCKED_SESSION_ARC_BIAS_LEDGER_MISSING",
        )
        expect(
            "stale_epoch_blocks",
            lambda: build_arc_bias(persona_id, ledger_path=tmp_path, expected_epoch=ledger["epoch"] - 1),
            "BLOCKED_SESSION_ARC_BIAS_STALE_LEDGER_EPOCH",
        )
        expect(
            "stale_hash_blocks",
            lambda: build_arc_bias(persona_id, ledger_path=tmp_path, expected_ledger_sha256="sha256:" + "0" * 64),
            "BLOCKED_SESSION_ARC_BIAS_STALE_LEDGER_HASH",
        )
        mutated = deepcopy(ledger)
        mutated["identity_core"]["central_desire"] = "mutated outside continuity rules"
        mutated_path = Path(tmp) / "mutated.json"
        mutated_path.write_text(json.dumps(mutated, indent=2) + "\n", encoding="utf-8")
        expect(
            "mutated_identity_core_blocks",
            lambda: build_arc_bias(persona_id, ledger_path=mutated_path),
            "BLOCKED_CORE_MUTATED",
        )
        no_delta = deepcopy(ledger)
        no_delta["arc_state"]["recent_arc_deltas"] = []
        no_delta_path = Path(tmp) / "no_delta.json"
        no_delta_path.write_text(json.dumps(no_delta, indent=2) + "\n", encoding="utf-8")
        expect(
            "missing_arc_delta_blocks",
            lambda: build_arc_bias(persona_id, ledger_path=no_delta_path),
            "BLOCKED_SESSION_ARC_BIAS_NO_ARC_DELTA",
        )
        unbound = deepcopy(ledger)
        unbound["arc_state"]["recent_arc_deltas"][-1].pop("idempotency_key", None)
        unbound_path = Path(tmp) / "unbound.json"
        unbound_path.write_text(json.dumps(unbound, indent=2) + "\n", encoding="utf-8")
        expect(
            "unbound_arc_delta_blocks",
            lambda: build_arc_bias(persona_id, ledger_path=unbound_path),
            "BLOCKED_SESSION_ARC_BIAS_ARC_DELTA_UNBOUND",
        )
        old_source = deepcopy(ledger)
        old_source["provenance"]["source_dream_ids"][-1] = "cycle_20260723T234851Z"
        old_source_path = Path(tmp) / "old_source.json"
        old_source_path.write_text(json.dumps(old_source, indent=2) + "\n", encoding="utf-8")
        expect(
            "non_live_chain_source_blocks",
            lambda: build_arc_bias(persona_id, ledger_path=old_source_path),
            "BLOCKED_SESSION_ARC_BIAS_SOURCE_NOT_LIVE_CHAIN",
        )
    return rows


def write_receipt(persona_id: str, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    ledger = load_required_ledger(persona_id)
    ledger_sha = sha_obj(ledger)
    bias = build_arc_bias(
        persona_id,
        expected_epoch=ledger["epoch"],
        expected_ledger_sha256=ledger_sha,
    )
    artifact_path = out_dir / "session_arc_bias.v1.json"
    artifact_path.write_text(json.dumps(bias, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    reread = json.loads(artifact_path.read_text(encoding="utf-8"))
    negatives = negative_controls(persona_id, ledger)
    receipt = {
        "schema": "persona_dream.session_arc_bias_receipt.v1",
        "created_at": utc_now(),
        "status": "PASS_SESSION_ARC_BIAS_RECEIPT" if all(
            row["status"] == "PASS_NEGATIVE_BLOCKED" for row in negatives
        ) else "BLOCKED_SESSION_ARC_BIAS_RECEIPT",
        "mocked": False,
        "live": False,
        "artifact": artifact(artifact_path),
        "artifact_readback": {
            "status": reread.get("status"),
            "artifact_sha256": reread.get("artifact_sha256"),
            "ledger_epoch": (reread.get("source") or {}).get("ledger_epoch"),
            "source_dream_cycle_id": (reread.get("source") or {}).get("source_dream_cycle_id"),
            "readback_ok": reread == bias,
        },
        "negative_controls": negatives,
        "claims": bias["claims"],
    }
    receipt_path = out_dir / "RECEIPT.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / "SHA256SUMS.txt").write_text(
        f"{sha_file(artifact_path).removeprefix('sha256:')}  {artifact_path.name}\n"
        f"{sha_file(receipt_path).removeprefix('sha256:')}  {receipt_path.name}\n",
        encoding="utf-8",
    )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--persona", default="embry")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt = write_receipt(args.persona, args.out_dir)
    summary = {
        "status": receipt["status"],
        "artifact": receipt["artifact"]["path"],
        "negative_controls": {
            "passed": sum(1 for row in receipt["negative_controls"] if row["status"] == "PASS_NEGATIVE_BLOCKED"),
            "total": len(receipt["negative_controls"]),
        },
    }
    print(json.dumps(summary if args.json else summary, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "PASS_SESSION_ARC_BIAS_RECEIPT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
