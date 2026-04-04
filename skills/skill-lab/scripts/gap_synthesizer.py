#!/usr/bin/env python3
"""LLM-powered gap synthesis — reason about missing skills and generate code.

When the transition matrix detects a zero-probability gap in a predicted chain,
this module uses LLM reasoning (/scillm) to:

1. Determine WHAT the missing skill should do (semantic role)
2. Define its provides/composes interface (valence shell)
3. Generate the composition manifest (for scaffolder.py)
4. Optionally generate the implementation code (scripts/)

This follows the 3-iteration label generation approach:
- Iteration 1: LLM reasons about the gap (teacher labels)
- Iteration 2: Once enough gap-fills accumulate, train a classifier
  to predict skill roles without LLM calls
- Iteration 3: Fine-tune a small GPT (QLoRA) for fast gap reasoning

Usage:
    python gap_synthesizer.py reason "extract tables" --chain extractor ? memory
    python gap_synthesizer.py synthesize "extract tables" --chain extractor ? memory
    python gap_synthesizer.py status
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from loguru import logger

SCRIPTS_DIR = Path(__file__).parent
STATE_DIR = SCRIPTS_DIR.parent / "state"
SKILLS_DIR = SCRIPTS_DIR.parent.parent

_PROMPT_DIR = SKILLS_DIR / "prompt-lab" / "prompts"


def _load_prompt(name: str) -> str:
    path = _PROMPT_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt '{name}' not found at {path}")
    return path.read_text().strip()

GAP_LABELS_FILE = STATE_DIR / "gap_labels.jsonl"
GAP_CLASSIFIER_MODEL = STATE_DIR / "gap_classifier.pkl"
GAP_GPT_MODEL = STATE_DIR / "gap_gpt.gguf"
GAP_SYNTHESIS_LOG = STATE_DIR / "gap_synthesis_log.jsonl"

# Minimum labels before training the gap classifier
MIN_LABELS_FOR_CLASSIFIER = 30
MIN_LABELS_FOR_GPT = 100

sys.path.insert(0, str(SCRIPTS_DIR))


def _call_scillm(prompt: str, max_tokens: int = 1500) -> str | None:
    """Call /scillm for LLM reasoning about a gap."""
    scillm_dir = SKILLS_DIR / "scillm"
    if not scillm_dir.exists():
        return None

    try:
        result = subprocess.run(
            [str(scillm_dir / "run.sh"), "complete", "--prompt", prompt,
             "--max-tokens", str(max_tokens), "--json"],
            capture_output=True, text=True, timeout=60,
            cwd=str(scillm_dir),
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                return data.get("text", result.stdout)
            except json.JSONDecodeError:
                return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def _load_gap_labels() -> list[dict]:
    """Load accumulated gap reasoning labels."""
    if not GAP_LABELS_FILE.exists():
        return []
    labels = []
    for line in GAP_LABELS_FILE.read_text().strip().split("\n"):
        if line.strip():
            try:
                labels.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return labels


def _save_gap_label(label: dict) -> None:
    """Append a gap label for future training."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(GAP_LABELS_FILE, "a") as f:
        f.write(json.dumps(label) + "\n")


