#!/usr/bin/env python3
"""Run the oc-subagent MVP persistence/concurrency proof against OpenCode serve."""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


TURN1_PROMPT = (
    "You are subagent_1. Compute 3 * 6, then add the project-agent previous result, which is 4. "
    "Store the resulting number as your last_result for this session. Return only JSON with keys "
    "subagent_run_id, answer, last_result, used_project_result, where subagent_run_id is "
    '"subagent_1", answer and last_result are the number you computed, and used_project_result is 4.'
)
# Turn 2 states neither the prior value nor the answer. It uses the word "ten" (no digits
# at all) so a correct answer of 32 can only come from session-local recall of last_result,
# not from the prompt text. assert_turn_2_no_leak enforces this at startup.
TURN2_PROMPT = (
    "You are subagent_1. Add ten to your last_result from this same session. Store the new value "
    "as last_result. Return only JSON with keys subagent_run_id, answer, last_result, "
    'persistence_used, where subagent_run_id is "subagent_1", answer and last_result are the new '
    "number, and persistence_used is true."
)
NEGATIVE_CONTROL_PROMPT = TURN2_PROMPT
TURN2_FORBIDDEN_TOKENS = ("22", "18", "4", "32")
SUBAGENT_2_PROMPT = (
    "You are subagent_2. Answer this independent task: What is the capital of France? "
    'Return only JSON: {"subagent_run_id":"subagent_2","answer":"Paris"}.'
)
SUBAGENT_3_PROMPT = (
    "You are subagent_3. Answer this independent task: In simple everyday examples, "
    "what color is most commonly associated with an apple? "
    'Return only JSON: {"subagent_run_id":"subagent_3","answer":"red"}.'
)


class OcSubagentError(RuntimeError):
    pass


PREFLIGHT_PROMPT = 'Return only JSON: {"answer":4}.'
LOCAL_OLLAMA_PREFERENCE = (
    "qwen3:14b",
    "qwen3:8b-nothink",
    "qwen3:8b",
    "qwen3:4b-nothink",
    "qwen3:4b",
    "qwen2.5:14b",
    "qwen2.5-coder:7b",
    "qwen2.5:7b",
    "qwen2.5:3b",
    "qwen2.5:1.5b",
    "qwen2.5:0.5b",
)


def env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip() or default


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def now_ms() -> int:
    return int(time.time() * 1000)


