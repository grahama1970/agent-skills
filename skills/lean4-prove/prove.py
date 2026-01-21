#!/usr/bin/env python3
"""
lean4-prove: Generate and verify Lean4 proofs using Claude CLI.

Takes a requirement + optional tactics + optional persona, generates proof
candidates via Claude, compiles each in Docker, retries with error feedback.
"""
import json
import os
import subprocess
import sys
import time
import concurrent.futures
from pathlib import Path
from typing import Optional

# Default model for theorem proving
DEFAULT_MODEL = os.getenv("LEAN4_PROVE_MODEL", "opus")


def call_claude(prompt: str, system: str, model: str = None) -> str:
    """Call Claude via Claude Code CLI in headless non-interactive mode.

    Args:
        prompt: The user prompt
        system: System prompt
        model: Model alias (sonnet, opus, haiku) or full name

    Returns:
        The Claude response text
    """
    model = model or DEFAULT_MODEL

    # Build the full prompt with system context
    full_prompt = f"{system}\n\n{prompt}"

    # Use Claude Code CLI with -p for print/headless mode
    # Key flags for headless operation:
    # - -p: print mode (non-interactive, outputs to stdout)
    # - --output-format text: plain text output
    # - --max-turns 1: single turn, no conversation
    # - --no-stream: wait for full response (don't stream)
    cmd = [
        "claude",
        "-p", full_prompt,
        "--model", model,
        "--output-format", "text",
        "--max-turns", "1",
    ]

    # Clean environment to avoid Claude detecting it's being called from Claude
    env = os.environ.copy()
    env.pop("CLAUDE_CODE", None)
    env.pop("CLAUDECODE", None)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,  # 3 minutes for complex proofs
            cwd=Path.home(),  # Run from home to avoid workspace issues
            env=env,
        )

        if result.returncode != 0:
            stderr = result.stderr.strip()
            if stderr:
                raise RuntimeError(f"Claude CLI error: {stderr}")
            raise RuntimeError(f"Claude CLI failed with code {result.returncode}")

        return result.stdout.strip()

    except subprocess.TimeoutExpired:
        raise RuntimeError("Claude CLI timeout after 180s")
    except FileNotFoundError:
        raise RuntimeError("Claude CLI not found - ensure 'claude' is in PATH")


def compile_lean(code: str, container: str, timeout: int) -> dict:
    """Compile Lean4 code in Docker container."""
    skill_dir = Path(__file__).parent.parent / "lean4-verify"
    run_script = skill_dir / "run.sh"

    if run_script.exists():
        # Use lean4-verify skill
        result = subprocess.run(
            [str(run_script), "--container", container, "--timeout", str(timeout)],
            input=code,
            capture_output=True,
            text=True,
            timeout=timeout + 10
        )
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"success": False, "exit_code": 1, "stdout": result.stdout, "stderr": result.stderr}
    else:
        # Direct Docker compilation
        temp_file = f"/tmp/proof_{int(time.time() * 1000)}.lean"

        # Write code to container
        subprocess.run(
            ["docker", "exec", container, "bash", "-c", f"cat > {temp_file}"],
            input=code,
            text=True,
            check=True
        )

        # Compile
        result = subprocess.run(
            ["docker", "exec", container, "bash", "-c",
             f"cd /workspace && lake env lean '{temp_file}' 2>&1"],
            capture_output=True,
            text=True,
            timeout=timeout
        )

        # Cleanup
        subprocess.run(["docker", "exec", container, "rm", "-f", temp_file],
                      capture_output=True)

        return {
            "success": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr
        }


def extract_lean_code(response: str) -> str:
    """Extract Lean4 code from Claude response."""
    # Look for ```lean or ```lean4 blocks
    import re

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


def build_system_prompt(tactics: list[str] | None, persona: str | None) -> str:
    """Build system prompt with optional tactics and persona."""
    parts = [
        "You are an expert Lean4 theorem prover. Generate valid, compilable Lean4 code.",
        "Return ONLY the Lean4 code in a ```lean4 code block. No explanations.",
        "Use Mathlib tactics and lemmas when appropriate.",
        "The code must be self-contained and compile with `lake env lean`."
    ]

    if tactics:
        parts.append(f"\nPreferred tactics: {', '.join(tactics)}")

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


