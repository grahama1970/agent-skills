"""contract - persona_dream_av_bakeoff.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def package_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_contract_path() -> Path:
    return package_root() / "contracts" / "embry_voice_bakeoff_contract.json"


def load_contract(path: str | Path | None) -> dict[str, Any]:
    contract_path = Path(path) if path else default_contract_path()
    with contract_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_contract_copy(contract: dict[str, Any], out_dir: str | Path) -> Path:
    p = Path(out_dir) / "contract.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(contract, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def find_dialogue_shot(contract: dict[str, Any]) -> dict[str, Any]:
    for shot in contract.get("scene", {}).get("shots", []):
        if shot.get("shot_type") == "speaking_character" and shot.get("dialogue"):
            return shot
    raise ValueError("No speaking_character shot with dialogue found in contract.")


def assert_contract_policy(contract: dict[str, Any]) -> None:
    policy = contract.get("policy", {})
    if not policy.get("source_grounded_residue_required", False):
        raise ValueError("Contract must require source-grounded residue.")
    if not policy.get("no_memory_write", False):
        raise ValueError("Contract must explicitly assert no_memory_write=true.")
    if not policy.get("no_arango_upsert", False):
        raise ValueError("Contract must explicitly assert no_arango_upsert=true.")
    if not policy.get("no_qdrant_upsert", False):
        raise ValueError("Contract must explicitly assert no_qdrant_upsert=true.")

    shot = find_dialogue_shot(contract)
    if not shot.get("source_grounded_residue_ids"):
        raise ValueError("Dialogue shot must cite source_grounded_residue_ids.")
    if not shot.get("audio_first"):
        raise ValueError("Dialogue shot must declare audio_first=true.")
    if not shot.get("lip_sync_required"):
        raise ValueError("Dialogue shot must declare lip_sync_required=true.")
