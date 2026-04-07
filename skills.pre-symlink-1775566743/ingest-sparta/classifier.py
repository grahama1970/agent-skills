#!/usr/bin/env python3
"""Dynamic content classifier for SPARTA URL downloads.

Sensai-Cascade / KARL pattern:
  1. scillm teacher (Gemini Flash cascade) labels real downloaded HTML
  2. sklearn student (TF-IDF + LogReg) learns from those labels
  3. /assistant shadows with classifier + GPT during bulk pipeline runs

Bootstrap trains the classifier. Once trained, classification is <1ms/doc.
"""
from __future__ import annotations

import json
import os
import random
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SCILLM_BASE = os.getenv("SCILLM_BASE", "http://localhost:4001")
SCILLM_KEY = os.getenv("SCILLM_KEY", "sk-dev-proxy-123")
TRAINING_DATA_DIR = Path.home() / ".pi" / "assistant" / "training_data"
CLASSIFIER_MODEL_PATH = Path.home() / ".pi" / "models" / "classifiers"
CLASSIFIER_FILE = CLASSIFIER_MODEL_PATH / "url_content_quality_classifier.joblib"
SKILLS_DIR = Path(__file__).parent.parent
ASSISTANT_DIR = SKILLS_DIR / "assistant"

MAX_TEXT_LENGTH = 200_000
_SENTENCE_RE = re.compile(r"[.!?](?:\s|$)")
# Structured definition patterns: key-value pairs, numbered items, colons, bullets
_DEFINITION_RE = re.compile(
    r"(?:"
    r"^\s*(?:ID|Name|Description|Type|Category|Control|Tactic|Technique|Mitigation|Platform|Domain)"
    r"\s*[:=]"
    r"|^\s*(?:\d+\.|[-•*])\s+\S"
    r"|^\s*\|[^|]+\|"
    r")",
    re.MULTILINE | re.IGNORECASE,
)

_cached_classifier = None


# ---------------------------------------------------------------------------
# Classify (fast path — uses trained model)
# ---------------------------------------------------------------------------

def load_classifier():
    """Load trained sklearn classifier, or None if not yet bootstrapped."""
    global _cached_classifier
    if _cached_classifier is not None:
        return _cached_classifier
    if not CLASSIFIER_FILE.exists():
        return None
    try:
        import joblib
        _cached_classifier = joblib.load(CLASSIFIER_FILE)
        logger.info("Loaded content classifier from {}", CLASSIFIER_FILE)
        return _cached_classifier
    except Exception as e:
        logger.warning("Failed to load classifier: {}", e)
        return None


def classify_content(text: str) -> tuple[str, float]:
    """Classify text as 'content' or 'junk'.

    Returns (label, confidence). Falls back to heuristic if no model.
    """
    clf = load_classifier()
    if clf is None:
        # Heuristic fallback — lenient for structured definitions
        sents = len(_SENTENCE_RE.findall(text))
        has_structure = bool(_DEFINITION_RE.search(text))
        if sents >= 3 and len(text) >= 200:
            return ("content", 0.5)
        if has_structure and len(text) >= 80:
            return ("content", 0.45)
        return ("junk", 0.5)

    try:
        proba = clf.predict_proba([text])[0]
        classes = list(clf.classes_)
        idx = proba.argmax()
        return (classes[idx], float(proba[idx]))
    except Exception:
        return ("content", 0.5)


# ---------------------------------------------------------------------------
# scillm teacher labeling
# ---------------------------------------------------------------------------

def _scillm_label(text: str, max_input: int = 4000) -> str:
    """Ask scillm (Gemini Flash cascade) to label text as content or junk."""
    truncated = text[:max_input]
    resp = httpx.post(
        f"{SCILLM_BASE}/v1/chat/completions",
        headers={"Authorization": f"Bearer {SCILLM_KEY}"},
        json={
            "model": "text",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a content quality classifier. Given text extracted "
                        "from a web page about cybersecurity, space systems, or "
                        "defense frameworks, classify it as exactly one of:\n"
                        "- content: Meaningful technical content including sentences, "
                        "descriptions, structured data, or SHORT DEFINITION PAGES "
                        "about security controls, techniques, mitigations, or "
                        "frameworks. A page with just an ID, name, description, "
                        "and metadata fields IS valid content even if very short.\n"
                        "- junk: Navigation fragments, cookie notices, login forms, "
                        "error pages, empty boilerplate, meta refresh redirects, "
                        "or content too garbled to be useful.\n\n"
                        "Respond with ONLY the word 'content' or 'junk'."
                    ),
                },
                {"role": "user", "content": truncated},
            ],
            "max_tokens": 8,
            "temperature": 0,
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"].strip().lower()
    return "content" if "content" in raw else "junk"


# ---------------------------------------------------------------------------
# Bootstrap: sample → label → train
# ---------------------------------------------------------------------------

