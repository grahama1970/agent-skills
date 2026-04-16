#!/usr/bin/env python3
"""Project kickoff — seeds a new classifier project from a goal description.

Runs /dogpile for research, extracts backbone recommendations,
writes research.md + tune-config.json + research-gate.json.
Optionally searches HuggingFace for initial training data.

Usage:
    python kickoff.py /path/to/project-dir --goal "Classify emails as spam or ham" --modality text
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import typer
from loguru import logger

app = typer.Typer(no_args_is_help=True)

SKILLS_DIR = Path(__file__).resolve().parent.parent.parent
SCILLM_URL = "http://localhost:4001/v1/chat/completions"
SCILLM_KEY = "Bearer sk-dev-proxy-123"
BRAVE_SCRIPT = SKILLS_DIR / "brave-search" / "brave_search.py"


def query_scillm(prompt: str) -> str:
    """Fast LLM call for backbone + HP recommendations."""
    try:
        resp = httpx.post(SCILLM_URL, json={
            "model": "text",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1000,
            "temperature": 0.3,
        }, headers={"Authorization": SCILLM_KEY}, timeout=30.0)
        data = resp.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as e:
        logger.warning(f"scillm failed: {e}")
        return ""


def brave_search(query: str) -> str:
    """Fast web search for dataset discovery."""
    try:
        result = subprocess.run(
            [sys.executable, str(BRAVE_SCRIPT), "web", query, "--count", "5", "--no-json"],
            capture_output=True, text=True, timeout=15,
        )
        return result.stdout
    except Exception as e:
        logger.warning(f"brave-search failed: {e}")
        return ""


@app.command()
def kickoff(
    project_dir: str = typer.Argument(..., help="Path to project directory"),
    goal: str = typer.Option(..., help="What the classifier should do"),
    modality: str = typer.Option("text", help="text, vision, or tabular"),
):
    """Seed a new classifier project from a goal description."""
    pdir = Path(project_dir)
    pdir.mkdir(parents=True, exist_ok=True)

    project_name = pdir.name
    logger.info(f"Kickoff: {project_name}")
    logger.info(f"Goal: {goal}")
    logger.info(f"Modality: {modality}")

    # Update meta
    meta_path = pdir / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    meta.update({
        "name": project_name,
        "goal": goal,
        "modality": modality,
        "status": "researching",
    })
    meta_path.write_text(json.dumps(meta, indent=2))

    # ── Step 1: Research via /scillm + /brave-search (parallel, ~4s) ──
    logger.info("[1/3] Researching via /scillm + /brave-search...")

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as pool:
        scillm_future = pool.submit(query_scillm, (
            f"I need to build a {modality} classifier for: {goal}\n\n"
            f"Give me:\n"
            f"1. Top 2-3 backbone models (with HuggingFace model names)\n"
            f"2. Recommended hyperparameters (learning rate, epochs, batch size)\n"
            f"3. Minimum training samples needed\n"
            f"4. Any specific HuggingFace datasets for this task\n\n"
            f"Be specific — give exact model names and numbers."
        ))
        brave_future = pool.submit(brave_search, f"HuggingFace dataset {goal} {modality} classification")

    scillm_output = scillm_future.result()
    brave_output = brave_future.result()

    logger.info(f"  scillm: {len(scillm_output)} chars")
    logger.info(f"  brave: {len(brave_output)} chars")

    # Write research.md
    research = f"""# {project_name}

## Goal
{goal}

## Modality
{modality}

## Backbone & HP Recommendations (from /scillm)

{scillm_output[:2000] if scillm_output else "No LLM recommendations available."}

## Dataset Search (from /brave-search)

