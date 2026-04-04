"""Persona Integration core module for create-movie.

PersonaContext dataclass, PersonaIntegration class, BRIDGE_PROMPT_AUGMENTS,
singleton accessor, and convenience functions.
"""

import json
import subprocess
import sys
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from loguru import logger


def _find_project_root() -> Path:
    """Find project root by traversing up to .git directory."""
    start = Path(__file__).resolve().parent
    for parent in [start] + list(start.parents):
        if (parent / ".git").exists():
            return parent
    try:
        from dotenv import find_dotenv
        dotenv_path = find_dotenv(usecwd=True)
        if dotenv_path:
            return Path(dotenv_path).parent
    except ImportError:
        pass
    return Path.cwd()


_PROJECT_ROOT = _find_project_root()

try:
    from dotenv import load_dotenv
    _root_env = _PROJECT_ROOT / ".env"
    if _root_env.exists():
        load_dotenv(_root_env, override=False)
except ImportError:
    pass

_COMMON_SKILLS_PATH = _PROJECT_ROOT / ".agent" / "skills"
if _COMMON_SKILLS_PATH.exists() and str(_COMMON_SKILLS_PATH) not in sys.path:
    sys.path.insert(0, str(_COMMON_SKILLS_PATH))

PERSONA_PROJECT_PATH = os.environ.get(
    "PERSONA_PROJECT_PATH",
    str(_PROJECT_ROOT / "memory" / "persona")
)
MEMORY_PROJECT_PATH = os.environ.get(
    "MEMORY_PROJECT_PATH",
    str(_PROJECT_ROOT / "memory")
)

_persona_paths = [
    PERSONA_PROJECT_PATH,
    str(Path(PERSONA_PROJECT_PATH).parent),
    str(Path(PERSONA_PROJECT_PATH) / "code"),
    str(Path(PERSONA_PROJECT_PATH) / "bridge"),
]
for p in _persona_paths:
    if p not in sys.path and Path(p).exists():
        sys.path.insert(0, p)


@dataclass
class PersonaContext:
    """Context package from persona system for screenplay generation."""
    episodic: list
    semantic: list
    federated: list
    user_state: Optional[dict] = None
    bridge_attributes: list = None

    def __post_init__(self):
        if self.bridge_attributes is None:
            self.bridge_attributes = []

    def render(self) -> str:
        """Render as prompt-friendly context string."""
        sections = []

        if self.federated:
            sections.append("## Thematic Connections (Horus Lore)")
            for item in self.federated[:3]:
                if isinstance(item, dict):
                    text = item.get('text', item.get('full_text', str(item)))[:150]
                    bridges = item.get('shared_bridges', [])
                    sections.append(f"- {text}... [bridges: {', '.join(bridges)}]")

        if self.semantic:
            sections.append("## Technical Knowledge")
            for doc in self.semantic[:2]:
                text = doc.get('text', doc.get('content', str(doc)))[:100]
                sections.append(f"- {text}...")

        if self.bridge_attributes:
            sections.append(f"## Thematic Bridges: {', '.join(self.bridge_attributes)}")

        return "\n\n".join(sections) if sections else ""

    def to_dict(self) -> dict:
        return {
            "episodic": self.episodic,
            "semantic": self.semantic,
            "federated": self.federated,
            "user_state": self.user_state,
            "bridge_attributes": self.bridge_attributes
        }


