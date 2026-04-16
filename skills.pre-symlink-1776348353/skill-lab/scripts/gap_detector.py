#!/usr/bin/env python3
"""Detect capability gaps and generate composition manifests.

Given a task description, decomposes it into capability requirements,
matches against the capability graph, and outputs a composition manifest
showing HAVE (existing skills) and CREATE (missing capabilities).

Usage:
    python gap_detector.py --task "monitor arxiv and learn papers" --graph graph.json
    python gap_detector.py --task "..." --graph graph.json --json
"""
from __future__ import annotations
import os

import json
import subprocess
import sys
from pathlib import Path

from loguru import logger

SCRIPTS_DIR = Path(__file__).parent
SKILLS_DIR = SCRIPTS_DIR.parent.parent

try:
    import yaml
    _dump_yaml = lambda d: yaml.dump(d, default_flow_style=False, sort_keys=False)
except ImportError:
    _dump_yaml = lambda d: json.dumps(d, indent=2)


# Capability decomposition heuristics (no LLM needed for common patterns)
TASK_CAPABILITY_MAP = {
    "arxiv": ["arxiv-search", "web-fetch", "document-ingestion", "memory-learn"],
    "paper": ["arxiv-search", "web-fetch", "document-ingestion", "memory-learn"],
    "search": ["web-search", "deep-research"],
    "monitor": ["progress-tracking", "scheduling"],
    "learn": ["memory-learn", "memory-recall", "document-ingestion"],
    "extract": ["pdf-extraction", "html-extraction"],
    "security": ["security-scan", "competitive-security"],
    "voice": ["voice-training", "voice-conversion", "audio-separation"],
    "image": ["image-generation"],
    "classify": ["skill-creation"],
    "train": ["skill-creation"],
    "review": ["code-review", "project-assessment"],
    "test": ["hardening", "competitive-selection"],
    "ingest": ["document-ingestion", "web-fetch"],
    "schedule": ["progress-tracking"],
    "validate": ["skill-validation", "quality-audit"],
    "tag": ["taxonomy-tagging"],
    "embed": ["embedding"],
}

# Lab routing based on capability type
LAB_ROUTES = {
    "prompt": "prompt-lab",
    "filter": "prompt-lab",
    "score": "prompt-lab",
    "classify": "classifier-lab",
    "detect": "classifier-lab",
    "model": "gpt-lab",
    "infer": "gpt-lab",
}


def decompose_task(task: str) -> list[str]:
    """Decompose a task description into capability requirements.
    Uses keyword heuristics. For complex tasks, falls back to LLM."""
    capabilities = set()
    task_lower = task.lower()

    for keyword, caps in TASK_CAPABILITY_MAP.items():
        if keyword in task_lower:
            capabilities.update(caps)

    # Always need memory for any non-trivial task
    if len(capabilities) > 1:
        capabilities.add("memory-recall")

    return sorted(capabilities)


def _recall_skills_for_task(task: str) -> list[dict]:
    """Query /memory for skills matching this task description."""
    try:
        from scan_soup import _memory_recall
        return _memory_recall(task, scope="skill_registry", k=5, threshold=0.3)
    except ImportError:
        return []


