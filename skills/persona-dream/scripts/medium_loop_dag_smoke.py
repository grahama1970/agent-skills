#!/usr/bin/env python3
"""Persona-dream local proof ladder.

This file is intentionally *not* a ``ScillmDagHarness`` implementation.  It is
an inspectable local-command graph runner used to prove narrow rungs without
silently expanding the claim surface.

Public rungs
============

``fixture``
    Scheduler wiring only.  No persona-dream or $scillm evidence.

``scillm-one``
    Exactly one loopback $scillm HTTP request with exact parsed-JSON
    validation and one item receipt.

``scillm-two-concurrent``
    Exactly two loopback $scillm HTTP requests started concurrently inside one
    probe node, with one receipt per item and an aggregate receipt that requires
    the client-side request intervals to overlap.  This does not prove DAG-node
    concurrency or server-side parallel execution.

``real-gates``
    Selected persona-dream gates in deterministic serial order, followed by a
    receipt aggregate and terminal verification.

``scillm-one-plus-real-gates``
    The one-call transport-contract probe followed by the selected real gates.

The graph runner validates node identifiers and dependencies, computes a stable
(topological, declaration-order-tiebroken) execution order, streams JSONL
progress, writes state after every transition, and never invokes a shell.
It executes one graph node at a time by design.

Examples
========

One local $scillm call::

    export SCILLM_API_KEY=<local-proxy-token>  # only when the local proxy needs it
    .venv/bin/python scripts/medium_loop_dag_smoke.py \
      --rung scillm-one --stream-json

Exactly two concurrent local $scillm calls::

    .venv/bin/python scripts/medium_loop_dag_smoke.py \
      --rung scillm-two-concurrent --stream-json

Cheap real gates only::

    .venv/bin/python scripts/medium_loop_dag_smoke.py \
      --rung real-gates --stream-json

Scope statement
===============

A passing result is evidence only for the selected rung.  It is not evidence
for Dreamer orchestration, panel correctness, semantic repair, provider/Kling
readiness, voice cloning, paid-call isolation, external-network isolation, or
``ScillmDagHarness`` behavior.
"""

from __future__ import annotations

from pydantic_step_gate import validate_http_json

import argparse
import asyncio
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlsplit
import uuid


AGENT_SKILLS = Path("/home/graham/workspace/experiments/agent-skills")
DEFAULT_PERSONA_DREAM = AGENT_SKILLS / "skills/persona-dream"
DEFAULT_RUN_ROOT = Path(
    "/mnt/storage12tb/skills/persona-dream/outputs/"
    "20260612-horus-embry-storyboard-first-scillm-strict"
)
DEFAULT_ARTIFACT_ROOT = Path(".artifacts/persona-dream-local-proof")
DEFAULT_FAST_GATE_TIMEOUT_S = 240
DEFAULT_REPAIR_GATE_TIMEOUT_S = 1200
DEFAULT_SCILLM_BASE_URL = "http://localhost:4001"
DEFAULT_SCILLM_MODEL = "gpt-5.5"
DEFAULT_SCILLM_TIMEOUT_S = 180
DEFAULT_SCILLM_API_KEY_ENV = "SCILLM_API_KEY"

DEFAULT_REAL_GATES = ("phase-02", "phase-05", "phase-06")
OPTIONAL_REAL_GATES = ("phase-06-repair", "voice-clone")
REAL_GATES = DEFAULT_REAL_GATES + OPTIONAL_REAL_GATES
GATE_TO_NODE = {
    "phase-02": "phase_02_gate",
    "phase-05": "phase_05_gate",
    "phase-06": "phase_06_gate",
    "phase-06-repair": "phase_06_repair_gate",
    "voice-clone": "voice_clone_gate",
}

PUBLIC_RUNGS = (
    "fixture",
    "scillm-one",
    "scillm-two-concurrent",
    "real-gates",
    "scillm-one-plus-real-gates",
)

SCHEMA_GRAPH = "persona_dream.local_serial_graph.v2"
SCHEMA_EVENT = "persona_dream.local_serial_graph.event.v2"
SCHEMA_STATE = "persona_dream.local_serial_graph.state.v2"
SCHEMA_SUMMARY = "persona_dream.local_proof.summary.v2"
SCHEMA_SCILLM_ITEM = "persona_dream.scillm_probe_item_receipt.v2"
SCHEMA_SCILLM_BATCH = "persona_dream.scillm_probe_batch_receipt.v2"
SCHEMA_GATE_COMMAND = "persona_dream.real_gate_command_receipt.v2"
SCHEMA_GATE_AGGREGATE = "persona_dream.real_gate_aggregate.v2"

SAFE_ITEM_ID = re.compile(r"[A-Za-z0-9_.-]+")


