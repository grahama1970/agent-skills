"""Tier 1.5 probes: Classifier/GPT quality checks.

P10: classifier-quality-check — Run trained model on sample, compare with existing
P11: shadow-agreement — Report classifier vs Brandon agreement rate
P12: confidence-distribution — Distribution of classifier confidence scores

These probes only activate after sufficient training labels exist and a model
has been trained via /create-gpt.
"""
from __future__ import annotations
import os

import json
import sys
from pathlib import Path

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from probes import ProbeResult, ProbeStatus, register_probe

SKILLS_DIR = Path(__file__).resolve().parents[2]
if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))


def _find_model_dir() -> Path | None:
    """Find trained taxonomy-assessor model (create-gpt or local state)."""
    candidates = [
        SKILLS_DIR / "create-gpt" / "models" / "taxonomy-assessor" / "gguf",
        SKILLS_DIR / "create-gpt" / "models" / "taxonomy-assessor" / "sft",
        config.STATE_DIR / "models" / "taxonomy-assessor",
    ]
    for path in candidates:
        if path.exists() and any(path.iterdir()):
            return path
    return None


def _model_available() -> bool:
    """Check if a trained taxonomy assessor model exists."""
    return _find_model_dir() is not None


def _label_count() -> int:
    """Count training labels accumulated so far."""
    if not config.TRAINING_LABELS_FILE.exists():
        return 0
    return sum(1 for line in config.TRAINING_LABELS_FILE.read_text().splitlines() if line.strip())


@register_probe("P10", "classifier-quality-check", tier=15)
def probe_classifier_quality(autofix: bool = False) -> ProbeResult:
    """Run trained classifier on sampled documents, compare with existing tags."""
    if not _model_available():
        labels = _label_count()
        return ProbeResult(
            probe_id="P10", name="classifier-quality-check", tier=15,
            status=ProbeStatus.SKIP,
            message=f"No trained model yet ({labels}/{config.RETRAIN_LABEL_THRESHOLD} labels)",
            details={"labels": labels, "threshold": config.RETRAIN_LABEL_THRESHOLD},
        )

    # Run classifier on a sample and compare with existing tags
    import httpx

    try:
        from cascade_taxonomy import tier15_classifier as clf_fn, GRADES

        sample_limit = min(config.SAMPLE_SIZE, 50)
        transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0) as client:
            resp = client.post("/list", json={"collection": "lessons", "limit": sample_limit})
            if resp.status_code != 200:
                return ProbeResult(
                    probe_id="P10", name="classifier-quality-check", tier=15,
                    status=ProbeStatus.SKIP, message=f"Memory unavailable: HTTP {resp.status_code}",
                )
            data = resp.json()
        docs = [d for d in data.get("items", data.get("results", []))
                if (d.get("mind") or d.get("heart") or d.get("bridge_attributes")) and d.get("text")]

        if not docs:
            return ProbeResult(
                probe_id="P10", name="classifier-quality-check", tier=15,
                status=ProbeStatus.PASS, message="No documents to check",
            )

        agree = disagree = errors = 0
        for doc in docs:
            try:
                result = clf_fn(doc)
                if result is None:
                    errors += 1
                    continue
                grade = result.result.get("grade", "CORRECT")
                # "CORRECT" means classifier agrees existing tags are fine
                if grade == "CORRECT":
                    agree += 1
                else:
                    disagree += 1
            except Exception:
                errors += 1

        total = agree + disagree
        if total == 0:
            return ProbeResult(
                probe_id="P10", name="classifier-quality-check", tier=15,
                status=ProbeStatus.WARN,
                message=f"Classifier returned no results ({errors} errors)",
                details={"errors": errors},
            )

        agree_pct = agree / total * 100
        status = ProbeStatus.PASS if agree_pct >= 80 else ProbeStatus.WARN

        return ProbeResult(
            probe_id="P10", name="classifier-quality-check", tier=15,
            status=status,
            message=f"Classifier: {agree_pct:.0f}% agree with existing tags ({agree}/{total}, {errors} errors)",
            details={
                "agree": agree,
                "disagree": disagree,
                "errors": errors,
                "total": total,
                "agree_pct": round(agree_pct, 1),
            },
        )
    except Exception as e:
        return ProbeResult(
            probe_id="P10", name="classifier-quality-check", tier=15,
            status=ProbeStatus.FAIL, message=f"Classifier probe failed: {e}",
        )


