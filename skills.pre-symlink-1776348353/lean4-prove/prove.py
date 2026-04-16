#!/usr/bin/env python3
"""
lean4-prove: Generate and verify Lean4 proofs using Claude CLI.

Takes a requirement + optional tactics + optional persona, generates proof
candidates via Claude, compiles each in Docker, retries with error feedback.

Supports retrieval-augmented generation from the DeepSeek-Prover-V1 dataset
stored in ArangoDB (via memory skill).

DB/retrieval/memory layer lives in prove_retrieval.py.
"""
import json
import os
import re
import subprocess
import sys
import concurrent.futures
from pathlib import Path
from typing import Optional, List, Dict, Any

import httpx
import typer
from loguru import logger
from prove_retrieval import (
    RETRIEVAL_ENABLED,
    RETRIEVAL_K,
    retrieve_similar_proofs,
    build_support_pack,
    extract_lemma_deps,
    learn_result,
    # Re-export for backward compatibility (sanity.sh imports these)
    get_arango_db,
)

# Default model for theorem proving — uses scillm text cascade
DEFAULT_MODEL = os.getenv("LEAN4_PROVE_MODEL", "text")
SCILLM_BASE = os.getenv("SCILLM_API_BASE", "http://localhost:4001")
SCILLM_KEY = os.getenv("SCILLM_PROXY_KEY", "sk-dev-proxy-123")


def call_claude(prompt: str, system: str, model: str = None) -> str:
    """Call LLM via scillm Docker proxy (httpx).

    Replaces the old `claude -p` subprocess approach.
    Uses the standard OpenAI-compatible endpoint at localhost:4001.
    """
    model = model or DEFAULT_MODEL

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    resp = httpx.post(
        f"{SCILLM_BASE}/v1/chat/completions",
        json={
            "model": model,
            "messages": messages,
            "max_tokens": 4096,
            "temperature": 0.2,
        },
        headers={"Authorization": f"Bearer {SCILLM_KEY}"},
        timeout=180,
    )
    resp.raise_for_status()
    data = resp.json()

    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"scillm malformed response: {exc}") from exc


LEAN4_SERVICE_URL = os.getenv("LEAN4_SERVICE_URL", "http://127.0.0.1:8604")


def compile_lean(code: str, container: str, timeout: int) -> Dict[str, Any]:
    """Compile Lean4 code via HTTP service or lean-interact fallback.

    Priority:
      1. lean4-prove-service HTTP at LEAN4_SERVICE_URL (:8604) — preferred
      2. lean-interact host-native — fallback if HTTP unavailable
    """
    # 1. Docker HTTP compilation service (preferred — stable, no import side effects)
    try:
        resp = httpx.post(
            f"{LEAN4_SERVICE_URL}/compile",
            json={"code": code, "timeout": timeout},
            timeout=timeout + 10,
        )
        if resp.status_code == 200:
            result = resp.json()
            return {
                "success": result.get("success", False),
                "exit_code": 0 if result.get("success") else 1,
                "stdout": result.get("stdout", ""),
                "stderr": result.get("error", ""),
                "elapsed_ms": result.get("elapsed_ms"),
            }
        logger.warning("Lean4 HTTP service returned {}: {}", resp.status_code, resp.text[:200])
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        logger.debug("Lean4 HTTP service unavailable: {}", e)
    except Exception as e:
        logger.warning("Lean4 HTTP service error: {}", e)

    # 2. lean-interact fallback (import can be slow on cold start)
    try:
        from compiler import compile_lean_compat
        return compile_lean_compat(code, container="_internal", timeout=timeout)
    except ImportError:
        pass
    except Exception as e:
        logger.warning("lean-interact error: {}", e)

    return {
        "success": False,
        "exit_code": 1,
        "stdout": "",
        "stderr": f"No compilation backend: HTTP service at {LEAN4_SERVICE_URL} "
                  f"unavailable, lean-interact not installed",
    }


def extract_lean_code(response: str) -> str:
    """Extract Lean4 code from Claude response."""
    # Look for ```lean or ```lean4 blocks
    patterns = [
        r'```lean4?\s*\n(.*?)```',
        r'```\s*\n(.*?)```',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, response, re.DOTALL)
        if matches:
            return matches[0].strip()

    # If no code blocks, return the whole response (might be raw code)
    return response.strip()


