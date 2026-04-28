"""Embry OS indexing workflow for skills, packages, configuration, and extensions."""

#!/usr/bin/env python3
"""
/ask os learn — Crawl and index embry-os internal knowledge.

Crawls:
  - .pi/skills/*/SKILL.md        — Skill manifests (YAML frontmatter + body)
  - packages/*/package.json      — Package metadata
  - packages/*/README.md         — Package documentation
  - .pi/config.toml              — OS configuration
  - .pi/extensions/*.ts          — Extension hooks
  - package.json                 — Workspace registry

Produces QRA triples tagged with scope=os, bridge attributes, and source metadata.
Stores everything to /memory for semantic recall.
"""

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

import typer
import yaml
from loguru import logger as log

log.remove()
if os.environ.get("ASK_DEBUG"):
    log.add(sys.stderr, level="DEBUG")
else:
    log.add(sys.stderr, level="INFO")

from .skills_exec import run_skill, parse_json_output
from .monitor import AskMonitor
from .dry_run_spec import build_os_learn_dry_run_spec, print_execution_spec
from .run_state import AskRunState, make_run_id
from .taxonomy import extract_bridges_from_content

# Paths
SKILL_DIR = Path(__file__).parent
PROJECT_ROOT = SKILL_DIR.parent.parent.parent
PI_DIR = PROJECT_ROOT / ".pi"
SKILLS_ROOT = PI_DIR / "skills"
PACKAGES_ROOT = PROJECT_ROOT / "packages"

# Depth configs
DEPTH_CONFIG = {
    "quick": {"max_skills": 50, "max_packages": 4, "generate_qra": False},
    "standard": {"max_skills": 200, "max_packages": 10, "generate_qra": True},
    "deep": {"max_skills": 999, "max_packages": 999, "generate_qra": True},
}


# ---------------------------------------------------------------------------
# Crawlers
# ---------------------------------------------------------------------------

