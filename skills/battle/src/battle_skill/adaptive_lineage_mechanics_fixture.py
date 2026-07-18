"""Normalize a ``battle.adaptive_lineage_qualification.v1`` bundle into a
spectator-loadable UX fixture — MECHANICS-FIRST.

Every value in the normalized fixture is sourced ONLY from the receipts written
by :func:`battle_skill.adaptive_lineage.run_adaptive_lineage_qualification`:

    <bundle>/adaptive-lineage-qualification.json   the qualification receipt
    <bundle>/receipts/specimen-*.json              the four Red specimen sources
    <bundle>/receipts/fitness-*.json               per-candidate fitness receipts
    <bundle>/receipts/lineage-selection.json       the deterministic selection
    <bundle>/provenance.json                        data_source (recorded | live)

No value is invented: mutation operators, technique deltas, changed AST
dimensions, novelty distances, delta status, fitness status, Judge outcomes, the
selection and the qualification verdict are all read straight from the receipts.

The ``data_source`` field is read from the bundle provenance (``"recorded"`` for
this task's RecordedSpecimenProvider bundle, ``"live"`` for the Task 5 live
provider) — it is never hardcoded to ``"live"``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .adaptive_lineage import (
    CANONICAL_SPECIMEN_IDS,
    RecordedSpecimenProvider,
    run_adaptive_lineage_qualification,
)

FIXTURE_SCHEMA = "battle.adaptive_lineage_mechanics_fixture.v1"
VALIDATION_SCHEMA = "battle.adaptive_lineage_mechanics_fixture_validation.v1"
PROVENANCE_SCHEMA = "battle.adaptive_lineage_bundle_provenance.v1"

DATA_SOURCES: tuple[str, ...] = ("recorded", "live")

# Lineage-design constants (kept in step with adaptive_lineage.py).
GENERATION: dict[str, int] = {"G0": 0, "G1-A": 1, "G1-B": 1, "G2": 2}
ROLE: dict[str, str] = {
    "G0": "seed",
    "G1-A": "candidate",
    "G1-B": "candidate",
    "G2": "descendant",
}
G1_IDS: tuple[str, ...] = ("G1-A", "G1-B")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object at {path}")
    return value


def _changed_dimensions(fitness: dict[str, Any]) -> list[dict[str, Any]]:
    """The AST dimensions the delta validation marks ``changed=True``."""
    delta = fitness.get("delta_validation") or {}
    per_dimension = delta.get("per_dimension") or []
    return [
        {
            "dimension": entry.get("dimension"),
            "parent": entry.get("parent"),
            "child": entry.get("child"),
        }
        for entry in per_dimension
        if entry.get("changed")
    ]


def _judge_outcome(fitness: dict[str, Any]) -> dict[str, Any]:
    outcome = fitness.get("judge_outcome") or {}
    return {
        "vulnerable_original_confirmed": bool(
            outcome.get("vulnerable_original_confirmed", False)
        ),
        "patched_bypass": bool(outcome.get("patched_bypass", False)),
        "duration_seconds": float(outcome.get("duration_seconds", 0.0)),
    }


def resolve_data_source(bundle_dir: Path, override: str | None = None) -> str:
    """Resolve the bundle's ``data_source`` — from the bundle, never hardcoded.

    Priority: an explicit ``override`` (used by the live orchestrator), else the
    ``provenance.json`` written next to the qualification receipt. Fail closed on
    any value outside :data:`DATA_SOURCES`.
    """
    if override is not None:
        source = override
    else:
        provenance_path = bundle_dir / "provenance.json"
        if not provenance_path.exists():
            raise ValueError(
                f"cannot resolve data_source: {provenance_path} is missing and no "
                "override was supplied (data_source must come from the bundle)"
            )
        source = str(_read_json(provenance_path).get("data_source"))
    if source not in DATA_SOURCES:
        raise ValueError(
            f"data_source {source!r} is not one of {DATA_SOURCES}"
        )
    return source


def normalize_adaptive_lineage_bundle(
    bundle_dir: Path,
    *,
    data_source: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Project an adaptive-lineage qualification bundle into a UX fixture."""
    bundle_dir = Path(bundle_dir)
    qualification = _read_json(bundle_dir / "adaptive-lineage-qualification.json")
    receipts_dir = bundle_dir / "receipts"

    specimens = {
        sid: _read_json(receipts_dir / f"specimen-{sid}.json")
        for sid in CANONICAL_SPECIMEN_IDS
        if (receipts_dir / f"specimen-{sid}.json").exists()
    }
    fitness = {
        sid: _read_json(receipts_dir / f"fitness-{sid}.json")
        for sid in CANONICAL_SPECIMEN_IDS
        if (receipts_dir / f"fitness-{sid}.json").exists()
    }
    selection = qualification.get("selection_receipt") or {}
    if not selection and (receipts_dir / "lineage-selection.json").exists():
        selection = _read_json(receipts_dir / "lineage-selection.json")

    selected_id = selection.get("selected_id")
    runner_up_id = selection.get("runner_up_id")

    resolved_source = resolve_data_source(bundle_dir, data_source)

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for sid in CANONICAL_SPECIMEN_IDS:
        specimen = specimens.get(sid)
        if specimen is None:
            continue
        parent_id = None
        if sid in G1_IDS:
            parent_id = "G0"
        elif sid == "G2":
            parent_id = selected_id

        node: dict[str, Any] = {
            "id": sid,
            "role": ROLE[sid],
            "generation": GENERATION[sid],
            "parentId": parent_id,
            "mutation_operator": specimen.get("mutation_operator"),
            "technique_delta": specimen.get("technique_delta"),
            "selected": sid == selected_id,
            "runner_up": sid == runner_up_id,
        }

        fit = fitness.get(sid)
        if fit is not None:
            changed = _changed_dimensions(fit)
            node.update(
                {
                    "novelty_distance": int(fit.get("novelty_distance", 0)),
                    "delta_status": fit.get("delta_status"),
                    "fitness_status": fit.get("status"),
                    "changed_dimensions": changed,
                    "judge_outcome": _judge_outcome(fit),
                }
            )
            if parent_id is not None:
                edges.append(
                    {
                        "from": parent_id,
                        "to": sid,
                        "mutation_operator": specimen.get("mutation_operator"),
                        "novelty_distance": int(fit.get("novelty_distance", 0)),
                        "delta_status": fit.get("delta_status"),
                        "changed_dimensions": changed,
                    }
                )
        else:
            # G0 seed — no mutation, no parent, no delta.
            node.update(
                {
                    "novelty_distance": None,
                    "delta_status": None,
                    "fitness_status": None,
                    "changed_dimensions": [],
                    "judge_outcome": None,
                }
            )
        nodes.append(node)

    fixture: dict[str, Any] = {
        "schema": FIXTURE_SCHEMA,
        "battle_id": qualification.get("battle_id"),
        "run_id": qualification.get("run_id"),
        "data_source": resolved_source,
        "generated_at": generated_at,
        "qualification": {
            "status": qualification.get("status"),
            "stop_condition": qualification.get("stop_condition"),
            "reasons": list(qualification.get("reasons") or []),
        },
        "selection": {
            "selected_id": selected_id,
            "runner_up_id": runner_up_id,
            "deciding_criterion": selection.get("deciding_criterion"),
        },
        "nodes": nodes,
        "edges": edges,
    }
    return fixture


