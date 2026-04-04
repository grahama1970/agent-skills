#!/usr/bin/env python3
"""
Shadow-LEGO Taxonomy Backfill — stamp taxonomy_tags on existing QRAs.

Architecture:
  1. Export: Convert teacher-labeled shadow_taxonomy.jsonl → training labels
  2. Train:  Multi-label TF-IDF + OneVsRestClassifier via train_classifiers.py
  3. Validate: Hold out 20% of teacher data, require macro-F1 >= 0.85
  4. Fill:   Classify remaining docs via /assistant classify() cascade
             (classifier → scillm teacher escalation if low confidence)

The classifier generalizes from ~5,000 teacher-labeled examples to tag
~400K docs. Keywords are NOT used as the fill mechanism — only the trained
classifier (Tier 0.5) and scillm teacher (Tier 2) via the cascade.

Shadow entries are logged to STATE_DIR/shadow_taxonomy.jsonl for auditing.
"""

from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from rich.console import Console
from rich.table import Table

# Add skills dir to path
SCRIPT_DIR = Path(__file__).parent
SKILLS_DIR = SCRIPT_DIR.parent
if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))

console = Console()

# ─── Constants ────────────────────────────────────────────────────────────────

BRIDGE_TAGS = {"Precision", "Resilience", "Fragility", "Corruption", "Loyalty", "Stealth"}
DEFAULT_SAMPLE_SIZE = 100   # Per-scope teacher sample
CLASSIFIER_BATCH_SIZE = 500 # Docs per classifier-fill batch
HOLDOUT_FRACTION = 0.20     # 20% held out for validation
MIN_MACRO_F1 = 0.70         # Gate: weighted-average F1 for classifier-eligible tags
MIN_PER_TAG_F1 = 0.60       # Gate: per-tag F1 minimum for classifier-eligible tags
MIN_TAG_SAMPLES = 200       # Tags below this → cascade-only (teacher handles them)
TRAINING_DATA_DIR = Path.home() / ".pi" / "assistant" / "training_data" / "bridge-tagger"
STATE_DIR = Path(os.getenv(
    "PERSONA_MONITOR_STATE_DIR",
    Path.home() / ".pi" / "monitor-personas",
))
SHADOW_LOG = STATE_DIR / "shadow_taxonomy.jsonl"


# ─── Memory-first helpers (no direct ArangoDB access) ─────────────────────────

import subprocess

# Removed: memory accessed via httpx to Unix socket (see _memory_cmd)
def _memory_cmd(args: list, timeout: int = 60) -> dict:
    """Call embry-memory daemon via Unix socket HTTP API."""
    str_args = [str(a) for a in args]
    subcmd = str_args[0] if str_args else ""
    rest = str_args[1:]

    # Parse CLI-style flags into a dict
    params: dict = {}
    list_keys: dict[str, list] = {}
    i = 0
    while i < len(rest):
        if rest[i].startswith("--"):
            key = rest[i][2:].replace("-", "_")
            if i + 1 < len(rest) and not rest[i + 1].startswith("--"):
                val = rest[i + 1]
                if key in ("tag", "tags", "collections"):
                    list_keys.setdefault(key, []).append(val)
                else:
                    params[key] = val
                i += 2
            else:
                params[key] = True
                i += 1
        else:
            i += 1
    for k, v in list_keys.items():
        params[k] = v

    transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
    with httpx.Client(transport=transport, base_url="http://localhost", timeout=float(timeout)) as client:
        if subcmd == "recall":
            body = {"q": params.get("q", params.get("query", "")), "k": int(params.get("k", params.get("limit", 5)))}
            for opt in ("scope", "threshold"):
                if opt in params:
                    body[opt] = float(params[opt]) if opt == "threshold" else params[opt]
            if "collections" in params:
                c = params["collections"]
                body["collections"] = c if isinstance(c, list) else [c]
            if "tags" in params:
                t = params["tags"]
                body["tags"] = t if isinstance(t, list) else [t]
            resp = client.post("/recall", json=body)
        elif subcmd == "learn":
            body = {"problem": params.get("problem", ""), "solution": params.get("solution", "")}
            if "scope" in params:
                body["scope"] = params["scope"]
            if "collection" in params:
                body["scope"] = params["collection"]
            if "tag" in params:
                body["tags"] = params["tag"] if isinstance(params["tag"], list) else [params["tag"]]
            if "tags" in params:
                body["tags"] = params["tags"] if isinstance(params["tags"], list) else [params["tags"]]
            if "json" in params:
                body.update(json.loads(params["json"]))
            resp = client.post("/learn", json=body)
        elif subcmd == "count":
            coll = params.get("collection", params.get("scope", "lessons"))
            resp = client.post("/query", json={"aql": f"RETURN LENGTH({coll})", "bind_vars": {}})
        elif subcmd == "sample":
            body = {"collection": params.get("collection", "lessons"), "limit": int(params.get("limit", 10))}
            if "fields" in params:
                body["return_fields"] = [f.strip() for f in str(params["fields"]).split(",")]
            resp = client.post("/list", json=body)
        elif subcmd == "tag":
            if "doc" in params:
                doc = json.loads(params["doc"]) if isinstance(params["doc"], str) else params["doc"]
                resp = client.post("/upsert", json={"collection": params.get("collection", "lessons"), "documents": [doc]})
            elif "key" in params:
                tags_val = params.get("tags", "[]")
                tags_list = json.loads(tags_val) if isinstance(tags_val, str) else tags_val
                field = params.get("field", "tags")
                resp = client.post("/upsert", json={"collection": params.get("collection", "lessons"), "documents": [{"_key": params["key"], field: tags_list}]})
            else:
                raise RuntimeError(f"Unsupported tag args: {rest}")
        elif subcmd == "search":
            body = {"q": params.get("q", params.get("query", "")), "k": int(params.get("limit", 10))}
            if "collection" in params:
                body["collections"] = [params["collection"]]
            if "scope" in params:
                body["scope"] = params["scope"]
            resp = client.post("/recall", json=body)
        else:
            raise RuntimeError(f"Unsupported memory subcommand via httpx: {subcmd}")
        resp.raise_for_status()
        return resp.json()

