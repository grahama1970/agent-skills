#!/usr/bin/env python3
"""Offline check: composed pipeline emits sandbox-valid prelude + live ladders."""
from __future__ import annotations
import importlib.util, json
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "cpw", Path(__file__).resolve().parent / "compose_pipeline_workflow.py")
cpw = importlib.util.module_from_spec(spec); spec.loader.exec_module(cpw)
roster = {
  "roles": {
    "research": {"ladder": ["gpt-5.5", "zai-glm"], "rungs": [], "live": ["zai-glm"], "ready": True},
    "synthesis": {"ladder": ["zai-glm"], "rungs": [], "live": ["zai-glm"], "ready": True},
    "code_run": {"ladder": ["zai-glm-flash", "zai-glm"], "rungs": [], "live": [], "ready": False},
  },
  "seats": [{"seat": "webkimi", "ok": True, "consecutive_failures": 0}],
  "ready": False,
}
js = cpw.emit(roster, "/tmp/pkt", "NONCE-1", "test question", allow_degraded=True)
assert "async function" not in js, "sandbox rejects async helpers"
assert "function runWithFallback" in js and "tryRung" in js
assert '{ agent: "worker", model: "zai-glm" }' in js, "live rung baked in"
assert "code_run" in js.splitlines()[1], "roster recorded in header"
assert "DERIVED_FROM" in js and "one-shot --out-dir" in js
assert "research.failed" in js and '"BLOCKED"' in js, "fail-closed stage settling present"
assert "verify_roster" in js and "ping_model_roster.py" in js, "mandatory Stage 0 availability verification embedded"
print(json.dumps({"schema": "ask.compose_pipeline_offline_eval.v1", "status": "PASS",
                  "checked": ["no async helpers", "promise-chain fallback", "live rungs baked",
                              "roster header", "blocked-stage settling"]}, indent=2))

if __name__ == "__main__":
    raise SystemExit(0)
