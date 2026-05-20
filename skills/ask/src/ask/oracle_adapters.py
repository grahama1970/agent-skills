"""Oracle adapter functions for scillm and subagent-runner calls.

This module contains the side-effecting LLM adapter layer used by ask_oracle:
scillm HTTP calls, Codex subagent-runner sessions, heartbeat persistence, and
bounded deliberation transcript formatting. It keeps orchestration policy in
ask_oracle.py while isolating external process/network behavior here.
"""


from .env import load_dotenv_once

load_dotenv_once()
import hashlib
import json
import os
import socket
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
from loguru import logger as log

from .ask_config import (
    DOGPILE_RUN,
    MEMORY_RUN,
    MONITOR_PERSONAS_RUN,
    ORACLE_BACKENDS,
    SCILLM_API_KEY,
    SCILLM_BASE_URL,
    SCILLM_RUN,
    SUBAGENT_OUTPUT_DIR,
    SUBAGENT_RUNNER,
)

def _record_subagent_heartbeat(
    state: dict,
    *,
    artifact_dir: str,
    task_id: str,
    persona: str,
    model: str,
    turn_number: int,
    heartbeat_kind: str,
) -> None:
    """Store sparse subagent liveness snapshots in memory."""
    now = time.time()
    last_output_at = state.get("last_output_at")
    last_output_age_ms = None
    if isinstance(last_output_at, (int, float)):
        last_output_age_ms = max(0, int((now - float(last_output_at)) * 1000))
    transcript_path = Path(artifact_dir) / "transcript.log"
    transcript_bytes = transcript_path.stat().st_size if transcript_path.exists() else 0
    session_id = str(state.get("session_id") or Path(artifact_dir).name)
    document = {
        "_key": hashlib.sha256(f"{session_id}:{heartbeat_kind}:{int(now)}".encode()).hexdigest()[:32],
        "type": "ask_subagent_heartbeat",
        "ts": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
        "task_id": task_id,
        "session_id": session_id,
        "artifact_dir": artifact_dir,
        "persona": persona,
        "model": model,
        "turn_number": turn_number,
        "heartbeat_kind": heartbeat_kind,
        "status": str(state.get("status", "")),
        "status_reason": str(state.get("status_reason", "")),
        "last_output_at": last_output_at,
        "last_output_age_ms": last_output_age_ms,
        "transcript_bytes": transcript_bytes,
        "timeout_seconds": state.get("timeout_seconds"),
        "idle_timeout_seconds": state.get("idle_timeout_seconds"),
    }
    try:
        transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=5.0) as client:
            response = client.post(
                "/upsert",
                json={"collection": "ask_subagent_heartbeat", "documents": [document]},
            )
            response.raise_for_status()
    except Exception as exc:
        log.error("Failed to store subagent heartbeat: %s", exc)

_META_TAGS = frozenset({
    "routing", "global_standard", "pi_harness", "found_false_default",
    "evidence_case", "skill_route",
})

_META_SOURCES = frozenset({"skill_descriptions"})


