#!/usr/bin/env python3
"""Systematic UI interaction testing with DOM assertions and PASS/FAIL verdicts.

Uses CDP directly — single persistent WebSocket, no subprocess overhead.
Playwright-inspired assertions with auto-retry for SPA testing.

Manifest interactions support:
  Actions: screenshot | click | type | wait | scroll
  Assertions: assert_selector | assert_visible | assert_text | assert_absent |
    assert_count | assert_attribute | assert_css | assert_value | assert_url |
    assert_enabled | assert_disabled | assert_aria
  All assertions support _not suffix for negation and auto-retry with timeout.
"""

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

from cdp_client import CDPClient
from assertions import run_assertions

app = typer.Typer(help="Systematic UI interaction testing with verification.")


# --- Results tracking ---

@dataclass
class InteractionResult:
    surface: str
    element: str
    action: str
    description: str
    status: str = "SKIP"
    evidence: str = ""
    screenshot: str = ""
    duration_ms: int = 0
    assertions: list = field(default_factory=list)


@dataclass
class TestResults:
    app: str = ""
    total: int = 0
    passed: int = 0
    failed: int = 0
    warned: int = 0
    skipped: int = 0
    interactions: list = field(default_factory=list)

    def add(self, r: InteractionResult):
        self.interactions.append(r)
        self.total += 1
        if r.status == "PASS":
            self.passed += 1
        elif r.status == "FAIL":
            self.failed += 1
        elif r.status == "WARN":
            self.warned += 1
        else:
            self.skipped += 1


# --- Interaction executor ---

def _execute_interaction(
    cdp: CDPClient,
    interaction: dict,
    element_name: str,
    surface_name: str,
    output_dir: Path,
) -> InteractionResult:
    action = interaction.get("action", "screenshot")
    description = interaction.get("description", f"{action} on {element_name}")
    safe_name = f"{element_name}_{action}".replace(" ", "_").replace("/", "_")
    wait_ms = interaction.get("wait_ms", 300)
    t0 = time.time()

    result = InteractionResult(
        surface=surface_name, element=element_name,
        action=action, description=description,
    )

    try:
        if action == "screenshot":
            path = str(output_dir / f"{safe_name}.png")
            cdp.screenshot(path)
            result.screenshot = path
            result.status = "PASS"
            result.evidence = f"captured {path}"

        elif action == "click":
            target = interaction.get("target", "")
            if not target:
                result.status = "FAIL"
                result.evidence = "no target selector specified"
            else:
                click_result = cdp.click_selector(target)
                if click_result.get("ok"):
                    result.status = "PASS"
                    tag = click_result.get("tag", "?")
                    text = click_result.get("text", "")[:60]
                    result.evidence = f"clicked <{tag}> {text!r}"
                else:
                    result.status = "FAIL"
                    result.evidence = click_result.get("error", "click failed")

        elif action == "type":
            target = interaction.get("target", "")
            value = interaction.get("value", interaction.get("text", ""))
            if not target:
                result.status = "FAIL"
                result.evidence = "no target selector specified"
            else:
                type_result = cdp.type_into(target, value)
                if type_result.get("ok"):
                    result.status = "PASS"
                    result.evidence = f"typed {value!r}, value={type_result.get('value', '?')!r}"
                else:
                    result.status = "FAIL"
                    result.evidence = type_result.get("error", "type failed")

        elif action == "wait":
            wait_sel = interaction.get("target") or interaction.get("wait_for", "body")
            timeout = interaction.get("timeout_ms", 5000)
            found = cdp.wait_for_selector(wait_sel, timeout)
            result.status = "PASS" if found else "FAIL"
            result.evidence = f"{'found' if found else 'NOT found'} {wait_sel} within {timeout}ms"

        elif action == "scroll":
            direction = interaction.get("direction", "down")
            amount = interaction.get("amount", 500)
            cdp.evaluate(
                f"window.scrollBy(0, {amount if direction == 'down' else -amount})"
            )
            result.status = "PASS"
            result.evidence = f"scrolled {direction} {amount}px"

        else:
            result.status = "WARN"
            result.evidence = f"unknown action: {action}"

        # Run assertions (skip if action already failed)
        if result.status != "FAIL":
            assertions = run_assertions(cdp, interaction, wait_ms)
            result.assertions = assertions
            for a in assertions:
                if a["status"] == "FAIL":
                    result.status = "FAIL"
                    result.evidence += f" | ASSERTION FAILED: {a['check']} — {a['evidence']}"
                    break

        # Screenshot after action
        if action != "screenshot" and interaction.get("screenshot_after", False):
            time.sleep(wait_ms / 1000.0)
            path = str(output_dir / f"{safe_name}.png")
            cdp.screenshot(path)
            result.screenshot = path

        # Burst capture for animations
        if interaction.get("burst"):
            frames = interaction.get("burst_frames", 10)
            interval = interaction.get("burst_interval_ms", 100)
            burst_dir = output_dir / "burst"
            burst_dir.mkdir(parents=True, exist_ok=True)
            for i in range(1, frames + 1):
                cdp.screenshot(str(burst_dir / f"BURST_{safe_name}_f{i:02d}.png"))
                if i < frames:
                    time.sleep(interval / 1000.0)

    except Exception as e:
        result.status = "FAIL"
        result.evidence = f"exception: {e}"

    result.duration_ms = int((time.time() - t0) * 1000)

    icon = {"PASS": "\u2713", "FAIL": "\u2717", "WARN": "!", "SKIP": "-"}.get(result.status, "?")
    logger.info("  [{}] {} — {} | {}", icon, result.status, description, result.evidence)
    for a in result.assertions:
        a_icon = "\u2713" if a["status"] == "PASS" else "\u2717"
        logger.info("      [{}] {} — {}", a_icon, a["check"], a["evidence"])

    return result


