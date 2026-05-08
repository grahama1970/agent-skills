"""Diagnose/Fix split for code-runner retry loop.

Separates root-cause inference from code generation. Two scillm calls
instead of one combined "analyze + fix" call.

Architecture (from scratch.md spec):
  1. DIAGNOSE — separate scillm call at higher effort. Returns structured data only.
  2. VALIDATE — does primary_target.file exist? symbol exist in treesitter?
  3. DEDUP — same diagnosis as prior round? Escalate diagnoser, not fixer.
  4. FIX — lean prompt with only file + diagnosis + one repair intent.

Separating "understanding stuck" from "implementation stuck":
  - Understanding stuck: repeated/low-confidence diagnoses → escalate diagnoser
  - Implementation stuck: stable diagnosis, patches fail same way → escalate fixer
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import sys

import httpx
from loguru import logger
from pydantic import BaseModel, Field

# json_utils lives in common/ — add to path if needed
_common = str(Path(__file__).resolve().parent.parent / "common")
if _common not in sys.path:
    sys.path.insert(0, _common)
from json_utils import clean_json_string  # noqa: E402

from stderr_parser import ErrorEvidence

# ── Diagnosis Schema ───────────────────────────────────────────────────

class PrimaryTarget(BaseModel):
    file: str
    symbol: str = ""
    line: Optional[int] = None


class Diagnosis(BaseModel):
    """Structured diagnosis — execution contract, not advisory report."""
    failure_kind: str = Field(
        description="syntax_error|import_error|type_error|runtime_error|"
                    "assertion_failure|contract_mismatch|lint_failure|unknown"
    )
    confidence: float = Field(ge=0.0, le=1.0)
    root_cause: str
    primary_target: PrimaryTarget
    evidence: list[str] = Field(default_factory=list)
    repair_intent: str = Field(description="Singular, actionable repair description")
    do_not_do: list[str] = Field(default_factory=list)


# ── Diagnosis Call ─────────────────────────────────────────────────────

def normalize_scillm_chat_url(raw_url: str | None) -> str:
    """Return the concrete OpenAI-compatible chat completions endpoint."""
    url = (raw_url or "http://localhost:4001/v1/chat/completions").strip().rstrip("/")
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if path in ("", "/"):
        return f"{url}/v1/chat/completions"
    if path == "/v1":
        return f"{url}/chat/completions"
    return url


SCILLM_URL = normalize_scillm_chat_url(os.environ.get("SCILLM_API_BASE"))
SCILLM_KEY = os.environ.get("SCILLM_PROXY_KEY", "sk-dev-proxy-123")

_DIAGNOSE_SYSTEM = """You are a code failure diagnostician. You receive error output and source code.
Your job is to produce a STRUCTURED DIAGNOSIS in JSON. Do NOT propose code fixes.

Return EXACTLY this JSON schema (no markdown, no explanation):
{
  "failure_kind": "syntax_error|import_error|type_error|runtime_error|assertion_failure|contract_mismatch|lint_failure|unknown",
  "confidence": 0.0-1.0,
  "root_cause": "one sentence explaining WHY the code fails",
  "primary_target": {
    "file": "path/to/file.py",
    "symbol": "function_or_class_name",
    "line": 42
  },
  "evidence": ["stderr line 1 that supports diagnosis", "stderr line 2"],
  "repair_intent": "one sentence describing what the fix should do",
  "do_not_do": ["do not change public API signatures", "do not suppress the exception"]
}

