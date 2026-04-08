#!/usr/bin/env python3
"""Code Runner v2 — Autoresearch-pattern self-improvement loop for code tasks.

Architecture (same pattern as classifier-lab backbone_train_loop.py):
  1. LLM proposes code
  2. T0 deterministic evidence collection (errors, lint, DoD)
  3. Composite score (0-1) like autoresearch's val_bpb
  4. Score improved? → git commit (KEEP) : git revert (DISCARD)
  5. /scillm structured fix prompt with full trajectory
  6. Strategy escalation (5-step)
  7. Experiment log (rounds.jsonl)

90% deterministic (subprocess, regex, git), 10% LLM (propose fix).
The subagent CAN follow this because every step is a subprocess call.
"""
from __future__ import annotations

import concurrent.futures
import fcntl
import random
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import typer
from loguru import logger
from trace_compress import compress_tool_trace, trace_events_to_dict

# common/ modules (llm_invocations, estimate_timeout, json_utils)
_skills_dir = Path(os.environ.get("SKILLS_DIR", str(Path(__file__).resolve().parent.parent)))
_common = str(_skills_dir / "common")
if _common not in sys.path:
    sys.path.insert(0, _common)

from evidence import (
    classify_errors,
    collect_evidence,
    extract_symbols,
    get_strategy,
    build_fix_prompt,
)
from llm_invocations import log_invocation  # noqa: E402
from diagnose import (
    call_diagnose,
    validate_diagnosis,
    check_stagnation,
    check_fix_consistency,
    _treesitter_symbols,
    build_fix_from_diagnosis,
    Diagnosis,
    DiagnosisRejected,
)
from apply import (
    build_file_context,
    generate_hunk_review,
)
from tool_use import run_tool_use_loop
from models import TaskSpec, TaskResult, PreflightError

app = typer.Typer(no_args_is_help=True)


def _emit_event(event: str, **fields) -> None:
    """Emit a structured JSON event to stderr for real-time monitoring.

    Project agents can parse lines starting with '{"event":' from the
    stderr stream while loguru provides human-readable output alongside.
    """
    payload = {"event": event, "ts": time.time(), **fields}
    print(json.dumps(payload, default=str), file=sys.stderr, flush=True)

SCILLM_URL = os.environ.get("SCILLM_API_BASE", "http://localhost:4001/v1/chat/completions")
SCILLM_KEY = os.environ.get("SCILLM_PROXY_KEY", "sk-dev-proxy-123")

SKILLS_DIR = Path(os.environ.get("SKILLS_DIR", str(Path(__file__).resolve().parent.parent)))
GIT_TIMEOUT = 30  # seconds — prevents hangs on large repos

# Actionable fix advice per field (for Pydantic validation errors)
_FIX_ADVICE = {
    "prompt": "Add: which file to read, what's broken, what the fix should do. Min 20 chars.",
    "definition_of_done": "Add definition_of_done: {command: '...', assertion: '...'}",
    "definition_of_done.command": "Add a shell command that RUNS the code and checks OUTPUT. "
        "Example: 'python3 -c \"from module import func; assert func(x) == y; print(OK)\"'",
    "allowlist": "Add specific files: [\"src/auth.py\"]. For dirs: [\"scripts/\"]. "
        "Or set allowlist_optional: true.",
    "cwd": "Set cwd to an existing directory, typically the repo root.",
    "backend": "Use one of: codex, claude, text, gemini, deepseek.",
    "task_id": "Add a unique task_id string.",
}


def _preflight_fix_advice(field: str, msg: str) -> str:
    """Map a Pydantic field error to actionable fix advice."""
    # Try exact match, then prefix match
    if field in _FIX_ADVICE:
        return _FIX_ADVICE[field]
    for prefix, advice in _FIX_ADVICE.items():
        if field.startswith(prefix):
            return advice
    return f"Fix the '{field}' field: {msg}"


# ── Git Integration (autoresearch pattern) ───────────────────────────


def git_snapshot(cwd: str) -> str:
    """Return current HEAD commit hash."""
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=cwd, timeout=GIT_TIMEOUT,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def git_stash_save(cwd: str) -> bool:
    """Stash uncommitted changes before code-runner starts. Returns True if stashed.

    Only stashes tracked modifications (not untracked files) to avoid conflicts
    when code-runner commits new files that overlap with stashed untracked files.
    """
    proc = subprocess.run(
        ["git", "stash", "push", "-m", "code-runner-pre-run-stash"],
        capture_output=True, text=True, cwd=cwd, timeout=GIT_TIMEOUT,
    )
    stashed = "Saved working directory" in proc.stdout
    if stashed:
        logger.info("Stashed pre-existing changes (tracked only)")
    return stashed


def git_stash_pop(cwd: str) -> None:
    """Restore stashed changes after code-runner finishes.

    Falls back to git stash drop if pop conflicts (e.g., code-runner committed
    files that overlap with stashed content).
    """
    proc = subprocess.run(["git", "stash", "pop"], capture_output=True, text=True, cwd=cwd, timeout=GIT_TIMEOUT)
    if proc.returncode != 0:
        # Conflict: code-runner committed files that clash with stash
        if "conflict" in proc.stderr.lower() or "already exists" in proc.stderr.lower():
            logger.warning("git stash pop conflict — dropping stash (code-runner committed overlapping files)")
            subprocess.run(["git", "stash", "drop"], capture_output=True, text=True, cwd=cwd, timeout=GIT_TIMEOUT)
        else:
            logger.error("git stash pop FAILED — user changes may be trapped in stash: {}", proc.stderr[:300])
    else:
        logger.info("Restored stashed changes")


def git_commit_round(cwd: str, task_id: str, round_num: int, score: float,
                     written_files: list[str]) -> str:
    """Commit ONLY written files with code-runner metadata. Returns commit hash."""
    if not written_files:
        return ""
    # Stage only the files we wrote — not unrelated changes
    subprocess.run(["git", "add", "--"] + written_files, cwd=cwd, capture_output=True, timeout=GIT_TIMEOUT)
    msg = f"code-runner: {task_id} round {round_num} (score={score:.3f})"
    proc = subprocess.run(
        ["git", "commit", "-m", msg, "--no-verify"],
        capture_output=True, text=True, cwd=cwd, timeout=GIT_TIMEOUT,
    )
    if proc.returncode != 0:
        logger.warning("git commit failed: {}", proc.stderr[:200])
        return ""
    return git_snapshot(cwd)


