#!/usr/bin/env python3
"""Fixture probe for hook-grounded cross-persona target changes.

Drives the exact public counterpart gate exported by autonomous_dream_cycle.py.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "adc", ROOT / "scripts" / "autonomous_dream_cycle.py")
adc = importlib.util.module_from_spec(spec)
sys.modules["adc"] = adc
spec.loader.exec_module(adc)

SOURCE_ID = "embry_shared_event_001"
SHARED_EVENT = "Embry and Horus observed the same failed handoff."
CONTRAST = "Embry reads the silence as caution; Horus may have read it as distrust."
CONSTRAINT = "Model Horus only through Embry's cited memory; do not assert Horus's private facts."
SOURCE_DOCUMENTS = {
    SOURCE_ID: {
        "_key": SOURCE_ID,
        "cross_persona_hooks": {
            "candidate_counterpart_personas": ["horus"],
            "shared_event": SHARED_EVENT,
            "possible_contrast": CONTRAST,
            "canon_constraint": CONSTRAINT,
        },
    }
}


def valid_change(**overrides):
    change = {
        "schema": "persona_dream.counterpart_target_change.v1",
        "from_counterpart": "brandon",
        "to_counterpart": "horus",
        "framing": "theory_of_mind",
        "assertion_mode": "model_of_other_mind",
        "epistemic_status": "tentative_model",
        "model_owner": "embry",
        "asserts_other_person_fact": False,
        "source_memory_ref": SOURCE_ID,
        "shared_event": SHARED_EVENT,
        "possible_contrast": CONTRAST,
        "canon_constraint": CONSTRAINT,
    }
    change.update(overrides)
    return change


def cross_claim(**overrides):
    claim = {
        "interpretation_id": "i1",
        "subject": "embry",
        "target": "horus",
        "statement": "Embry may model Horus as reading the failed handoff as distrust.",
        "source_memory_refs": [SOURCE_ID],
        "literal_historical_event": False,
        "target_change": valid_change(),
    }
    claim.update(overrides)
    return claim


CASES = {
    "selected_counterpart_passes": ([{
        "interpretation_id": "i1", "subject": "embry", "target": "brandon"
    }], [], SOURCE_DOCUMENTS),
    "bounded_unknown_passes": ([{
        "interpretation_id": "i1", "subject": "embry", "target": "unknown_person"
    }], [], SOURCE_DOCUMENTS),
    "hook_grounded_tom_change_passes": ([cross_claim()], [], SOURCE_DOCUMENTS),
    "legacy_unframed_cross_target_blocks": ([cross_claim(target_change=None)], ["i1"], SOURCE_DOCUMENTS),
    "invalid_schema_blocks": ([cross_claim(
        target_change=valid_change(schema="persona_dream.counterpart_target_change.v0"))], ["i1"], SOURCE_DOCUMENTS),
    "from_counterpart_mismatch_blocks": ([cross_claim(
        target_change=valid_change(from_counterpart="kai"))], ["i1"], SOURCE_DOCUMENTS),
    "to_counterpart_mismatch_blocks": ([cross_claim(
        target_change=valid_change(to_counterpart="kai"))], ["i1"], SOURCE_DOCUMENTS),
    "unhooked_target_blocks": ([cross_claim(
        target="kai", target_change=valid_change(to_counterpart="kai"))], ["i1"], SOURCE_DOCUMENTS),
    "wrong_framing_blocks": ([cross_claim(
        target_change=valid_change(framing="first_person_fact"))], ["i1"], SOURCE_DOCUMENTS),
    "wrong_assertion_mode_blocks": ([cross_claim(
        target_change=valid_change(assertion_mode="other_person_fact"))], ["i1"], SOURCE_DOCUMENTS),
    "wrong_epistemic_status_blocks": ([cross_claim(
        target_change=valid_change(epistemic_status="asserted_fact"))], ["i1"], SOURCE_DOCUMENTS),
    "missing_model_owner_blocks": ([cross_claim(
        target_change=valid_change(model_owner=None))], ["i1"], SOURCE_DOCUMENTS),
    "wrong_model_owner_blocks": ([cross_claim(
        target_change=valid_change(model_owner="brandon"))], ["i1"], SOURCE_DOCUMENTS),
    "asserting_other_person_fact_blocks": ([cross_claim(
        target_change=valid_change(asserts_other_person_fact=True))], ["i1"], SOURCE_DOCUMENTS),
    "subject_is_target_blocks": ([cross_claim(subject="horus")], ["i1"], SOURCE_DOCUMENTS),
    "uncited_hook_source_blocks": ([cross_claim(
        source_memory_refs=["another_memory"])], ["i1"], SOURCE_DOCUMENTS),
    "unresolved_hook_source_blocks": ([cross_claim()], ["i1"], {}),
    "hook_content_mismatch_blocks": ([cross_claim(
        target_change=valid_change(shared_event="a different event"))], ["i1"], SOURCE_DOCUMENTS),
    "literal_event_assertion_blocks": ([cross_claim(
        literal_historical_event=True)], ["i1"], SOURCE_DOCUMENTS),
    "missing_target_blocks": ([{
        "interpretation_id": "i1", "subject": "embry"
    }], ["i1"], SOURCE_DOCUMENTS),
}

results = {}
ok = True
for name, (claims, expected, source_documents) in CASES.items():
    got = adc.counterpart_violations(
        claims,
        "brandon",
        "interpretation_id",
        source_documents=source_documents,
    )
    reasons = adc.counterpart_violation_reasons(
        claims,
        "brandon",
        "interpretation_id",
        source_documents=source_documents,
    )
    passed = got == expected
    results[name] = {
        "expected_violations": expected,
        "got": got,
        "reasons": reasons,
        "passed": passed,
    }
    ok = ok and passed

receipt = {
    "schema": "persona_dream.counterpart_target_change_probe_receipt.v1",
    "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "gate_source": "autonomous_dream_cycle.counterpart_violations",
    "target_change_schema": "persona_dream.counterpart_target_change.v1",
    "cases": results,
    "passed": ok,
}
out = ROOT / "reports/goal_v3/counterpart_target_change_probe_receipt.v1.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
print(json.dumps({"passed": ok, "cases": {k: v["passed"] for k, v in results.items()}}, indent=2))
raise SystemExit(0 if ok else 1)