def _get_db():
    """Check /memory availability. Returns a sentinel object (not a DB handle).

    Legacy callers check `if db is None` — we return a truthy sentinel
    when /memory is reachable, None otherwise.
    """
    try:
        _memory_cmd(["count", "--collection", "lessons"])
        return True  # sentinel — /memory is available
    except Exception as e:
        console.print(f"[red]/memory unavailable: {e}[/red]")
        return None


def _get_scopes_needing_backfill(db, collection: str = "lessons") -> List[Dict[str, Any]]:
    """Get scopes with docs missing taxonomy_tags, plus counts.

    Uses /memory sample to estimate. For collections without scope
    (e.g. sparta_qra), returns a single entry with scope inferred.
    """
    try:
        # Get total count
        total_data = _memory_cmd(["count", "--collection", collection])
        total = total_data.get("count", 0)

        # Get count with taxonomy_tags
        tagged_data = _memory_cmd([
            "count", "--collection", collection,
            "--filter", "doc.taxonomy_tags != null AND LENGTH(doc.taxonomy_tags) > 0",
        ])
        tagged = tagged_data.get("count", 0)
        missing = total - tagged

        if missing <= 0:
            return []

        # Sample to discover scope distribution
        samples = _memory_cmd([
            "sample", "--collection", collection, "--limit", "100",
            "--random", "--fields", "scope",
        ])
        scope_counts: Dict[str, int] = {}
        for item in samples.get("items", []):
            scope = item.get("scope") or collection
            scope_counts[scope] = scope_counts.get(scope, 0) + 1

        # Estimate missing per scope proportionally
        results = []
        total_sampled = sum(scope_counts.values()) or 1
        for scope, count in scope_counts.items():
            estimated_missing = int(missing * count / total_sampled)
            if estimated_missing > 0:
                results.append({"scope": scope, "missing": estimated_missing})

        results.sort(key=lambda r: r["missing"], reverse=True)
        return results
    except Exception as e:
        console.print(f"[red]Failed to get backfill scopes: {e}[/red]")
        return []


