#!/usr/bin/env python3
"""#1586/#GLM: accepted shame output must not render a prose Status Report footer.

The machine contract is the fenced pi.agent_status.v1 JSON block. Human prose
belongs before it, written by the agent. The extension must not append a second
receipt-heavy Status Report after validation; GLM copied that footer and buried
what was actually done.
"""
import json, os, sys, tempfile
from pathlib import Path

SCHEMA = Path(os.environ.get("SHAME_SCHEMA", str(
    Path(__file__).resolve().parents[1] / "scripts" / "agent_status_schema.py")))
INDEX = Path(os.environ.get("SHAME_EXTENSION_INDEX", str(
    Path(__file__).resolve().parents[3] / "extensions" / "pi" / "lazy-report-shame-shame-shame" / "index.ts")))
sys.path.insert(0, str(SCHEMA.parent))
import agent_status_schema as s  # noqa: E402

checks = []
def check(name, cond):
    checks.append({"name": name, "passed": bool(cond)})

proof_tmp = Path(tempfile.mkstemp(suffix=".txt")[1])
proof_tmp.write_text("proof line\n")
status = {"schema": "pi.agent_status.v1", "goal": "ship the fix",
          "state": "done", "answer": "Fixed: no prose footer after status JSON.",
          "changed": ["extensions/pi/lazy-report-shame-shame-shame/index.ts"],
          "verified": [{"command": f"read {proof_tmp}", "result": "proof line"}],
          "proof": [str(proof_tmp)]}
s.AgentStatus.model_validate(status)
index_text = INDEX.read_text(encoding="utf-8")

check("schema_accepts_plain_answer_field", hasattr(s.AgentStatus, "model_fields") and "plain_answer" in s.AgentStatus.model_fields)
check("accepted_path_does_not_append_status_report_footer", "appendText(event.message.content, line)" not in index_text)
check("accepted_path_does_not_strip_and_rewrite_json", "const strippedContent = stripStatusJson" not in index_text)
check("accepted_continuing_does_not_reset_retry_budget", "if (statusState !== \"continuing\") resetGuardRepairBudget()" in index_text)
check("renderer_function_not_terminal_contract", "never append a model-visible prose" in index_text)

passed = all(c["passed"] for c in checks)
out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/shame-renderer-case.json")
out.write_text(json.dumps({"schema": "shame.status_report_renderer_eval.v2", "mocked": True,
                           "live": False, "passed": passed, "checks": checks}, indent=2) + "\n")
print(json.dumps({"passed": passed, "failing": [c["name"] for c in checks if not c["passed"]]}))
sys.exit(0 if passed else 1)