def parse_skill_md(path: Path) -> Optional[dict]:
    """Parse a SKILL.md file extracting YAML frontmatter and body."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        log.debug("Cannot read %s: %s", path, e)
        return None

    # Split frontmatter from body
    frontmatter = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                frontmatter = yaml.safe_load(parts[1]) or {}
            except yaml.YAMLError:
                pass
            body = parts[2].strip()

    name = frontmatter.get("name", path.parent.name)
    return {
        "name": name,
        "description": frontmatter.get("description", ""),
        "provides": frontmatter.get("provides", []),
        "composes": frontmatter.get("composes", []),
        "triggers": frontmatter.get("triggers", []),
        "metadata": frontmatter.get("metadata", {}),
        "body": body[:2000],  # Truncate for indexing
        "path": str(path.relative_to(PROJECT_ROOT)),
        "source": "skill",
    }


def crawl_skills(max_skills: int = 200) -> list[dict]:
    """Parse all SKILL.md files under .pi/skills/."""
    skills = []
    if not SKILLS_ROOT.is_dir():
        log.warning("Skills directory not found: %s", SKILLS_ROOT)
        return skills

    skill_dirs = sorted(SKILLS_ROOT.iterdir())
    for skill_dir in skill_dirs[:max_skills]:
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if skill_md.exists():
            parsed = parse_skill_md(skill_md)
            if parsed:
                skills.append(parsed)

    log.info("Crawled %d skills from %s", len(skills), SKILLS_ROOT)
    return skills


def crawl_packages(max_packages: int = 10) -> list[dict]:
    """Walk package.json workspaces, extract package metadata + README summaries."""
    packages = []
    if not PACKAGES_ROOT.is_dir():
        log.warning("Packages directory not found: %s", PACKAGES_ROOT)
        return packages

    pkg_dirs = sorted(PACKAGES_ROOT.iterdir())
    for pkg_dir in pkg_dirs[:max_packages]:
        if not pkg_dir.is_dir():
            continue

        pkg_json = pkg_dir / "package.json"
        if not pkg_json.exists():
            continue

        try:
            data = json.loads(pkg_json.read_text())
        except (OSError, json.JSONDecodeError):
            continue

        readme = ""
        readme_path = pkg_dir / "README.md"
        if readme_path.exists():
            try:
                readme = readme_path.read_text(encoding="utf-8", errors="replace")[:2000]
            except OSError:
                pass

        packages.append({
            "name": data.get("name", pkg_dir.name),
            "description": data.get("description", ""),
            "version": data.get("version", ""),
            "dependencies": list(data.get("dependencies", {}).keys()),
            "scripts": list(data.get("scripts", {}).keys()),
            "readme": readme,
            "path": str(pkg_dir.relative_to(PROJECT_ROOT)),
            "source": "package",
        })

    log.info("Crawled %d packages from %s", len(packages), PACKAGES_ROOT)
    return packages


def crawl_config() -> list[dict]:
    """Crawl .pi/config.toml and root package.json for configuration knowledge."""
    configs = []

    # .pi/config.toml
    config_toml = PI_DIR / "config.toml"
    if config_toml.exists():
        try:
            text = config_toml.read_text(encoding="utf-8", errors="replace")
            configs.append({
                "name": "pi-config",
                "description": "Embry-OS configuration",
                "body": text[:2000],
                "path": str(config_toml.relative_to(PROJECT_ROOT)),
                "source": "config",
            })
        except OSError:
            pass

    # Root package.json (workspace registry)
    root_pkg = PROJECT_ROOT / "package.json"
    if root_pkg.exists():
        try:
            data = json.loads(root_pkg.read_text())
            workspaces = data.get("workspaces", [])
            configs.append({
                "name": "workspace-registry",
                "description": f"Mono-repo workspace registry: {', '.join(workspaces[:10])}",
                "workspaces": workspaces,
                "path": "package.json",
                "source": "config",
            })
        except (OSError, json.JSONDecodeError):
            pass

    # Extensions
    ext_dir = PI_DIR / "extensions"
    if ext_dir.is_dir():
        for ext_file in sorted(ext_dir.glob("*.ts")):
            try:
                text = ext_file.read_text(encoding="utf-8", errors="replace")
                configs.append({
                    "name": f"extension:{ext_file.stem}",
                    "description": f"Extension hook: {ext_file.name}",
                    "body": text[:1500],
                    "path": str(ext_file.relative_to(PROJECT_ROOT)),
                    "source": "extension",
                })
            except OSError:
                pass

    log.info("Crawled %d config items", len(configs))
    return configs


# ---------------------------------------------------------------------------
# Capability Graph
# ---------------------------------------------------------------------------

def build_capability_graph(skills: list[dict]) -> dict:
    """Build provides→composes edges from skill manifests.

    Returns dict with:
      - providers: {capability: [skill_names]}
      - composers: {skill_name: [composed_skills]}
      - edges: [(from_skill, to_skill, relationship)]
    """
    providers: dict[str, list[str]] = {}
    composers: dict[str, list[str]] = {}
    edges: list[tuple[str, str, str]] = []

    for skill in skills:
        name = skill["name"]

        for p in skill.get("provides", []) or []:
            providers.setdefault(p, []).append(name)

        composes = skill.get("composes", []) or []
        if composes:
            composers[name] = composes
            for c in composes:
                edges.append((name, c, "composes"))

    log.info("Capability graph: %d providers, %d composers, %d edges",
             len(providers), len(composers), len(edges))

    return {
        "providers": providers,
        "composers": composers,
        "edges": edges,
    }


# ---------------------------------------------------------------------------
# QRA Generation
# ---------------------------------------------------------------------------

def generate_skill_qra(skill: dict) -> list[dict]:
    """Generate Q-R-A triples from a single skill manifest."""
    name = skill["name"]
    desc = skill.get("description", "").strip()
    provides = skill.get("provides", []) or []
    composes = skill.get("composes", []) or []
    triggers = skill.get("triggers", []) or []
    body = skill.get("body", "")

    qras = []

    # Core: what does this skill do?
    if desc:
        qras.append({
            "question": f"What does the /{name} skill do?",
            "reasoning": f"The {name} skill manifest describes its purpose and capabilities.",
            "answer": desc[:500],
            "tags": [f"skill:{name}", "source:skill"],
        })

    # Provides
    if provides:
        provides_str = ", ".join(str(p) for p in provides)
        qras.append({
            "question": f"What does /{name} provide?",
            "reasoning": f"Checking the provides field of {name}'s SKILL.md manifest.",
            "answer": f"/{name} provides: {provides_str}",
            "tags": [f"skill:{name}", "source:skill"],
        })

    # Composes
    if composes:
        composes_str = ", ".join(str(c) for c in composes)
        qras.append({
            "question": f"What skills does /{name} compose or depend on?",
            "reasoning": f"Checking the composes field of {name}'s SKILL.md manifest.",
            "answer": f"/{name} composes: {composes_str}",
            "tags": [f"skill:{name}", "source:skill"],
        })

    # Triggers
    if triggers:
        trigger_str = ", ".join(f'"{t}"' for t in triggers[:5])
        qras.append({
            "question": f"How do I invoke /{name}?",
            "reasoning": f"Looking at the triggers that activate the {name} skill.",
            "answer": f"/{name} can be triggered with: {trigger_str}",
            "tags": [f"skill:{name}", "source:skill"],
        })

    return qras


def generate_package_qra(pkg: dict) -> list[dict]:
    """Generate Q-R-A triples from a package."""
    name = pkg["name"]
    desc = pkg.get("description", "").strip()
    deps = pkg.get("dependencies", [])
    readme = pkg.get("readme", "")

    qras = []

    if desc:
        qras.append({
            "question": f"What is the {name} package?",
            "reasoning": f"Reading the package.json description for {name}.",
            "answer": desc[:500],
            "tags": [f"package:{name}", "source:package"],
        })

    if deps:
        dep_str = ", ".join(deps[:15])
        qras.append({
            "question": f"What are the dependencies of {name}?",
            "reasoning": f"Listing the npm dependencies from {name}/package.json.",
            "answer": f"{name} depends on: {dep_str}",
            "tags": [f"package:{name}", "source:package"],
        })

    # Extract key info from README
    if readme and len(readme) > 100:
        # First paragraph as summary
        paragraphs = [p.strip() for p in readme.split("\n\n") if p.strip() and not p.strip().startswith("#")]
        if paragraphs:
            qras.append({
                "question": f"How does the {name} package work?",
                "reasoning": f"Summarizing the README for {name}.",
                "answer": paragraphs[0][:500],
                "tags": [f"package:{name}", "source:package"],
            })

    return qras


def generate_os_qra(
    skills: list[dict],
    packages: list[dict],
    configs: list[dict],
    graph: dict,
) -> list[dict]:
    """Generate all Q-R-A triples from crawled OS knowledge."""
    all_qras = []

    for skill in skills:
        all_qras.extend(generate_skill_qra(skill))

    for pkg in packages:
        all_qras.extend(generate_package_qra(pkg))

    # Config QRAs
    for cfg in configs:
        if cfg.get("description"):
            all_qras.append({
                "question": f"What is {cfg['name']}?",
                "reasoning": f"Reading {cfg.get('path', 'config')}.",
                "answer": cfg["description"][:500],
                "tags": [f"source:{cfg['source']}"],
            })

    # Graph-level QRAs
    providers = graph.get("providers", {})
    for capability, skill_names in providers.items():
        if len(skill_names) > 1:
            all_qras.append({
                "question": f"Which skills provide {capability}?",
                "reasoning": f"Scanning provides fields across all skill manifests.",
                "answer": f"{capability} is provided by: {', '.join(skill_names)}",
                "tags": ["source:graph"],
            })

    log.info("Generated %d QRA triples", len(all_qras))
    return all_qras


# ---------------------------------------------------------------------------
# Memory Storage
# ---------------------------------------------------------------------------

def store_qra_to_memory(
    qras: list[dict],
    scope: str = "os",
    dry_run: bool = False,
) -> dict:
    """Store QRA triples to memory with scope=os.

    Returns stats dict with stored count and errors.
    """
    stats = {"total": len(qras), "stored": 0, "errors": 0, "skipped": 0}

    if dry_run:
        stats["skipped"] = len(qras)
        return stats

    for qra in qras:
        problem = qra["question"]
        solution = f"Reasoning: {qra['reasoning']}\nAnswer: {qra['answer']}"
        tags = qra.get("tags", [])

        args = ["learn", "--problem", problem, "--solution", solution, "--scope", scope]
        for tag in tags:
            args.extend(["--tag", tag])

        result = run_skill("memory", args, timeout=30)
        if result["returncode"] == 0:
            stats["stored"] += 1
        else:
            stats["errors"] += 1
            log.error("Memory store failed for %r: %s", problem[:60], result["stderr"][:100])

    return stats


# ---------------------------------------------------------------------------
# Bridge Tagging
# ---------------------------------------------------------------------------

def tag_qras_with_bridges(qras: list[dict]) -> list[dict]:
    """Add bridge tags to QRA triples based on content analysis."""
    for qra in qras:
        text = f"{qra['question']} {qra['answer']}"
        bridges = extract_bridges_from_content(text, content_type="article")
        if bridges:
            existing_tags = qra.get("tags", [])
            for bridge in bridges:
                tag = f"bridge:{bridge}"
                if tag not in existing_tags:
                    existing_tags.append(tag)
            qra["tags"] = existing_tags
    return qras


# ---------------------------------------------------------------------------
# Domain Classification
# ---------------------------------------------------------------------------

def classify_domain(item: dict) -> str:
    """Classify an item into an OS domain."""
    name = item.get("name", "").lower()
    desc = (item.get("description", "") or "").lower()
    combined = f"{name} {desc}"

    if any(kw in combined for kw in ["monitor-", "ops-", "scheduler", "health", "workstation"]):
        return "infrastructure"
    if any(kw in combined for kw in ["create-", "music", "movie", "voice", "story", "horus"]):
        return "creative"
    if any(kw in combined for kw in ["security", "sparta", "hack", "scan", "cmmc", "cui"]):
        return "security"
    if any(kw in combined for kw in ["learn-", "ingest-", "extract", "corpus", "datalake"]):
        return "knowledge"
    if any(kw in combined for kw in ["persona", "consult", "journal", "converse"]):
        return "persona"

    source = item.get("source", "")
    if source == "package":
        return "packages"

    return "skills"


# ---------------------------------------------------------------------------
# Main Pipeline
# ---------------------------------------------------------------------------

def learn_os(
    depth: str = "standard",
    dry_run: bool = False,
    monitor: Optional[AskMonitor] = None,
    run_state: Optional[AskRunState] = None,
) -> dict:
    """Full OS learning pipeline: crawl → extract → tag → store.

    Args:
        depth: "quick", "standard", or "deep"
        dry_run: Preview without storing
        monitor: Optional progress monitor

    Returns:
        Stats dict with crawl counts, QRA counts, store stats
    """
    start = time.time()
    cfg = DEPTH_CONFIG.get(depth, DEPTH_CONFIG["standard"])
    stats = {
        "depth": depth,
        "skills_crawled": 0,
        "packages_crawled": 0,
        "configs_crawled": 0,
        "qras_generated": 0,
        "graph_edges": 0,
        "stored": 0,
        "errors": 0,
        "dry_run": dry_run,
    }

    print(f"\n== /ask os learn ==")
    print(f"   Depth: {depth}")
    if dry_run:
        print("   [DRY RUN]")
    print()

    # Step 1: Crawl skills
    print("   [1/5] Crawling skills...")
    if run_state:
        run_state.step_started("os_crawl_skills")
    skills = crawl_skills(max_skills=cfg["max_skills"])
    stats["skills_crawled"] = len(skills)
    print(f"         Found {len(skills)} skills")
    if run_state:
        run_state.step_finished("os_crawl_skills", skills_crawled=len(skills))

    # Step 2: Crawl packages
    print("   [2/5] Crawling packages...")
    if run_state:
        run_state.step_started("os_crawl_packages")
    packages = crawl_packages(max_packages=cfg["max_packages"])
    stats["packages_crawled"] = len(packages)
    print(f"         Found {len(packages)} packages")
    if run_state:
        run_state.step_finished("os_crawl_packages", packages_crawled=len(packages))

    # Step 3: Crawl config
    print("   [3/5] Crawling configuration...")
    if run_state:
        run_state.step_started("os_crawl_config")
    configs = crawl_config()
    stats["configs_crawled"] = len(configs)
    print(f"         Found {len(configs)} config items")
    if run_state:
        run_state.step_finished("os_crawl_config", configs_crawled=len(configs))

    # Step 4: Build capability graph
    print("   [4/5] Building capability graph...")
    if run_state:
        run_state.step_started("os_build_graph")
    graph = build_capability_graph(skills)
    stats["graph_edges"] = len(graph.get("edges", []))
    print(f"         {stats['graph_edges']} composition edges")
    if run_state:
        run_state.step_finished("os_build_graph", graph_edges=stats["graph_edges"])

    # Step 5: Generate QRAs
    print("   [5/5] Generating QRA triples...")
    if run_state:
        run_state.step_started("os_generate_qra")
    qras = generate_os_qra(skills, packages, configs, graph)

    # Add domain tags
    for qra in qras:
        tags = qra.get("tags", [])
        # Infer domain from tags
        for tag in tags:
            if tag.startswith("skill:"):
                skill_name = tag.split(":", 1)[1]
                matching = [s for s in skills if s["name"] == skill_name]
                if matching:
                    domain = classify_domain(matching[0])
                    domain_tag = f"domain:{domain}"
                    if domain_tag not in tags:
                        tags.append(domain_tag)
            elif tag.startswith("package:"):
                if "domain:packages" not in tags:
                    tags.append("domain:packages")

    # Bridge tagging (only for standard+ depth)
    if cfg.get("generate_qra", True):
        print("         Tagging with bridges...")
        qras = tag_qras_with_bridges(qras)

    stats["qras_generated"] = len(qras)
    print(f"         {len(qras)} QRA triples generated")
    if run_state:
        run_state.step_finished("os_generate_qra", qras_generated=len(qras))

    if dry_run:
        # Show sample QRAs
        print("\n   Sample QRAs (dry run):")
        for qra in qras[:5]:
            print(f"     Q: {qra['question']}")
            print(f"     A: {qra['answer'][:100]}...")
            print(f"     Tags: {qra.get('tags', [])}")
            print()
        elapsed = time.time() - start
        print(f"\n== OS Learn Complete (dry run, {elapsed:.1f}s) ==")
        print(f"   Would store {len(qras)} QRA triples to memory (scope=os)")
        return stats

    # Store to memory
    print("\n   Storing to memory (scope=os)...")
    if run_state:
        run_state.step_started("os_store_memory", dry_run=dry_run)
    store_stats = store_qra_to_memory(qras, scope="os", dry_run=dry_run)
    stats["stored"] = store_stats["stored"]
    stats["errors"] = store_stats["errors"]
    if run_state:
        run_state.step_finished("os_store_memory", stored=stats["stored"], errors=stats["errors"])

    elapsed = time.time() - start
    print(f"\n== OS Learn Complete ({elapsed:.1f}s) ==")
    print(f"   Skills:    {stats['skills_crawled']}")
    print(f"   Packages:  {stats['packages_crawled']}")
    print(f"   Configs:   {stats['configs_crawled']}")
    print(f"   QRAs:      {stats['qras_generated']}")
    print(f"   Stored:    {stats['stored']}")
    if stats["errors"]:
        print(f"   Errors:    {stats['errors']}")
    print()

    return stats


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

app = typer.Typer(help="/ask os learn — Index embry-os internal knowledge")


@app.command("learn")
def cmd_learn(
    depth: str = typer.Option("standard", help="Crawl depth: quick, standard, deep"),
    dry_run: bool = typer.Option(False, help="Preview without storing"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
    ask_id: Optional[str] = typer.Option(None, "--ask-id", help="Stable runtime artifact id for this OS learn call"),
    run_output_root: Optional[str] = typer.Option(None, "--run-output-root", help="Directory for runtime artifacts"),
    overwrite_run: bool = typer.Option(False, "--overwrite", help="Replace an existing run directory for --ask-id"),
    resume_run: bool = typer.Option(False, "--resume", help="Resume a non-terminal existing run directory for --ask-id"),
    debug: bool = typer.Option(False, help="Enable debug logging"),
):
    """Crawl and index embry-os knowledge into memory."""
    if debug:
        log.remove()
        log.add(sys.stderr, level="DEBUG")

    if depth not in DEPTH_CONFIG:
        print(f"Invalid depth: {depth}. Use: quick, standard, deep")
        raise SystemExit(1)

    request = {"command": "os learn", "depth": depth, "dry_run": dry_run}
    if dry_run:
        print_execution_spec(build_os_learn_dry_run_spec(request), as_json=as_json)
        raise typer.Exit(code=0)

    run_state = AskRunState(
        ask_id or make_run_id(f"os learn {depth}"),
        output_root=run_output_root,
        overwrite=overwrite_run,
        resume=resume_run,
    )
    run_state.write_request(request)
    try:
        stats = learn_os(depth=depth, dry_run=dry_run, run_state=run_state)
    except Exception as exc:
        run_state.fail(exc)
        raise
    run_state.finish(stats, state="completed" if stats["stored"] > 0 or stats.get("dry_run") else "no_results")

    if as_json:
        print(json.dumps(stats, indent=2))

    raise SystemExit(0 if stats["stored"] > 0 or stats.get("dry_run") else 1)


if __name__ == "__main__":
    app()
