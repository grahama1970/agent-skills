#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import shlex
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import typer


app = typer.Typer(help="Round-based alignment lock generator.")

DEFAULT_ROOT = Path(".align")
QUESTION_RE = re.compile(r"(?:^|\b)(Question|Q)\[(blocking|nonblocking)\]\s*:\s*(.+)", re.IGNORECASE)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict:
    if not path.exists():
        raise typer.BadParameter(f"Missing required file: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise typer.BadParameter(f"Expected JSON object in {path}")
    return data


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def state_path(root: Path) -> Path:
    return root / "alignment_state.json"


def brief_path(root: Path) -> Path:
    return root / "alignment_brief.md"


def load_state(root: Path) -> dict:
    return read_json(state_path(root))


def save_state(root: Path, state: dict) -> None:
    state["updated_at"] = utc_now()
    write_json(state_path(root), state)


def normalize_participant(name: str) -> str:
    clean = name.strip().lower().replace("-", "_")
    if not clean:
        raise typer.BadParameter("Participant must not be empty")
    if not re.fullmatch(r"[a-z][a-z0-9_]*", clean):
        raise typer.BadParameter(f"Invalid participant name: {name}")
    return clean


def round_dir(root: Path, round_number: int) -> Path:
    if round_number < 1:
        raise typer.BadParameter("Round must be >= 1")
    return root / "rounds" / f"round-{round_number:03d}"


def render_brief(state: dict) -> str:
    lines = [
        f"# Alignment Brief: {state['goal']}",
        "",
        f"- Schema: `{state['schema']}`",
        f"- Status: `{state['status']}`",
        f"- Created: {state['created_at']}",
        f"- Updated: {state['updated_at']}",
        f"- Max rounds: {state['max_rounds']}",
        f"- Current round: {state['current_round']}",
        "",
        "## Goal",
        "",
        state["goal"],
        "",
        "## Output Shape",
        "",
        state["output_shape"],
        "",
        "## Participants",
        "",
    ]
    for participant in state["participants"]:
        lines.append(f"- `{participant}`")
    if state.get("webgpt_tab_id"):
        lines.extend(["", f"WebGPT tab id: `{state['webgpt_tab_id']}`"])
    lines.extend(["", "## Source Context", ""])
    for source in state.get("source_context", []):
        lines.append(f"- {source}")
    lines.extend(["", "## Acceptance Criteria", ""])
    for criterion in state.get("acceptance_criteria", []):
        lines.append(f"- {criterion}")
    lines.extend(["", "## Open Questions", ""])
    questions = state.get("open_questions", [])
    if questions:
        for question in questions:
            status = "blocking" if question.get("blocking") else "nonblocking"
            answered = "answered" if question.get("answered") else "open"
            lines.append(f"- [{answered}] ({status}) {question['question']}")
    else:
        lines.append("- none recorded")
    lines.append("")
    return "\n".join(lines)


@app.command()
def init(
    goal: Annotated[str, typer.Option("--goal", help="Human-facing task goal.")],
    output_shape: Annotated[str, typer.Option("--output-shape", help="Expected output artifact shape.")],
    root: Annotated[Path, typer.Option("--root", help="Alignment artifact root.")] = DEFAULT_ROOT,
    participant: Annotated[list[str], typer.Option("--participant", help="Participant to include.")] = None,
    source_context: Annotated[list[str], typer.Option("--source", help="Known source path, command, or artifact.")] = None,
    acceptance_criteria: Annotated[list[str], typer.Option("--acceptance", help="Acceptance criterion.")] = None,
    max_rounds: Annotated[int, typer.Option("--max-rounds", help="Maximum alignment rounds.")] = 3,
    webgpt_tab_id: Annotated[str | None, typer.Option("--webgpt-tab-id", help="Known WebGPT tab id.")] = None,
    overwrite: Annotated[bool, typer.Option("--overwrite", help="Replace an existing alignment root.")] = False,
) -> None:
    if root.exists() and any(root.iterdir()) and not overwrite:
        raise typer.BadParameter(f"{root} already exists; use --overwrite to replace it")
    root.mkdir(parents=True, exist_ok=True)
    participants = [normalize_participant(p) for p in (participant or ["human", "project_agent"])]
    state = {
        "schema": "align.state.v1",
        "status": "collecting",
        "goal": goal,
        "output_shape": output_shape,
        "participants": participants,
        "source_context": source_context or [],
        "acceptance_criteria": acceptance_criteria or [],
        "max_rounds": max_rounds,
        "current_round": 1,
        "webgpt_tab_id": webgpt_tab_id,
        "open_questions": [],
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    save_state(root, state)
    brief_path(root).write_text(render_brief(state), encoding="utf-8")
    round_dir(root, 1).mkdir(parents=True, exist_ok=True)
    typer.echo(f"Initialized alignment at {root}")


@app.command("add-response")
def add_response(
    participant: Annotated[str, typer.Option("--participant", help="Participant name.")],
    round_number: Annotated[int, typer.Option("--round", help="Round number.")] = 1,
    root: Annotated[Path, typer.Option("--root", help="Alignment artifact root.")] = DEFAULT_ROOT,
    text: Annotated[str | None, typer.Option("--text", help="Inline response text.")] = None,
    file: Annotated[Path | None, typer.Option("--file", help="Path to response text.")] = None,
) -> None:
    state = load_state(root)
    participant_name = normalize_participant(participant)
    if participant_name not in state["participants"]:
        state["participants"].append(participant_name)
    if (text is None) == (file is None):
        raise typer.BadParameter("Provide exactly one of --text or --file")
    response_text = text if text is not None else file.read_text(encoding="utf-8")
    out = round_dir(root, round_number) / f"participant-{participant_name}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(response_text.rstrip() + "\n", encoding="utf-8")
    state["current_round"] = max(state["current_round"], round_number)
    save_state(root, state)
    typer.echo(f"Recorded {participant_name} response at {out}")


def extract_questions(text: str, participant: str) -> list[dict]:
    questions = []
    for match in QUESTION_RE.finditer(text):
        kind = match.group(2).lower()
        question = match.group(3).strip()
        questions.append({
            "id": sha256_text(f"{participant}:{kind}:{question}")[:12],
            "participant": participant,
            "question": question,
            "blocking": kind == "blocking",
            "answered": False,
        })
    return questions


@app.command("compile-round")
def compile_round(
    round_number: Annotated[int, typer.Option("--round", help="Round number.")] = 1,
    root: Annotated[Path, typer.Option("--root", help="Alignment artifact root.")] = DEFAULT_ROOT,
) -> None:
    state = load_state(root)
    rdir = round_dir(root, round_number)
    if not rdir.exists():
        raise typer.BadParameter(f"Round directory does not exist: {rdir}")
    response_files = sorted(rdir.glob("participant-*.md"))
    if not response_files:
        raise typer.BadParameter(f"No participant responses found in {rdir}")
    all_questions = []
    summary_lines = [f"# Round {round_number:03d} Summary", ""]
    for response_file in response_files:
        participant = response_file.stem.removeprefix("participant-")
        response = response_file.read_text(encoding="utf-8")
        digest = sha256_text(response)
        summary_lines.extend([f"## {participant}", "", f"- Response SHA-256: `{digest}`", ""])
        all_questions.extend(extract_questions(response, participant))
    existing = {q["id"]: q for q in state.get("open_questions", [])}
    for question in all_questions:
        existing.setdefault(question["id"], question)
    state["open_questions"] = list(existing.values())
    save_state(root, state)
    write_json(rdir / "questions.json", {"schema": "align.questions.v1", "questions": all_questions})
    (rdir / "round_summary.md").write_text("\n".join(summary_lines), encoding="utf-8")
    brief_path(root).write_text(render_brief(state), encoding="utf-8")
    typer.echo(f"Compiled round {round_number:03d}: {len(all_questions)} question(s)")


@app.command("answer-question")
def answer_question(
    question_id: Annotated[str, typer.Option("--id", help="Question id.")],
    answer: Annotated[str, typer.Option("--answer", help="Answer text.")],
    root: Annotated[Path, typer.Option("--root", help="Alignment artifact root.")] = DEFAULT_ROOT,
) -> None:
    state = load_state(root)
    found = False
    for question in state.get("open_questions", []):
        if question["id"] == question_id:
            question["answered"] = True
            question["answer"] = answer
            question["answered_at"] = utc_now()
            found = True
            break
    if not found:
        raise typer.BadParameter(f"Question id not found: {question_id}")
    save_state(root, state)
    brief_path(root).write_text(render_brief(state), encoding="utf-8")
    typer.echo(f"Answered question {question_id}")


@app.command("prepare-review")
def prepare_review(
    reviewer: Annotated[str, typer.Option("--reviewer", help="scillm, ask, dogpile, or webgpt.")],
    round_number: Annotated[int, typer.Option("--round", help="Round number.")] = 1,
    root: Annotated[Path, typer.Option("--root", help="Alignment artifact root.")] = DEFAULT_ROOT,
    webgpt_tab_id: Annotated[str | None, typer.Option("--webgpt-tab-id", help="WebGPT tab id.")] = None,
    scillm_model: Annotated[str, typer.Option("--scillm-model", help="scillm model for direct model review.")] = "gpt-5.5",
    reasoning_effort: Annotated[str, typer.Option("--reasoning-effort", help="Reasoning effort for scillm review.")] = "high",
    persona_prompt: Annotated[str | None, typer.Option("--persona-prompt", help="Optional system/persona prompt for scillm review.")] = None,
) -> None:
    state = load_state(root)
    reviewer_name = normalize_participant(reviewer)
    if reviewer_name not in {"scillm", "ask", "dogpile", "webgpt"}:
        raise typer.BadParameter("--reviewer must be one of: scillm, ask, dogpile, webgpt")
    brief = brief_path(root).read_text(encoding="utf-8")
    prompt = (
        "Review this alignment brief. Return: understood goal, missing facts, "
        "contradictions, blocking questions, non-blocking questions, and whether "
        "the brief is ready for execution. Do not implement the task.\n\n"
        f"{brief}"
    )
    out_dir = root / "reviews"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"round-{round_number:03d}-{reviewer_name}-request"
    if reviewer_name == "scillm":
        system_prompt = persona_prompt or (
            "You are an alignment reviewer. Your job is to reconcile context "
            "between the human, project agent, memory, project knowledge, and "
            "external reviewers. Do not implement the task. Identify blockers, "
            "contradictions, assumptions, and the smallest next clarification."
        )
        payload = {
            "model": scillm_model,
            "reasoning_effort": reasoning_effort,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "scillm_metadata": {
                "caller": "align",
                "round": round_number,
                "goal_sha256": sha256_text(state["goal"]),
                "reviewer_lane": "scillm",
            },
        }
        request_path = out_dir / f"{stem}.json"
        write_json(request_path, payload)
        command = [
            "curl",
            "-s",
            "http://localhost:4001/v1/chat/completions",
            "-H",
            "Authorization: Bearer sk-dev-proxy-123",
            "-H",
            "X-Caller-Skill: align",
            "-H",
            "Content-Type: application/json",
            "-d",
            f"@{request_path}",
        ]
        command_text = "#!/usr/bin/env bash\nset -euo pipefail\n" + " ".join(shlex.quote(part) for part in command) + "\n"
        command_path = out_dir / f"round-{round_number:03d}-scillm-command.sh"
        command_path.write_text(command_text, encoding="utf-8")
        command_path.chmod(0o755)
    else:
        tab = webgpt_tab_id or state.get("webgpt_tab_id")
        if reviewer_name == "dogpile":
            prompt = (
                "Research only the external/current facts needed to unblock this "
                "alignment brief. Return sources, what they establish, what remains "
                "unknown, and questions the human or project agent must answer. "
                "Do not design or implement the final task.\n\n"
                f"{brief}"
            )
        extra = f"\n\nWebGPT tab id: {tab}" if reviewer_name == "webgpt" and tab else ""
        request_path = out_dir / f"{stem}.md"
        request_path.write_text(prompt + extra + "\n", encoding="utf-8")
        if reviewer_name == "webgpt":
            command = [
                "skills/ask/run.sh",
                "ask",
                "webgpt",
                f"Review the alignment request at {request_path}",
            ]
            if tab:
                command.extend(["--webgpt-tab-id", str(tab)])
            command.extend(["--oracle-iterations", "1"])
            command_text = "#!/usr/bin/env bash\nset -euo pipefail\n" + " ".join(shlex.quote(part) for part in command) + "\n"
            command_path = out_dir / f"round-{round_number:03d}-webgpt-ask-command.sh"
            command_path.write_text(command_text, encoding="utf-8")
            command_path.chmod(0o755)
    typer.echo(f"Wrote {reviewer_name} request under {out_dir}")


@app.command()
def lock(
    root: Annotated[Path, typer.Option("--root", help="Alignment artifact root.")] = DEFAULT_ROOT,
    ready: Annotated[bool, typer.Option("--ready/--not-ready", help="Whether execution is approved.")] = False,
    approved_by: Annotated[str, typer.Option("--approved-by", help="Approver identity.")] = "human",
    force: Annotated[bool, typer.Option("--force", help="Allow not-ready lock with open blockers.")] = False,
) -> None:
    state = load_state(root)
    open_blockers = [
        q for q in state.get("open_questions", [])
        if q.get("blocking") and not q.get("answered")
    ]
    if ready and open_blockers:
        raise typer.BadParameter(
            f"Cannot create ready lock with {len(open_blockers)} open blocking question(s)"
        )
    if not ready and open_blockers and not force:
        raise typer.BadParameter("Use --force to write a not-ready lock with open blockers")
    lock_data = {
        "schema": "align.lock.v1",
        "goal": state["goal"],
        "non_goals": [],
        "source_context": state.get("source_context", []),
        "participants": state["participants"],
        "output_shape": state["output_shape"],
        "acceptance_criteria": state.get("acceptance_criteria", []),
        "open_questions": state.get("open_questions", []),
        "ready_for_execution": ready,
        "approved_by": approved_by,
        "created_at": utc_now(),
        "state_sha256": sha256_text(json.dumps(state, sort_keys=True)),
    }
    write_json(root / "alignment_lock.json", lock_data)
    state["status"] = "locked_ready" if ready else "locked_not_ready"
    save_state(root, state)
    brief_path(root).write_text(render_brief(state), encoding="utf-8")
    typer.echo(f"Wrote alignment lock: ready_for_execution={ready}")


if __name__ == "__main__":
    app()
