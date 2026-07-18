#!/usr/bin/env python
"""Generate the committed recorded adaptive-lineage mechanics fixture.

Builds a real ``battle.adaptive_lineage_qualification.v1`` bundle from recorded
specimens (RecordedSpecimenProvider), normalizes it, and writes the spectator
fixture to ``spectator/src/lineage/__fixtures__/adaptive-lineage-recorded.json``.

Usage:
    uv run python scripts/build_adaptive_lineage_recorded_fixture.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from battle_skill.adaptive_lineage_mechanics_fixture import (  # noqa: E402
    build_recorded_qualification_bundle,
    normalize_adaptive_lineage_bundle,
    validate_normalized_adaptive_lineage_fixture,
)

# Deterministic timestamp so the committed fixture is byte-stable.
GENERATED_AT = "2026-07-18T00:00:00Z"

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "spectator"
    / "src"
    / "lineage"
    / "__fixtures__"
    / "adaptive-lineage-recorded.json"
)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        bundle_dir = build_recorded_qualification_bundle(Path(tmp) / "bundle")
        fixture = normalize_adaptive_lineage_bundle(
            bundle_dir, generated_at=GENERATED_AT
        )

    report = validate_normalized_adaptive_lineage_fixture(fixture)
    if report["status"] != "PASS":
        print(json.dumps(report, indent=2))
        raise SystemExit("normalized fixture failed validation")

    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(
        json.dumps(fixture, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {FIXTURE_PATH}")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
