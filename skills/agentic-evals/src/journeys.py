"""Requirements-to-journey planning over claims and live discovery (#1629).

Discovery answers what the implementation exposes; requirements answer what the
product must be able to do. This module joins them: every declared requirement
is bound against the QIDs actually observed by `test-interactions discover`,
and a required flow the crawler cannot see stays visible as ``UNBOUND`` instead
of disappearing.

Hard rules:
- UI actions reference QIDs only. Any positional/class/text/XPath selector in a
  requirement fails validation closed. Generated manifest fragments emit only
  ``[data-qid='...']`` selectors.
- Reference integrity is fail-closed: a requirement naming an unknown
  capability claim or seam is a validation error, not a silent skip.
- A discovered control with no requirement linkage is reported as an
  ``unlinked_control``; it never manufactures a capability claim.
- A journey without a failing-capable oracle is ``weak_oracle`` and cannot
  satisfy coverage.
- The plan records sha256 hashes of every input it consumed plus the discovery
  run identity, so a plan can be tied to the exact evidence it was built from.

The planner proposes; it never proves. Binding status is not readiness, and
nothing here can emit PROVEN or READY.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

REQUIREMENTS_SCHEMA = "agentic_evals.requirements.v1"
PLAN_SCHEMA = "agentic_evals.journey_plan.v1"

BOUND = "BOUND"
PARTIALLY_BOUND = "PARTIALLY_BOUND"
UNBOUND = "UNBOUND"
NOT_APPLICABLE = "NOT_APPLICABLE"

# Selector shapes that are never legal in a requirement's UI actions. QID-only
# is the whole contract; these are the fallbacks people reach for (#1628).
_FORBIDDEN_SELECTOR = re.compile(
    r"nth-child|nth-of-type|xpath|//|:contains|\.[A-Za-z_-]+\s*>|^#|^\.", re.IGNORECASE
)

_QID_RE = re.compile(r"^[A-Za-z0-9_:. \-]+$")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path, label: str, errors: list[str]) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"{label}: file not found: {path}")
    except json.JSONDecodeError as exc:
        errors.append(f"{label}: invalid JSON: {exc}")
    return None


def observed_qids(inventory: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Union of interactive QIDs across all observed discovery states."""
    seen: dict[str, dict[str, Any]] = {}
    for state in inventory.get("inventory") or []:
        for el in state.get("interactives") or []:
            qid = el.get("qid") or ""
            if not qid:
                continue
            entry = seen.setdefault(
                qid, {"qid": qid, "tags": set(), "visible": False, "enabled": False}
            )
            entry["tags"].add(el.get("tag") or "")
            entry["visible"] = entry["visible"] or bool(el.get("visible"))
            entry["enabled"] = entry["enabled"] or bool(el.get("enabled"))
    for entry in seen.values():
        entry["tags"] = sorted(t for t in entry["tags"] if t)
    return seen