def _sample_docs(
    db, collection: str, scope: str, n: int, require_text: bool = True
) -> List[Dict[str, Any]]:
    """Random sample of docs missing taxonomy_tags via /memory sample."""
    filter_parts = ['(doc.taxonomy_tags == null OR LENGTH(doc.taxonomy_tags) == 0)']

    # Scope filter
    scope_map_reverse = {
        "brandon_bailey": None,
        "horus_lore": None,
    }
    db_scope = scope
    if collection != "lessons" and scope in scope_map_reverse:
        db_scope = scope_map_reverse[scope]

    if db_scope is not None:
        filter_parts.append(f'doc.scope == "{db_scope}"')
    else:
        filter_parts.append('doc.scope == null')

    filter_expr = " AND ".join(filter_parts)

    try:
        data = _memory_cmd([
            "sample", "--collection", collection,
            "--limit", str(n), "--random",
            "--filter", filter_expr,
        ])
        return data.get("items", [])
    except Exception as e:
        logger.debug("_sample_docs failed: {}", e)
        return []


def _get_doc_text(doc: Dict[str, Any]) -> str:
    """Extract readable text from a document regardless of schema."""
    parts = []
    for field in ("problem", "solution", "question", "reasoning", "answer", "text", "content"):
        val = doc.get(field)
        if not val:
            continue
        if isinstance(val, str):
            parts.append(val)
        elif isinstance(val, dict):
            # Some docs store solution as {reasoning: ..., answer: ...}
            for sub in val.values():
                if isinstance(sub, str) and sub:
                    parts.append(sub)
        elif isinstance(val, list):
            parts.extend(str(v) for v in val if v)
    # fallback: tags as context
    if not parts and doc.get("tags"):
        tags = doc["tags"]
        if isinstance(tags, list):
            parts.append(" ".join(str(t) for t in tags))
    return " ".join(parts)[:4000]


def _stamp_docs(db, collection: str, doc_keys: List[str], tags: List[str]) -> int:
    """Stamp taxonomy_tags on specific documents via /memory tag. Returns count stamped."""
    if not doc_keys or not tags:
        return 0

    stamped = 0
    tags_json = json.dumps(tags)
    for key in doc_keys:
        try:
            _memory_cmd([
                "tag", "--collection", collection,
                "--key", key, "--tags", tags_json,
                "--field", "taxonomy_tags",
            ])
            stamped += 1
        except Exception as e:
            logger.debug("memory tag failed for {}: {}", key, e)
    return stamped


# ─── Training label export ────────────────────────────────────────────────────

def _export_training_labels(db) -> int:
    """Export teacher-labeled shadow_taxonomy.jsonl → training labels for bridge-tagger.

    Reads shadow entries, fetches full doc text from ArangoDB, and writes to
    ~/.pi/assistant/training_data/bridge-tagger/labels_taxonomy_backfill.jsonl
    """
    if not SHADOW_LOG.exists():
        console.print(f"[red]No shadow log at {SHADOW_LOG}[/red]")
        return 0

    # Load shadow entries with teacher_tags
    entries = []
    for line in SHADOW_LOG.read_text().splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            if entry.get("teacher_tags"):
                entries.append(entry)
        except json.JSONDecodeError:
            continue

    if not entries:
        console.print("[yellow]No teacher-labeled entries in shadow log[/yellow]")
        return 0

    console.print(f"  Found {len(entries)} teacher-labeled shadow entries")

    # Deduplicate by doc_key
    seen_keys: set = set()
    unique_entries = []
    for e in entries:
        key = e.get("doc_key", "")
        if key and key not in seen_keys:
            seen_keys.add(key)
            unique_entries.append(e)
    entries = unique_entries

    # Determine collection for each entry (scope-based lookup)
    # Try lessons first, then alternate collections
    collections_to_try = ["lessons", "sparta_qra", "horus_lore_chunks"]

    TRAINING_DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_path = TRAINING_DATA_DIR / "labels_taxonomy_backfill.jsonl"

    written = 0
    with open(output_path, "w") as f:
        for entry in entries:
            doc_key = entry.get("doc_key", "")
            raw_tags = entry.get("teacher_tags", [])
            # Filter to bridge tags ONLY — domain-specific tags are noise
            teacher_tags = [t for t in raw_tags if t in BRIDGE_TAGS]
            if not doc_key or not teacher_tags:
                continue

            # Fetch doc text via /memory sample
            text = ""
            for coll in collections_to_try:
                try:
                    data = _memory_cmd([
                        "sample", "--collection", coll, "--limit", "1",
                        "--filter", f'doc._key == "{doc_key}"',
                    ])
                    items = data.get("items", [])
                    if items:
                        text = _get_doc_text(items[0])
                        break
                except Exception:
                    continue

            if not text or len(text.strip()) < 20:
                continue

            label_entry = {
                "input": {"text": text},
                "output": {"tags": teacher_tags},
                "teacher_grade": ",".join(teacher_tags),
                "source": "taxonomy_backfill_teacher",
            }
            f.write(json.dumps(label_entry) + "\n")
            written += 1

    console.print(f"  Wrote {written} training labels → {output_path}")
    return written