# ---------------------------------------------------------------------------
# Small, deterministic file and data helpers
# ---------------------------------------------------------------------------


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def load_json_or_none(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return value if isinstance(value, dict) else None


def redact_error_message(message: str, *, limit: int = 1200) -> str:
    return message.replace("\r", " ").replace("\n", " ")[:limit]


def ensure_safe_item_id(item_id: str) -> str:
    if not SAFE_ITEM_ID.fullmatch(item_id):
        raise ValueError(f"unsafe item id: {item_id!r}")
    return item_id


def stable_run_directory(root: Path, rung: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid.uuid4().hex[:8]
    return root.expanduser().resolve() / f"{stamp}-{rung}-{suffix}"


class TailBuffer:
    """Bounded character tail used for state summaries."""

    def __init__(self, limit: int = 12_000) -> None:
        self.limit = limit
        self._parts: deque[str] = deque()
        self._size = 0

    def append(self, text: str) -> None:
        self._parts.append(text)
        self._size += len(text)
        while self._parts and self._size > self.limit:
            removed = self._parts.popleft()
            self._size -= len(removed)
        if self._parts and self._size > self.limit:
            first = self._parts.popleft()
            keep = first[-(self.limit - (self._size - len(first))) :]
            self._parts.appendleft(keep)
            self._size = sum(len(part) for part in self._parts)

    def value(self) -> str:
        return "".join(self._parts)[-self.limit :]


class EventSink:
    def __init__(self, path: Path, *, stream: bool) -> None:
        self.path = path
        self.stream = stream
        self.sequence = 0
        self._lock = asyncio.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("", encoding="utf-8")

    async def emit(self, event: Mapping[str, Any]) -> None:
        async with self._lock:
            self.sequence += 1
            payload = {
                "schema": SCHEMA_EVENT,
                "sequence": self.sequence,
                "ts_utc": utc_now(),
                "ts_epoch_s": time.time(),
                **dict(event),
            }
            line = json.dumps(payload, sort_keys=True, ensure_ascii=False)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            if self.stream:
                print(line, flush=True)


# ---------------------------------------------------------------------------
# Graph schema and deterministic serial runner
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NodeSpec:
    node_id: str
    argv: tuple[str, ...]
    depends_on: tuple[str, ...]
    timeout_s: float
    dependency_policy: str


def dump_graph_yaml(path: Path, graph: Mapping[str, Any]) -> None:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("PyYAML is required") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(dict(graph), sort_keys=False), encoding="utf-8")


def load_graph_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("PyYAML is required") from exc
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("graph document must be a mapping")
    return value


def parse_and_validate_graph(graph: Mapping[str, Any]) -> tuple[list[NodeSpec], str]:
    if graph.get("schema") != SCHEMA_GRAPH:
        raise ValueError(f"unsupported graph schema: {graph.get('schema')!r}")
    raw_nodes = graph.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise ValueError("graph.nodes must be a non-empty list")

    nodes: list[NodeSpec] = []
    seen: set[str] = set()
    declaration_index: dict[str, int] = {}
    for index, raw in enumerate(raw_nodes):
        if not isinstance(raw, dict):
            raise ValueError(f"graph.nodes[{index}] must be a mapping")
        node_id = str(raw.get("id", ""))
        if not SAFE_ITEM_ID.fullmatch(node_id):
            raise ValueError(f"invalid node id: {node_id!r}")
        if node_id in seen:
            raise ValueError(f"duplicate node id: {node_id}")
        seen.add(node_id)
        declaration_index[node_id] = index

        if raw.get("surface") != "local_command":
            raise ValueError(f"{node_id}: only surface=local_command is supported")
        argv = raw.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(part, str) and part for part in argv):
            raise ValueError(f"{node_id}: argv must be a non-empty list of strings")
        depends_on_raw = raw.get("depends_on") or []
        if not isinstance(depends_on_raw, list) or not all(isinstance(dep, str) for dep in depends_on_raw):
            raise ValueError(f"{node_id}: depends_on must be a list of node ids")
        if len(depends_on_raw) != len(set(depends_on_raw)):
            raise ValueError(f"{node_id}: duplicate dependencies")
        if node_id in depends_on_raw:
            raise ValueError(f"{node_id}: self dependency")
        timeout_s = float(raw.get("timeout_s", 300))
        if timeout_s <= 0:
            raise ValueError(f"{node_id}: timeout_s must be positive")
        dependency_policy = str(raw.get("dependency_policy", "success"))
        if dependency_policy not in {"success", "complete"}:
            raise ValueError(f"{node_id}: dependency_policy must be success or complete")
        nodes.append(
            NodeSpec(
                node_id=node_id,
                argv=tuple(argv),
                depends_on=tuple(depends_on_raw),
                timeout_s=timeout_s,
                dependency_policy=dependency_policy,
            )
        )

    node_ids = {node.node_id for node in nodes}
    for node in nodes:
        unknown = sorted(set(node.depends_on) - node_ids)
        if unknown:
            raise ValueError(f"{node.node_id}: unknown dependencies: {unknown}")

    terminal_node = str(graph.get("terminal_node", ""))
    if terminal_node not in node_ids:
        raise ValueError(f"terminal_node is missing or unknown: {terminal_node!r}")

    # Stable Kahn topological sort.  Ties use YAML declaration order.
    indegree = {node.node_id: len(node.depends_on) for node in nodes}
    children: dict[str, list[str]] = {node.node_id: [] for node in nodes}
    for node in nodes:
        for dependency in node.depends_on:
            children[dependency].append(node.node_id)
    ready = sorted((node_id for node_id, degree in indegree.items() if degree == 0), key=declaration_index.get)
    order: list[str] = []
    while ready:
        current = ready.pop(0)
        order.append(current)
        for child in sorted(children[current], key=declaration_index.get):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
                ready.sort(key=declaration_index.get)
    if len(order) != len(nodes):
        cyclic = sorted(node_id for node_id, degree in indegree.items() if degree > 0)
        raise ValueError(f"graph contains a dependency cycle: {cyclic}")

    by_id = {node.node_id: node for node in nodes}
    return [by_id[node_id] for node_id in order], terminal_node


async def read_process_stream(
    reader: asyncio.StreamReader,
    *,
    node_id: str,
    stream_name: str,
    sink: EventSink,
    tail: TailBuffer,
) -> None:
    while True:
        raw = await reader.readline()
        if not raw:
            return
        text = raw.decode("utf-8", errors="replace").rstrip("\n")
        tail.append(text + "\n")
        event: dict[str, Any] = {
            "event": "node_stream",
            "node_id": node_id,
            "stream": stream_name,
            "line": text[:32_000],
            "line_truncated": len(text) > 32_000,
        }
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            event["child_json"] = parsed
            child_event = parsed.get("event")
            if isinstance(child_event, str):
                event["child_event"] = child_event
        await sink.emit(event)


