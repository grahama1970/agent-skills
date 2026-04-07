#!/usr/bin/env python3
"""Data enrichment loop for Classifier Lab.

Deterministic self-improvement loop that runs UNTIL data sufficiency is met
or all strategies are exhausted. The agent WILL NOT do this reliably on its own.

Strategies (executed in order):
  1. Search HuggingFace for matching datasets
  2. Search GitHub for labeled data repositories
  3. Mine local conversation transcripts from /episodic-archiver (ArangoDB)
  4. Abandon project if all strategies fail

Usage:
    python data_enrichment.py /path/to/project-dir [--min-per-class 100] [--dry-run]
"""
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import httpx
import typer
from loguru import logger

app = typer.Typer(no_args_is_help=True)

MEMORY_SOCKET = "/run/user/1000/embry/memory.sock"
SCILLM_URL = "http://localhost:4001/v1/chat/completions"
SCILLM_KEY = "Bearer sk-dev-proxy-123"


def load_samples(path: Path) -> list[dict]:
    """Load samples from JSONL file."""
    if not path.exists():
        return []
    samples = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            samples.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return samples


def check_sufficiency(samples: list[dict], min_per_class: int) -> dict:
    """Deterministic sufficiency check."""
    train = [s for s in samples if s.get("split", "train") == "train"]
    label_counts: Counter[str] = Counter()
    for s in train:
        labels = s.get("labels")
        if isinstance(labels, list) and labels:
            label_counts.update(labels)
        else:
            lbl = s.get("class", s.get("className", s.get("label", "")))
            if lbl:
                label_counts[str(lbl)] += 1

    num_classes = len(label_counts)
    total_train = len(train)
    required = num_classes * min_per_class
    min_count = min(label_counts.values()) if label_counts else 0
    deficit = max(0, required - total_train)

    return {
        "sufficient": total_train >= required and min_count >= min_per_class // 2,
        "num_classes": num_classes,
        "total_train": total_train,
        "required": required,
        "deficit": deficit,
        "min_per_class": min_count,
        "label_counts": dict(label_counts),
    }


def strategy_search_huggingface(project_dir: Path, meta: dict, existing_labels: set[str]) -> list[dict]:
    """Strategy 1: Search HuggingFace for datasets with matching task."""
    logger.info("Strategy 1: Searching HuggingFace for matching datasets...")
    try:
        from huggingface_hub import HfApi
        api = HfApi()

        task_name = meta.get("name", "").lower()
        modality = meta.get("modality", "text")

        queries = [
            task_name,
            f"{modality} classification",
            "intent classification" if "intent" in task_name or "routing" in task_name else task_name,
        ]

        found_datasets: list[dict[str, Any]] = []
        for q in queries:
            try:
                datasets = api.list_datasets(search=q, sort="downloads", limit=5)
                for ds in datasets:
                    found_datasets.append({"id": ds.id, "downloads": ds.downloads})
                    logger.info(f"  Found: {ds.id} ({ds.downloads:,} downloads)")
            except Exception as e:
                logger.warning(f"  HF search failed for '{q}': {e}")

        if not found_datasets:
            logger.info("  No matching datasets found on HuggingFace")
            return []

        # Try to load datasets, map labels, extract samples
        from datasets import load_dataset

        hf_token = os.environ.get("HF_TOKEN", "")
        existing_lower = {l.lower(): l for l in existing_labels}
        new_samples: list[dict] = []

        for ds_info in found_datasets[:8]:
            if new_samples:
                break  # got data, stop
            try:
                # Try multiple splits
                loaded = None
                for try_split in ["train", "validation", "test"]:
                    try:
                        loaded = load_dataset(ds_info["id"], split=try_split, token=hf_token or None, trust_remote_code=False)
                        logger.info(f"  {ds_info['id']}: loaded {try_split} ({len(loaded)} rows)")
                        break
                    except Exception:
                        continue
                if loaded is None:
                    continue

                # Find text field
                text_field = None
                for f in ["text", "sms", "sentence", "content", "reviewText", "review", "message", "input"]:
                    if f in loaded.features:
                        text_field = f
                        break

                # Find label field — prefer string fields over integers
                label_field = None
                for f in ["sentiment", "class", "category", "label", "labels"]:
                    if f in loaded.features:
                        label_field = f
                        break

                if not text_field or not label_field:
                    logger.info(f"  {ds_info['id']}: no text/label fields — {list(loaded.features.keys())}")
                    continue

                # Map labels — handle ClassLabel (int→name) and direct strings
                label_map: dict[str, str] = {}
                feat = loaded.features.get(label_field)
                if hasattr(feat, "names"):
                    for i, name in enumerate(feat.names):
                        if name.lower() in existing_lower:
                            label_map[str(i)] = existing_lower[name.lower()]
                    if label_map:
                        logger.info(f"  {ds_info['id']}: ClassLabel map: {label_map}")
                else:
                    sample_labels = {str(row[label_field]) for row in loaded.select(range(min(100, len(loaded))))}
                    for sl in sample_labels:
                        if sl.lower() in existing_lower:
                            label_map[sl] = existing_lower[sl.lower()]
                    if label_map:
                        logger.info(f"  {ds_info['id']}: string label map: {label_map}")

                if not label_map:
                    logger.info(f"  {ds_info['id']}: no label match")
                    continue

                # Extract
                count = 0
                for row in loaded:
                    text = row[text_field]
                    if not isinstance(text, str) or len(text.strip()) < 5:
                        continue
                    raw = str(row[label_field])
                    if raw in label_map:
                        new_samples.append({"text": text.strip()[:1000], "class": label_map[raw], "split": "train", "_source": ds_info["id"]})
                        count += 1
                logger.info(f"  {ds_info['id']}: extracted {count} samples")
            except Exception as e:
                logger.warning(f"  {ds_info['id']}: failed — {e}")

        logger.info(f"  HuggingFace enrichment: {len(new_samples)} new samples")
        return new_samples

    except ImportError:
        logger.warning("  huggingface_hub not installed")
        return []


