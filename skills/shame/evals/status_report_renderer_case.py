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
    # Twin of the extension renderStatusLine (index.ts). Keep in sync.
    # plain_answer is the human verdict lead; answer stays the <=300 headline.
    # verified[].result substrings are validation-only and are NOT displayed.
    lines = []
    if status.get("plain_answer"):
        lines.append(f"Answer: {status['plain_answer']}")
    elif status.get("answer"):
        lines.append(f"Answer: {status['answer']}")
    lines.append("Status Report")
    lines.append(f"- Goal: {status.get('goal','')}")
    lines.append(f"- State: {status.get('state','')}")
    for c in status.get("changed") or []:
        lines.append(f"- Changed: {c}")
    verified = status.get("verified") or []
    if verified:
        lines.append(f"- Verified: {len(verified)} command(s), each backed by a proof file below")
        for v in verified:
            lines.append(f"- Verified: {v.get('command','')} (receipt-backed)")
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

# plain_answer + no-fragment display (operator 2026-09-11):
import tempfile
proof_tmp = Path(tempfile.mkstemp(suffix=".txt")[1])
proof_tmp.write_text("SECTION HEADING FRAGMENT:\nproof body line\n")
plain_status = {"schema": "pi.agent_status.v1", "goal": "ship the fix",
                "state": "done",
                "answer": "done: renderer fixed",
                "plain_answer": ("Fixed. The renderer now leads with this plain verdict, "
                                 "and verified lines no longer dump raw proof substrings."),
                "changed": ["extensions/pi/lazy-report-shame-shame-shame/index.ts"],
                "verified": [{"command": f"read {proof_tmp}", "result": "SECTION HEADING FRAGMENT:"}],
                "proof": [str(proof_tmp)]}
s.AgentStatus.model_validate(plain_status)  # schema must accept plain_answer
rendered2 = render_status(plain_status)
check("plain_answer_accepted_by_schema", True)
check("plain_answer_leads_render", rendered2.startswith("Answer: Fixed. The renderer now leads"))
check("raw_result_fragment_hidden", "SECTION HEADING FRAGMENT:" not in rendered2.split("```json")[0])
check("verified_shows_command_and_backing",
      f"- Verified: read {proof_tmp} (receipt-backed)" in rendered2
      and "1 command(s), each backed by a proof file" in rendered2)
reparsed2 = extract_status_block(rendered2)
s.AgentStatus.model_validate(reparsed2)
check("plain_round_trip_validates", reparsed2["plain_answer"] == plain_status["plain_answer"])

passed = all(c["passed"] for c in checks)
out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/shame-renderer-case.json")
out.write_text(json.dumps({"schema": "shame.status_report_renderer_eval.v1", "mocked": True,
                           "live": False, "passed": passed, "checks": checks}, indent=2) + "\n")
print(json.dumps({"passed": passed, "failing": [c["name"] for c in checks if not c["passed"]]}))
sys.exit(0 if passed else 1)