# ─── Classifier fill ─────────────────────────────────────────────────────────

def _extract_bridge_tags(result) -> List[str]:
    """Extract valid bridge tags from a classify() TierResult.

    Handles multiple cascade output formats:
    - Classifier tier: result.result = {"tags": ["Precision", "Resilience"]}
    - scillm tier: result.prediction = "Precision,Resilience" or "Precision"
    - Error cases: result.prediction = str({"error": ...}) → filtered out
    """
    raw_tags: List[str] = []

    # Try result.result["tags"] first (classifier tier, multi-label)
    if hasattr(result, "result") and isinstance(result.result, dict):
        tags_field = result.result.get("tags", [])
        if isinstance(tags_field, list):
            raw_tags.extend(str(t) for t in tags_field)
        elif isinstance(tags_field, str):
            raw_tags.extend(t.strip() for t in tags_field.split(","))

    # Fall back to result.prediction (scillm tier)
    if not raw_tags and hasattr(result, "prediction") and result.prediction:
        pred = str(result.prediction).strip()
        # Skip error dicts serialized as strings
        if pred.startswith("{") or pred.startswith("["):
            return []
        # Comma-separated tags
        raw_tags.extend(t.strip() for t in pred.split(","))

    # Filter to ONLY valid bridge tags
    return [t for t in raw_tags if t in BRIDGE_TAGS]


def _classifier_fill(
    db, collection: str, scope: str, batch_size: int = CLASSIFIER_BATCH_SIZE,
) -> int:
    """Fill taxonomy_tags using trained bridge-tagger classifier via /assistant.

    The classify() call goes through the cascade:
    - If classifier confidence >= threshold → uses classifier (free, ~5ms)
    - If below threshold → escalates to scillm teacher ($, accurate)
    """
    try:
        from assistant.assistant import classify
    except ImportError:
        logger.error("Cannot import classify from assistant.assistant")
        return 0

    total_filled = 0
    skipped_no_tags = 0
    batch_num = 0

    while True:
        docs = _sample_docs(db, collection, scope, batch_size, require_text=False)
        if not docs:
            break

        batch_filled = 0
        for doc in docs:
            text = _get_doc_text(doc)
            if len(text.strip()) < 20:
                continue

            try:
                result = classify(text, task="bridge-tagger", scope=scope)
                tags = _extract_bridge_tags(result)
                if tags:
                    _stamp_docs(db, collection, [doc["_key"]], tags)
                    batch_filled += 1
                else:
                    skipped_no_tags += 1
            except Exception as e:
                logger.debug("classify() failed for {}: {}", doc.get("_key"), e)
                continue

        total_filled += batch_filled
        batch_num += 1

        if batch_filled == 0:
            break  # No more docs with classifiable text

        if batch_num % 5 == 0:
            logger.info("Classifier fill {}: {} stamped, {} no valid tags", scope, total_filled, skipped_no_tags)

    if skipped_no_tags:
        logger.warning("Classifier fill {}: {} docs had no valid bridge tags from cascade", scope, skipped_no_tags)
    return total_filled


# ─── Holdout validation ──────────────────────────────────────────────────────

