"""Reviewer adapters for /review-code."""
from __future__ import annotations
# --- dotenv (MUST be before any os.getenv / os.environ) ---
import sys
from pathlib import Path as _Path

def _resolve_skills_dir() -> _Path:
    p = _Path(__file__).resolve()
    for parent in [p, *p.parents]:
        if parent.name == "skills":
            return parent
    return p.parents[1]

_SKILLS_DIR = _resolve_skills_dir()
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

try:
    from dotenv_helper import load_env as _load_env
except Exception:
    def _load_env() -> None:
        return

_load_env()


import json
import os
import re
import shlex
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

SUPPORTED_REVIEWER_SPEC = "ask:gpt-5.5"
DEFAULT_REASONING = "high"
TERMINAL_REVIEW_STATUSES = {"terminal_review", "review_complete", "completed", "success"}
CLARIFICATION_STATUSES = {"clarification_request", "needs_clarification", "questions"}
MERGE_RECOMMENDATIONS = {"SAFE_TO_MERGE", "SAFE_WITH_CONDITIONS", "CHANGES_REQUESTED", "NOT_SAFE"}


@dataclass(frozen=True)
class AskReviewerSpec:
    raw: str
    model: str
    reasoning: str = DEFAULT_REASONING


@dataclass
class AskReviewerResult:
    reviewer_spec: str
    requested_model: str
    requested_reasoning: str
    actual_model: Optional[str]
    actual_reasoning: Optional[str]
    stdout: str
    stderr: str
    exit_code: int
    session_path: Optional[str]
    status: str
    terminal_status: str
    content: str
    events: list[dict[str, Any]] = field(default_factory=list)
    command: list[str] = field(default_factory=list)
    artifact_path: Optional[str] = None


def parse_reviewer_spec(spec: str) -> AskReviewerSpec:
    """Support only the explicit /ask reviewer spec currently promised."""
    if spec != SUPPORTED_REVIEWER_SPEC:
        raise ValueError(f"Unknown reviewer spec: {spec}. Supported specs: {SUPPORTED_REVIEWER_SPEC}")
    _, model = spec.split(":", 1)
    return AskReviewerSpec(raw=spec, model=model, reasoning=DEFAULT_REASONING)


def build_review_prompt(bundle_text: str) -> str:
    """Build the /ask prompt from the complete WebGPT review bundle text."""
    if not bundle_text.strip():
        raise ValueError("Review bundle is empty")
    return (
        "Run a high-reasoning, read-only code review of the following review bundle. "
        "Do not ask follow-up questions unless the evidence is insufficient to make a "
        "terminal merge-safety recommendation. Use the bundle evidence directly; do not "
        "replace it with a summary. Return merge-blocking findings and exactly one merge "
        "recommendation when possible.\n\n"
        "--- BEGIN REVIEW BUNDLE ---\n"
        f"{bundle_text}"
        "\n--- END REVIEW BUNDLE ---\n"
    )


def build_ask_command(
    *,
    ask_executable: str,
    prompt: str,
    requested_model: str,
    requested_reasoning: str,
    run_output_root: Path,
    ask_id: str,
) -> list[str]:
    """Construct the supported /ask CLI invocation."""
    tokens = shlex.split(ask_executable)
    if not tokens:
        raise ValueError("ask_executable is empty")
    exe = Path(tokens[0])
    prefix = [sys.executable, str(exe), *tokens[1:]] if exe.suffix == ".py" else tokens
    return [
        *prefix,
        "-",
        "--json",
        "--oracle",
        "--oracle-backend", "subagent-runner",
        "--oracle-model", requested_model,
        "--oracle-reasoning", requested_reasoning,
        "--run-output-root", str(run_output_root),
        "--ask-id", ask_id,
        "--overwrite",
    ]


def run_ask_reviewer(
    *,
    reviewer_spec: str,
    bundle_path: str | Path,
    output_dir: str | Path,
    ask_executable: Optional[str] = None,
    timeout: Optional[float] = None,
    allow_model_downgrade: bool = False,
) -> AskReviewerResult:
    """Run the real /ask CLI boundary and persist auditable artifacts.

    Fails closed for missing bundle artifacts, unknown specs, non-zero exits,
    missing terminal status, and model downgrade unless explicitly opted in.
    """
    spec = parse_reviewer_spec(reviewer_spec)
    bundle = Path(bundle_path)
    if not bundle.is_file():
        raise RuntimeError(f"Missing review bundle artifact: {bundle}")
    prompt = build_review_prompt(bundle.read_text(errors="replace"))

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ask-reviewer-prompt.md").write_text(prompt)

    run_root = out_dir / "ask-runs"
    ask_id = f"review-code-{int(time.time() * 1000)}"
    executable = ask_executable or os.environ.get("ASK_REVIEWER_CLI") or _default_ask_executable()
    cmd = build_ask_command(
        ask_executable=executable,
        prompt=prompt,
        requested_model=spec.model,
        requested_reasoning=spec.reasoning,
        run_output_root=run_root,
        ask_id=ask_id,
    )

    proc = subprocess.run(cmd, input=prompt, text=True, capture_output=True, timeout=timeout)
    parsed = _parse_stdout_json(proc.stdout)
    content = _extract_content(parsed, proc.stdout)
    terminal_status, events = _classify_terminal_status(parsed, content)
    actual_model = _extract_actual_model(parsed, proc.stdout, proc.stderr)
    actual_reasoning = _extract_actual_reasoning(parsed, proc.stdout, proc.stderr)
    session_path = _extract_session_path(parsed, proc.stdout, proc.stderr, run_root / ask_id)

    result = AskReviewerResult(
        reviewer_spec=reviewer_spec,
        requested_model=spec.model,
        requested_reasoning=spec.reasoning,
        actual_model=actual_model,
        actual_reasoning=actual_reasoning,
        stdout=proc.stdout,
        stderr=proc.stderr,
        exit_code=proc.returncode,
        session_path=session_path,
        status="ok" if proc.returncode == 0 else "failed",
        terminal_status=terminal_status,
        content=content,
        events=events,
        command=_redact_prompt_from_command(cmd),
    )
    artifact_path = out_dir / "ask-reviewer-result.json"
    result.artifact_path = str(artifact_path)
    artifact_path.write_text(json.dumps(asdict(result), indent=2, sort_keys=True))
    (out_dir / "ask-reviewer-stdout.txt").write_text(proc.stdout)
    (out_dir / "ask-reviewer-stderr.txt").write_text(proc.stderr)

    if proc.returncode != 0:
        raise RuntimeError(f"/ask reviewer failed with exit code {proc.returncode}; artifact: {artifact_path}")
    if not terminal_status:
        raise RuntimeError(f"/ask reviewer exited without terminal status; artifact: {artifact_path}")
    if actual_model and actual_model != spec.model and not allow_model_downgrade:
        raise RuntimeError(
            f"/ask reviewer model downgrade/refusal: requested {spec.model}, got {actual_model}; artifact: {artifact_path}"
        )
    return result


