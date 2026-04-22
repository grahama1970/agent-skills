#!/usr/bin/env python3
"""Systematic UI interaction testing with DOM assertions and PASS/FAIL verdicts.

Uses CDP directly — single persistent WebSocket, no subprocess overhead.
Playwright-inspired assertions with auto-retry for SPA testing.

Architecture:
  RUN stage  — deterministic CDP interactions + assertions → PASS/FAIL verdicts
  REVIEW stage — batch all screenshots into one /scillm call → visual critique

The LLM never decides pass/fail. It only comments on evidence after deterministic
tests have already run. All interactions target [data-qid] selectors — no exceptions.

Manifest interactions support:
  Actions: screenshot | click | type | wait | scroll | key | tab
  Assertions: assert_selector | assert_visible | assert_text | assert_absent |
    assert_count | assert_attribute | assert_css | assert_value | assert_url |
    assert_enabled | assert_disabled | assert_aria |
    assert_min_size | assert_font_size | assert_contrast | assert_title |
    assert_qs_action | assert_focus_visible
  All assertions support _not suffix for negation and auto-retry with timeout.

  Per-surface: qid_compliance scan checks all [data-qid] elements for
  4-attribute rule (data-qid, data-qs-action, title) and COTS sizing (C02).
"""

import json
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

import yaml
from typing import Optional

import typer
from loguru import logger

from cdp_client import CDPClient
from assertions import run_assertions, run_qid_compliance

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

_VLM_PREPARE = None
_VLM_PREPARE_CHECKED = False


def _get_vlm_prepare():
    """Lazy-load VLM image preprocessor (auto-crop + upscale + sharpen)."""
    global _VLM_PREPARE, _VLM_PREPARE_CHECKED
    if _VLM_PREPARE_CHECKED:
        return _VLM_PREPARE
    _VLM_PREPARE_CHECKED = True
    try:
        import sys
        common_dir = Path(__file__).resolve().parent.parent / "common"
        if str(common_dir) not in sys.path:
            sys.path.insert(0, str(common_dir))
        from vlm_image import prepare_for_vlm  # type: ignore
        _VLM_PREPARE = prepare_for_vlm
    except Exception as e:  # noqa: BLE001
        logger.debug("vlm_image unavailable for per-step preprocessing: {}", e)
        _VLM_PREPARE = None
    return _VLM_PREPARE


def _capture_step_screenshot(cdp: CDPClient, path: str):
    """Capture screenshot for each interaction and preprocess for visual clarity."""
    cdp.screenshot(path)
    prepare = _get_vlm_prepare()
    if prepare:
        raw = Path(path).read_bytes()
        out = prepare(raw)
        Path(path).write_bytes(out)