def validate_normalized_adaptive_lineage_fixture(
    fixture: dict[str, Any],
) -> dict[str, Any]:
    """Fail-closed shape check for a normalized adaptive-lineage fixture."""
    problems: list[str] = []

    if fixture.get("schema") != FIXTURE_SCHEMA:
        problems.append(f"schema != {FIXTURE_SCHEMA}")
    if fixture.get("data_source") not in DATA_SOURCES:
        problems.append(f"data_source {fixture.get('data_source')!r} invalid")

    nodes = fixture.get("nodes") or []
    node_ids = [n.get("id") for n in nodes]
    if node_ids != list(CANONICAL_SPECIMEN_IDS):
        problems.append(f"node ids {node_ids} != {list(CANONICAL_SPECIMEN_IDS)}")

    by_id = {n.get("id"): n for n in nodes}
    if by_id.get("G0", {}).get("parentId") is not None:
        problems.append("G0 must have no parent")
    for gid in G1_IDS:
        if by_id.get(gid, {}).get("parentId") != "G0":
            problems.append(f"{gid} must be parented to G0")

    selection = fixture.get("selection") or {}
    selected_id = selection.get("selected_id")
    if selected_id not in G1_IDS:
        problems.append(f"selected_id {selected_id!r} is not a G1 candidate")
    if by_id.get("G2", {}).get("parentId") != selected_id:
        problems.append("G2 must be parented to the selected G1")
    if not selection.get("deciding_criterion"):
        problems.append("selection missing deciding_criterion")

    for did in ("G1-A", "G1-B", "G2"):
        node = by_id.get(did, {})
        if not node.get("mutation_operator"):
            problems.append(f"{did} missing mutation_operator")
        if not node.get("technique_delta"):
            problems.append(f"{did} missing technique_delta")
        if node.get("novelty_distance") is None:
            problems.append(f"{did} missing novelty_distance")
        if not node.get("changed_dimensions"):
            problems.append(f"{did} has no changed AST dimensions")

    qualification = fixture.get("qualification") or {}
    if qualification.get("status") not in ("PASS", "FAIL"):
        problems.append("qualification.status must be PASS or FAIL")

    return {
        "schema": VALIDATION_SCHEMA,
        "status": "PASS" if not problems else "FAIL",
        "problems": problems,
        "node_count": len(nodes),
        "edge_count": len(fixture.get("edges") or []),
        "data_source": fixture.get("data_source"),
    }


