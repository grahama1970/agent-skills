"""Stopped-failure regression and real Ask preflight observation; no model calls."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
from watchdog import handlers

parser = argparse.ArgumentParser()
parser.add_argument("mode", choices=["boundary", "compile", "captured"])
parser.add_argument("--out", type=Path, required=True)
parser.add_argument("--baseline-ref")
parser.add_argument("--run-dir", type=Path)
args = parser.parse_args()
args.out.mkdir(parents=True, exist_ok=False)
inspect = handlers.inspect_tau_stream
if args.baseline_ref:
    source = subprocess.check_output(["git", "show", args.baseline_ref + ":skills/project-watchdog/scripts/watchdog/handlers.py"], cwd=SKILL)
    module = types.ModuleType("watchdog.stopped_failure_baseline")
    module.__package__ = "watchdog"
    exec(compile(source, "baseline-handlers.py", "exec"), module.__dict__)
    inspect = module.inspect_tau_stream

if args.mode == "boundary":
    ask = args.out / "ask"
    run = ask / "run"
    def put(name, data):
        p = run / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data))
    put("dag.json", {"nodes": [{"id": n} for n in ["creator", "reviewer", "join"]]})
    put("dag-progress.json", {"status": "BLOCKED"})
    for node, status in [("creator", "PASS"), ("reviewer", "NEEDS_ATTENTION"), ("join", "DEGRADED")]:
        put(f"node-artifacts/{node}/node-receipt.json", {"node_id": node, "status": status})
    r = inspect(ask)
    assert r["terminal"] and r["terminal_status"] == "BLOCKED", r
    put("node-artifacts/reviewer/node-receipt.json", {"node_id": "reviewer", "status": "RUNNING"})
    assert not inspect(ask)["terminal"]
    put("node-artifacts/reviewer/node-receipt.json", {"node_id": "wrong-node", "status": "PASS"})
    assert not inspect(ask)["terminal"]
    (run / "node-artifacts/reviewer/node-receipt.json").unlink()
    assert not inspect(ask)["terminal"]
    put("node-artifacts/reviewer/node-receipt.json", {"node_id": "reviewer", "status": "NEEDS_ATTENTION"})
    put("dag-progress.json", {"status": "RUNNING"})
    assert not inspect(ask)["terminal"]
    put("dag-progress.json", {"status": "PASS"})
    r = inspect(ask)
    assert r["terminal"] and r["terminal_status"] == "NEEDS_ATTENTION"
    result = {"status": "PASS", "checks": 6, "mocked": True, "live": False,
              "scope": "complete degraded join and node identity/liveness negatives"}
elif args.mode == "compile":
    ask = args.out / "ask"
    # Match the real repair-task producer, which terminates its text with a newline.
    task = "Pre-dispatch refusal probe for ticket 1605; no execution requested.\n"
    (args.out / "repair-task.md").write_text(task)
    command = [str(SKILL.parent / "ask/run.sh"), "tau-dag", task,
        "--repo", "grahama1970/agent-skills", "--target", "stopped-failure-1605",
        "--immutable-goal", "Observe compile refusal without starting a model.",
        "--dag-template", "single-call", "--handler", "claude-fable-low",
        "--handler-workspace", f"claude-fable-low={SKILL.parents[1]}",
        "--run-output-root", str(ask), "--json"]
    execution = handlers.run_ask_tau_dag_with_stream_monitor(command, cwd=SKILL.parents[1],
        timeout_s=60, ask_run_dir=ask, monitor_path=args.out / "tau-stream-monitor.json", poll_interval_s=0.1)
    assert execution["exit_code"] == 2
    r = inspect(ask)
    assert r["terminal"] and r["terminal_status"] == "BLOCKED", r
    assert r["compile_refusal"]["failure_code"] == "ask_handler_binding_invalid"
    monitor_path = args.out / "tau-stream-monitor.json"
    monitor = json.loads(monitor_path.read_text())
    assert monitor["terminal"] is True
    for key, value in [("process_running", True), ("timed_out", True), ("process_exit_code", 0), ("process_running", 0), ("ask_run_dir", "/wrong-run")]:
        altered = dict(monitor, **{key: value})
        monitor_path.write_text(json.dumps(altered))
        assert not inspect(ask)["terminal"], key
    monitor_path.write_text(json.dumps(monitor))
    (args.out / "repair-task.md").write_text("different task")
    assert not inspect(ask)["terminal"]
    (args.out / "repair-task.md").write_text(task)
    result = {"status": "PASS", "mocked": False, "live": True, "provider_calls": 0,
              "scope": "real installed Ask compiler and watchdog monitor; altered-observation negatives; no model execution",
              "monitor": str(monitor_path), "command": command}
else:
    assert args.run_dir
    r = inspect(args.run_dir)
    assert r["terminal"] and r["terminal_status"] in {"BLOCKED", "DEGRADED", "NEEDS_ATTENTION"}, r
    result = {"status": "PASS", "mocked": False, "live": False,
              "scope": "captured real canary artifact replay", "observation": r}
(args.out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(json.loads((args.out / "result.json").read_text())))