@register_probe("P11", "shadow-agreement", tier=15)
def probe_shadow_agreement(autofix: bool = False) -> ProbeResult:
    """Report classifier vs Brandon agreement rate from shadow.jsonl."""
    if not config.SHADOW_FILE.exists():
        return ProbeResult(
            probe_id="P11", name="shadow-agreement", tier=15,
            status=ProbeStatus.SKIP,
            message="No shadow data yet (waiting for classifier + teacher runs)",
        )

    try:
        agree = disagree = 0
        for line in config.SHADOW_FILE.read_text().splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                if entry.get("task") != "taxonomy-assessor":
                    continue
                if entry.get("agreed"):
                    agree += 1
                else:
                    disagree += 1
            except (json.JSONDecodeError, KeyError):
                continue

        total = agree + disagree
        if total == 0:
            return ProbeResult(
                probe_id="P11", name="shadow-agreement", tier=15,
                status=ProbeStatus.SKIP,
                message="No taxonomy shadow entries yet",
            )

        rate = agree / total
        if rate >= 0.90:
            status = ProbeStatus.PASS
            msg = f"Shadow agreement {rate:.1%} ({agree}/{total}) — ready for promotion"
        elif rate >= 0.70:
            status = ProbeStatus.WARN
            msg = f"Shadow agreement {rate:.1%} ({agree}/{total}) — still learning"
        else:
            status = ProbeStatus.WARN
            msg = f"Shadow agreement {rate:.1%} ({agree}/{total}) — early stage"

        return ProbeResult(
            probe_id="P11", name="shadow-agreement", tier=15,
            status=status, message=msg,
            details={"agree": agree, "disagree": disagree, "total": total, "rate": round(rate, 4)},
        )
    except Exception as e:
        return ProbeResult(
            probe_id="P11", name="shadow-agreement", tier=15,
            status=ProbeStatus.FAIL, message=f"Failed to read shadow data: {e}",
        )


@register_probe("P12", "confidence-distribution", tier=15)
def probe_confidence_distribution(autofix: bool = False) -> ProbeResult:
    """Distribution of cascade confidence scores from metrics.jsonl."""
    if not config.METRICS_FILE.exists():
        return ProbeResult(
            probe_id="P12", name="confidence-distribution", tier=15,
            status=ProbeStatus.SKIP,
            message="No metrics data yet",
        )

    try:
        buckets = {"0.0-0.3": 0, "0.3-0.6": 0, "0.6-0.8": 0, "0.8-1.0": 0}
        total = 0
        for line in config.METRICS_FILE.read_text().splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                if entry.get("task") != "taxonomy-assessor":
                    continue
                conf = entry.get("confidence", 0.0)
                total += 1
                if conf < 0.3:
                    buckets["0.0-0.3"] += 1
                elif conf < 0.6:
                    buckets["0.3-0.6"] += 1
                elif conf < 0.8:
                    buckets["0.6-0.8"] += 1
                else:
                    buckets["0.8-1.0"] += 1
            except (json.JSONDecodeError, KeyError):
                continue

        if total == 0:
            return ProbeResult(
                probe_id="P12", name="confidence-distribution", tier=15,
                status=ProbeStatus.SKIP,
                message="No taxonomy metrics entries yet",
            )

        # High-confidence ratio
        high_conf = buckets["0.8-1.0"] / total if total > 0 else 0
        status = ProbeStatus.PASS if high_conf >= 0.60 else ProbeStatus.WARN

        return ProbeResult(
            probe_id="P12", name="confidence-distribution", tier=15,
            status=status,
            message=f"{total} assessments, {high_conf:.0%} high-confidence",
            details={"buckets": buckets, "total": total, "high_confidence_pct": round(high_conf, 3)},
        )
    except Exception as e:
        return ProbeResult(
            probe_id="P12", name="confidence-distribution", tier=15,
            status=ProbeStatus.FAIL, message=f"Failed to read metrics: {e}",
        )