def reason_about_gap(
    task: str,
    chain: list[str],
    gap_position: int | None = None,
    from_skill: str | None = None,
    to_skill: str | None = None,
) -> dict:
    """Use LLM reasoning to determine what a missing skill should do.

    The 3-tier cascade:
    1. Try gap classifier (fast, if trained)
    2. Try gap GPT (medium, if fine-tuned)
    3. Fall back to /scillm teacher (slow, always available)

    Returns:
        {
            "name": "suggested-skill-name",
            "description": "What the skill does",
            "provides": ["capability-a", "capability-b"],
            "composes": ["skill-x", "skill-y"],
            "role": "What role it fills in the chain",
            "confidence": float,
            "source": "classifier" | "gpt" | "scillm" | "heuristic",
        }
    """
    # Tier 1: Try classifier (if trained)
    if GAP_CLASSIFIER_MODEL.exists():
        result = _tier_classifier(task, chain, gap_position, from_skill, to_skill)
        if result and result.get("confidence", 0) > 0.7:
            result["source"] = "classifier"
            _save_gap_label({**result, "task": task, "chain": chain,
                           "timestamp": datetime.now(timezone.utc).isoformat()})
            return result

    # Tier 2: Try small GPT (if fine-tuned)
    if GAP_GPT_MODEL.exists():
        result = _tier_gpt(task, chain, gap_position, from_skill, to_skill)
        if result and result.get("confidence", 0) > 0.6:
            result["source"] = "gpt"
            _save_gap_label({**result, "task": task, "chain": chain,
                           "timestamp": datetime.now(timezone.utc).isoformat()})
            return result

    # Tier 3: /scillm teacher (always available)
    result = _tier_scillm(task, chain, gap_position, from_skill, to_skill)
    if result:
        result["source"] = "scillm"
        _save_gap_label({**result, "task": task, "chain": chain,
                       "timestamp": datetime.now(timezone.utc).isoformat()})
        return result

    # Fallback: heuristic reasoning
    return _tier_heuristic(task, chain, gap_position, from_skill, to_skill)


def _tier_classifier(task, chain, gap_position, from_skill, to_skill) -> dict | None:
    """Tier 1: Fast classifier prediction for gap role."""
    try:
        import pickle
        import numpy as np
        with open(GAP_CLASSIFIER_MODEL, "rb") as f:
            model = pickle.load(f)

        features = _extract_gap_features(task, chain, gap_position, from_skill, to_skill)
        prediction = model.predict([features])[0]
        proba = model.predict_proba([features]).max()

        return json.loads(prediction) if isinstance(prediction, str) else {
            "name": prediction,
            "confidence": float(proba),
        }
    except Exception:
        return None


def _tier_gpt(task, chain, gap_position, from_skill, to_skill) -> dict | None:
    """Tier 2: Small GPT for gap reasoning."""
    raise NotImplementedError("Tier 2 GPT gap reasoning not yet implemented — needs sufficient labeled data")


def _tier_scillm(task, chain, gap_position, from_skill, to_skill) -> dict | None:
    """Tier 3: Full LLM reasoning about the gap via /scillm."""
    chain_str = " → ".join(chain)
    if gap_position is not None:
        chain_display = list(chain)
        chain_display.insert(gap_position, "???")
        chain_str = " → ".join(chain_display)

    context_parts = [f"Task: {task}", f"Skill chain: {chain_str}"]
    if from_skill:
        context_parts.append(f"Gap is between: {from_skill} and {to_skill or '(end)'}")

    # Load known skills for context
    try:
        from scan_soup import scan_soup
        graph = scan_soup(SKILLS_DIR)
        known_skills = list(graph.get("skills", {}).keys())[:30]
        known_caps = list(graph.get("capabilities", {}).keys())[:20]
        context_parts.append(f"Known skills: {', '.join(known_skills)}")
        context_parts.append(f"Known capabilities: {', '.join(known_caps)}")
    except Exception as e:
        logger.debug("value lookup failed: {}", e)

    context = "\n".join(context_parts)

    prompt = _load_prompt("skill_lab_gap_reasoning_v1").format(
        context=context,
        from_skill=from_skill or chain[0] if chain else "start",
        to_skill=to_skill or chain[-1] if chain else "end",
    )

    response = _call_scillm(prompt)
    if not response:
        return None

    # Parse JSON from response
    try:
        # Try to extract JSON from response
        text = response.strip()
        if "```" in text:
            # Extract from code block
            start = text.index("{")
            end = text.rindex("}") + 1
            text = text[start:end]
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def _tier_heuristic(task, chain, gap_position, from_skill, to_skill) -> dict:
    """Fallback heuristic reasoning about gaps."""
    # Common gap patterns
    COMMON_GAPS = {
        ("extractor", "memory"): {
            "name": "review-pdf",
            "description": "Quality gate between extraction and memory ingestion",
            "provides": ["pdf-extraction-review", "quality-gate"],
            "composes": ["extractor", "memory"],
            "role": "Validates extraction quality before ingestion",
        },
        ("dogpile", "memory"): {
            "name": "extractor",
            "description": "Extract and learn research findings to memory",
            "provides": ["document-ingestion", "content-extraction"],
            "composes": ["memory"],
            "role": "Structures raw research into memory-ready format",
        },
        ("arxiv", "memory"): {
            "name": "extractor",
            "description": "Extract and learn paper content to memory",
            "provides": ["document-ingestion", "content-extraction"],
            "composes": ["memory"],
            "role": "Bridges paper content to memory-ready format",
        },
        ("hack", "memory"): {
            "name": "security-report",
            "description": "Structure security findings for memory storage",
            "provides": ["security-reporting"],
            "composes": ["memory"],
            "role": "Formats vulnerability findings as structured lessons",
        },
    }

    key = (from_skill, to_skill) if from_skill and to_skill else None
    if key and key in COMMON_GAPS:
        result = COMMON_GAPS[key].copy()
        result["confidence"] = 0.6
        result["source"] = "heuristic"
        return result

    # Generic gap
    return {
        "name": f"bridge-{from_skill or 'start'}-{to_skill or 'end'}",
        "description": f"Bridge skill between {from_skill} and {to_skill}",
        "provides": ["data-transformation"],
        "composes": [s for s in [from_skill, to_skill] if s],
        "role": f"Transform output of {from_skill} for input to {to_skill}",
        "confidence": 0.3,
        "source": "heuristic",
    }