def _execute_interaction(
    cdp: CDPClient,
    interaction: dict,
    element_name: str,
    surface_name: str,
    output_dir: Path,
    step_index: int,
) -> InteractionResult:
    action = interaction.get("action", "screenshot")
    description = interaction.get("description", f"{action} on {element_name}")
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{element_name}_{action}").strip("_") or "interaction"
    safe_name = f"{step_index:04d}_{slug}"
    wait_ms = interaction.get("wait_ms", 300)
    t0 = time.time()

    result = InteractionResult(
        surface=surface_name, element=element_name,
        action=action, description=description,
    )

    try:
        if action == "screenshot":
            result.status = "PASS"
            result.evidence = "screenshot requested"

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

        elif action == "key":
            key_name = interaction.get("key", interaction.get("target", ""))
            if not key_name:
                result.status = "FAIL"
                result.evidence = "no key specified"
            else:
                cdp.press_key(key_name)
                focused_qid = cdp.get_focused_qid()
                result.status = "PASS"
                result.evidence = f"pressed {key_name}, focus on qid={focused_qid}"

        elif action == "tab":
            count = interaction.get("count", 1)
            focused_qids = []
            for _ in range(count):
                cdp.press_key("Tab")
                time.sleep(0.1)
                focused_qids.append(cdp.get_focused_qid())
            result.status = "PASS"
            result.evidence = f"tabbed {count}x, focus path: {focused_qids}"

        elif action == "hover":
            target = interaction.get("target", "")
            if not target:
                result.status = "FAIL"
                result.evidence = "no target selector specified"
            else:
                hover_result = cdp.hover_selector(target)
                if hover_result.get("ok"):
                    result.status = "PASS"
                    tag = hover_result.get("tag", "?")
                    text = hover_result.get("text", "")[:60]
                    x, y = hover_result.get("x", 0), hover_result.get("y", 0)
                    result.evidence = f"hovered <{tag}> {text!r} at ({x:.0f}, {y:.0f})"
                else:
                    result.status = "FAIL"
                    result.evidence = hover_result.get("error", "hover failed")

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
    finally:
        try:
            if action != "screenshot":
                time.sleep(wait_ms / 1000.0)
            path = str(output_dir / f"{safe_name}.png")
            _capture_step_screenshot(cdp, path)
            result.screenshot = path
            if action == "screenshot" and result.evidence == "screenshot requested":
                result.evidence = f"captured {path}"
        except Exception as shot_e:  # noqa: BLE001
            if result.status != "FAIL":
                result.status = "FAIL"
            if result.evidence:
                result.evidence += f" | screenshot failed: {shot_e}"
            else:
                result.evidence = f"screenshot failed: {shot_e}"

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
    text = manifest_path.read_text()
    if manifest_path.suffix in (".yaml", ".yml"):
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
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

    step_index = 0
    for element in surface.get("elements", []):
        element_name = element.get("name", "unnamed")
        for interaction in element.get("interactions", []):
            step_index += 1
            r = _execute_interaction(cdp, interaction, element_name, surface_name, surface_dir, step_index)
            results.add(r)

    # Per-surface qid compliance scan (deterministic, no LLM)
    if surface.get("qid_compliance", True):
        qid_results = run_qid_compliance(cdp)
        for qr in qid_results:
            r = InteractionResult(
                surface=surface_name, element=qr["qid"],
                action="qid_compliance", description=qr["check"],
                status=qr["status"], evidence=qr["evidence"],
            )
            results.add(r)
            icon = "\u2713" if r.status == "PASS" else "\u2717"
            logger.info("  [{}] {} — qid:{} | {}", icon, r.status, qr["qid"], qr["evidence"])


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


def _preprocess_screenshots(captures_dir: Path):
    """Preprocess all PNGs with vlm_image: auto-crop, sharpen, upscale.

    Modifies files in-place. Skips if vlm_image is not available.
    """
    import sys
    common_dir = Path(__file__).resolve().parent.parent / "common"
    if not (common_dir / "vlm_image.py").exists():
        logger.warning("vlm_image.py not found at {}, skipping preprocessing", common_dir)
        return
    if str(common_dir) not in sys.path:
        sys.path.insert(0, str(common_dir))
    try:
        from vlm_image import prepare_for_vlm, stitch_vertical
    except ImportError:
        logger.warning("Failed to import vlm_image (missing Pillow?), skipping preprocessing")
        return

    screenshots = sorted(captures_dir.rglob("*.png"))
    if not screenshots:
        return

    processed = 0
    for png in screenshots:
        if "BURST_" in png.name:
            continue  # burst frames get stitched below
        raw = png.read_bytes()
        out = prepare_for_vlm(raw)
        png.write_bytes(out)
        processed += 1

    # Stitch burst frames into single filmstrip per element
    for burst_dir in sorted(captures_dir.rglob("burst")):
        frames = sorted(burst_dir.glob("BURST_*.png"))
        if len(frames) > 1:
            frame_bytes = [f.read_bytes() for f in frames]
            stitched = stitch_vertical(frame_bytes)
            filmstrip_path = burst_dir.parent / f"{burst_dir.parent.name}_filmstrip.png"
            filmstrip_path.write_bytes(stitched)
            processed += 1

    if processed:
        logger.info("Preprocessed {} screenshots with vlm_image", processed)


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
    captures: Path, context: str = "", provider: str = "subagent", persona: str = "",
) -> Optional[str]:
    """Call /review-design with provider fallback. Returns review text or None."""
    import subprocess

    if not persona:
        logger.error("No persona specified for /review-design — a review without a persona is a failure")
        return None

    run_sh = _find_review_design()
    if not run_sh:
        logger.warning("review-design skill not found, skipping visual review")
        return None

    screenshots = sorted(captures.rglob("*.png"))
    if not screenshots:
        logger.warning("No screenshots found in {}", captures)
        return None

    screenshot_dirs = {p.parent for p in screenshots}
    screenshots_path = max(screenshot_dirs, key=lambda d: len(list(d.glob("*.png")))) if screenshot_dirs else captures

    providers_to_try = [provider] + [p for p in ["subagent", "claude", "openai", "gemini"] if p != provider]
    logger.info("Running /review-design on {} screenshots...", len(screenshots))

    for active_provider in providers_to_try:
        cmd = [
            str(run_sh), "review", "--screenshots", str(screenshots_path),
            "--provider", active_provider, "--persona", persona,
        ]
        if context:
            cmd.extend(["--context", context])

        try:
            logger.info("Trying /review-design provider: {}", active_provider)
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300,
                env={**__import__("os").environ, "REVIEW_DESIGN_ROUNDS": "1"},
            )
            if result.returncode == 0:
                review_dirs = [captures / "review_output", run_sh.parent / "review_output"]
                for review_dir in review_dirs:
                    if review_dir.exists():
                        finals = sorted(review_dir.glob("*_final.md"), key=lambda p: p.stat().st_mtime)
                        if finals:
                            logger.info("review-design succeeded with {} (file: {})", active_provider, finals[-1])
                            return finals[-1].read_text()
                if result.stdout.strip():
                    logger.info("review-design succeeded with {} (stdout)", active_provider)
                    return result.stdout.strip()
                if result.stderr.strip():
                    logger.info("review-design succeeded with {} (stderr fallback)", active_provider)
                    return result.stderr.strip()
            else:
                err_excerpt = (result.stderr or result.stdout or "").strip()[:600]
                logger.warning("review-design provider {} failed (exit {}): {}", active_provider, result.returncode, err_excerpt)
        except subprocess.TimeoutExpired:
            logger.warning("review-design provider {} timed out after 300s", active_provider)
        except Exception as e:
            logger.warning("review-design provider {} failed: {}", active_provider, e)

    return None