async def terminate_process(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    if os.name == "posix":
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:  # pragma: no cover - Windows fallback
        proc.kill()
    await proc.wait()


async def run_local_node(
    node: NodeSpec,
    *,
    cwd: Path,
    sink: EventSink,
) -> dict[str, Any]:
    await sink.emit(
        {
            "event": "node_started",
            "node_id": node.node_id,
            "argv": list(node.argv),
            "timeout_s": node.timeout_s,
        }
    )
    started_monotonic = time.monotonic()
    started_utc = utc_now()
    stdout_tail = TailBuffer()
    stderr_tail = TailBuffer()
    proc: asyncio.subprocess.Process | None = None
    error: str | None = None
    timed_out = False
    exit_code: int | None = None

    try:
        proc = await asyncio.create_subprocess_exec(
            *node.argv,
            cwd=str(cwd),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=(os.name == "posix"),
        )
        assert proc.stdout is not None
        assert proc.stderr is not None
        readers = (
            asyncio.create_task(
                read_process_stream(
                    proc.stdout,
                    node_id=node.node_id,
                    stream_name="stdout",
                    sink=sink,
                    tail=stdout_tail,
                )
            ),
            asyncio.create_task(
                read_process_stream(
                    proc.stderr,
                    node_id=node.node_id,
                    stream_name="stderr",
                    sink=sink,
                    tail=stderr_tail,
                )
            ),
        )
        try:
            exit_code = await asyncio.wait_for(proc.wait(), timeout=node.timeout_s)
        except asyncio.TimeoutError:
            timed_out = True
            error = f"timeout_after_{node.timeout_s:g}s"
            await terminate_process(proc)
            exit_code = proc.returncode
        await asyncio.gather(*readers, return_exceptions=True)
    except (FileNotFoundError, PermissionError, OSError) as exc:
        error = f"{type(exc).__name__}: {redact_error_message(str(exc))}"

    elapsed_s = round(time.monotonic() - started_monotonic, 3)
    status = "success" if exit_code == 0 and not timed_out and error is None else "failed"
    result: dict[str, Any] = {
        "node_id": node.node_id,
        "status": status,
        "started_utc": started_utc,
        "finished_utc": utc_now(),
        "output": {
            "argv": list(node.argv),
            "exit_code": exit_code,
            "elapsed_s": elapsed_s,
            "stdout_tail": stdout_tail.value(),
            "stderr_tail": stderr_tail.value(),
            "timed_out": timed_out,
        },
    }
    if error:
        result["error"] = error
    await sink.emit(
        {
            "event": "node_finished",
            "node_id": node.node_id,
            "status": status,
            "exit_code": exit_code,
            "elapsed_s": elapsed_s,
            "error": error,
        }
    )
    return result


async def run_serial_graph(
    graph_path: Path,
    *,
    run_dir: Path,
    state_path: Path,
    stream_json: bool,
) -> dict[str, Any]:
    graph = load_graph_yaml(graph_path)
    ordered_nodes, terminal_node = parse_and_validate_graph(graph)
    events_path = run_dir / "context/dag-events.jsonl"
    sink = EventSink(events_path, stream=stream_json)
    results: dict[str, dict[str, Any]] = {}

    await sink.emit(
        {
            "event": "dag_started",
            "graph_id": graph.get("graph_id"),
            "graph_path": str(graph_path),
            "execution_model": "deterministic_serial_topological",
            "node_count": len(ordered_nodes),
        }
    )

    for node in ordered_nodes:
        dependency_statuses = {dep: results[dep]["status"] for dep in node.depends_on}
        failed_dependencies = [dep for dep, status in dependency_statuses.items() if status != "success"]
        if node.dependency_policy == "success" and failed_dependencies:
            result = {
                "node_id": node.node_id,
                "status": "blocked",
                "started_utc": None,
                "finished_utc": utc_now(),
                "output": {
                    "reason": "dependencies_not_successful",
                    "dependency_statuses": dependency_statuses,
                },
            }
            results[node.node_id] = result
            await sink.emit(
                {
                    "event": "node_blocked",
                    "node_id": node.node_id,
                    "dependency_statuses": dependency_statuses,
                }
            )
        else:
            results[node.node_id] = await run_local_node(node, cwd=run_dir, sink=sink)

        partial_state = {
            "schema": SCHEMA_STATE,
            "graph_id": graph.get("graph_id"),
            "terminal_node": terminal_node,
            "terminal_status": None,
            "nodes": results,
            "events_path": str(events_path),
        }
        write_json_atomic(state_path, partial_state)

    terminal_status = "pass" if results[terminal_node]["status"] == "success" else "fail"
    state = {
        "schema": SCHEMA_STATE,
        "graph_id": graph.get("graph_id"),
        "proof_scope": graph.get("proof_scope"),
        "execution_model": "deterministic_serial_topological",
        "terminal_node": terminal_node,
        "terminal_status": terminal_status,
        "nodes": results,
        "events_path": str(events_path),
    }
    write_json_atomic(state_path, state)
    await sink.emit(
        {
            "event": "dag_finished",
            "graph_id": graph.get("graph_id"),
            "terminal_node": terminal_node,
            "terminal_status": terminal_status,
        }
    )
    return state


# ---------------------------------------------------------------------------
# $scillm transport-contract probe
# ---------------------------------------------------------------------------


def validate_loopback_base_url(base_url: str) -> str:
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("$scillm base URL must use http or https")
    hostname = parsed.hostname
    if hostname is None:
        raise ValueError("$scillm base URL is missing a host")
    try:
        addresses = {
            result[4][0]
            for result in socket.getaddrinfo(hostname, parsed.port, type=socket.SOCK_STREAM)
        }
    except OSError as exc:
        raise ValueError(f"could not resolve $scillm host {hostname!r}: {exc}") from exc
    if not addresses or any(not ipaddress.ip_address(address).is_loopback for address in addresses):
        raise ValueError(
            f"refusing non-loopback $scillm host {hostname!r} resolved as {sorted(addresses)}; "
            "this proof authorizes only a local service call"
        )
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("$scillm base URL must not contain credentials, query, or fragment")
    if parsed.path not in {"", "/"}:
        raise ValueError("$scillm base URL must not contain a path")
    return base_url.rstrip("/")


def extract_choice_text(response_json: Mapping[str, Any]) -> str:
    choices = response_json.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("missing choices")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise ValueError("choices[0] is not an object")
    message = choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("missing choices[0].message")
    content = message.get("content")
    if not isinstance(content, str):
        raise ValueError("choices[0].message.content is not a string")
    return content.strip()


def request_payload(model: str, expected: Mapping[str, Any]) -> dict[str, Any]:
    exact = canonical_json(expected)
    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "Return only valid JSON. No markdown. No prose.",
            },
            {
                "role": "user",
                "content": f"Return exactly this JSON object and no other text: {exact}",
            },
        ],
        "response_format": {"type": "json_object"},
    }