def _recommend_chain_for_task(task: str) -> list[dict] | None:
    """Query /recommend-skill-chain for skills matching this task description.

    Returns a list of chain recommendation dicts (with skill names and bond scores),
    or None if the skill is unavailable, times out, or returns unparseable output.
    """
    run_sh = SKILLS_DIR / "recommend-skill-chain" / "run.sh"
    if not run_sh.exists():
        logger.debug("recommend-skill-chain not found at {}, skipping", run_sh)
        return None

    try:
        result = subprocess.run(
            [str(run_sh), "recommend", "--task", task, "--json"],
            capture_output=True,
            text=True,
            timeout=30,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode != 0:
            logger.debug(
                "recommend-skill-chain exited {}: {}",
                result.returncode,
                result.stderr.strip(),
            )
            return None

        data = json.loads(result.stdout)
        # Accept either a bare list or {"chain": [...]} / {"recommendations": [...]}
        if isinstance(data, list):
            return data
        for key in ("chain", "recommendations", "skills"):
            if isinstance(data.get(key), list):
                return data[key]
        logger.debug("recommend-skill-chain returned unexpected shape: {}", list(data.keys()))
        return None

    except subprocess.TimeoutExpired:
        logger.warning("recommend-skill-chain timed out after 30s for task: {}", task)
        return None
    except (json.JSONDecodeError, ValueError) as exc:
        logger.debug("recommend-skill-chain JSON parse error: {}", exc)
        return None
    except Exception as exc:
        logger.debug("recommend-skill-chain unexpected error: {}", exc)
        return None


def detect_gaps(task: str, graph: dict) -> dict:
    """Detect capability gaps for a task against the capability graph."""
    # Query /memory for skills matching this task BEFORE heuristic decomposition
    memory_hints = _recall_skills_for_task(task)

    # --- Primary: use /recommend-skill-chain to identify HAVE skills ---
    chain_recs = _recommend_chain_for_task(task)
    if chain_recs is not None:
        logger.info("Gap detection via recommend-skill-chain ({} recommendations)", len(chain_recs))
        have_skill_names: set[str] = set()
        for rec in chain_recs:
            if isinstance(rec, dict):
                skill = rec.get("skill") or rec.get("name") or rec.get("skill_name")
                if skill:
                    have_skill_names.add(str(skill))
            elif isinstance(rec, str):
                have_skill_names.add(rec)

        # Map recommended skills back to capability graph entries where possible,
        # otherwise synthesise lightweight HAVE entries directly from skill names.
        have: list[dict] = []
        caps_covered: set[str] = set()
        for cap, providers in graph.get("capabilities", {}).items():
            if any(p in have_skill_names for p in providers):
                best = next(p for p in providers if p in have_skill_names)
                have.append({
                    "capability": cap,
                    "skill": best,
                    "alternatives": [p for p in providers if p != best],
                    "bond": f"run.sh {cap.split('-')[0]}",
                })
                caps_covered.add(cap)
        # Recommended skills not in the graph still count as HAVE
        for skill_name in sorted(have_skill_names):
            if not any(item["skill"] == skill_name for item in have):
                have.append({
                    "capability": skill_name,
                    "skill": skill_name,
                    "alternatives": [],
                    "bond": f"run.sh {skill_name.split('-')[0]}",
                })

        # Anything in the keyword-derived required set NOT covered is CREATE
        required = decompose_task(task)
        create: list[dict] = []
        for cap in required:
            if cap not in caps_covered and not any(item["skill"] == cap for item in have):
                lab = _route_to_lab(cap)
                create.append({
                    "capability": cap,
                    "description": f"Missing capability: {cap}",
                    "lab": lab,
                })

        total = len(have) + len(create)
        return {
            "task": task,
            "required_capabilities": required,
            "have": have,
            "create": create,
            "coverage": len(have) / total if total else 1.0,
            "memory_hints": len(memory_hints),
            "detection_method": "recommend-skill-chain",
        }

    # --- Fallback: keyword matching ---
    logger.info("Gap detection via keyword fallback")
    required = decompose_task(task)

    # Merge memory-recalled capabilities into required set
    if memory_hints:
        for hint in memory_hints:
            try:
                data = json.loads(hint.get("solution", "{}"))
                for cap in data.get("provides", []):
                    if cap not in required:
                        required.append(cap)
            except (json.JSONDecodeError, TypeError):
                pass

    have = []
    create = []

    for cap in required:
        providers = graph.get("capabilities", {}).get(cap, [])
        if providers:
            # Pick the best provider (first one, could be smarter)
            have.append({
                "capability": cap,
                "skill": providers[0],
                "alternatives": providers[1:] if len(providers) > 1 else [],
                "bond": f"run.sh {cap.split('-')[0]}",
            })
        else:
            # This capability doesn't exist — needs creation
            lab = _route_to_lab(cap)
            create.append({
                "capability": cap,
                "description": f"Missing capability: {cap}",
                "lab": lab,
            })

    return {
        "task": task,
        "required_capabilities": required,
        "have": have,
        "create": create,
        "coverage": len(have) / len(required) if required else 1.0,
        "memory_hints": len(memory_hints),
        "detection_method": "keyword-fallback",
    }


def _route_to_lab(capability: str) -> str | None:
    """Route a missing capability to the appropriate lab skill."""
    cap_lower = capability.lower()
    for keyword, lab in LAB_ROUTES.items():
        if keyword in cap_lower:
            return lab
    return None  # Simple code, no lab needed


def generate_manifest(gaps: dict, skill_name: str | None = None) -> dict:
    """Generate a composition manifest from gap analysis."""
    if not skill_name:
        # Auto-generate name from task
        words = gaps["task"].lower().split()[:3]
        skill_name = "-".join(w for w in words if len(w) > 2)

    manifest = {
        "schema_version": "1.0",
        "name": skill_name,
        "task": gaps["task"],
        "coverage": gaps["coverage"],
        "composition": {
            "have": [
                {
                    "skill": item["skill"],
                    "role": item["capability"],
                    "bond": item["bond"],
                    "alternatives": item.get("alternatives", []),
                }
                for item in gaps["have"]
            ],
            "create": [
                {
                    "capability": item["capability"],
                    "description": item["description"],
                    "lab": item["lab"],
                }
                for item in gaps["create"]
            ],
        },
        "validation": {
            "skills_ci": True,
            "security_scan": True,
            "battle_compete": len(gaps["create"]) > 1,
            "anvil_harden": False,
        },
    }

    return manifest


import typer
from typing import Optional

app = typer.Typer(help="Detect capability gaps")


@app.callback(invoke_without_command=True)
def main(
    task: str = typer.Option(..., help="Task description"),
    graph_path: Optional[str] = typer.Option(None, "--graph", help="Path to capability graph JSON"),
    skills_root: Optional[str] = typer.Option(None, help="Scan skills directly"),
    name: Optional[str] = typer.Option(None, help="Name for the new skill"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
    manifest: bool = typer.Option(False, help="Output composition manifest"),
) -> None:
    """Detect capability gaps for a task."""
    # Load or build graph
    if graph_path:
        graph = json.loads(Path(graph_path).read_text())
    elif skills_root:
        from scan_soup import scan_soup
        graph = scan_soup(Path(skills_root))
    else:
        # Default: scan parent directory
        default_root = Path(__file__).parent.parent.parent
        from scan_soup import scan_soup
        graph = scan_soup(default_root)

    gaps = detect_gaps(task, graph)

    if manifest:
        manifest_data = generate_manifest(gaps, name)
        print(_dump_yaml(manifest_data))
    elif json_output:
        print(json.dumps(gaps, indent=2))
    else:
        print(f"Task: {gaps['task']}")
        print(f"Coverage: {gaps['coverage']:.0%}")
        print()

        if gaps["have"]:
            print("HAVE (existing skills):")
            for item in gaps["have"]:
                alts = f" (also: {', '.join(item['alternatives'])})" if item.get("alternatives") else ""
                print(f"  ✓ {item['capability']} → {item['skill']}{alts}")

        if gaps["create"]:
            print()
            print("CREATE (missing capabilities):")
            for item in gaps["create"]:
                lab = f" → craft via /{item['lab']}" if item["lab"] else " → direct implementation"
                print(f"  ✗ {item['capability']}{lab}")

        if not gaps["create"]:
            print()
            print("All capabilities available! Use `./run.sh scaffold` to wire them together.")


if __name__ == "__main__":
    app()
