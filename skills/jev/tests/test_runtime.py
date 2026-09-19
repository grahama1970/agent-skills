"""Offline contracts; fixture transports do NOT prove live semantic quality."""
from __future__ import annotations
import asyncio
import copy
import json
import subprocess
from pathlib import Path
from typing import Literal
import pytest
from jev_runtime import Candidate, Jev, Policy, Request, rank, select, tool
from jev_runtime.core import fingerprint
from jev_runtime.routing import memory_disposition, ModelOption, choose_model

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "contracts/conformance.json").read_text())


def execute(c):
    called = []
    async def transport(body):
        called.append(body)
        return copy.deepcopy(c["response"])
    async def run():
        return await Jev(Policy(**c["policy"]), transport=transport).ask(Request(**c["request"]))
    return asyncio.run(run()), called


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_conformance(case):
    result, calls = execute(case)
    assert result.status == case["status"]
    assert result.confident == case.get("confident", [])
    assert len(calls) == (0 if case["status"] == "blocked" else 1)


def test_typescript_decisions_match_python():
    rows = json.loads(subprocess.check_output(["node", "--experimental-strip-types", "tests/conformance.ts"], cwd=ROOT, text=True))
    for case, row in zip(CASES, rows, strict=True):
        result, _ = execute(case)
        assert row == {"status": result.status, "confident": result.confident,
                       "request_hash": result.request_hash, "policy_hash": result.policy_hash}


def test_rank_keeps_uncertainty_contradiction_and_pinned():
    async def transport(_):
        return {"model":"fixture","answers":{f"c{i}":{"type":"noul","noul":v} for i,v in enumerate([0.999,0.001,0.5,0.001])}}
    async def run():
        return await rank(Jev(Policy(allow_egress=True,data_class="public"),transport=transport), "bug report",
                          [Candidate(id=str(i),description="known failure" if i==0 else "candidate",pinned=i==3) for i in range(4)])
    result=asyncio.run(run())
    assert result.ids == ["0","2","3"] and result.excluded == ["1"] and result.uncertain == ["2"]


def test_empty_no_call():
    async def fail(_):
        raise AssertionError("must not call")
    assert asyncio.run(rank(Jev(transport=fail), "empty", [])).status == "no_match"


def test_timeout_rank_preserves_candidates():
    async def slow(_):
        await asyncio.sleep(5)
    async def run():
        return await rank(Jev(Policy(allow_egress=True,data_class="public",timeout_ms=100),transport=slow), "x",[Candidate(id="a",description="evidence")])
    result=asyncio.run(run())
    assert result.ids==["a"] and result.receipt.reason=="deadline"


def test_unknown_egress_never_calls():
    async def fail(_):
        raise AssertionError("must not call")
    c=CASES[0]
    result=asyncio.run(Jev(transport=fail).ask(Request(**c["request"])))
    assert result.status=="blocked"


def test_decorator_preserves_function_and_validates_arguments():
    calls=[]
    @tool(name="run_tests")
    def run_tests(mode: Literal["focused","full"], repo: str):
        """Run a registered test mode in a known repository."""
        calls.append(mode)
    candidate=run_tests.jev.candidate(mode="focused",repo="demo")
    assert candidate.payload["arguments"]["mode"]=="focused" and not calls
    with pytest.raises(ValueError):
        run_tests.jev.candidate(mode="arbitrary shell",repo="demo")
    with pytest.raises(ValueError):
        run_tests.jev.candidate(mode="full",repo="demo",extra=True)
    run_tests("full","demo")
    assert calls==["full"]


@pytest.mark.parametrize("route,flags,expected",[
    ("ANSWER",{"work_requested":True,"covers_request":True},"continue_agent"),
    ("ANSWER",{"work_requested":False,"covers_request":True},"respond"),
    ("CLARIFY",{"work_requested":True,"human_checkpoint":True},"await_human"),
    ("DRAFT",{"work_requested":True},"blocked"),
    ("NO_MATCH",{"work_requested":True},"continue_agent"),
    ("DEFLECT",{"work_requested":True,"scope_only":True},"continue_agent"),
    ("DEFLECT",{"work_requested":True,"scope_only":True,"policy_denied":True},"blocked"),
    ("ERROR",{"work_requested":True,"dependency_required":True},"blocked"),
    ("garbage",{"work_requested":True},"blocked"),
])
def test_memory_contract(route,flags,expected):
    assert memory_disposition(route,**flags)==expected


def test_model_selection_respects_stale_quota_quality_pin():
    base=dict(capabilities=["code"],qualified=True,authorized=True,available_slots=1,observed_at_ms=0,expires_at_ms=1000,cooldown_until_ms=0,estimated_total_cost=1.0,estimated_latency_ms=10)
    models=[ModelOption(id="cheap",**{**base,"estimated_total_cost":0.0,"available_slots":0}),ModelOption(id="good",**base)]
    options=dict(required=["code"],now_ms=100,max_cost=2,deadline_ms=200)
    assert choose_model(models,**options)=="good"
    assert choose_model(models,**options,pinned="cheap") is None
    assert choose_model(models,**{**options,"now_ms":2000,"deadline_ms":3000}) is None


def test_numeric_bindings_and_mutations():
    assert fingerprint({"x":1})==fingerprint({"x":1.0})
    assert fingerprint({"x":1})!=fingerprint({"x":"1"})
    assert fingerprint({"state":"a","criteria":"x"})!=fingerprint({"state":"a","criteria":"y"})
    with pytest.raises(ValueError): fingerprint(float("nan"))
    with pytest.raises(ValueError): fingerprint(2**54)


def test_cli_gate_no_sdk_and_no_key():
    result=subprocess.run(["python","-m","jev_runtime.cli","gate","--state",'{"safe":true}',"--questions",'{"bad":"CUI//"}'],cwd=ROOT,text=True,capture_output=True)
    assert result.returncode==1 and json.loads(result.stdout)["egress"]=="blocked"