class PersonaIntegration:
    """
    Unified persona integration for create-movie.

    Handles lazy loading of persona components and graceful degradation
    when persona system is unavailable.
    """

    def __init__(self):
        self._context_engineer = None
        self._taxonomy_verifier = None
        self._tts_client = None
        self._available = None

    @property
    def available(self) -> bool:
        """Check if persona system is available."""
        if self._available is None:
            self._available = Path(PERSONA_PROJECT_PATH).exists()
        return self._available

    @property
    def context_engineer(self):
        """Lazy load ContextEngineer."""
        if self._context_engineer is None and self.available:
            try:
                from context_engineering import create_context_engineer
                self._context_engineer = create_context_engineer()
            except ImportError as e:
                print(f"[persona] ContextEngineer unavailable: {e}")
        return self._context_engineer

    @property
    def taxonomy_verifier(self):
        """Lazy load HorusTaxonomyVerifier."""
        if self._taxonomy_verifier is None and self.available:
            try:
                from horus_taxonomy_verifier import create_verifier
                self._taxonomy_verifier = create_verifier()
            except ImportError:
                try:
                    from persona.bridge.horus_taxonomy_verifier import create_verifier
                    self._taxonomy_verifier = create_verifier()
                except ImportError as e:
                    print(f"[persona] TaxonomyVerifier unavailable: {e}")
        return self._taxonomy_verifier

    @property
    def tts_client(self):
        """Lazy load HorusTTSClient."""
        if self._tts_client is None and self.available:
            try:
                from tts_client import HorusTTSClient
                config_path = Path(PERSONA_PROJECT_PATH) / "configs" / "tts" / "horus_qwen3_1.7b.yaml"
                if not config_path.exists():
                    config_path = Path(MEMORY_PROJECT_PATH) / "configs" / "tts" / "horus_qwen3_1.7b.yaml"
                if config_path.exists():
                    self._tts_client = HorusTTSClient(config_path)
                else:
                    print(f"[persona] TTS config not found at {config_path}")
            except ImportError as e:
                print(f"[persona] TTSClient unavailable: {e}")
        return self._tts_client

    def get_screenplay_context(self, prompt: str, user_id: str = "horus_filmmaker") -> PersonaContext:
        """Get persona-enriched context for screenplay generation."""
        if not self.context_engineer:
            return PersonaContext(episodic=[], semantic=[], federated=[])

        try:
            pkg = self.context_engineer.build_for_horus(prompt, user_id)
            bridges = set()
            for item in pkg.federated:
                if isinstance(item, dict):
                    bridges.update(item.get('shared_bridges', []))

            return PersonaContext(
                episodic=pkg.episodic,
                semantic=pkg.semantic,
                federated=pkg.federated,
                user_state=pkg.user_state,
                bridge_attributes=list(bridges)
            )
        except Exception as e:
            print(f"[persona] Context retrieval failed: {e}")
            return PersonaContext(episodic=[], semantic=[], federated=[])

    def extract_cinematography_bridges(self, scene_description: str) -> list[str]:
        """Extract HMT bridge attributes from a scene description."""
        if not self.taxonomy_verifier:
            return []

        try:
            doc = {
                "full_text": scene_description,
                "collection": "operational"
            }
            features = self.taxonomy_verifier.extract_features(doc)
            return features.bridge_attributes
        except Exception as e:
            print(f"[persona] Bridge extraction failed: {e}")
            return []

    def synthesize_narration(self, text: str, output_path: Path, max_seconds: float = 30.0) -> Optional[Path]:
        """Generate Horus voice narration using Qwen3-TTS."""
        if not self.tts_client:
            return self._tts_fallback(text, output_path)

        try:
            return self.tts_client.synthesize(text, output_path, max_seconds)
        except Exception as e:
            print(f"[persona] TTS synthesis failed: {e}")
            return self._tts_fallback(text, output_path)

    def _tts_fallback(self, text: str, output_path: Path) -> Optional[Path]:
        """Fallback to tts-train skill for synthesis."""
        skill_dir = Path(__file__).parent.parent

        tts_skill = skill_dir / "tts-train" / "run.sh"
        if tts_skill.exists():
            try:
                result = subprocess.run(
                    ["bash", str(tts_skill), "synthesize", "--text", text, "--output", str(output_path)],
                    capture_output=True, text=True, timeout=60,
                    cwd=str(tts_skill.parent),
                    env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
                )
                if result.returncode == 0 and output_path.exists():
                    return output_path
            except Exception as e:
                logger.debug("result extraction failed: {}", e)

        print(f"[persona] No TTS available, skipping narration for: {text[:50]}...")
        return None

    def archive_creation_session(
        self,
        project_name: str,
        prompt: str,
        phases_completed: list[str],
        output_path: Optional[str],
        bridges_used: list[str],
        duration_seconds: float
    ) -> bool:
        """Archive the movie creation session to episodic memory."""
        if not self.available:
            return False

        episode = {
            "type": "movie_creation",
            "project_name": project_name,
            "prompt": prompt,
            "phases_completed": phases_completed,
            "output_path": output_path,
            "bridge_attributes": bridges_used,
            "duration_seconds": duration_seconds,
            "timestamp": datetime.now().isoformat(),
            "scope": "horus-filmmaking"
        }

        try:
            import httpx
            transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
            with httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0) as client:
                resp = client.post("/learn", json={
                    "problem": f"Created movie: {project_name}",
                    "solution": json.dumps(episode),
                    "scope": "horus-filmmaking",
                    "tags": ["movie", "creation", *bridges_used],
                })
                return resp.status_code == 200
        except Exception as e:
            print(f"[persona] Episodic archiving failed: {e}")

        return False

    def get_lore_for_theme(self, theme: str, limit: int = 3) -> list[dict]:
        """Retrieve Horus lore entries matching a theme."""
        if not self.taxonomy_verifier:
            return []

        try:
            import httpx
            transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
            with httpx.Client(transport=transport, base_url="http://localhost", timeout=15.0) as client:
                resp = client.post("/recall", json={
                    "q": theme,
                    "scope": "horus_lore",
                    "k": limit,
                })
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list):
                        return data[:limit]
                    items = data.get("items", data.get("results", []))
                    return items[:limit]
        except Exception as e:
            print(f"[persona] Lore retrieval failed: {e}")

        return []


