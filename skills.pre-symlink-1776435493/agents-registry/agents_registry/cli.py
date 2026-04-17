"""CLI for agents-registry: generate, list, and query agent metadata."""

from __future__ import annotations
import os

import json
import subprocess
import sys
from pathlib import Path

import typer
import yaml
from loguru import logger
import httpx

app = typer.Typer(help="Agent identity registry generator and query tool.")

SKILLS_ROOT = Path(__file__).resolve().parents[3]
AGENTS_DIR = SKILLS_ROOT / "agents"
REGISTRY_PATH = SKILLS_ROOT / "agents-registry.json"
# Removed: memory accessed via httpx to Unix socket (see _memory_cmd)
def _parse_agents_md(path: Path) -> dict | None:
    """Parse a single AGENTS.md and return registry entry."""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning(f"Cannot read {path}: {e}")
        return None

    if not content.startswith("---"):
        logger.warning(f"No frontmatter in {path}")
        return None

    end_idx = content.find("\n---", 3)
    if end_idx == -1:
        logger.warning(f"Unterminated frontmatter in {path}")
        return None

    try:
        fm = yaml.safe_load(content[4:end_idx])
    except yaml.YAMLError as e:
        logger.warning(f"Invalid YAML in {path}: {e}")
        return None

    if not isinstance(fm, dict) or "name" not in fm:
        logger.warning(f"Missing 'name' in frontmatter: {path}")
        return None

    name = fm["name"]
    collaborators_raw = fm.get("collaborators", [])
    collaborators = []
    for c in collaborators_raw if isinstance(collaborators_raw, list) else []:
        # Strip inline comments: "jennifer-cheung    # co-assessor" → "jennifer-cheung"
        clean = str(c).split("#")[0].strip()
        if clean:
            collaborators.append({"id": clean, "role": "peer"})

    return {
        "id": name,
        "name": name,
        "scope": fm.get("scope", name.replace("-", "_")),
        "provides": fm.get("provides", []),
        "composes": fm.get("composes", []),
        "collaborators": collaborators,
        "taxonomy_bridges": fm.get("taxonomy", []),
        "voice": {"enabled": False},
        "inference": {},
        "paths": {"agents_md": str(path.relative_to(SKILLS_ROOT.parent))},
        "active": True,
    }


def _scan_agents() -> list[dict]:
    """Scan .pi/agents/ and return all agent entries."""
    if not AGENTS_DIR.is_dir():
        logger.error(f"Agents directory not found: {AGENTS_DIR}")
        return []

    agents = []
    for agent_dir in sorted(AGENTS_DIR.iterdir()):
        if not agent_dir.is_dir():
            continue
        md_path = agent_dir / "AGENTS.md"
        if not md_path.exists():
            logger.debug(f"Skipping {agent_dir.name}: no AGENTS.md")
            continue
        entry = _parse_agents_md(md_path)
        if entry:
            agents.append(entry)

    return agents


def _sync_to_memory(agents: list[dict]) -> None:
    """Sync agent entries to /memory via learn subcommand."""
    for agent in agents:
        doc = (
            f"Agent: {agent['name']}\n"
            f"Scope: {agent['scope']}\n"
            f"Provides: {', '.join(agent['provides'])}\n"
            f"Composes: {', '.join(agent['composes'])}\n"
            f"Collaborators: {', '.join(c['id'] for c in agent['collaborators'])}\n"
            f"Taxonomy: {', '.join(agent['taxonomy_bridges'])}"
        )
        try:
            subprocess.run(
                [MEMORY_RUN, "learn", "--collection", "agents",
                 "--text", doc, "--tags", f"agent,{agent['name']}"],
                capture_output=True, text=True, timeout=30,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            logger.info(f"Synced {agent['name']} to memory")
        except Exception as e:
            logger.warning(f"Failed to sync {agent['name']}: {e}")


@app.command()
def generate(
    sync_memory: bool = typer.Option(False, "--sync-memory", help="Also sync to /memory"),
    output: Path = typer.Option(REGISTRY_PATH, "--output", "-o", help="Output JSON path"),
) -> None:
    """Scan .pi/agents/ and generate agents-registry.json."""
    agents = _scan_agents()
    if not agents:
        logger.error("No agents found")
        raise typer.Exit(1)

    registry = {
        "version": 1,
        "generated_by": "agents-registry",
        "agent_count": len(agents),
        "agents": agents,
    }

    output.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    logger.info(f"Wrote {len(agents)} agents to {output}")

    if sync_memory:
        _sync_to_memory(agents)

    typer.echo(json.dumps(registry, indent=2))


@app.command("list")
def list_agents() -> None:
    """List all agents from the registry."""
    if not REGISTRY_PATH.exists():
        logger.info("Registry not found, generating...")
        agents = _scan_agents()
    else:
        data = json.loads(REGISTRY_PATH.read_text())
        agents = data.get("agents", [])

    for agent in agents:
        caps = ", ".join(agent.get("provides", [])[:3])
        typer.echo(f"  {agent['id']:<20s} {caps}")


@app.command()
def query(
    capability: str = typer.Option(None, "--capability", "-c", help="Find by capability"),
    agent: str = typer.Option(None, "--agent", "-a", help="Get agent by name"),
) -> None:
    """Query the registry by capability or agent name."""
    if not REGISTRY_PATH.exists():
        agents = _scan_agents()
    else:
        data = json.loads(REGISTRY_PATH.read_text())
        agents = data.get("agents", [])

    if agent:
        matches = [a for a in agents if a["id"] == agent]
    elif capability:
        matches = [a for a in agents if capability in a.get("provides", [])]
    else:
        typer.echo("Specify --capability or --agent")
        raise typer.Exit(1)

    if not matches:
        typer.echo("No matches found")
        raise typer.Exit(1)

    typer.echo(json.dumps(matches, indent=2))


if __name__ == "__main__":
    app()