def build_system_prompt(
    tactics: list[str] | None,
    persona: str | None,
    support_pack: Dict[str, Any] | None = None,
) -> str:
    """Build system prompt with optional tactics, persona, and retrieved exemplars."""
    parts = [
        "You are an expert Lean4 theorem prover. Generate valid, compilable Lean4 code.",
        "Return ONLY the Lean4 code in a ```lean4 code block. No explanations.",
        "The code must be self-contained and compile with `lake env lean`."
    ]

    # Add validated imports from exemplars
    if support_pack and support_pack.get("imports"):
        imports_list = sorted(support_pack["imports"])
        parts.append(f"\nUse these imports (validated to work):\n```lean4\n{chr(10).join(imports_list)}\n```")

    # Add tactics from user + exemplars
    all_tactics = set(tactics or [])
    if support_pack and support_pack.get("tactics"):
        all_tactics.update(support_pack["tactics"])
    if all_tactics:
        parts.append(f"\nPreferred tactics: {', '.join(sorted(all_tactics))}")

    # Add similar proof examples
    if support_pack and support_pack.get("examples"):
        parts.append("\n## Similar proofs that compiled successfully:")
        for i, ex in enumerate(support_pack["examples"], 1):
            parts.append(f"\nExample {i}:")
            parts.append(f"Statement: {ex['statement']}")
            parts.append(f"Proof: {ex['proof']}")

    if persona:
        parts.append(f"\nPersona: {persona}")

    return "\n".join(parts)


def build_retry_prompt(requirement: str, previous_code: str, error: str) -> str:
    """Build prompt for retry attempt with error feedback."""
    return f"""Previous attempt failed to compile.

Requirement: {requirement}

Previous code:
```lean4
{previous_code}
```

Compiler error:
{error}

Fix the code to compile successfully. Return ONLY the corrected Lean4 code."""


def generate_candidate(
    requirement: str,
    system_prompt: str,
    model: str,
    candidate_id: int
) -> tuple[int, str]:
    """Generate a single proof candidate."""
    prompt = f"Prove the following in Lean4:\n\n{requirement}"
    response = call_claude(prompt, system_prompt, model)
    code = extract_lean_code(response)
    return (candidate_id, code)


# ── Provability gate ────────────────────────────────────────────────────
# Classifier-based early rejection of inputs that can't be formalized.
#
# Design principles:
#   - NO regex (we don't know what inputs look like — regex is brittle)
#   - Default to ALLOW (lean4 coverage is crucial for requirements)
#   - Only reject at high classifier confidence (>= 0.80)
#   - Graceful degradation if /assistant unavailable
#   - The 91.6% proof success rate on compliance requirements proves
#     that MOST inputs ARE formalizable — the gate catches the few that aren't
#
# Train the classifier:
#   /create-classifier lean4_provable --export-from proof_jobs
#   (uses 477+ proved vs 5 failed outcomes as training signal)


def _check_provable(requirement: str) -> str | None:
    """Check if input is formalizable using /assistant classifier cascade.

    Returns rejection reason if classifier is confident the input cannot
    be formalized into a Lean4 theorem. Returns None to allow through.

    The classifier is trained on actual proof outcomes from the proof_jobs
    collection — it learns what requirement text succeeds vs fails, not
    what the input format looks like.
    """
    text = requirement.strip()

    # Only hard gate: truly empty input
    if not text:
        return "empty input"

    # Use /assistant classifier cascade (heuristic → classifier → GPT → scillm)
    try:
        _skills = str(Path.home() / ".pi" / "skills")
        if _skills not in sys.path:
            sys.path.insert(0, _skills)
        from assistant import classify

        result = classify(
            text=text,
            task="lean4_provable",
            confidence_threshold=0.80,  # Blocks bare IDs/headers/boilerplate; passes all real requirements
        )

        if (result.prediction == "not_formalizable"
                and result.confidence >= 0.80):
            return (
                f"classifier rejected (confidence={result.confidence:.2f}, "
                f"tier={result.tier}, source={result.source}): "
                f"input unlikely to be formalizable as a Lean4 theorem"
            )
    except ImportError:
        pass  # /assistant not available — allow through
    except Exception as e:
        # Log but never block on classifier errors
        print(
            f"[lean4-prove] provability check error (allowing through): {e}",
            file=sys.stderr,
        )

    # Default: allow through (maximize lean4 coverage)
    return None


