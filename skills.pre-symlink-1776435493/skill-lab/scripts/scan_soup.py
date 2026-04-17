#!/usr/bin/env python3
"""Scan the skill soup and build a capability graph.

Reads all SKILL.md frontmatter to extract provides:/composes: fields,
builds a directed graph of skill dependencies and capabilities.

Usage:
    python scan_soup.py                          # Scan and print summary
    python scan_soup.py --json                   # JSON capability graph
    python scan_soup.py --task "description"      # Show which skills match
    python scan_soup.py --register               # Register all skills in /memory
"""
from __future__ import annotations
import os

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from loguru import logger

SCRIPTS_DIR = Path(__file__).parent
SKILLS_DIR = SCRIPTS_DIR.parent.parent

try:
    import yaml
    def _parse_yaml(text: str) -> dict:
        return yaml.safe_load(text) or {}
except ImportError:
    def _parse_yaml(text: str) -> dict:
        """Minimal YAML parser for frontmatter.

        Handles:
        - key: value (scalar)
        - key: [a, b, c] (inline list)
        - key:\\n  - a\\n  - b (block list)
        - key: >\\n  multi-line text (YAML fold → single string)
        - key: |\\n  multi-line text (YAML literal → preserved newlines)
        """
        result: dict = {}
        current_key = None
        fold_mode: str | None = None  # ">" or "|" when collecting continuation

        for line in text.split("\n"):
            stripped = line.strip()

            # Blank lines end fold/literal continuation
            if not stripped:
                if fold_mode:
                    fold_mode = None
                continue

            if stripped.startswith("#"):
                continue

            # Continuation line for > or | blocks (indented, no colon at root level)
            if fold_mode and current_key and (line.startswith("  ") or line.startswith("\t")):
                prev = result.get(current_key, "")
                sep = " " if fold_mode == ">" else "\n"
                result[current_key] = (prev + sep + stripped).strip()
                continue
            else:
                fold_mode = None

            if stripped.startswith("- ") and current_key:
                if not isinstance(result[current_key], list):
                    result[current_key] = []
                result[current_key].append(stripped[2:].strip())
            elif ":" in stripped:
                k, v = stripped.split(":", 1)
                k = k.strip()
                v = v.strip()
                current_key = k
                if v in (">", "|"):
                    result[k] = ""
                    fold_mode = v
                elif v == "":
                    result[k] = []
                elif v.startswith("[") and v.endswith("]"):
                    result[k] = [x.strip() for x in v[1:-1].split(",") if x.strip()]
                else:
                    result[k] = v
        return result


def extract_frontmatter(skill_md: Path) -> dict | None:
    """Extract YAML frontmatter from SKILL.md."""
    try:
        text = skill_md.read_text(errors="replace")
    except Exception:
        return None
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    return _parse_yaml(parts[1])


