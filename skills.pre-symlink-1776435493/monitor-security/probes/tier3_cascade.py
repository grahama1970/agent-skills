"""Tier 3 — Cascade Validation probes.

P30: cascade-validate
P31: label-accumulation
P32: shadow-tracking
P33: retrain-trigger
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from loguru import logger

import config
from probes import register_probe, ProbeResult, ProbeStatus


def _count_lines(file_path: Path) -> int:
    """Count lines in a file."""
    if not file_path.exists():
        return 0
    try:
        return sum(1 for _ in open(file_path))
    except OSError:
        return 0


@register_probe("P30", "cascade-validate", tier=4, auto_fixable=False)
def probe_cascade_validate(autofix: bool = False) -> ProbeResult:
    """Pipe all T2 findings through CascadeRunner (T0->T1.5->T2)."""
    report_path = config.STATE_DIR / "report_t2.json"

    if not report_path.exists():
        return ProbeResult(
            probe_id="P30", name="cascade-validate", tier=4,
            status=ProbeStatus.SKIP,
            message="No T2 findings to validate (run tier 3 first)",
        )

    try:
        data = json.loads(report_path.read_text())
    except (json.JSONDecodeError, OSError):
        return ProbeResult(
            probe_id="P30", name="cascade-validate", tier=4,
            status=ProbeStatus.FAIL, message="Failed to read T2 report",
        )

    raw_output = data.get("raw_output", "")
    finding_count = data.get("findings", 0)

    if finding_count == 0:
        return ProbeResult(
            probe_id="P30", name="cascade-validate", tier=4,
            status=ProbeStatus.PASS,
            message="No findings to validate",
        )

    # Try to import cascade from pi-mono
    try:
        import sys
        pi_skills = str(config.SKILLS_DIR)
        if pi_skills not in sys.path:
            sys.path.insert(0, pi_skills)
        from hack.cascade_integration import cascade_validate_findings
    except ImportError:
        return ProbeResult(
            probe_id="P30", name="cascade-validate", tier=4,
            status=ProbeStatus.SKIP,
            message="cascade_integration not available (pi-mono not accessible)",
        )

    # Build findings list from raw output
    findings = []
    for line in raw_output.splitlines():
        if "Issue:" in line or "Severity:" in line or "vuln" in line.lower():
            findings.append({
                "description": line.strip()[:500],
                "file_path": "",
                "severity": "medium",
            })

    if not findings:
        findings = [{"description": raw_output[:1000], "severity": "medium"}]

    validated = cascade_validate_findings(findings)

    tp = sum(1 for f in validated if f.get("cascade_verdict") == "true_positive")
    fp = sum(1 for f in validated if f.get("cascade_verdict") == "false_positive")

    # Save cascade report
    cascade_report = config.STATE_DIR / "report_t3.json"
    try:
        import os
        tmp = cascade_report.with_suffix(".tmp")
        tmp.write_text(json.dumps({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "total": len(validated),
            "true_positive": tp,
            "false_positive": fp,
            "findings": validated[:50],
        }, indent=2))
        os.replace(tmp, cascade_report)
    except OSError:
        pass

    if tp == 0 and fp > 0:
        return ProbeResult(
            probe_id="P30", name="cascade-validate", tier=4,
            status=ProbeStatus.PASS,
            message=f"All {fp} findings classified as false positive by cascade",
            details={"true_positive": tp, "false_positive": fp},
        )

    return ProbeResult(
        probe_id="P30", name="cascade-validate", tier=4,
        status=ProbeStatus.WARN if tp > 0 else ProbeStatus.PASS,
        message=f"Cascade: {tp} true positive, {fp} false positive out of {len(validated)}",
        details={"true_positive": tp, "false_positive": fp, "total": len(validated)},
    )


@register_probe("P31", "label-accumulation", tier=4, auto_fixable=False)
def probe_label_accumulation(autofix: bool = False) -> ProbeResult:
    """Check Brandon judgment labels accumulated for training."""
    labels_file = config.TRAINING_LABELS_FILE

    count = _count_lines(labels_file)

    if count == 0:
        return ProbeResult(
            probe_id="P31", name="label-accumulation", tier=4,
            status=ProbeStatus.PASS,
            message="No training labels yet (Brandon hasn't judged any findings)",
            details={"label_count": 0, "threshold": config.RETRAIN_LABEL_THRESHOLD},
        )

    pct_of_threshold = count / config.RETRAIN_LABEL_THRESHOLD * 100

    return ProbeResult(
        probe_id="P31", name="label-accumulation", tier=4,
        status=ProbeStatus.PASS,
        message=f"{count} training labels ({pct_of_threshold:.0f}% of retrain threshold {config.RETRAIN_LABEL_THRESHOLD})",
        details={
            "label_count": count,
            "threshold": config.RETRAIN_LABEL_THRESHOLD,
            "pct_of_threshold": round(pct_of_threshold, 1),
        },
    )


@register_probe("P32", "shadow-tracking", tier=4, auto_fixable=False)
def probe_shadow_tracking(autofix: bool = False) -> ProbeResult:
    """Report GPT swarm agreement rate and promotion readiness."""
    shadow_file = config.SHADOW_FILE

    if not shadow_file.exists():
        return ProbeResult(
            probe_id="P32", name="shadow-tracking", tier=4,
            status=ProbeStatus.PASS,
            message="No shadow entries yet (GPT swarm not active)",
        )

    total = agree = disagree = 0
    try:
        for line in shadow_file.read_text().splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                if entry.get("agreed"):
                    agree += 1
                else:
                    disagree += 1
                total += 1
            except json.JSONDecodeError:
                continue
    except OSError:
        pass

    if total == 0:
        return ProbeResult(
            probe_id="P32", name="shadow-tracking", tier=4,
            status=ProbeStatus.PASS,
            message="No shadow comparisons recorded",
        )

    rate = agree / total if total > 0 else 0.0
    readiness = "ready" if rate >= 0.90 else "learning" if rate >= 0.70 else "early"

    return ProbeResult(
        probe_id="P32", name="shadow-tracking", tier=4,
        status=ProbeStatus.PASS,
        message=f"Shadow: {rate:.1%} agreement ({total} comparisons, status={readiness})",
        details={
            "total": total,
            "agree": agree,
            "disagree": disagree,
            "agreement_rate": round(rate, 4),
            "readiness": readiness,
        },
    )


@register_probe("P33", "retrain-trigger", tier=4, auto_fixable=False)
def probe_retrain_trigger(autofix: bool = False) -> ProbeResult:
    """If new labels > threshold, trigger /create-gpt retraining."""
    labels_file = config.TRAINING_LABELS_FILE
    count = _count_lines(labels_file)

    if count < config.RETRAIN_LABEL_THRESHOLD:
        return ProbeResult(
            probe_id="P33", name="retrain-trigger", tier=4,
            status=ProbeStatus.PASS,
            message=f"{count}/{config.RETRAIN_LABEL_THRESHOLD} labels (retrain not triggered)",
            details={"label_count": count, "threshold": config.RETRAIN_LABEL_THRESHOLD},
        )

    # Threshold reached — trigger retraining
    if not autofix:
        return ProbeResult(
            probe_id="P33", name="retrain-trigger", tier=4,
            status=ProbeStatus.WARN,
            message=f"{count} labels reached threshold! Run with --autofix to trigger /create-gpt retrain",
            details={"label_count": count, "threshold": config.RETRAIN_LABEL_THRESHOLD},
            auto_fixable=True,
        )

    # Attempt to trigger /create-gpt retraining
    create_gpt_skill = config.SKILLS_DIR / "create-gpt"
    create_gpt_script = create_gpt_skill / "run.sh"

    if not create_gpt_script.exists():
        return ProbeResult(
            probe_id="P33", name="retrain-trigger", tier=4,
            status=ProbeStatus.WARN,
            message=f"{count} labels ready but /create-gpt skill not found",
            details={"label_count": count},
            auto_fixable=True,
        )

    try:
        result = subprocess.run(
            [str(create_gpt_script), "train",
             "--labels", str(labels_file),
             "--task", "vuln-classifier",
             "--mode", "teacher-student"],
            capture_output=True, text=True, timeout=600,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode == 0:
            return ProbeResult(
                probe_id="P33", name="retrain-trigger", tier=4,
                status=ProbeStatus.FIXED,
                message=f"Retrain triggered with {count} labels",
                details={"label_count": count},
                auto_fixable=True,
                fix_applied=True,
            )
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.error("Retrain trigger failed: {}", e)

    return ProbeResult(
        probe_id="P33", name="retrain-trigger", tier=4,
        status=ProbeStatus.WARN,
        message=f"Retrain attempted but failed ({count} labels)",
        details={"label_count": count},
        auto_fixable=True,
    )
