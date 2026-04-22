"""T0 deterministic evidence collection and strategy escalation for code-runner.

All functions are pure subprocess + regex — no LLM calls.
Strategy escalation follows the same 5-step pattern as classifier-lab's 10-step.

NOTE: Core patterns (Strategy, ErrorSeverity, should_keep) are now in common/self_improvement.py
for sharing with prompt-lab and other self-improvement skills.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

import httpx
from loguru import logger

# Import shared patterns from common/
_skills_dir = Path(__file__).resolve().parent.parent
_common = str(_skills_dir / "common")
if _common not in sys.path:
    sys.path.insert(0, _common)

from self_improvement import (
    Strategy,
    STRATEGIES as _STRATEGIES_ENUM,
    get_strategy as _get_strategy_common,
    should_keep,  # noqa: F401 - re-exported for code_runner.py
    ErrorSeverity,
    ERROR_TYPE_TO_SEVERITY,
    classify_error_severity,
    strategy_instruction,  # noqa: F401 - re-exported
)

from language_profiles import get_profile, LanguageProfile

MEMORY_SOCKET = "/run/user/1000/embry/memory.sock"

# ── Error types for T0 classification ────────────────────────────────
# Legacy dict format for backwards compatibility. New code should use
# ErrorSeverity enum and ERROR_TYPE_TO_SEVERITY from common/self_improvement.py

ERROR_PATTERNS = {
    "SyntaxError": "syntax", "IndentationError": "syntax",
    "ImportError": "import", "ModuleNotFoundError": "import",
    "TypeError": "contract", "AttributeError": "contract", "KeyError": "contract",
    "AssertionError": "logic", "ValueError": "logic",
    "RuntimeError": "runtime", "FileNotFoundError": "runtime", "TimeoutError": "runtime",
    "NameError": "contract", "IndexError": "logic",
}

# ── Strategy escalation (5-step, like classifier-lab 10-step) ────────
# String list for backwards compatibility. New code should use Strategy enum.

STRATEGIES = ["direct_fix", "structured_analysis", "different_approach", "simplify", "escalate"]


def get_strategy(round_num: int, classification: dict, rounds_history: list[dict]) -> str:
    """Deterministic strategy selection based on round + error trajectory.

    Wrapper around common/self_improvement.get_strategy() that maintains
    the existing interface (dict-based classification, string return).
    """
    # Extract previous error severity from rounds_history
    prev_sev = None
    if rounds_history:
        prev_sev = rounds_history[-1].get("error_severity", "")

    # Current error severity from classification dict
    curr_sev = classification.get("severity", "")

    # Check if score is improving
    score_improving = False
    if len(rounds_history) >= 2:
        recent_scores = [r.get("score", 0) for r in rounds_history[-2:]]
        if len(recent_scores) == 2 and recent_scores[-1] > recent_scores[-2]:
            score_improving = True

    # Call common implementation
    strategy = _get_strategy_common(
        round_num=round_num,
        prev_error_severity=prev_sev,
        curr_error_severity=curr_sev,
        score_improving=score_improving,
    )

    # Return string for backwards compatibility
    return strategy.value


# ── T0 Deterministic Evidence Collection ─────────────────────────────


def classify_errors(stderr: str) -> dict:
    """T0: Parse stderr for error types. Pure regex, NO LLM."""
    errors_by_type: dict[str, int] = {}
    for pattern in ERROR_PATTERNS:
        count = len(re.findall(rf"\b{re.escape(pattern)}\b", stderr))
        if count:
            errors_by_type[pattern] = count

    total = sum(errors_by_type.values())

    # Determine severity from highest-priority error
    severity = "unknown"
    for error_type, sev in ERROR_PATTERNS.items():
        if error_type in errors_by_type:
            severity = sev
            break

    return {"error_types": errors_by_type, "total": total, "severity": severity}


def collect_evidence(cwd: str, dod_command: str, dod_assertion: str, lang: str = "") -> dict:
    """T0: Run ALL deterministic checks, return structured evidence JSON.

    Args:
        cwd: Working directory
        dod_command: Definition of Done shell command
        dod_assertion: Assertion to check in output
        lang: Language profile to use (python, rust, typescript). Empty = auto-detect.
    """
    # Get language profile for language-aware checks
    profile = get_profile(lang, cwd)
    logger.info("Using {} profile for evidence collection", profile.name)

    # 1. Run DoD command
    if dod_command:
        try:
            # Strip ALL .venv paths from env so DoD uses system/project Python
            clean_env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
            clean_env["PATH"] = os.pathsep.join(
                p for p in clean_env.get("PATH", "").split(os.pathsep)
                if ".venv" not in p
            )
            dod_timeout = int(os.environ.get("CODE_RUNNER_DOD_TIMEOUT", "60"))
            proc = subprocess.run(
                ["bash", "-lc", dod_command],
                capture_output=True, text=True, timeout=dod_timeout, cwd=cwd, env=clean_env,
            )
            stdout, stderr, exit_code = proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired:
            stdout, stderr, exit_code = "", f"DoD command timed out after {dod_timeout}s", 1
        except Exception as e:
            stdout, stderr, exit_code = "", f"DoD error: {e}", 1
    else:
        stdout, stderr, exit_code = "", "", 0

    # 2. Classify errors (language-aware)
    error_result = profile.classify_errors(stderr, stdout)
    classification = {
        "error_types": error_result.error_types,
        "total": error_result.total,
        "severity": error_result.severity,
    }

    # 3. Lint modified files (language-aware)
    modified_files = profile.get_modified_files(cwd)
    lint_result = profile.lint_check(modified_files, cwd)
    lint_violations = lint_result.violations

    # 3b. File size check — penalize files over 800 lines (project convention + LLM reliability limit)
    oversized_files: list[str] = []
    for f in modified_files:
        fpath = Path(cwd) / f
        if fpath.exists():
            loc = len(fpath.read_text(encoding="utf-8", errors="replace").splitlines())
            if loc > 800:
                oversized_files.append(f"{f} ({loc} lines)")

    # 4. Best-practices violations (language-aware)
    bp_violations: list[str] = []
    try:
        git_proc = subprocess.run(
            ["git", "diff", "HEAD"], capture_output=True, text=True, cwd=cwd, timeout=30,
        )
        bp_result = profile.best_practices(git_proc.stdout)
        bp_violations = bp_result.violations
    except subprocess.SubprocessError:
        pass

    # 5. DoD assertion check — safe predicates only, NO eval()
    combined = f"{stdout}\n{stderr}".strip()
    if not dod_assertion:
        dod_passed = exit_code == 0
    elif dod_assertion.strip() == "exit_code == 0":
        dod_passed = exit_code == 0
    elif dod_assertion.strip() == "exit_code != 0":
        dod_passed = exit_code != 0
    elif re.match(r'^exit_code\s*==\s*(\d+)$', dod_assertion.strip()):
        expected = int(re.match(r'^exit_code\s*==\s*(\d+)$', dod_assertion.strip()).group(1))
        dod_passed = exit_code == expected
    elif dod_assertion.strip().startswith("json_has_keys:"):
        # Structured: "json_has_keys: key1, key2, key3"
        keys = [k.strip() for k in dod_assertion.split(":", 1)[1].split(",")]
        try:
            data = json.loads(stdout.strip())
            dod_passed = exit_code == 0 and all(k in data for k in keys)
        except (json.JSONDecodeError, TypeError):
            dod_passed = False
    elif re.match(r'^(?:Returns|Contains|Has)\s+JSON\s+with\s+', dod_assertion, re.IGNORECASE):
        # Natural language: "Returns JSON with family_id, confidence, rules_matched"
        key_text = re.sub(r'^(?:Returns|Contains|Has)\s+JSON\s+with\s+', '', dod_assertion, flags=re.IGNORECASE)
        keys = [k.strip().strip('"\'') for k in re.split(r'[,\s]+', key_text) if k.strip()]
        try:
            data = json.loads(stdout.strip())
            dod_passed = exit_code == 0 and all(k in data for k in keys)
        except (json.JSONDecodeError, TypeError):
            dod_passed = exit_code == 0 and dod_assertion.lower() in combined.lower()
    else:
        # String match: assertion text must appear in output
        dod_passed = exit_code == 0 and dod_assertion.lower() in combined.lower()

    # 6. Composite score (0.0 = broken, 1.0 = perfect)
    # DoD is dominant: if DoD fails, score CAPPED at 0.49 regardless of other metrics
    # Oversized files penalize score (soft limit, not a hard block)
    size_penalty = 0.05 * len(oversized_files) if oversized_files else 0.0
    if dod_passed:
        score = (
            0.5
            + 0.25 * max(0.0, 1.0 - classification["total"] / 10.0)
            + 0.15 * max(0.0, 1.0 - lint_violations / 20.0)
            + 0.10 * (1.0 if not bp_violations else 0.0)
            - size_penalty
        )
    else:
        score = min(0.49, (
            0.3 * max(0.0, 1.0 - classification["total"] / 10.0)
            + 0.15 * max(0.0, 1.0 - lint_violations / 20.0)
            + 0.05 * (1.0 if not bp_violations else 0.0)
            - size_penalty
        ))

    return {
        "score": round(score, 4),
        "dod_passed": dod_passed,
        "exit_code": exit_code,
        "error_count": classification["total"],
        "oversized_files": oversized_files,
        "errors_by_type": classification["error_types"],
        "error_severity": classification["severity"],
        "lint_violations": lint_violations,
        "bp_violations": bp_violations,
        "stdout": stdout[:2000],  # truncated for prompt injection; full in stdout_full
        "stderr": stderr[:2000],  # truncated for prompt injection; full in stderr_full
        "stdout_full": stdout,
        "stderr_full": stderr,
        "timestamp": time.time(),
    }


def extract_symbols(file_paths: list[str], cwd: str) -> str:
    """Use /treesitter to extract function/class/import symbols from files. Fast + deterministic."""
    skills_dir = Path(os.environ.get("SKILLS_DIR", str(Path(__file__).resolve().parent.parent)))
    treesitter_skill = skills_dir / "treesitter"
    if not treesitter_skill.exists():
        return ""

    symbols: list[str] = []
    for fpath in file_paths[:5]:  # cap at 5 files to keep prompt reasonable
        abs_path = Path(cwd) / fpath if not Path(fpath).is_absolute() else Path(fpath)
        if not abs_path.exists():
            continue
        try:
            proc = subprocess.run(
                ["bash", "-lc", f"cd {shlex.quote(str(treesitter_skill))} && ./run.sh parse {shlex.quote(str(abs_path))} --json"],
                capture_output=True, text=True, timeout=10,
                env={**os.environ, "VIRTUAL_ENV": ""},
            )
            if proc.returncode == 0 and proc.stdout.strip():
                data = json.loads(proc.stdout)
                file_symbols = []
                for item in data if isinstance(data, list) else data.get("symbols", []):
                    kind = item.get("kind", item.get("type", ""))
                    name = item.get("name", "")
                    sig = item.get("signature", item.get("text", ""))
                    if name:
                        file_symbols.append(f"  {kind}: {sig or name}")
                if file_symbols:
                    symbols.append(f"  {fpath}:\n" + "\n".join(file_symbols[:20]))
        except (json.JSONDecodeError, subprocess.TimeoutExpired, Exception):
            pass

    return "\n".join(symbols) if symbols else ""


RECALL_CONFIDENCE_THRESHOLD = 0.55  # ignore low-confidence matches (subagent_v5 pattern)
RECALL_MAX_ITEMS = 3


def recall_similar_fixes(task_description: str, error_severity: str) -> str:
    """Recall prior SUCCESSFUL code-runner rounds via /memory httpx service.

    Filters by confidence threshold to avoid injecting irrelevant prior fixes.
    """
    query = f"CODE-RUNNER outcome:pass severity={error_severity} {task_description[:80]}"
    try:
        transport = httpx.HTTPTransport(uds=MEMORY_SOCKET)
        with httpx.Client(transport=transport, timeout=10.0) as client:
            resp = client.post("http://localhost/recall", json={
                "q": query, "scope": "code-runner", "limit": 10,
            })
            if resp.status_code != 200:
                return ""
            data = resp.json()
    except (httpx.ConnectError, OSError):
        return ""  # memory service down — non-fatal
    except Exception:
        return ""

    items = data.get("items", [])
    successful = []
    for item in items:
        confidence = item.get("confidence", item.get("score", 0))
        if isinstance(confidence, str):
            try:
                confidence = float(confidence)
            except ValueError:
                confidence = 0
        if confidence < RECALL_CONFIDENCE_THRESHOLD:
            continue

        solution = item.get("solution", "")
        if isinstance(solution, str):
            try:
                sol_data = json.loads(solution)
            except json.JSONDecodeError:
                sol_data = {}
        else:
            sol_data = solution
        if sol_data.get("dod_passed") or "outcome:pass" in (item.get("tags") or []):
            successful.append((item, confidence))

    successful.sort(key=lambda x: x[1], reverse=True)

    summaries = []
    for item, conf in successful[:RECALL_MAX_ITEMS]:
        problem = item.get("problem", "")[:150]
        sol_str = item.get("solution", "")
        try:
            sol = json.loads(sol_str) if isinstance(sol_str, str) else sol_str
            strategy = sol.get("strategy", "?")
            score = sol.get("score", 0)
            symbols = sol.get("symbols", "")[:200]
            summaries.append(
                f"  Prior fix: {problem}\n"
                f"    Strategy: {strategy}, Score: {score:.3f}"
                + (f"\n    Symbols: {symbols}" if symbols else "")
            )
        except (json.JSONDecodeError, TypeError):
            summaries.append(f"  Prior fix: {problem}")
    return "\n".join(summaries)


def build_fix_prompt(
    evidence: dict,
    rounds_history: list[dict],
    strategy: str,
    original_task: str,
    file_context: str = "",
    allowlist: list[str] | None = None,
) -> str:
    """Build user prompt for round 2+. Keep it simple — the LLM is not smart.

    System prompt has: original request, DoD, allowlist, format rules, prior fixes, history.
    User prompt has: what's wrong NOW, what strategy to try, current file state.
    """
    strategy_instructions = {
        "direct_fix": "Fix the specific error below.",
        "structured_analysis": (
            "Direct fix failed. Is this a missing import, data contract mismatch, or logic error? "
            "Fix based on error category."
        ),
        "different_approach": (
            "Same error keeps recurring. Try a fundamentally different approach. "
            "Do not expand scope."
        ),
        "simplify": (
            "Multiple approaches failed. Do the minimum viable implementation. "
            "Remove all complexity not required by the DoD."
        ),
    }

    # Condense stderr into structured evidence
    from stderr_parser import condense_stderr
    error_evidence = condense_stderr(
        evidence.get("stderr", ""), evidence.get("stdout", ""),
    )

    # One-liner objective
    err_loc = error_evidence.primary_location
    objective = f"Fix {err_loc.file}:{err_loc.line}" if err_loc and err_loc.file else "Fix the failing code"

    # Allowlist reminder to prevent drift in later rounds
    allowlist_reminder = ""
    if allowlist:
        allowlist_reminder = "EDITABLE FILES: " + ", ".join(allowlist) + "\n\n"

    return (
        f"OBJECTIVE: {objective}\n\n"
        f"{allowlist_reminder}"
        f"Strategy: {strategy}\n"
        f"{strategy_instructions.get(strategy, 'Fix the error.')}\n\n"
        f"Evidence:\n"
        f"  Score: {evidence['score']:.3f}\n"
        f"  DoD passed: {evidence['dod_passed']}\n"
        f"  Errors: {evidence.get('error_count', 0)}\n"
        f"  Lint: {evidence['lint_violations']}\n\n"
        f"Error diagnosis:\n{error_evidence.to_prompt_block()}\n\n"
        f"{file_context}\n"
    )
