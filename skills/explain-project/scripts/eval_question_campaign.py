"""Seeded, stratified live cockpit hardening campaign for Explain Project."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import httpx

SEED = 20260919
CATEGORIES = (
    "direct", "paraphrase", "source", "flow", "failure", "proof",
    "debugger", "diagram", "scale", "tradeoff", "ambiguity", "noise",
)
NOISE = (
    "What is the weather in Quito tomorrow?", "Write a sonnet about apricots.",
    "How many moons orbit Neptune?", "Translate bonjour into Japanese.",
    "Recommend a pasta sauce for dinner.", "Who won the 1978 chess championship?",
    "Explain photosynthesis to a six year old.", "Find a hotel near the Louvre.",
    "What is the tallest waterfall in Peru?", "Compose a jazz chord progression.",
    "How do migratory birds navigate?", "Calculate the area of a regular hexagon.",
    "Which tea pairs with lemon cake?", "Summarize the history of paper making.",
    "Name five constellations visible in winter.",
)


def build_bank(explainers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bank: list[dict[str, Any]] = []
    for category in CATEGORIES:
        for index in range(15):
            row = explainers[index % len(explainers)]
            other = explainers[(index + 1) % len(explainers)]
            title, question = row["title"], row["question"]
            templates = {
                "direct": question,
                "paraphrase": f"Explain {title} in plain English. {question}",
                "source": f"Which source code implements {title}, and where should I start reading?",
                "flow": f"Walk through {title} step by step from input to result.",
                "failure": f"What fails first in {title}, and how is that failure contained?",
                "proof": f"What evidence proves {title}, and what remains deliberately unproven?",
                "debugger": f"Where would you set a breakpoint to inspect {title} at runtime?",
                "diagram": f"Which architecture diagram nodes explain {title}, in execution order?",
                "scale": f"What breaks first at scale in {title}, and which bound controls it?",
                "tradeoff": f"What tradeoff did you make in {title}, and why was it acceptable?",
                "ambiguity": f"Compare {title} with {other['title']}; which explainer answers this?",
                "noise": NOISE[index],
            }
            bank.append({
                "id": f"{category}-{index:02d}",
                "category": category,
                "question": templates[category],
                "expected_feature": None if category in {"ambiguity", "noise"} else row["feature_id"],
                "base_feature": row["feature_id"],
            })
    return bank


def select(bank: list[dict[str, Any]], seed: int, per_category: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in bank:
        grouped[case["category"]].append(case)
    return [case for category in CATEGORIES for case in rng.sample(grouped[category], per_category)]


def post_question(client: httpx.Client, case: dict[str, Any], trial: int) -> dict[str, Any]:
    bootstrap = client.get("/api/cockpit/bootstrap").json()
    revision = bootstrap["state"]["revision"]
    started = time.perf_counter()
    response = client.post("/api/cockpit/event", json={
        "schema": "explain_project.cockpit_event.v1",
        "type": "question.manual",
        "event_id": f"campaign-{case['id']}-t{trial}-{revision}",
        "expected_revision": revision,
        "payload": {"text": case["question"]},
    })
    response.raise_for_status()
    payload = response.json()
    state = payload.get("state", payload)
    route = state.get("route") or {}
    source = state.get("source") or {}
    diagram = state.get("diagram") or {}
    return {
        "trial": trial,
        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        "revision": state.get("revision"),
        "route_status": route.get("status"),
        "matched_feature": route.get("matched_feature"),
        "candidates": route.get("candidates") or [],
        "scores": route.get("scores") or {},
        "step_id": (state.get("selection") or {}).get("step_id"),
        "source": (source.get("location") or {}),
        "debugger_target": (state.get("debugger") or {}).get("target"),
        "diagram_source": diagram.get("source_path"),
        "diagram_nodes": diagram.get("active_node_ids") or [],
        "answer_status": (state.get("teleprompter") or {}).get("answer_status"),
        "question_intent": (state.get("teleprompter") or {}).get("question_intent"),
        "narration": str((state.get("teleprompter") or {}).get("spoken") or "").strip(),
    }


def board_node_ids(repo: Path, source: str | None) -> set[str]:
    if not source:
        return set()
    data = json.loads((repo / source).read_text(encoding="utf-8"))
    return {
        str(item["id"])
        for item in data.get("elements", [])
        if item.get("type") not in {"text", "arrow"} and not item.get("isDeleted")
    }


def cockpit_event(client: httpx.Client, event_type: str, revision: int, case_id: str) -> dict[str, Any]:
    response = client.post("/api/cockpit/event", json={
        "schema": "explain_project.cockpit_event.v1",
        "type": event_type,
        "event_id": f"campaign-{event_type}-{case_id}-{revision}",
        "expected_revision": revision,
        "payload": {},
    })
    response.raise_for_status()
    return response.json().get("state", response.json())


def exercise_bridge(client: httpx.Client, repo: Path, output: Path, case: dict[str, Any], trial: dict[str, Any]) -> dict[str, Any]:
    if trial["route_status"] != "MATCHED":
        return {"source_reveal": "NOT_APPLICABLE", "debugger_prepare": "NOT_APPLICABLE"}
    revision = int(trial["revision"])
    cockpit_event(client, "source.reveal.request", revision, case["id"])
    command = [
        str(Path(__file__).resolve().parents[1] / "run.sh"), "bridge",
        "--repo", str(repo), "--base-url", str(client.base_url),
        "--out-dir", str(output / case["id"] / "source"), "--execute",
    ]
    source_run = subprocess.run(command, capture_output=True, text=True, timeout=180, check=True)
    source_result = json.loads(source_run.stdout[source_run.stdout.index("{"):])
    result = {"source_reveal": source_result.get("receipt") or source_result}
    current = client.get("/api/cockpit/bootstrap").json()["state"]
    debugger_needed = trial["question_intent"] == "debugger"
    if debugger_needed and trial["debugger_target"]:
        cockpit_event(client, "debugger.prepare.request", int(current["revision"]), case["id"])
        debug_command = command.copy()
        debug_command[debug_command.index(str(output / case["id"] / "source"))] = str(output / case["id"] / "debugger")
        debug_run = subprocess.run(debug_command, capture_output=True, text=True, timeout=180, check=True)
        debug_result = json.loads(debug_run.stdout[debug_run.stdout.index("{"):])
        result["debugger_prepare"] = debug_result.get("receipt") or debug_result
    else:
        result["debugger_prepare"] = "MISSING_TARGET" if debugger_needed else "NOT_REQUIRED"
    return result


def speak(text: str, case_id: str) -> dict[str, Any]:
    command = [
        str(Path(__file__).resolve().parents[2] / "chatterbox-speak" / "run.sh"),
        "speak", "--voice", "embry", "--text", text[:500],
        "--context", f"Explain Project question campaign {case_id}", "--tone", "calm_precise",
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=180, check=True)
    data = json.loads(result.stdout[result.stdout.index("{"):])
    receipt, wav = Path(data["receipt"]), Path(data["wav"])
    receipt_data = json.loads(receipt.read_text(encoding="utf-8"))
    return {
        "receipt": str(receipt), "wav": str(wav), "wav_bytes": wav.stat().st_size,
        "wav_sha256": hashlib.sha256(wav.read_bytes()).hexdigest(),
        "duration_seconds": data.get("duration_seconds"), "backend": data.get("backend"),
        "receipt_schema": receipt_data.get("schema"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:15174")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--per-category", type=int, default=5)
    parser.add_argument("--trials", type=int, default=2)
    parser.add_argument("--speak", action="store_true")
    parser.add_argument("--exercise-bridges", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    timeout = httpx.Timeout(30.0, connect=3.0)
    with httpx.Client(base_url=args.base_url, timeout=timeout) as client:
        bootstrap = client.get("/api/cockpit/bootstrap").json()
        explainers = bootstrap["explainers"]
        bank = build_bank(explainers)
        selected = select(bank, args.seed, args.per_category)
        (args.output / "question-bank.json").write_text(json.dumps(bank, indent=2) + "\n")
        (args.output / "selection.json").write_text(json.dumps({"seed": args.seed, "cases": selected}, indent=2) + "\n")
        traces = []
        for number, case in enumerate(selected, 1):
            trials = [post_question(client, case, trial) for trial in range(args.trials)]
            stable = len({(t["route_status"], t["matched_feature"], t["step_id"], json.dumps(t["source"], sort_keys=True)) for t in trials}) == 1
            expected = case["expected_feature"]
            expected_ok = (
                trials[0]["route_status"] == "NO_MATCH" if case["category"] == "noise"
                else trials[0]["matched_feature"] == expected if expected else trials[0]["route_status"] in {"MATCHED", "AMBIGUOUS"}
            )
            narration = trials[0]["narration"] if trials[0]["route_status"] == "MATCHED" else (
                "I need you to choose between the matching explainers." if trials[0]["route_status"] == "AMBIGUOUS"
                else "I do not have a source-backed explainer for that question."
            )
            diagram_valid = True
            if trials[0]["route_status"] == "MATCHED":
                if args.repo is None:
                    diagram_valid = bool(trials[0]["diagram_source"] and trials[0]["diagram_nodes"])
                else:
                    diagram_valid = bool(trials[0]["diagram_nodes"]) and set(trials[0]["diagram_nodes"]) <= board_node_ids(args.repo, trials[0]["diagram_source"])
            trace = {
                **case, "trials": trials, "stable": stable, "expected_ok": expected_ok,
                "diagram_binding_valid": diagram_valid,
                "decision_owner": "deterministic_fallback",
                "jev_status": "blocked_missing_api_key",
            }
            if args.exercise_bridges:
                if args.repo is None:
                    raise SystemExit("--exercise-bridges requires --repo")
                trace["bridge"] = exercise_bridge(client, args.repo, args.output / "bridge", case, trials[-1])
            if args.speak:
                trace["chatterbox"] = speak(narration, case["id"])
            traces.append(trace)
            print(f"[{number:02d}/{len(selected)}] {case['id']} {trials[0]['route_status']} stable={stable} expected={expected_ok}", flush=True)
    trace_path = args.output / "traces.jsonl"
    trace_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in traces))
    outcomes = Counter(row["trials"][0]["route_status"] for row in traces)
    failures = [row["id"] for row in traces if not row["stable"] or not row["expected_ok"] or not row["diagram_binding_valid"]]
    summary = {
        "schema": "explain_project.question_campaign.v1", "seed": args.seed,
        "bank_size": len(bank), "selected_count": len(selected), "trials_per_question": args.trials,
        "trial_count": len(selected) * args.trials, "categories": list(CATEGORIES),
        "outcomes": dict(outcomes), "stable_count": sum(row["stable"] for row in traces),
        "expected_count": sum(row["expected_ok"] for row in traces), "failures": failures,
        "chatterbox_receipts": sum("chatterbox" in row for row in traces),
        "diagram_bindings_valid": sum(row["diagram_binding_valid"] for row in traces),
        "source_reveals": sum(isinstance(row.get("bridge", {}).get("source_reveal"), dict) for row in traces),
        "debugger_prepares": sum(isinstance(row.get("bridge", {}).get("debugger_prepare"), dict) for row in traces),
        "jev_status": "blocked_missing_api_key; deterministic typed fallback retained",
        "status": "PASS" if not failures else "NEEDS_ATTENTION",
        "proof_boundary": "Live cockpit routing and optional live Chatterbox rendering; debugger execution and human-perceived audio quality are not claimed.",
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
