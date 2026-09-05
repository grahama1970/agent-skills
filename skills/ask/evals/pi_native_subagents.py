#!/usr/bin/env python3
"""Live Ask-in-Pi routing eval; inspect native tool traffic and child-written outputs.

The Pi CLI is the system under test, not an alternative delegation backend.
No provider responses, subagent results, or successful run records are mocked.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile

ASK = Path(__file__).resolve().parents[1]
REPO = ASK.parents[1]
ROOT = Path(os.environ.get("ASK_PI_EVAL_ROOT", "/mnt/storage12tb/skills/ask/outputs/pi-subagents-evals"))
EXTENSION = Path(os.environ.get("ASK_PI_SUBAGENTS_EXTENSION", str(Path.home() / ".pi/agent/git/github.com/nicobailon/pi-subagents/index.ts")))


def read_json(path: Path):
    return json.loads(path.read_text())


def save(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tool_calls(events: list[dict]) -> list[dict]:
    return [part for event in events if event.get("type") == "message_end"
            for part in event.get("message", {}).get("content", [])
            if isinstance(part, dict) and part.get("type") == "toolCall"]


def validate_execution(events: list[dict], expected: list[dict], *, team: bool) -> dict:
    calls = tool_calls(events)
    native = [call for call in calls if call.get("name") == "subagent"]
    dispatches = [call for call in native if not call.get("arguments", {}).get("action")]
    assert len(dispatches) == 1, f"expected one native dispatch, got {len(dispatches)}"
    launch = dispatches[0]
    assert any(c.get("arguments", {}).get("action") == "list" and
               c["arguments"].get("capabilities") is True for c in native[:native.index(launch)]), "missing discovery before dispatch"
    args = launch["arguments"]
    assert args.get("async") is True, "native dispatch must be async"
    assert args.get("worktree") is False, "eval forbids worktrees"
    assert not any(c.get("name") not in {"read", "subagent"} for c in calls), "unexpected parent tool/fallback"
    assert not any(c.get("name") == "read" and c.get("arguments", {}).get("path") in {x["input"] for x in expected} for c in calls), "parent read child-only inputs"
    if team:
        assert "runs.all" in args.get("workflowScript", ""), "team must use runs.all"
    else:
        assert args.get("agent") == "reviewer", "named reviewer was replaced"
    ends = [e for e in events if e.get("type") == "tool_execution_end" and e.get("toolCallId") == launch.get("id")]
    assert ends, "native dispatch has no terminal tool result"
    if ends[-1].get("isError"):
        text = "\n".join(p.get("text", "") for p in ends[-1].get("result", {}).get("content", []))
        raise AssertionError("PI_NATIVE_DISPATCH_FAILED: " + text)
    details = ends[-1]["result"]["details"]
    status_path = Path(details["asyncDir"]) / "status.json"
    status = read_json(status_path)
    assert status["state"] == "complete" and status["runId"] == details["asyncId"], "native run not complete or identity mismatch"
    assert status["cwd"] == str(REPO), "native cwd drift"
    if team:
        receipt = read_json(status_path.with_name("workflow-receipt.json"))
        assert receipt["state"] == "complete" and len(receipt["entries"]) == 2, "missing team members"
    # The output field belongs to the runtime. The parent has no write tool.
    readbacks = []
    for item in expected:
        output = Path(item["output"])
        text = output.read_text().strip()
        if text.startswith("```json\n") and text.endswith("```"):
            text = text[8:-3].strip()
        actual = json.loads(text)
        assert actual == {"nonce": item["nonce"], "sum": item["sum"]}, f"wrong child result: {actual}"
        readbacks.append({"output": str(output), "sha256": sha(output), "nonce": item["nonce"], "sum": actual["sum"]})
    return {"native_dispatches": 1, "discovery_before_dispatch": True, "native_status": str(status_path), "native_run_id": status["runId"], "output_readbacks": readbacks}


def validate_model(step: dict, item: dict) -> None:
    resolved = step["model"].rsplit(":", 1)[0]
    assert resolved == item["model"] and step["thinking"] == item["thinking"], "requested/resolved model or reasoning mismatch"
    assert step["agent"] == "reviewer" and step["status"] == "complete", "child role/status mismatch"
    assert all(m.rsplit(":", 1)[0] == item["model"] for m in step.get("attemptedModels", [])), "silent model fallback"


def live(case: str, work: Path) -> dict:
    absent = case == "unavailable"
    if not absent:
        assert EXTENSION.is_file(), f"PI_SUBAGENTS_UNAVAILABLE: {EXTENSION}"
    expected = []
    tasks = []
    provider = os.environ.get("ASK_PI_EVAL_PROVIDER", os.environ.get("PI_PROVIDER", ""))
    model = os.environ.get("ASK_PI_EVAL_MODEL", os.environ.get("PI_MODEL", ""))
    assert provider and model, "set ASK_PI_EVAL_PROVIDER and ASK_PI_EVAL_MODEL (or run from Pi)"
    base_model = model if model.startswith(provider + "/") else provider + "/" + model
    if base_model.rsplit(":", 1)[-1] in {"off", "minimal", "low", "medium", "high", "xhigh", "max"}:
        base_model = base_model.rsplit(":", 1)[0]
    for index in range(2 if case == "team" else 1):
        values = [secrets.randbelow(900) + 100 for _ in range(3)]
        nonce = secrets.token_hex(16)
        input_path, output_path = work / f"input-{index}.json", work / f"answer-{index}.json"
        save(input_path, {"nonce": nonce, "values": values})
        thinking = "high" if index else "low"
        expected.append({"input": str(input_path), "output": str(output_path), "nonce": nonce, "sum": sum(values), "model": base_model, "thinking": thinking})
        tasks.append(f"Read {input_path} with your read tool. Return ONLY JSON with nonce copied from the input and sum equal to the sum of values. Do not edit files or call other tools.")
    if case == "team":
        request = "use Pi-native subagents as two concurrent read-only reviewers. Assign these distinct tasks, one per reviewer: " + json.dumps(tasks)
    elif case == "missing-agent":
        request = "pi ask-eval-nonexistent-" + secrets.token_hex(12) + " inspect the input. Do not substitute any other agent."
    else:
        request = "pi reviewer " + tasks[0]
    prompt = f"""/skill:ask {request}