def _extract_gap_features(task, chain, gap_position, from_skill, to_skill) -> list[float]:
    """Extract numerical features for the gap classifier."""
    features = [
        len(chain),
        gap_position or 0,
        len(task.split()),
        hash(from_skill or "") % 100 / 100,
        hash(to_skill or "") % 100 / 100,
    ]
    return features


def synthesize_skill(
    task: str,
    chain: list[str],
    gap_position: int | None = None,
    from_skill: str | None = None,
    to_skill: str | None = None,
    dry_run: bool = True,
) -> dict:
    """Full synthesis: reason about gap → generate manifest → scaffold skill.

    Args:
        task: What the user is trying to do
        chain: The predicted skill chain with the gap
        gap_position: Where in the chain the gap is
        from_skill: Skill before the gap
        to_skill: Skill after the gap
        dry_run: If True, don't write files

    Returns:
        {
            "gap_analysis": {...},  # From reason_about_gap
            "manifest": {...},      # Composition manifest
            "scaffolded": bool,     # Whether files were written
            "output_dir": str,      # Where the skill was created
        }
    """
    # Step 1: Reason about what the missing skill should do
    gap_analysis = reason_about_gap(task, chain, gap_position, from_skill, to_skill)

    # Step 2: Check if this skill already exists
    skill_name = gap_analysis.get("name", "unknown")
    existing_dir = SKILLS_DIR / skill_name
    is_existing = gap_analysis.get("existing", False) or existing_dir.exists()
    if is_existing:
        return {
            "gap_analysis": gap_analysis,
            "manifest": None,
            "scaffolded": False,
            "existing": True,
            "skill_name": skill_name,
            "reason": f"Existing skill '{skill_name}' fills this gap — no new skill needed",
            "suggestion": "The transition matrix may need updating — "
                         "this skill exists but isn't well-connected in the graph. "
                         "Consider adding a bond between the adjacent skills.",
        }

    # Step 3: Build composition manifest
    from gap_detector import detect_gaps
    try:
        from scan_soup import scan_soup
        graph = scan_soup(SKILLS_DIR)
    except Exception:
        graph = {"capabilities": {}, "skills": {}}

    manifest = {
        "schema_version": "1.0",
        "name": skill_name,
        "task": gap_analysis.get("description", task),
        "generated_by": "gap_synthesizer",
        "gap_context": {
            "original_task": task,
            "chain": chain,
            "gap_position": gap_position,
            "from_skill": from_skill,
            "to_skill": to_skill,
        },
        "composition": {
            "have": [],
            "create": [{
                "capability": cap,
                "description": f"Provided by {skill_name}",
                "lab": None,
            } for cap in gap_analysis.get("provides", [])],
        },
        "provides": gap_analysis.get("provides", []),
        "composes": gap_analysis.get("composes", []),
    }

    # Add existing skills this composes with
    for dep_skill in gap_analysis.get("composes", []):
        if dep_skill in graph.get("skills", {}):
            manifest["composition"]["have"].append({
                "skill": dep_skill,
                "role": dep_skill,
                "bond": f"run.sh",
            })

    # Step 4: Scaffold (or dry-run)
    output_dir = SKILLS_DIR / skill_name
    if not dry_run:
        from scaffolder import scaffold_skill
        scaffold_skill(manifest, output_dir, dry_run=False)
        scaffolded = True
    else:
        scaffolded = False
        print(f"[dry-run] Would scaffold: {output_dir}")
        print(f"  Name: {skill_name}")
        print(f"  Description: {gap_analysis.get('description', '')}")
        print(f"  Provides: {gap_analysis.get('provides', [])}")
        print(f"  Composes: {gap_analysis.get('composes', [])}")
        print(f"  Role: {gap_analysis.get('role', '')}")
        print(f"  Implementation hint: {gap_analysis.get('implementation_hint', '')}")

    # Log synthesis
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task": task,
        "chain": chain,
        "gap_position": gap_position,
        "skill_name": skill_name,
        "source": gap_analysis.get("source", "unknown"),
        "confidence": gap_analysis.get("confidence", 0),
        "scaffolded": scaffolded,
    }
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(GAP_SYNTHESIS_LOG, "a") as f:
        f.write(json.dumps(log_entry) + "\n")

    return {
        "gap_analysis": gap_analysis,
        "manifest": manifest,
        "scaffolded": scaffolded,
        "output_dir": str(output_dir),
    }