def scan_soup(skills_root: Path) -> dict:
    """Scan all skills and build capability graph."""
    graph = {
        "skills": {},
        "capabilities": {},  # capability -> list of providers
        "edges": [],         # composes edges
        "stats": {
            "total_skills": 0,
            "with_provides": 0,
            "with_composes": 0,
            "total_capabilities": 0,
            "total_edges": 0,
        },
    }

    for skill_dir in sorted(skills_root.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue

        fm = extract_frontmatter(skill_md)
        if not fm:
            continue

        name = fm.get("name", skill_dir.name)
        provides = fm.get("provides", [])
        composes = fm.get("composes", [])

        if isinstance(provides, str):
            provides = [provides]
        if isinstance(composes, str):
            composes = [composes]
        if not isinstance(provides, list):
            provides = []
        if not isinstance(composes, list):
            composes = []

        has_run_sh = (skill_dir / "run.sh").exists()
        has_sanity = (skill_dir / "sanity.sh").exists()

        triggers = fm.get("triggers", [])
        if isinstance(triggers, str):
            triggers = [triggers]
        if not isinstance(triggers, list):
            triggers = []

        taxonomy = fm.get("taxonomy", [])
        if isinstance(taxonomy, str):
            taxonomy = [taxonomy]
        if not isinstance(taxonomy, list):
            taxonomy = []

        # Granularity metrics (BFF SUBLEQ lesson: instruction density matters)
        script_count = 0
        lines_of_code = 0
        scripts_dir = skill_dir / "scripts"
        if scripts_dir.exists():
            for sf in scripts_dir.iterdir():
                if sf.suffix in (".py", ".sh"):
                    script_count += 1
                    try:
                        lines_of_code += len(sf.read_text(errors="replace").splitlines())
                    except Exception as e:
                        logger.debug("lines_of_code failed: {}", e)
        # Also count root-level scripts
        for sf in skill_dir.iterdir():
            if sf.is_file() and sf.suffix in (".py", ".sh") and sf.name != "run.sh":
                script_count += 1
                try:
                    lines_of_code += len(sf.read_text(errors="replace").splitlines())
                except Exception as e:
                    logger.debug("lines_of_code failed: {}", e)

        provides_count = len(provides)
        import math
        composability_score = round(
            provides_count / max(1.0, math.log2(max(1, lines_of_code))),
            3,
        )

        graph["skills"][name] = {
            "path": str(skill_dir),
            "provides": provides,
            "composes": composes,
            "taxonomy": taxonomy,
            "triggers": triggers,
            "has_run_sh": has_run_sh,
            "has_sanity": has_sanity,
            "description": fm.get("description", ""),
            "short_description": fm.get("metadata", {}).get("short-description", "") if isinstance(fm.get("metadata"), dict) else "",
            "composability_score": composability_score,
            "provides_count": provides_count,
            "script_count": script_count,
            "lines_of_code": lines_of_code,
        }

        graph["stats"]["total_skills"] += 1
        if provides:
            graph["stats"]["with_provides"] += 1
        if composes:
            graph["stats"]["with_composes"] += 1

        # Build capability index
        for cap in provides:
            if cap not in graph["capabilities"]:
                graph["capabilities"][cap] = []
            graph["capabilities"][cap].append(name)

        # Build edges
        for dep in composes:
            graph["edges"].append({
                "from": name,
                "to": dep,
                "type": "composes",
            })

    graph["stats"]["total_capabilities"] = len(graph["capabilities"])
    graph["stats"]["total_edges"] = len(graph["edges"])

    # Granularity warnings (SUBLEQ lesson: coarse-grained skills don't compose well)
    graph["granularity_warnings"] = []
    for name, info in graph["skills"].items():
        score = info.get("composability_score", 0)
        if score < 0.3 and info.get("lines_of_code", 0) > 100:
            graph["granularity_warnings"].append({
                "skill": name,
                "composability_score": score,
                "provides_count": info.get("provides_count", 0),
                "lines_of_code": info.get("lines_of_code", 0),
                "recommendation": "Consider splitting into smaller skills with more provides: entries",
            })

    return graph


def find_skills_for_task(graph: dict, capabilities_needed: list[str]) -> dict:
    """Given required capabilities, find which skills provide them and what's missing."""
    have = {}
    missing = []

    for cap in capabilities_needed:
        providers = graph["capabilities"].get(cap, [])
        if providers:
            have[cap] = providers
        else:
            missing.append(cap)

    return {"have": have, "missing": missing}


def print_summary(graph: dict):
    """Print human-readable summary of the capability graph."""
    stats = graph["stats"]
    print(f"Skill Soup Summary")
    print(f"  Total skills:      {stats['total_skills']}")
    print(f"  With provides:     {stats['with_provides']}")
    print(f"  With composes:     {stats['with_composes']}")
    print(f"  Missing valence:   {stats['total_skills'] - stats['with_provides']}")
    print(f"  Capabilities:      {stats['total_capabilities']}")
    print(f"  Composition edges: {stats['total_edges']}")
    print()

    # Top capabilities
    caps = sorted(graph["capabilities"].items(), key=lambda x: -len(x[1]))
    print("Top capabilities (most providers):")
    for cap, providers in caps[:15]:
        print(f"  {cap}: {', '.join(providers)}")

    # Skills without valence
    no_valence = [
        name for name, info in graph["skills"].items()
        if not info["provides"]
    ]
    if no_valence:
        print(f"\nSkills missing provides: ({len(no_valence)})")
        for name in no_valence[:20]:
            print(f"  - {name}")
        if len(no_valence) > 20:
            print(f"  ... and {len(no_valence) - 20} more")


def _memory_learn(
    problem: str,
    solution: str,
    tags: list[str],
    scope: str = "skill_registry",
) -> bool:
    """Store a lesson in /memory with correct --tag syntax.

    Uses repeated --tag flags (not --tags with comma-joined values).
    This is the shared helper for all skill-lab → /memory writes.
    """
    memory_skill = SKILLS_DIR / "memory"
    if not (memory_skill / "run.sh").exists():
        return False
    cmd = [
        str(memory_skill / "run.sh"), "learn",
        "--problem", problem,
        "--solution", solution,
        "--scope", scope,
    ]
    for tag in tags:
        cmd.extend(["--tag", str(tag)])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        return result.returncode == 0
    except Exception:
        return False


def _memory_recall(
    query: str,
    scope: str = "skill_registry",
    k: int = 5,
    threshold: float = 0.3,
) -> list[dict]:
    """Query /memory for lessons matching a query."""
    memory_skill = SKILLS_DIR / "memory"
    if not (memory_skill / "run.sh").exists():
        return []
    try:
        result = subprocess.run(
            [str(memory_skill / "run.sh"), "recall",
             "--q", query, "--scope", scope,
             "--k", str(k), "--threshold", str(threshold)],
            capture_output=True, text=True, timeout=15,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return data.get("items", [])
    except Exception as e:
        logger.debug("value lookup failed: {}", e)
    return []


def _data_hash(info: dict) -> str:
    """Compute hash of skill data for deduplication on re-registration."""
    key_data = json.dumps({
        "provides": sorted(info.get("provides", [])),
        "composes": sorted(info.get("composes", [])),
        "taxonomy": sorted(info.get("taxonomy", [])),
    }, sort_keys=True)
    return hashlib.md5(key_data.encode()).hexdigest()[:12]


def register_in_memory(graph: dict, skills_root: Path):
    """Register all skills in /memory for multi-hop traversal.

    Uses batch_learn from common.memory_client for concurrent inserts
    instead of serial subprocess calls (~10x faster).

    Three registration passes collected into a single batch:
    1. Skill registry entries — one per skill with structured JSON
    2. Capability registry entries — one per unique capability
    3. Composition edge entries — one per composes relationship
    """
    # Try batch path first (fast), fall back to serial subprocess
    try:
        _register_in_memory_batch(graph, skills_root)
    except Exception as e:
        print(f"WARN: batch registration failed ({e}), falling back to serial")
        _register_in_memory_serial(graph, skills_root)


def _register_in_memory_batch(graph: dict, skills_root: Path):
    """Fast batch registration via concurrent subprocess calls to /memory.

    Collects all items first, then fires them in parallel using
    ThreadPoolExecutor (8 concurrent workers) — ~8x faster than serial.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    items: list[dict] = []  # Each: {problem, solution, tags}

    # --- Collect Pass 1: Skill registry entries ---
    for name, info in graph["skills"].items():
        provides_csv = ", ".join(info["provides"]) if info["provides"] else "none"
        dh = _data_hash(info)

        tags = ["skill", f"skill:{name}"]
        for tax_tag in info.get("taxonomy", []):
            tags.append(str(tax_tag))

        # Build a rich problem field for BM25 matching.
        # Include description + triggers so task-oriented queries like
        # "fix table extraction" match the skill that handles it.
        desc = info.get("description", "") or ""
        if isinstance(desc, list):
            desc = " ".join(str(d) for d in desc)
        triggers = info.get("triggers", []) or []
        if isinstance(triggers, list) and triggers:
            triggers_str = " | ".join(str(t) for t in triggers)
            problem_text = f"skill {name}: {desc} — provides {provides_csv}. Triggers: {triggers_str}"
        else:
            problem_text = f"skill {name}: {desc} — provides {provides_csv}"

        items.append({
            "problem": problem_text.strip(),
            "solution": json.dumps({
                "name": name,
                "path": info["path"],
                "provides": info["provides"],
                "composes": info["composes"],
                "triggers": info.get("triggers", []),
                "taxonomy": info["taxonomy"],
                "description": desc,
                "short_description": info.get("short_description", ""),
                "composability_score": info.get("composability_score", 0),
                "has_run_sh": info.get("has_run_sh", False),
                "has_sanity": info.get("has_sanity", False),
                "data_hash": dh,
            }),
            "tags": tags,
        })
    skill_count = len(items)

    # --- Collect Pass 2: Capability registry entries ---
    for cap_name, providers in graph["capabilities"].items():
        scored = sorted(
            providers,
            key=lambda p: graph["skills"].get(p, {}).get("composability_score", 0),
            reverse=True,
        )
        best = scored[0] if scored else ""

        lab_route = None
        cap_lower = cap_name.lower()
        for keyword, lab in [("prompt", "prompt-lab"), ("filter", "prompt-lab"),
                             ("classify", "classifier-lab"), ("detect", "classifier-lab"),
                             ("model", "gpt-lab"), ("infer", "gpt-lab")]:
            if keyword in cap_lower:
                lab_route = lab
                break

        items.append({
            "problem": f"capability {cap_name}: which skills provide this?",
            "solution": json.dumps({
                "capability": cap_name,
                "providers": scored,
                "best_provider": best,
                "lab_route": lab_route,
            }),
            "tags": ["capability", f"cap:{cap_name}", f"provider:{best}"],
        })
    cap_count = len(items) - skill_count

    # --- Collect Pass 3: Composition edge entries ---
    for edge in graph["edges"]:
        from_skill = edge["from"]
        to_skill = edge["to"]

        try:
            from composer import AFFINITIES
            affinity = 0.0
            for partner, weight in AFFINITIES.get(from_skill, []):
                if partner == to_skill:
                    affinity = weight
                    break
        except ImportError:
            affinity = 0.0

        items.append({
            "problem": f"composition: {from_skill} uses {to_skill}",
            "solution": f"Skill {from_skill} composes {to_skill}. Bond affinity: {affinity}.",
            "tags": ["composition", f"skill:{from_skill}", f"skill:{to_skill}"],
        })
    edge_count = len(items) - skill_count - cap_count

    # --- Concurrent batch insert ---
    concurrency = 8
    print(f"Batch inserting {len(items)} items (concurrency={concurrency})...")
    results: list[bool] = [False] * len(items)

    def learn_one(idx: int) -> tuple[int, bool]:
        item = items[idx]
        return idx, _memory_learn(item["problem"], item["solution"], item["tags"])

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(learn_one, i): i for i in range(len(items))}
        for fut in as_completed(futures):
            try:
                idx, ok = fut.result()
                results[idx] = ok
            except Exception as e:
                logger.debug("result extraction failed: {}", e)

    reg_skills = sum(results[:skill_count])
    reg_caps = sum(results[skill_count:skill_count + cap_count])
    reg_edges = sum(results[skill_count + cap_count:])

    print(f"Registered {reg_skills}/{skill_count} skills, "
          f"{reg_caps} capabilities, {reg_edges} edges in /memory")


def _register_in_memory_serial(graph: dict, skills_root: Path):
    """Fallback serial registration via subprocess calls."""
    memory_skill = skills_root / "memory"
    if not (memory_skill / "run.sh").exists():
        print("WARN: /memory skill not found, skipping registration")
        return

    reg_skills = 0
    reg_caps = 0
    reg_edges = 0

    for name, info in graph["skills"].items():
        provides_csv = ", ".join(info["provides"]) if info["provides"] else "none"
        dh = _data_hash(info)
        problem = f"skill {name}: {info.get('description', '')} — provides {provides_csv}"
        solution = json.dumps({
            "name": name, "path": info["path"], "provides": info["provides"],
            "composes": info["composes"], "taxonomy": info["taxonomy"],
            "composability_score": info.get("composability_score", 0),
            "has_run_sh": info.get("has_run_sh", False),
            "has_sanity": info.get("has_sanity", False), "data_hash": dh,
        })
        tags = ["skill", f"skill:{name}"]
        for tax_tag in info.get("taxonomy", []):
            tags.append(str(tax_tag))
        if _memory_learn(problem, solution, tags):
            reg_skills += 1

    for cap_name, providers in graph["capabilities"].items():
        scored = sorted(providers, key=lambda p: graph["skills"].get(p, {}).get("composability_score", 0), reverse=True)
        best = scored[0] if scored else ""
        lab_route = None
        cap_lower = cap_name.lower()
        for keyword, lab in [("prompt", "prompt-lab"), ("filter", "prompt-lab"),
                             ("classify", "classifier-lab"), ("detect", "classifier-lab"),
                             ("model", "gpt-lab"), ("infer", "gpt-lab")]:
            if keyword in cap_lower:
                lab_route = lab
                break
        problem = f"capability {cap_name}: which skills provide this?"
        solution = json.dumps({"capability": cap_name, "providers": scored, "best_provider": best, "lab_route": lab_route})
        tags = ["capability", f"cap:{cap_name}", f"provider:{best}"]
        if _memory_learn(problem, solution, tags):
            reg_caps += 1

    for edge in graph["edges"]:
        from_skill, to_skill = edge["from"], edge["to"]
        try:
            from composer import AFFINITIES
            affinity = 0.0
            for partner, weight in AFFINITIES.get(from_skill, []):
                if partner == to_skill:
                    affinity = weight
                    break
        except ImportError:
            affinity = 0.0
        problem = f"composition: {from_skill} uses {to_skill}"
        solution = f"Skill {from_skill} composes {to_skill}. Bond affinity: {affinity}."
        tags = ["composition", f"skill:{from_skill}", f"skill:{to_skill}"]
        if _memory_learn(problem, solution, tags):
            reg_edges += 1

    print(f"Registered {reg_skills}/{len(graph['skills'])} skills, "
          f"{reg_caps} capabilities, {reg_edges} edges in /memory")


import typer
from typing import Optional

app = typer.Typer(help="Scan skill soup")


@app.callback(invoke_without_command=True)
def main(
    skills_root: str = typer.Option(str(Path(__file__).parent.parent.parent), help="Root of skills directory"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
    task: Optional[str] = typer.Option(None, help="Show which skills match a task description"),
    register: bool = typer.Option(False, help="Register in /memory"),
) -> None:
    """Scan the skill soup and build a capability graph."""
    root = Path(skills_root).resolve()
    graph = scan_soup(root)

    if register:
        register_in_memory(graph, root)

    if json_output:
        print(json.dumps(graph, indent=2, default=str))
    elif task:
        print(f"Task: {task}")
        print(f"Soup: {graph['stats']['total_skills']} skills, {graph['stats']['total_capabilities']} capabilities")
        print()
        print("Available capabilities:")
        for cap, providers in sorted(graph["capabilities"].items()):
            print(f"  {cap}: {', '.join(providers)}")
        print()
        print("Use `./run.sh compose --task '...'` to generate a composition manifest")
    else:
        print_summary(graph)


if __name__ == "__main__":
    app()
