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
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

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
    spec_file = output_root / f"{task_id}-spec.json"
    subagent_prompt = _format_subagent_oracle_prompt(prompt)

    command = [
        "codex",
        "exec",
        "--model",
        model,
        "-c",
        f'reasoning_effort="{reasoning_effort}"',
        "--sandbox",
        "read-only",
        "--cd",
        str(Path.cwd()),
        "--output-last-message",
        str(answer_file),
        "--color",
        "never",
        subagent_prompt,
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
            "ASK_ORACLE_IDLE_TIMEOUT": str(idle_timeout),
            "ASK_ORACLE_HEARTBEAT_INTERVAL": str(heartbeat_interval),
            "SUBAGENT_RUNNER_IDLE_MODE": "heartbeat",
            "SUBAGENT_RUNNER_HEARTBEAT_INTERVAL": str(heartbeat_interval),
        },
        "tags": ["ask", "oracle", "subagent-runner", model, reasoning_effort],
    }
    spec_file.write_text(json.dumps(spec, indent=2))

    started = subprocess.run(
        [str(runner), "start", str(spec_file)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if started.returncode != 0:
        raise RuntimeError(f"subagent-runner start failed: {started.stderr.strip()}")

    start_data = json.loads(started.stdout)
    artifact_dir = str(start_data["artifact_dir"])
    state = _wait_for_subagent_session(
        runner,
        artifact_dir,
        timeout,
        heartbeat_interval=heartbeat_interval,
        task_id=task_id,
        persona=persona,
        model=model,
        turn_number=turn_number,
    )
    if state.get("status") != "completed":
        transcript = _read_subagent_transcript(artifact_dir)
        raise RuntimeError(
            f"subagent-runner session {state.get('status')}: "
            f"{state.get('status_reason', '')}\n{transcript[-2000:]}"
        )

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


def _looks_like_hook_pollution(content: str) -> bool:
    lowered = content.lower()
    return any(
        marker in lowered
        for marker in (
            "cdp verification hook",
            ".codex/ui-verification",
            "no rendered ui target",
            "no real target url",
            "ui verification marker",
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
    heartbeat_interval: float,
    task_id: str,
    persona: str,
    model: str,
    turn_number: int,
) -> dict:
    """Follow /subagent-runner event stream until terminal state."""
    terminal_statuses = {"completed", "failed", "cancelled", "timed_out", "stalled"}
    deadline = time.time() + timeout + 15
    last_state: dict = {}
    events_path = Path(artifact_dir) / "events.jsonl"
    status_path = Path(artifact_dir) / "status.json"
    event_position = 0
    next_heartbeat_at = 0.0
    heartbeat_interval = max(5.0, heartbeat_interval)
    while time.time() < deadline:
        now = time.time()
        event_seen = False
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
                    event_seen = True
                    last_state = _read_subagent_state(status_path, fallback_status=event.get("status"))
                    kind = str(event.get("kind", "event"))
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
                    if last_state.get("status") in terminal_statuses:
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
) -> tuple[str, str]:
    """Make one scillm oracle completion call."""
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
    }
    response = httpx.post(
        f"{SCILLM_BASE_URL.rstrip('/')}/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {SCILLM_API_KEY}",
            "X-Caller-Skill": "ask",
        },
        json=body,
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"], data.get("model", model)


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