def strategy_mine_transcripts(project_dir: Path, meta: dict, existing_labels: set[str]) -> list[dict]:
    """Strategy 3: Mine conversation transcripts from ArangoDB via /memory."""
    logger.info("Strategy 3: Mining conversation transcripts from ArangoDB...")
    new_samples: list[dict] = []

    try:
        # Query memory for conversation transcripts that mention skills
        transport = httpx.HTTPTransport(uds=MEMORY_SOCKET)
        client = httpx.Client(transport=transport, base_url="http://localhost")

        # Search for documents tagged with skill invocations
        for label in list(existing_labels)[:20]:  # check top 20 labels
            try:
                resp = client.post("/recall", json={
                    "query": f"skill invocation {label}",
                    "scope": "operational",
                    "k": 50,
                }, timeout=10.0)
                if resp.status_code == 200:
                    results = resp.json()
                    for doc in results.get("results", []):
                        text = doc.get("problem", doc.get("content", ""))
                        if text and len(text) > 20:
                            new_samples.append({
                                "text": text[:1000],
                                "labels": [label],
                                "split": "train",
                                "_source": "memory-transcript",
                            })
            except Exception:
                pass

        logger.info(f"  Transcript mining: {len(new_samples)} new samples")
        return new_samples

    except Exception as e:
        logger.warning(f"  Memory mining failed: {e}")
        return []


def strategy_abandon(project_dir: Path, meta: dict, attempts: list[dict]) -> None:
    """Final strategy: abandon the project with full audit trail."""
    logger.warning("All enrichment strategies exhausted. Abandoning project.")

    meta["status"] = "abandoned"
    meta["abandon_reason"] = "Data insufficient after exhausting all enrichment strategies"
    meta["enrichment_attempts"] = attempts
    (project_dir / "meta.json").write_text(json.dumps(meta, indent=2))

    logger.info(f"Project abandoned: {project_dir.name}")


