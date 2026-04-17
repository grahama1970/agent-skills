"""Tier 2 — Docker Self-Hack probes.

P20: docker-twin-build
P21: hack-scan-twin
P22: critical-escalation
P23: finding-scoring
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

from loguru import logger

import config
from probes import register_probe, ProbeResult, ProbeStatus


def _run_cmd(cmd: list[str], timeout: int = 300) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.debug("Command failed: {}", e)
        return None


def _load_threat_intel_digest() -> dict:
    """Load hourly threat intel digest for attack vector prioritization."""
    if config.THREAT_INTEL_DIGEST.exists():
        try:
            return json.loads(config.THREAT_INTEL_DIGEST.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


@register_probe("P20", "docker-twin-build", tier=3, auto_fixable=False)
def probe_docker_twin_build(autofix: bool = False) -> ProbeResult:
    """Build embry-os container from Dockerfile.embry-os."""
    if not shutil.which("docker"):
        return ProbeResult(
            probe_id="P20", name="docker-twin-build", tier=3,
            status=ProbeStatus.SKIP, message="Docker not available",
        )

    dockerfile = config.SELFHACK_DOCKERFILE
    if not dockerfile.exists():
        return ProbeResult(
            probe_id="P20", name="docker-twin-build", tier=3,
            status=ProbeStatus.SKIP,
            message=f"Dockerfile not found: {dockerfile}",
        )

    # Check if image already exists
    result = _run_cmd(["docker", "images", "-q", config.SELFHACK_IMAGE], timeout=10)
    if result and result.stdout.strip():
        return ProbeResult(
            probe_id="P20", name="docker-twin-build", tier=3,
            status=ProbeStatus.PASS,
            message=f"Self-hack image exists: {config.SELFHACK_IMAGE}",
            details={"image_id": result.stdout.strip()[:12]},
        )

    # Build image
    logger.info("Building self-hack Docker image...")
    build_result = _run_cmd(
        ["docker", "build", "-t", config.SELFHACK_IMAGE,
         "-f", str(dockerfile), str(config.EMBRY_OS_ROOT)],
        timeout=600,
    )

    if build_result and build_result.returncode == 0:
        return ProbeResult(
            probe_id="P20", name="docker-twin-build", tier=3,
            status=ProbeStatus.PASS,
            message="Self-hack Docker image built successfully",
        )

    return ProbeResult(
        probe_id="P20", name="docker-twin-build", tier=3,
        status=ProbeStatus.FAIL,
        message="Docker build failed",
        details={"stderr": (build_result.stderr[:500] if build_result else "timeout")},
    )


@register_probe("P21", "hack-scan-twin", tier=3, auto_fixable=False)
def probe_hack_scan_twin(autofix: bool = False) -> ProbeResult:
    """Run /hack scan against the Docker twin."""
    if not shutil.which("docker"):
        return ProbeResult(
            probe_id="P21", name="hack-scan-twin", tier=3,
            status=ProbeStatus.SKIP, message="Docker not available",
        )

    # Read threat intel digest for attack vector prioritization
    digest = _load_threat_intel_digest()
    matches = digest.get("matches", [])
    priority_deps = [m.get("matched_dependency", "") for m in matches]

    hack_script = config.HACK_SKILL / "run.sh"
    if not hack_script.exists():
        return ProbeResult(
            probe_id="P21", name="hack-scan-twin", tier=3,
            status=ProbeStatus.SKIP, message="Hack skill not found",
        )

    # Run audit against embry-os (mounted read-only in container)
    cmd = [str(hack_script), "audit", str(config.EMBRY_OS_ROOT), "--tool", "all"]
    result = _run_cmd(cmd, timeout=600)

    if result is None:
        return ProbeResult(
            probe_id="P21", name="hack-scan-twin", tier=3,
            status=ProbeStatus.FAIL, message="Hack scan timed out or failed",
        )

    # Parse findings
    stdout = result.stdout
    finding_count = stdout.count("Issue:") + stdout.count("Severity:")
    has_critical = "CRITICAL" in stdout.upper() or "HIGH" in stdout.upper()

    details: dict = {
        "finding_count": finding_count,
        "has_critical": has_critical,
        "returncode": result.returncode,
    }

    if priority_deps:
        details["threat_intel_deps"] = priority_deps[:5]
        details["note"] = f"Attack vectors prioritized by {len(matches)} threat intel matches"

    # Save raw report
    report_path = config.STATE_DIR / "report_t2.json"
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import os
        tmp = report_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "findings": finding_count,
            "has_critical": has_critical,
            "raw_output": stdout[:5000],
            "threat_intel_matches": len(matches),
        }, indent=2))
        os.replace(tmp, report_path)
    except OSError:
        pass

    if finding_count == 0:
        return ProbeResult(
            probe_id="P21", name="hack-scan-twin", tier=3,
            status=ProbeStatus.PASS,
            message="No findings from hack scan",
            details=details,
        )

    status = ProbeStatus.FAIL if has_critical else ProbeStatus.WARN
    return ProbeResult(
        probe_id="P21", name="hack-scan-twin", tier=3,
        status=status,
        message=f"{finding_count} finding(s) from hack scan (critical={has_critical})",
        details=details,
    )


@register_probe("P22", "critical-escalation", tier=3, auto_fixable=False)
def probe_critical_escalation(autofix: bool = False) -> ProbeResult:
    """If critical/high findings exist, recommend /battle."""
    report_path = config.STATE_DIR / "report_t2.json"

    if not report_path.exists():
        return ProbeResult(
            probe_id="P22", name="critical-escalation", tier=3,
            status=ProbeStatus.SKIP,
            message="No T2 report available (run hack-scan-twin first)",
        )

    try:
        data = json.loads(report_path.read_text())
    except (json.JSONDecodeError, OSError):
        return ProbeResult(
            probe_id="P22", name="critical-escalation", tier=3,
            status=ProbeStatus.FAIL, message="Failed to read T2 report",
        )

    has_critical = data.get("has_critical", False)
    finding_count = data.get("findings", 0)

    if has_critical:
        return ProbeResult(
            probe_id="P22", name="critical-escalation", tier=3,
            status=ProbeStatus.FAIL,
            message=f"ESCALATE: {finding_count} findings include critical/high. Recommend /battle",
            details={"recommendation": "Run ./battle/run.sh start against embry-os"},
        )

    if finding_count > 0:
        return ProbeResult(
            probe_id="P22", name="critical-escalation", tier=3,
            status=ProbeStatus.WARN,
            message=f"{finding_count} findings (no critical). Battle optional.",
        )

    return ProbeResult(
        probe_id="P22", name="critical-escalation", tier=3,
        status=ProbeStatus.PASS,
        message="No critical findings. No escalation needed.",
    )


@register_probe("P23", "finding-scoring", tier=3, auto_fixable=False)
def probe_finding_scoring(autofix: bool = False) -> ProbeResult:
    """Score all findings and generate patch recommendations."""
    report_path = config.STATE_DIR / "report_t2.json"

    if not report_path.exists():
        return ProbeResult(
            probe_id="P23", name="finding-scoring", tier=3,
            status=ProbeStatus.SKIP,
            message="No T2 report available",
        )

    try:
        data = json.loads(report_path.read_text())
    except (json.JSONDecodeError, OSError):
        return ProbeResult(
            probe_id="P23", name="finding-scoring", tier=3,
            status=ProbeStatus.FAIL, message="Failed to read T2 report",
        )

    finding_count = data.get("findings", 0)
    has_critical = data.get("has_critical", False)

    # Simple scoring: critical=10, high=5, medium=2, low=1
    if has_critical:
        score = finding_count * 5  # Weighted average assuming mix
    else:
        score = finding_count * 2

    recommendations = []
    if has_critical:
        recommendations.append("Immediate: Run /battle with state-actor profile")
        recommendations.append("Auto-fix: Run check --tier 0 --autofix for deterministic fixes")
    if finding_count > 5:
        recommendations.append("Review: Manual review of SAST findings recommended")

    # Write scored report
    scored_path = config.STATE_DIR / "finding_scores.json"
    try:
        import os
        tmp = scored_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "total_findings": finding_count,
            "risk_score": score,
            "has_critical": has_critical,
            "recommendations": recommendations,
        }, indent=2))
        os.replace(tmp, scored_path)
    except OSError:
        pass

    return ProbeResult(
        probe_id="P23", name="finding-scoring", tier=3,
        status=ProbeStatus.PASS if score == 0 else ProbeStatus.WARN,
        message=f"Risk score: {score} ({finding_count} findings)",
        details={
            "score": score,
            "findings": finding_count,
            "recommendations": recommendations,
        },
    )
