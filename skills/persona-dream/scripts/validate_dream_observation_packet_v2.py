#!/usr/bin/env python3
"""Validate one persona-dream v2 observation packet.

Checks:
  1. JSON-schema conformance against dream_observation_packet.v2.schema.json.
  2. psychological_interpretation_performed is false (evidence-only invariant).
  3. No psychology token leaked into any enriched visible_entities/actions/
     absences/summary field (independent re-scan; the filter must have caught it).
  4. Independent rehash of every sampled frame under the run root.
  5. packet_status/degradations consistency.

Exit 0 on PASS, 1 on any failure. Prints a JSON report.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from build_observation_packet_v2 import psychology_hit, sha256_file  # noqa: E402
from pydantic_step_gate import pydantic_error_messages

SCHEMA_PATH = ROOT / "schemas/dream_observation_packet.v2.schema.json"


def validate(packet_path: Path, run_root: Path, frames_root: Path | None = None) -> tuple[bool, dict[str, Any]]:
    errors: list[str] = []
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    # Frame paths are relative to the packet's own directory (same convention as
    # the v1 packet). Callers may override with an explicit frames_root.
    frames_root = frames_root or packet_path.resolve().parent

    for message in pydantic_error_messages(schema, packet):
        errors.append(f"schema[pydantic]: {message}")
    validator = jsonschema.Draft202012Validator(schema)
    schema_errors = sorted(validator.iter_errors(packet), key=lambda e: e.path)
    for e in schema_errors:
        loc = "/".join(str(p) for p in e.path)
        errors.append(f"schema[{loc}]: {e.message}")

    if packet.get("psychological_interpretation_performed") is not False:
        errors.append("psychological_interpretation_performed must be false")

    # independent psychology re-scan of enriched fields
    vef = packet.get("visible_entities_per_frame", {})
    for fr in vef.get("frames", []) or []:
        for field in ("visible_entities", "actions", "absences"):
            for phrase in fr.get(field, []) or []:
                tok = psychology_hit(str(phrase))
                if tok:
                    errors.append(f"psychology leak frame {fr.get('index')} {field}: {tok!r} in {phrase!r}")
        if fr.get("summary"):
            tok = psychology_hit(str(fr["summary"]))
            if tok:
                errors.append(f"psychology leak frame {fr.get('index')} summary: {tok!r}")

    # rehash sampled frames
    frames = packet.get("sampled_frames", {}).get("frames", []) or []
    rehashed = 0
    for fr in frames:
        rel = fr.get("path", "")
        fp = (frames_root / rel).resolve()
        try:
            fp.relative_to(frames_root.resolve())
        except ValueError:
            errors.append(f"frame path escapes run root: {rel}")
            continue
        if not fp.is_file():
            errors.append(f"frame missing: {rel}")
            continue
        if sha256_file(fp) != fr.get("sha256"):
            errors.append(f"frame sha256 mismatch: {rel}")
        else:
            rehashed += 1

    # status/degradation consistency
    status = packet.get("packet_status")
    degs = packet.get("degradations", [])
    if status == "DEGRADED" and not degs:
        errors.append("packet_status DEGRADED but no degradations recorded")
    if status == "ACCEPTED" and degs:
        errors.append("packet_status ACCEPTED but degradations present")

    report = {
        "packet": str(packet_path),
        "schema_valid": not schema_errors,
        "frames_rehashed": rehashed,
        "packet_status": status,
        "psychology_rejected_recorded": len(vef.get("rejected_by_psychology_filter", []) or []),
        "vertex_consistency_outcomes": [
            v.get("outcome") for v in packet.get("vertex_consistency", {}).get("vertices", [])
        ],
        "errors": errors,
        "ok": not errors,
    }
    return not errors, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet")
    parser.add_argument("--run-root", default=str(ROOT))
    args = parser.parse_args(argv)
    ok, report = validate(Path(args.packet), Path(args.run_root))
    print(json.dumps(report, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