def _default_ask_executable() -> str:
    local_run_sh = Path(__file__).resolve().parents[1] / "ask" / "run.sh"
    if local_run_sh.is_file():
        return f"{local_run_sh} ask"
    return "ask"


def _parse_stdout_json(stdout: str) -> dict[str, Any]:
    text = stdout.strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        pass
    for match in reversed(list(re.finditer(r"\{", stdout))):
        try:
            value = json.loads(stdout[match.start():])
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            continue
    return {}


def _extract_content(parsed: dict[str, Any], stdout: str) -> str:
    for key in ("answer", "content", "review", "response", "output"):
        value = parsed.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            nested = _extract_content(value, "")
            if nested:
                return nested
    oracle = parsed.get("oracle")
    if isinstance(oracle, dict):
        nested = _extract_content(oracle, "")
        if nested:
            return nested
    return stdout


def _classify_terminal_status(parsed: dict[str, Any], content: str) -> tuple[str, list[dict[str, Any]]]:
    raw_status = _first_string(parsed, ["terminal_status", "review_status", "status"])
    normalized = raw_status.lower().strip() if raw_status else ""
    if normalized in TERMINAL_REVIEW_STATUSES:
        return "terminal_review", []
    if normalized in CLARIFICATION_STATUSES:
        return "clarification_request", [_clarification_event(content)]
    if any(token in content for token in MERGE_RECOMMENDATIONS):
        return "terminal_review", []
    if _looks_like_clarification_request(content):
        return "clarification_request", [_clarification_event(content)]
    return "", []


def _looks_like_clarification_request(content: str) -> bool:
    lower = content.lower()
    return (
        "clarifying question" in lower
        or ("clarification" in lower and "?" in content)
        or (content.count("?") >= 2 and not any(token in content for token in MERGE_RECOMMENDATIONS))
    )


def _clarification_event(content: str) -> dict[str, Any]:
    questions = [line.strip(" -") for line in content.splitlines() if "?" in line]
    return {"type": "clarification_request", "questions": questions, "content": content}


def _extract_actual_model(parsed: dict[str, Any], stdout: str, stderr: str) -> Optional[str]:
    value = _first_string(parsed, ["actual_model", "served_model", "oracle_model", "model"])
    return value or _regex_first(r"(?:actual|served|oracle)[_-]?model\s*[:=]\s*([\w.:-]+)", stdout + "\n" + stderr)


def _extract_actual_reasoning(parsed: dict[str, Any], stdout: str, stderr: str) -> Optional[str]:
    value = _first_string(parsed, ["actual_reasoning", "reasoning_effort", "oracle_reasoning", "reasoning"])
    return value or _regex_first(r"(?:actual|oracle)?[_-]?reasoning(?:_effort)?\s*[:=]\s*([\w.:-]+)", stdout + "\n" + stderr)


def _extract_session_path(parsed: dict[str, Any], stdout: str, stderr: str, expected: Path) -> Optional[str]:
    value = _first_string(parsed, ["session_path", "session_dir", "artifact_dir", "run_dir"])
    if value:
        return value
    value = _regex_first(r"(?:session|artifact|run)[_-]?(?:path|dir)\s*[:=]\s*(\S+)", stdout + "\n" + stderr)
    if value:
        return value
    return str(expected) if expected.exists() else None


def _first_string(data: Any, keys: list[str]) -> Optional[str]:
    if not isinstance(data, dict):
        return None
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for value in data.values():
        if isinstance(value, dict):
            found = _first_string(value, keys)
            if found:
                return found
    return None


def _regex_first(pattern: str, text: str) -> Optional[str]:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else None


def _redact_prompt_from_command(cmd: list[str]) -> list[str]:
    redacted = list(cmd)
    for i, arg in enumerate(redacted):
        if i > 0 and not arg.startswith("-") and i + 1 < len(redacted) and redacted[i + 1].startswith("--"):
            redacted[i] = "<review bundle prompt redacted; see ask-reviewer-prompt.md>"
            break
    return redacted