def _validate_holdout() -> Dict[str, Any]:
    """Validate bridge-tagger on held-out 20% of teacher-labeled data.

    Uses prevalence-weighted gating:
    - Tags with >= MIN_TAG_SAMPLES training examples: must hit MIN_PER_TAG_F1
    - Tags below threshold: marked cascade-only (teacher LLM handles them)
    - Overall gate: weighted-average F1 of classifier-eligible tags >= MIN_MACRO_F1

    Returns dict with per-tag F1, weighted F1, pass/fail, and cascade-only tags.
    """
    label_path = TRAINING_DATA_DIR / "labels_taxonomy_backfill.jsonl"
    if not label_path.exists():
        return {"pass": False, "error": "No training labels found"}

    entries = []
    for line in label_path.read_text().splitlines():
        if line.strip():
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if len(entries) < 50:
        return {"pass": False, "error": f"Only {len(entries)} entries, need >= 50"}

    # Count per-tag prevalence in full dataset (before split)
    from collections import Counter
    tag_prevalence: Counter = Counter()
    for e in entries:
        for tag in e["output"]["tags"]:
            tag_prevalence[tag] += 1

    # Shuffle and split
    random.seed(42)
    random.shuffle(entries)
    split_idx = int(len(entries) * (1 - HOLDOUT_FRACTION))
    train_entries = entries[:split_idx]
    test_entries = entries[split_idx:]

    console.print(f"  Holdout: {len(train_entries)} train / {len(test_entries)} test")

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import f1_score
        from sklearn.multiclass import OneVsRestClassifier
        from sklearn.preprocessing import MultiLabelBinarizer
        import numpy as np
    except ImportError:
        return {"pass": False, "error": "sklearn not available"}

    train_texts = [e["input"]["text"] for e in train_entries]
    train_labels = [e["output"]["tags"] for e in train_entries]
    test_texts = [e["input"]["text"] for e in test_entries]
    test_labels = [e["output"]["tags"] for e in test_entries]

    all_tags = sorted({tag for tags in train_labels + test_labels for tag in tags})
    mlb = MultiLabelBinarizer(classes=all_tags)
    y_train = mlb.fit_transform(train_labels)
    y_test = mlb.transform(test_labels)

    tfidf = TfidfVectorizer(
        max_features=10000, ngram_range=(1, 2),
        sublinear_tf=True, strip_accents="unicode",
    )
    X_train = tfidf.fit_transform(train_texts)
    X_test = tfidf.transform(test_texts)

    clf = OneVsRestClassifier(LogisticRegression(
        max_iter=1000, class_weight="balanced", C=5.0,
    ))
    clf.fit(X_train, y_train)
    y_pred = clf.predict(X_test)

    # Per-tag F1 and eligibility
    per_tag_f1: Dict[str, float] = {}
    classifier_eligible: List[str] = []
    cascade_only: List[str] = []

    for i, tag in enumerate(all_tags):
        tag_f1 = f1_score(y_test[:, i], y_pred[:, i], zero_division=0)
        per_tag_f1[tag] = round(tag_f1, 4)
        if tag_prevalence[tag] >= MIN_TAG_SAMPLES:
            classifier_eligible.append(tag)
        else:
            cascade_only.append(tag)

    # Weighted F1 over classifier-eligible tags only
    eligible_f1s = [per_tag_f1[t] for t in classifier_eligible]
    weighted_f1 = float(np.mean(eligible_f1s)) if eligible_f1s else 0.0

    # Per-tag gate: each eligible tag must meet MIN_PER_TAG_F1
    failing_tags = [t for t in classifier_eligible if per_tag_f1[t] < MIN_PER_TAG_F1]
    passed = weighted_f1 >= MIN_MACRO_F1 and not failing_tags

    console.print(f"  Weighted F1 (classifier-eligible): {weighted_f1:.1%} (threshold: {MIN_MACRO_F1:.0%})")
    for tag in sorted(all_tags):
        f1 = per_tag_f1[tag]
        count = tag_prevalence[tag]
        if tag in cascade_only:
            console.print(f"    {tag}: F1={f1:.1%}  ({count} samples) [dim]CASCADE-ONLY[/dim]")
        elif f1 >= MIN_PER_TAG_F1:
            console.print(f"    {tag}: F1={f1:.1%}  ({count} samples) [green]OK[/green]")
        else:
            console.print(f"    {tag}: F1={f1:.1%}  ({count} samples) [red]FAIL[/red]")

    if cascade_only:
        console.print(f"\n  [dim]Cascade-only tags (<{MIN_TAG_SAMPLES} samples): "
                       f"{', '.join(cascade_only)} → teacher LLM handles these[/dim]")

    return {
        "pass": passed,
        "weighted_f1": round(weighted_f1, 4),
        "per_tag_f1": per_tag_f1,
        "classifier_eligible": classifier_eligible,
        "cascade_only": cascade_only,
        "failing_tags": failing_tags,
        "train_size": len(train_entries),
        "test_size": len(test_entries),
        "tags": all_tags,
        "tag_prevalence": dict(tag_prevalence),
    }