# --- Commands ---

def _load_manifest(manifest_path: Path) -> dict:
    if not manifest_path.exists():
        logger.error("Manifest not found: {}", manifest_path)
        raise typer.Exit(1)
    data = json.loads(manifest_path.read_text())
    if "surfaces" not in data:
        logger.error("Manifest missing 'surfaces' key")
        raise typer.Exit(1)
    return data


def _run_surface(cdp: CDPClient, surface: dict, base_url: str, output_dir: Path, results: TestResults):
    """Run all interactions for a single surface."""
    surface_name = surface.get("name", "unnamed")
    path = surface.get("path", "/")
    surface_dir = output_dir / surface_name
    surface_dir.mkdir(parents=True, exist_ok=True)

    nav_url = f"{base_url.rstrip('/')}{path}" if base_url else path
    logger.info("Surface: {} ({})", surface_name, nav_url)

    cdp.navigate(nav_url, wait_ms=2000)

    wait_ready = surface.get("wait_ready")
    if wait_ready:
        timeout = surface.get("wait_ready_timeout_ms", 15000)
        found = cdp.wait_for_selector(wait_ready, timeout_ms=timeout)
        if not found:
            logger.warning("wait_ready {} not found within {}ms", wait_ready, timeout)

    for element in surface.get("elements", []):
        element_name = element.get("name", "unnamed")
        for interaction in element.get("interactions", []):
            r = _execute_interaction(cdp, interaction, element_name, surface_name, surface_dir)
            results.add(r)