def git_revert_to(cwd: str, commit_hash: str, written_files: list[str]) -> None:
    """Revert ONLY written files to their state at commit_hash. Non-destructive.

    Handles both modified files (checkout) and NEW files created by the LLM
    that don't exist in best_commit (delete them).
    """
    if not commit_hash or not written_files:
        return
    # Separate files that exist in best_commit from new files
    existing_in_commit: list[str] = []
    new_files: list[str] = []
    for f in written_files:
        proc = subprocess.run(
            ["git", "cat-file", "-e", f"{commit_hash}:{f}"],
            capture_output=True, cwd=cwd, timeout=GIT_TIMEOUT,
        )
        if proc.returncode == 0:
            existing_in_commit.append(f)
        else:
            new_files.append(f)

    # Restore modified files to their state at best_commit
    if existing_in_commit:
        subprocess.run(
            ["git", "checkout", commit_hash, "--"] + existing_in_commit,
            capture_output=True, cwd=cwd, timeout=GIT_TIMEOUT,
        )
    # Delete new files that don't exist in best_commit (LLM created them this round)
    for f in new_files:
        fpath = Path(cwd) / f
        try:
            if fpath.is_file() or fpath.is_symlink():
                fpath.unlink()
                logger.info("  Removed new file: {}", f)
            elif fpath.is_dir():
                logger.warning("  Skipped directory removal: {}", f)
        except OSError as e:
            logger.warning("  Failed to remove {}: {}", f, e)
    logger.info("Reverted {} files to {} (removed {} new)", len(existing_in_commit), commit_hash[:8], len(new_files))


# ── Experiment Log ───────────────────────────────────────────────────


def log_round(output_dir: Path, task_id: str, entry: dict,
              session_key: str = "", symbols: str = "",
              learn_to_memory: bool = True, scope: str = "") -> None:
    """Append round result to local experiment log + optionally /memory."""
    # Local log (always — full history for debugging)
    log_file = output_dir / f"{task_id}.rounds.jsonl"
    with log_file.open("a") as f:
        f.write(json.dumps(entry) + "\n")

    # /memory learn (only for kept rounds + terminal — avoids polluting recall with noise)
    if learn_to_memory:
        _learn_round_to_memory(task_id, entry, session_key=session_key, symbols=symbols, scope=scope)


def _learn_round_to_memory(task_id: str, entry: dict, session_key: str = "",
                           symbols: str = "", scope: str = "") -> None:
    """Store round to ArangoDB llm_invocations via unified logger.

    session_key links all rounds for one code-runner invocation.
    symbols contains /treesitter output for the modified files.
    """
    # Build output: include tool trace text so it's BM25-searchable at top level
    output_text = entry.get("response_snippet", "")
    if entry.get("tool_trace"):
        output_text = f"{output_text}\n\nTOOL TRACE:\n{entry['tool_trace']}"

    log_invocation(
        agent="code-runner",
        session_key=session_key,
        round=entry.get("round", 1),
        role="assistant",
        turn_index=entry.get("round", 1),
        input=entry.get("prompt_snippet", ""),
        output=output_text,
        outcome="success" if entry.get("dod_passed") else "failed",
        duration_ms=entry.get("duration_ms", 0),
        model=entry.get("model", ""),
        score=entry.get("score"),
        error=entry.get("error_severity"),
        tags=[
            "code-runner", "self-improvement",
            f"task:{task_id}",
            f"strategy:{entry.get('strategy', '')}",
            f"severity:{entry.get('error_severity', '')}",
            f"outcome:{'pass' if entry.get('dod_passed') else 'fail'}",
        ],
        parent_session="",
        scope=scope,
        metadata={
            "task_id": task_id,
            "status": entry.get("status", ""),
            "errors_by_type": entry.get("errors_by_type", {}),
            "lint_violations": entry.get("lint_violations", 0),
            "bp_violations": entry.get("bp_violations", []),
            "commit": entry.get("commit", ""),
            "symbols": symbols[:1000] if symbols else "",
            "dod_passed": entry.get("dod_passed", False),
            "tool_trace_events": entry.get("tool_trace_events", []),
        },
    )



# ── Dogpile Research (last resort before escalate) ───────────────────


def _dogpile_research(rounds_history: list[dict], cwd: str) -> str:
    """Search for solutions to persistent errors via /dogpile skill.

    Called when strategy reaches 'escalate' — all fix approaches exhausted.
    Extracts the dominant error from history and searches web/GitHub/arXiv.
    Returns research text to inject into one final fix attempt, or empty string.
    """
    skills_dir = Path(os.environ.get("SKILLS_DIR", str(Path(__file__).resolve().parent.parent)))
    dogpile_skill = skills_dir / "dogpile" / "run.sh"
    if not dogpile_skill.exists():
        return ""

    # Build search query from the most recent error
    last = rounds_history[-1] if rounds_history else {}
    stderr = last.get("stderr", "")
    severity = last.get("error_severity", "unknown")
    errors = last.get("errors_by_type", {})

    # Extract the most specific error line from stderr
    error_lines = [l for l in stderr.splitlines() if any(e in l for e in errors)]
    query = error_lines[0][:200] if error_lines else f"{severity} error: {stderr[:150]}"

    try:
        proc = subprocess.run(
            ["bash", str(dogpile_skill), "search", "--query", query, "--max-results", "3", "--json"],
            capture_output=True, text=True, timeout=30,
            cwd=cwd,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout)
            results = data.get("results", [])
            if results:
                summaries = []
                for r in results[:3]:
                    title = r.get("title", "")[:100]
                    snippet = r.get("snippet", r.get("summary", ""))[:300]
                    source = r.get("source", r.get("url", ""))[:100]
                    summaries.append(f"  [{source}] {title}\n    {snippet}")
                return "\n".join(summaries)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
        pass
    return ""