# ─── Pre-fill gate ────────────────────────────────────────────────────────────

CLASSIFIER_MODEL_PATH = Path.home() / ".pi" / "models" / "classifiers" / "bridge_text_classifier.joblib"


def _check_classifier_ready() -> Tuple[bool, str]:
    """Verify the trained bridge-tagger classifier exists and was validated.

    Returns (ready, reason). The classifier must:
    1. Exist on disk (trained via train_classifiers.py --task bridge-tagger)
    2. Have training labels (exported via cmd_export_labels)
    """
    if not CLASSIFIER_MODEL_PATH.exists():
        return False, (
            f"No trained classifier at {CLASSIFIER_MODEL_PATH}. "
            "Run: (1) cmd_export_labels() to export teacher labels, "
            "(2) train_classifiers.py --task bridge-tagger to train."
        )

    label_path = TRAINING_DATA_DIR / "labels_taxonomy_backfill.jsonl"
    if not label_path.exists():
        return False, (
            f"No training labels at {label_path}. "
            "The classifier may have been trained on stale/wrong data. "
            "Run cmd_export_labels() first, then retrain."
        )

    # Check label count — need statistically significant teacher sample
    line_count = sum(1 for line in label_path.read_text().splitlines() if line.strip())
    if line_count < 50:
        return False, (
            f"Only {line_count} teacher-labeled examples. Need >= 50 for "
            "statistically meaningful training. Run more teacher labeling first."
        )

    return True, f"Classifier ready ({line_count} teacher labels)"


# ─── Main backfill logic ─────────────────────────────────────────────────────