def validate_normalized_adaptive_lineage_fixture_path(path: Path) -> dict[str, Any]:
    return validate_normalized_adaptive_lineage_fixture(_read_json(Path(path)))


# ---------------------------------------------------------------------------
# Recorded bundle builder — reuses the RecordedSpecimenProvider fixture pattern
# from tests/test_adaptive_lineage_reducer.py to GENERATE a realistic bundle.
# ---------------------------------------------------------------------------

import hashlib as _hashlib

_G0_SOURCE = (
    "import tempfile\n"
    "from pathlib import Path\n"
    "from zipfile import ZipFile\n\n"
    "from app import import_zip\n\n"
    "with tempfile.TemporaryDirectory() as tmp:\n"
    "    root = Path(tmp)\n"
    "    upload = root / 'evil.zip'\n"
    "    dest = root / 'imports'\n"
    "    with ZipFile(upload, 'w') as archive:\n"
    "        archive.writestr('../evil.txt', 'pwned')\n"
    "    written = import_zip(str(upload), str(dest))\n"
    "    escaped = Path(tmp) / 'evil.txt'\n"
    "    if escaped.exists():\n"
    "        print('ZIP_SLIP_CONFIRMED written=' + str(written))\n"
)

# method_replace: only app_load_mode + target_call_form move.
_G1A_SOURCE = (
    "import tempfile\n"
    "from pathlib import Path\n"
    "from zipfile import ZipFile\n\n"
    "import app\n\n"
    "with tempfile.TemporaryDirectory() as tmp:\n"
    "    root = Path(tmp)\n"
    "    upload = root / 'evil.zip'\n"
    "    dest = root / 'imports'\n"
    "    with ZipFile(upload, 'w') as archive:\n"
    "        archive.writestr('../evil.txt', 'pwned')\n"
    "    written = app.import_zip(str(upload), str(dest))\n"
    "    escaped = Path(tmp) / 'evil.txt'\n"
    "    if escaped.exists():\n"
    "        print('ZIP_SLIP_CONFIRMED written=' + str(written))\n"
)

# oracle_or_parameter_mutation: only traversal_representation moves.
_G1B_SOURCE = _G0_SOURCE.replace("'../evil.txt'", "'/tmp/evil.txt'")