def prove(
    requirement: str,
    tactics: list[str] | None = None,
    persona: str | None = None,
    max_retries: int = 3,
    candidates: int = 3,
    model: str = "opus",
    container: str = "lean_runner",
    timeout: int = 120,
) -> dict:
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

    Returns:
        dict with success, code, attempts, errors
    """
    # Check container
    result = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"],
        capture_output=True,
        text=True
    )
    if container not in result.stdout:
        return {
            "success": False,
            "error": f"Container '{container}' not running",
            "code": None,
            "attempts": 0
        }

    system_prompt = build_system_prompt(tactics, persona)
    all_errors = []
    total_attempts = 0

    # Generate candidates in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=candidates) as executor:
        futures = [
            executor.submit(generate_candidate, requirement, system_prompt, model, i)
            for i in range(candidates)
        ]

        candidate_codes = []
        for future in concurrent.futures.as_completed(futures):
            try:
                cid, code = future.result()
                candidate_codes.append((cid, code))
            except Exception as e:
                all_errors.append(f"Generation error: {e}")

    # Try each candidate with retries
    for cid, code in candidate_codes:
        for attempt in range(max_retries):
            total_attempts += 1

            try:
                result = compile_lean(code, container, timeout)
            except subprocess.TimeoutExpired:
                all_errors.append(f"Candidate {cid} attempt {attempt + 1}: timeout")
                continue
            except Exception as e:
                all_errors.append(f"Candidate {cid} attempt {attempt + 1}: {e}")
                continue

            if result.get("success"):
                return {
                    "success": True,
                    "code": code,
                    "attempts": total_attempts,
                    "candidate": cid,
                    "errors": all_errors if all_errors else None
                }

            # Failed - prepare retry with error feedback
            error_msg = result.get("stdout", "") or result.get("stderr", "")
            all_errors.append(f"Candidate {cid} attempt {attempt + 1}: {error_msg[:500]}")

            if attempt < max_retries - 1:
                # Retry with error feedback
                retry_prompt = build_retry_prompt(requirement, code, error_msg)
                try:
                    response = call_claude(retry_prompt, system_prompt, model)
                    code = extract_lean_code(response)
                except Exception as e:
                    all_errors.append(f"Retry generation error: {e}")

    return {
        "success": False,
        "code": None,
        "attempts": total_attempts,
        "errors": all_errors
    }


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Generate and verify Lean4 proofs")
    parser.add_argument("--requirement", "-r", help="Theorem to prove")
    parser.add_argument("--tactics", "-t", help="Comma-separated tactics")
    parser.add_argument("--persona", "-p", help="Persona context")
    parser.add_argument("--retries", type=int, default=3, help="Max retries per candidate")
    parser.add_argument("--candidates", "-n", type=int, default=3, help="Parallel candidates")
    parser.add_argument("--model", default="opus", help="Claude model (opus, sonnet, haiku)")
    parser.add_argument("--container", default="lean_runner", help="Docker container")
    parser.add_argument("--timeout", type=int, default=120, help="Compile timeout")

    args = parser.parse_args()

    # Get requirement from args or stdin
    if args.requirement:
        requirement = args.requirement
    else:
        # Try JSON from stdin
        stdin_data = sys.stdin.read().strip()
        if stdin_data:
            try:
                data = json.loads(stdin_data)
                requirement = data.get("requirement", stdin_data)
                # Override with JSON values if present
                if "tactics" in data and not args.tactics:
                    args.tactics = ",".join(data["tactics"]) if isinstance(data["tactics"], list) else data["tactics"]
                if "persona" in data and not args.persona:
                    args.persona = data["persona"]
            except json.JSONDecodeError:
                requirement = stdin_data
        else:
            parser.error("--requirement or stdin input required")

    tactics = args.tactics.split(",") if args.tactics else None

    result = prove(
        requirement=requirement,
        tactics=tactics,
        persona=args.persona,
        max_retries=args.retries,
        candidates=args.candidates,
        model=args.model,
        container=args.container,
        timeout=args.timeout,
    )

    print(json.dumps(result, indent=2))
    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()

