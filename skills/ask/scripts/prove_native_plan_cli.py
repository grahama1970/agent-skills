"""Retained read-only Ask -> native Tau CLI -> SciLLM plan proof (#1220 slice)."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys
import re
import time
import uuid

import httpx

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "src"))
from ask.project_plan import validate_project_plan
from ask.project_plan_to_tau import compile_plan_to_tau_spec

parser = argparse.ArgumentParser()
parser.add_argument("mode", choices=["schema", "live", "missing-tools", "reuse"])
parser.add_argument("--out", required=True, type=Path)
parser.add_argument("--watch", action="store_true")
args = parser.parse_args()
args.out.mkdir(parents=True, exist_ok=False)
workspace = args.out / "evidence"
workspace.mkdir()
nonce = uuid.uuid4().hex
(workspace / "nonce.txt").write_text(nonce)
goal = "Independently read and verify a nonce through two native Tau agents."
plan = {
    "schema": "ask.project_plan.v1", "goal": goal,
    "target": {"repo": "grahama1970/agent-skills", "workspace": str(workspace)},
    "deliverables": [{"name": "nonce readback", "acceptance_criteria": ["both nodes read the actual nonce"]}],
    "workstreams": [
        {"id": "inspect", "role": "backend", "prompt": "Use the read tool once to read nonce.txt. Return NONCE=<trimmed file contents>. Do not guess or write files.",
         "allowed_paths": ["nonce.txt"], "allowed_tools": ["read"], "max_turns": 4, "max_tool_calls": 2},
        {"id": "review", "role": "independent_reviewer", "depends_on": ["inspect"],
         "prompt": "Independently use the read tool once to read nonce.txt, even though upstream context contains an answer. Return NONCE=<trimmed file contents>. Do not guess or write files.",
         "allowed_paths": ["nonce.txt"], "allowed_tools": ["read"], "max_turns": 4, "max_tool_calls": 2},
    ],
    "team": {"preset": "fullstack-premium"},
    "execution": {"topology": "sequential", "max_concurrency": 1, "max_retries": 0},
    "unresolved": [],
}
if args.mode == "schema":
    assert validate_project_plan(plan)[0]
    for mutation in [{"max_turns": True}, {"allowed_tools": "read"}, {"surprise": 1}, {"depends_on": True}]:
        bad = copy.deepcopy(plan)
        bad["workstreams"][0].update(mutation)
        ok, errors = validate_project_plan(bad)
        assert not ok and errors, mutation
    spec = compile_plan_to_tau_spec(plan, run_id="native-contract", run_dir=args.out / "compiled")
    reviewer = spec["nodes"][1]["tau_agent"]
    assert reviewer["agent_requirement"]["role"] == "review"
    assert reviewer["allowed_tools"] == ["read"]
    assert spec["goal"]["goal_hash"] == spec["extensions"]["source_plan"]["goal_hash"]
    result = {"status": "PASS", "mocked": True, "live": False, "scope": "plan validation and native requirement emission"}
else:
    if args.mode == "missing-tools":
        plan["workstreams"][0].pop("allowed_tools")
    plan_path = args.out / "plan.json"
    plan_path.write_text(json.dumps(plan, indent=2))
    command = [str(SKILL / "run.sh"), "team-plan", goal, "--plan-file", str(plan_path),
               "--out", str(args.out / "execution"), "--execute", "--live", "--json"]
    if args.mode == "reuse":
        (args.out / "execution/run").mkdir(parents=True)
        (args.out / "execution/dag-spec.json").write_text("preserved-native-spec\n")
        command.remove("--execute")
        command.remove("--live")
    if args.watch:
        command.append("--watch")
    viewer_snapshot = None
    with (args.out / "stdout.log").open("w") as stdout, (args.out / "stderr.log").open("w") as stderr:
        proc = subprocess.Popen(command, cwd=SKILL.parents[1], stdout=stdout, stderr=stderr)
        deadline = time.monotonic() + 1200
        while proc.poll() is None and time.monotonic() < deadline:
            if args.watch and viewer_snapshot is None:
                match = re.search(r"LIVE DAG VIEWER: (http://[^\s]+)", (args.out / "stderr.log").read_text())
                if match:
                    try:
                        response = httpx.get(match.group(1).rstrip("/") + "/api/v1/state", timeout=5)
                        if response.status_code == 200 and response.json().get("schema") == "tau.dag_view_snapshot.v2":
                            viewer_snapshot = response.json()
                            (args.out / "viewer-state-during-run.json").write_text(json.dumps(viewer_snapshot, indent=2))
                    except httpx.HTTPError:
                        pass
            time.sleep(0.2)
        assert proc.poll() is not None, "native run exceeded the observation window; inspect its retained run state"
    if args.mode == "reuse":
        response = json.loads((args.out / "stdout.log").read_text())
        assert proc.returncode == 2 and response["status"] == "INVALID_PLAN"
        assert "native run directory already exists" in response["errors"][0]
        assert (args.out / "execution/dag-spec.json").read_text() == "preserved-native-spec\n"
        result = {"status": "PASS", "mocked": True, "live": False,
                  "scope": "real preview preserves fixture-backed existing native evidence"}
        (args.out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result))
        raise SystemExit(0)
    if args.mode == "missing-tools":
        response = json.loads((args.out / "stdout.log").read_text())
        assert proc.returncode == 1 and response["status"] == "EXECUTION_BLOCKED"
        assert "requires explicit allowed_tools" in response["errors"][0]
        assert not (args.out / "execution/run").exists()
        result = {"status": "PASS", "mocked": False, "live": False,
                  "scope": "real Ask CLI refuses an undeclared tool requirement before Tau/provider launch"}
        (args.out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result))
        raise SystemExit(0)
    assert proc.returncode == 0, (args.out / "stderr.log").read_text()[-2000:]
    summary = json.loads((args.out / "execution/execution-summary.json").read_text())
    native = json.loads(Path(summary["native_receipt"]).read_text())
    assert native["status"] == "PASS" and summary["exit_code"] == 0
    # Tau's read API must run in Tau's interpreter too (currently Python 3.14).
    readback = '''import json,sys
from pathlib import Path
from tau_coding.dag_runtime.agent_events import load_agent_events
from tau_coding.dag_runtime.run_store import SqliteDagRunStore
r=json.loads(Path(sys.argv[1]).read_text()); nonce=sys.argv[2]
store=SqliteDagRunStore(Path(r["run_store_path"])); nodes=[]
try:
 for n in r["nodes"]:
  a=n["accepted_output"]
  assert nonce in a["final_text"] and a["settlement"]["state"]=="completed"
  assert n["provider_invoked"]
  events=[e["agent_event"] for e in load_agent_events(store,r["scheduler_run_id"],node_id=n["node_id"])]
  assert any(e["event_type"]=="tool_effect_recorded" and nonce in json.dumps(e["payload"]) for e in events)
  nodes.append({"node_id":n["node_id"],"profile":n["transport_profile"]["profile_id"],"nonce_in_tool_effect":True})
finally: store.close()
assert len({n["profile"] for n in nodes})==2
print(json.dumps(nodes))'''
    nodes = json.loads(subprocess.check_output(["uv", "run", "--project", "/home/graham/workspace/experiments/tau", "python", "-c", readback, summary["native_receipt"], nonce], text=True))
    if args.watch:
        assert viewer_snapshot is not None, "no valid native viewer snapshot observed during execution"
    result = {"status": "PASS", "mocked": False, "live": True, "nodes": nodes,
              "viewer_state_observed_during_run": viewer_snapshot is not None,
              "command": command, "native_receipt": summary["native_receipt"],
              "scope": "two read-only native agents through the actual Ask and Tau CLIs; no authoring or watchdog closure"}
(args.out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result))