class Observability:
    def __init__(self, artifact_dir: Path, run_id: str, *, heartbeat_interval_s: float) -> None:
        self.artifact_dir = artifact_dir
        self.run_id = run_id
        self.heartbeat_interval_s = max(0.1, heartbeat_interval_s)
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None
        self.session_to_subagent: dict[str, str] = {}
        self.tasks: dict[str, dict[str, Any]] = {}
        self.event_count = 0
        self.heartbeat_count = 0
        for name in ("events.jsonl", "heartbeats.jsonl", "timeline.jsonl"):
            (self.artifact_dir / name).touch()
        self._write_status_locked()

    def _append_jsonl_locked(self, name: str, payload: dict[str, Any]) -> None:
        with (self.artifact_dir / name).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")

    def emit(self, event: str, **fields: Any) -> None:
        with self.lock:
            payload = {
                "schema": "oc-subagent.timeline_event.v1",
                "run_id": self.run_id,
                "ts_ms": now_ms(),
                "event": event,
                **fields,
            }
            self._append_jsonl_locked("timeline.jsonl", payload)
            self._write_status_locked()

    def _write_status_locked(self) -> None:
        write_json(
            self.artifact_dir / "task-status.json",
            {
                "schema": "oc-subagent.task_status.v1",
                "run_id": self.run_id,
                "updated_at_ms": now_ms(),
                "event_count": self.event_count,
                "heartbeat_count": self.heartbeat_count,
                "tasks": self.tasks,
            },
        )

    def register_session(self, subagent_run_id: str, child_session_id: str) -> None:
        with self.lock:
            self.session_to_subagent[child_session_id] = subagent_run_id
            self._append_jsonl_locked(
                "timeline.jsonl",
                {
                    "schema": "oc-subagent.timeline_event.v1",
                    "run_id": self.run_id,
                    "ts_ms": now_ms(),
                    "event": "session_registered",
                    "subagent_run_id": subagent_run_id,
                    "child_session_id": child_session_id,
                },
            )
            self._write_status_locked()

    def start_task(self, dag_node_id: str, subagent_run_id: str, child_session_id: str) -> None:
        started = now_ms()
        with self.lock:
            self.tasks[dag_node_id] = {
                "dag_node_id": dag_node_id,
                "subagent_run_id": subagent_run_id,
                "child_session_id": child_session_id,
                "state": "dispatched",
                "started_at_ms": started,
                "updated_at_ms": started,
                "completed_at_ms": None,
                "elapsed_ms": 0,
                "last_event_id": None,
                "last_event_type": None,
                "last_event_at_ms": None,
                "last_event_age_ms": None,
                "heartbeat_count": 0,
                "answer": None,
                "error": None,
            }
            self._append_jsonl_locked(
                "timeline.jsonl",
                {
                    "schema": "oc-subagent.timeline_event.v1",
                    "run_id": self.run_id,
                    "ts_ms": started,
                    "event": "task_started",
                    "dag_node_id": dag_node_id,
                    "subagent_run_id": subagent_run_id,
                    "child_session_id": child_session_id,
                    "state": "dispatched",
                },
            )
            self._write_status_locked()

    def finish_task(self, dag_node_id: str, *, answer: Any = None, error: str | None = None) -> None:
        finished = now_ms()
        with self.lock:
            task = self.tasks.setdefault(dag_node_id, {"dag_node_id": dag_node_id})
            task["state"] = "validated" if error is None else "failed"
            task["updated_at_ms"] = finished
            task["completed_at_ms"] = finished
            task["elapsed_ms"] = finished - int(task.get("started_at_ms") or finished)
            task["answer"] = answer
            task["error"] = error
            self._append_jsonl_locked(
                "timeline.jsonl",
                {
                    "schema": "oc-subagent.timeline_event.v1",
                    "run_id": self.run_id,
                    "ts_ms": finished,
                    "event": "task_completed" if error is None else "task_failed",
                    "dag_node_id": dag_node_id,
                    "state": task["state"],
                    "answer": answer,
                    "error": error,
                },
            )
            self._write_status_locked()

    def task_timing(self, dag_node_id: str) -> tuple[int | None, int | None]:
        with self.lock:
            task = self.tasks.get(dag_node_id, {})
            return task.get("started_at_ms"), task.get("completed_at_ms")

    def observe_sse_event(self, event: dict[str, Any]) -> None:
        properties = event.get("properties") if isinstance(event.get("properties"), dict) else {}
        session_id = properties.get("sessionID")
        if not isinstance(session_id, str):
            info = properties.get("info") if isinstance(properties.get("info"), dict) else {}
            session_id = info.get("sessionID") or info.get("id")
        if not isinstance(session_id, str):
            session_id = ""
        event_type = str(event.get("type") or "unknown")
        timestamp = now_ms()
        with self.lock:
            subagent_run_id = self.session_to_subagent.get(session_id)
            self.event_count += 1
            normalized = {
                "schema": "oc-subagent.sse_event.v1",
                "run_id": self.run_id,
                "ts_ms": timestamp,
                "event_id": event.get("id"),
                "event_type": event_type,
                "session_id": session_id or None,
                "subagent_run_id": subagent_run_id,
                "raw": event,
            }
            self._append_jsonl_locked("events.jsonl", normalized)
            for task in self.tasks.values():
                if task.get("child_session_id") != session_id:
                    continue
                if task.get("completed_at_ms") is not None:
                    continue
                task["updated_at_ms"] = timestamp
                task["last_event_id"] = event.get("id")
                task["last_event_type"] = event_type
                task["last_event_at_ms"] = timestamp
                task["last_event_age_ms"] = 0
                if event_type == "session.status":
                    status = properties.get("status")
                    if isinstance(status, dict) and isinstance(status.get("type"), str):
                        task["state"] = status["type"]
                elif task.get("state") == "dispatched":
                    task["state"] = "streaming"
            self._write_status_locked()

    def start_heartbeats(self) -> None:
        if self.thread is not None:
            return
        self.thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self.thread.start()

    def stop_heartbeats(self) -> None:
        self.stop.set()
        if self.thread is not None:
            self.thread.join(timeout=2)

    def _heartbeat_loop(self) -> None:
        while not self.stop.wait(self.heartbeat_interval_s):
            timestamp = now_ms()
            with self.lock:
                for dag_node_id, task in self.tasks.items():
                    if task.get("completed_at_ms") is not None:
                        continue
                    started = int(task.get("started_at_ms") or timestamp)
                    last_event_at = task.get("last_event_at_ms")
                    task["heartbeat_count"] = int(task.get("heartbeat_count") or 0) + 1
                    task["elapsed_ms"] = timestamp - started
                    task["updated_at_ms"] = timestamp
                    task["last_event_age_ms"] = None if last_event_at is None else timestamp - int(last_event_at)
                    self.heartbeat_count += 1
                    self._append_jsonl_locked(
                        "heartbeats.jsonl",
                        {
                            "schema": "oc-subagent.heartbeat.v1",
                            "run_id": self.run_id,
                            "ts_ms": timestamp,
                            "dag_node_id": dag_node_id,
                            "subagent_run_id": task.get("subagent_run_id"),
                            "child_session_id": task.get("child_session_id"),
                            "state": task.get("state"),
                            "elapsed_ms": task.get("elapsed_ms"),
                            "last_event_id": task.get("last_event_id"),
                            "last_event_type": task.get("last_event_type"),
                            "last_event_age_ms": task.get("last_event_age_ms"),
                        },
                    )
                self._write_status_locked()