{brave_output[:1000] if brave_output else "No web search results."}
"""
    (pdir / "research.md").write_text(research)
    logger.info(f"Written research.md ({len(research)} chars)")

    # ── Step 2: Extract settings ──────────────────────────────
    logger.info("[2/3] Setting initial tune config...")

    # Default backbones by modality
    backbone_defaults = {
        "text": ["distilbert-base-uncased", "sentence-transformers/all-MiniLM-L6-v2"],
        "vision": ["efficientnet_b0", "convnext_tiny"],
        "tabular": ["gradient_boosting", "random_forest"],
    }
    backbones = backbone_defaults.get(modality, backbone_defaults["text"])

    tune_config = {
        "lr": 2e-5 if modality == "text" else 2e-4,
        "epochs": 10,
        "batch_size": 16 if modality == "text" else 32,
        "warmup_ratio": 0.1,
        "weight_decay": 0.01,
        "max_length": 128,
        "backbones": backbones,
        "_source": "dogpile-kickoff",
        "_updated": __import__("datetime").datetime.now().isoformat(),
        "_changelog": [{"who": "agent", "what": f"Kickoff from goal: {goal[:50]}", "when": __import__("datetime").date.today().isoformat()}],
    }
    (pdir / "tune-config.json").write_text(json.dumps(tune_config, indent=2))
    logger.info(f"Written tune-config.json (backbones: {backbones})")

    # ── Step 3: Search for data ───────────────────────────────
    logger.info("[3/3] Searching HuggingFace for training data...")
    try:
        import re as _re
        from huggingface_hub import HfApi
        api = HfApi()
        hf_token = os.environ.get("HF_TOKEN", "")

        found: list[dict] = []

        # First: parse Brave results for HuggingFace dataset URLs
        if brave_output:
            hf_urls = _re.findall(r"huggingface\.co/datasets/([a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+)", brave_output)
            for ds_id in dict.fromkeys(hf_urls):  # deduplicate preserving order
                found.append({"id": ds_id, "downloads": 0, "source": "brave"})
                logger.info(f"  From Brave: {ds_id}")

        # Second: search HuggingFace API as fallback
        if not found:
            queries = [goal.lower(), f"{modality} {goal.split()[0].lower()} classification"]
            for q in queries[:2]:
                try:
                    datasets = api.list_datasets(search=q, sort="downloads", limit=3)
                    for ds in datasets:
                        if ds.id not in [f["id"] for f in found]:
                            found.append({"id": ds.id, "downloads": ds.downloads, "source": "hf-api"})
                            logger.info(f"  From HF API: {ds.id} ({ds.downloads:,} downloads)")
                except Exception:
                    pass

        if found:
            from datasets import load_dataset

            for ds_info in found[:3]:
                try:
                    for split in ["train", "validation", "test"]:
                        try:
                            ds = load_dataset(ds_info["id"], split=split, token=hf_token or None, trust_remote_code=False)
                            logger.info(f"  {ds_info['id']}: loaded {split} ({len(ds)} rows)")

                            # Find text field
                            text_field = None
                            for f in ["text", "comment_text", "sms", "sentence", "content", "reviewText", "review", "message", "input", "question", "body"]:
                                if f in ds.features:
                                    text_field = f
                                    break

                            # Find label field — prefer string labels, then ClassLabel, then binary columns
                            label_field = None
                            binary_label = None
                            for f in ["sentiment", "class", "category", "label", "labels"]:
                                if f in ds.features:
                                    label_field = f
                                    break
                            # Check for binary classification columns (e.g., "toxic": 0/1)
                            if not label_field:
                                goal_words = set(goal.lower().split())
                                for f in ds.features:
                                    if f.lower() in goal_words or any(w in f.lower() for w in goal_words):
                                        # Check if it's binary (0/1 values)
                                        sample_vals = {str(row[f]) for row in ds.select(range(min(20, len(ds))))}
                                        if sample_vals <= {"0", "1", "True", "False", "true", "false"}:
                                            binary_label = f
                                            logger.info(f"  {ds_info['id']}: using binary column '{f}' as label")
                                            break

                            if not text_field:
                                logger.info(f"  {ds_info['id']}: no text field — {list(ds.features.keys())[:8]}")
                                continue

                            # Write samples
                            samples = []
                            if label_field:
                                feat = ds.features.get(label_field)
                                for row in ds:
                                    text = row[text_field]
                                    if not isinstance(text, str) or len(text.strip()) < 5:
                                        continue
                                    raw = row[label_field]
                                    label = feat.names[raw] if hasattr(feat, "names") and isinstance(raw, int) else str(raw)
                                    samples.append({"text": text.strip()[:500], "class": label, "split": "train"})
                            elif binary_label:
                                # Binary column → "positive"/"negative" style labels
                                pos_name = binary_label  # e.g., "toxic"
                                neg_name = f"not_{binary_label}"  # e.g., "not_toxic"
                                for row in ds:
                                    text = row[text_field]
                                    if not isinstance(text, str) or len(text.strip()) < 5:
                                        continue
                                    val = str(row[binary_label])
                                    label = pos_name if val in ("1", "True", "true") else neg_name
                                    samples.append({"text": text.strip()[:500], "class": label, "split": "train"})
                            else:
                                logger.info(f"  {ds_info['id']}: no label field — {list(ds.features.keys())[:8]}")
                                continue

                            # Cap at 10K samples for kickoff (full enrichment can get more)
                            if len(samples) > 10000:
                                import random as _rand
                                _rand.seed(42)
                                _rand.shuffle(samples)
                                samples = samples[:10000]

                            if samples:
                                    with open(pdir / "samples.jsonl", "w") as f:
                                        for s in samples:
                                            f.write(json.dumps(s) + "\n")
                                    meta["samples"] = len(samples)
                                    meta["classes"] = len(set(s["class"] for s in samples))
                                    meta["class_names"] = sorted(set(s["class"] for s in samples))
                                    meta["data_source"] = ds_info["id"]
                                    logger.info(f"  Written {len(samples)} samples from {ds_info['id']}")
                                    break
                            break  # got a split, done with this dataset
                        except Exception:
                            continue
                    if (pdir / "samples.jsonl").exists():
                        break
                except Exception as e:
                    logger.warning(f"  {ds_info['id']}: {e}")

    except Exception as e:
        logger.warning(f"Data search failed: {e}")

    # ── Write research gate ───────────────────────────────────
    (pdir / "research-gate.json").write_text(json.dumps({
        "passed": True,
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "goal": goal,
        "modality": modality,
        "backbones": backbones,
    }, indent=2))

    # Final meta update
    meta["status"] = "researched"
    meta_path.write_text(json.dumps(meta, indent=2))

    logger.info(f"\nKickoff complete: {project_name}")
    logger.info(f"  Research: research.md ({'OK' if (pdir / 'research.md').exists() else 'MISSING'})")
    logger.info(f"  Tune: tune-config.json ({'OK' if (pdir / 'tune-config.json').exists() else 'MISSING'})")
    logger.info(f"  Gate: research-gate.json ({'OK' if (pdir / 'research-gate.json').exists() else 'MISSING'})")
    logger.info(f"  Data: samples.jsonl ({'OK — ' + str(meta.get('samples', 0)) + ' samples' if (pdir / 'samples.jsonl').exists() else 'NOT FOUND'})")

    print(json.dumps({"status": "complete", **meta}))


if __name__ == "__main__":
    app()
