"""Tier 7: Pytest suite runner for the memory project.

Runs the full pytest test suite against live ArangoDB + memory service.
Parses JUnit XML output to report pass/fail/error/skip counts and
identify specific failing tests for auto-repair triage.

Test categories:
  - tests/health/       Infrastructure, indexes, views, analyzers, embeddings
  - tests/unit/         Pure unit tests (no DB required)
  - tests/retrieval/    Search accuracy benchmarks
  - test_memory_performance.py   Latency budgets (BM25 <100ms, hybrid <300ms)
  - test_entity_grounding.py     Entity extraction accuracy

Schedule: Nightly at 06:30 (after all other tiers complete).
"""
from __future__ import annotations

import json
import os
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from loguru import logger

import config
from probes import ProbeResult, ProbeStatus, register_probe

# Memory project test root
MEMORY_PROJECT = config.MEMORY_PROJECT_PATH
TESTS_DIR = MEMORY_PROJECT / "tests"

# JUnit output for parsing
JUNIT_XML = config.STATE_DIR / "pytest_junit.xml"
RESULTS_JSON = config.STATE_DIR / "pytest_results.json"

# Timeout for full suite (10 minutes)
PYTEST_TIMEOUT_S = 600

# Test suites to run, ordered by priority
TEST_SUITES = [
    ("health", "tests/health/"),
    ("unit", "tests/unit/"),
    ("performance", "tests/test_memory_performance.py"),
    ("entity_grounding", "tests/test_entity_grounding.py"),
    ("retrieval", "tests/retrieval/"),
]


def _parse_junit_xml(xml_path: Path) -> dict:
    """Parse JUnit XML into structured results."""
    if not xml_path.exists():
        return {"error": "junit xml not found"}

    tree = ET.parse(xml_path)
    root = tree.getroot()

    # Handle both <testsuites> and <testsuite> root
    if root.tag == "testsuites":
        suites = list(root)
    else:
        suites = [root]

    total = errors = failures = skipped = 0
    failed_tests: list[dict] = []
    error_tests: list[dict] = []

    for suite in suites:
        total += int(suite.get("tests", 0))
        errors += int(suite.get("errors", 0))
        failures += int(suite.get("failures", 0))
        skipped += int(suite.get("skipped", 0))

        for tc in suite.iter("testcase"):
            name = f"{tc.get('classname', '')}.{tc.get('name', '')}"
            time_s = float(tc.get("time", 0))

            failure = tc.find("failure")
            error = tc.find("error")

            if failure is not None:
                failed_tests.append({
                    "test": name,
                    "message": (failure.get("message", "") or "")[:200],
                    "time_s": time_s,
                })
            elif error is not None:
                error_tests.append({
                    "test": name,
                    "message": (error.get("message", "") or "")[:200],
                    "time_s": time_s,
                })

    passed = total - failures - errors - skipped
    return {
        "total": total,
        "passed": passed,
        "failed": failures,
        "errors": errors,
        "skipped": skipped,
        "pass_rate": round(passed / total * 100, 1) if total > 0 else 0.0,
        "failed_tests": failed_tests,
        "error_tests": error_tests,
    }


def _run_pytest(suite_paths: list[str], timeout: int = PYTEST_TIMEOUT_S) -> tuple[int, str]:
    """Run pytest with JUnit XML output. Returns (exit_code, stderr)."""
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)

    cmd = [
        "uv", "run", "python", "-m", "pytest",
        f"--junit-xml={JUNIT_XML}",
        "--tb=short",
        "-q",
        "--no-header",
    ]
    cmd.extend(suite_paths)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(MEMORY_PROJECT),
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        return result.returncode, result.stderr
    except subprocess.TimeoutExpired:
        return -1, f"pytest timed out after {timeout}s"
    except Exception as e:
        return -2, str(e)


def _save_results(results: dict) -> None:
    """Save structured results for dashboard consumption."""
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    results["timestamp"] = datetime.now().isoformat()
    tmp = RESULTS_JSON.with_suffix(".tmp")
    tmp.write_text(json.dumps(results, indent=2))
    os.replace(tmp, RESULTS_JSON)


# ---------------------------------------------------------------------------
# P30: Full pytest suite
# ---------------------------------------------------------------------------