def bootstrap_classifier(
    get_techniques_fn,
    bs4_strip_fn,
    sample_size: int = 200,
    workers: int = 5,
) -> dict[str, Any]:
    """Bootstrap the content classifier from actual downloaded HTML files.

    Phase 0 of the Sensai-Cascade / KARL pattern:
      Sample HTML files → BS4 strip → scillm labels → JSONL → train sklearn.

    Args:
        get_techniques_fn: Callable returning list of technique dicts with URLs.
        bs4_strip_fn: Callable to strip HTML boilerplate.
        sample_size: Number of files to sample for labeling.
        workers: Concurrent scillm labeling workers.
    """
    logger.info("Phase 0: Bootstrap content classifier from downloaded HTML")

    techniques = get_techniques_fn()
    all_files: list[dict] = []
    for tech in techniques:
        for u in tech.get("urls", []):
            fp = u.get("file_path")
            if fp and Path(fp).exists() and Path(fp).stat().st_size > 0:
                all_files.append({
                    "file_path": fp,
                    "control_id": tech["control_id"],
                    "source_framework": tech.get("source_framework", ""),
                })

    logger.info("Found {} files with content", len(all_files))
    if len(all_files) < 20:
        return {"ok": False, "error": "too_few_files", "count": len(all_files)}

    # Stratified sample by source_framework
    sampled = _stratified_sample(all_files, sample_size)
    logger.info("Sampled {} files", len(sampled))

    # BS4 strip + scillm label (concurrent)
    labeled, errors = _label_samples(sampled, bs4_strip_fn, workers)
    content_count = sum(1 for l in labeled if l["label"] == "content")
    junk_count = sum(1 for l in labeled if l["label"] == "junk")
    logger.info(
        "Labeled {}: {} content, {} junk, {} errors",
        len(labeled), content_count, junk_count, errors,
    )

    if len(labeled) < 20:
        return {"ok": False, "error": "too_few_labeled", "count": len(labeled)}

    # Write JSONL training data for /assistant
    jsonl_path = _write_training_data(labeled)
    logger.info("Wrote {} labels to {}", len(labeled), jsonl_path)

    # Train sklearn classifier via /assistant
    _train_via_assistant()

    # Reset cached classifier
    global _cached_classifier
    _cached_classifier = None

    return {
        "ok": True,
        "samples": len(sampled),
        "labeled": len(labeled),
        "content": content_count,
        "junk": junk_count,
        "errors": errors,
        "training_data": str(jsonl_path),
        "model_path": str(CLASSIFIER_FILE),
    }


def _stratified_sample(all_files: list[dict], sample_size: int) -> list[dict]:
    """Stratified sample by source_framework."""
    by_framework: dict[str, list] = {}
    for f in all_files:
        fw = f.get("source_framework", "unknown")
        by_framework.setdefault(fw, []).append(f)

    sampled: list[dict] = []
    per_fw = max(1, sample_size // max(len(by_framework), 1))
    for fw, files in by_framework.items():
        n = min(per_fw, len(files))
        sampled.extend(random.sample(files, n))

    remaining = sample_size - len(sampled)
    if remaining > 0:
        pool = [f for f in all_files if f not in sampled]
        sampled.extend(random.sample(pool, min(remaining, len(pool))))

    return sampled


def _label_samples(
    sampled: list[dict],
    bs4_strip_fn,
    workers: int,
) -> tuple[list[dict], int]:
    """Label samples via scillm with concurrent workers."""
    labeled: list[dict] = []
    errors = 0

    def _label_one(entry: dict) -> dict | None:
        try:
            raw = Path(entry["file_path"]).read_text(errors="ignore")
            if len(raw) > MAX_TEXT_LENGTH:
                raw = raw[:MAX_TEXT_LENGTH]
            text = bs4_strip_fn(raw) if "<html" in raw[:500].lower() else raw.strip()
            if len(text) < 10:
                return {"text": text, "label": "junk", "source": "heuristic"}
            label = _scillm_label(text)
            return {
                "text": text,
                "label": label,
                "source": "scillm",
                "file_path": entry["file_path"],
                "control_id": entry["control_id"],
            }
        except Exception as e:
            logger.debug("Label error: {}", str(e)[:100])
            return None

    logger.info("Labeling {} samples via scillm ({} workers)...", len(sampled), workers)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_label_one, s): s for s in sampled}
        for fut in as_completed(futures):
            result = fut.result()
            if result:
                labeled.append(result)
            else:
                errors += 1

    return labeled, errors


def _write_training_data(labeled: list[dict]) -> Path:
    """Write JSONL training data for /assistant."""
    task_dir = TRAINING_DATA_DIR / "url-content-quality"
    task_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = task_dir / "labels_bootstrap.jsonl"
    with jsonl_path.open("w") as f:
        for entry in labeled:
            record = {
                "input": {"text": entry["text"][:4000]},
                "output": {"prediction": entry["label"]},
                "teacher_grade": entry["label"],
                "source": entry.get("source", "scillm"),
            }
            f.write(json.dumps(record) + "\n")
    return jsonl_path


def _train_via_assistant() -> None:
    """Train sklearn classifier via /assistant train_classifiers.py."""
    train_script = ASSISTANT_DIR / "train_classifiers.py"
    if not train_script.exists():
        logger.warning("/assistant train_classifiers.py not found")
        return

    logger.info("Training sklearn classifier via /assistant...")
    try:
        result = subprocess.run(
            [sys.executable, str(train_script), "--task", "url-content-quality"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(ASSISTANT_DIR),
        )
        if result.returncode == 0:
            logger.info("Classifier trained successfully")
        else:
            logger.warning("Train returned {}: {}", result.returncode, result.stderr[:200])
    except Exception as e:
        logger.error("Training failed: {}", e)
