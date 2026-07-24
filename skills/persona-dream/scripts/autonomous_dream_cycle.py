#!/usr/bin/env python3
"""Compatibility entrypoint that installs the amended counterpart gate.

The historical GOAL_V3 cycle implementation is preserved byte-for-byte in
``autonomous_dream_cycle_legacy.py``. This entrypoint re-exports that module's
public surface and replaces only the counterpart-isolation decision with the
hook-grounded target-change gate.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_LEGACY_PATH = _HERE / "autonomous_dream_cycle_legacy.py"
_GATE_PATH = _HERE / "counterpart_isolation_gate.py"


def _load_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {name}: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_legacy = _load_path("persona_dream_autonomous_cycle_legacy", _LEGACY_PATH)
_gate = _load_path("persona_dream_counterpart_isolation_gate", _GATE_PATH)

# Preserve the prior script's import surface for existing probes and callers.
for _name in dir(_legacy):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_legacy, _name)


def _source_memory(source_id: str) -> dict[str, Any] | None:
    for visibility_state in ("active", None):
        filters: dict[str, Any] = {"_key": source_id}
        if visibility_state is not None:
            filters["visibility_state"] = visibility_state
        response = _legacy.post(
            "/list",
            {"collection": "persona_memory", "filters": filters, "limit": 3},
        )
        documents = response.get("documents") or []
        if documents:
            return documents[0]
    return None


def counterpart_violation_reasons(
    claims: list,
    counterpart_id: str,
    id_field: str,
    *,
    source_documents=None,
    source_resolver=None,
):
    resolver = source_resolver
    if resolver is None and source_documents is None:
        resolver = _source_memory
    return _gate.counterpart_violation_reasons(
        claims,
        counterpart_id,
        id_field,
        source_documents=source_documents,
        source_resolver=resolver,
        model_owner_id=getattr(_legacy, "PERSONA", "embry"),
    )


def counterpart_violations(
    claims: list,
    counterpart_id: str,
    id_field: str,
    *,
    source_documents=None,
    source_resolver=None,
) -> list:
    return list(counterpart_violation_reasons(
        claims,
        counterpart_id,
        id_field,
        source_documents=source_documents,
        source_resolver=source_resolver,
    ))


# main() resolves this name from the legacy module's globals at runtime.
_legacy.counterpart_violations = counterpart_violations


def main() -> int:
    _legacy.counterpart_violations = counterpart_violations
    return _legacy.main()


if __name__ == "__main__":
    raise SystemExit(main())
