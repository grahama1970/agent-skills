#!/usr/bin/env python3
"""Generate receipt-derived pause_after_round spectator fixtures."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


BATTLE_DIR = Path(__file__).resolve().parents[1]
BASE_FIXTURE = BATTLE_DIR / "spectator/public/battle-fixtures/battle-004-same-run-qualification/battle.normalized_ux_fixture.json"
PUBLIC_ROOT = BATTLE_DIR / "spectator/public/battle-fixtures"


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _state_item(
    *,
    state: str,
    receipt: dict[str, Any] | None,
    receipt_path: str | None,
    label: str,
    backend_receipt: bool,
) -> dict[str, Any]:
    return {
        "state": state,
        "status": receipt.get("status") if receipt else "UNAVAILABLE",
        "label": label,
        "request_id": receipt.get("request_id") if receipt else None,
        "reason_code": receipt.get("reason_code") if receipt else "backend_receipt_missing",
        "receipt_path": receipt_path,
        "receipt_schema": receipt.get("schema") if receipt else None,
        "backend_receipt": backend_receipt,
        "live": bool(receipt.get("live")) if receipt else True,
        "mocked": bool(receipt.get("mocked")) if receipt else False,
    }


def _panel(run_id: str, proof_receipt: Path, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": "battle.human_interjection_panel.v1",
        "source": "backend_receipts",
        "run_id": run_id,
        "mocked": False,
        "live": True,
        "source_proof_receipt": str(proof_receipt),
        "states": items,
        "claims": {
            "proves": [
                "Canonical Pixi receipt replay reads pause_after_round state from backend proof receipts.",
                "The UI fails closed when backend pause_after_round receipts are unavailable or absent.",
            ],
            "does_not_prove": [
                "Tau execution pausing beyond the backend after-round application receipt.",
                "Production auth, websocket fanout, or staging infrastructure readiness.",
            ],
        },
    }


def _fixture(base: dict[str, Any], fixture_id: str, panel: dict[str, Any] | None) -> dict[str, Any]:
    fixture = dict(base)
    fixture["fixture_id"] = fixture_id
    fixture["qualification_fixture_key"] = fixture_id
    fixture["source_fixture_url"] = f"/battle-fixtures/{fixture_id}/battle.normalized_ux_fixture.json"
    if panel is None:
        fixture.pop("human_interjection_panel", None)
    else:
        fixture["human_interjection_panel"] = panel
    return fixture


def generate(*, proof_path: Path, out_dir: Path | None = None) -> dict[str, Any]:
    proof_path = proof_path.resolve()
    proof = _read(proof_path)
    case_paths = proof["case_receipts"]
    receipts = {name: _read(Path(path)) for name, path in case_paths.items()}
    run_id = proof["run_id"]
    base = _read(BASE_FIXTURE)
    if base.get("mocked") is not False:
        raise RuntimeError(f"base fixture is not non-mocked: {BASE_FIXTURE}")

    generated: dict[str, str] = {}
    fixtures = {
        "battle-004-pause-after-round-pending": _panel(
            run_id,
            proof_path,
            [
                _state_item(
                    state="pending",
                    receipt=receipts["accepted"],
                    receipt_path=case_paths["accepted"],
                    label="Authenticated current-run pause is queued for the next after-round boundary.",
                    backend_receipt=True,
                )
            ],
        ),
        "battle-004-pause-after-round-accepted": _panel(
            run_id,
            proof_path,
            [
                _state_item(
                    state="accepted",
                    receipt=receipts["duplicate"],
                    receipt_path=case_paths["duplicate"],
                    label="Duplicate request id is accepted idempotently against the same backend receipt family.",
                    backend_receipt=True,
                )
            ],
        ),
        "battle-004-pause-after-round-applied": _panel(
            run_id,
            proof_path,
            [
                _state_item(
                    state="applied",
                    receipt=receipts["application"],
                    receipt_path=case_paths["application"],
                    label="Pause request applied after the round without mutating the Judge receipt.",
                    backend_receipt=True,
                )
            ],
        ),
        "battle-004-pause-after-round-rejected": _panel(
            run_id,
            proof_path,
            [
                _state_item(
                    state="rejected",
                    receipt=receipts["invalid_auth"],
                    receipt_path=case_paths["invalid_auth"],
                    label="Invalid pause_after_round auth fails closed with a rejection receipt.",
                    backend_receipt=True,
                )
            ],
        ),
        "battle-004-pause-after-round-unavailable": _panel(
            run_id,
            proof_path,
            [
                _state_item(
                    state="unavailable",
                    receipt=None,
                    receipt_path=str(proof_path),
                    label="No usable backend pause_after_round receipt is available for this fixture state.",
                    backend_receipt=False,
                )
            ],
        ),
        "battle-004-pause-after-round-missing-backend": None,
    }
    for fixture_id, panel in fixtures.items():
        payload = _fixture(base, fixture_id, panel)
        public_path = PUBLIC_ROOT / fixture_id / "battle.normalized_ux_fixture.json"
        _write(public_path, payload)
        generated[fixture_id] = str(public_path)
        if out_dir is not None:
            copy_path = out_dir / fixture_id / "battle.normalized_ux_fixture.json"
            copy_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(public_path, copy_path)

    summary = {
        "schema": "battle.human_interjection_spectator_fixture_generation.v1",
        "status": "PASS",
        "mocked": False,
        "live": True,
        "source_proof_receipt": str(proof_path),
        "generated": generated,
    }
    if out_dir is not None:
        _write(out_dir / "fixture-generation.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate pause_after_round spectator fixtures")
    parser.add_argument("--proof", type=Path, required=True, help="battle.human_interjection_proof.v1 receipt")
    parser.add_argument("--out-dir", type=Path, help="Optional proof copy directory")
    args = parser.parse_args()
    generate(proof_path=args.proof, out_dir=args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