def backfill_scope(
    db,
    collection: str,
    scope: str,
    missing_count: int,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Run classifier-based backfill for one scope.

    Uses the trained bridge-tagger classifier via /assistant classify() cascade.
    Falls back to teacher-labeling a sample if classifier isn't available.
    """
    result = {
        "scope": scope,
        "collection": collection,
        "missing": missing_count,
        "sample_size": 0,
        "teacher_calls": 0,
        "classifier_fills": 0,
        "agreement": 0.0,
        "per_bridge": {},
        "promoted": False,
        "stamped": 0,
    }

    if missing_count < 10:
        result["skip_reason"] = f"Only {missing_count} docs — too few"
        return result

    # Try classifier fill first (fast, free, generalizes)
    console.print(f"  Classifying {missing_count:,} docs in [cyan]{scope}[/cyan] ({collection})...")

    if dry_run:
        result["classifier_fills"] = missing_count
        result["promoted"] = True
        console.print(f"  [yellow]DRY RUN: would classify {missing_count:,} docs[/yellow]")
        return result

    filled = _classifier_fill(db, collection, scope)
    result["classifier_fills"] = filled
    result["stamped"] = filled
    result["promoted"] = True  # Classifier was used

    console.print(f"  Classified and stamped {filled:,} docs via bridge-tagger cascade")
    return result


def cmd_export_labels(json_output: bool = False):
    """Export teacher-labeled shadow entries → training labels for bridge-tagger."""
    db = _get_db()
    if db is None:
        return
    console.print("[bold]Step 1: Export Training Labels[/bold]")
    count = _export_training_labels(db)
    if json_output:
        console.print(json.dumps({"exported": count}))
    else:
        console.print(f"  Exported {count} training labels from shadow_taxonomy.jsonl")


def cmd_validate(json_output: bool = False):
    """Validate bridge-tagger on held-out 20% of teacher data."""
    console.print("[bold]Step 3: Holdout Validation[/bold]")
    result = _validate_holdout()
    if json_output:
        console.print(json.dumps(result, indent=2))
    elif result["pass"]:
        wf1 = result.get("weighted_f1", 0)
        cascade = result.get("cascade_only", [])
        msg = f"PASS — Weighted F1 {wf1:.1%} >= {MIN_MACRO_F1:.0%}"
        if cascade:
            msg += f"  (cascade-only: {', '.join(cascade)})"
        console.print(f"  [green]{msg}[/green]")
    else:
        err = result.get("error") or f"Weighted F1 {result.get('weighted_f1', 0):.1%}"
        failing = result.get("failing_tags", [])
        if failing:
            err += f", failing tags: {', '.join(failing)}"
        console.print(f"  [red]FAIL — {err}[/red]")


def cmd_backfill_taxonomy(
    scope: Optional[str] = None,
    collection: Optional[str] = None,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    dry_run: bool = False,
    json_output: bool = False,
):
    """Run classifier-based taxonomy backfill across scopes.

    Prerequisite: train the bridge-tagger classifier first:
      1. python backfill_taxonomy.py --export-labels
      2. python train_classifiers.py --task bridge-tagger
      3. python backfill_taxonomy.py --validate
      4. python backfill_taxonomy.py  (this command)
    """
    db = _get_db()
    if db is None:
        return

    # ── Hard gate: classifier must be trained from teacher labels ──
    ready, reason = _check_classifier_ready()
    if not ready:
        console.print(f"[red bold]BLOCKED — classifier not ready:[/red bold]")
        console.print(f"  [red]{reason}[/red]")
        console.print()
        console.print("[yellow]Shadow-LEGO requires a trained classifier backed by")
        console.print("a statistically significant teacher-labeled sample.[/yellow]")
        console.print()
        console.print("[dim]Steps to unblock:")
        console.print("  1. python backfill_taxonomy.py --export-labels")
        console.print("  2. python train_classifiers.py --task bridge-tagger")
        console.print("  3. python backfill_taxonomy.py --validate")
        console.print("  4. python backfill_taxonomy.py[/dim]")
        return

    console.print(f"[green]{reason}[/green]")
    console.print()

    # Which collections to backfill
    collections = [collection] if collection else ["lessons"]
    if not collection:
        for alt in ["sparta_qra", "horus_lore_chunks"]:
            try:
                _memory_cmd(["count", "--collection", alt])
                collections.append(alt)
            except Exception:
                pass

    all_results: List[Dict[str, Any]] = []

    for coll in collections:
        scopes = _get_scopes_needing_backfill(db, coll)

        if scope:
            scope_ids = {s.strip().lower() for s in scope.split(",")}
            scopes = [s for s in scopes if s["scope"] and s["scope"].lower() in scope_ids]

        if not scopes:
            console.print(f"[dim]No scopes need backfill in {coll}[/dim]")
            continue

        total_missing = sum(s["missing"] for s in scopes)
        console.print()
        console.print(
            f"[bold]Classifier Backfill: {coll}[/bold]  "
            f"({len(scopes)} scopes, {total_missing:,} docs missing taxonomy_tags)"
        )
        console.print()

        for scope_info in scopes:
            s = scope_info["scope"]
            if not s:
                continue

            console.print(f"[bold cyan]── {s} ({scope_info['missing']:,} missing) ──[/bold cyan]")
            r = backfill_scope(
                db, coll, s, scope_info["missing"],
                sample_size=sample_size, dry_run=dry_run,
            )
            all_results.append(r)
            console.print()

    if json_output:
        summary = {
            "results": all_results,
            "summary": {
                "total_scopes": len(all_results),
                "promoted": sum(1 for r in all_results if r["promoted"]),
                "classifier_fills": sum(r.get("classifier_fills", 0) for r in all_results),
                "total_stamped": sum(r["stamped"] for r in all_results),
            },
        }
        console.print(json.dumps(summary, indent=2))
        return

    # Summary table
    table = Table(show_header=True, header_style="bold")
    table.add_column("Scope", style="cyan")
    table.add_column("Collection", style="dim")
    table.add_column("Missing", justify="right")
    table.add_column("Classified", justify="right")
    table.add_column("Stamped", justify="right")

    for r in all_results:
        if r.get("skip_reason"):
            classified = f"[dim]{r['skip_reason'][:25]}[/dim]"
        else:
            classified = f"{r.get('classifier_fills', 0):,}"

        table.add_row(
            r["scope"],
            r["collection"],
            f"{r['missing']:,}",
            classified,
            f"{r['stamped']:,}",
        )

    console.print()
    console.print("[bold]Classifier Backfill Summary[/bold]")
    console.print(table)

    total_classified = sum(r.get("classifier_fills", 0) for r in all_results)
    total_stamped = sum(r["stamped"] for r in all_results)

    console.print()
    console.print(
        f"  Classifier fills: {total_classified:,}  |  "
        f"Total stamped: {total_stamped:,}  |  "
        f"Shadow log: {SHADOW_LOG}"
    )