@app.command()
def run(
    manifest: Path = typer.Option(..., help="Path to interaction manifest JSON"),
    output_dir: Path = typer.Option(Path("./captures"), help="Output directory for screenshots"),
    surface: Optional[str] = typer.Option(None, help="Run only this surface (by name)"),
    max_retries: int = typer.Option(1, help="Max attempts per surface on failure"),
):
    """Execute an interaction manifest with verification. Returns PASS/FAIL per interaction."""
    data = _load_manifest(manifest)
    output_dir.mkdir(parents=True, exist_ok=True)

    base_url = data.get("base_url", "")
    surfaces = data["surfaces"]
    if surface:
        surfaces = [s for s in surfaces if s.get("name") == surface]
        if not surfaces:
            logger.error("Surface '{}' not found in manifest", surface)
            raise typer.Exit(1)

    total_interactions = sum(
        len(el.get("interactions", []))
        for s in surfaces
        for el in s.get("elements", [])
    )

    results = TestResults(app=data.get("app", "unknown"))
    cdp = CDPClient()
    cdp.connect()

    logger.info("Running {} interactions across {} surfaces", total_interactions, len(surfaces))

    try:
        for s in surfaces:
            for attempt in range(1, max_retries + 1):
                attempt_results = TestResults(app=data.get("app", "unknown"))
                _run_surface(cdp, s, base_url, output_dir, attempt_results)
                if attempt_results.failed == 0 or attempt >= max_retries:
                    for r in attempt_results.interactions:
                        results.add(r)
                    break
                logger.warning("Surface '{}' had {} failures, retrying ({}/{})",
                              s.get("name"), attempt_results.failed, attempt + 1, max_retries)
                cdp.reconnect()
    finally:
        cdp.close()

    logger.info("")
    logger.info("=" * 60)
    logger.info("RESULTS: {} PASS / {} FAIL / {} WARN / {} total",
                results.passed, results.failed, results.warned, results.total)
    logger.info("=" * 60)

    if results.failed > 0:
        logger.info("")
        logger.info("FAILURES:")
        for r in results.interactions:
            if r.status == "FAIL":
                logger.info("  {} > {} > {} — {}", r.surface, r.element, r.action, r.evidence)

    results_path = output_dir / "results.json"
    results_path.write_text(json.dumps(asdict(results), indent=2, default=str))
    logger.info("Results written to {}", results_path)

    if results.failed > 0:
        raise typer.Exit(1)


@app.command()
def generate(
    url: str = typer.Option(..., help="Target URL to analyze"),
    output: Path = typer.Option(Path("manifest.json"), help="Output manifest path"),
):
    """Generate an interaction manifest from a URL."""
    cdp = CDPClient()
    cdp.connect()
    try:
        cdp.navigate(url)
        title = cdp.evaluate("document.title") or url
        manifest = {
            "version": 1, "app": title, "base_url": url,
            "surfaces": [{
                "name": "main", "path": "/",
                "elements": [{"name": "full-page", "selector": "body",
                    "interactions": [{"action": "screenshot", "description": f"Full page of {url}"}]}],
            }],
        }
    finally:
        cdp.close()
    output.write_text(json.dumps(manifest, indent=2))
    logger.info("Manifest written to {}", output)


def _find_review_design() -> Optional[Path]:
    """Locate the /review-design skill run.sh."""
    candidates = [
        Path.home() / ".claude" / "skills" / "review-design" / "run.sh",
        Path.home() / ".pi" / "skills" / "review-design" / "run.sh",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def _run_review_design(
    captures: Path, context: str = "", provider: str = "gemini", persona: str = "",
) -> Optional[str]:
    """Call /review-design on captured screenshots. Returns review text or None.

    Args:
        captures: Directory containing captured screenshots.
        context: Optional context string for the review.
        provider: Vision LLM provider.
        persona: REQUIRED persona agent name (e.g. brandon-bailey, rob-armstrong).
                 Without a persona, the review is generic and useless.
    """
    import subprocess

    if not persona:
        logger.error("No persona specified for /review-design — a review without a persona is a failure")
        return None

    run_sh = _find_review_design()
    if not run_sh:
        logger.warning("review-design skill not found, skipping visual review")
        return None

    # Collect all PNGs across surface subdirectories
    screenshots = sorted(captures.rglob("*.png"))
    if not screenshots:
        logger.warning("No screenshots found in {}", captures)
        return None

    cmd = [str(run_sh), "review", "--screenshots", str(captures),
           "--provider", provider, "--persona", persona]
    if context:
        cmd.extend(["--context", context])

    logger.info("Running /review-design on {} screenshots...", len(screenshots))
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
            env={**__import__("os").environ, "REVIEW_DESIGN_ROUNDS": "1"},
        )
        if result.returncode == 0:
            # Check for output files
            review_dir = captures / "review_output"
            if review_dir.exists():
                finals = sorted(review_dir.glob("*_final.md"))
                if finals:
                    return finals[-1].read_text()
            # Fallback: return stdout if it has content
            if result.stdout.strip():
                return result.stdout.strip()
        else:
            logger.warning("review-design exited {}: {}", result.returncode, result.stderr[:200] if result.stderr else "no stderr")
    except subprocess.TimeoutExpired:
        logger.warning("review-design timed out after 120s")
    except Exception as e:
        logger.warning("review-design failed: {}", e)
    return None