# ── LLM Backend Routing ──────────────────────────────────────────────


def _call_llm(prompt: str, backend: str, cwd: str, temperature: float = 0.2,
              reasoning: str = "low", system_prompt: str = "") -> str:
    """Call LLM backend to propose or fix code. Returns response text.

    ALL backends route through /scillm API (text in, text out). The agent
    controls what goes to disk via apply.py's allowlist enforcement.

    Temperature increases on repeated failures (LLMLOOP pattern) to break local minima.
    Reasoning escalation (low/medium/high) increases max_tokens and prompt depth.
    """
    model = {
        "codex": "gpt-5.3-codex",
        "claude": "text-claude",
        "text": "text",
        "gemini": "text-gemini",
        "deepseek": "text",
    }.get(backend, "gpt-5.3-codex")

    max_tokens = {"low": 4000, "medium": 8000, "high": 16000}.get(reasoning, 4000)

    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if not model.startswith("gpt-"):
        payload["temperature"] = min(temperature, 1.0)

    # Retry with backoff + jitter on transient errors
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            resp = httpx.post(
                SCILLM_URL,
                headers={"Authorization": f"Bearer {SCILLM_KEY}"},
                json=payload,
                timeout=180.0,
            )
            if resp.status_code in (500, 502, 503, 429) and attempt < max_retries:
                base = min(0.5 * (2 ** attempt), 32.0)
                wait = base + random.random() * 0.25 * base
                logger.warning("/scillm {} (attempt {}/{}) — retrying in {:.1f}s",
                               resp.status_code, attempt, max_retries, wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except httpx.TimeoutException:
            if attempt < max_retries:
                base = min(0.5 * (2 ** attempt), 32.0)
                wait = base + random.random() * 0.25 * base
                logger.warning("/scillm timeout (attempt {}/{}) — retrying in {:.1f}s",
                               attempt, max_retries, wait)
                time.sleep(wait)
                continue
            logger.error("/scillm timeout after {} attempts", max_retries)
            return f"ERROR: /scillm timeout after {max_retries} attempts"
        except Exception as e:
            logger.error("/scillm call failed: {}", e)
            return f"ERROR: /scillm call failed: {e}"
    return "ERROR: /scillm exhausted retries"


# ── Memory-Backed Prompt Assembly (extracted to prompt_assembly.py) ─────
from prompt_assembly import build_system_prompt as _build_system_prompt


# ── Main Loop (autoresearch pattern) ─────────────────────────────────


@app.command()
def run(
    spec_file: str = typer.Argument(..., help="Path to task spec JSON"),
    max_rounds: int = typer.Option(5, help="Max self-improvement rounds"),
    backend: str = typer.Option("", help="Override LLM backend"),
) -> None:
    """Run task with autoresearch-pattern self-improvement loop."""
    # Wrap spec read in error handling — crash here = no stash to restore, but produce structured error
    try:
        raw_spec = json.loads(Path(spec_file).read_text())
    except (FileNotFoundError, json.JSONDecodeError, PermissionError) as e:
        logger.error("Cannot read spec file {}: {}", spec_file, e)
        sys.exit(1)

    # ── Pydantic validation (declarative preflight) ──────────────
    task_id = raw_spec.get("task_id", "unknown")
    output_dir = Path(raw_spec.get("output_dir", "/tmp/code-runner"))

    try:
        spec = TaskSpec.model_validate(raw_spec)
    except Exception as e:
        # Convert Pydantic errors to actionable preflight errors
        preflight_errors = []
        if hasattr(e, "errors"):
            for err in e.errors():
                field = ".".join(str(x) for x in err.get("loc", []))
                preflight_errors.append(PreflightError(
                    field=field or "spec",
                    error=err.get("msg", str(e)),
                    fix=_preflight_fix_advice(field, err.get("msg", "")),
                ))
        else:
            preflight_errors.append(PreflightError(
                field="spec", error=str(e),
                fix="Check the task spec JSON against the TaskSpec schema.",
            ))

        logger.error("=== PRE-FLIGHT FAILED for {} ({} issues) ===", task_id, len(preflight_errors))
        for pf in preflight_errors:
            logger.error("  [{}] {}", pf.field, pf.error)
            logger.error("    FIX: {}", pf.fix)

        output_dir.mkdir(parents=True, exist_ok=True)
        result = TaskResult(
            task_id=task_id, title=raw_spec.get("title", ""),
            status="preflight_fail",
            preflight_errors=preflight_errors,
        )
        (output_dir / f"{task_id}.result.json").write_text(result.model_dump_json(indent=2))
        sys.exit(1)

    # Warn on weak DoD (not a failure, but logged)
    if spec.has_weak_dod:
        logger.warning("DoD has no assertion and doesn't run tests — LLM may game it")

    # FAIL on silent DoD mismatch (assertion will never match empty stdout)
    if spec.has_silent_dod_mismatch:
        logger.error("=== PRE-FLIGHT FAILED: DoD assertion will never match ===")
        logger.error("  {}", spec.silent_dod_detail)
        output_dir = Path(spec.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        result = TaskResult(
            task_id=spec.task_id, title=spec.title, status="preflight_fail",
            preflight_errors=[PreflightError(
                field="definition_of_done.assertion",
                error=spec.silent_dod_detail,
                fix="Use 'exit_code == 0' for commands that output nothing on success. "
                    "Or use a command that produces output (e.g., 'npx tsc --noEmit && echo passed').",
            )],
        )
        (output_dir / f"{spec.task_id}.result.json").write_text(result.model_dump_json(indent=2))
        sys.exit(1)

    # ── DoD dry-run: verify the command is syntactically valid and runnable ──
    # Runs the DoD against the CURRENT cwd (before any LLM changes).
    # Expected to fail (code isn't fixed yet) but should NOT crash with syntax errors.
    dod_cmd = spec.definition_of_done.command
    if dod_cmd:
        try:
            dod_check = subprocess.run(
                ["bash", "-lc", dod_cmd],
                capture_output=True, text=True, timeout=15, cwd=spec.cwd,
            )
            # If it crashes with bash/python syntax error (not assertion failure), warn
            if dod_check.returncode != 0 and "SyntaxError" in dod_check.stderr:
                logger.error("DoD command has SYNTAX ERROR — the command itself is broken:")
                logger.error("  {}", dod_check.stderr.strip().splitlines()[-1][:200] if dod_check.stderr.strip() else "unknown")
                output_dir = Path(spec.output_dir)
                output_dir.mkdir(parents=True, exist_ok=True)
                result = TaskResult(
                    task_id=spec.task_id, title=spec.title, status="preflight_fail",
                    preflight_errors=[PreflightError(
                        field="definition_of_done.command",
                        error=f"DoD command has Python SyntaxError: {dod_check.stderr.strip().splitlines()[-1][:200]}",
                        fix="Fix the syntax in the DoD command. Multi-line Python in -c requires proper escaping. "
                            "Consider using a test file instead of inline python3 -c.",
                    )],
                )
                (output_dir / f"{spec.task_id}.result.json").write_text(result.model_dump_json(indent=2))
                sys.exit(1)
        except subprocess.TimeoutExpired:
            logger.warning("DoD dry-run timed out (15s) — proceeding anyway")
        except Exception:
            pass  # DoD may legitimately fail before code is written

    # Extract validated fields
    task_id = spec.task_id
    title = spec.title
    prompt = spec.prompt
    llm_backend = backend or spec.backend
    cwd = spec.cwd
    output_dir = Path(spec.output_dir)
    dod_command = spec.definition_of_done.command
    dod_assertion = spec.definition_of_done.assertion
    allowlist = spec.allowlist
    read_context = spec.read_context
    skills_used = spec.skills_used

    # Bug fix: spec max_rounds should override CLI default (5)
    # CLI --max-rounds only wins if explicitly passed (typer sets default=5)
    if spec.max_rounds != 5 and max_rounds == 5:
        max_rounds = spec.max_rounds

    # ── Preflight warnings (not hard failures, but logged for project agent) ──

    # Design decision detection — code-runner is an executor, not an architect
    if spec.is_design_decision:
        logger.error("PRE-FLIGHT WARNING: Prompt asks code-runner to make a DESIGN DECISION")
        logger.error("  Code-runner is a bounded executor. Architecture choices belong in /plan.")
        logger.error("  FIX: Choose the approach in /plan, then tell code-runner 'implement X using Y'.")

    # Unseen dependencies (empirical: 3+ unseen deps = ~50% fail rate on text backend)
    if spec.unseen_dep_count >= 3:
        logger.error("PRE-FLIGHT WARNING: {} modules referenced but not in allowlist or read_context: {}",
                     spec.unseen_dep_count, spec.unseen_deps)
        logger.error("  FIX: Add them to read_context so code-runner can extract interface maps.")

    # Escalation chain
    default_chain = [
        [llm_backend, "medium"],
        [llm_backend, "high"],
        ["claude", "high"],
    ]
    escalation_chain: list[list[str]] = spec.escalation_chain or default_chain
    escalation_idx = 0

    logger.info("=== CODE-RUNNER v2: {} ===", title)
    logger.info("  Backend: {}", llm_backend)
    logger.info("  DoD: {}", dod_command[:100] if dod_command else "(none)")
    logger.info("  Max rounds: {}", max_rounds)

    # Validate git repo — keep/discard pattern requires git
    git_dir_proc = subprocess.run(
        ["git", "rev-parse", "--git-dir"], capture_output=True, text=True, cwd=cwd, timeout=GIT_TIMEOUT,
    )
    is_git_repo = git_dir_proc.returncode == 0
    git_dir = Path(cwd) / git_dir_proc.stdout.strip() if is_git_repo else None
    if not is_git_repo:
        logger.warning("cwd is NOT a git repo — keep/discard disabled, no hunk review")

    # Repo lock: prevent concurrent code-runner runs in same repo
    lock_file = None
    if is_git_repo and git_dir:
        lock_path = git_dir / "code-runner.lock"
        lock_file = open(lock_path, "w")
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            logger.error("Another code-runner is already running in {}. Aborting.", cwd)
            lock_file.close()
            sys.exit(1)

    # Session key links all rounds in /memory for graph traversal
    session_key = f"cr-{task_id}-{int(time.time())}"
    failure_reason = ""  # populated on timeout, zero-writes, stash conflict
    run_start_time = time.monotonic()

    # Git safety: stash pre-existing changes before we start
    stashed = git_stash_save(cwd) if is_git_repo else False

    # Create output dir AFTER stash — if output_dir is inside cwd, stash would remove it
    output_dir.mkdir(parents=True, exist_ok=True)

    # Git snapshot (autoresearch: remember where we started)
    snapshot = git_snapshot(cwd)

    rounds_history: list[dict] = []
    prior_diagnoses: list[Diagnosis] = []
    best_score = 0.0
    best_commit = snapshot
    try:  # try/finally guarantees stash pop + lock release even on crash
        # Staged context escalation: start with interface maps for read_context,
        # escalate specific files to full content on failure (research-validated pattern)
        escalated_files: set[str] = set()  # read_context files promoted to full content after failure
        file_context = build_file_context(allowlist, cwd, read_context, escalated_files)

        # Format instructions are in system prompt (v2) — user prompt is just task + files
        current_prompt = prompt + "\n\n" + file_context
        final_response = ""
        temperature = 0.2  # Dynamic: increments by 0.1 on repeated same-error (LLMLOOP pattern)
        dogpile_done = False  # only search once per run
        dogpile_context = ""  # research results injected into prompt

        # Memory-backed system prompt: fixed context (recalled once, doesn't grow)
        # Original request + DoD are embedded as immutable anchors to prevent drift
        dod_desc = f"Command: {dod_command}\nAssertion: {dod_assertion}" if dod_command else ""
        system_prompt = _build_system_prompt(
            task_id, session_key, prompt, round_num=1,
            dod_desc=dod_desc, allowlist=allowlist, recent_rounds=[],
            skills_used=skills_used)

        consecutive_zero_writes = 0
        MAX_CONSECUTIVE_ZERO_WRITES = 3

        for round_num in range(1, max_rounds + 1):
            # 1. Determine strategy (deterministic)
            # Classify from both stderr AND stdout — many tools (pytest, custom scripts) print failures to stdout
            prev_output = (rounds_history[-1].get("stderr", "") + "\n" + rounds_history[-1].get("stdout", "")) if rounds_history else ""
            classification = classify_errors(prev_output) if rounds_history else {"severity": "unknown", "total": 0, "error_types": {}}
            strategy = get_strategy(round_num, classification, rounds_history)

            # Dynamic temperature + escalation on stagnation (same error OR no score improvement)
            same_error_repeating = False
            score_stagnant = False
            if len(rounds_history) >= 2:
                prev_sev = rounds_history[-1].get("error_severity", "")
                prev_prev_sev = rounds_history[-2].get("error_severity", "")
                same_error_repeating = bool(prev_sev and prev_sev == prev_prev_sev)
                score_stagnant = rounds_history[-1].get("score", 0) <= rounds_history[-2].get("score", 0)

            if same_error_repeating or score_stagnant:
                temperature = min(temperature + 0.1, 1.0)
                escalation_idx = min(escalation_idx + 1, len(escalation_chain) - 1)

                # Dogpile early: if stuck (same error or stagnant score), research before wasting rounds
                if not dogpile_done and len(rounds_history) >= 2 and (same_error_repeating or score_stagnant):
                    research = _dogpile_research(rounds_history, cwd)
                    if research:
                        dogpile_context = f"\n\n--- Research from /dogpile ---\n{research}\n"
                        logger.info("  /dogpile found research for repeated {} error", rounds_history[-1].get("error_severity"))
                    dogpile_done = True  # only search once per run

            cur_backend, cur_reasoning = escalation_chain[escalation_idx]
            _emit_event("round_start", task_id=task_id, round=round_num,
                        max_rounds=max_rounds, strategy=strategy,
                        backend=cur_backend, reasoning=cur_reasoning,
                        temperature=round(temperature, 2))
            if same_error_repeating:
                logger.info("── Round {}/{} [strategy={} temp={:.1f}↑ {}:{}] ──",
                            round_num, max_rounds, strategy, temperature, cur_backend, cur_reasoning)
            else:
                logger.info("── Round {}/{} [strategy={} {}:{}] ──",
                            round_num, max_rounds, strategy, cur_backend, cur_reasoning)

            if strategy == "escalate":
                # Dogpile already ran on first repeated error (round 3+).
                # If we're here, either dogpile had no results or research didn't help.
                last = rounds_history[-1] if rounds_history else {}
                diagnosis = {
                    "escalation": "all strategies exhausted",
                    "rounds_attempted": len(rounds_history),
                    "persistent_error": last.get("error_severity", "unknown"),
                    "error_evidence": last.get("error_evidence"),
                    "strategies_tried": [r.get("strategy") for r in rounds_history],
                    "dogpile_searched": dogpile_done,
                    "best_score": best_score,
                    "recommendation": "Task needs project agent intervention or decomposition into smaller subtasks.",
                }
                (output_dir / f"{task_id}.diagnosis.json").write_text(
                    json.dumps(diagnosis, indent=2, default=str))
                logger.warning("Strategy: ESCALATE — diagnosis written to {}.diagnosis.json", task_id)
                break

            # 2. Call LLM (the 10% agent part)
            if round_num > 1:
                evidence = rounds_history[-1]

                # Staged context escalation: if error references a read_context file, promote to full content
                err_ev = evidence.get("error_evidence") or {}
                err_loc = err_ev.get("primary_location") or {}
                err_file = err_loc.get("file", "")
                if err_file and read_context:
                    for rc in read_context:
                        if err_file.endswith(rc) or rc.endswith(err_file) or Path(err_file).name == Path(rc).name:
                            if rc not in escalated_files:
                                escalated_files.add(rc)
                                logger.info("  Context escalation: {} promoted to full content", rc)

                file_context = build_file_context(allowlist, cwd, read_context, escalated_files)

                # Snapshot treesitter symbols BEFORE LLM writes (for consistency Check 4)
                pre_fix_symbols: dict[str, set[str]] = {}
                if allowlist and round_num > 1:
                    for af in allowlist[:5]:
                        abs_af = Path(cwd) / af if not Path(af).is_absolute() else Path(af)
                        if abs_af.exists() and abs_af.is_file():
                            pre_fix_symbols[af] = _treesitter_symbols(abs_af)

                # ── DIAGNOSE/FIX SPLIT (two scillm calls instead of one) ──
                # Call 1: DIAGNOSE — structured root-cause inference, no code
                from stderr_parser import condense_stderr
                error_ev_obj = condense_stderr(
                    evidence.get("stderr", ""), evidence.get("stdout", ""),
                )
                file_symbols = extract_symbols(evidence.get("written_files", []), cwd)

                diag_backend, diag_reasoning = cur_backend, "high"  # diagnoser always high effort
                _emit_event("diagnose_start", task_id=task_id, round=round_num,
                            backend=diag_backend)

                try:
                    diagnosis = call_diagnose(
                        error_evidence=error_ev_obj,
                        stderr=evidence.get("stderr", ""),
                        stdout=evidence.get("stdout", ""),
                        file_content=file_context,
                        symbols=file_symbols,
                        task_prompt=prompt,
                        backend=diag_backend,
                        reasoning=diag_reasoning,
                    )
                    logger.info("  DIAGNOSIS: {} in {}::{} (confidence={:.2f})",
                                diagnosis.failure_kind,
                                diagnosis.primary_target.file,
                                diagnosis.primary_target.symbol,
                                diagnosis.confidence)
                    logger.info("  ROOT CAUSE: {}", diagnosis.root_cause)
                    logger.info("  REPAIR INTENT: {}", diagnosis.repair_intent)

                    # Save diagnosis to disk for audit
                    diag_path = output_dir / "logs" / f"round_{round_num}_diagnosis.json"
                    diag_path.parent.mkdir(exist_ok=True)
                    diag_path.write_text(diagnosis.model_dump_json(indent=2))

                    # HARD GATE: validate diagnosis against reality
                    validation = validate_diagnosis(
                        diagnosis, cwd, symbols=file_symbols,
                        stderr=evidence.get("stderr", ""),
                        stdout=evidence.get("stdout", ""),
                    )
                    if validation.hard_failures:
                        for f in validation.hard_failures:
                            logger.error("  DIAGNOSIS REJECTED: {}", f)
                        raise DiagnosisRejected(validation.hard_failures)
                    if validation.warnings:
                        for w in validation.warnings:
                            logger.warning("  DIAGNOSIS WARNING: {}", w)

                    # Check stagnation: understanding stuck vs implementation stuck
                    prior_scores = [r.get("score", 0) for r in rounds_history]
                    stagnation = check_stagnation(diagnosis, prior_diagnoses, prior_scores)

                    if stagnation.stagnation_type == "understanding":
                        # Escalate diagnoser, not fixer
                        logger.warning("  STAGNATION: understanding stuck — {}", stagnation.reason)
                        escalation_idx = min(escalation_idx + 1, len(escalation_chain) - 1)
                    elif stagnation.stagnation_type == "implementation":
                        logger.warning("  STAGNATION: implementation stuck — {}", stagnation.reason)

                    prior_diagnoses.append(diagnosis)

                    # Call 2: FIX — lean prompt constrained by diagnosis
                    prior_trace = rounds_history[-1].get("tool_trace", "") if rounds_history else ""
                    current_prompt = build_fix_from_diagnosis(
                        diagnosis, file_context, allowlist=allowlist,
                        prior_tool_trace=prior_trace,
                    )

                except DiagnosisRejected as exc:
                    logger.warning("  Diagnosis REJECTED ({}), falling back to combined prompt", exc.reasons)
                    _emit_event("diagnosis_rejected", task_id=task_id, round=round_num,
                                reasons=exc.reasons)
                    current_prompt = build_fix_prompt(evidence, rounds_history, strategy, prompt, file_context, allowlist=allowlist)
                except (httpx.HTTPStatusError, httpx.RequestError, httpx.TimeoutException) as exc:
                    logger.warning("  Diagnosis call failed ({}), falling back to combined prompt", exc)
                    current_prompt = build_fix_prompt(evidence, rounds_history, strategy, prompt, file_context, allowlist=allowlist)
                except (ValueError, KeyError) as exc:
                    logger.warning("  Diagnosis parse failed ({}), falling back to combined prompt", exc)
                    current_prompt = build_fix_prompt(evidence, rounds_history, strategy, prompt, file_context, allowlist=allowlist)

                if dogpile_context:
                    current_prompt += dogpile_context

            # Refresh system prompt every round with latest round history
            if round_num > 1:
                system_prompt = _build_system_prompt(
                    task_id, session_key, prompt, round_num,
                    dod_desc=dod_desc, allowlist=allowlist,
                    recent_rounds=rounds_history)

            # 2. Call LLM via tool_use agent loop
            model_name = {
                "codex": "gpt-5.3-codex", "claude": "claude-sonnet-4-6",
                "gemini": "text-gemini",
            }.get(cur_backend, "gpt-5.3-codex")

            # Dynamic timeout: P95 from /memory history, or env override
            if os.environ.get("CODE_RUNNER_ROUND_TIMEOUT"):
                ROUND_TIMEOUT = int(os.environ["CODE_RUNNER_ROUND_TIMEOUT"])
            else:
                sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
                from estimate_timeout import estimate_skill
                ROUND_TIMEOUT = estimate_skill("code-runner", units=1)
                logger.info("  Round timeout: {}s (from /memory P95)", ROUND_TIMEOUT)
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    run_tool_use_loop,
                    system_prompt=system_prompt,
                    user_prompt=current_prompt,
                    model=model_name,
                    cwd=cwd,
                    allowlist=allowlist,
                    read_context=read_context,
                    temperature=temperature,
                    max_tokens={"low": 4000, "medium": 8000, "high": 16000}.get(cur_reasoning, 4000),
                    dod_command=dod_command,
                )
                try:
                    written, tool_messages = future.result(timeout=ROUND_TIMEOUT)
                except concurrent.futures.TimeoutError:
                    _emit_event("round_timeout", task_id=task_id, round=round_num,
                                timeout_seconds=ROUND_TIMEOUT)
                    logger.error("  ROUND TIMEOUT: tool_use loop exceeded {}s", ROUND_TIMEOUT)
                    failure_reason = (f"Round {round_num} timed out after {ROUND_TIMEOUT}s. "
                                      f"Set CODE_RUNNER_ROUND_TIMEOUT={ROUND_TIMEOUT * 2} or increase timeout_seconds in task spec.")
                    written, tool_messages = [], []

            # Compress tool trace for inter-round context persistence
            trace_events, trace_text = compress_tool_trace(tool_messages)
            trace_events_json = trace_events_to_dict(trace_events)

            # Extract final text response (last assistant message without tool_calls)
            response = ""
            for m in reversed(tool_messages):
                if m.get("role") == "assistant" and not m.get("tool_calls"):
                    response = m.get("content", "")
                    break
            final_response = response
            llm_metadata = {"summary": response[:200], "approach": strategy}
            _emit_event("tool_use_complete", task_id=task_id, round=round_num,
                        files_written=len(written), tool_calls=sum(
                            1 for m in tool_messages if m.get("role") == "assistant" and m.get("tool_calls")))

            # Save round response
            round_file = output_dir / f"{task_id}.round_{round_num}.txt"
            if response:
                round_file.write_text(response)
            else:
                round_file.write_text(json.dumps({"tool_iterations": len(tool_messages)}))

            if written:
                logger.info("  Applied {} files: {}", len(written), written)
                consecutive_zero_writes = 0

                # Fix-to-diagnosis consistency check (round 2+ only, when diagnosis exists)
                if prior_diagnoses and round_num > 1:
                    last_diag = prior_diagnoses[-1]
                    # pre_fix_symbols captured before LLM call at top of round
                    consistency = check_fix_consistency(
                        last_diag, written, allowlist,
                        cwd=cwd,
                        pre_fix_symbols=pre_fix_symbols if 'pre_fix_symbols' in dir() else None,
                    )
                    if not consistency.consistent:
                        for v in consistency.violations:
                            logger.error("  FIX DRIFT: {}", v)
                        _emit_event("fix_drift", task_id=task_id, round=round_num,
                                    violations=consistency.violations)
                        # Revert drifted fix — don't let it pollute scoring
                        if is_git_repo:
                            git_revert_to(cwd, best_commit, written)
                        logger.warning("  Reverted drifted fix — diagnosis targets {}, fix edited {}",
                                       last_diag.primary_target.file, written)
                        written = []  # force zero-write path
            else:
                consecutive_zero_writes += 1
                if consecutive_zero_writes >= MAX_CONSECUTIVE_ZERO_WRITES:
                    _emit_event("early_abort", task_id=task_id, round=round_num,
                                reason=f"{consecutive_zero_writes} consecutive rounds wrote 0 files")
                    logger.error("  EARLY ABORT: {} consecutive rounds wrote 0 files — LLM not producing edits",
                                 consecutive_zero_writes)
                    failure_reason = (f"LLM wrote 0 files for {consecutive_zero_writes} consecutive rounds. "
                                      f"Backend '{llm_backend}' may not be executing tool calls. "
                                      f"Try backend 'codex' or check scillm health.")
                    break

            # 3. T0 deterministic evidence collection (NOW evaluates changed files)
            evidence_raw = collect_evidence(cwd, dod_command, dod_assertion)
            score = evidence_raw["score"]

            # If LLM wrote zero files AND DoD didn't pass, force score to 0.
            # But if DoD genuinely passes (work already done, or read-only task),
            # respect that — don't override a real pass.
            if not written:
                if not evidence_raw["dod_passed"]:
                    score = 0.0
                    evidence_raw["score"] = 0.0
                    evidence_raw["_zero_files_override"] = True
                evidence_raw["_zero_write_reason"] = "tool_use_no_writes"
            _emit_event("round_score", task_id=task_id, round=round_num,
                        score=round(score, 4), dod_passed=evidence_raw["dod_passed"],
                        errors=evidence_raw["error_count"], lint=evidence_raw["lint_violations"],
                        files_written=len(written),
                        zero_write_reason=evidence_raw.get("_zero_write_reason", ""))
            logger.info("  Score: {:.3f} (DoD:{} errors:{} lint:{} bp:{})",
                         score, evidence_raw["dod_passed"], evidence_raw["error_count"],
                         evidence_raw["lint_violations"], len(evidence_raw["bp_violations"]))

            # Save full stdout/stderr per round (untruncated, for debugging)
            log_dir = output_dir / "logs"
            log_dir.mkdir(exist_ok=True)
            (log_dir / f"round_{round_num}_stdout.txt").write_text(evidence_raw.get("stdout_full", evidence_raw["stdout"]))
            (log_dir / f"round_{round_num}_stderr.txt").write_text(evidence_raw.get("stderr_full", evidence_raw["stderr"]))

            # Condense stderr into structured evidence for logging
            from stderr_parser import condense_stderr
            error_ev = condense_stderr(evidence_raw["stderr"], evidence_raw["stdout"])
            evidence_raw["error_evidence"] = {
                "failure_type": error_ev.failure_type,
                "summary": error_ev.summary,
                "primary_location": {
                    "file": error_ev.primary_location.file,
                    "line": error_ev.primary_location.line,
                } if error_ev.primary_location else None,
                "root_cause_lines": error_ev.root_cause_lines,
                "failing_tests": error_ev.failing_tests,
            }

            # 4. Keep/discard (autoresearch pattern) — epsilon threshold avoids churn
            EPSILON = 0.01
            prev_best = best_score
            if score > best_score + EPSILON:
                commit = git_commit_round(cwd, task_id, round_num, score, written) if is_git_repo else ""
                if is_git_repo and not commit:
                    # Git commit failed — don't advance best_score or it'll diverge from recoverable state
                    status = "discard"
                    logger.warning("  DISCARD (score improved but git commit failed)")
                else:
                    best_score = score
                    best_commit = commit or best_commit
                    status = "keep"
                    logger.info("  KEEP (score {:.3f} > previous {:.3f})", score, prev_best)
            else:
                if is_git_repo:
                    git_revert_to(cwd, best_commit, written)
                status = "discard"
                logger.info("  DISCARD (score {:.3f} <= best {:.3f})", score, best_score)

            _emit_event("round_decision", task_id=task_id, round=round_num,
                        status=status, score=round(score, 4), best_score=round(best_score, 4))

            # 5. Log round — structured context for next iteration and audit trail
            round_entry = {
                # Identity
                "round": round_num,
                "task_id": task_id,
                # Scoring
                "score": score,
                "prev_score": rounds_history[-1]["score"] if rounds_history else 0,
                "delta": score - (rounds_history[-1]["score"] if rounds_history else 0),
                "dod_passed": evidence_raw["dod_passed"],
                # Decision
                "status": status,
                "strategy": strategy,
                # Errors (fed back to LLM in fix prompt)
                "error_count": evidence_raw["error_count"],
                "error_severity": evidence_raw["error_severity"],
                "errors_by_type": evidence_raw["errors_by_type"],
                "lint_violations": evidence_raw["lint_violations"],
                "bp_violations": evidence_raw["bp_violations"],
                # Condensed error evidence (structured, not raw dump)
                "error_evidence": evidence_raw.get("error_evidence"),
                # Output (truncated for prompt; full logs in output/logs/)
                "stdout": evidence_raw["stdout"][:1000],
                "stderr": evidence_raw["stderr"][:1000],
                # Files
                "written_files": written,
                "commit": best_commit[:8] if best_commit else "",
                "backend": cur_backend, "reasoning": cur_reasoning,
                "temperature": round(temperature, 1),
                "timestamp": evidence_raw["timestamp"],
                # v2 JSON header: LLM's self-reported summary/approach
                "llm_summary": (llm_metadata or {}).get("summary", ""),
                "llm_approach": (llm_metadata or {}).get("approach", ""),
                # Zero-write diagnosis (only present when LLM wrote nothing)
                "zero_write_reason": evidence_raw.get("_zero_write_reason", ""),
                # Tool call trace (compressed text for prompt, structured for /memory)
                "tool_trace": trace_text,
                "tool_trace_events": trace_events_json,
            }
            rounds_history.append(round_entry)

            # Save structured context JSON per round (debuggable inter-round contract)
            (log_dir / f"round_{round_num}_context.json").write_text(
                json.dumps(round_entry, indent=2, default=str))

            file_symbols = extract_symbols(written, cwd) if written else ""
            # Learn ALL rounds to /memory — failures are training signal for what NOT to do.
            # Tags distinguish outcome:pass vs outcome:fail for recall filtering.
            log_round(output_dir, task_id, round_entry,
                      session_key=session_key, symbols=file_symbols,
                      learn_to_memory=True, scope=Path(cwd).name)

            # 6. Check if DoD passed
            if evidence_raw["dod_passed"]:
                _emit_event("dod_passed", task_id=task_id, round=round_num,
                            score=round(score, 4), total_rounds=round_num)
                logger.info("=== DoD PASSED on round {} (score={:.3f}) ===", round_num, score)
                break

        # Final outputs
        response_file = output_dir / f"{task_id}.response.txt"
        response_file.write_text(final_response)

        status = "pass" if rounds_history and rounds_history[-1]["dod_passed"] else "fail"
        if not rounds_history:
            failure_reason = failure_reason or "No rounds completed. Check git state and scillm connectivity."
        elif not failure_reason and status == "fail":
            last = rounds_history[-1]
            failure_reason = (f"DoD failed after {len(rounds_history)} rounds. "
                              f"Best score: {best_score:.3f}. Last strategy: {last.get('strategy', '?')}.")
        result = TaskResult(
            task_id=task_id, title=title,
            status=status,
            rounds=len(rounds_history), best_score=best_score,
            dod_passed=rounds_history[-1]["dod_passed"] if rounds_history else False,
            backend=llm_backend,
            best_commit=best_commit[:8] if best_commit else "",
            error=failure_reason,
            round_details=rounds_history,
        )
        result_file = output_dir / f"{task_id}.result.json"
        result_file.write_text(result.model_dump_json(indent=2))

        _emit_event("run_complete", task_id=task_id, status=result.status,
                    score=round(best_score, 4), rounds=len(rounds_history),
                    dod_passed=result.dod_passed, backend=llm_backend)
        logger.info("=== RESULT: {} | score={:.3f} | {} rounds ===",
                     result.status.upper(), best_score, len(rounds_history))

        # Record duration to /memory for timeout estimation flywheel
        run_duration = time.monotonic() - run_start_time
        from estimate_timeout import record as record_duration
        record_duration(
            "code-runner", run_duration,
            units=len(rounds_history),
            outcome="success" if result.dod_passed else "failed",
            trigger="orchestrate",
            metadata={"task_id": task_id, "backend": llm_backend,
                      "best_score": best_score, "rounds": len(rounds_history)},
        )

        if is_git_repo:
            generate_hunk_review(output_dir, task_id, cwd, rounds_history, snapshot)

        print(final_response)

        if not result.dod_passed:
            sys.exit(1)
    except Exception as exc:
        # ── Crash reporting: write result.json + structured event so failures are NEVER silent ──
        import traceback
        crash_msg = f"{type(exc).__name__}: {exc}"
        crash_tb = traceback.format_exc()
        logger.critical("CODE-RUNNER CRASHED: {}", crash_msg)
        logger.critical("Traceback:\n{}", crash_tb)
        _emit_event("crash", task_id=task_id, error=crash_msg,
                     traceback=crash_tb[-500:])
        # Write result.json so orchestrator has structured failure data
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            crash_result = TaskResult(
                task_id=task_id, title=title,
                status="crash",
                rounds=len(rounds_history) if 'rounds_history' in dir() else 0,
                best_score=best_score if 'best_score' in dir() else 0,
                dod_passed=False,
                backend=llm_backend,
                error=f"CRASH: {crash_msg}",
                round_details=rounds_history if 'rounds_history' in dir() else [],
            )
            crash_result_file = output_dir / f"{task_id}.result.json"
            crash_result_file.write_text(crash_result.model_dump_json(indent=2))
            logger.info("Crash result written to {}", crash_result_file)
        except Exception as write_exc:
            logger.error("Failed to write crash result: {}", write_exc)
        raise  # re-raise so exit code is still non-zero
    finally:
        # Always restore stashed changes, even on crash
        if stashed:
            git_stash_pop(cwd)
        # Release repo lock and remove lock file
        if lock_file:
            try:
                fcntl.flock(lock_file, fcntl.LOCK_UN)
                lock_file.close()
                lock_path = git_dir / "code-runner.lock" if git_dir else None
                if lock_path and lock_path.exists():
                    lock_path.unlink()
            except Exception:
                pass  # best-effort cleanup


@app.command(name="dry-run")
def dry_run(spec_file: str = typer.Argument(..., help="Path to task spec JSON")) -> None:
    """Show what would execute without calling LLM."""
    spec = json.loads(Path(spec_file).read_text())
    dod = spec.get("definition_of_done", {})
    print(f"Task:      {spec.get('title', '?')}")
    print(f"Backend:   {spec.get('backend', 'text')}")
    print(f"CWD:       {spec.get('cwd', os.getcwd())}")
    print(f"DoD cmd:   {dod.get('command', '(none)')}")
    print(f"DoD assert: {dod.get('assertion', '(none)')}")
    print(f"Prompt:    {spec.get('prompt', '')[:200]}...")


if __name__ == "__main__":
    app()
