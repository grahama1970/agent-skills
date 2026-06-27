"""Validate a Watch UI overlay payload against its JSON Schema."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


DEFAULT_ARCH_DIR = Path(__file__).resolve().parents[1] / "docs" / "architecture"
DEFAULT_SCHEMA = DEFAULT_ARCH_DIR / "watch_ui_overlay_payload.schema.json"
DEFAULT_PAYLOAD = (
    DEFAULT_ARCH_DIR
    / "generated"
    / "bad_santa_marcus_0248_overlay_payload"
    / "watch_ui_overlay_payload.bad_santa_marcus.json"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--payload", type=Path, default=DEFAULT_PAYLOAD)
    args = parser.parse_args()

    schema = _read_json(args.schema)
    payload = _read_json(args.payload)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(payload),
        key=lambda error: list(error.path),
    )
    if errors:
        details = "\n".join(
            f"- {list(error.path)}: {error.message}" for error in errors
        )
        raise SystemExit(f"overlay_payload_schema_invalid\n{details}")

    print(
        "overlay_payload_schema_ok",
        payload["overlay_count"],
        ",".join(payload["proof_scope"]),
    )
    return 0


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise TypeError(f"expected JSON object: {path}")
    return data


if __name__ == "__main__":
    raise SystemExit(main())