@app.command()
def enrich(
    project_dir: str = typer.Argument(..., help="Path to classifier project directory"),
    min_per_class: int = typer.Option(100, help="Minimum samples per class for multi-label"),
    dry_run: bool = typer.Option(False, help="Check sufficiency without modifying data"),
    max_iterations: int = typer.Option(3, help="Max enrichment iterations"),
):
    """Run the data enrichment loop until sufficient or exhausted."""
    pdir = Path(project_dir)
    if not pdir.exists():
        logger.error(f"Project directory not found: {pdir}")
        raise typer.Exit(1)

    meta = json.loads((pdir / "meta.json").read_text()) if (pdir / "meta.json").exists() else {}
    samples = load_samples(pdir / "samples.jsonl")

    logger.info(f"Project: {pdir.name}")
    logger.info(f"Initial samples: {len(samples)}")

    # Get existing labels
    existing_labels: set[str] = set()
    for s in samples:
        labels = s.get("labels")
        if isinstance(labels, list) and labels:
            existing_labels.update(labels)
        else:
            lbl = s.get("class", s.get("className", s.get("label", "")))
            if lbl:
                existing_labels.add(str(lbl))

    # Pre-check
    status = check_sufficiency(samples, min_per_class)
    logger.info(f"Initial sufficiency: {status['sufficient']} ({status['total_train']}/{status['required']})")

    if status["sufficient"]:
        logger.info("Data already sufficient. No enrichment needed.")
        print(json.dumps({"status": "sufficient", **status}))
        return

    if dry_run:
        logger.info("Dry run — not modifying data")
        print(json.dumps({"status": "insufficient", **status}))
        return

    # ── Self-improvement loop ──────────────────────────────────────
    strategies = [
        ("huggingface", strategy_search_huggingface),
        ("transcripts", strategy_mine_transcripts),
    ]

    attempts: list[dict] = []

    for iteration in range(max_iterations):
        logger.info(f"\n{'='*60}")
        logger.info(f"Enrichment iteration {iteration + 1}/{max_iterations}")
        logger.info(f"{'='*60}")

        made_progress = False

        for strategy_name, strategy_fn in strategies:
            # Check if already tried this strategy
            if any(a["strategy"] == strategy_name and a.get("tried") for a in attempts):
                continue

            logger.info(f"\nRunning strategy: {strategy_name}")
            try:
                new_samples = strategy_fn(pdir, meta, existing_labels)
                attempt = {
                    "strategy": strategy_name,
                    "tried": True,
                    "new_samples": len(new_samples),
                    "iteration": iteration + 1,
                }
                attempts.append(attempt)

                if new_samples:
                    # Deduplicate against existing
                    existing_texts = {s.get("text", "")[:200] for s in samples}
                    unique_new = [s for s in new_samples if s.get("text", "")[:200] not in existing_texts]
                    logger.info(f"  New unique samples: {len(unique_new)} (from {len(new_samples)} total)")

                    if unique_new:
                        samples.extend(unique_new)
                        made_progress = True

                        # Re-check sufficiency
                        status = check_sufficiency(samples, min_per_class)
                        logger.info(f"  Sufficiency after {strategy_name}: {status['sufficient']} ({status['total_train']}/{status['required']})")

                        if status["sufficient"]:
                            # Write updated data and exit
                            logger.info("Data sufficient! Writing updated samples.")
                            with open(pdir / "samples.jsonl", "w") as f:
                                for s in samples:
                                    f.write(json.dumps(s) + "\n")
                            meta["status"] = "data-enriched"
                            meta["enrichment_attempts"] = attempts
                            (pdir / "meta.json").write_text(json.dumps(meta, indent=2))
                            print(json.dumps({"status": "sufficient", **status}))
                            return
            except Exception as e:
                logger.error(f"  Strategy {strategy_name} failed: {e}")
                attempts.append({"strategy": strategy_name, "tried": True, "error": str(e), "iteration": iteration + 1})

        if not made_progress:
            logger.info("No progress made this iteration. Stopping.")
            break

    # All strategies exhausted — check one more time
    status = check_sufficiency(samples, min_per_class)
    if status["sufficient"]:
        with open(pdir / "samples.jsonl", "w") as f:
            for s in samples:
                f.write(json.dumps(s) + "\n")
        meta["status"] = "data-enriched"
        meta["enrichment_attempts"] = attempts
        (pdir / "meta.json").write_text(json.dumps(meta, indent=2))
        print(json.dumps({"status": "sufficient", **status}))
    else:
        # Write whatever we found, then abandon
        if any(a.get("new_samples", 0) > 0 for a in attempts):
            with open(pdir / "samples.jsonl", "w") as f:
                for s in samples:
                    f.write(json.dumps(s) + "\n")

        strategy_abandon(pdir, meta, attempts)
        print(json.dumps({"status": "abandoned", "attempts": attempts, **status}))


if __name__ == "__main__":
    app()
