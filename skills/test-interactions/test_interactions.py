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
import os
import re
import time
import base64
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from typing import Optional

import typer
from loguru import logger

from cdp_client import CDPClient
from assertions import run_assertions, run_qid_compliance
from visual_evidence import (
    build_animation_clipping_finding,
    capture_animation_evidence,
    capture_step_visual_evidence,
    parse_analyst_findings,
    qid_from_selector,
    validate_visual_finding,
    write_findings_jsonl,
)
from discovery import discover_live_dom, write_discovery_artifacts
from page_eval import normalize_page_eval_findings
from ticket_integration import run_ticket_integration

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

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
    visual_evidence: dict = field(default_factory=dict)
    animation_evidence: dict = field(default_factory=dict)
    visual_findings: list = field(default_factory=list)


@dataclass
class TestResults:
    app: str = ""
    run_id: str = ""
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
    """Capture an untouched full-viewport screenshot for each interaction."""
    cdp.screenshot(path)


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("test-interactions-%Y%m%dT%H%M%S%fZ")


def _should_capture_visual_evidence(interaction: dict) -> bool:
    if interaction.get("visual_evidence") is False:
        return False
    if interaction.get("visual_evidence") is True:
        return True
    return bool(
        interaction.get("target")
        and (
            interaction.get("animation_capture")
            or interaction.get("animation_video")
            or interaction.get("burst")
            or interaction.get("expected_visual_state")
            or interaction.get("visual_finding_kind")
            or interaction.get("detect_animation_clipping")
        )
    )


def _should_capture_animation(interaction: dict) -> bool:
    return bool(
        interaction.get("animation_capture")
        or interaction.get("animation_video")
        or interaction.get("burst_video")
        or interaction.get("burst")
    )


def _url_origin(url: str) -> str:
    parsed = urlsplit(url)
    if not parsed.scheme or not parsed.netloc:
        return url.rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc}"


def _allows_url_guard_escape(interaction: dict, target_href: str, url_guard: str) -> bool:
    if not url_guard:
        return False
    if interaction.get("allow_external_navigation"):
        return True
    parsed = urlsplit(target_href or "")
    if parsed.scheme in {"mailto", "tel"}:
        return True
    if parsed.scheme and parsed.netloc:
        return _url_origin(target_href) != _url_origin(url_guard)
    return False