@register_probe("P30", "pytest-full", tier=7, auto_fixable=False)
def probe_pytest_full(autofix: bool = False) -> ProbeResult:
    """Run the full memory project pytest suite and report results."""
    if not TESTS_DIR.exists():
        return ProbeResult(
            probe_id="P30",
            name="pytest-full",
            tier=7,
            status=ProbeStatus.SKIP,
            message=f"Tests directory not found: {TESTS_DIR}",
            details={"tests_dir": str(TESTS_DIR)},
        )

    # Collect paths for all suites that exist
    paths = []
    for label, rel_path in TEST_SUITES:
        full = MEMORY_PROJECT / rel_path
        if full.exists():
            paths.append(rel_path)
        else:
            logger.warning("Test suite '{}' not found at {}", label, full)

    if not paths:
        return ProbeResult(
            probe_id="P30",
            name="pytest-full",
            tier=7,
            status=ProbeStatus.SKIP,
            message="No test suites found",
            details={"searched": [s[1] for s in TEST_SUITES]},
        )

    logger.info("Running pytest on {} suite(s): {}", len(paths), paths)
    exit_code, stderr = _run_pytest(paths)

    if exit_code == -1:
        return ProbeResult(
            probe_id="P30",
            name="pytest-full",
            tier=7,
            status=ProbeStatus.FAIL,
            message=f"Pytest timed out after {PYTEST_TIMEOUT_S}s",
            details={"timeout_s": PYTEST_TIMEOUT_S},
        )

    if exit_code == -2:
        return ProbeResult(
            probe_id="P30",
            name="pytest-full",
            tier=7,
            status=ProbeStatus.FAIL,
            message=f"Pytest execution error: {stderr[:200]}",
            details={"error": stderr[:500]},
        )

    results = _parse_junit_xml(JUNIT_XML)
    _save_results(results)

    total = results.get("total", 0)
    passed = results.get("passed", 0)
    failed = results.get("failed", 0)
    errors = results.get("errors", 0)
    skipped = results.get("skipped", 0)
    pass_rate = results.get("pass_rate", 0.0)

    # Determine status
    if failed + errors == 0:
        status = ProbeStatus.PASS
        msg = f"{passed}/{total} tests passed ({skipped} skipped)"
    elif pass_rate >= 95.0:
        status = ProbeStatus.WARN
        msg = f"{passed}/{total} passed, {failed} failed, {errors} errors ({pass_rate}%)"
    else:
        status = ProbeStatus.FAIL
        msg = f"{passed}/{total} passed, {failed} failed, {errors} errors ({pass_rate}%)"

    details = {
        "total": total,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
        "pass_rate": pass_rate,
        "failed_tests": results.get("failed_tests", [])[:10],
        "error_tests": results.get("error_tests", [])[:10],
        "junit_xml": str(JUNIT_XML),
        "results_json": str(RESULTS_JSON),
    }

    return ProbeResult(
        probe_id="P30",
        name="pytest-full",
        tier=7,
        status=status,
        message=msg,
        details=details,
    )


# ---------------------------------------------------------------------------
# P31: Health tests only (fast, infrastructure validation)
# ---------------------------------------------------------------------------

@register_probe("P31", "pytest-health", tier=7, auto_fixable=False)
def probe_pytest_health(autofix: bool = False) -> ProbeResult:
    """Run only tests/health/ — ArangoDB infra, indexes, views, analyzers."""
    health_dir = MEMORY_PROJECT / "tests" / "health"
    if not health_dir.exists():
        return ProbeResult(
            probe_id="P31",
            name="pytest-health",
            tier=7,
            status=ProbeStatus.SKIP,
            message="tests/health/ not found",
        )

    exit_code, stderr = _run_pytest(["tests/health/"], timeout=120)

    if exit_code < 0:
        return ProbeResult(
            probe_id="P31",
            name="pytest-health",
            tier=7,
            status=ProbeStatus.FAIL,
            message=f"Health tests failed to run: {stderr[:200]}",
            details={"error": stderr[:500]},
        )

    results = _parse_junit_xml(JUNIT_XML)
    total = results.get("total", 0)
    passed = results.get("passed", 0)
    failed = results.get("failed", 0)
    errors = results.get("errors", 0)

    if failed + errors == 0:
        status = ProbeStatus.PASS
        msg = f"Health: {passed}/{total} passed"
    else:
        status = ProbeStatus.FAIL
        msg = f"Health: {failed} failed, {errors} errors out of {total}"

    return ProbeResult(
        probe_id="P31",
        name="pytest-health",
        tier=7,
        status=status,
        message=msg,
        details={
            "total": total,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "failed_tests": results.get("failed_tests", [])[:10],
            "error_tests": results.get("error_tests", [])[:10],
        },
    )


# ---------------------------------------------------------------------------
# P32: Performance budget tests
# ---------------------------------------------------------------------------

@register_probe("P32", "pytest-performance", tier=7, auto_fixable=False)
def probe_pytest_performance(autofix: bool = False) -> ProbeResult:
    """Run performance benchmarks — latency budgets for BM25, hybrid, traversal."""
    perf_file = MEMORY_PROJECT / "tests" / "test_memory_performance.py"
    if not perf_file.exists():
        return ProbeResult(
            probe_id="P32",
            name="pytest-performance",
            tier=7,
            status=ProbeStatus.SKIP,
            message="test_memory_performance.py not found",
        )

    exit_code, stderr = _run_pytest(
        ["tests/test_memory_performance.py", "-m", "performance"],
        timeout=180,
    )

    if exit_code < 0:
        return ProbeResult(
            probe_id="P32",
            name="pytest-performance",
            tier=7,
            status=ProbeStatus.FAIL,
            message=f"Performance tests failed to run: {stderr[:200]}",
            details={"error": stderr[:500]},
        )

    results = _parse_junit_xml(JUNIT_XML)
    total = results.get("total", 0)
    passed = results.get("passed", 0)
    failed = results.get("failed", 0)

    if failed == 0:
        status = ProbeStatus.PASS
        msg = f"Performance: {passed}/{total} within budget"
    else:
        status = ProbeStatus.WARN
        msg = f"Performance: {failed}/{total} exceeded latency budget"

    return ProbeResult(
        probe_id="P32",
        name="pytest-performance",
        tier=7,
        status=status,
        message=msg,
        details={
            "total": total,
            "passed": passed,
            "failed": failed,
            "failed_tests": results.get("failed_tests", [])[:10],
        },
    )