def validate_requirements(doc: Any, known_claims: set[str], known_seams: set[str]) -> list[str]:
    errors: list[str] = []
    if not isinstance(doc, dict) or doc.get("schema") != REQUIREMENTS_SCHEMA:
        return [f"requirements: schema must be {REQUIREMENTS_SCHEMA!r}"]
    reqs = doc.get("requirements")
    if not isinstance(reqs, list) or not reqs:
        return ["requirements: 'requirements' must be a non-empty list"]
    seen_ids: set[str] = set()
    for i, req in enumerate(reqs):
        where = f"requirements[{i}]"
        if not isinstance(req, dict):
            errors.append(f"{where}: must be an object")
            continue
        rid = req.get("id")
        if not rid or not isinstance(rid, str):
            errors.append(f"{where}: missing string 'id'")
            continue
        where = f"requirement {rid!r}"
        if rid in seen_ids:
            errors.append(f"{where}: duplicate id")
        seen_ids.add(rid)
        if req.get("criticality") not in ("critical", "important", "optional"):
            errors.append(f"{where}: criticality must be critical|important|optional")
        for claim in req.get("capability_claims") or []:
            if claim not in known_claims:
                errors.append(f"{where}: unknown capability claim {claim!r}")
        for seam in req.get("seams") or []:
            if seam not in known_seams:
                errors.append(f"{where}: unknown seam {seam!r}")
        journey = req.get("journey")
        if req.get("applicable", True) is False:
            continue  # NOT_APPLICABLE needs no journey
        if not isinstance(journey, dict):
            errors.append(f"{where}: missing 'journey' object")
            continue
        actions = journey.get("actions")
        if not isinstance(actions, list) or not actions:
            errors.append(f"{where}: journey.actions must be a non-empty list")
            actions = []
        for j, action in enumerate(actions):
            aw = f"{where} action[{j}]"
            if not isinstance(action, dict):
                errors.append(f"{aw}: must be an object")
                continue
            kind = action.get("kind")
            if kind == "ui":
                qid = action.get("qid") or ""
                if not qid:
                    errors.append(f"{aw}: ui action missing 'qid'")
                elif _FORBIDDEN_SELECTOR.search(qid) or not _QID_RE.match(qid):
                    errors.append(
                        f"{aw}: qid {qid!r} looks like a selector fallback; "
                        "QID identity only, no nth-child/class/text/XPath"
                    )
                for key in ("selector", "css", "xpath"):
                    if action.get(key):
                        errors.append(f"{aw}: raw '{key}' is forbidden; use qid")
            elif kind != "command":
                errors.append(f"{aw}: kind must be 'ui' or 'command'")
        oracles = journey.get("oracles")
        if not isinstance(oracles, list):
            errors.append(f"{where}: journey.oracles must be a list")
    return errors