def _execute_interaction(
    cdp: CDPClient,
    interaction: dict,
    element_name: str,
    surface_name: str,
    output_dir: Path,
    step_index: int,
    run_id: str,
    url_guard: str = "",
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
    target_selector = str(
        interaction.get("target")
        or interaction.get("review_target")
        or interaction.get("focus")
        or ""
    ).strip()
    target_href = ""
    pre_action_screenshot = ""

    try:
        if target_selector:
            target_href = str(cdp.get_attribute(target_selector, "href") or "")
        assertions_before = interaction.get("assert_timing") == "before"
        if assertions_before:
            assertions = run_assertions(cdp, interaction, wait_ms)
            result.assertions = assertions
            for a in assertions:
                if a["status"] == "FAIL":
                    result.status = "FAIL"
                    result.evidence = f"PRE-ASSERTION FAILED: {a['check']} — {a['evidence']}"
                    break
            if result.status == "FAIL":
                return result

        if _should_capture_animation(interaction) and target_selector:
            pre_dir = output_dir / "visual-evidence"
            pre_dir.mkdir(parents=True, exist_ok=True)
            pre_action_screenshot = str(pre_dir / f"{safe_name}_pre-action.png")
            cdp.screenshot(pre_action_screenshot)

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
        if result.status != "FAIL" and not assertions_before:
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

        if url_guard:
            current_url = cdp.current_url()
            if not current_url.startswith(url_guard) and not _allows_url_guard_escape(interaction, target_href, url_guard):
                result.status = "FAIL"
                drift = f"URL drifted outside test target: {current_url!r} does not start with {url_guard!r}"
                result.evidence = f"{result.evidence} | {drift}" if result.evidence else drift

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
            if _should_capture_visual_evidence(interaction):
                result.visual_evidence = capture_step_visual_evidence(
                    cdp,
                    source_screenshot=Path(path),
                    output_dir=output_dir,
                    surface=surface_name,
                    element=element_name,
                    action=action,
                    description=description,
                    step_index=step_index,
                    interaction=interaction,
                    deterministic_status=result.status,
                    run_id=run_id,
                )
            if _should_capture_animation(interaction) and target_selector:
                result.animation_evidence = capture_animation_evidence(
                    cdp,
                    output_dir=output_dir,
                    step_index=step_index,
                    surface=surface_name,
                    element=element_name,
                    action=action,
                    interaction=interaction,
                )
                if pre_action_screenshot:
                    result.animation_evidence["pre_action_screenshot"] = pre_action_screenshot
                if result.animation_evidence.get("clipped_frame_count", 0) > 0:
                    qid = (
                        result.visual_evidence.get("qid")
                        or cdp.get_attribute(target_selector, "data-qid")
                        or qid_from_selector(target_selector)
                    )
                    finding = build_animation_clipping_finding(
                        run_id=run_id,
                        surface=surface_name,
                        element=element_name,
                        step_index=step_index,
                        qid=qid,
                        deterministic_status=result.status,
                        visual_evidence=result.visual_evidence,
                        animation_evidence=result.animation_evidence,
                        expected_state=str(interaction.get("expected_visual_state") or ""),
                        reproduction=(
                            f"Run this manifest and execute step {step_index}: "
                            f"{surface_name} > {element_name} > {description}"
                        ),
                    )
                    ok, errors = validate_visual_finding(finding)
                    if ok:
                        result.visual_findings.append(finding)
                    else:
                        invalid_path = output_dir / "visual-evidence" / f"{safe_name}_invalid-finding.json"
                        invalid_path.write_text(json.dumps({"finding": finding, "errors": errors}, indent=2) + "\n")
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
    url_guard = surface.get("url_guard") or base_url
    isolate_interactions = bool(surface.get("isolate_interactions"))
    logger.info("Surface: {} ({})", surface_name, nav_url)

    def navigate_surface():
        cdp.navigate(nav_url, wait_ms=2000)
        wait_ready = surface.get("wait_ready")
        if wait_ready:
            timeout = surface.get("wait_ready_timeout_ms", 15000)
            found = cdp.wait_for_selector(wait_ready, timeout_ms=timeout)
            if not found:
                logger.warning("wait_ready {} not found within {}ms", wait_ready, timeout)

    navigate_surface()

    step_index = 0
    for element in surface.get("elements", []):
        element_name = element.get("name", "unnamed")
        for interaction in element.get("interactions", []):
            step_index += 1
            if isolate_interactions:
                navigate_surface()
            r = _execute_interaction(
                cdp,
                interaction,
                element_name,
                surface_name,
                surface_dir,
                step_index,
                results.run_id,
                url_guard,
            )
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

    results = TestResults(app=data.get("app", "unknown"), run_id=_run_id())
    cdp = CDPClient()
    cdp.connect()

    logger.info("Running {} interactions across {} surfaces", total_interactions, len(surfaces))

    try:
        for s in surfaces:
            for attempt in range(1, max_retries + 1):
                attempt_results = TestResults(app=data.get("app", "unknown"), run_id=results.run_id)
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

    visual_findings = [
        finding
        for item in results.interactions
        for finding in getattr(item, "visual_findings", [])
    ]
    findings_path = output_dir / "visual-findings.jsonl"
    write_findings_jsonl(findings_path, visual_findings)
    logger.info("Structured visual findings written to {} ({} finding(s))", findings_path, len(visual_findings))

    if results.failed > 0:
        raise typer.Exit(1)


@app.command()
def generate(
    url: str = typer.Option(..., help="Target URL to analyze"),
    output: Path = typer.Option(Path("manifest.json"), help="Output manifest path"),
    output_dir: Path = typer.Option(Path("./discovery"), help="Directory for discovery inventory/findings/state graph"),
    max_depth: int = typer.Option(2, help="Maximum state exploration depth"),
    max_states: int = typer.Option(12, help="Maximum unique states to visit"),
    max_actions: int = typer.Option(40, help="Maximum QID actions to execute during discovery"),
):
    """Generate a replayable QID-only interaction manifest from the live DOM."""
    cdp = CDPClient()
    cdp.connect()
    try:
        result = discover_live_dom(
            cdp,
            url=url,
            max_depth=max_depth,
            max_states=max_states,
            max_actions=max_actions,
        )
    finally:
        cdp.close()
    paths = write_discovery_artifacts(result, output_dir, manifest_output=output)
    logger.info(
        "Manifest written to {} from {} discovered state(s), {} action(s), {} finding(s)",
        output, result["states_seen"], result["actions_run"], len(result.get("findings") or []),
    )
    logger.info("Discovery artifacts: {}", paths)


@app.command()
def discover(
    url: str = typer.Option(..., help="Target URL to explore via live CDP"),
    output_dir: Path = typer.Option(Path("./discovery"), help="Output directory for discovery artifacts"),
    manifest_output: Path = typer.Option(Path("./manifest.generated.json"), help="Generated replayable manifest path"),
    max_depth: int = typer.Option(2, help="Maximum state exploration depth"),
    max_states: int = typer.Option(12, help="Maximum unique states to visit"),
    max_actions: int = typer.Option(40, help="Maximum QID actions to execute during discovery"),
):
    """Explore live DOM states and write inventory, findings, state graph, and manifest."""
    cdp = CDPClient()
    cdp.connect()
    try:
        result = discover_live_dom(
            cdp,
            url=url,
            max_depth=max_depth,
            max_states=max_states,
            max_actions=max_actions,
        )
    finally:
        cdp.close()
    paths = write_discovery_artifacts(result, output_dir, manifest_output=manifest_output)
    logger.info("Discovery artifacts written: {}", paths)


@app.command("ticket-findings")
def ticket_findings(
    repo: str = typer.Option(..., help="Target GitHub repository, owner/name"),
    output_dir: Path = typer.Option(Path("./ticket-findings"), help="Output directory for candidates, previews, and apply/readback receipts"),
    target: str = typer.Option("skills/test-interactions", help="Concrete target path or skill for filed tickets"),
    policy: str = typer.Option("preview", help="Ticket policy: off, preview, deterministic-only, high-confidence, apply-confirmed"),
    results: Optional[Path] = typer.Option(None, help="results.json from run stage"),
    visual_findings: Optional[Path] = typer.Option(None, help="visual-findings.jsonl from #1095 structured visual findings"),
    discovery_findings: Optional[Path] = typer.Option(None, help="discovery-findings.jsonl from #1096 live discovery"),
    page_eval_findings: Optional[Path] = typer.Option(None, help="page-eval.finding.v1 JSONL from normalize-page-eval"),
    replay_command: str = typer.Option(..., help="Exact command that replays the source interaction/finding"),
    ticket_skill: Path = typer.Option(Path("skills/ticket/run.sh"), help="Delegated ticket runtime entrypoint"),
    confidence_threshold: float = typer.Option(0.85, help="Minimum visual confidence for high-confidence policy"),
    max_apply: int = typer.Option(1, help="Maximum issues to create in apply-confirmed mode"),
):
    """Normalize findings and preview/apply repair tickets through skills/ticket."""
    try:
        result = run_ticket_integration(
            repo=repo,
            target=target,
            policy=policy,
            output_dir=output_dir,
            ticket_skill=ticket_skill,
            replay_command=replay_command,
            results=results,
            visual_findings=visual_findings,
            discovery_findings=discovery_findings,
            page_eval_findings=page_eval_findings,
            threshold=confidence_threshold,
            max_apply=max_apply,
        )
    except Exception as exc:  # noqa: BLE001
        output_dir.mkdir(parents=True, exist_ok=True)
        failure_path = output_dir / "ticket-failure.json"
        failure_path.write_text(json.dumps({"error": str(exc), "mocked": False, "live": policy == "apply-confirmed"}, indent=2) + "\n")
        logger.error("Ticket integration failed; wrote {}", failure_path)
        raise typer.Exit(1)
    logger.info(
        "Ticket integration wrote {} candidate(s), {} preview(s), {} duplicate comment(s), {} created issue(s) to {}",
        result["candidate_count"], result["preview_count"], result["duplicate_count"], result["created_count"], output_dir,
    )


@app.command("normalize-page-eval")
def normalize_page_eval(
    repo: str = typer.Option(..., help="Target repository, owner/name"),
    target: str = typer.Option("skills/test-interactions", help="Concrete target path or skill for filed tickets"),
    route: str = typer.Option("/", help="Rendered app route evaluated by the source artifacts"),
    viewport: str = typer.Option("unknown", help="Viewport label or WxH used by the source artifacts"),
    output: Path = typer.Option(Path("./page-eval-findings.jsonl"), help="Strict page-eval.finding.v1 JSONL output"),
    summary_output: Path = typer.Option(Path("./page-eval-summary.json"), help="Normalization summary output"),
    impeccable_findings: Optional[Path] = typer.Option(None, help="Impeccable detector JSON output"),
    disable_impeccable: bool = typer.Option(False, help="Exclude Impeccable design findings even when --impeccable-findings is provided"),
    results: Optional[Path] = typer.Option(None, help="test-interactions results.json from run stage"),
    discovery_findings: Optional[Path] = typer.Option(None, help="test-interactions discovery-findings.jsonl"),
    visual_findings: Optional[Path] = typer.Option(None, help="test-interactions visual-findings.jsonl"),
    replay_command: str = typer.Option(..., help="Exact command that reproduces the source artifacts"),
):
    """Normalize Impeccable and test-interactions artifacts into one strict schema."""
    try:
        summary = normalize_page_eval_findings(
            repo=repo,
            target=target,
            route=route,
            viewport=viewport,
            replay_command=replay_command,
            output=output,
            summary_output=summary_output,
            impeccable_findings=impeccable_findings,
            disable_impeccable=disable_impeccable,
            results=results,
            discovery_findings=discovery_findings,
            visual_findings=visual_findings,
        )
    except Exception as exc:  # noqa: BLE001
        output.parent.mkdir(parents=True, exist_ok=True)
        failure_path = output.parent / "page-eval-failure.json"
        failure_path.write_text(json.dumps({"error": str(exc), "mocked": False, "live": False}, indent=2) + "\n")
        logger.error("Page-eval normalization failed; wrote {}", failure_path)
        raise typer.Exit(1)
    logger.info(
        "Page-eval normalization wrote {} finding(s) to {} (impeccable_included={})",
        summary["finding_count"], output, summary["impeccable_included"],
    )


def _preprocess_screenshots(captures_dir: Path):
    """Preprocess all PNGs with vlm_image: auto-crop, sharpen, upscale.

    Writes separate VLM copies. Human proof screenshots must remain untouched.
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

    vlm_dir = captures_dir / "vlm_preprocessed"
    screenshots = sorted(
        p for p in captures_dir.rglob("*.png")
        if "vlm_preprocessed" not in p.parts
    )
    if not screenshots:
        return

    processed = 0
    for png in screenshots:
        if "BURST_" in png.name:
            continue  # burst frames get stitched below
        raw = png.read_bytes()
        out = prepare_for_vlm(raw)
        target = vlm_dir / png.relative_to(captures_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(out)
        processed += 1

    # Stitch burst frames into single filmstrip per element
    for burst_dir in sorted(captures_dir.rglob("burst")):
        frames = sorted(burst_dir.glob("BURST_*.png"))
        if len(frames) > 1:
            frame_bytes = [f.read_bytes() for f in frames]
            stitched = stitch_vertical(frame_bytes)
            filmstrip_path = vlm_dir / burst_dir.parent.relative_to(captures_dir) / f"{burst_dir.parent.name}_filmstrip.png"
            filmstrip_path.parent.mkdir(parents=True, exist_ok=True)
            filmstrip_path.write_bytes(stitched)
            processed += 1

    if processed:
        logger.info("Preprocessed {} screenshots with vlm_image into {}", processed, vlm_dir)


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

    review_set_dir = captures / "semantic_review_selection"
    review_set_dir.mkdir(parents=True, exist_ok=True)
    for old_png in review_set_dir.glob("*.png"):
        old_png.unlink()
    for old_json in review_set_dir.glob("*.json"):
        old_json.unlink()
    failure_path = captures / "review-design-failure.json"
    if failure_path.exists():
        failure_path.unlink()
    selected_screenshots = _selected_visual_review_screenshots(captures, limit=6)
    selection_manifest = []
    for index, (label, screenshot) in enumerate(selected_screenshots, start=1):
        safe_label = re.sub(r"[^A-Za-z0-9_.-]+", "_", label).strip("_").lower()
        target = review_set_dir / f"{index:02d}_{safe_label}_{screenshot.parent.name}_{screenshot.name}"
        if not target.exists():
            target.write_bytes(screenshot.read_bytes())
        selection_manifest.append({
            "index": index,
            "label": label,
            "source": str(screenshot),
            "review_copy": str(target),
        })
    (review_set_dir / "selection_manifest.json").write_text(json.dumps(selection_manifest, indent=2))
    screenshots_path = review_set_dir

    fallback_env = os.environ.get("TEST_INTERACTIONS_REVIEW_PROVIDER_FALLBACKS", "")
    fallback_providers = [p.strip() for p in fallback_env.split(",") if p.strip()]
    providers_to_try = [provider] + [p for p in fallback_providers if p != provider]
    timeout_s = int(os.environ.get("TEST_INTERACTIONS_REVIEW_DESIGN_TIMEOUT_SEC", "600"))
    logger.info(
        "Running /review-design on {} selected screenshots from {} total...",
        len(selected_screenshots), len(screenshots),
    )

    for active_provider in providers_to_try:
        cmd = [
            str(run_sh), "review", "--screenshots", str(screenshots_path),
            "--provider", active_provider, "--persona", persona,
            "--rounds", "1",
        ]
        if context:
            cmd.extend(["--code-context", context])

        try:
            logger.info("Trying /review-design provider: {}", active_provider)
            started_at = time.time()
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout_s,
                env={
                    **os.environ,
                    "REVIEW_DESIGN_ROUNDS": "1",
                    "REVIEW_DESIGN_SCILLM_TIMEOUT_SEC": str(max(30, timeout_s - 10)),
                    "REVIEW_DESIGN_SCILLM_MODEL": os.environ.get(
                        "TEST_INTERACTIONS_REVIEW_DESIGN_MODEL",
                        "vlm",
                    ),
                },
            )
            if result.returncode == 0:
                review_dirs = [
                    captures / "review_output",
                    Path("${HOME}/workspace/experiments/embry-os/docs/review-output") / screenshots_path.name,
                    run_sh.parent / "review_output",
                ]
                for review_dir in review_dirs:
                    if review_dir.exists():
                        finals = sorted(
                            (
                                p for p in review_dir.glob("*_final.md")
                                if p.stat().st_mtime >= started_at - 1
                            ),
                            key=lambda p: p.stat().st_mtime,
                        )
                        if finals:
                            logger.info("review-design succeeded with {} (file: {})", active_provider, finals[-1])
                            if failure_path.exists():
                                failure_path.unlink()
                            return (
                                f"### Primary review-design Semantic Review ({active_provider})\n\n"
                                f"Reviewed {len(selected_screenshots)} purpose-labeled screenshots:\n"
                                + "\n".join(
                                    f"- `{item['review_copy']}` — {item['label']}"
                                    for item in selection_manifest
                                )
                                + "\n\n"
                                + finals[-1].read_text()
                            )
                if result.stdout.strip():
                    logger.info("review-design succeeded with {} (stdout)", active_provider)
                    if failure_path.exists():
                        failure_path.unlink()
                    return (
                        f"### Primary review-design Semantic Review ({active_provider})\n\n"
                        + result.stdout.strip()
                    )
                if result.stderr.strip():
                    logger.info("review-design succeeded with {} (stderr fallback)", active_provider)
                    if failure_path.exists():
                        failure_path.unlink()
                    return (
                        f"### Primary review-design Semantic Review ({active_provider})\n\n"
                        + result.stderr.strip()
                    )
            else:
                err_excerpt = (result.stderr or result.stdout or "").strip()[:600]
                logger.warning("review-design provider {} failed (exit {}): {}", active_provider, result.returncode, err_excerpt)
        except subprocess.TimeoutExpired as e:
            failure = {
                "stage": "review-design",
                "provider": active_provider,
                "timeout_s": timeout_s,
                "screenshots_total": len(screenshots),
                "screenshots_selected": [str(p) for p in selected_screenshots],
                "stdout": (e.stdout or "")[-2000:] if isinstance(e.stdout, str) else "",
                "stderr": (e.stderr or "")[-2000:] if isinstance(e.stderr, str) else "",
            }
            failure_path.write_text(json.dumps(failure, indent=2))
            logger.warning(
                "review-design provider {} timed out after {}s; wrote {}",
                active_provider, timeout_s, failure_path,
            )
        except Exception as e:
            logger.warning("review-design provider {} failed: {}", active_provider, e)

    return None


def _selected_visual_review_screenshots(captures: Path, limit: int = 6) -> list[tuple[str, Path]]:
    """Pick generic screenshots/crops for batched visual review."""
    results_file = captures / "results.json"
    if not results_file.exists():
        return [(path.name, path) for path in sorted(captures.rglob("*.png"))[:limit]]
    try:
        data = json.loads(results_file.read_text())
    except Exception:
        return [(path.name, path) for path in sorted(captures.rglob("*.png"))[:limit]]

    selected: list[tuple[str, Path]] = []
    selected_paths: set[Path] = set()
    for item in data.get("interactions", []):
        evidence = item.get("visual_evidence") or {}
        artifacts = evidence.get("artifacts") or {}
        for role in ("target_crop_enlarged", "target_crop", "semantic_container_crop"):
            artifact = artifacts.get(role) or {}
            path = Path(str(artifact.get("path") or ""))
            if path.exists() and path not in selected_paths:
                selected.append((f"{role}: {item.get('element', '')}", path))
                selected_paths.add(path)
                if len(selected) >= limit:
                    return selected[:limit]
    for item in data.get("interactions", []):
        if item.get("status") != "FAIL":
            continue
        screenshot = item.get("screenshot")
        path = Path(screenshot) if screenshot else Path()
        if path.exists() and path not in selected_paths:
            selected.append((f"deterministic failure: {item.get('element', '')}", path))
            selected_paths.add(path)
            if len(selected) >= limit:
                return selected[:limit]
    for path in sorted(captures.rglob("*.png")):
        if len(selected) >= limit:
            break
        if path not in selected_paths and "vlm_preprocessed" not in path.parts and "semantic_review_selection" not in path.parts:
            selected.append((path.name, path))
            selected_paths.add(path)
    return selected[:limit]


def _run_scillm_visual_review(captures: Path, context: str = "", persona: str = "") -> Optional[str]:
    """Fallback semantic screenshot review through scillm's VLM route."""
    import httpx

    screenshots = _selected_visual_review_screenshots(captures)
    if not screenshots:
        logger.warning("No screenshots available for scillm visual review")
        return None
    model = os.environ.get("TEST_INTERACTIONS_VISUAL_REVIEW_MODEL", "vlm")

    content: list[dict] = [
        {
            "type": "text",
            "text": (
                f"You are {persona or 'a practical UI QA reviewer'} reviewing UI interaction evidence. "
                "Review only the screenshots and crop metadata provided for each interaction. "
                "Call out candidate visual defects such as clipping, occlusion, unreadable text, incorrect transition order, "
                "unexpected visual state, missing feedback, or target/context mismatch. "
                "Do not change deterministic PASS/FAIL verdicts; visual observations are candidate findings only. "
                f"Context/profile: {context or 'generic UI interaction test'}"
            ),
        }
    ]
    for label, screenshot in screenshots:
        encoded = base64.b64encode(screenshot.read_bytes()).decode("ascii")
        content.append({"type": "text", "text": f"Screenshot: {label} — {screenshot.name}"})
        content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}})

    try:
        response = httpx.post(
            "http://localhost:4001/v1/chat/completions",
            headers={
                "Authorization": "Bearer sk-dev-proxy-123",
                "X-Caller-Skill": "test-interactions",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": content}],
                "timeout": 90,
            },
            timeout=90.0,
        )
        response.raise_for_status()
        text = response.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        logger.warning("scillm visual review failed: {}", exc)
        return None
    return (
        f"### Fallback Semantic Screenshot Review via scillm VLM ({model})\n\n"
        f"Reviewed {len(screenshots)} selected screenshots:\n"
        + "\n".join(f"- `{path}` — {label}" for label, path in screenshots)
        + "\n\n"
        + text
    )