# Bridge attribute descriptions for prompt augmentation
BRIDGE_PROMPT_AUGMENTS = {
    "Precision": {
        "visual": "methodical framing, geometric composition, calculated camera movement",
        "narrative": "deliberate pacing, strategic reveals, mathematical tension",
        "examples": ["siege warfare", "calculated betrayal", "iron fortresses"]
    },
    "Resilience": {
        "visual": "static wide shots, monumental architecture, weathered textures",
        "narrative": "endurance themes, last stands, unwavering resolve",
        "examples": ["Siege of Terra", "Imperial Fists", "unyielding walls"]
    },
    "Fragility": {
        "visual": "shattered glass, cracked surfaces, delicate lighting",
        "narrative": "breaking points, tragic flaws, irreversible mistakes",
        "examples": ["Webway collapse", "Magnus's Folly", "broken oaths"]
    },
    "Corruption": {
        "visual": "creeping shadows, color degradation, organic distortion",
        "narrative": "gradual descent, insidious influence, loss of self",
        "examples": ["Davin corruption", "Warp taint", "Chaos possession"]
    },
    "Loyalty": {
        "visual": "golden light, ceremonial compositions, brotherhood imagery",
        "narrative": "oaths kept, sacrifice for others, trust tested",
        "examples": ["Luna Wolves brotherhood", "Oaths of Moment", "Loken's integrity"]
    },
    "Stealth": {
        "visual": "shadows, obscured faces, layered depth of field",
        "narrative": "hidden agendas, misdirection, secrets within secrets",
        "examples": ["Alpha Legion operations", "infiltration", "Alpharius deception"]
    }
}


def augment_prompt_with_bridges(base_prompt: str, bridges: list[str]) -> str:
    """Augment a visual/narrative prompt with bridge-specific keywords."""
    augments = []

    for bridge in bridges:
        if bridge in BRIDGE_PROMPT_AUGMENTS:
            info = BRIDGE_PROMPT_AUGMENTS[bridge]
            augments.append(info["visual"])

    if augments:
        return f"{base_prompt}, {', '.join(augments)}"
    return base_prompt


def get_bridge_examples(bridges: list[str]) -> list[str]:
    """Get lore examples for the given bridges to use as creative anchors."""
    examples = []
    for bridge in bridges:
        if bridge in BRIDGE_PROMPT_AUGMENTS:
            examples.extend(BRIDGE_PROMPT_AUGMENTS[bridge]["examples"])
    return examples


# Singleton instance for easy access
_persona = None

def get_persona() -> PersonaIntegration:
    """Get the singleton PersonaIntegration instance."""
    global _persona
    if _persona is None:
        _persona = PersonaIntegration()
    return _persona


def enrich_screenplay_context(prompt: str, persona_id: str = "default") -> PersonaContext:
    """Convenience function to get persona context for screenplay."""
    return get_persona().get_screenplay_context(prompt, user_id=f"{persona_id}_filmmaker")


def extract_bridges(scene_description: str) -> list[str]:
    """Convenience function to extract bridges from scene description."""
    return get_persona().extract_cinematography_bridges(scene_description)


def generate_narration(text: str, output_path: Path, persona_id: str = "default") -> Optional[Path]:
    """Convenience function to generate voice narration for the configured persona."""
    return get_persona().synthesize_narration(text, output_path)


# Alias for backwards compatibility
generate_horus_narration = generate_narration


def archive_session(project_name: str, prompt: str, phases: list, output: str, bridges: list, duration: float) -> bool:
    """Convenience function to archive creation session."""
    return get_persona().archive_creation_session(project_name, prompt, phases, output, bridges, duration)