def prove(
    requirement: str,
    tactics: list[str] | None = None,
    persona: str | None = None,
    max_retries: int = 3,
    candidates: int = 3,
    model: str = "text",
    container: str = "lean_runner",
    timeout: int = 120,
    project: str | None = None,
    extract_deps: bool = False,
) -> Dict[str, Any]:
    """
    Generate and verify a Lean4 proof.

    Args:
        requirement: The theorem to prove
        tactics: Preferred tactics to use (e.g., ["simp", "ring", "omega"])
        persona: Optional persona context (e.g., "cryptographer")
        max_retries: Maximum retry attempts per candidate
        candidates: Number of parallel proof candidates to generate
        model: Claude model alias (sonnet, opus, haiku) or full name
        container: Docker container name
        timeout: Compilation timeout in seconds
        project: Project identifier for grouping related proofs (for dependency graph)
        extract_deps: Whether to extract lemma dependencies after successful proof

    Returns:
        dict with success, code, attempts, errors
    """
    # Check compilation backend availability (HTTP service preferred)
    _has_backend = False
    try:
        health_resp = httpx.get(f"{LEAN4_SERVICE_URL}/health", timeout=5)
        _has_backend = health_resp.status_code == 200 and health_resp.json().get("ok", False)
    except Exception:
        pass

    if not _has_backend:
        # Check lean-interact as fallback
        try:
            from compiler import compile_lean_compat  # noqa: F401
            _has_backend = True
        except ImportError:
            pass

    if not _has_backend:
        return {
            "success": False,
            "error": f"No compilation backend available: "
                     f"HTTP service at {LEAN4_SERVICE_URL} not responding, "
                     f"lean-interact not installed",
            "code": None,
            "attempts": 0
        }

    # ── Early rejection gate ────────────────────────────────────────────
    # Reject non-mathematical inputs before burning Claude Opus + Docker.
    # Uses /assistant classifier if available, falls back to heuristics.
    rejection = _check_provable(requirement)
    if rejection:
        return {
            "success": False,
            "error": f"Input rejected (not a provable theorem): {rejection}",
            "code": None,
            "attempts": 0,
            "rejected_early": True,
        }

    # Retrieval-augmented generation: fetch similar proofs
    support_pack = None
    retrieval_info = None
    if RETRIEVAL_ENABLED:
        exemplars = retrieve_similar_proofs(requirement, tactics, k=RETRIEVAL_K)
        if exemplars:
            support_pack = build_support_pack(exemplars)
            retrieval_info = {
                "retrieved": len(exemplars),
                "tactics_added": list(support_pack.get("tactics", [])),
                "imports_count": len(support_pack.get("imports", [])),
            }

    system_prompt = build_system_prompt(tactics, persona, support_pack)

    # ── Dispatch via /code-runner ──────────────────────────────────────
    # Each candidate is a /code-runner session with lean4 compile as DoD.
    # /code-runner handles the propose→compile→fix loop (up to max_retries).
    #
    # DoD: curl lean4 HTTP service, parse JSON, check success field.
    # The code-runner writes a .lean file, DoD compiles it.

    import tempfile
    code_runner = Path(__file__).parent.parent / "code-runner" / "run.sh"
    if not code_runner.exists():
        # Fallback to legacy path
        code_runner = Path.home() / ".pi" / "skills" / "code-runner" / "run.sh"

    if not code_runner.exists():
        return {
            "success": False,
            "error": f"/code-runner not found at {code_runner}",
            "code": None,
            "attempts": 0,
        }

    all_errors: list[str] = []
    total_attempts = 0

    # DoD: compile proof.lean via lean4 HTTP service using curl (always available)
    dod_script = (
        f"test -f proof.lean || {{ echo 'ERROR: proof.lean not found'; exit 1; }}; "
        f"RESULT=$(curl -sf {LEAN4_SERVICE_URL}/compile "
        f"-H 'Content-Type: application/json' "
        f"--max-time {timeout + 10} "
        f"-d \"$(python3 -c \"import json; print(json.dumps({{'code': open('proof.lean').read(), 'timeout': {timeout}}}))\")\" "
        f"); "
        f"echo \"$RESULT\" | python3 -c \"import json,sys; d=json.load(sys.stdin); "
        f"print('COMPILED' if d.get('success') else 'ERROR: '+str(d.get('error',''))[:500]); "
        f"sys.exit(0 if d.get('success') else 1)\""
    )

    prompt = (
        f"{system_prompt}\n\n"
        f"Write a complete Lean4 proof for the following requirement.\n"
        f"The file must compile with the Lean4 compiler.\n\n"
        f"Requirement: {requirement}\n\n"
        f"Return your answer in EXACTLY this format:\n\n"
        f"### FILE: proof.lean\n"
        f"```lean\n"
        f"-- your Lean4 code here\n"
        f"```\n"
    )

    for cid in range(candidates):
        tmpdir = tempfile.mkdtemp(prefix="lean4_cr_")
        # code-runner needs a git repo for keep/discard
        subprocess.run(["git", "init", "-q"], cwd=tmpdir, capture_output=True,
                       env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"})
        subprocess.run(["git", "commit", "--allow-empty", "-m", "init", "-q"], cwd=tmpdir,
                       capture_output=True, env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"})

        spec = {
            "task_id": f"lean4-prove-c{cid}",
            "title": f"Lean4 proof candidate {cid}: {requirement[:80]}",
            "prompt": prompt,
            "backend": model,
            "cwd": tmpdir,
            "output_dir": tmpdir,
            "allowlist": ["proof.lean"],
            "definition_of_done": {
                "command": dod_script,
                "assertion": "COMPILED",
            },
            "max_rounds": max_retries,
        }

        spec_file = Path(tmpdir) / "task_spec.json"
        spec_file.write_text(json.dumps(spec, indent=2))

        try:
            proc = subprocess.run(
                [str(code_runner), "run", str(spec_file)],
                capture_output=True, text=True,
                timeout=timeout * max_retries + 60,
                cwd=tmpdir,
                env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
            )
            total_attempts += 1

            # Read result — /code-runner writes {task_id}.result.json
            result_file = Path(tmpdir) / f"lean4-prove-c{cid}.result.json"
            if not result_file.exists():
                matches = list(Path(tmpdir).glob("*.result.json"))
                if matches:
                    result_file = matches[0]
            if result_file.exists():
                cr_result = json.loads(result_file.read_text())
                if cr_result.get("dod_passed"):
                    proof_file = Path(tmpdir) / "proof.lean"
                    code = proof_file.read_text() if proof_file.exists() else None

                    if code:
                        lemma_deps = None
                        if extract_deps:
                            lemma_deps = extract_lemma_deps(code, container, timeout)

                        learned_key = learn_result(
                            requirement=requirement, code=code, success=True,
                            errors=None, tactics=tactics,
                            metadata={"model": model, "attempts": total_attempts,
                                      "candidate": cid, "runner": "code-runner",
                                      "rounds": cr_result.get("rounds", 0),
                                      "retrieval_count": retrieval_info.get("retrieved") if retrieval_info else 0},
                            project=project, lemma_deps=lemma_deps,
                        )

                        return {
                            "success": True,
                            "code": code,
                            "attempts": total_attempts,
                            "candidate": cid,
                            "errors": None,
                            "retrieval": retrieval_info,
                            "learned": learned_key,
                            "project": project,
                            "lemma_deps": lemma_deps,
                        }

                # DoD didn't pass
                all_errors.append(
                    f"Candidate {cid}: /code-runner {cr_result.get('rounds', 0)} rounds, "
                    f"score={cr_result.get('best_score', 0):.3f}, "
                    f"dod_passed={cr_result.get('dod_passed', False)}"
                )
            else:
                all_errors.append(f"Candidate {cid}: /code-runner produced no result.json")

        except subprocess.TimeoutExpired:
            all_errors.append(f"Candidate {cid}: /code-runner timeout")
        except Exception as e:
            all_errors.append(f"Candidate {cid}: /code-runner error: {e}")

    # All candidates failed
    learned_key = learn_result(
        requirement=requirement, code=None, success=False, errors=all_errors,
        tactics=tactics,
        metadata={"model": model, "attempts": total_attempts,
                  "retrieval_count": retrieval_info.get("retrieved") if retrieval_info else 0},
        project=project, lemma_deps=None,
    )

    return {
        "success": False,
        "code": None,
        "attempts": total_attempts,
        "errors": all_errors,
        "retrieval": retrieval_info,
        "learned": learned_key,
        "project": project,
    }


def main(
    requirement: Optional[str] = typer.Option(None, help="Theorem to prove"),
    tactics: Optional[str] = typer.Option(None, help="Comma-separated tactics"),
    persona: Optional[str] = typer.Option(None, help="Persona context"),
    retries: int = typer.Option(3, help="Max retries per candidate"),
    candidates: int = typer.Option(3, help="Parallel candidates"),
    model: str = typer.Option("text", help="scillm model (text, gemini, deepseek)"),
    container: str = typer.Option("lean_runner", help="Docker container"),
    timeout: int = typer.Option(120, help="Compile timeout"),
    project: Optional[str] = typer.Option(None, help="Project identifier for grouping related proofs"),
    extract_deps: bool = typer.Option(False, help="Extract lemma dependencies after successful proof"),
):
    """CLI entry point."""

    # Get requirement from args or stdin
    if requirement:
        requirement = requirement
    else:
        # Try JSON from stdin
        stdin_data = sys.stdin.read().strip()
        if stdin_data:
            try:
                data = json.loads(stdin_data)
                requirement = data.get("requirement", stdin_data)
                # Override with JSON values if present
                if "tactics" in data and not tactics:
                    tactics = ",".join(data["tactics"]) if isinstance(data["tactics"], list) else data["tactics"]
                if "persona" in data and not persona:
                    persona = data["persona"]
                if "project" in data and not project:
                    project = data["project"]
                if data.get("extract_deps") and not extract_deps:
                    extract_deps = True
            except json.JSONDecodeError:
                requirement = stdin_data
        else:
            parser.error("--requirement or stdin input required")

    tactics = tactics.split(",") if tactics else None

    result = prove(
        requirement=requirement,
        tactics=tactics,
        persona=persona,
        max_retries=retries,
        candidates=candidates,
        model=model,
        container=container,
        timeout=timeout,
        project=project,
        extract_deps=extract_deps,
    )

    print(json.dumps(result, indent=2))
    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    typer.run(main)