@app.command()
def review(
    captures: Path = typer.Option(..., help="Directory containing captured screenshots"),
    output: Path = typer.Option(Path("./INTERACTION_REPORT.md"), help="Output report path"),
    skip_visual: bool = typer.Option(False, help="Skip /review-design visual AI review"),
    context: str = typer.Option("", help="Context string for /review-design"),
    provider: str = typer.Option("gemini", help="Vision AI provider for /review-design"),
    persona: str = typer.Option("", "--persona", help="Persona agent for /review-design (e.g. brandon-bailey, rob-armstrong). REQUIRED for visual review."),
):
    """Generate report from results.json + /review-design visual audit.

    --persona is required for visual review. Without it, the /review-design
    call is skipped — generic reviews are useless.
    """
    if not captures.exists():
        logger.error("Captures directory not found: {}", captures)
        raise typer.Exit(1)

    results_file = captures / "results.json"
    if not results_file.exists():
        logger.warning("No results.json in {}. Run `test-interactions run` first.", captures)
        return

    data = json.loads(results_file.read_text())
    lines = [
        f"# Interaction Test Report: {data.get('app', 'Unknown')}",
        f"**Date**: {time.strftime('%Y-%m-%d %H:%M')}",
        f"**Results**: {data['passed']} PASS / {data['failed']} FAIL / {data['warned']} WARN / {data['total']} total",
        "", "## DOM Assertion Results", "",
        "| Surface | Element | Action | Status | Evidence |",
        "|---------|---------|--------|--------|----------|",
    ]
    for r in data.get("interactions", []):
        status = {"PASS": "PASS", "FAIL": "**FAIL**", "WARN": "WARN"}.get(r["status"], r["status"])
        evidence = r.get("evidence", "")[:100].replace("|", "/")
        lines.append(f"| {r['surface']} | {r['element']} | {r['action']} | {status} | {evidence} |")
        for a in r.get("assertions", []):
            a_st = {"PASS": "PASS", "FAIL": "**FAIL**"}.get(a["status"], a["status"])
            lines.append(f"| | | assertion | {a_st} | {a['check']}: {a['evidence'][:80]} |")

    if data["failed"] > 0:
        lines.extend(["", "## Failures", ""])
        for r in data.get("interactions", []):
            if r["status"] == "FAIL":
                lines.append(f"### {r['surface']} > {r['element']} > {r['action']}")
                lines.append(f"- **Description**: {r['description']}")
                lines.append(f"- **Evidence**: {r['evidence']}")
                if r.get("screenshot"):
                    lines.append(f"- **Screenshot**: {r['screenshot']}")
                lines.append("")

    # Run /review-design visual audit (persona required — generic reviews are useless)
    if not skip_visual and not persona:
        logger.warning("No --persona specified — skipping /review-design (generic reviews are useless)")
        skip_visual = True

    if not skip_visual:
        visual_review = _run_review_design(captures, context, provider, persona)
        if visual_review:
            lines.extend(["", "## Visual Design Review", ""])
            lines.append("*Generated by /review-design — AI vision audit of captured screenshots.*")
            lines.append("")
            lines.append(visual_review)
        else:
            lines.extend(["", "## Visual Design Review", ""])
            lines.append("*Skipped — /review-design not available or returned no output.*")

    output.write_text("\n".join(lines))
    logger.info("Report written to {}", output)


