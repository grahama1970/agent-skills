#!/usr/bin/env python3
"""#1586: deterministic Status Report renderer round-trips through the checker.

The renderer (extension renderStatusLine + this Python twin of the same
projection) is derived ONLY from the validated pi.agent_status.v1 JSON, never
hand-authored prose. Round-trip proof: build a status, validate it with the
real checker schema, render it with the deterministic renderer, and re-extract
the JSON from the rendered fenced block -- the re-parsed status must validate
and preserve state/goal/not_done.next_command anchors.
"""
import json, os, sys
from pathlib import Path

SCHEMA = Path(os.environ.get("SHAME_SCHEMA", str(
    Path(__file__).resolve().parents[1] / "scripts" / "agent_status_schema.py")))
sys.path.insert(0, str(SCHEMA.parent))
import agent_status_schema as s  # noqa: E402


def render_status(status: dict) -> str:
    lines = ["Status Report"]
    lines.append(f"- Goal: {status.get('goal','')}")
    lines.append(f"- State: {status.get('state','')}")
    for c in status.get("changed") or []:
        lines.append(f"- Changed: {c}")
    for nd in status.get("not_done") or []:
        lines.append(f"- Not done: {nd.get('item','')} -> {nd.get('next_command','')}")
    body = "\n".join(lines)
    return f"{body}\n```json\n{json.dumps(status, indent=2, sort_keys=True)}\n```"


def extract_status_block(text: str) -> dict:
    inside, buf = False, []
    for line in text.splitlines():
        if line.strip() == "```json":
            inside, buf = True, []
            continue
        if inside and line.strip() == "```":
            return json.loads("\n".join(buf))
        if inside:
            buf.append(line)
    raise AssertionError("no fenced json block in rendered output")


checks = []


def check(name, cond):
    checks.append({"name": name, "passed": bool(cond)})


status = {"schema": "pi.agent_status.v1", "goal": "close tickets and log results",
          "state": "continuing",
          "changed": ["skills/x: deterministic renderer"],
          "not_done": [{"item": "next ticket", "next_command": "gh issue view 1"}]}
s.AgentStatus.model_validate(status)  # validates against the real checker schema
rendered = render_status(status)
check("renders_status_report_header", rendered.startswith("Status Report"))
check("anchors_present", all(t in rendered for t in ("- Goal:", "- State:", "- Not done:", "```json")))
reparsed = extract_status_block(rendered)
s.AgentStatus.model_validate(reparsed)
check("round_trip_validates", True)
check("round_trip_preserves_anchors",
      reparsed["state"] == "continuing"
      and reparsed["not_done"][0]["next_command"] == "gh issue view 1"
      and reparsed["goal"] == status["goal"])

passed = all(c["passed"] for c in checks)
out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/shame-renderer-case.json")
out.write_text(json.dumps({"schema": "shame.status_report_renderer_eval.v1", "mocked": True,
                           "live": False, "passed": passed, "checks": checks}, indent=2) + "\n")
print(json.dumps({"passed": passed, "failing": [c["name"] for c in checks if not c["passed"]]}))
sys.exit(0 if passed else 1)
