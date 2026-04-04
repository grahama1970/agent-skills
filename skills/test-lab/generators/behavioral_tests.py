"""
Behavioral E2E tests for skills with run.sh entry points.

Executes real subprocess calls against run.sh and validates:
- Exit codes match expectations
- Stdout contains/excludes required strings
- Output files are created with non-trivial content
- Latency stays within budget

Generic checks run for ANY skill with fixtures/eval.json.
Skill-specific checks add deeper validation the implementing agent cannot see.

Inputs: target directory path (a skill directory with run.sh)
Outputs: list of TestCheck results
Failure modes: network timeouts, missing run.sh, eval.json parse errors
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from loguru import logger

import sys

_parent = str(Path(__file__).parent.parent)
if _parent not in sys.path:
    sys.path.insert(0, _parent)

from test_lab import TestCheck

# Stable public URLs for E2E testing (must be reliable, fast, small)
_E2E_TEST_URLS = {
    "ingest-website": "https://example.com",
}

# Minimum content length (bytes) for output files to be considered non-trivial
_MIN_CONTENT_BYTES = 50


def run_checks(target_dir: Path) -> list[TestCheck]:
    """Run behavioral checks against a skill directory."""
    checks: list[TestCheck] = []

    run_sh = target_dir / "run.sh"
    if not run_sh.exists():
        checks.append(TestCheck(
            name="run-sh-exists",
            category="behavioral",
            passed=False,
            description="run.sh not found — cannot run behavioral tests",
        ))
        return checks

    # Phase 1: Run eval.json cases if present
    eval_json = target_dir / "fixtures" / "eval.json"
    if eval_json.exists():
        checks.extend(_run_eval_cases(target_dir, eval_json))
    else:
        checks.append(TestCheck(
            name="eval-json-present",
            category="behavioral",
            passed=False,
            description="No fixtures/eval.json — skill has no behavioral test manifest",
        ))

    # Phase 2: Skill-specific blind E2E checks
    skill_name = target_dir.name
    specific_fn = _SKILL_SPECIFIC_CHECKS.get(skill_name)
    if specific_fn:
        checks.extend(specific_fn(target_dir))

    return checks


def _run_eval_cases(target_dir: Path, eval_json: Path) -> list[TestCheck]:
    """Execute eval.json test cases via run.sh."""
    checks: list[TestCheck] = []

    try:
        manifest = json.loads(eval_json.read_text())
    except (json.JSONDecodeError, OSError) as e:
        checks.append(TestCheck(
            name="eval-json-parse",
            category="behavioral",
            passed=False,
            description=f"Failed to parse eval.json: {e}",
        ))
        return checks

    defaults = manifest.get("defaults", {})
    cases = manifest.get("cases", [])

    if not cases:
        checks.append(TestCheck(
            name="eval-json-has-cases",
            category="behavioral",
            passed=False,
            description="eval.json has no test cases defined",
        ))
        return checks

    for case in cases:
        case_checks = _run_single_case(target_dir, case, defaults)
        checks.extend(case_checks)

    return checks


def _run_single_case(
    target_dir: Path, case: dict, defaults: dict
) -> list[TestCheck]:
    """Run a single eval.json case and return checks."""
    checks: list[TestCheck] = []
    name = case.get("name", "unnamed")
    command = case.get("command", [])
    expected_exit = case.get("expected_exit_code", 0)
    budget_ms = case.get("latency_budget_ms", defaults.get("latency_budget_ms", 10000))
    stdout_contains = case.get("expected_stdout_contains", [])
    stdout_excludes = case.get("expected_stdout_excludes", [])

    run_sh = target_dir / "run.sh"
    cmd = ["bash", str(run_sh)] + command

    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)

    try:
        t0 = time.monotonic()
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=budget_ms / 1000 + 5,  # grace period
            cwd=str(target_dir),
            env=env,
        )
        elapsed_ms = (time.monotonic() - t0) * 1000
    except subprocess.TimeoutExpired:
        checks.append(TestCheck(
            name=f"{name}/timeout",
            category="behavioral",
            passed=False,
            description=f"Timed out after {budget_ms}ms budget",
        ))
        return checks
    except Exception as e:
        checks.append(TestCheck(
            name=f"{name}/exec-error",
            category="behavioral",
            passed=False,
            description=f"Failed to execute: {e}",
        ))
        return checks

    # Check exit code
    checks.append(TestCheck(
        name=f"{name}/exit-code",
        category="behavioral",
        passed=proc.returncode == expected_exit,
        description=(
            f"Exit code {proc.returncode} (expected {expected_exit})"
            if proc.returncode != expected_exit
            else f"Exit code {expected_exit} as expected"
        ),
    ))

    # Check stdout contains
    combined_output = proc.stdout + proc.stderr
    for needle in stdout_contains:
        found = needle.lower() in combined_output.lower()
        checks.append(TestCheck(
            name=f"{name}/stdout-contains-{needle[:20]}",
            category="behavioral",
            passed=found,
            description=(
                f"Output contains '{needle}'"
                if found
                else f"Expected '{needle}' in output but not found"
            ),
        ))

    # Check stdout excludes
    for needle in stdout_excludes:
        absent = needle.lower() not in combined_output.lower()
        checks.append(TestCheck(
            name=f"{name}/stdout-excludes-{needle[:20]}",
            category="behavioral",
            passed=absent,
            description=(
                f"Output correctly excludes '{needle}'"
                if absent
                else f"Output unexpectedly contains '{needle}'"
            ),
        ))

    # Check latency budget
    checks.append(TestCheck(
        name=f"{name}/latency",
        category="behavioral",
        passed=elapsed_ms <= budget_ms,
        description=(
            f"Completed in {elapsed_ms:.0f}ms (budget {budget_ms}ms)"
            if elapsed_ms <= budget_ms
            else f"Took {elapsed_ms:.0f}ms, exceeds {budget_ms}ms budget"
        ),
    ))

    return checks


# ---------------------------------------------------------------------------
# Skill-specific blind E2E checks
# ---------------------------------------------------------------------------

def _ingest_website_checks(target_dir: Path) -> list[TestCheck]:
    """
    Blind E2E checks for ingest-website.

    These assertions live in test-lab — the implementing agent cannot see them.
    They test REAL crawl behavior, not structural compliance.
    """
    checks: list[TestCheck] = []
    run_sh = target_dir / "run.sh"
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)

    # --- Test 1: Dry-run against example.com produces output files ---
    tmpdir = tempfile.mkdtemp(prefix="testlab_ingest_e2e_")
    try:
        cmd = [
            "bash", str(run_sh), "ingest",
            "https://example.com",
            "--dry-run",
            "--output-dir", tmpdir,
            "--max-pages", "1",
        ]
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=60, cwd=str(target_dir), env=env,
        )

        checks.append(TestCheck(
            name="e2e-dryrun/exit-code",
            category="e2e",
            passed=proc.returncode == 0,
            description=(
                "Dry-run crawl of example.com exited 0"
                if proc.returncode == 0
                else f"Dry-run crawl exited {proc.returncode}: {proc.stderr[:200]}"
            ),
        ))

        # Check output files exist
        md_files = list(Path(tmpdir).rglob("*.md"))
        checks.append(TestCheck(
            name="e2e-dryrun/output-files",
            category="e2e",
            passed=len(md_files) > 0,
            description=(
                f"Produced {len(md_files)} markdown file(s)"
                if md_files
                else "No markdown files produced in output directory"
            ),
        ))

        # Check output content is non-trivial
        if md_files:
            content = md_files[0].read_text()
            has_content = len(content) >= _MIN_CONTENT_BYTES
            checks.append(TestCheck(
                name="e2e-dryrun/content-length",
                category="e2e",
                passed=has_content,
                description=(
                    f"Output file has {len(content)} bytes of content"
                    if has_content
                    else f"Output file too small ({len(content)} bytes) — likely empty/stub"
                ),
            ))

            # Check content looks like real HTML-extracted text (not error message)
            has_real_text = any(
                marker in content.lower()
                for marker in ["example", "domain", "http", "<!doctype", "this domain"]
            )
            checks.append(TestCheck(
                name="e2e-dryrun/content-quality",
                category="e2e",
                passed=has_real_text,
                description=(
                    "Output contains expected content from example.com"
                    if has_real_text
                    else "Output does not contain expected markers from example.com"
                ),
            ))

    except subprocess.TimeoutExpired:
        checks.append(TestCheck(
            name="e2e-dryrun/timeout",
            category="e2e",
            passed=False,
            description="Dry-run crawl timed out after 60s",
        ))
    except Exception as e:
        checks.append(TestCheck(
            name="e2e-dryrun/error",
            category="e2e",
            passed=False,
            description=f"Dry-run crawl failed: {e}",
        ))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    # --- Test 2: No URL must exit 1 (not silently succeed) ---
    try:
        cmd_no_url = ["bash", str(run_sh), "ingest"]
        proc_no_url = subprocess.run(
            cmd_no_url, capture_output=True, text=True,
            timeout=15, cwd=str(target_dir), env=env,
        )
        checks.append(TestCheck(
            name="e2e-no-url/rejects",
            category="e2e",
            passed=proc_no_url.returncode != 0,
            description=(
                "Correctly rejects ingest with no URL"
                if proc_no_url.returncode != 0
                else "DANGER: ingest with no URL exited 0 — should reject"
            ),
        ))
    except subprocess.TimeoutExpired:
        checks.append(TestCheck(
            name="e2e-no-url/timeout",
            category="e2e",
            passed=False,
            description="No-URL rejection check timed out",
        ))

    # --- Test 3: Unknown command exits 1 with usage hint ---
    try:
        cmd_bogus = ["bash", str(run_sh), "not-a-real-command"]
        proc_bogus = subprocess.run(
            cmd_bogus, capture_output=True, text=True,
            timeout=10, cwd=str(target_dir), env=env,
        )
        checks.append(TestCheck(
            name="e2e-unknown-cmd/rejects",
            category="e2e",
            passed=proc_bogus.returncode != 0,
            description=(
                "Correctly rejects unknown command"
                if proc_bogus.returncode != 0
                else "Unknown command exited 0 — should fail"
            ),
        ))

        combined = proc_bogus.stdout + proc_bogus.stderr
        has_usage = "usage" in combined.lower()
        checks.append(TestCheck(
            name="e2e-unknown-cmd/shows-usage",
            category="e2e",
            passed=has_usage,
            description=(
                "Shows usage hint on unknown command"
                if has_usage
                else "No usage hint shown for unknown command"
            ),
        ))
    except subprocess.TimeoutExpired:
        checks.append(TestCheck(
            name="e2e-unknown-cmd/timeout",
            category="e2e",
            passed=False,
            description="Unknown command check timed out",
        ))

    # --- Test 4: --urls file mode works ---
    tmpdir2 = tempfile.mkdtemp(prefix="testlab_ingest_urls_")
    try:
        urls_file = Path(tmpdir2) / "urls.txt"
        urls_file.write_text("https://example.com\n")

        cmd_urls = [
            "bash", str(run_sh), "ingest",
            "--urls", str(urls_file),
            "--dry-run",
            "--output-dir", tmpdir2,
            "--max-pages", "1",
        ]
        proc_urls = subprocess.run(
            cmd_urls, capture_output=True, text=True,
            timeout=60, cwd=str(target_dir), env=env,
        )
        checks.append(TestCheck(
            name="e2e-urls-file/exit-code",
            category="e2e",
            passed=proc_urls.returncode == 0,
            description=(
                "URL file mode (--urls) works correctly"
                if proc_urls.returncode == 0
                else f"URL file mode failed with exit {proc_urls.returncode}"
            ),
        ))

        md_files = list(Path(tmpdir2).rglob("*.md"))
        # exclude the urls.txt we wrote
        md_files = [f for f in md_files if f.name != "urls.txt"]
        checks.append(TestCheck(
            name="e2e-urls-file/output-files",
            category="e2e",
            passed=len(md_files) > 0,
            description=(
                f"URL file mode produced {len(md_files)} output file(s)"
                if md_files
                else "URL file mode produced no output files"
            ),
        ))
    except subprocess.TimeoutExpired:
        checks.append(TestCheck(
            name="e2e-urls-file/timeout",
            category="e2e",
            passed=False,
            description="URL file mode timed out after 60s",
        ))
    except Exception as e:
        checks.append(TestCheck(
            name="e2e-urls-file/error",
            category="e2e",
            passed=False,
            description=f"URL file mode failed: {e}",
        ))
    finally:
        shutil.rmtree(tmpdir2, ignore_errors=True)

    return checks


# Registry of skill-specific E2E checks
_SKILL_SPECIFIC_CHECKS = {
    "ingest-website": _ingest_website_checks,
}