Rules:
- repair_intent must be SINGULAR and ACTIONABLE
- primary_target.file must be a real file path from the provided context
- evidence must be actual lines from the error output
- do_not_do prevents common bad fixes for this failure type
- confidence < 0.5 means you are guessing — say so in root_cause"""


def call_diagnose(
    error_evidence: ErrorEvidence,
    stderr: str,
    stdout: str,
    file_content: str,
    symbols: str,
    task_prompt: str,
    backend: str = "codex",
    reasoning: str = "high",
) -> Diagnosis:
    """Call scillm to produce structured diagnosis. No code, just analysis."""
    model = {
        "codex": "gpt-5.5",
        "claude": "claude-sonnet-4-6",
        "gemini": "text-gemini",
    }.get(backend, "gpt-5.5")

    user_prompt = (
        f"TASK: {task_prompt[:500]}\n\n"
        f"ERROR EVIDENCE:\n{error_evidence.to_prompt_block()}\n\n"
        f"STDERR (last 1500 chars):\n{stderr[-1500:]}\n\n"
        f"STDOUT (last 500 chars):\n{stdout[-500:]}\n\n"
        f"SYMBOLS:\n{symbols[:1000]}\n\n"
        f"FILE CONTENT:\n{file_content[:4000]}\n\n"
        f"Produce a structured JSON diagnosis. No code."
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _DIAGNOSE_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
    }

    # Claude doesn't support response_format
    if model.startswith("claude-"):
        del payload["response_format"]

    resp = httpx.post(
        SCILLM_URL,
        headers={
            "Authorization": f"Bearer {SCILLM_KEY}",
            "X-Caller-Skill": "code-runner:diagnose",
        },
        json=payload,
        timeout=httpx.Timeout(120.0, connect=5.0),
    )
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"]

    # Parse — use json_utils repair chain (fences, regex extract, json_repair)
    parsed = clean_json_string(raw, return_dict=True)
    if isinstance(parsed, dict):
        return Diagnosis.model_validate(parsed)

    # Fallback: retry once with fresh corrective instruction (don't anchor on bad output)
    logger.warning("Diagnosis JSON parse failed, retrying with explicit format instruction")
    retry_payload = {
        **payload,
        "messages": [
            payload["messages"][0],  # system prompt (unchanged)
            payload["messages"][1],  # original user prompt (unchanged)
            {"role": "user", "content": "Your previous response was not valid JSON. Return ONLY the JSON object matching the schema above. No explanation, no markdown fences."},
        ],
    }
    retry_resp = httpx.post(
        SCILLM_URL,
        headers={
            "Authorization": f"Bearer {SCILLM_KEY}",
            "X-Caller-Skill": "code-runner:diagnose",
        },
        json=retry_payload,
        timeout=httpx.Timeout(120.0, connect=5.0),
    )
    retry_resp.raise_for_status()
    retry_raw = retry_resp.json()["choices"][0]["message"]["content"]
    retry_parsed = clean_json_string(retry_raw, return_dict=True)
    if isinstance(retry_parsed, dict):
        return Diagnosis.model_validate(retry_parsed)

    raise ValueError(f"Diagnosis JSON parse failed after retry: {retry_raw[:200]}")


# ── Diagnosis Validation (HARD GATE — rejects, does not warn) ─────────

class DiagnosisRejected(ValueError):
    """Raised when diagnosis fails hard validation. Caller must handle."""
    def __init__(self, reasons: list[str]):
        self.reasons = reasons
        super().__init__(f"Diagnosis rejected: {'; '.join(reasons)}")


@dataclass
class DiagnosisValidation:
    valid: bool
    hard_failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_diagnosis(
    diagnosis: Diagnosis,
    cwd: str,
    symbols: str = "",
    stderr: str = "",
    stdout: str = "",
) -> DiagnosisValidation:
    """Hard-gate diagnosis validation. Rejects garbage instead of warning.

    Hard failures (diagnosis rejected):
      - primary_target.file does not exist
      - evidence lines not grounded in stderr/stdout
      - confidence below threshold with no evidence

    Warnings (logged but diagnosis proceeds):
      - symbol not in treesitter (may be dynamic/generated)
      - low confidence with evidence present
    """
    hard_failures: list[str] = []
    warnings: list[str] = []

    # HARD: primary_target.file must exist AND resolve inside cwd (no path traversal)
    cwd_resolved = Path(cwd).resolve()
    target_raw = diagnosis.primary_target.file
    if Path(target_raw).is_absolute():
        hard_failures.append(
            f"primary_target.file is absolute path (rejected): {target_raw}"
        )
    else:
        target_path = (cwd_resolved / target_raw).resolve()
        if not target_path.is_relative_to(cwd_resolved):
            hard_failures.append(
                f"primary_target.file escapes cwd via traversal: {target_raw}"
            )
        elif not target_path.exists():
            hard_failures.append(
                f"primary_target.file does not exist: {target_raw}"
            )

    # HARD: evidence must be grounded in actual stderr/stdout
    # At least one evidence line must appear (substring) in the real output
    # Strip ANSI escape codes + collapse whitespace before matching
    _ansi_re = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
    def _normalize(s: str) -> str:
        return re.sub(r"\s+", " ", _ansi_re.sub("", s)).lower().strip()

    combined_output = _normalize(stderr + "\n" + stdout)
    if diagnosis.evidence:
        grounded_count = sum(
            1 for e in diagnosis.evidence
            if _normalize(e)[:40] in combined_output  # first 40 chars match
        )
        if grounded_count == 0:
            hard_failures.append(
                f"no evidence lines grounded in stderr/stdout "
                f"({len(diagnosis.evidence)} claimed, 0 found)"
            )
    else:
        # No evidence at all — hard fail unless confidence is very high
        if diagnosis.confidence < 0.9:
            hard_failures.append(
                "no evidence lines and confidence < 0.9"
            )

    # HARD: confidence floor — reject guesses
    if diagnosis.confidence < 0.3:
        hard_failures.append(
            f"confidence too low ({diagnosis.confidence:.2f}), diagnosis is a guess"
        )

    # WARN: symbol check (soft — symbols may be generated or dynamic)
    if diagnosis.primary_target.symbol and symbols:
        if diagnosis.primary_target.symbol not in symbols:
            warnings.append(
                f"primary_target.symbol not in treesitter: "
                f"{diagnosis.primary_target.symbol}"
            )

    # WARN: low confidence with evidence (proceed with caution)
    if 0.3 <= diagnosis.confidence < 0.5 and not hard_failures:
        warnings.append(f"low confidence ({diagnosis.confidence:.2f})")

    return DiagnosisValidation(
        valid=len(hard_failures) == 0,
        hard_failures=hard_failures,
        warnings=warnings,
    )


# ── Fix-to-Diagnosis Consistency Check ─────────────────────────────────

@dataclass
class ConsistencyResult:
    consistent: bool
    violations: list[str] = field(default_factory=list)


def _treesitter_symbols(file_path: Path) -> set[str]:
    """Extract symbol names from a file via treesitter. Returns set of names."""
    skills_dir = Path(os.environ.get("SKILLS_DIR", str(Path(__file__).resolve().parent.parent)))
    treesitter_skill = skills_dir / "treesitter"
    if not treesitter_skill.exists() or not file_path.exists():
        return set()
    try:
        proc = subprocess.run(
            ["bash", "-lc",
             f"cd {shlex.quote(str(treesitter_skill))} && "
             f"./run.sh parse {shlex.quote(str(file_path))} --json"],
            capture_output=True, text=True, timeout=10,
            env={**os.environ, "VIRTUAL_ENV": ""},
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return set()
        data = json.loads(proc.stdout)
        items = data if isinstance(data, list) else data.get("symbols", [])
        return {item["name"] for item in items if item.get("name")}
    except (json.JSONDecodeError, subprocess.TimeoutExpired, OSError, KeyError):
        return set()


def _symbol_diff(before: set[str], after: set[str]) -> set[str]:
    """Return symbols that were added, removed, or (by proxy) modified.

    We can't detect in-body changes from names alone, so we return the
    symmetric difference (added + removed). If the target symbol was
    renamed, it shows up as removed-old + added-new.
    """
    return before.symmetric_difference(after)


def check_fix_consistency(
    diagnosis: Diagnosis,
    written_files: list[str],
    allowlist: list[str] | None = None,
    cwd: str = "",
    pre_fix_symbols: dict[str, set[str]] | None = None,
) -> ConsistencyResult:
    """Verify the fix actually addresses the diagnosis. Reject drift.

    Checks:
    1. Patch must touch the diagnosed target file (or a direct dependency)
    2. Patch must not ONLY touch test files when diagnosis targets source
    3. Patch must not edit files outside allowlist
    4. If diagnosis names a symbol, treesitter diff must show that symbol changed
    """
    violations: list[str] = []
    target_file = diagnosis.primary_target.file

    if not written_files:
        violations.append("fix wrote zero files")
        return ConsistencyResult(consistent=False, violations=violations)

    # Check 1: diagnosed target file must be in written files
    target_touched = any(
        f == target_file
        or f.endswith(Path(target_file).name)
        or Path(target_file).name == Path(f).name
        for f in written_files
    )
    if not target_touched:
        violations.append(
            f"diagnosis targets {target_file} but fix edited: "
            f"{', '.join(written_files)}"
        )

    # Check 2: if diagnosis targets source, fix must not ONLY touch tests
    if target_file and not any(t in target_file for t in ("test", "spec", "fixture")):
        only_tests = all(
            any(t in f for t in ("test", "spec", "fixture", "__test__", "_test."))
            for f in written_files
        )
        if only_tests:
            violations.append(
                f"diagnosis targets source ({target_file}) but fix only edited tests"
            )

    # Check 3: files outside allowlist
    if allowlist:
        for f in written_files:
            in_allowlist = any(
                f == a or f.startswith(a) or Path(f).name == Path(a).name
                for a in allowlist
            )
            if not in_allowlist:
                violations.append(f"fix edited {f} which is outside allowlist")

    # Check 4: treesitter symbol diff — did the fix touch the diagnosed symbol?
    # Only fires when: diagnosis names a symbol, cwd is provided, and pre-fix
    # symbols were captured. This is a WARNING, not a hard rejection — in-body
    # changes (same function name, different implementation) won't show up in
    # the symbol list, so we can't hard-reject on this alone.
    target_symbol = diagnosis.primary_target.symbol
    if target_symbol and cwd and pre_fix_symbols is not None:
        # Find the target file in written_files (fuzzy match like Check 1)
        matched_file = None
        for f in written_files:
            if (f == target_file
                    or f.endswith(Path(target_file).name)
                    or Path(target_file).name == Path(f).name):
                matched_file = f
                break

        if matched_file:
            before = pre_fix_symbols.get(matched_file, set())
            abs_path = Path(cwd) / matched_file if not Path(matched_file).is_absolute() else Path(matched_file)
            after = _treesitter_symbols(abs_path)

            if before and after:
                changed = _symbol_diff(before, after)
                # If symbols changed but target wasn't among them, the fix
                # edited the right file but the wrong function
                if changed and target_symbol not in changed:
                    # Check if target is still present (in-body change, not rename)
                    if target_symbol in after:
                        logger.info(
                            "Symbol drift check: {} still exists, "
                            "assuming in-body change (OK)",
                            target_symbol,
                        )
                    else:
                        violations.append(
                            f"diagnosis targets symbol '{target_symbol}' but fix "
                            f"changed different symbols: {', '.join(sorted(changed)[:5])}"
                        )

    return ConsistencyResult(
        consistent=len(violations) == 0,
        violations=violations,
    )


# ── Diagnosis Dedup ────────────────────────────────────────────────────

@dataclass
class StagnationSignal:
    stagnation_type: str  # "none" | "understanding" | "implementation"
    reason: str = ""


def check_stagnation(
    diagnosis: Diagnosis,
    prior_diagnoses: list[Diagnosis],
    prior_scores: list[float],
) -> StagnationSignal:
    """Compare current diagnosis to prior rounds. Detect understanding vs implementation stuck."""
    if not prior_diagnoses:
        return StagnationSignal("none")

    last = prior_diagnoses[-1]

    # Same root cause + same target = understanding stuck (diagnoser not helping)
    same_root = (
        diagnosis.root_cause == last.root_cause
        and diagnosis.primary_target.file == last.primary_target.file
        and diagnosis.failure_kind == last.failure_kind
    )

    if same_root:
        # But if evidence changed, it might be a different aspect of the same problem
        evidence_changed = set(diagnosis.evidence) != set(last.evidence)
        if not evidence_changed:
            return StagnationSignal(
                "understanding",
                f"Same diagnosis repeated: {diagnosis.failure_kind} in {diagnosis.primary_target.file}"
            )

    # Different diagnosis but score not improving = implementation stuck
    if len(prior_scores) >= 2 and prior_scores[-1] <= prior_scores[-2]:
        return StagnationSignal(
            "implementation",
            f"Diagnosis changed but score stagnant ({prior_scores[-1]:.3f} <= {prior_scores[-2]:.3f})"
        )

    return StagnationSignal("none")


# ── Fix Prompt (lean — diagnosis-constrained) ──────────────────────────

def build_fix_from_diagnosis(
    diagnosis: Diagnosis,
    file_content: str,
    allowlist: list[str] | None = None,
    prior_tool_trace: str = "",
) -> str:
    """Build a lean fix prompt constrained by the diagnosis. No trajectory dump."""
    allowlist_block = ""
    if allowlist:
        allowlist_block = f"EDITABLE FILES: {', '.join(allowlist)}\n\n"

    do_not_block = ""
    if diagnosis.do_not_do:
        do_not_block = "DO NOT:\n" + "\n".join(f"  - {d}" for d in diagnosis.do_not_do) + "\n\n"

    tool_trace_block = ""
    if prior_tool_trace:
        tool_trace_block = (
            "WHAT YOU TRIED LAST ROUND (do not repeat failed approaches):\n"
            f"{prior_tool_trace}\n\n"
        )

    return (
        f"OBJECTIVE: {diagnosis.repair_intent}\n\n"
        f"{allowlist_block}"
        f"DIAGNOSIS:\n"
        f"  Failure: {diagnosis.failure_kind}\n"
        f"  Root cause: {diagnosis.root_cause}\n"
        f"  Target: {diagnosis.primary_target.file}"
        f"{'::' + diagnosis.primary_target.symbol if diagnosis.primary_target.symbol else ''}"
        f"{':' + str(diagnosis.primary_target.line) if diagnosis.primary_target.line else ''}\n"
        f"  Evidence:\n" + "\n".join(f"    {e}" for e in diagnosis.evidence[:5]) + "\n\n"
        f"{tool_trace_block}"
        f"{do_not_block}"
        f"FILE CONTENT:\n{file_content}\n"
    )
