"""Production-loop adapter: the battle orchestrator's thin caller of the
deterministic campaign-contract evaluator.

WebGPT step 4 boundary:
- Same evaluator entry point as the oai-trial gate (run_contract_campaign);
  the adapter implements no verdict aggregation of its own.
- Authorization (security.target_authorization.v1) is validated BEFORE any
  execution; invalid or missing authorization means ZERO target launches.
- The loop may ADD candidate cases; it can never remove the mandatory suite,
  override expectations, or reinterpret a failed receipt as a pass — those are
  plan-resolution failures, not adapter options.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from .acceptance_floor import validate_acceptance_floor
from .campaign_contract import run_contract_campaign, validate_request
from .invariant_campaign import load_profile

_ADAPTER_PATH = Path(__file__).resolve()
for _candidate in (_ADAPTER_PATH.parents[3] / "skills",):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from common.security_authorization import validate_target_authorization  # noqa: E402

ADAPTER_SCHEMA = "battle.production_adapter_request.v1"


def build_contract_request(adapter_request: dict[str, Any]) -> dict[str, Any]:
    """Turn a production adapter request into a campaign contract request.

    adapter_request keys:
      authorization_manifest: path (required)
      expected_target: canonical target id the authorization must cover (required)
      base_request: the mandatory campaign contract request (required)
      acceptance_floor: optional {bundle_path, case_map} from acceptance-contract;
                        every acceptance case must map to required campaign cases
      candidate_cases: optional list of extra retained case dirs (advisory adds;
                       they appear in lineage only — case admission is plan-level)
    """
    if adapter_request.get("schema") != ADAPTER_SCHEMA:
        raise ValueError(f"adapter request schema must be {ADAPTER_SCHEMA}")
    base = adapter_request["base_request"]
    validate_request(base)
    return dict(base)


def run_production_round(adapter_request: dict[str, Any]) -> dict[str, Any]:
    """Authorization-first contract round. Zero launches without valid auth."""
    auth_path = adapter_request.get("authorization_manifest")
    expected_target = adapter_request.get("expected_target")
    if not auth_path or not expected_target:
        return {"schema": "battle.production_adapter_round.v1",
                "status": "BLOCKED",
                "failure_code": "adapter-authorization-missing",
                "target_launches": 0}
    receipt = validate_target_authorization(
        Path(auth_path),
        expected_target=expected_target,
        requested_action="battle",
        requested_runtime_mode="battle",
    )
    if receipt.get("status") != "PASS":
        return {"schema": "battle.production_adapter_round.v1",
                "status": "BLOCKED",
                "failure_code": "adapter-authorization-invalid",
                "authorization_receipt": receipt,
                "target_launches": 0}
    request = build_contract_request(adapter_request)
    floor_request = adapter_request.get("acceptance_floor")
    floor_receipt = None
    if floor_request is not None:
        if not isinstance(floor_request, dict):
            return {"schema": "battle.production_adapter_round.v1",
                    "status": "BLOCKED",
                    "failure_code": "acceptance-floor-invalid",
                    "authorization_receipt": receipt,
                    "target_launches": 0}
        profile = load_profile(request["profile_path"])
        floor_receipt = validate_acceptance_floor(
            bundle_path=floor_request.get("bundle_path"),
            campaign_profile=profile,
            case_map=floor_request.get("case_map"),
        )
        if floor_receipt["status"] != "PASS":
            return {"schema": "battle.production_adapter_round.v1",
                    "status": "BLOCKED",
                    "failure_code": "acceptance-floor-incomplete",
                    "authorization_receipt": receipt,
                    "acceptance_floor": floor_receipt,
                    "target_launches": 0}
    campaign = run_contract_campaign(request)
    return {"schema": "battle.production_adapter_round.v1",
            "status": campaign["verdict"],
            "authorization_receipt": receipt,
            "acceptance_floor": floor_receipt,
            "target_launches": campaign["aggregation"]["cases_total"],
            "campaign": campaign,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
