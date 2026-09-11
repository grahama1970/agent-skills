#!/usr/bin/env python3
"""#1616 first-ask runtime route: trusted-family bound NeedsAgent handlers.

Deterministic against the real agent_status_schema validator with env-injected
runtime families (the trusted supply the runtime provides):
- openai runtime -> exactly claude-fable-low accepted; other handlers typed-fail
- claude runtime -> exactly gpt-5.5-high accepted
- unsupported family / missing runtime supply -> typed operational failure
- agent-authored family that disagrees with the runtime -> typed failure
"""
import json
import os
import sys
from pathlib import Path

SCHEMA = Path(os.environ.get("SHAME_SCHEMA", str(
    Path(__file__).resolve().parents[1] / "scripts" / "agent_status_schema.py")))
sys.path.insert(0, str(SCHEMA.parent))
import agent_status_schema as s  # noqa: E402

ENV_KEYS = ("LRSSS_PROJECT_AGENT_FAMILY", "LAZY_REPORT_SHAME_PROJECT_AGENT_FAMILY",
            "PI_PROJECT_AGENT_FAMILY", "PI_MODEL", "PI_PROVIDER")
HANDLER_ENV_KEYS = ("LRSSS_AVAILABLE_ASK_HANDLERS", "LAZY_REPORT_SHAME_AVAILABLE_ASK_HANDLERS",
                    "ASK_AVAILABLE_HANDLERS")

checks = []


def check(name, cond):
    checks.append({"name": name, "passed": bool(cond)})


REF = [{
    "receipt_id": "b1",
    "receipt_path": "/tmp/b1.json",
    "expected_schema": "brave.search_result.v1",
    "expected_producer": "brave-search",
    "digest": "sha256:" + "a" * 64,
}]


def attempt(env_provider, payload_family, handler):
    old = {k: os.environ.get(k) for k in ENV_KEYS + HANDLER_ENV_KEYS}
    try:
        for k in ENV_KEYS + HANDLER_ENV_KEYS:
            os.environ.pop(k, None)
        if env_provider is not None:
            os.environ["PI_PROVIDER"] = env_provider
        if env_provider is not None:
            os.environ["ASK_AVAILABLE_HANDLERS"] = "claude-fable-low,gpt-5.5-high"
        try:
            s.NeedsAgent(project_agent_family=payload_family, handler=handler,
                         question="q", parent_refs=REF)
            return None
        except Exception as exc:
            try:
                return str(exc.errors()[0].get("type", exc))[:120]
            except Exception:
                return str(exc)[:120]
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# openai runtime -> claude-fable-low only
check("openai_accepts_claude_fable_low",
      attempt("openai/gpt-x", "openai", "claude-fable-low") is None)
check("openai_rejects_same_family_handler",
      "needs_agent_requires_cross_family_handler" in (attempt("openai/gpt-x", "openai", "gpt-5.5-high") or ""))
# claude runtime -> gpt-5.5-high only
check("claude_accepts_gpt_5_5_high",
      attempt("anthropic/claude-x", "claude", "gpt-5.5-high") is None)
check("claude_rejects_same_family_handler",
      "needs_agent_requires_cross_family_handler" in (attempt("anthropic/claude-x", "claude", "claude-fable-low") or ""))
# agent-authored family disagreeing with runtime -> typed failure
check("payload_family_must_match_runtime",
      "needs_agent_project_family_not_runtime_bound" in (attempt("openai/gpt-x", "claude", "gpt-5.5-high") or ""))
# unsupported runtime family -> typed operational failure
check("unsupported_runtime_family_typed_failure",
      "needs_agent_unsupported_runtime_family" in (attempt("gemini/gemini-x", "openai", "claude-fable-low") or ""))
# missing runtime supply -> typed failure
check("missing_runtime_supply_fails",
      "needs_agent_runtime_family_missing" in (attempt(None, "openai", "claude-fable-low") or ""))

passed = all(c["passed"] for c in checks)
out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/shame-first-ask-route.json")
out.write_text(json.dumps({"schema": "shame.first_ask_route_eval.v1", "mocked": True,
                           "live": False, "passed": passed, "checks": checks}, indent=2) + "\n")
print(json.dumps({"passed": passed, "failing": [c["name"] for c in checks if not c["passed"]]}))
sys.exit(0 if passed else 1)