def _run_oracle_subagent_iterations(
    model: str,
    reasoning_effort: str,
    timeout: float,
    idle_timeout: float,
    heartbeat_interval: float,
    base_prompt: str,
    persona: Optional[str],
    consult_personas: list[dict],
    peer: Optional[str],
    iterations: int,
    persona_model: Optional[str],
    peer_model: Optional[str],
    run_state: Any | None = None,
) -> tuple[str, str, list[dict]]:
    """Run oracle deliberation as focused Codex sessions plus scillm one-shot peers."""
    total_iterations = max(1, iterations)
    peer_name = peer or _default_oracle_peer(consult_personas)
    primary_name = persona or "primary oracle"
    turns: list[dict] = []
    primary_model = persona_model or model

    if total_iterations > 1 and peer and not peer_model and _is_codex_agent_model(primary_model):
        prompt = (
            f"{base_prompt}\n\n"
            "Dynamic persona deliberation:\n"
            f"- Primary persona: {primary_name}\n"
            f"- Peer persona: {peer_name}\n"
            f"- Rounds requested: {total_iterations}\n\n"
            "Use one subagent session and switch personas internally. Start as the primary persona, "
            "then explicitly ask the peer persona for critique where useful, then switch into the peer "
            "persona and answer that critique. Repeat only as needed for the requested rounds. "
            "Produce one final answer that states the strongest conclusion and any unresolved disagreement. "
            "Do not spawn another /ask or subagent session for the peer persona."
        )
        content, artifact_dir = _complete_oracle_subagent_call(
            model=primary_model,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
            idle_timeout=idle_timeout,
            heartbeat_interval=heartbeat_interval,
            prompt=prompt,
            persona=f"{primary_name} with {peer_name}",
            turn_number=1,
            run_state=run_state,
        )
        return content, primary_model, [{
            "iteration": 1,
            "persona": primary_name,
            "peer": peer_name,
            "model": primary_model,
            "backend": "subagent-runner",
            "mode": "dynamic-persona-switch",
            "content": content,
            "artifact_dir": artifact_dir,
        }]

    for index in range(total_iterations):
        turn_number = index + 1
        active_persona = primary_name if index % 2 == 0 else peer_name
        active_model = (persona_model or model) if index % 2 == 0 else (peer_model or model)
        transcript = _format_deliberation_transcript(turns)
        prompt = (
            f"{base_prompt}\n\n"
            "Deliberation transcript so far:\n"
            f"{transcript or '[none]'}\n\n"
            f"Iteration {turn_number}/{total_iterations}. You are {active_persona}. "
            "This is a focused oracle subagent call. Challenge weak assumptions, "
            "incorporate useful prior turns, and return the best current answer. "
            "If this is the final iteration, produce the final answer."
        )
        if _is_codex_agent_model(active_model):
            content, artifact_dir = _complete_oracle_subagent_call(
                model=active_model,
                reasoning_effort=reasoning_effort,
                timeout=timeout,
                idle_timeout=idle_timeout,
                heartbeat_interval=heartbeat_interval,
                prompt=prompt,
                persona=active_persona,
                turn_number=turn_number,
                run_state=run_state,
            )
            turns.append({
                "iteration": turn_number,
                "persona": active_persona,
                "model": active_model,
                "backend": "subagent-runner",
                "content": content,
                "artifact_dir": artifact_dir,
            })
        else:
            content, model_served = _complete_oracle_call(
                model=active_model,
                reasoning_effort=reasoning_effort,
                timeout=timeout,
                prompt=prompt,
                run_state=run_state,
                iteration=turn_number,
                persona=active_persona,
            )
            turns.append({
                "iteration": turn_number,
                "persona": active_persona,
                "model": model_served,
                "backend": "scillm",
                "content": content,
            })

    return turns[-1]["content"], str(turns[-1].get("model", model)), turns