async def execute_scillm_batch(
    *,
    base_url: str,
    model: str,
    timeout_s: float,
    count: int,
    caller_skill: str,
    api_key_env: str,
    item_dir: Path,
    aggregate_receipt_path: Path,
) -> dict[str, Any]:
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("httpx is required for $scillm probes") from exc

    if count not in {1, 2}:
        raise ValueError("this proof supports exactly one or exactly two calls")
    local_base_url = validate_loopback_base_url(base_url)
    endpoint = f"{local_base_url}/v1/chat/completions"
    item_dir.mkdir(parents=True, exist_ok=True)
    api_key = os.environ.get(api_key_env) if api_key_env else None
    headers = {
        "X-Caller-Skill": caller_skill,
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    ready_count = 0
    ready_lock = asyncio.Lock()
    all_ready = asyncio.Event()
    release = asyncio.Event()
    batch_started_utc = utc_now()
    batch_started_epoch_ns = time.time_ns()

    async def worker(index: int, client: Any) -> dict[str, Any]:
        nonlocal ready_count
        item_id = f"scillm_probe_{index:02d}"
        ensure_safe_item_id(item_id)
        answer = "persona-dream-scillm-probe" if count == 1 else f"persona-dream-scillm-probe-{index:02d}"
        expected = {"ok": True, "answer": answer}
        payload = request_payload(model, expected)
        request_body = canonical_json(payload)
        receipt_path = item_dir / f"{item_id}.json"

        async with ready_lock:
            ready_count += 1
            if ready_count == count:
                all_ready.set()
        await release.wait()
        await asyncio.sleep(0)

        request_started_utc = utc_now()
        request_started_epoch_ns = time.time_ns()
        request_started_monotonic_ns = time.monotonic_ns()
        status_code: int | None = None
        response_text = ""
        response_json: dict[str, Any] | None = None
        parsed_content: Any = None
        content_text: str | None = None
        http_version: str | None = None
        request_id: str | None = None
        error: dict[str, str] | None = None
        ok = False

        try:
            response = await client.post(endpoint, headers=headers, json=payload)
            status_code = response.status_code
            response_text = response.text
            http_version = response.http_version
            request_id = response.headers.get("x-request-id") or response.headers.get("openai-request-id")
            response.raise_for_status()
            parsed = validate_http_json("chat_completion", response.json())
            if not isinstance(parsed, dict):
                raise ValueError("top-level response is not a JSON object")
            response_json = parsed
            content_text = extract_choice_text(response_json)
            parsed_content = json.loads(content_text)
            ok = parsed_content == expected
            if not ok:
                error = {
                    "type": "ContractMismatch",
                    "message": "parsed model content did not equal the expected JSON object",
                }
        except Exception as exc:  # Receipt must exist for every attempted item.
            error = {
                "type": type(exc).__name__,
                "message": redact_error_message(str(exc)),
            }

        request_finished_monotonic_ns = time.monotonic_ns()
        request_finished_epoch_ns = time.time_ns()
        receipt = {
            "schema": SCHEMA_SCILLM_ITEM,
            "status": "PASS" if ok else "FAIL",
            "ok": ok,
            "item_id": item_id,
            "endpoint": endpoint,
            "model": model,
            "caller_skill": caller_skill,
            "timeout_s": timeout_s,
            "request_started_utc": request_started_utc,
            "request_finished_utc": utc_now(),
            "request_started_epoch_ns": request_started_epoch_ns,
            "request_finished_epoch_ns": request_finished_epoch_ns,
            "request_started_monotonic_ns": request_started_monotonic_ns,
            "request_finished_monotonic_ns": request_finished_monotonic_ns,
            "elapsed_s": round((request_finished_monotonic_ns - request_started_monotonic_ns) / 1e9, 6),
            "http_status": status_code,
            "http_version": http_version,
            "request_id": request_id,
            "request_sha256": sha256_text(request_body),
            "response_sha256": sha256_text(response_text),
            "response_excerpt": response_text[:2000],
            "expected_content": expected,
            "actual_content": parsed_content,
            "raw_choice_content_sha256": sha256_text(content_text) if content_text is not None else None,
            "error": error,
            "authorization_header_present": bool(api_key),
            "network_target": "loopback_scillm",
            "local_scillm_call_authorized": True,
            "external_provider_call_authorized": False,
            "paid_call_authorized": False,
            "network_isolation_proven": False,
        }
        write_json_atomic(receipt_path, receipt)
        print(
            json.dumps(
                {
                    "event": "scillm_probe_item_finished",
                    "item_id": item_id,
                    "status": receipt["status"],
                    "http_status": status_code,
                    "elapsed_s": receipt["elapsed_s"],
                    "receipt_path": str(receipt_path),
                    "error": error,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        return receipt

    timeout = httpx.Timeout(
        timeout_s,
        connect=min(timeout_s, 10.0),
        write=min(timeout_s, 30.0),
        pool=min(timeout_s, 10.0),
    )
    limits = httpx.Limits(max_connections=count, max_keepalive_connections=count)
    async with httpx.AsyncClient(
        timeout=timeout,
        limits=limits,
        follow_redirects=False,
        trust_env=False,
    ) as client:
        tasks = [asyncio.create_task(worker(index, client)) for index in range(1, count + 1)]
        await asyncio.wait_for(all_ready.wait(), timeout=min(timeout_s, 10.0))
        release_epoch_ns = time.time_ns()
        print(
            json.dumps(
                {
                    "event": "scillm_probe_batch_released",
                    "count": count,
                    "endpoint": endpoint,
                    "model": model,
                    "release_epoch_ns": release_epoch_ns,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        release.set()
        receipts = await asyncio.gather(*tasks)

    overlap_ns: int | None = None
    client_intervals_overlap: bool | None = None
    if count == 2:
        left, right = receipts
        # Both workers live in this process, so monotonic intervals are directly
        # comparable and immune to wall-clock adjustments.
        overlap_ns = min(
            int(left["request_finished_monotonic_ns"]),
            int(right["request_finished_monotonic_ns"]),
        ) - max(
            int(left["request_started_monotonic_ns"]),
            int(right["request_started_monotonic_ns"]),
        )
        client_intervals_overlap = overlap_ns > 0

    all_items_passed = len(receipts) == count and all(item.get("status") == "PASS" for item in receipts)
    concurrency_requirement_passed = count == 1 or client_intervals_overlap is True
    ok = all_items_passed and concurrency_requirement_passed
    aggregate = {
        "schema": SCHEMA_SCILLM_BATCH,
        "status": "PASS" if ok else "FAIL",
        "ok": ok,
        "proof_scope": (
            "local_scillm_single_transport_contract"
            if count == 1
            else "local_scillm_two_call_client_concurrency_contract"
        ),
        "call_count": count,
        "expected_call_count": count,
        "endpoint": endpoint,
        "model": model,
        "caller_skill": caller_skill,
        "batch_started_utc": batch_started_utc,
        "batch_finished_utc": utc_now(),
        "batch_started_epoch_ns": batch_started_epoch_ns,
        "release_epoch_ns": release_epoch_ns,
        "item_receipts": [str(item_dir / f"{item['item_id']}.json") for item in receipts],
        "item_statuses": {str(item["item_id"]): item["status"] for item in receipts},
        "all_items_passed": all_items_passed,
        "client_request_overlap_ns": overlap_ns,
        "client_request_intervals_overlap": client_intervals_overlap,
        "concurrency_requirement_passed": concurrency_requirement_passed,
        "dag_node_concurrency_proven": False,
        "server_parallelism_proven": False,
        "deterministic_model_generation_proven": False,
        "local_scillm_call_authorized": True,
        "external_provider_call_authorized": False,
        "paid_call_authorized": False,
        "network_isolation_proven": False,
    }
    write_json_atomic(aggregate_receipt_path, aggregate)
    print(
        json.dumps(
            {
                "event": "scillm_probe_batch_finished",
                "status": aggregate["status"],
                "call_count": count,
                "client_request_intervals_overlap": client_intervals_overlap,
                "receipt_path": str(aggregate_receipt_path),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return aggregate


def node_scillm_batch(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="_node-scillm-batch")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--timeout-s", type=float, required=True)
    parser.add_argument("--count", type=int, choices=[1, 2], required=True)
    parser.add_argument("--caller-skill", default="persona-dream")
    parser.add_argument("--api-key-env", default=DEFAULT_SCILLM_API_KEY_ENV)
    parser.add_argument("--item-dir", type=Path, required=True)
    parser.add_argument("--aggregate-receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        aggregate = asyncio.run(
            execute_scillm_batch(
                base_url=args.base_url,
                model=args.model,
                timeout_s=args.timeout_s,
                count=args.count,
                caller_skill=args.caller_skill,
                api_key_env=args.api_key_env,
                item_dir=args.item_dir,
                aggregate_receipt_path=args.aggregate_receipt,
            )
        )
    except Exception as exc:
        failure = {
            "schema": SCHEMA_SCILLM_BATCH,
            "status": "FAIL",
            "ok": False,
            "call_count": args.count,
            "error": {
                "type": type(exc).__name__,
                "message": redact_error_message(str(exc)),
            },
            "local_scillm_call_authorized": True,
            "external_provider_call_authorized": False,
            "paid_call_authorized": False,
            "network_isolation_proven": False,
        }
        write_json_atomic(args.aggregate_receipt, failure)
        print(json.dumps({"event": "scillm_probe_batch_failed", "error": failure["error"]}), flush=True)
        return 1
    return 0 if aggregate.get("status") == "PASS" else 1


# ---------------------------------------------------------------------------
# Persona-dream real gate execution and aggregation
# ---------------------------------------------------------------------------


def summarize_gate_receipt(gate: str, receipt_path: Path) -> dict[str, Any]:
    data = load_json_or_none(receipt_path)
    summary: dict[str, Any] = {
        "gate": gate,
        "path": str(receipt_path),
        "exists": data is not None,
        "status": "MISSING",
        "blockers": [f"{gate}:missing_gate_receipt"],
    }
    if data is None:
        return summary

    if gate == "phase-02":
        ok = data.get("status") == "ok" and data.get("phase_verdict") == "PHASE_02_COMPLETE"
        summary.update(
            {
                "status": "PASS" if ok else "FAIL",
                "phase_verdict": data.get("phase_verdict"),
                "schema": data.get("schema"),
                "blockers": [] if ok else [f"{gate}:phase_verdict_not_complete"],
            }
        )
        return summary

    failed = data.get("failed")
    ok = isinstance(failed, int) and failed == 0
    blockers: list[str] = []
    raw_gates = data.get("gates")
    if isinstance(raw_gates, list):
        for item in raw_gates:
            if not isinstance(item, dict) or item.get("status") == "PASS":
                continue
            item_id = str(item.get("id", "gate"))
            details = item.get("blockers")
            if not isinstance(details, list) or not details:
                details = [str(item.get("status", "unknown"))]
            blockers.extend(f"{gate}:{item_id}:{detail}" for detail in details)
    summary.update(
        {
            "status": "PASS" if ok else "FAIL",
            "failed": failed,
            "passed": data.get("passed"),
            "schema": data.get("schema"),
            "blockers": [] if ok else blockers or [f"{gate}:failed_{failed!r}"],
        }
    )
    return summary


def parse_phase_02_stdout(stdout_path: Path) -> dict[str, Any] | None:
    try:
        text = stdout_path.read_text(encoding="utf-8")
    except OSError:
        return None
    stripped = text.strip()
    if stripped:
        try:
            value = json.loads(stripped)
        except json.JSONDecodeError:
            value = None
        if isinstance(value, dict):
            return value
    for line in reversed(text.splitlines()):
        candidate = line.strip()
        if not candidate.startswith("{"):
            continue
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and (
            "phase_verdict" in value or value.get("status") == "ok" or "schema" in value
        ):
            return value
    return None


def stream_subprocess_to_logs(
    command: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    stdout_path: Path,
    stderr_path: Path,
) -> tuple[int, str, str]:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        list(command),
        cwd=str(cwd),
        env=dict(env),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    stdout_tail = TailBuffer()
    stderr_tail = TailBuffer()

    def pump(stream: Any, path: Path, tail: TailBuffer, target: Any) -> None:
        assert stream is not None
        with path.open("w", encoding="utf-8") as log:
            for line in stream:
                log.write(line)
                log.flush()
                tail.append(line)
                target.write(line)
                target.flush()

    threads = (
        threading.Thread(target=pump, args=(proc.stdout, stdout_path, stdout_tail, sys.stdout), daemon=True),
        threading.Thread(target=pump, args=(proc.stderr, stderr_path, stderr_tail, sys.stderr), daemon=True),
    )
    for thread in threads:
        thread.start()
    returncode = proc.wait()
    for thread in threads:
        thread.join(timeout=5)
    return returncode, stdout_tail.value(), stderr_tail.value()


def node_real_gate(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="_node-real-gate")
    parser.add_argument("--gate", choices=REAL_GATES, required=True)
    parser.add_argument("--persona-dream-dir", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--context-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    gate = args.gate
    persona_dream = args.persona_dream_dir.resolve()
    run_root = args.run_root.resolve()
    context = args.context_dir.resolve()
    context.mkdir(parents=True, exist_ok=True)
    output_path = context / f"gate-{gate}.json"
    command_receipt_path = context / f"gate-{gate}-command-receipt.json"
    stdout_log = context / f"gate-{gate}.stdout.log"
    stderr_log = context / f"gate-{gate}.stderr.log"

    if not persona_dream.is_dir():
        write_json_atomic(
            command_receipt_path,
            {
                "schema": SCHEMA_GATE_COMMAND,
                "gate": gate,
                "status": "FAIL",
                "error": f"persona-dream directory not found: {persona_dream}",
            },
        )
        return 1
    if not run_root.is_dir():
        write_json_atomic(
            command_receipt_path,
            {
                "schema": SCHEMA_GATE_COMMAND,
                "gate": gate,
                "status": "FAIL",
                "error": f"run root not found: {run_root}",
            },
        )
        return 1

    if gate == "phase-02":
        command = [
            sys.executable,
            str(persona_dream / "scripts/run_phase_02_memory_recall.py"),
            "--run-root",
            str(run_root),
            "--no-report",
        ]
    else:
        command = [
            str(persona_dream / "run.sh"),
            "validate-gate",
            "--gate",
            gate,
            "--run-root",
            str(run_root),
            "--output",
            str(output_path),
        ]

    env = os.environ.copy()
    removed_credentials: list[str] = []
    for name in ("KLING_ACCESS_KEY", "KLING_SECRET_KEY", "KLING_TOKEN"):
        if name in env:
            removed_credentials.append(name)
            env.pop(name, None)
    env.pop("PERSONA_DREAM_RUN_ROOT", None)

    print(
        json.dumps(
            {
                "event": "real_gate_started",
                "gate": gate,
                "command": command,
                "run_root": str(run_root),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    started = time.monotonic()
    started_utc = utc_now()
    try:
        returncode, stdout_tail, stderr_tail = stream_subprocess_to_logs(
            command,
            cwd=persona_dream,
            env=env,
            stdout_path=stdout_log,
            stderr_path=stderr_log,
        )
        execution_error: str | None = None
    except Exception as exc:
        returncode = None
        stdout_tail = ""
        stderr_tail = ""
        execution_error = f"{type(exc).__name__}: {redact_error_message(str(exc))}"

    if gate == "phase-02" and returncode == 0 and not output_path.exists():
        parsed = parse_phase_02_stdout(stdout_log)
        if parsed is not None:
            write_json_atomic(output_path, parsed)

    gate_summary = summarize_gate_receipt(gate, output_path)
    ok = returncode == 0 and gate_summary.get("status") == "PASS" and execution_error is None
    receipt = {
        "schema": SCHEMA_GATE_COMMAND,
        "status": "PASS" if ok else "FAIL",
        "gate": gate,
        "run_root": str(run_root),
        "persona_dream_dir": str(persona_dream),
        "command": command,
        "started_utc": started_utc,
        "finished_utc": utc_now(),
        "exit_code": returncode,
        "elapsed_s": round(time.monotonic() - started, 3),
        "stdout_log": str(stdout_log),
        "stderr_log": str(stderr_log),
        "stdout_sha256": sha256_file(stdout_log),
        "stderr_sha256": sha256_file(stderr_log),
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
        "gate_receipt": str(output_path),
        "gate_receipt_exists": output_path.exists(),
        "gate_summary": gate_summary,
        "execution_error": execution_error,
        "provider_credentials_removed": removed_credentials,
        "requested_external_provider_policy": "not_authorized",
        "requested_paid_call_policy": "not_authorized",
        "network_isolation_enforced": False,
        "no_paid_no_live_proven": False,
    }
    write_json_atomic(command_receipt_path, receipt)
    print(
        json.dumps(
            {
                "event": "real_gate_finished",
                "gate": gate,
                "status": receipt["status"],
                "exit_code": returncode,
                "elapsed_s": receipt["elapsed_s"],
                "command_receipt": str(command_receipt_path),
                "gate_receipt": str(output_path) if output_path.exists() else None,
                "blockers": gate_summary.get("blockers", []),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0 if ok else 1


def node_aggregate_real_gates(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="_node-aggregate-real-gates")
    parser.add_argument("--context-dir", type=Path, required=True)
    parser.add_argument("--gate", action="append", choices=REAL_GATES, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    context = args.context_dir.resolve()
    records: list[dict[str, Any]] = []
    blockers: list[str] = []
    for gate in args.gate:
        command_path = context / f"gate-{gate}-command-receipt.json"
        gate_path = context / f"gate-{gate}.json"
        command = load_json_or_none(command_path)
        gate_summary = summarize_gate_receipt(gate, gate_path)
        record = {
            "gate": gate,
            "command_receipt": str(command_path),
            "command_receipt_exists": command is not None,
            "command_status": command.get("status") if command else "MISSING",
            "command_exit_code": command.get("exit_code") if command else None,
            "gate_receipt": str(gate_path),
            "gate_summary": gate_summary,
            "status": "PASS",
            "blockers": [],
        }
        if command is None:
            record["status"] = "FAIL"
            record["blockers"].append(f"{gate}:missing_command_receipt")
        elif command.get("status") != "PASS" or command.get("exit_code") != 0:
            record["status"] = "FAIL"
            record["blockers"].append(f"{gate}:command_not_pass")
        if gate_summary.get("status") != "PASS":
            record["status"] = "FAIL"
            record["blockers"].extend(str(item) for item in gate_summary.get("blockers", []))
        if record["status"] != "PASS":
            blockers.extend(record["blockers"] or [f"{gate}:not_pass"])
        records.append(record)

    aggregate = {
        "schema": SCHEMA_GATE_AGGREGATE,
        "status": "PASS" if not blockers and len(records) == len(args.gate) else "FAIL",
        "proof_scope": "real_gate_sanity",
        "expected_gates": args.gate,
        "gate_count": len(records),
        "passed": sum(record["status"] == "PASS" for record in records),
        "failed": sum(record["status"] != "PASS" for record in records),
        "blockers": blockers,
        "receipts": records,
        "external_provider_call_authorized": False,
        "paid_call_authorized": False,
        "network_isolation_proven": False,
        "no_paid_no_live_proven": False,
    }
    write_json_atomic(args.output, aggregate)
    print(json.dumps({"event": "real_gate_aggregate_finished", **aggregate}, sort_keys=True), flush=True)
    return 0 if aggregate["status"] == "PASS" else 1


# ---------------------------------------------------------------------------
# Generic verification and fixture nodes
# ---------------------------------------------------------------------------


def node_verify_receipts(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="_node-verify-receipts")
    parser.add_argument("--receipt", type=Path, action="append", required=True)
    parser.add_argument("--expected-schema", action="append")
    args = parser.parse_args(argv)

    expected_schemas = args.expected_schema or []
    if expected_schemas and len(expected_schemas) != len(args.receipt):
        raise SystemExit("--expected-schema count must match --receipt count")

    checks: list[dict[str, Any]] = []
    for index, path in enumerate(args.receipt):
        data = load_json_or_none(path)
        expected_schema = expected_schemas[index] if expected_schemas else None
        ok = data is not None and data.get("status") == "PASS"
        if expected_schema is not None:
            ok = ok and data is not None and data.get("schema") == expected_schema
        checks.append(
            {
                "path": str(path),
                "exists": data is not None,
                "status": data.get("status") if data else "MISSING",
                "schema": data.get("schema") if data else None,
                "expected_schema": expected_schema,
                "ok": ok,
            }
        )
    ok = all(check["ok"] for check in checks)
    print(json.dumps({"event": "terminal_verification", "ok": ok, "checks": checks}, sort_keys=True), flush=True)
    return 0 if ok else 1


def node_fixture(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="_node-fixture")
    parser.add_argument("--label", required=True)
    args = parser.parse_args(argv)
    print(json.dumps({"event": "fixture_step", "label": args.label}), flush=True)
    return 0


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def command_for(script: Path, python_exe: str, internal_command: str, *args: str) -> list[str]:
    return [python_exe, str(script), internal_command, *args]


def graph_node(
    node_id: str,
    argv: Sequence[str],
    *,
    depends_on: Iterable[str] = (),
    timeout_s: float = 300,
    dependency_policy: str = "success",
) -> dict[str, Any]:
    return {
        "id": node_id,
        "surface": "local_command",
        "depends_on": list(depends_on),
        "dependency_policy": dependency_policy,
        "argv": list(argv),
        "timeout_s": timeout_s,
    }


def selected_real_gates(*, include_panel_repair: bool, include_voice_clone: bool) -> list[str]:
    gates = list(DEFAULT_REAL_GATES)
    if include_panel_repair:
        gates.append("phase-06-repair")
    if include_voice_clone:
        gates.append("voice-clone")
    return gates


def append_scillm_nodes(
    nodes: list[dict[str, Any]],
    *,
    script: Path,
    python_exe: str,
    context_dir: Path,
    count: int,
    base_url: str,
    model: str,
    timeout_s: int,
    api_key_env: str,
    depends_on: Sequence[str] = (),
) -> tuple[str, Path]:
    label = "one" if count == 1 else "two-concurrent"
    batch_node = "scillm_oneshot_probe" if count == 1 else "scillm_two_concurrent_probe"
    verify_node = "verify_scillm_oneshot" if count == 1 else "verify_scillm_two_concurrent"
    item_dir = context_dir / f"scillm-{label}/items"
    aggregate_path = context_dir / (
        "scillm-oneshot-probe-receipt.json"
        if count == 1
        else "scillm-two-concurrent-probe-receipt.json"
    )
    nodes.append(
        graph_node(
            batch_node,
            command_for(
                script,
                python_exe,
                "_node-scillm-batch",
                "--base-url",
                base_url,
                "--model",
                model,
                "--timeout-s",
                str(timeout_s),
                "--count",
                str(count),
                "--api-key-env",
                api_key_env,
                "--item-dir",
                str(item_dir),
                "--aggregate-receipt",
                str(aggregate_path),
            ),
            depends_on=depends_on,
            timeout_s=timeout_s + 20,
        )
    )
    nodes.append(
        graph_node(
            verify_node,
            command_for(
                script,
                python_exe,
                "_node-verify-receipts",
                "--receipt",
                str(aggregate_path),
                "--expected-schema",
                SCHEMA_SCILLM_BATCH,
            ),
            depends_on=[batch_node],
            timeout_s=30,
            dependency_policy="complete",
        )
    )
    return verify_node, aggregate_path


def append_real_gate_nodes(
    nodes: list[dict[str, Any]],
    *,
    script: Path,
    python_exe: str,
    context_dir: Path,
    persona_dream_dir: Path,
    run_root: Path,
    gates: Sequence[str],
    fast_timeout_s: int,
    repair_timeout_s: int,
    depends_on: Sequence[str] = (),
) -> tuple[str, Path]:
    previous = list(depends_on)
    gate_node_ids: list[str] = []
    for gate in gates:
        node_id = GATE_TO_NODE[gate]
        gate_node_ids.append(node_id)
        timeout_s = repair_timeout_s if gate == "phase-06-repair" else fast_timeout_s
        nodes.append(
            graph_node(
                node_id,
                command_for(
                    script,
                    python_exe,
                    "_node-real-gate",
                    "--gate",
                    gate,
                    "--persona-dream-dir",
                    str(persona_dream_dir),
                    "--run-root",
                    str(run_root),
                    "--context-dir",
                    str(context_dir),
                ),
                depends_on=previous,
                timeout_s=timeout_s,
            )
        )
        previous = [node_id]

    aggregate_path = context_dir / "aggregate_real_gates.json"
    aggregate_args: list[str] = [
        "--context-dir",
        str(context_dir),
        "--output",
        str(aggregate_path),
    ]
    for gate in gates:
        aggregate_args.extend(["--gate", gate])
    nodes.append(
        graph_node(
            "aggregate_real_gate_receipts",
            command_for(script, python_exe, "_node-aggregate-real-gates", *aggregate_args),
            depends_on=gate_node_ids,
            timeout_s=60,
            dependency_policy="complete",
        )
    )
    nodes.append(
        graph_node(
            "verify_terminal_real",
            command_for(
                script,
                python_exe,
                "_node-verify-receipts",
                "--receipt",
                str(aggregate_path),
                "--expected-schema",
                SCHEMA_GATE_AGGREGATE,
            ),
            depends_on=["aggregate_real_gate_receipts"],
            timeout_s=30,
            dependency_policy="complete",
        )
    )
    return "verify_terminal_real", aggregate_path


def build_graph(
    *,
    rung: str,
    script: Path,
    python_exe: str,
    context_dir: Path,
    persona_dream_dir: Path,
    run_root: Path,
    gates: Sequence[str],
    fast_timeout_s: int,
    repair_timeout_s: int,
    scillm_base_url: str,
    scillm_model: str,
    scillm_timeout_s: int,
    scillm_api_key_env: str,
) -> tuple[dict[str, Any], list[Path]]:
    nodes: list[dict[str, Any]] = []
    evidence_receipts: list[Path] = []

    if rung == "fixture":
        previous: list[str] = []
        for label in ("first", "second", "verify"):
            nodes.append(
                graph_node(
                    label,
                    command_for(script, python_exe, "_node-fixture", "--label", label),
                    depends_on=previous,
                    timeout_s=30,
                )
            )
            previous = [label]
        terminal_node = "verify"
        proof_scope = "fixture_scheduler_only"
        proves = ["local command launch", "stable serial dependency order", "JSONL event and state writing"]
    elif rung == "scillm-one":
        terminal_node, receipt = append_scillm_nodes(
            nodes,
            script=script,
            python_exe=python_exe,
            context_dir=context_dir,
            count=1,
            base_url=scillm_base_url,
            model=scillm_model,
            timeout_s=scillm_timeout_s,
            api_key_env=scillm_api_key_env,
        )
        evidence_receipts.append(receipt)
        proof_scope = "local_scillm_single_transport_contract"
        proves = ["one loopback HTTP call", "one exact parsed-JSON contract sample", "one item receipt"]
    elif rung == "scillm-two-concurrent":
        terminal_node, receipt = append_scillm_nodes(
            nodes,
            script=script,
            python_exe=python_exe,
            context_dir=context_dir,
            count=2,
            base_url=scillm_base_url,
            model=scillm_model,
            timeout_s=scillm_timeout_s,
            api_key_env=scillm_api_key_env,
        )
        evidence_receipts.append(receipt)
        proof_scope = "local_scillm_two_call_client_concurrency_contract"
        proves = [
            "exactly two loopback HTTP calls",
            "one receipt per item",
            "overlapping client request intervals inside one probe node",
        ]
    elif rung == "real-gates":
        terminal_node, receipt = append_real_gate_nodes(
            nodes,
            script=script,
            python_exe=python_exe,
            context_dir=context_dir,
            persona_dream_dir=persona_dream_dir,
            run_root=run_root,
            gates=gates,
            fast_timeout_s=fast_timeout_s,
            repair_timeout_s=repair_timeout_s,
        )
        evidence_receipts.append(receipt)
        proof_scope = "real_gate_sanity"
        proves = [f"selected gate receipts passed: {', '.join(gates)}", "deterministic serial gate order"]
    elif rung == "scillm-one-plus-real-gates":
        scillm_terminal, scillm_receipt = append_scillm_nodes(
            nodes,
            script=script,
            python_exe=python_exe,
            context_dir=context_dir,
            count=1,
            base_url=scillm_base_url,
            model=scillm_model,
            timeout_s=scillm_timeout_s,
            api_key_env=scillm_api_key_env,
        )
        real_terminal, real_receipt = append_real_gate_nodes(
            nodes,
            script=script,
            python_exe=python_exe,
            context_dir=context_dir,
            persona_dream_dir=persona_dream_dir,
            run_root=run_root,
            gates=gates,
            fast_timeout_s=fast_timeout_s,
            repair_timeout_s=repair_timeout_s,
            depends_on=[scillm_terminal],
        )
        terminal_node = "verify_combined"
        nodes.append(
            graph_node(
                terminal_node,
                command_for(
                    script,
                    python_exe,
                    "_node-verify-receipts",
                    "--receipt",
                    str(scillm_receipt),
                    "--receipt",
                    str(real_receipt),
                    "--expected-schema",
                    SCHEMA_SCILLM_BATCH,
                    "--expected-schema",
                    SCHEMA_GATE_AGGREGATE,
                ),
                depends_on=[scillm_terminal, real_terminal],
                timeout_s=30,
                dependency_policy="complete",
            )
        )
        evidence_receipts.extend([scillm_receipt, real_receipt])
        proof_scope = "local_scillm_single_transport_plus_real_gate_sanity"
        proves = ["one loopback $scillm contract sample", f"selected gate receipts passed: {', '.join(gates)}"]
    else:  # pragma: no cover - argparse prevents this
        raise ValueError(f"unsupported rung: {rung}")

    graph = {
        "schema": SCHEMA_GRAPH,
        "graph_id": f"persona-dream-{rung}",
        "proof_scope": proof_scope,
        "execution_model": "deterministic_serial_topological",
        "terminal_node": terminal_node,
        "claims": {
            "proves": proves,
            "does_not_prove": [
                "ScillmDagHarness behavior",
                "Dreamer orchestration",
                "deterministic model generation",
                "bounded semantic repair",
                "panel or WebGPT correctness",
                "provider or Kling readiness",
                "voice clone readiness",
                "paid-call isolation",
                "external-network isolation",
            ],
        },
        "nodes": nodes,
    }
    return graph, evidence_receipts


# ---------------------------------------------------------------------------
# Public orchestration
# ---------------------------------------------------------------------------


def public_main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rung", choices=PUBLIC_RUNGS, required=True)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Use this exact output directory instead of creating a timestamped directory.",
    )
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--persona-dream-dir", type=Path, default=DEFAULT_PERSONA_DREAM)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--fast-timeout-s", type=int, default=DEFAULT_FAST_GATE_TIMEOUT_S)
    parser.add_argument("--repair-timeout-s", type=int, default=DEFAULT_REPAIR_GATE_TIMEOUT_S)
    parser.add_argument("--scillm-base-url", default=DEFAULT_SCILLM_BASE_URL)
    parser.add_argument("--scillm-model", default=DEFAULT_SCILLM_MODEL)
    parser.add_argument("--scillm-timeout-s", type=int, default=DEFAULT_SCILLM_TIMEOUT_S)
    parser.add_argument("--scillm-api-key-env", default=DEFAULT_SCILLM_API_KEY_ENV)
    parser.add_argument("--stream-json", action="store_true")
    parser.add_argument(
        "--include-panel-repair",
        action="store_true",
        help="Append phase-06-repair. May launch review-panel/WebGPT; never enabled by default.",
    )
    parser.add_argument(
        "--include-voice-clone",
        action="store_true",
        help="Append voice-clone. Never enabled by default.",
    )
    args = parser.parse_args(argv)

    if args.fast_timeout_s <= 0 or args.repair_timeout_s <= 0 or args.scillm_timeout_s <= 0:
        parser.error("all timeout values must be positive")
    if args.rung not in {"real-gates", "scillm-one-plus-real-gates"} and (
        args.include_panel_repair or args.include_voice_clone
    ):
        parser.error("optional real gates are valid only for a rung that executes real gates")
    if args.rung in {"scillm-one", "scillm-two-concurrent", "scillm-one-plus-real-gates"}:
        try:
            validate_loopback_base_url(args.scillm_base_url)
        except ValueError as exc:
            parser.error(str(exc))

    run_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir
        else stable_run_directory(args.artifact_root, args.rung)
    )
    if run_dir.exists() and any(run_dir.iterdir()):
        parser.error(f"output directory is not empty: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)
    context_dir = run_dir / "context"
    context_dir.mkdir(parents=True, exist_ok=True)
    graph_path = run_dir / "graph.yaml"
    state_path = run_dir / "state.json"
    summary_path = context_dir / "proof-summary.json"

    gates = selected_real_gates(
        include_panel_repair=args.include_panel_repair,
        include_voice_clone=args.include_voice_clone,
    )
    script = Path(__file__).resolve()
    graph, evidence_receipts = build_graph(
        rung=args.rung,
        script=script,
        python_exe=args.python,
        context_dir=context_dir,
        persona_dream_dir=args.persona_dream_dir.expanduser().resolve(),
        run_root=args.run_root.expanduser().resolve(),
        gates=gates,
        fast_timeout_s=args.fast_timeout_s,
        repair_timeout_s=args.repair_timeout_s,
        scillm_base_url=args.scillm_base_url,
        scillm_model=args.scillm_model,
        scillm_timeout_s=args.scillm_timeout_s,
        scillm_api_key_env=args.scillm_api_key_env,
    )
    dump_graph_yaml(graph_path, graph)

    started_utc = utc_now()
    try:
        state = asyncio.run(
            run_serial_graph(
                graph_path,
                run_dir=run_dir,
                state_path=state_path,
                stream_json=args.stream_json,
            )
        )
        orchestration_error: dict[str, str] | None = None
    except Exception as exc:
        state = {
            "schema": SCHEMA_STATE,
            "graph_id": graph.get("graph_id"),
            "terminal_status": "fail",
            "nodes": {},
        }
        orchestration_error = {
            "type": type(exc).__name__,
            "message": redact_error_message(str(exc)),
        }
        write_json_atomic(state_path, state)

    summary = {
        "schema": SCHEMA_SUMMARY,
        "status": "PASS" if state.get("terminal_status") == "pass" and orchestration_error is None else "FAIL",
        "rung": args.rung,
        "proof_scope": graph["proof_scope"],
        "started_utc": started_utc,
        "finished_utc": utc_now(),
        "execution_model": graph["execution_model"],
        "claims": graph["claims"],
        "run_root": str(args.run_root.expanduser().resolve()) if "real-gates" in args.rung else None,
        "selected_gates": gates if "real-gates" in args.rung else [],
        "scillm": {
            "base_url": args.scillm_base_url if "scillm" in args.rung else None,
            "model": args.scillm_model if "scillm" in args.rung else None,
            "api_key_env": args.scillm_api_key_env if "scillm" in args.rung else None,
            "local_scillm_call_authorized": "scillm" in args.rung,
            "external_provider_call_authorized": False,
            "paid_call_authorized": False,
            "network_isolation_proven": False,
        },
        "terminal_node": state.get("terminal_node"),
        "terminal_status": state.get("terminal_status"),
        "node_statuses": {
            node_id: result.get("status") for node_id, result in (state.get("nodes") or {}).items()
        },
        "evidence_receipts": [str(path) for path in evidence_receipts],
        "graph_path": str(graph_path),
        "state_path": str(state_path),
        "events_path": str(context_dir / "dag-events.jsonl"),
        "output_dir": str(run_dir),
        "orchestration_error": orchestration_error,
    }
    write_json_atomic(summary_path, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["status"] == "PASS" else 1


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments:
        internal = arguments[0]
        rest = arguments[1:]
        if internal == "_node-scillm-batch":
            return node_scillm_batch(rest)
        if internal == "_node-real-gate":
            return node_real_gate(rest)
        if internal == "_node-aggregate-real-gates":
            return node_aggregate_real_gates(rest)
        if internal == "_node-verify-receipts":
            return node_verify_receipts(rest)
        if internal == "_node-fixture":
            return node_fixture(rest)
    return public_main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