def _bind_requirement(req: dict[str, Any], observed: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if req.get("applicable", True) is False:
        return {"binding_status": NOT_APPLICABLE, "missing": [], "bound_qids": [], "weak_oracle": False}
    journey = req.get("journey") or {}
    ui_qids = [a.get("qid") for a in journey.get("actions") or [] if a.get("kind") == "ui"]
    missing = [q for q in ui_qids if q not in observed]
    bound = [q for q in ui_qids if q in observed]
    if not ui_qids:
        status = BOUND  # command-only journeys bind trivially against discovery
    elif not missing:
        status = BOUND
    elif bound:
        status = PARTIALLY_BOUND
    else:
        status = UNBOUND
    oracles = journey.get("oracles") or []
    failing_capable = any(o.get("failing_capable") for o in oracles if isinstance(o, dict))
    return {
        "binding_status": status,
        "missing": [{"kind": "control", "qid": q} for q in missing],
        "bound_qids": bound,
        "weak_oracle": not failing_capable,
    }


def build_plan(
    *,
    fixture: dict[str, Any],
    requirements_doc: dict[str, Any],
    inventory: dict[str, Any],
    state_graph: Any,
    hashes: dict[str, str],
) -> dict[str, Any]:
    observed = observed_qids(inventory)
    claims = {c.get("id"): c for c in fixture.get("capability_claims") or []}
    reqs = requirements_doc.get("requirements") or []

    journeys: list[dict[str, Any]] = []
    referenced_qids: set[str] = set()
    for req in reqs:
        binding = _bind_requirement(req, observed)
        referenced_qids.update(binding["bound_qids"])
        journey = req.get("journey") or {}
        journeys.append(
            {
                "requirement_id": req["id"],
                "description": req.get("description", ""),
                "criticality": req.get("criticality"),
                "capability_claims": req.get("capability_claims") or [],
                "seams": req.get("seams") or [],
                "preconditions": req.get("preconditions") or [],
                "actions": journey.get("actions") or [],
                "oracles": journey.get("oracles") or [],
                "evidence_required": req.get("evidence_required") or [],
                "binding_status": binding["binding_status"],
                "missing": binding["missing"],
                "weak_oracle": binding["weak_oracle"],
                "coverage_satisfiable": (
                    binding["binding_status"] in (BOUND, NOT_APPLICABLE)
                    and not binding["weak_oracle"]
                )
                or binding["binding_status"] == NOT_APPLICABLE,
            }
        )

    # Claim traceability: every critical claim needs a journey or an explicit
    # missing-journey finding. Requirements pull claims in; claims never pull
    # requirements into existence.
    traced: dict[str, list[str]] = {cid: [] for cid in claims}
    for j in journeys:
        for cid in j["capability_claims"]:
            traced.setdefault(cid, []).append(j["requirement_id"])
    missing_journeys = [
        {
            "capability_claim": cid,
            "criticality": claims[cid].get("criticality"),
            "finding": "no requirement/journey traces to this claim",
        }
        for cid, rids in traced.items()
        if not rids and claims.get(cid, {}).get("criticality") == "critical"
    ]

    unlinked = sorted(q for q in observed if q not in referenced_qids)

    return {
        "schema": PLAN_SCHEMA,
        "source": {
            "hashes": hashes,
            "discovery_run_id": inventory.get("run_id"),
            "discovery_url": inventory.get("url"),
            "state_graph_transitions": len(state_graph) if isinstance(state_graph, list) else 0,
        },
        "journeys": journeys,
        "claim_traceability": traced,
        "missing_journeys": missing_journeys,
        "unlinked_controls": [
            {"qid": q, "note": "observed control with no requirement linkage; no claim manufactured"}
            for q in unlinked
        ],
        "summary": {
            "requirements": len(journeys),
            "bound": sum(1 for j in journeys if j["binding_status"] == BOUND),
            "partially_bound": sum(1 for j in journeys if j["binding_status"] == PARTIALLY_BOUND),
            "unbound": sum(1 for j in journeys if j["binding_status"] == UNBOUND),
            "not_applicable": sum(1 for j in journeys if j["binding_status"] == NOT_APPLICABLE),
            "weak_oracle": sum(1 for j in journeys if j["weak_oracle"]),
            "missing_critical_journeys": len(missing_journeys),
        },
    }


def scaffold_manifest_fragment(plan: dict[str, Any]) -> dict[str, Any]:
    """Candidate test-interactions manifest fragment for BOUND journeys.

    Generated tests are candidates, not proof; the fragment is written for
    human review and never merged into a fixture automatically.
    """
    elements = []
    for j in plan["journeys"]:
        if j["binding_status"] != BOUND:
            continue
        interactions = [
            {"action": a.get("action", "click"), "selector": f"[data-qid='{a['qid']}']"}
            for a in j["actions"]
            if a.get("kind") == "ui"
        ]
        if interactions:
            elements.append({"name": j["requirement_id"], "interactions": interactions})
    return {
        "schema": "test_interactions.manifest_fragment.candidate.v1",
        "note": "candidate only; generated tests are not executed evidence",
        "source_plan_schema": plan["schema"],
        "elements": elements,
    }


def plan_journeys_files(
    *,
    fixture_path: Path,
    requirements_path: Path,
    inventory_path: Path,
    state_graph_path: Path,
    output_path: Path,
    scaffold_output: Path | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Load, validate fail-closed, bind, and write the plan. Returns (plan, errors)."""
    errors: list[str] = []
    fixture = load_json(fixture_path, "fixture", errors)
    requirements_doc = load_json(requirements_path, "requirements", errors)
    inventory = load_json(inventory_path, "inventory", errors)
    state_graph = load_json(state_graph_path, "state-graph", errors)
    if errors:
        return None, errors

    known_claims = {c.get("id") for c in fixture.get("capability_claims") or []}
    known_seams = {s.get("id") for s in fixture.get("seams") or []}
    errors = validate_requirements(requirements_doc, known_claims, known_seams)
    if not isinstance(inventory, dict) or "inventory" not in inventory:
        errors.append("inventory: missing 'inventory' key; not a discovery-inventory.json")
    if errors:
        return None, errors

    hashes = {
        "fixture_sha256": _sha256_file(fixture_path),
        "requirements_sha256": _sha256_file(requirements_path),
        "inventory_sha256": _sha256_file(inventory_path),
        "state_graph_sha256": _sha256_file(state_graph_path),
    }
    plan = build_plan(
        fixture=fixture,
        requirements_doc=requirements_doc,
        inventory=inventory,
        state_graph=state_graph,
        hashes=hashes,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if scaffold_output is not None:
        fragment = scaffold_manifest_fragment(plan)
        scaffold_output.parent.mkdir(parents=True, exist_ok=True)
        scaffold_output.write_text(json.dumps(fragment, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return plan, []