def _complete_oracle_subagent_call(
    model: str,
    reasoning_effort: str,
    timeout: float,
    idle_timeout: float,
    heartbeat_interval: float,
    prompt: str,
    persona: str,
    turn_number: int,
    run_state: Any | None = None,
) -> tuple[str, str]:
    """Start one /subagent-runner Codex exec session and return its final answer."""
    runner = Path(SUBAGENT_RUNNER)
    if not runner.exists():
        raise RuntimeError(f"subagent-runner not found: {runner}")

    output_root = Path(SUBAGENT_OUTPUT_DIR)
    output_root.mkdir(parents=True, exist_ok=True)
    safe_persona = _safe_task_fragment(persona)
    task_id = f"ask-oracle-{safe_persona}-{turn_number}-{int(time.time())}"
    answer_file = output_root / f"{task_id}-answer.txt"
    prompt_file = output_root / f"{task_id}-prompt.md"
    spec_file = output_root / f"{task_id}-spec.json"
    subagent_prompt = _format_subagent_oracle_prompt(prompt)
    prompt_file.write_text(subagent_prompt)
    event_socket, event_socket_path = _open_subagent_event_socket(task_id)

    command = [
        "bash",
        "-lc",
        (
            'codex exec --model "$ASK_ORACLE_MODEL" '
            '-c "reasoning_effort=\\"$ASK_ORACLE_REASONING\\"" '
            '--sandbox read-only '
            '--cd "$ASK_ORACLE_CWD" '
            '--output-last-message "$ASK_ORACLE_ANSWER_FILE" '
            '--color never '
            '- < "$ASK_ORACLE_PROMPT_FILE"'
        ),
    ]
    spec = {
        "task_id": task_id,
        "title": f"/ask oracle {persona} turn {turn_number}",
        "prompt": " ",
        "backend": "codex",
        "command": command,
        "cwd": str(Path.cwd()),
        "output_dir": str(output_root),
        "timeout_seconds": int(timeout),
        "idle_timeout_seconds": int(max(30, min(idle_timeout, timeout))),
        "env": {
            "ASK_ORACLE_MEMORY_RUN": str(Path(MEMORY_RUN)),
            "ASK_ORACLE_SCILLM_RUN": str(Path(SCILLM_RUN)),
            "ASK_ORACLE_DOGPILE_RUN": str(Path(DOGPILE_RUN)),
            "ASK_ORACLE_MONITOR_PERSONAS_RUN": str(Path(MONITOR_PERSONAS_RUN)),
            "SCILLM_BASE_URL": SCILLM_BASE_URL,
            "SCILLM_API_KEY": SCILLM_API_KEY,
            "ASK_ORACLE_MODEL": model,
            "ASK_ORACLE_REASONING": reasoning_effort,
            "ASK_ORACLE_CWD": str(Path.cwd()),
            "ASK_ORACLE_ANSWER_FILE": str(answer_file),
            "ASK_ORACLE_PROMPT_FILE": str(prompt_file),
            "ASK_ORACLE_IDLE_TIMEOUT": str(idle_timeout),
            "ASK_ORACLE_HEARTBEAT_INTERVAL": str(heartbeat_interval),
            "SUBAGENT_RUNNER_FINAL_MESSAGE_FILE": str(answer_file),
            "SUBAGENT_RUNNER_IDLE_MODE": "heartbeat",
            "SUBAGENT_RUNNER_HEARTBEAT_INTERVAL": str(heartbeat_interval),
            "SUBAGENT_RUNNER_EVENT_SOCKET": event_socket_path or "",
        },
        "tags": ["ask", "oracle", "subagent-runner", model, reasoning_effort],
    }
    spec_file.write_text(json.dumps(spec, indent=2))

    try:
        env = {**os.environ}
        if event_socket_path:
            env["SUBAGENT_RUNNER_EVENT_SOCKET"] = event_socket_path
        started = subprocess.run(
            [str(runner), "start", str(spec_file)],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        if started.returncode != 0:
            raise RuntimeError(f"subagent-runner start failed: {started.stderr.strip()}")

        start_data = json.loads(started.stdout)
        artifact_dir = str(start_data["artifact_dir"])
        state = _wait_for_subagent_session(
            runner,
            artifact_dir,
            timeout,
            idle_timeout=idle_timeout,
            heartbeat_interval=heartbeat_interval,
            task_id=task_id,
            persona=persona,
            model=model,
            turn_number=turn_number,
            event_socket=event_socket,
            run_state=run_state,
        )
    finally:
        _close_subagent_event_socket(event_socket, event_socket_path)
    if state.get("status") != "completed":
        transcript = _read_subagent_transcript(artifact_dir)
        raise RuntimeError(
            f"subagent-runner session {state.get('status')}: "
            f"{state.get('status_reason', '')}\n{transcript[-2000:]}"
        )

    result_message = _read_subagent_result_final_message(artifact_dir)
    if result_message:
        return result_message, artifact_dir

    if answer_file.exists():
        content = answer_file.read_text().strip()
        if content:
            if _looks_like_hook_pollution(content):
                transcript_content = _extract_pre_hook_content(_read_subagent_transcript(artifact_dir)).strip()
                if transcript_content:
                    return transcript_content, artifact_dir
            return content, artifact_dir

    transcript = _read_subagent_transcript(artifact_dir).strip()
    if not transcript:
        raise RuntimeError("subagent-runner completed without answer output")
    return transcript, artifact_dir


def _read_subagent_result_final_message(artifact_dir: str) -> str:
    result_path = Path(artifact_dir) / "result.json"
    if not result_path.exists():
        return ""
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    status = str(result.get("final_message_status") or "")
    message = str(result.get("final_message") or "").strip()
    if status in {"ok", "degraded"} and message and not _looks_like_hook_pollution(message):
        return message
    return ""


def _looks_like_hook_pollution(content: str) -> bool:
    lowered = content.lower()
    return any(
        marker in lowered
        for marker in (
            "cdp verification hook",
            "cdp verification",
            "ui cdp verification",
            ".codex/ui-verification",
            "no rendered ui target",
            "no real target url",
            "ui verification marker",
            "hook script",
            "<target-url>",
        )
    )


def _extract_pre_hook_content(transcript: str) -> str:
    if not transcript:
        return ""
    hook_index = transcript.find("\nhook: Stop")
    if hook_index < 0:
        return transcript
    before_hook = transcript[:hook_index].rstrip()
    marker_index = before_hook.rfind("\ncodex\n")
    if marker_index >= 0:
        return before_hook[marker_index + len("\ncodex\n"):].strip()
    return before_hook


def _wait_for_subagent_session(
    runner: Path,
    artifact_dir: str,
    timeout: float,
    *,
    idle_timeout: float,
    heartbeat_interval: float,
    task_id: str,
    persona: str,
    model: str,
    turn_number: int,
    event_socket: socket.socket | None = None,
    run_state: Any | None = None,
) -> dict:
    """Follow /subagent-runner events until terminal state.

    The preferred transport is a parent-owned Unix datagram socket. The
    canonical events.jsonl and status.json files remain the durable fallback.
    """
    terminal_statuses = {"completed", "failed", "cancelled", "timed_out", "stalled"}
    deadline = time.time() + timeout + 15
    event_idle_timeout = max(30.0, float(idle_timeout))
    last_event_at = time.time()
    last_state: dict = {}
    events_path = Path(artifact_dir) / "events.jsonl"
    status_path = Path(artifact_dir) / "status.json"
    event_position = 0
    next_heartbeat_at = 0.0
    heartbeat_interval = max(5.0, heartbeat_interval)
    seen_events: set[str] = set()

    def process_event(event: dict[str, Any]) -> bool:
        nonlocal last_state, last_event_at
        event_key = json.dumps(event, sort_keys=True, default=str)
        if event_key in seen_events:
            return False
        seen_events.add(event_key)
        last_event_at = time.time()
        last_state = _read_subagent_state(status_path, fallback_status=event.get("status"))
        kind = str(event.get("kind", "event"))
        _mirror_subagent_event(
            run_state,
            event,
            state=last_state,
            artifact_dir=artifact_dir,
            task_id=task_id,
            persona=persona,
            model=model,
            turn_number=turn_number,
        )
        terminal_status = str(last_state.get("status") or "")
        if terminal_status in terminal_statuses and kind not in {
            "session_completed",
            "session_failed",
            "session_cancelled",
            "session_timed_out",
            "session_stalled",
        }:
            _mirror_subagent_event(
                run_state,
                {
                    "kind": _event_kind_for_terminal_status(terminal_status),
                    "status": terminal_status,
                    "payload": {
                        "exit_code": last_state.get("exit_code"),
                        "summary": last_state.get("status_reason"),
                    },
                },
                state=last_state,
                artifact_dir=artifact_dir,
                task_id=task_id,
                persona=persona,
                model=model,
                turn_number=turn_number,
            )
        if kind in {
            "session_started",
            "session_heartbeat",
            "session_completed",
            "session_failed",
            "session_cancelled",
            "session_timed_out",
            "session_stalled",
        }:
            _record_subagent_heartbeat(
                last_state,
                artifact_dir=artifact_dir,
                task_id=task_id,
                persona=persona,
                model=model,
                turn_number=turn_number,
                heartbeat_kind=f"event:{kind}",
            )
        return True

    while time.time() < deadline:
        now = time.time()
        event_seen = False
        for event in _drain_subagent_event_socket(event_socket):
            event_seen = process_event(event) or event_seen
            if last_state.get("status") in terminal_statuses:
                return last_state
        if events_path.exists():
            with events_path.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(event_position)
                while True:
                    line_start = event_position
                    line = handle.readline()
                    if not line:
                        break
                    event_position = handle.tell()
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        event_position = line_start
                        break
                    event_seen = process_event(event) or event_seen
                    if last_state.get("status") in terminal_statuses:
                        return last_state

        if now - last_event_at > event_idle_timeout:
            subprocess.run([str(runner), "cancel", artifact_dir], capture_output=True, text=True, timeout=15)
            last_state = _read_subagent_state(status_path)
            last_state["status"] = "stalled"
            last_state["status_reason"] = f"no subagent events for {event_idle_timeout:g}s"
            _mirror_subagent_event(
                run_state,
                {
                    "kind": "controller_stalled",
                    "status": "stalled",
                    "payload": {"idle_for_seconds": round(now - last_event_at, 3)},
                },
                state=last_state,
                artifact_dir=artifact_dir,
                task_id=task_id,
                persona=persona,
                model=model,
                turn_number=turn_number,
            )
            _record_subagent_heartbeat(
                last_state,
                artifact_dir=artifact_dir,
                task_id=task_id,
                persona=persona,
                model=model,
                turn_number=turn_number,
                heartbeat_kind="controller_idle_timeout",
            )
            return last_state

        if now >= next_heartbeat_at:
            last_state = _read_subagent_state(status_path)
            _record_subagent_heartbeat(
                last_state,
                artifact_dir=artifact_dir,
                task_id=task_id,
                persona=persona,
                model=model,
                turn_number=turn_number,
                heartbeat_kind="controller_wait",
            )
            next_heartbeat_at = now + heartbeat_interval
        if last_state.get("status") in terminal_statuses:
            terminal_status = str(last_state.get("status"))
            _mirror_subagent_event(
                run_state,
                {
                    "kind": _event_kind_for_terminal_status(terminal_status),
                    "status": terminal_status,
                    "payload": {
                        "exit_code": last_state.get("exit_code"),
                        "summary": last_state.get("status_reason"),
                    },
                },
                state=last_state,
                artifact_dir=artifact_dir,
                task_id=task_id,
                persona=persona,
                model=model,
                turn_number=turn_number,
            )
            _record_subagent_heartbeat(
                last_state,
                artifact_dir=artifact_dir,
                task_id=task_id,
                persona=persona,
                model=model,
                turn_number=turn_number,
                heartbeat_kind="terminal",
            )
            return last_state
        time.sleep(0.25 if event_seen else 1)

    subprocess.run([str(runner), "cancel", artifact_dir], capture_output=True, text=True, timeout=15)
    last_state["status"] = "timed_out"
    last_state["status_reason"] = f"controller timed out after {timeout}s"
    _mirror_subagent_event(
        run_state,
        {"kind": "controller_timed_out", "status": "timed_out", "payload": {"timeout_seconds": timeout}},
        state=last_state,
        artifact_dir=artifact_dir,
        task_id=task_id,
        persona=persona,
        model=model,
        turn_number=turn_number,
    )
    _record_subagent_heartbeat(
        last_state,
        artifact_dir=artifact_dir,
        task_id=task_id,
        persona=persona,
        model=model,
        turn_number=turn_number,
        heartbeat_kind="controller_timeout",
    )
    return last_state


def _open_subagent_event_socket(task_id: str) -> tuple[socket.socket | None, str | None]:
    socket_path = Path(tempfile.gettempdir()) / f"ask-subagent-events-{hashlib.sha256(task_id.encode()).hexdigest()[:16]}.sock"
    server: socket.socket | None = None
    try:
        if socket_path.exists():
            socket_path.unlink()
        server = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        server.bind(str(socket_path))
        server.setblocking(False)
        return server, str(socket_path)
    except OSError:
        if server is not None:
            try:
                server.close()
            except Exception:
                pass
        return None, None


def _close_subagent_event_socket(event_socket: socket.socket | None, socket_path: str | None) -> None:
    if event_socket is not None:
        try:
            event_socket.close()
        except OSError:
            pass
    if socket_path:
        try:
            Path(socket_path).unlink()
        except OSError:
            pass


def _drain_subagent_event_socket(event_socket: socket.socket | None) -> list[dict[str, Any]]:
    if event_socket is None:
        return []
    events: list[dict[str, Any]] = []
    while True:
        try:
            data = event_socket.recv(1024 * 1024)
        except BlockingIOError:
            break
        except OSError:
            break
        if not data:
            break
        try:
            event = json.loads(data.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _mirror_subagent_event(
    run_state: Any | None,
    event: dict[str, Any],
    *,
    state: dict[str, Any],
    artifact_dir: str,
    task_id: str,
    persona: str,
    model: str,
    turn_number: int,
) -> None:
    if run_state is None or getattr(run_state, "disabled", False):
        return
    kind = str(event.get("kind", "event"))
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    subagent = {
        "task_id": task_id,
        "session_id": str(state.get("session_id") or Path(artifact_dir).name),
        "artifact_dir": artifact_dir,
        "persona": persona,
        "model": model,
        "turn_number": turn_number,
        "last_event": kind,
        "status": str(state.get("status") or event.get("status") or "unknown"),
        "status_reason": str(state.get("status_reason") or ""),
        "transcript_bytes": payload.get("transcript_bytes"),
        "last_output_at": state.get("last_output_at"),
    }
    try:
        run_state.event(
            f"subagent_{kind}",
            subagent=subagent,
            child_payload=_safe_child_payload(kind, payload),
        )
        run_state.update(
            "running",
            current_step="synthesis",
            subagent=subagent,
        )
    except Exception as exc:
        log.warning("Failed to mirror subagent event into ask run state: %s", exc)


def _safe_child_payload(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Keep parent runtime events useful without copying prompts/transcripts."""
    if kind == "transcript_delta":
        return {
            "bytes": payload.get("bytes"),
            "transcript_bytes": payload.get("transcript_bytes"),
        }
    if kind == "session_heartbeat":
        return {
            "pid": payload.get("pid"),
            "process_alive": payload.get("process_alive"),
            "idle_for_seconds": payload.get("idle_for_seconds"),
        }
    if kind == "session_started":
        return {
            "pid": payload.get("pid"),
            "pty_device": payload.get("pty_device"),
            "command_argv_count": len(payload.get("command") or []) if isinstance(payload.get("command"), list) else None,
        }
    if kind in {"session_completed", "session_failed", "session_cancelled", "session_timed_out", "session_stalled"}:
        return {
            "exit_code": payload.get("exit_code"),
            "summary": payload.get("summary"),
        }
    return {
        key: value
        for key, value in payload.items()
        if key not in {"command", "prompt", "transcript", "stdout", "stderr"}
        and isinstance(value, (str, int, float, bool, type(None)))
    }


def _event_kind_for_terminal_status(status: str) -> str:
    return {
        "completed": "session_completed",
        "failed": "session_failed",
        "cancelled": "session_cancelled",
        "timed_out": "session_timed_out",
        "stalled": "session_stalled",
    }.get(status, "session_terminal")


def _read_subagent_state(status_path: Path, *, fallback_status: object | None = None) -> dict:
    if status_path.exists():
        for _ in range(3):
            try:
                return json.loads(status_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                time.sleep(0.05)
    return {"status": fallback_status or "unknown", "status_reason": "status file not yet available"}


def _read_subagent_transcript(artifact_dir: str) -> str:
    """Read a subagent transcript if present."""
    transcript_path = Path(artifact_dir) / "transcript.log"
    if not transcript_path.exists():
        return ""
    return transcript_path.read_text(encoding="utf-8", errors="replace")


def _format_subagent_oracle_prompt(prompt: str) -> str:
    """Add mandatory memory-access instructions for focused oracle subagents."""
    memory_path = Path(MEMORY_RUN)
    scillm_path = Path(SCILLM_RUN)
    dogpile_path = Path(DOGPILE_RUN)
    monitor_personas_path = Path(MONITOR_PERSONAS_RUN)
    return (
        "You are an /ask oracle subagent running inside pi-mono.\n"
        "Your core skill tool belt is /memory, /scillm, /dogpile, and /monitor-personas.\n"
        "You are not limited to the packaged prompt context. You MUST use /memory when the answer depends on stored facts, personas, persona lessons, persona lore, prior lessons, or database state.\n"
        "Use /scillm for focused one-shot model checks when another model perspective is useful. Use /dogpile only when fresh external discovery is needed.\n"
        "Core command patterns:\n"
        f"  {memory_path} recall --q \"your focused query\"\n"
        f"  {scillm_path} warm-check --json\n"
        f"  {dogpile_path} --help\n"
        f"  {monitor_personas_path} readiness --json\n"
        f"  {monitor_personas_path} list-personas --json\n"
        "If the user asks for a persona such as Brandon, Horus, Embry, or another stored persona, query /memory for the actual persona profile before answering.\n"
        "If no persona is specified and the question appears to need a specialist perspective, use /memory recall as the primary selector because it combines semantic, BM25, and graph traversal over persona lessons/lore. Use /monitor-personas only as an optional readiness/ops check. State which persona you selected and why. If no ready persona fits, answer as the generic oracle.\n"
        "Persona runs must assume the persona may have lessons and lore. Query /memory for the persona profile, persona lessons, and persona lore before answering from that persona's perspective.\n"
        "Useful persona memory queries include: \"Persona: <name>\", \"<name> persona lessons\", \"<name> persona lore\", and \"<name> lessons learned\".\n"
        "If the conversation produces a durable, reusable lesson, you MAY store it with /memory learn. Keep it concise, grounded, and tagged to the persona/task; do not store transient chatter or secrets.\n"
        f"  {memory_path} learn --problem \"meaningful lesson trigger\" --solution \"durable lesson\" --scope pi-mono --tag ask --tag persona\n"
        "If you are blocked or unsure and a peer persona is provided in the deliberation context, ask that peer by addressing the uncertainty in your turn; do not recursively launch /ask unless the user explicitly requested recursive calls.\n"
        "Do not modify files, commit, push, or run broad scans. Use memory recall for database knowledge and only inspect local files if the prompt explicitly requires file-level evidence.\n"
        "Do not use /dogpile for private/internal facts that should be in /memory. Do not use /scillm for batch loops. In your final answer, state when you used retrieved memory context, scillm peer checks, dogpile discovery, or inference.\n\n"
        f"{prompt}"
    )


def _resolve_oracle_backend(
    backend: str,
    iterations: int,
    persona: Optional[str],
    peer: Optional[str],
    consult_personas: list[dict],
) -> str:
    """Resolve auto oracle backend selection."""
    if backend not in ORACLE_BACKENDS:
        raise ValueError(f"Unknown oracle backend '{backend}'. Valid: {', '.join(sorted(ORACLE_BACKENDS))}")
    if backend != "auto":
        return backend
    if iterations > 1 or persona or peer or consult_personas:
        return "subagent-runner"
    return "scillm"


def _safe_task_fragment(value: str) -> str:
    """Create a conservative session id fragment."""
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned[:40] or "oracle"


def _is_codex_agent_model(model: str) -> bool:
    """Return True when a model should run through a Codex CLI agent session."""
    lowered = model.lower()
    return lowered.startswith("gpt-") or lowered.startswith("codex-")


def _complete_oracle_call(
    model: str,
    reasoning_effort: str,
    timeout: float,
    prompt: str,
    run_state: object | None = None,
    iteration: int | None = None,
    persona: str | None = None,
) -> tuple[str, str]:
    """Make one scillm oracle completion call."""
    event_payload = {
        "backend": "scillm",
        "model": model,
        "reasoning_effort": reasoning_effort,
        "timeout_seconds": timeout,
    }
    if iteration is not None:
        event_payload["iteration"] = iteration
    if persona:
        event_payload["persona"] = persona
    if run_state is not None and hasattr(run_state, "event"):
        run_state.event("oracle_scillm_call_started", **event_payload)
    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are the /ask oracle synthesis pass. Use maximum available reasoning "
                    "for one final answer. Do not invent source support; distinguish retrieved "
                    "knowledge from inference."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "reasoning_effort": reasoning_effort,
        "stream": True,
        "stream_progress_events": True,
        "timeout": timeout,
        "stream_heartbeat_s": max(5.0, min(15.0, float(timeout) / 20.0)),
    }
    try:
        content_parts: list[str] = []
        model_served = model
        saw_done = False
        last_progress_at = time.monotonic()
        heartbeat_interval = float(body["stream_heartbeat_s"])
        timeout_config = httpx.Timeout(
            float(timeout),
            connect=min(10.0, float(timeout)),
            read=max(30.0, heartbeat_interval * 3.0),
            write=30.0,
            pool=10.0,
        )
        with httpx.stream(
            "POST",
            f"{SCILLM_BASE_URL.rstrip('/')}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {SCILLM_API_KEY}",
                "X-Caller-Skill": "ask",
            },
            json=body,
            timeout=timeout_config,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                if line.startswith(":"):
                    now = time.monotonic()
                    if now - last_progress_at >= heartbeat_interval and run_state is not None and hasattr(run_state, "event"):
                        run_state.event(
                            "oracle_scillm_stream_progress",
                            **event_payload,
                            model_served=model_served,
                            content_chars=sum(len(part) for part in content_parts),
                            heartbeat=True,
                        )
                        last_progress_at = now
                    continue
                if not line.startswith("data:"):
                    continue
                data_text = line[len("data:"):].strip()
                if data_text == "[DONE]":
                    saw_done = True
                    break
                try:
                    data = json.loads(data_text)
                except json.JSONDecodeError:
                    continue
                if data.get("error"):
                    raise RuntimeError(str(data["error"]))
                model_served = str(data.get("model") or model_served)
                choices = data.get("choices") or []
                if choices and isinstance(choices[0], dict):
                    choice = choices[0]
                    delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
                    message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
                    content = delta.get("content")
                    if content is None:
                        content = message.get("content")
                    if content:
                        content_parts.append(str(content))
                now = time.monotonic()
                if now - last_progress_at >= heartbeat_interval and run_state is not None and hasattr(run_state, "event"):
                    run_state.event(
                        "oracle_scillm_stream_progress",
                        **event_payload,
                        model_served=model_served,
                        content_chars=sum(len(part) for part in content_parts),
                    )
                    last_progress_at = now
        content = "".join(content_parts)
        if not saw_done and not content:
            raise RuntimeError("scillm stream ended without content or [DONE]")
        if run_state is not None and hasattr(run_state, "event"):
            run_state.event(
                "oracle_scillm_call_finished",
                **event_payload,
                model_served=model_served,
                stream=True,
                content_chars=len(content),
            )
        return content, model_served
    except Exception as exc:
        if run_state is not None and hasattr(run_state, "event"):
            run_state.event(
                "oracle_scillm_call_failed",
                **event_payload,
                error_type=type(exc).__name__,
                error=str(exc)[:500],
            )
        raise


def _default_oracle_peer(consult_personas: list[dict]) -> str:
    """Choose a deliberation peer from suggested personas or a generic critic."""
    if consult_personas:
        return str(consult_personas[0].get("name", "critical reviewer"))
    return "critical reviewer"


def _format_deliberation_transcript(turns: list[dict], max_chars: int = 12000) -> str:
    """Render prior oracle turns into bounded context."""
    text = "\n\n".join(
        f"[{turn['iteration']}] {turn['persona']}:\n{turn['content']}"
        for turn in turns
    )
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]
