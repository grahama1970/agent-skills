"""Validate Battle music score packets without rendering or playing audio.

Inputs:
  - battle.music_score_packet.v1 JSON
  - optional motif manifest JSON

Outputs:
  - battle.music_score_packet_validation.v1 JSON report

Failure modes:
  - missing required fields
  - unsupported timing, tempo, motif, or claim boundary values
  - raw host paths or terminal outcome overclaims
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import typer
from loguru import logger


app = typer.Typer(help="Battle music score packet validation")

SCHEMA = "battle.music_score_packet.v1"
REPORT_SCHEMA = "battle.music_score_packet_validation.v1"
ALLOWED_STATUS = {
    "generated_unvalidated",
    "validation_failed",
    "validator_passed",
}
ALLOWED_MOTIF_ROLES = {
    "foreground",
    "counterpoint",
    "background",
    "accent",
    "fallback",
}
TERMINAL_WORDS = {
    "victory",
    "death",
    "kill",
    "killed",
    "terminal",
    "blue_block",
    "blue_kill",
    "exploit_success",
}
FORBIDDEN_CLAIM_PATTERNS = [
    re.compile(r"\b(exploit|red)\s+(succeeded|success|won)\b", re.IGNORECASE),
    re.compile(r"\bblue\s+(blocked|killed|contained|detected)\b", re.IGNORECASE),
    re.compile(r"\b(judge|runtime|playback|audio)\s+(verified|proved|passed|played)\b", re.IGNORECASE),
    re.compile(r"\b(score|midi)\s+(validated|promoted)\b", re.IGNORECASE),
]
RAW_PATH_MARKERS = (
    "/tmp/",
    "/home/",
    "/mnt/",
    "/workspace",
    "tau-dag-run/",
    "command-loop/",
    "command-artifacts/",
    "provider-workspace",
    "C:\\",
    "D:\\",
)


@app.command("validate")
def validate(
    packet: Path = typer.Option(..., "--packet", exists=True, file_okay=True, dir_okay=False, readable=True),
    out: Path | None = typer.Option(None, "--out", help="Optional path for validation report JSON."),
    motif_manifest: Path | None = typer.Option(
        None,
        "--motif-manifest",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Optional manifest with known sprite or motif ids.",
    ),
) -> None:
    """Validate a Battle score packet and optionally write the report."""

    report = validate_score_packet_path(packet=packet, motif_manifest=motif_manifest)
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        logger.info("Wrote Battle score packet validation report: {}", out)
    typer.echo(json.dumps(report, indent=2, sort_keys=True))
    if report["status"] != "PASS":
        raise typer.Exit(1)


def validate_score_packet_path(*, packet: Path, motif_manifest: Path | None = None) -> dict[str, Any]:
    data = _read_json(packet)
    motif_ids = _load_motif_ids(motif_manifest)
    return validate_score_packet(data, packet_path=packet, motif_ids=motif_ids)


def validate_score_packet(
    data: dict[str, Any],
    *,
    packet_path: Path | None = None,
    motif_ids: set[str] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    required = {
        "schema",
        "battle_id",
        "score_id",
        "source_receipt_ids",
        "start_boundary",
        "duration_bars",
        "tempo_bpm",
        "time_signature_plan",
        "tonal_center",
        "intensity",
        "motifs",
        "required_theme_ids",
        "forbidden_claims",
        "output_midi",
        "fallback_score_id",
        "status",
    }
    missing = sorted(required - set(data))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    if data.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA}")
    if data.get("status") not in ALLOWED_STATUS:
        errors.append(f"status must be one of {sorted(ALLOWED_STATUS)}")
    if data.get("status") != "generated_unvalidated":
        warnings.append("validator expects composer packets to remain generated_unvalidated before Battle promotion")

    _validate_receipts(data.get("source_receipt_ids"), errors)
    _validate_start_boundary(data.get("start_boundary"), errors)
    _validate_duration(data.get("duration_bars"), errors)
    _validate_tempo(data.get("tempo_bpm"), errors)
    _validate_time_signatures(data.get("time_signature_plan"), errors)
    _validate_intensity(data.get("intensity"), errors)
    _validate_motifs(data.get("motifs"), motif_ids, errors, warnings)
    _validate_string_list(data.get("required_theme_ids"), "required_theme_ids", errors)
    _validate_forbidden_claims(data.get("forbidden_claims"), errors)
    _validate_paths(data, errors)
    _validate_claim_boundary(data, errors)

    report = {
        "schema": REPORT_SCHEMA,
        "status": "FAIL" if errors else "PASS",
        "mocked": False,
        "live": "local_deterministic_validator",
        "packet": str(packet_path) if packet_path is not None else None,
        "battle_id": data.get("battle_id"),
        "score_id": data.get("score_id"),
        "errors": errors,
        "warnings": warnings,
        "checks": {
            "required_fields": not missing,
            "receipt_bound": not any(error.startswith("source_receipt_ids") for error in errors),
            "future_boundary_shape": not any(error.startswith("start_boundary") for error in errors),
            "motif_shape": not any(error.startswith("motifs") for error in errors),
            "claim_boundary": not any("claim" in error.lower() for error in errors),
            "raw_path_boundary": not any("raw path" in error.lower() for error in errors),
            "rendering_not_run": True,
            "playback_not_run": True,
        },
        "claims": {
            "proves": [
                "The Battle music score packet is structurally valid for deterministic handoff."
            ]
            if not errors
            else [],
            "does_not_prove": [
                "The MIDI renders successfully.",
                "The score was promoted by Battle.",
                "The score was scheduled or played.",
                "Any Battle death, victory, exploit, Blue, or Judge outcome occurred.",
            ],
        },
    }
    return report


def _validate_receipts(value: Any, errors: list[str]) -> None:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        errors.append("source_receipt_ids must be a non-empty list of strings")


def _validate_start_boundary(value: Any, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append("start_boundary must be an object")
        return
    bar = value.get("bar")
    beat = value.get("beat")
    if not isinstance(bar, int) or bar < 1:
        errors.append("start_boundary.bar must be an integer >= 1")
    if not isinstance(beat, int | float) or beat < 1:
        errors.append("start_boundary.beat must be a number >= 1")


def _validate_duration(value: Any, errors: list[str]) -> None:
    if not isinstance(value, int) or value < 1 or value > 128:
        errors.append("duration_bars must be an integer from 1 to 128")


def _validate_tempo(value: Any, errors: list[str]) -> None:
    if not isinstance(value, int | float) or value < 40 or value > 220:
        errors.append("tempo_bpm must be a number from 40 to 220")


def _validate_time_signatures(value: Any, errors: list[str]) -> None:
    if not isinstance(value, list) or not value:
        errors.append("time_signature_plan must be a non-empty list")
        return
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            errors.append(f"time_signature_plan[{index}] must be an object")
            continue
        if not isinstance(item.get("bar_start"), int) or item["bar_start"] < 1:
            errors.append(f"time_signature_plan[{index}].bar_start must be an integer >= 1")
        if not isinstance(item.get("numerator"), int) or item["numerator"] < 1 or item["numerator"] > 12:
            errors.append(f"time_signature_plan[{index}].numerator must be an integer from 1 to 12")
        if item.get("denominator") not in {2, 4, 8, 16}:
            errors.append(f"time_signature_plan[{index}].denominator must be one of 2, 4, 8, 16")


def _validate_intensity(value: Any, errors: list[str]) -> None:
    if not isinstance(value, int | float) or value < 0 or value > 1:
        errors.append("intensity must be a number from 0 to 1")


def _validate_motifs(value: Any, motif_ids: set[str] | None, errors: list[str], warnings: list[str]) -> None:
    if not isinstance(value, list) or not value:
        errors.append("motifs must be a non-empty list")
        return
    foreground_count = 0
    for index, motif in enumerate(value):
        if not isinstance(motif, dict):
            errors.append(f"motifs[{index}] must be an object")
            continue
        sprite_id = motif.get("sprite_id")
        role = motif.get("role")
        if not isinstance(sprite_id, str) or not sprite_id:
            errors.append(f"motifs[{index}].sprite_id must be a non-empty string")
        elif motif_ids is not None and sprite_id not in motif_ids:
            errors.append(f"motifs[{index}].sprite_id is not present in motif manifest: {sprite_id}")
        if role not in ALLOWED_MOTIF_ROLES:
            errors.append(f"motifs[{index}].role must be one of {sorted(ALLOWED_MOTIF_ROLES)}")
        if role == "foreground":
            foreground_count += 1
    if foreground_count > 2:
        errors.append("motifs may include at most two foreground motifs")
    if motif_ids is None:
        warnings.append("motif manifest not supplied; sprite_id existence was not checked")


def _validate_string_list(value: Any, field: str, errors: list[str]) -> None:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        errors.append(f"{field} must be a non-empty list of strings")


def _validate_forbidden_claims(value: Any, errors: list[str]) -> None:
    _validate_string_list(value, "forbidden_claims", errors)
    if not isinstance(value, list):
        return
    lower = {str(item).lower() for item in value}
    for required in ["victory", "death", "exploit_success"]:
        if required not in lower:
            errors.append(f"forbidden_claims must include {required}")


def _validate_paths(data: dict[str, Any], errors: list[str]) -> None:
    output_midi = data.get("output_midi")
    if not isinstance(output_midi, str) or not output_midi.endswith(".mid"):
        errors.append("output_midi must be a relative .mid path")
    for field in ["output_midi", "fallback_score_id"]:
        value = data.get(field)
        if isinstance(value, str) and any(marker in value for marker in RAW_PATH_MARKERS):
            errors.append(f"{field} contains a raw path marker")


def _validate_claim_boundary(data: dict[str, Any], errors: list[str]) -> None:
    claim_payload = dict(data)
    claim_payload.pop("forbidden_claims", None)
    claim_payload.pop("claims", None)
    serialized_claim_surface = json.dumps(claim_payload, sort_keys=True)
    for pattern in FORBIDDEN_CLAIM_PATTERNS:
        if pattern.search(serialized_claim_surface):
            errors.append("score packet metadata contains unsupported Battle outcome claim")
            break
    claims = data.get("claims")
    if isinstance(claims, dict):
        proves = " ".join(str(item) for item in claims.get("proves", []))
        for pattern in FORBIDDEN_CLAIM_PATTERNS:
            if pattern.search(proves):
                errors.append("claims.proves contains unsupported Battle outcome or validation claim")
                break
    if _contains_terminal_material(data) and not _has_terminal_receipt_hint(data):
        errors.append("terminal-themed material requires an explicit terminal/Judge source receipt hint")


def _contains_terminal_material(data: dict[str, Any]) -> bool:
    surfaces: list[str] = []
    for field in ["score_id", "fallback_score_id", "output_midi", "tonal_center"]:
        value = data.get(field)
        if isinstance(value, str):
            surfaces.append(value.lower())
    for motif in data.get("motifs", []) if isinstance(data.get("motifs"), list) else []:
        if isinstance(motif, dict):
            surfaces.extend(str(value).lower() for value in motif.values() if isinstance(value, str))
    surface = " ".join(surfaces)
    return any(word in surface for word in TERMINAL_WORDS)


def _has_terminal_receipt_hint(data: dict[str, Any]) -> bool:
    receipt_ids = " ".join(str(item).lower() for item in data.get("source_receipt_ids", []) if isinstance(item, str))
    return any(word in receipt_ids for word in ["terminal", "judge", "victory", "death", "exploit_success"])


def _load_motif_ids(path: Path | None) -> set[str] | None:
    if path is None:
        return None
    data = _read_json(path)
    ids: set[str] = set()
    for key in ["motifs", "sprites", "characters"]:
        value = data.get(key)
        if isinstance(value, dict):
            ids.update(str(item) for item in value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    ids.add(item)
                elif isinstance(item, dict):
                    for field in ["sprite_id", "motif_id", "id"]:
                        if isinstance(item.get(field), str):
                            ids.add(item[field])
    return ids


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise typer.BadParameter(f"{path} must contain a JSON object")
    return data


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "validate":
        sys.argv.pop(1)
    app()