@app.command()
def full(
    url: str = typer.Option(..., help="Target URL to test"),
    output_dir: Path = typer.Option(Path("./captures"), help="Output directory"),
    manifest: Optional[Path] = typer.Option(None, help="Existing manifest (skip generate)"),
    skip_visual: bool = typer.Option(False, help="Skip /review-design visual AI review"),
    context: str = typer.Option("", help="Context string for /review-design"),
    provider: str = typer.Option("gemini", help="Vision AI provider for /review-design"),
    persona: str = typer.Option("", "--persona", help="Persona agent for /review-design (e.g. brandon-bailey). REQUIRED for visual review."),
    surface: Optional[str] = typer.Option(None, help="Run only this surface (by name)"),
    max_retries: int = typer.Option(1, help="Max attempts per surface on failure"),
):
    """Full pipeline: generate manifest -> run interactions -> review + visual audit."""
    manifest_path = manifest or (output_dir / "manifest.json")
    output_dir.mkdir(parents=True, exist_ok=True)

    if not manifest:
        logger.info("Step 1/3: Generating manifest")
        generate(url=url, output=manifest_path)
    else:
        logger.info("Step 1/3: Using existing manifest {}", manifest_path)

    logger.info("Step 2/3: Running interactions")
    try:
        run(manifest=manifest_path, output_dir=output_dir, surface=surface, max_retries=max_retries)
    except SystemExit:
        pass

    logger.info("Step 3/3: Reviewing captures{}",
                " (with /review-design)" if not skip_visual else "")
    report_path = output_dir / "INTERACTION_REPORT.md"
    review(captures=output_dir, output=report_path,
           skip_visual=skip_visual, context=context, provider=provider, persona=persona)
    logger.info("Done. Report: {}", report_path)


@app.command("run-server")
def run_server(
    server_url: str = typer.Option("http://localhost:3001", help="UX Lab server URL"),
    group: Optional[str] = typer.Option(None, help="Run only this test group"),
    test_id: Optional[str] = typer.Option(None, "--test", help="Run only this test ID"),
    timeout: int = typer.Option(180, help="Max wait seconds for run to complete"),
):
    """Run tests via the UX Lab Express test runner API (Puppeteer CDP backend)."""
    import httpx

    # Build request
    body: dict = {}
    if group:
        body["group"] = group
    if test_id:
        body["tests"] = [test_id]

    # Start run
    logger.info("Starting test run on {} ...", server_url)
    resp = httpx.post(f"{server_url}/api/test-runner/run", json=body, timeout=10.0)
    resp.raise_for_status()
    run_data = resp.json()
    run_id = run_data["runId"]
    total = run_data["totalTests"]
    logger.info("Run {} started: {} tests", run_id, total)

    # Poll for completion
    import time as _time
    start = _time.time()
    results = None
    while _time.time() - start < timeout:
        _time.sleep(3)
        r = httpx.get(f"{server_url}/api/test-runner/results/{run_id}", timeout=10.0)
        if r.status_code != 200:
            continue
        data = r.json()
        status = data.get("status")
        if status and status != "RUNNING":
            results = data
            break

    if not results:
        logger.error("Test run timed out after {}s", timeout)
        raise typer.Exit(1)

    # Print results
    summary = results.get("summary", {})
    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    total_ran = summary.get("total", 0)
    duration = results.get("durationMs", 0) / 1000

    print(f"\n{'='*50}")
    print(f"TEST RUN: {passed}/{total_ran} passed, {failed} failed ({duration:.1f}s)")
    print(f"{'='*50}")
    for r in results.get("results", []):
        icon = "✓" if r["status"] == "PASSED" else "✗"
        detail = ""
        for st in r.get("steps", []):
            if st.get("status") == "FAILED":
                detail = f" — {st.get('detail', '')[:80]}"
                break
        print(f"  {icon} {r['testId']}: {r['status']}{detail}")

    # Write results JSON
    results_path = Path("test-results.json")
    results_path.write_text(json.dumps(results, indent=2))
    logger.info("Results written to {}", results_path)

    if failed > 0:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
