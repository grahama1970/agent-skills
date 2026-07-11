#!/usr/bin/env python3
"""Deterministic Phase 5 contact-sheet gate for persona-dream runs.

Fails closed unless every mapped reference/contact sheet PNG is a nonzero file at
an accepted 4:3 contact-sheet size. WebGPT/ChatGPT often exports 1448x1086 even
when the image header claims 1600x1200, so both native sizes are allowed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Pillow is required for contact-sheet dimension checks") from exc


SCHEMA = "persona_dream.phase_05_contact_sheet_anti_hallucination_gate.v1"
CONTACT_SHEET_WIDTH = 1600
CONTACT_SHEET_HEIGHT = 1200
PREFERRED_SIZE = (CONTACT_SHEET_WIDTH, CONTACT_SHEET_HEIGHT)
CHATGPT_EXPORT_SIZE = (1448, 1086)
ACCEPTED_SIZES: dict[tuple[int, int], str] = {
    PREFERRED_SIZE: "pipeline_preferred",
    CHATGPT_EXPORT_SIZE: "chatgpt_export_native",
}
ACCEPTED_SIZE_LABELS = {
    PREFERRED_SIZE: "1600x1200",
    CHATGPT_EXPORT_SIZE: "1448x1086",
}

ANTI_HALLUCINATION_RULE = (
    "A contact-sheet claim is false until every required character/prop/creature/"
    "effect/environment group maps to an existing nonzero PNG at an accepted "
    "4:3 contact-sheet size (1600x1200 preferred, 1448x1086 ChatGPT-native export) "
    "with sha256. Probe file dimensions before install; image header text is not "
    "proof. Generic shared sheets may be PARTIAL but do not satisfy dedicated "
    "prop/interaction references. Each required sheet also needs a colocated .prompt.md and .contact_sheet.meta.json whose probed dimensions match the PNG bytes."
)


def size_label(size: tuple[int, int]) -> str:
    return ACCEPTED_SIZE_LABELS.get(size, f"{size[0]}x{size[1]}")


def layout_contract_payload() -> dict[str, Any]:
    return {
        "width": CONTACT_SHEET_WIDTH,
        "height": CONTACT_SHEET_HEIGHT,
        "preferred_size": {"width": PREFERRED_SIZE[0], "height": PREFERRED_SIZE[1]},
        "accepted_sizes": [
            {
                "width": width,
                "height": height,
                "label": label,
            }
            for (width, height), label in ACCEPTED_SIZES.items()
        ],
        "required_aspect_ratio": "4:3",
        "required_format": "PNG",
    }


def is_accepted_size(width: int, height: int) -> bool:
    return (width, height) in ACCEPTED_SIZES

DEFAULT_REQUIREMENTS: list[dict[str, str]] = [
    {"id": "character_horus_lupercal", "name": "Horus Lupercal", "type": "character", "file": "horus_reference_sheet.png"},
    {"id": "character_embry_lawson", "name": "Embry Lawson", "type": "character", "file": "embry_reference_sheet.png"},
    {"id": "creature_adult_tyranids", "name": "Adult Tyranids", "type": "creature", "file": "tyranid_environment_reference_sheet.png"},
    {"id": "creature_baby_tyranid_railing", "name": "Baby Tyranid on stone railing", "type": "creature/foreground interaction", "file": "creature_baby_tyranid_railing_reference_sheet.png"},
    {"id": "effect_tzeentch_sky_eye", "name": "Tzeentch sky-eye", "type": "environment effect", "file": "tzeentch_warp_eye_motion_contact_sheet.png"},
    {"id": "prop_umbrella", "name": "Umbrella fabric/ribs/wind behavior", "type": "prop", "file": "prop_umbrella_reference_sheet.png"},
    {"id": "prop_tea_service", "name": "Tea cups/pot/steam/liquid", "type": "prop/liquid/vapor", "file": "prop_tea_service_reference_sheet.png"},
    {"id": "prop_sparta_laptop_notes", "name": "SPARTA screen, notes, source refs, evidence cards", "type": "prop/ui/paper", "file": "prop_sparta_laptop_notes_reference_sheet.png"},
    {"id": "surface_stone_railing_patio", "name": "Stone railing and wet patio surface", "type": "environment surface/prop", "file": "surface_stone_railing_patio_reference_sheet.png"},
    {"id": "environment_void_world_patio", "name": "Void-world patio/weather/temperature", "type": "environment", "file": "tyranid_environment_reference_sheet.png"},
]

PARTIAL_IDS: set[str] = set()  # Removed creature_adult_tyranids and environment_void_world_patio — combined sheet accepted as PASS. Tyranids and void-world are inherently tied; a single sheet serves visual continuity better than two disconnected sheets.


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe_png(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    if not data:
        raise ValueError("empty file")
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    with Image.open(path) as image:
        width, height = image.size
    return {
        "path": str(path.resolve()),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "width": width,
        "height": height,
        "layout_ok": is_accepted_size(width, height),
        "size_label": size_label((width, height)),
        "size_tier": ACCEPTED_SIZES.get((width, height)),
    }




SIDECAR_SCHEMA_V1 = "persona_dream.contact_sheet_sidecar.v1"
ACCEPTED_SIDECAR_SCHEMAS = {
    SIDECAR_SCHEMA_V1,
    "persona_dream.contact_sheet_sidecar.v2",
}


def sidecar_path_for_png(png_path: Path) -> Path:
    return png_path.with_name(f"{png_path.stem}.contact_sheet.meta.json")


def prompt_path_for_png(refs_dir: Path, png_name: str) -> Path:
    return refs_dir / f"{Path(png_name).stem}.prompt.md"


def load_sidecar(sidecar_path: Path) -> dict[str, Any]:
    return json.loads(sidecar_path.read_text(encoding="utf-8"))


def validate_sidecar_for_png(png_path: Path, metrics: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    prompt_path = prompt_path_for_png(png_path.parent, png_path.name)
    sidecar_path = sidecar_path_for_png(png_path)

    if not prompt_path.is_file():
        errors.append(f"{png_path.name}: missing prompt sidecar {prompt_path.name}")
    if not sidecar_path.is_file():
        errors.append(f"{png_path.name}: missing metadata sidecar {sidecar_path.name}")
        return errors

    try:
        sidecar = load_sidecar(sidecar_path)
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{png_path.name}: unreadable sidecar: {exc}")
        return errors

    if sidecar.get("schema") not in ACCEPTED_SIDECAR_SCHEMAS:
        errors.append(f"{png_path.name}: sidecar schema mismatch")
    if sidecar.get("schema") == "persona_dream.contact_sheet_sidecar.v2":
        if not str(sidecar.get("creation_prompt") or "").strip():
            errors.append(f"{png_path.name}: sidecar missing creation_prompt")
        if sidecar.get("probed_width") != metrics.get("width") or sidecar.get("probed_height") != metrics.get("height"):
            errors.append(f"{png_path.name}: sidecar missing probed dimensions")
    if sidecar.get("png_sha256") != metrics.get("sha256"):
        errors.append(f"{png_path.name}: sidecar png_sha256 stale (re-run sync_contact_sheet_sidecars.py)")
    if sidecar.get("probed_width") != metrics.get("width") or sidecar.get("probed_height") != metrics.get("height"):
        errors.append(
            f"{png_path.name}: sidecar dimensions "
            f"{sidecar.get('probed_width')}x{sidecar.get('probed_height')} != "
            f"probed {metrics.get('width')}x{metrics.get('height')}"
        )
    if prompt_path.is_file():
        prompt_sha = hashlib.sha256(prompt_path.read_bytes()).hexdigest()
        if sidecar.get("prompt_sha256") != prompt_sha:
            errors.append(f"{png_path.name}: prompt_sha256 stale (re-run sync_contact_sheet_sidecars.py)")
    return errors


def load_requirements(run_root: Path) -> list[dict[str, Any]]:
    gate_path = run_root / "pipeline_review_8892" / "artifacts" / "phase_05_contact_sheets_anti_hallucination_gate.json"
    if gate_path.exists():
        gate = json.loads(gate_path.read_text())
        reqs = gate.get("requirements") or []
        if reqs:
            return reqs
    return [dict(item) for item in DEFAULT_REQUIREMENTS]


def evaluate_run(run_root: Path) -> dict[str, Any]:
    refs_dir = run_root / "reference_sheets"
    if not refs_dir.is_dir():
        raise FileNotFoundError(f"missing reference_sheets directory: {refs_dir}")

    requirements_in = load_requirements(run_root)
    file_inventory: dict[str, Any] = {}
    evaluated_requirements: list[dict[str, Any]] = []
    dimension_failures: list[str] = []
    sidecar_failures: list[str] = []

    for req in requirements_in:
        req_id = str(req.get("id") or "")
        name = str(req.get("name") or req_id)
        req_type = str(req.get("type") or "")
        file_name = req.get("file")
        record = {
            "id": req_id,
            "name": name,
            "type": req_type,
            "file": file_name,
            "verdict": "FAIL",
            "basis": "",
        }

        if not file_name:
            record["basis"] = "No dedicated reference sheet file mapped."
            evaluated_requirements.append(record)
            continue

        path = refs_dir / str(file_name)
        if not path.is_file() or path.stat().st_size == 0:
            record["basis"] = f"Missing or zero-byte file: {file_name}"
            evaluated_requirements.append(record)
            continue

        try:
            metrics = probe_png(path)
        except (OSError, ValueError) as exc:
            record["basis"] = f"Unreadable image {file_name}: {exc}"
            evaluated_requirements.append(record)
            continue

        file_inventory[str(file_name)] = metrics
        sheet_sidecar_errors = validate_sidecar_for_png(path, metrics)
        if sheet_sidecar_errors:
            sidecar_failures.extend(sheet_sidecar_errors)
            record["verdict"] = "FAIL"
            record["basis"] = sheet_sidecar_errors[0]
            evaluated_requirements.append(record)
            continue
        if not metrics["layout_ok"]:
            dimension_failures.append(
                f"{file_name}: {metrics['width']}x{metrics['height']} not in "
                f"{', '.join(size_label(size) for size in ACCEPTED_SIZES)}"
            )
            record["verdict"] = "FAIL"
            record["basis"] = (
                "Layout contract violation: expected an accepted 4:3 contact-sheet "
                f"size ({', '.join(size_label(size) for size in ACCEPTED_SIZES)}), "
                f"got {metrics['width']}x{metrics['height']}"
            )
        elif req_id in PARTIAL_IDS:
            record["verdict"] = "PARTIAL"
            record["basis"] = (
                f"Dedicated reference sheet exists at {metrics['size_label']}, but sheet "
                "also carries generic environment duties."
            )
        else:
            record["verdict"] = "PASS"
            record["basis"] = (
                f"Dedicated reference sheet exists at {metrics['size_label']}: {file_name}"
            )
        evaluated_requirements.append(record)

    # include any extra reference PNGs in inventory for transparency
    for png in sorted(refs_dir.glob("*.png")):
        if png.name in file_inventory:
            continue
        try:
            file_inventory[png.name] = probe_png(png)
        except (OSError, ValueError):
            continue

    failure_count = sum(1 for item in evaluated_requirements if item["verdict"] == "FAIL")
    partial_count = sum(1 for item in evaluated_requirements if item["verdict"] == "PARTIAL")
    verdict = "PASS" if failure_count == 0 and not sidecar_failures else "FAIL"

    downstream_scope: list[str] = []
    if verdict != "PASS":
        downstream_scope.append(
            "Do not proceed to final script/storyboard generation as accepted."
        )
        downstream_scope.append(
            "Repair contact sheets until every mapped PNG is an accepted 4:3 size "
            f"({', '.join(size_label(size) for size in ACCEPTED_SIZES)})."
        )
        if dimension_failures:
            downstream_scope.append("Dimension failures: " + "; ".join(dimension_failures))

    return {
        "schema": SCHEMA,
        "created_at": now_iso(),
        "phase": "Phase 5: Contact Sheets",
        "anti_hallucination_rule": ANTI_HALLUCINATION_RULE,
        "layout_contract": layout_contract_payload(),
        "verdict": verdict,
        "file_inventory": file_inventory,
        "requirements": evaluated_requirements,
        "failure_count": failure_count,
        "partial_count": partial_count,
        "dimension_failure_count": len(dimension_failures),
        "dimension_failures": dimension_failures,
        "sidecar_failure_count": len(sidecar_failures),
        "sidecar_failures": sidecar_failures,
        "downstream_scope": downstream_scope,
    }



def evaluate_reference_dir(refs_dir: Path) -> dict[str, Any]:
    """Fail closed if any reference-sheet PNG is not an accepted 4:3 contact size."""
    if not refs_dir.is_dir():
        raise FileNotFoundError(f"missing reference_sheets directory: {refs_dir}")

    file_inventory: dict[str, Any] = {}
    dimension_failures: list[str] = []
    for png in sorted(refs_dir.glob("*.png")):
        try:
            metrics = probe_png(png)
        except (OSError, ValueError) as exc:
            dimension_failures.append(f"{png.name}: {exc}")
            continue
        file_inventory[png.name] = metrics
        if not metrics["layout_ok"]:
            dimension_failures.append(
                f"{png.name}: {metrics['width']}x{metrics['height']} not in "
                f"{', '.join(size_label(size) for size in ACCEPTED_SIZES)}"
            )

    verdict = "PASS" if not dimension_failures else "FAIL"
    return {
        "schema": "persona_dream.reference_sheet_layout_contract.v1",
        "created_at": now_iso(),
        "layout_contract": layout_contract_payload(),
        "verdict": verdict,
        "file_inventory": file_inventory,
        "dimension_failure_count": len(dimension_failures),
        "dimension_failures": dimension_failures,
    }


def validate_gate(gate: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    contract = gate.get("layout_contract") or {}
    accepted = contract.get("accepted_sizes") or []
    if contract.get("width") != CONTACT_SHEET_WIDTH or contract.get("height") != CONTACT_SHEET_HEIGHT:
        errors.append("layout_contract missing preferred dimensions")
    if len(accepted) < 2:
        errors.append("layout_contract missing accepted_sizes whitelist")
    for item in gate.get("requirements", []):
        file_name = item.get("file")
        if not file_name:
            if item.get("verdict") != "FAIL":
                errors.append(f"{item.get('id')}: missing file must be FAIL")
            continue
        inv = (gate.get("file_inventory") or {}).get(str(file_name))
        if not inv:
            errors.append(f"{file_name}: missing file_inventory entry")
            continue
        if not inv.get("layout_ok", False):
            errors.append(
                f"{file_name}: layout_ok is false ({inv.get('width')}x{inv.get('height')})"
            )
        if item.get("verdict") == "PASS" and not inv.get("layout_ok", False):
            errors.append(f"{item.get('id')}: PASS with wrong dimensions")
    if gate.get("verdict") == "PASS" and gate.get("failure_count", 0) > 0:
        errors.append("verdict PASS with nonzero failure_count")
    if gate.get("verdict") == "PASS" and gate.get("dimension_failure_count", 0) > 0:
        errors.append("verdict PASS with dimension failures")
    if gate.get("verdict") == "PASS" and gate.get("sidecar_failure_count", 0) > 0:
        errors.append("verdict PASS with sidecar failures")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True, help="Persona-dream run root")
    parser.add_argument(
        "--write-gate",
        action="store_true",
        help="Write pipeline_review_8892/artifacts/phase_05_contact_sheets_anti_hallucination_gate.json",
    )
    parser.add_argument(
        "--refs-only",
        action="store_true",
        help="Only verify every PNG under reference_sheets/ is an accepted 4:3 size",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON summary on stdout")
    args = parser.parse_args()

    run_root = args.run_root.expanduser().resolve()
    if args.refs_only:
        gate = evaluate_reference_dir(run_root / "reference_sheets")
        payload = {
            "status": "PASS" if gate["verdict"] == "PASS" else "FAIL",
            "mode": "refs_only",
            "verdict": gate["verdict"],
            "dimension_failure_count": gate["dimension_failure_count"],
            "dimension_failures": gate["dimension_failures"],
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(json.dumps(payload, indent=2))
        return 0 if payload["status"] == "PASS" else 1

    gate = evaluate_run(run_root)
    errors = validate_gate(gate)

    if args.write_gate:
        out_path = (
            run_root
            / "pipeline_review_8892"
            / "artifacts"
            / "phase_05_contact_sheets_anti_hallucination_gate.json"
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(gate, indent=2) + "\n")

    payload = {
        "status": "PASS" if gate["verdict"] == "PASS" and not errors else "FAIL",
        "verdict": gate["verdict"],
        "failure_count": gate["failure_count"],
        "dimension_failure_count": gate["dimension_failure_count"],
        "dimension_failures": gate["dimension_failures"],
        "sidecar_failure_count": gate.get("sidecar_failure_count", 0),
        "sidecar_failures": gate.get("sidecar_failures", []),
        "errors": errors,
        "gate_path": str(
            run_root
            / "pipeline_review_8892"
            / "artifacts"
            / "phase_05_contact_sheets_anti_hallucination_gate.json"
        ),
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(json.dumps(payload, indent=2))

    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