def train_gap_classifier() -> dict:
    """Train a gap classifier from accumulated labels.

    Called by bond_harvest.py nightly when enough labels exist.
    """
    labels = _load_gap_labels()
    if len(labels) < MIN_LABELS_FOR_CLASSIFIER:
        return {
            "status": "insufficient_data",
            "labels": len(labels),
            "needed": MIN_LABELS_FOR_CLASSIFIER,
        }

    try:
        from sklearn.ensemble import RandomForestClassifier
        import pickle
        import numpy as np

        X = []
        y = []
        for label in labels:
            chain = label.get("chain", [])
            task = label.get("task", "")
            features = _extract_gap_features(
                task, chain,
                label.get("gap_position"),
                label.get("from_skill"),
                label.get("to_skill"),
            )
            X.append(features)
            y.append(json.dumps({
                "name": label.get("name", "unknown"),
                "provides": label.get("provides", []),
                "composes": label.get("composes", []),
            }))

        clf = RandomForestClassifier(n_estimators=50, random_state=42)
        clf.fit(np.array(X), y)

        with open(GAP_CLASSIFIER_MODEL, "wb") as f:
            pickle.dump(clf, f)

        return {
            "status": "trained",
            "labels_used": len(labels),
            "model_path": str(GAP_CLASSIFIER_MODEL),
        }
    except ImportError:
        return {"status": "sklearn_not_available"}


def export_gap_sft_data() -> dict:
    """Export gap labels as SFT chat format for /create-gpt training.

    Once enough labels exist (100+), export for QLoRA fine-tuning.
    """
    labels = _load_gap_labels()
    if len(labels) < MIN_LABELS_FOR_GPT:
        return {
            "status": "insufficient_data",
            "labels": len(labels),
            "needed": MIN_LABELS_FOR_GPT,
        }

    sft_data = []
    for label in labels:
        chain = label.get("chain", [])
        task = label.get("task", "")
        chain_str = " → ".join(chain)

        user_msg = (
            f"A skill chain has a gap. Task: {task}. "
            f"Chain: {chain_str}. "
            f"Gap between: {label.get('from_skill', '?')} and {label.get('to_skill', '?')}. "
            f"What skill should fill this gap?"
        )

        assistant_msg = json.dumps({
            "name": label.get("name", "unknown"),
            "description": label.get("description", ""),
            "provides": label.get("provides", []),
            "composes": label.get("composes", []),
            "role": label.get("role", ""),
        })

        sft_data.append({
            "messages": [
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": assistant_msg},
            ]
        })

    output_file = STATE_DIR / "gap_sft_data.jsonl"
    with open(output_file, "w") as f:
        for entry in sft_data:
            f.write(json.dumps(entry) + "\n")

    return {
        "status": "exported",
        "entries": len(sft_data),
        "output_file": str(output_file),
    }