@app.command()
def review(
    captures: Path = typer.Option(..., help="Directory containing captured screenshots"),
    output: Path = typer.Option(Path("./INTERACTION_REPORT.md"), help="Output report path"),
    context: str = typer.Option("", help="Context string for /review-design"),
    provider: str = typer.Option("subagent", help="Vision AI provider for /review-design (auto-fallback enabled)"),
    persona: str = typer.Option(..., "--persona", help="Persona agent for /review-design (e.g. brandon-bailey, rob-armstrong). REQUIRED."),
    preprocess: bool = typer.Option(True, help="Preprocess screenshots with vlm_image before review"),
):
    """Generate report from results.json + /review-design visual audit.

    --persona is REQUIRED. A review without a persona produces generic,
    unfocused feedback. The test fails if no persona is specified.
    """
    if not persona:
        logger.error("--persona is required. A review without a persona is a failure.")
        raise typer.Exit(1)

    if not captures.exists():
        logger.error("Captures directory not found: {}", captures)
        raise typer.Exit(1)

    results_file = captures / "results.json"
    if not results_file.exists():
        logger.warning("No results.json in {}. Run `test-interactions run` first.", captures)
        return

    # Preprocess screenshots for VLM (auto-crop, sharpen, upscale)
    if preprocess:
        _preprocess_screenshots(captures)

    data = json.loads(results_file.read_text())
    lines = [
        f"# Interaction Test Report: {data.get('app', 'Unknown')}",
        f"**Date**: {time.strftime('%Y-%m-%d %H:%M')}",
        f"**Persona**: {persona}",
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

    # QID compliance section
    qid_failures = [r for r in data.get("interactions", []) if r.get("action") == "qid_compliance" and r["status"] == "FAIL"]
    if qid_failures:
        lines.extend(["", "## QID Compliance Failures", ""])
        for r in qid_failures:
            lines.append(f"- **{r['element']}**: {r['description']} — {r['evidence']}")

    if data["failed"] > 0:
        lines.extend(["", "## Failures", ""])
        for r in data.get("interactions", []):
            if r["status"] == "FAIL" and r.get("action") != "qid_compliance":
                lines.append(f"### {r['surface']} > {r['element']} > {r['action']}")
                lines.append(f"- **Description**: {r['description']}")
                lines.append(f"- **Evidence**: {r['evidence']}")
                if r.get("screenshot"):
                    lines.append(f"- **Screenshot**: {r['screenshot']}")
                lines.append("")

    # Run /review-design visual audit — batched LLM call at the end
    visual_review = _run_review_design(captures, context, provider, persona)
    if visual_review:
        lines.extend(["", "## Visual Design Review", ""])
        lines.append(f"*Generated by /review-design — AI vision audit with persona: {persona}*")
        lines.append("")
        lines.append(visual_review)
    else:
        lines.extend(["", "## Visual Design Review", ""])
        lines.append("*Skipped — /review-design not available or returned no output.*")

    # Final persona summary — deterministic /scillm call
    summary = _persona_summary(data, visual_review, persona)
    if summary:
        lines.extend(["", "## Final Assessment", ""])
        lines.append(f"*{persona} overall verdict via /scillm text-gemini:*")
        lines.append("")
        lines.append(summary)

    output.write_text("\n".join(lines))
    logger.info("Report written to {}", output)


def _persona_summary(data: dict, visual_review: Optional[str], persona: str) -> Optional[str]:
    """Final deterministic /scillm call: persona gives overall pass/fail verdict."""
    import httpx as _httpx

    passed = data.get("passed", 0)
    failed = data.get("failed", 0)
    total = data.get("total", 0)
    app_name = data.get("app", "Unknown")

    # Build a concise prompt from test results + visual review excerpt
    visual_excerpt = (visual_review or "No visual review available.")[:2000]
    failures = []
    for r in data.get("interactions", []):
        if r.get("status") == "FAIL":
            failures.append(f"- {r['surface']} > {r['element']} > {r['action']}: {r.get('evidence', '')[:100]}")
    failure_text = "\n".join(failures[:20]) if failures else "None"

    prompt = (
        f"You are {persona}, a QA persona reviewing interaction test results for {app_name}.\n\n"
        f"Test Results: {passed}/{total} PASS, {failed}/{total} FAIL\n\n"
        f"Failures:\n{failure_text}\n\n"
        f"Visual Review Excerpt:\n{visual_excerpt}\n\n"
        f"Give a 3-5 sentence overall assessment as {persona}. "
        f"State whether the application is ready for the next phase or what must be fixed first. "
        f"Be specific and honest — do not declare victory if there are real failures."
    )

    try:
        resp = _httpx.post(
            "http://localhost:4001/v1/chat/completions",
            headers={"Authorization": "Bearer sk-dev-proxy-123"},
            json={"model": "sonnet", "messages": [{"role": "user", "content": prompt}], "max_tokens": 512},
            timeout=30.0,
        )
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"]
            logger.info("Persona summary generated ({} chars)", len(content))
            return content
        else:
            logger.warning("scillm returned {}", resp.status_code)
    except Exception as e:
        logger.warning("Persona summary failed: {}", e)
    return None


@app.command()
def full(
    url: str = typer.Option(..., help="Target URL to test"),
    output_dir: Path = typer.Option(Path("./captures"), help="Output directory"),
    manifest: Optional[Path] = typer.Option(None, help="Existing manifest (skip generate)"),
    context: str = typer.Option("", help="Context string for /review-design"),
    provider: str = typer.Option("subagent", help="Vision AI provider for /review-design (auto-fallback enabled)"),
    persona: str = typer.Option(..., "--persona", help="Persona agent for /review-design (e.g. brandon-bailey). REQUIRED."),
    surface: Optional[str] = typer.Option(None, help="Run only this surface (by name)"),
    max_retries: int = typer.Option(1, help="Max attempts per surface on failure"),
    preprocess: bool = typer.Option(True, help="Preprocess screenshots with vlm_image before review"),
):
    """Full pipeline: generate manifest -> run interactions -> review + visual audit.

    --persona is REQUIRED. A test run without a persona is a failure.
    """
    if not persona:
        logger.error("--persona is required. A test run without a persona is a failure.")
        raise typer.Exit(1)

    manifest_path = manifest or (output_dir / "manifest.json")
    output_dir.mkdir(parents=True, exist_ok=True)

    if not manifest:
        logger.info("Step 1/3: Generating manifest")
        generate(url=url, output=manifest_path)
    else:
        logger.info("Step 1/3: Using existing manifest {}", manifest_path)

    logger.info("Step 2/3: Running interactions (deterministic CDP + assertions)")
    try:
        run(manifest=manifest_path, output_dir=output_dir, surface=surface, max_retries=max_retries)
    except SystemExit:
        pass

    logger.info("Step 3/3: Reviewing captures (persona: {})", persona)
    report_path = output_dir / "INTERACTION_REPORT.md"
    review(captures=output_dir, output=report_path,
           context=context, provider=provider, persona=persona, preprocess=preprocess)
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