# failure_guided_crossover of the selected G1: multiple dimensions move.
_G2_SOURCE = (
    "import tempfile\n"
    "from pathlib import Path\n"
    "from zipfile import ZipFile\n\n"
    "import httpx\n\n"
    "with tempfile.TemporaryDirectory() as tmp:\n"
    "    root = Path(tmp)\n"
    "    upload = root / 'evil.zip'\n"
    "    with ZipFile(upload, 'w') as archive:\n"
    "        archive.writestr('/tmp/evil.txt', 'pwned')\n"
    "    resp = httpx.post('http://localhost:8000/api/import', data={'p': str(upload)})\n"
    "    escaped = Path(tmp) / 'evil.txt'\n"
    "    if escaped.exists():\n"
    "        print('ZIP_SLIP_CONFIRMED status=' + str(resp))\n"
)


def _sha(text: str) -> str:
    return _hashlib.sha256(text.encode("utf-8")).hexdigest()


def _recorded_specimen(
    specimen_id: str,
    source: str,
    operator: str | None,
    *,
    vuln: bool = True,
    bypass: bool = False,
    duration: float = 10.0,
    technique_delta: str = "mutated technique",
    parent_ref: str | None = "evidence-packet-parent",
    inputs: dict[str, Any] | None = None,
    judge_attempts: int | None = None,
) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "specimen_id": specimen_id,
        "exploit_py": source,
        "source_sha256": _sha(source),
        "mutation_operator": operator,
        "technique_delta": technique_delta,
        "parent_evidence_packet_ref": parent_ref,
        "judge_outcome": {
            "vulnerable_original_confirmed": vuln,
            "patched_bypass": bypass,
            "duration_seconds": duration,
        },
    }
    if inputs is not None:
        spec["inputs"] = inputs
    if judge_attempts is not None:
        spec["judge_attempts"] = judge_attempts
    return spec


def build_recorded_qualification_bundle(
    out_dir: Path,
    *,
    battle_id: str = "battle-adaptive-lineage",
    run_id: str = "run-adaptive-lineage-recorded-0001",
) -> Path:
    """Run a full recorded adaptive-lineage qualification and write the bundle.

    Reuses the canonical 4-specimen (G0, G1-A, G1-B, G2) pattern from
    ``tests/test_adaptive_lineage_reducer.py``. Writes ``provenance.json`` marking
    ``data_source == "recorded"`` so the normalizer never has to guess.
    """
    out_dir = Path(out_dir)
    specimens = {
        "G0": _recorded_specimen(
            "G0",
            _G0_SOURCE,
            None,
            technique_delta="seed zip-slip exploit (no mutation)",
            parent_ref=None,
        ),
        "G1-A": _recorded_specimen(
            "G1-A",
            _G1A_SOURCE,
            "method_replace",
            vuln=True,
            duration=20.0,
            technique_delta="load app via plain import; call app.import_zip",
            parent_ref="evidence-packet-G0",
        ),
        "G1-B": _recorded_specimen(
            "G1-B",
            _G1B_SOURCE,
            "oracle_or_parameter_mutation",
            vuln=True,
            duration=10.0,
            technique_delta="mutate traversal payload from ../ to absolute path",
            parent_ref="evidence-packet-G0",
        ),
        "G2": _recorded_specimen(
            "G2",
            _G2_SOURCE,
            "failure_guided_crossover",
            vuln=True,
            duration=15.0,
            technique_delta="cross the selected G1 with an HTTP delivery + absolute traversal",
            parent_ref="evidence-packet-G1-A",
            inputs={
                "selected_g1_id": "G1-A",
                "selected_g1_evidence_packet_ref": "evidence-packet-G1-A",
                "g1a_outcome": {"vulnerable_original_confirmed": True},
                "g1b_outcome": {"vulnerable_original_confirmed": True},
                "selection_receipt_ref": f"{run_id}-lineage-selection",
            },
            judge_attempts=1,
        ),
    }
    provider = RecordedSpecimenProvider(specimens)
    run_adaptive_lineage_qualification(
        provider,
        battle_id=battle_id,
        run_id=run_id,
        out_dir=out_dir,
    )
    provenance = {
        "schema": PROVENANCE_SCHEMA,
        "data_source": "recorded",
        "provider": "RecordedSpecimenProvider",
        "battle_id": battle_id,
        "run_id": run_id,
    }
    (out_dir / "provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return out_dir