@app.command("validate-visual-findings")
def validate_visual_findings_command(
    analyst_output: Path = typer.Option(..., help="JSON or JSONL analyst output to validate"),
    output: Path = typer.Option(Path("./visual-findings.jsonl"), help="Validated findings JSONL output"),
    failure_output: Path = typer.Option(Path("./visual-findings-invalid.json"), help="Invalid-output diagnostic artifact"),
):
    """Validate analyst visual-finding output and fail closed on prose/invalid schema."""
    if not analyst_output.exists():
        logger.error("Analyst output not found: {}", analyst_output)
        raise typer.Exit(1)
    valid, invalid = parse_analyst_findings(analyst_output.read_text())
    if invalid:
        failure_output.parent.mkdir(parents=True, exist_ok=True)
        failure_output.write_text(json.dumps({
            "schema": "test-interactions.visual-finding-validation.v1",
            "status": "review_failure",
            "source": str(analyst_output),
            "valid_count": len(valid),
            "invalid_count": len(invalid),
            "invalid": invalid,
        }, indent=2) + "\n")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("")
        logger.error("Invalid analyst output recorded at {}; zero structured findings emitted", failure_output)
        raise typer.Exit(1)
    write_findings_jsonl(output, valid)
    if failure_output.exists():
        failure_output.unlink()
    logger.info("Validated {} structured visual finding(s) into {}", len(valid), output)


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
    if not visual_review:
        visual_review = _run_scillm_visual_review(captures, context, persona)
    if visual_review:
        lines.extend(["", "## Visual Design Review", ""])
        lines.append(f"*Generated by semantic screenshot review — persona: {persona}*")
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
            headers={
                "Authorization": "Bearer sk-dev-proxy-123",
                "X-Caller-Skill": "test-interactions",
            },
            json={"model": "text", "messages": [{"role": "user", "content": prompt}], "timeout": 45},
            timeout=45.0,
        )
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"]
            logger.info("Persona summary generated ({} chars)", len(content))
            return content
        else:
            logger.warning("scillm returned {}: {}", resp.status_code, resp.text[:500])
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