def gap_status() -> dict:
    """Report gap synthesis system status."""
    labels = _load_gap_labels()
    log_entries = []
    if GAP_SYNTHESIS_LOG.exists():
        for line in GAP_SYNTHESIS_LOG.read_text().strip().split("\n"):
            if line.strip():
                try:
                    log_entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    return {
        "total_labels": len(labels),
        "classifier_ready": GAP_CLASSIFIER_MODEL.exists(),
        "classifier_threshold": MIN_LABELS_FOR_CLASSIFIER,
        "labels_until_classifier": max(0, MIN_LABELS_FOR_CLASSIFIER - len(labels)),
        "gpt_ready": GAP_GPT_MODEL.exists(),
        "gpt_threshold": MIN_LABELS_FOR_GPT,
        "labels_until_gpt": max(0, MIN_LABELS_FOR_GPT - len(labels)),
        "total_syntheses": len(log_entries),
        "syntheses_by_source": _count_by_key(log_entries, "source"),
        "skills_scaffolded": sum(1 for e in log_entries if e.get("scaffolded")),
        "tier": (
            "classifier" if GAP_CLASSIFIER_MODEL.exists()
            else "gpt" if GAP_GPT_MODEL.exists()
            else "scillm" if labels
            else "heuristic"
        ),
    }


def _count_by_key(items: list[dict], key: str) -> dict[str, int]:
    """Count items by a key value."""
    counts: dict[str, int] = {}
    for item in items:
        val = item.get(key, "unknown")
        counts[val] = counts.get(val, 0) + 1
    return counts


import typer
from typing import Optional

app = typer.Typer(help="LLM-powered gap synthesis for missing skills")


@app.command()
def reason(
    task: str = typer.Argument(..., help="Task description"),
    chain: Optional[list[str]] = typer.Option(None, help="Skill chain with gap"),
    from_skill: Optional[str] = typer.Option(None, help="Skill before gap"),
    to_skill: Optional[str] = typer.Option(None, help="Skill after gap"),
    position: Optional[int] = typer.Option(None, help="Gap position in chain"),
) -> None:
    """Reason about a gap."""
    result = reason_about_gap(
        task,
        chain=chain or [],
        gap_position=position,
        from_skill=from_skill,
        to_skill=to_skill,
    )
    print(json.dumps(result, indent=2))


@app.command()
def synthesize(
    task: str = typer.Argument(..., help="Task description"),
    chain: Optional[list[str]] = typer.Option(None, help="Skill chain"),
    from_skill: Optional[str] = typer.Option(None, help="Skill before gap"),
    to_skill: Optional[str] = typer.Option(None, help="Skill after gap"),
    position: Optional[int] = typer.Option(None, help="Gap position"),
    execute: bool = typer.Option(False, help="Actually create files"),
) -> None:
    """Full synthesis: reason + scaffold."""
    result = synthesize_skill(
        task,
        chain=chain or [],
        gap_position=position,
        from_skill=from_skill,
        to_skill=to_skill,
        dry_run=not execute,
    )
    print(json.dumps(result, indent=2, default=str))


@app.command(name="train-classifier")
def train_classifier_cmd() -> None:
    """Train gap classifier from labels."""
    result = train_gap_classifier()
    print(json.dumps(result, indent=2))


@app.command(name="export-sft")
def export_sft() -> None:
    """Export SFT data for GPT training."""
    result = export_gap_sft_data()
    print(json.dumps(result, indent=2))


@app.command()
def status() -> None:
    """Gap synthesis system status."""
    result = gap_status()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    app()