def request_json(
    base: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout_s: float | None = None,
) -> Any:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(base.rstrip("/") + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    password = os.environ.get("OPENCODE_SERVER_PASSWORD", "")
    if password:
        username = os.environ.get("OPENCODE_SERVER_USERNAME", "opencode")
        token = base64.b64encode(f"{username}:{password}".encode()).decode()
        req.add_header("Authorization", f"Basic {token}")
    try:
        with urllib.request.urlopen(
            req,
            timeout=timeout_s if timeout_s is not None else float(env("OC_SUBAGENT_HTTP_TIMEOUT_S", "600")),
        ) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise OcSubagentError(f"OpenCode request failed: {method} {path}: HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise OcSubagentError(f"OpenCode request failed: {method} {path}: {exc}") from exc
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise OcSubagentError(f"OpenCode returned non-JSON for {method} {path}: {raw[:500]!r}") from exc


def payload_error(payload: dict[str, Any]) -> str:
    info = payload.get("info")
    if not isinstance(info, dict):
        return ""
    error = info.get("error")
    if not error:
        return ""
    return json.dumps(error, sort_keys=True)[:1000]


def session_id(payload: dict[str, Any]) -> str:
    for key in ("id", "ID", "sessionID", "session_id", "sessionId"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise OcSubagentError(f"session payload missing id: {payload}")


def create_session(base: str, *, title: str, parent_id: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"title": title}
    if parent_id:
        body["parentID"] = parent_id
    data = request_json(base, "POST", "/session", body)
    if not isinstance(data, dict):
        raise OcSubagentError(f"OpenCode session create returned invalid payload: {data}")
    return data


def model_body_value(model: str) -> dict[str, str] | None:
    raw = model.strip()
    if not raw:
        return None
    if "/" in raw:
        provider_id, model_id = raw.split("/", 1)
    elif raw.startswith("gpt-") or raw.startswith("codex-"):
        provider_id, model_id = "openai", raw
    elif raw.startswith("oc-"):
        provider_id, model_id = "opencode", raw
    else:
        provider_id, model_id = "opencode", raw
    return {"providerID": provider_id.strip(), "modelID": model_id.strip()}


def send_turn(
    base: str,
    *,
    child_session_id: str,
    agent: str,
    prompt: str,
    model: str = "",
    timeout_s: float | None = None,
) -> dict[str, Any]:
    body = {"agent": agent, "parts": [{"type": "text", "text": prompt}]}
    model_value = model_body_value(model)
    if model_value is not None:
        body["model"] = model_value
    data = request_json(
        base,
        "POST",
        f"/session/{urllib.parse.quote(child_session_id)}/message",
        body,
        timeout_s=timeout_s,
    )
    if not isinstance(data, dict):
        raise OcSubagentError(f"OpenCode message returned invalid payload: {data}")
    return data


def list_json(base: str, path: str) -> Any:
    return request_json(base, "GET", path)


def discover_ollama_models() -> dict[str, Any]:
    bases = [
        os.environ.get("OLLAMA_BASE_URL", "").strip(),
        os.environ.get("OLLAMA_HOST", "").strip(),
        "http://127.0.0.1:11434",
        "http://localhost:11434",
    ]
    seen: set[str] = set()
    attempts: list[dict[str, Any]] = []
    for raw in bases:
        base = raw.rstrip("/")
        if not base or base in seen:
            continue
        if not re.match(r"^https?://", base):
            base = "http://" + base
        if base in seen:
            continue
        seen.add(base)
        try:
            with urllib.request.urlopen(base + "/api/tags", timeout=3) as response:
                data = json.loads(response.read().decode("utf-8"))
            models = sorted(
                str(item.get("name") or "").strip()
                for item in data.get("models", [])
                if isinstance(item, dict) and str(item.get("name") or "").strip()
            )
            return {"reachable": True, "base_url": base, "models": models, "attempts": attempts}
        except Exception as exc:
            attempts.append({"base_url": base, "error": f"{type(exc).__name__}: {exc}"})
    return {"reachable": False, "base_url": "", "models": [], "attempts": attempts}


def model_candidates(ollama: dict[str, Any]) -> list[dict[str, Any]]:
    override = os.environ.get("OC_MODEL", "").strip()
    if override:
        return [{"model": override, "source": "OC_MODEL"}]

    raw_candidates = os.environ.get("OC_MODEL_CANDIDATES", "").strip()
    if raw_candidates:
        values = [item.strip() for item in raw_candidates.split(",") if item.strip()]
        return [{"model": value, "source": "OC_MODEL_CANDIDATES"} for value in values]

    preferred_ollama = os.environ.get("OC_OLLAMA_MODEL", "").strip()
    models = set(ollama.get("models") or [])
    candidates: list[dict[str, Any]] = []
    if preferred_ollama and (not models or preferred_ollama in models):
        candidates.append({"model": f"ollama/{preferred_ollama}", "source": "preferred_local_ollama"})
    for name in LOCAL_OLLAMA_PREFERENCE:
        if not models or name in models:
            candidates.append({"model": f"ollama/{name}", "source": "discovered_local_ollama"})
            break
    candidates.extend(
        [
            {"model": "opencode-go/kimi-k2.6", "source": "cheap_opencode_go_fallback"},
            {"model": "openai/gpt-5.5", "source": "paid_openai_fallback"},
        ]
    )
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in candidates:
        if row["model"] in seen:
            continue
        seen.add(row["model"])
        deduped.append(row)
    return deduped


def select_model(base: str, *, agent: str, artifact_dir: Path, run_id: str) -> str:
    ollama = discover_ollama_models()
    candidates = model_candidates(ollama)
    attempts: list[dict[str, Any]] = []
    preflight_timeout_s = float(env("OC_SUBAGENT_PREFLIGHT_TIMEOUT_S", "45"))
    for index, candidate in enumerate(candidates, start=1):
        model = candidate["model"]
        attempt: dict[str, Any] = {"model": model, "source": candidate["source"], "status": "not_run"}
        try:
            parent = create_session(base, title=f"oc-subagent model preflight parent {run_id} {index}")
            parent_id = session_id(parent)
            child = create_session(base, title=f"oc-subagent model preflight child {model}", parent_id=parent_id)
            child_id = session_id(child)
            response = send_turn(
                base,
                child_session_id=child_id,
                agent=agent,
                model=model,
                prompt=PREFLIGHT_PROMPT,
                timeout_s=preflight_timeout_s,
            )
            error = payload_error(response)
            if error:
                raise OcSubagentError(error)
            answer = extract_answer(response, 4)
            attempt.update(
                {
                    "status": "selected",
                    "parent_session_id": parent_id,
                    "child_session_id": child_id,
                    "answer": answer,
                }
            )
            attempts.append(attempt)
            write_json(
                artifact_dir / "model-selection.json",
                {
                    "schema": "oc-subagent.model_selection.v1",
                    "selected_model": model,
                    "selected_source": candidate["source"],
                    "ollama_discovery": ollama,
                    "attempts": attempts,
                },
            )
            return model
        except Exception as exc:
            attempt.update({"status": "rejected", "error": f"{type(exc).__name__}: {exc}"})
            attempts.append(attempt)
    write_json(
        artifact_dir / "model-selection.json",
        {
            "schema": "oc-subagent.model_selection.v1",
            "selected_model": "",
            "ollama_discovery": ollama,
            "attempts": attempts,
        },
    )
    raise OcSubagentError("no candidate model passed preflight")


def assistant_text(payload: dict[str, Any]) -> str:
    parts = payload.get("parts")
    if isinstance(parts, list):
        chunks = [
            str(part.get("text"))
            for part in parts
            if isinstance(part, dict) and part.get("type") == "text" and part.get("text")
        ]
        if chunks:
            return "\n".join(chunks)
    info = payload.get("info")
    if isinstance(info, dict):
        for key in ("content", "text", "body"):
            value = info.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return json.dumps(payload)


def extract_answer(payload: dict[str, Any], expected: int | str) -> int | str:
    text = assistant_text(payload)
    candidates = [text, json.dumps(payload)]
    for candidate in candidates:
        parsed: Any = None
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", candidate, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                except json.JSONDecodeError:
                    parsed = None
        if isinstance(parsed, dict):
            value = parsed.get("answer")
            if value == expected:
                return expected
            if isinstance(expected, str) and isinstance(value, str) and value.casefold() == expected.casefold():
                return expected
    if isinstance(expected, int) and re.search(rf"(?<!\d){expected}(?!\d)", text):
        return expected
    if isinstance(expected, str) and re.search(rf"\b{re.escape(expected)}\b", text, re.IGNORECASE):
        return expected
    raise OcSubagentError(f"response did not contain answer={expected}: {text[:500]}")


def turn_2_leak_tokens() -> list[str]:
    return [
        token
        for token in TURN2_FORBIDDEN_TOKENS
        if re.search(rf"(?<!\d){re.escape(token)}(?!\d)", TURN2_PROMPT)
    ]


def assert_turn_2_no_leak() -> None:
    leaked = turn_2_leak_tokens()
    if leaked:
        raise OcSubagentError(f"turn 2 prompt leaks prior values: {leaked}")


def parse_answer_value(payload: dict[str, Any]) -> tuple[Any, str]:
    """Return (answer_value_or_None, assistant_text) without requiring a specific answer."""
    text = assistant_text(payload)
    for candidate in (text, json.dumps(payload)):
        try:
            parsed: Any = json.loads(candidate)
        except json.JSONDecodeError:
            parsed = None
            match = re.search(r"\{.*\}", candidate, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                except json.JSONDecodeError:
                    parsed = None
        if isinstance(parsed, dict) and "answer" in parsed:
            return parsed.get("answer"), text
    return None, text


def capture_events(base: str, path: Path, stop: threading.Event, observability: Observability) -> None:
    req = urllib.request.Request(base.rstrip("/") + "/event", method="GET")
    password = os.environ.get("OPENCODE_SERVER_PASSWORD", "")
    if password:
        username = os.environ.get("OPENCODE_SERVER_USERNAME", "opencode")
        token = base64.b64encode(f"{username}:{password}".encode()).decode()
        req.add_header("Authorization", f"Basic {token}")
    with path.open("w", encoding="utf-8") as handle:
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                while not stop.is_set():
                    line = response.readline()
                    if not line:
                        break
                    text = line.decode("utf-8", errors="replace")
                    handle.write(text)
                    handle.flush()
                    if text.startswith("data:"):
                        raw = text.removeprefix("data:").strip()
                        if not raw:
                            continue
                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError:
                            observability.emit("sse_parse_error", raw=raw[:500])
                            continue
                        if isinstance(event, dict):
                            observability.observe_sse_event(event)
        except Exception as exc:
            handle.write(f"\n# event capture ended: {type(exc).__name__}: {exc}\n")
            observability.emit("sse_capture_ended", error=f"{type(exc).__name__}: {exc}")


def validate_proof(proof: dict[str, Any], artifact_dir: Path) -> None:
    seq = proof["sequential_subagent_persistence"]
    conc = proof["concurrent_subagents"]
    checks = [
        proof["verdict"] == "PASS",
        proof["project_agent_persistence"]["step_1_result"] == 4,
        proof["project_agent_persistence"]["state_survived_unrelated_tasks"] is True,
        seq["child_session_id_turn_1"] == seq["child_session_id_turn_2"],
        seq["same_child_session"] is True,
        seq["turn_1_answer"] == 22,
        seq["turn_2_answer"] == 32,
        seq["turn_2_prompt_did_not_leak_prior_value"] is True,
        seq["turn_2_waited_for_turn_1"] is True,
        seq["passed"] is True,
        conc["subagent_2_child_session_id"] != conc["subagent_3_child_session_id"],
        conc["subagent_2_answer"] == "Paris",
        conc["subagent_3_answer"] == "red",
        conc["both_dispatched_before_first_result_consumed"] is True,
        conc["passed"] is True,
        proof["negative_control"]["produced_32"] is False,
        proof["negative_control"]["passed"] is True,
        proof["failure_reasons"] == [],
    ]
    if not all(checks):
        raise OcSubagentError(f"proof invariant failed: {proof}")
    for rel in proof["artifacts"].values():
        if not (artifact_dir / rel).exists():
            raise OcSubagentError(f"proof artifact missing: {rel}")


def send_observed_turn(
    base: str,
    *,
    observability: Observability,
    dag_node_id: str,
    subagent_run_id: str,
    child_session_id: str,
    agent: str,
    model: str,
    prompt: str,
    expected: int | str,
) -> tuple[dict[str, Any], int | str]:
    observability.start_task(dag_node_id, subagent_run_id, child_session_id)
    try:
        response = send_turn(base, child_session_id=child_session_id, agent=agent, model=model, prompt=prompt)
        answer = extract_answer(response, expected)
        observability.finish_task(dag_node_id, answer=answer)
        return response, answer
    except Exception as exc:
        observability.finish_task(dag_node_id, error=f"{type(exc).__name__}: {exc}")
        raise


def run() -> int:
    base = env("OPENCODE_BASE", env("OPENCODE_SERVER_URL", "http://127.0.0.1:4096"))
    agent = env("OC_AGENT", "build")
    run_id = env("RUN_ID", f"oc-subagent-persistence-{time.strftime('%Y%m%dT%H%M%S')}")
    artifact_dir = Path(env("ARTIFACT_DIR", f"./artifacts/{run_id}")).expanduser().resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)

    assert_turn_2_no_leak()

    try:
        request_json(base, "GET", "/global/health")
    except OcSubagentError as exc:
        blocked = {
            "verdict": "BLOCKED",
            "run_id": run_id,
            "opencode_base": base,
            "reason": "opencode_unreachable",
            "detail": str(exc),
        }
        write_json(artifact_dir / "proof.json", blocked)
        print(json.dumps(blocked, indent=2), file=sys.stderr)
        return 2

    try:
        model = select_model(base, agent=agent, artifact_dir=artifact_dir, run_id=run_id)
    except OcSubagentError as exc:
        blocked = {
            "verdict": "BLOCKED",
            "run_id": run_id,
            "opencode_base": base,
            "reason": "no_model_available",
            "detail": str(exc),
            "artifacts": {"model_selection": "model-selection.json"},
        }
        write_json(artifact_dir / "proof.json", blocked)
        print(json.dumps(blocked, indent=2), file=sys.stderr)
        return 2

    observability = Observability(
        artifact_dir,
        run_id,
        heartbeat_interval_s=float(env("OC_SUBAGENT_HEARTBEAT_S", "1")),
    )
    observability.emit("run_started", opencode_base=base, agent=agent, model=model)
    observability.start_heartbeats()

    stop_events = threading.Event()
    event_thread = threading.Thread(
        target=capture_events,
        args=(base, artifact_dir / "events.sse", stop_events, observability),
        daemon=True,
    )
    event_thread.start()

    try:
        parent = create_session(base, title=f"project-agent parent: {run_id}")
        parent_session_id = session_id(parent)
        write_json(artifact_dir / "parent-session.json", parent)

        project_state = {
            "run_id": run_id,
            "project_agent_step_1_result": 2 + 2,
            "notes": ["Project agent computed 2 + 2 before calling subagent_1."],
        }
        write_json(artifact_dir / "project-agent-state.json", project_state)

        sub1 = create_session(base, title="subagent_1 persistent arithmetic worker", parent_id=parent_session_id)
        sub1_id = session_id(sub1)
        write_json(artifact_dir / "subagent_1-session.json", sub1)
        observability.register_session("subagent_1", sub1_id)
        session_map = {
            "run_id": run_id,
            "parent_session_id": parent_session_id,
            "subagents": {"subagent_1": {"child_session_id": sub1_id, "turns": []}},
        }
        write_json(artifact_dir / "session-map.json", session_map)

        (artifact_dir / "subagent_1-turn-1-request.txt").write_text(TURN1_PROMPT, encoding="utf-8")
        turn1, turn1_answer = send_observed_turn(
            base,
            observability=observability,
            dag_node_id="subagent_1_turn_1",
            subagent_run_id="subagent_1",
            child_session_id=sub1_id,
            agent=agent,
            model=model,
            prompt=TURN1_PROMPT,
            expected=22,
        )
        write_json(artifact_dir / "subagent_1-turn-1-response.json", turn1)

        sub2 = create_session(base, title="subagent_2 concurrent France worker", parent_id=parent_session_id)
        sub3 = create_session(base, title="subagent_3 concurrent apple worker", parent_id=parent_session_id)
        sub2_id = session_id(sub2)
        sub3_id = session_id(sub3)
        if sub2_id == sub3_id:
            raise OcSubagentError("subagent_2 and subagent_3 received the same child session id")
        write_json(artifact_dir / "subagent_2-session.json", sub2)
        write_json(artifact_dir / "subagent_3-session.json", sub3)
        observability.register_session("subagent_2", sub2_id)
        observability.register_session("subagent_3", sub3_id)
        session_map["subagents"]["subagent_2"] = {"child_session_id": sub2_id, "turns": []}
        session_map["subagents"]["subagent_3"] = {"child_session_id": sub3_id, "turns": []}
        write_json(artifact_dir / "session-map.json", session_map)

        (artifact_dir / "subagent_2-concurrent-request.txt").write_text(SUBAGENT_2_PROMPT, encoding="utf-8")
        (artifact_dir / "subagent_3-concurrent-request.txt").write_text(SUBAGENT_3_PROMPT, encoding="utf-8")
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(
                    send_observed_turn,
                    base,
                    observability=observability,
                    dag_node_id="subagent_2_concurrent",
                    subagent_run_id="subagent_2",
                    child_session_id=sub2_id,
                    agent=agent,
                    model=model,
                    prompt=SUBAGENT_2_PROMPT,
                    expected="Paris",
                ): "subagent_2",
                executor.submit(
                    send_observed_turn,
                    base,
                    observability=observability,
                    dag_node_id="subagent_3_concurrent",
                    subagent_run_id="subagent_3",
                    child_session_id=sub3_id,
                    agent=agent,
                    model=model,
                    prompt=SUBAGENT_3_PROMPT,
                    expected="red",
                ): "subagent_3",
            }
            answers: dict[str, str] = {}
            first_concurrent_result_consumed_ms: int | None = None
            for future in as_completed(futures):
                if first_concurrent_result_consumed_ms is None:
                    first_concurrent_result_consumed_ms = now_ms()
                name = futures[future]
                response, answer = future.result()
                write_json(artifact_dir / f"{name}-concurrent-response.json", response)
                answers[name] = str(answer)

        (artifact_dir / "subagent_1-turn-2-request.txt").write_text(TURN2_PROMPT, encoding="utf-8")
        turn2, turn2_answer = send_observed_turn(
            base,
            observability=observability,
            dag_node_id="subagent_1_turn_2",
            subagent_run_id="subagent_1",
            child_session_id=sub1_id,
            agent=agent,
            model=model,
            prompt=TURN2_PROMPT,
            expected=32,
        )
        write_json(artifact_dir / "subagent_1-turn-2-response.json", turn2)

        neg = create_session(
            base,
            title="subagent_1_negative fresh-session control",
            parent_id=parent_session_id,
        )
        neg_id = session_id(neg)
        if neg_id in {sub1_id, sub2_id, sub3_id}:
            raise OcSubagentError("negative-control session reused an existing child session id")
        write_json(artifact_dir / "subagent_1_negative-session.json", neg)
        observability.register_session("subagent_1_negative", neg_id)
        session_map["subagents"]["subagent_1_negative"] = {"child_session_id": neg_id, "turns": []}
        write_json(artifact_dir / "session-map.json", session_map)
        (artifact_dir / "subagent_1_negative-request.txt").write_text(NEGATIVE_CONTROL_PROMPT, encoding="utf-8")
        observability.start_task("subagent_1_negative", "subagent_1_negative", neg_id)
        neg_response = send_turn(
            base,
            child_session_id=neg_id,
            agent=agent,
            model=model,
            prompt=NEGATIVE_CONTROL_PROMPT,
        )
        write_json(artifact_dir / "subagent_1_negative-response.json", neg_response)
        neg_answer, neg_text = parse_answer_value(neg_response)
        neg_produced_32 = neg_answer == 32 or bool(re.search(r"(?<!\d)32(?!\d)", neg_text))
        observability.finish_task(
            "subagent_1_negative",
            answer=neg_answer if neg_answer is not None else "no_answer",
        )

        children = list_json(base, f"/session/{urllib.parse.quote(parent_session_id)}/children")
        messages = list_json(base, f"/session/{urllib.parse.quote(sub1_id)}/message?limit=50")
        write_json(artifact_dir / "children-after.json", children)
        write_json(artifact_dir / "messages-subagent_1-after.json", messages)

        turn1_started_ms, turn1_completed_ms = observability.task_timing("subagent_1_turn_1")
        turn2_started_ms, _turn2_completed_ms = observability.task_timing("subagent_1_turn_2")
        sub2_started_ms, _sub2_completed_ms = observability.task_timing("subagent_2_concurrent")
        sub3_started_ms, _sub3_completed_ms = observability.task_timing("subagent_3_concurrent")

        did_not_leak = turn_2_leak_tokens() == []
        turn_2_waited = bool(
            turn1_completed_ms is not None
            and turn2_started_ms is not None
            and turn1_completed_ms <= turn2_started_ms
        )
        both_dispatched = bool(
            sub2_started_ms is not None
            and sub3_started_ms is not None
            and first_concurrent_result_consumed_ms is not None
            and max(sub2_started_ms, sub3_started_ms) <= first_concurrent_result_consumed_ms
        )
        seq_passed = turn1_answer == 22 and turn2_answer == 32 and did_not_leak and turn_2_waited
        conc_passed = (
            answers.get("subagent_2") == "Paris"
            and answers.get("subagent_3") == "red"
            and both_dispatched
        )
        neg_passed = not neg_produced_32

        failure_reasons: list[str] = []
        if turn1_answer != 22 or turn2_answer != 32:
            failure_reasons.append(f"sequential answers wrong: turn1={turn1_answer} turn2={turn2_answer}")
        if not did_not_leak:
            failure_reasons.append(f"turn 2 prompt leaked prior values: {turn_2_leak_tokens()}")
        if not turn_2_waited:
            failure_reasons.append("turn 2 did not wait for turn 1 to complete")
        if not both_dispatched:
            failure_reasons.append("concurrent subagents were not both dispatched before first result was consumed")
        if neg_produced_32:
            failure_reasons.append(
                "negative control produced 32 without a turn 1, so 32 is not proof of session memory"
            )
        verdict = "PASS" if not failure_reasons else "FAIL"

        proof = {
            "verdict": verdict,
            "run_id": run_id,
            "parent_session_id": parent_session_id,
            "model_selection": {
                "selected_model": model,
                "artifact": "model-selection.json",
            },
            "project_agent_persistence": {
                "step_1_result": 4,
                "state_survived_unrelated_tasks": project_state["project_agent_step_1_result"] == 4,
            },
            "sequential_subagent_persistence": {
                "subagent_run_id": "subagent_1",
                "child_session_id_turn_1": sub1_id,
                "child_session_id_turn_2": sub1_id,
                "same_child_session": True,
                "turn_1_answer": turn1_answer,
                "turn_2_answer": turn2_answer,
                "turn_2_prompt_did_not_leak_prior_value": did_not_leak,
                "turn_2_waited_for_turn_1": turn_2_waited,
                "passed": seq_passed,
            },
            "concurrent_subagents": {
                "subagent_2_child_session_id": sub2_id,
                "subagent_3_child_session_id": sub3_id,
                "subagent_2_answer": answers.get("subagent_2"),
                "subagent_3_answer": answers.get("subagent_3"),
                "both_dispatched_before_first_result_consumed": both_dispatched,
                "passed": conc_passed,
            },
            "negative_control": {
                "subagent_run_id": "subagent_1_negative",
                "child_session_id": neg_id,
                "prompt_is_turn_2_without_turn_1": True,
                "answer": neg_answer,
                "produced_32": neg_produced_32,
                "passed": neg_passed,
            },
            "failure_reasons": failure_reasons,
            "artifacts": {
                "model_selection": "model-selection.json",
                "session_map": "session-map.json",
                "events": "events.sse",
                "events_jsonl": "events.jsonl",
                "heartbeats": "heartbeats.jsonl",
                "timeline": "timeline.jsonl",
                "task_status": "task-status.json",
                "children_after": "children-after.json",
                "messages_subagent_1_after": "messages-subagent_1-after.json",
                "negative_control_session": "subagent_1_negative-session.json",
                "negative_control_response": "subagent_1_negative-response.json",
            },
        }
        observability.emit("run_completed", verdict=verdict)
        write_json(artifact_dir / "proof.json", proof)
        if verdict != "PASS":
            print(
                json.dumps(
                    {"verdict": "FAIL", "failure_reasons": failure_reasons, "artifact_dir": str(artifact_dir)},
                    indent=2,
                ),
                file=sys.stderr,
            )
            return 1
        validate_proof(proof, artifact_dir)
        print(json.dumps({"verdict": "PASS", "artifact_dir": str(artifact_dir)}, indent=2))
        return 0
    except Exception as exc:
        observability.emit("run_failed", error=f"{type(exc).__name__}: {exc}")
        failure = {
            "verdict": "FAIL",
            "run_id": run_id,
            "failure_reasons": [f"{type(exc).__name__}: {exc}"],
            "artifact_dir": str(artifact_dir),
        }
        write_json(artifact_dir / "proof.json", failure)
        print(json.dumps(failure, indent=2), file=sys.stderr)
        return 1
    finally:
        stop_events.set()
        event_thread.join(timeout=2)
        observability.stop_heartbeats()


if __name__ == "__main__":
    raise SystemExit(run())