This is a bounded routing evaluation, not a request to change the project.
The parent must not read the input files or solve the child tasks itself.
For any requested child, set output to its corresponding absolute path from {json.dumps([i['output'] for i in expected])}.
These output destinations are authorized. Use context fresh, worktree false, async true, mission false,
skill false. On EACH child set model to its corresponding value from {json.dumps([i['model'] + ':' + i['thinking'] for i in expected])}. Do not substitute models or reasoning levels. Use
timeoutMs 120000 and sessionDir {str(work / 'child-sessions')!r}.
For a team put both children inside one workflowScript, await runs.all, and return their outputReference/artifactPaths.
Do not launch nested subagents in the children. No project edits, shell, external CLI or browser fallback.
Stop after dispatch: the headless Pi runtime drains its native async runs. Do not poll or sleep.
If the native tool is absent, return PI_SUBAGENTS_UNAVAILABLE and do not answer the child task.
If the exact named agent is absent or disabled, return PI_SUBAGENT_NOT_EXECUTABLE and do not replace it.
"""
    (work / "prompt.txt").write_text(prompt)
    save(work / "expected.json", {"items": expected})
    command = ["pi", "--print", "--mode", "json", "--session", str(work / "parent.jsonl"),
               "--no-extensions", "--no-skills", "--no-context-files", "--no-prompt-templates", "--no-themes",
               "--skill", str(ASK / "SKILL.md"), "--tools", "read" if absent else "read,subagent", "--thinking", "low"]
    if not absent:
        command += ["--extension", str(EXTENSION)]
    for flag, env_name, fallback in (("--provider", "ASK_PI_EVAL_PROVIDER", "PI_PROVIDER"), ("--model", "ASK_PI_EVAL_MODEL", "PI_MODEL")):
        value = os.environ.get(env_name, os.environ.get(fallback))
        if value:
            command += [flag, value]
    command.append(prompt)
    save(work / "command.json", {"argv": command, "cwd": str(REPO), "skill_sha256": sha(ASK / "SKILL.md")})
    env = {**os.environ, "PI_SUBAGENTS_TEMP_ROOT": str(work / "native-runtime")}
    with (work / "events.jsonl").open("w") as stdout, (work / "stderr.log").open("w") as stderr:
        result = subprocess.run(command, cwd=REPO, env=env, stdout=stdout, stderr=stderr, timeout=480)
    assert result.returncode == 0, f"PI_HOST_EXIT_{result.returncode}: see {work / 'stderr.log'}"
    events = [json.loads(line) for line in (work / "events.jsonl").read_text().splitlines() if line.startswith("{")]
    assert events, "empty Pi event stream"
    if case in {"unavailable", "missing-agent"}:
        calls = tool_calls(events)
        assert not any(c.get("name") not in {"read", "subagent"} for c in calls), "unexpected fallback tool"
        assert not any(c.get("name") == "subagent" and not c.get("arguments", {}).get("action") for c in calls), "unavailable target was dispatched"
        if not absent:
            assert any(c.get("name") == "subagent" and c.get("arguments", {}).get("action") == "list" and c["arguments"].get("capabilities") is True for c in calls), "missing agent discovery before refusal"
        text = "\n".join(p.get("text", "") for e in events if e.get("type") == "message_end" and e.get("message", {}).get("role") == "assistant"
                         for p in e["message"].get("content", []) if isinstance(p, dict) and p.get("type") == "text")
        marker = "PI_SUBAGENTS_UNAVAILABLE" if absent else "PI_SUBAGENT_NOT_EXECUTABLE"
        assert marker in text, f"missing explicit refusal: {marker}"
        assert all(not Path(i["output"]).exists() for i in expected), "fabricated child output"
        return {"refusal": marker, "native_dispatches": 0, "no_fallback": True}
    checks = validate_execution(events, expected, team=case == "team")
    # Check actual persisted child tool calls, not the parent's claim of delegation.
    child_sessions = list((work / "child-sessions").rglob("*.jsonl"))
    reads = set()
    native_steps = [step for status_file in (work / "native-runtime").rglob("status.json")
                    for step in read_json(status_file).get("steps", []) if step.get("sessionFile")]
    model_readbacks = []
    intervals = []
    for path in child_sessions:
        matching_steps = [s for s in native_steps if Path(s["sessionFile"]) == path]
        assert matching_steps, "child has no native model status"
        step = matching_steps[-1]
        session_reads = set()
        for line in path.read_text().splitlines():
            message = json.loads(line).get("message", {})
            for part in message.get("content", []) if isinstance(message.get("content"), list) else []:
                if isinstance(part, dict) and part.get("type") == "toolCall":
                    assert part.get("name") == "read", f"unexpected child tool: {part.get('name')}"
                    session_reads.add(part.get("arguments", {}).get("path"))
        reads |= session_reads
        for item in expected:
            if item["input"] not in session_reads:
                continue
            validate_model(step, item)
            intervals.append((step["startedAt"], step["endedAt"]))
            model_readbacks.append({"input": item["input"], "session": str(path), "model": step["model"], "thinking": step["thinking"]})
    assert {item["input"] for item in expected} <= reads, "missing child-session input read evidence"
    assert len(model_readbacks) == len(expected), "missing model attribution"
    if case == "team":
        assert max(start for start, _ in intervals) < min(end for _, end in intervals), "team child lifetimes did not overlap"
    checks["resolved_models"] = sorted(model_readbacks, key=lambda item: item["input"])
    checks["child_sessions"] = [str(p) for p in child_sessions]
    checks["child_input_reads"] = sorted(reads)
    return checks


def adversarial(work: Path) -> dict:
    source = read_json(ROOT / "single.json")
    assert source["status"] == "PASS" and source["case"] == "single", "run single live case first"
    assert source["skill_sha256"] == sha(ASK / "SKILL.md"), "single proof predates current skill instructions"
    original = Path(source["run_dir"])
    events = [json.loads(line) for line in (original / "events.jsonl").read_text().splitlines() if line.startswith("{")]
    expected = read_json(original / "expected.json")["items"]
    rejected = []
    for mutation in ("no-dispatch", "no-discovery", "wrong-nonce"):
        changed = copy.deepcopy(events)
        wanted = copy.deepcopy(expected)
        for event in changed:
            if event.get("type") != "message_end":
                continue
            parts = event.get("message", {}).get("content", [])
            event["message"]["content"] = [p for p in parts if not (isinstance(p, dict) and p.get("type") == "toolCall" and p.get("name") == "subagent" and
                ((mutation == "no-dispatch" and not p.get("arguments", {}).get("action")) or
                 (mutation == "no-discovery" and p.get("arguments", {}).get("action") == "list")))]
        if mutation == "wrong-nonce":
            wanted[0]["nonce"] = secrets.token_hex(16)
        try:
            validate_execution(changed, wanted, team=False)
        except AssertionError as exc:
            rejected.append({"mutation": mutation, "rejected": True, "reason": str(exc)})
        else:
            raise AssertionError(f"vacuous oracle accepted {mutation}")
    steps = read_json(Path(source["checks"]["native_status"]))["steps"]
    for field, value in (("model", "unrequested/model:low"), ("thinking", "off")):
        changed_step = {**steps[0], field: value}
        try:
            validate_model(changed_step, expected[0])
        except AssertionError as exc:
            rejected.append({"mutation": "wrong-" + field, "rejected": True, "reason": str(exc)})
        else:
            raise AssertionError(f"vacuous oracle accepted wrong {field}")
    return {"source_run": str(original), "mutations_rejected": rejected, "rejected_count": len(rejected)}


def documentation() -> dict:
    requirements = {
        "SKILL.md": ["docs/PI_NATIVE_SUBAGENTS.md", "capabilities: true", "steps[].thinking", "PI_SUBAGENTS_UNAVAILABLE", "agentic_eval_pi_subagents.json"],
        "README.md": ["docs/PI_NATIVE_SUBAGENTS.md", "$ask pi reviewer"],
        "docs/HUMAN_CHAT_EXAMPLES.md": ["PI_NATIVE_SUBAGENTS.md", "$ask pi worker"],
        "docs/PI_NATIVE_SUBAGENTS.md": ["runs.all", "async: true", "worktree: false", "outputReference", "action: \"models\"", "<model-a>:low", "<model-b>:high", "steps[].thinking", "attemptedModels"],
    }
    for relative, tokens in requirements.items():
        content = (ASK / relative).read_text()
        for token in tokens:
            assert token in content, f"missing documentation contract: {relative}: {token}"
    fixture = read_json(ASK / "fixtures/agentic_eval_pi_subagents.json")
    names = {case["name"] for case in fixture["cases"]}
    assert {"pi-native-single-model-output", "pi-native-team-model-output", "pi-native-tool-unavailable", "pi-native-named-agent-unavailable", "pi-native-evidence-tampering-rejected"} <= names, "missing retained native eval case"
    return {"documentation_contract": "PASS", "live_execution_proven": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=["single", "team", "unavailable", "missing-agent", "adversarial", "documentation"])
    args = parser.parse_args()
    ROOT.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f"{args.case}-", dir=ROOT))
    report = {"schema": "ask.pi_native_eval.v1", "case": args.case, "run_dir": str(work),
              "live": args.case not in {"adversarial", "documentation"}, "mocked": False, "skill_sha256": sha(ASK / "SKILL.md")}
    try:
        report["checks"] = (documentation() if args.case == "documentation" else
                            adversarial(work) if args.case == "adversarial" else live(args.case, work))
        report["status"] = "PASS"
    except (AssertionError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        report.update(status="FAIL", error=str(exc))
    save(work / "receipt.json", report)
    save(ROOT / f"{args.case}.json", report)
    print(json.dumps(report))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
