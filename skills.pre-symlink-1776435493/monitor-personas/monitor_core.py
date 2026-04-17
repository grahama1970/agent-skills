"""
Monitor Personas - Core configuration, state management, and persona helpers.

Contains config loading, state persistence, persona dataclass, and shared utilities.
"""

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer
import yaml
from rich.console import Console

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(usecwd=True), override=False)

# Import canonical ingest-youtube channel listing
_SKILLS_DIR = Path(__file__).resolve().parent.parent
_IY_DIR = str(_SKILLS_DIR / "ingest-youtube")
if _IY_DIR not in sys.path:
    sys.path.insert(0, _IY_DIR)
from youtube_transcripts.downloader import list_channel_video_ids

console = Console()

# Paths
SKILL_DIR = Path(__file__).parent
CONFIG_FILE = SKILL_DIR / "personas.yaml"
PROJECT_ROOT = SKILL_DIR.parent.parent.parent

# Default state directory
STATE_DIR = Path(os.environ.get("PERSONA_MONITOR_STATE_DIR", Path.home() / ".pi/monitor-personas"))
STATE_DIR.mkdir(parents=True, exist_ok=True)

STATE_FILE = STATE_DIR / "state.json"
LEARNED_FILE = STATE_DIR / "learned.json"


@dataclass
class PersonaConfig:
    """Configuration for a monitored persona."""
    id: str
    name: str
    priority: str
    scope: str
    sources: List[Dict[str, str]]
    taxonomy_hints: List[str] = field(default_factory=list)
    notes: str = ""
    category: str = ""
    fictional: bool = False
    persona_definition: str = ""
    lore_sources: List[str] = field(default_factory=list)
    feeds_persona: str = ""
    curate_content: Dict[str, Any] = field(default_factory=dict)
    qra_target: int = 0


def load_config() -> Dict[str, Any]:
    """Load personas.yaml configuration."""
    if not CONFIG_FILE.exists():
        typer.echo(f"ERROR: Config file not found: {CONFIG_FILE}", err=True)
        raise typer.Exit(1)

    with open(CONFIG_FILE) as f:
        return yaml.safe_load(f)


def get_all_personas() -> List[PersonaConfig]:
    """Get all personas from config file."""
    config = load_config()
    personas = []

    for category, persona_list in config.items():
        if category == "settings":
            continue
        if not isinstance(persona_list, list):
            continue

        for p in persona_list:
            if not isinstance(p, dict):
                continue
            personas.append(PersonaConfig(
                id=p.get("id", ""),
                name=p.get("name", ""),
                priority=p.get("priority", "LOW"),
                scope=p.get("scope", ""),
                sources=p.get("sources", []),
                taxonomy_hints=p.get("taxonomy_hints", []),
                notes=p.get("notes", ""),
                category=category,
                fictional=p.get("fictional", False),
                persona_definition=p.get("persona_definition", ""),
                lore_sources=p.get("lore_sources", []),
                feeds_persona=p.get("feeds_persona", ""),
                curate_content=p.get("curate_content", {}),
                qra_target=p.get("qra_target", 0),
            ))

    return personas


def get_settings() -> Dict[str, Any]:
    """Get settings from config file."""
    config = load_config()
    return config.get("settings", {})


@dataclass
class SharedLibraryConfig:
    """Configuration for the shared persona datalake."""
    path: str
    subdirs: Dict[str, str]
    relevance: Dict[str, List[str]]

    def get_relevant_personas(self, doc_type: str) -> List[str]:
        """Get persona IDs relevant to a document type."""
        return self.relevance.get(doc_type, [])

    def get_doc_types_for_persona(self, persona_id: str) -> List[str]:
        """Get document types relevant to a persona."""
        return [dt for dt, personas in self.relevance.items() if persona_id in personas]

    def classify_document(self, filename: str, source_type: str = "") -> str:
        """Classify a document into a relevance category based on filename/source.

        Returns the best-matching relevance key, or empty string if no match.
        """
        name_lower = filename.lower()
        source_lower = source_type.lower()

        # Keyword-based classification
        classification_hints = {
            "nist_security": ["nist", "800-53", "800-171", "sp800", "rmf", "oscal"],
            "mil_std": ["mil-std", "mil_std", "do-178", "do-254", "do-326", "arp4754"],
            "mitre": ["mitre", "att&ck", "attack", "d3fend", "cwe", "capec"],
            "formal_methods": ["formal", "lean4", "tla+", "isabelle", "coq", "alloy"],
            "ics_ot": ["ics", "scada", "plc", "ot-", "dragos", "industrial"],
            "certification": ["certification", "accreditation", "assessment", "audit"],
            "space_cyber": ["sparta", "space", "satellite", "gps", "orbital"],
            "manufacturing": ["manufactur", "cnc", "machining", "tolerance", "gd&t"],
            "system_safety": ["safety", "hazard", "fault-tree", "fmea", "mishap"],
        }

        for doc_type, keywords in classification_hints.items():
            for kw in keywords:
                if kw in name_lower or kw in source_lower:
                    return doc_type

        return ""


def get_shared_library_config() -> Optional[SharedLibraryConfig]:
    """Load shared_library configuration from personas.yaml.

    Returns None if shared_library block is not configured.
    """
    config = load_config()
    sl = config.get("shared_library")
    if not sl or not isinstance(sl, dict):
        return None

    return SharedLibraryConfig(
        path=sl.get("path", ""),
        subdirs=sl.get("subdirs", {}),
        relevance=sl.get("relevance", {}),
    )


def get_transcript_dir() -> Path:
    """Get transcript directory from config."""
    settings = get_settings()
    return Path(settings.get("transcript_dir", PROJECT_ROOT / "run/youtube-transcripts"))


def get_youtube_video_count(handle: str) -> int:
    """Get total video count from YouTube channel.

    Delegates to canonical ingest-youtube list_channel_video_ids().
    """
    try:
        video_ids = list_channel_video_ids(handle, max_results=0)
        return len(video_ids)
    except Exception as e:
        typer.echo(f"    Error fetching YouTube count: {e}", err=True)
        return -1


def get_ingested_count(persona_id: str) -> int:
    """Get count of ingested transcripts for a persona."""
    transcript_dir = get_transcript_dir()
    persona_dir = transcript_dir / persona_id
    if not persona_dir.exists():
        return 0

    json_files = list(persona_dir.glob("*.json"))
    return len([f for f in json_files if f.name != ".batch_state.json"])


def load_state() -> Dict[str, Any]:
    """Load monitoring state."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            return {"personas": {}, "last_check": None}
    return {"personas": {}, "last_check": None}


def save_state(state: Dict[str, Any]):
    """Save monitoring state."""
    STATE_FILE.write_text(json.dumps(state, indent=2))


def load_learned() -> set:
    """Load set of already-learned transcript paths."""
    if LEARNED_FILE.exists():
        try:
            return set(json.loads(LEARNED_FILE.read_text()))
        except json.JSONDecodeError:
            return set()
    return set()


def save_learned(learned: set):
    """Save set of learned transcript paths."""
    LEARNED_FILE.write_text(json.dumps(list(learned)))
