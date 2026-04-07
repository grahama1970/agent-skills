"""
Memory Bridge for create-storyboard skill.

Integrates with /memory skill to:
1. RECALL learned filmmaking techniques from ingested movies
2. LEARN new techniques after completing storyboards
3. Search for specific references mentioned in screenplays

Uses the 'horus-storyboarding' scope for storyboard-specific learnings.
"""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# Memory scope for storyboard learnings
MEMORY_SCOPE = "horus-storyboarding"

# Path to memory skill
MEMORY_SKILL_PATH = Path(__file__).parent.parent / "memory"


@dataclass
class MemoryResult:
    """Result from a memory query."""
    found: bool
    content: str
    source: Optional[str] = None
    relevance: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            "found": self.found,
            "content": self.content,
            "source": self.source,
            "relevance": self.relevance
        }


@dataclass
class FilmTechnique:
    """A learned filmmaking technique from memory."""
    name: str
    description: str
    source_film: Optional[str] = None
    scene_context: Optional[str] = None
    camera_setup: Optional[str] = None
    lighting: Optional[str] = None
    emotional_effect: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "source_film": self.source_film,
            "scene_context": self.scene_context,
            "camera_setup": self.camera_setup,
            "lighting": self.lighting,
            "emotional_effect": self.emotional_effect
        }
    
    def format_for_suggestion(self) -> str:
        """Format as a suggestion for the creative dialogue."""
        lines = [f"**{self.name}**"]
        if self.source_film:
            lines.append(f"From: {self.source_film}")
        lines.append(self.description)
        if self.camera_setup:
            lines.append(f"Camera: {self.camera_setup}")
        if self.lighting:
            lines.append(f"Lighting: {self.lighting}")
        if self.emotional_effect:
            lines.append(f"Effect: {self.emotional_effect}")
        return "\n".join(lines)


def recall_techniques(query: str, scope: str = MEMORY_SCOPE, limit: int = 5) -> list[MemoryResult]:
    """
    Recall techniques from memory based on a query.
    
    Example queries:
    - "Blade Runner 2049 lighting techniques"
    - "tension building camera movements"
    - "emotional close-up techniques"
    """
    results = []
    
    # Try to call memory skill
    memory_cmd = [
        "python3", str(MEMORY_SKILL_PATH / "run.py"),
        "recall",
        "--query", query,
        "--scope", scope,
        "--limit", str(limit),
        "--format", "json"
    ]
    
    try:
        result = subprocess.run(
            memory_cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=MEMORY_SKILL_PATH
        )
        
        if result.returncode == 0:
            # Parse JSON output
            data = json.loads(result.stdout)
            for item in data.get('results', []):
                results.append(MemoryResult(
                    found=True,
                    content=item.get('content', ''),
                    source=item.get('source'),
                    relevance=item.get('relevance', 0.0)
                ))
        else:
            # Memory skill failed - return empty results
            pass
            
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        # Memory skill not available or failed
        pass
    
    return results


def recall_film_reference(film_name: str) -> list[FilmTechnique]:
    """
    Recall specific techniques learned from a referenced film.
    
    This searches memory for techniques associated with a specific film,
    typically ingested via /ingest-movie.
    """
    techniques = []
    
    # Search for the film in memory
    query = f"cinematography techniques from {film_name}"
    results = recall_techniques(query, scope="horus-movies")
    
    for r in results:
        if r.found and r.content:
            # Parse the content into a technique
            # This expects structured content from /ingest-movie
            try:
                # Try to parse as JSON first
                data = json.loads(r.content)
                techniques.append(FilmTechnique(
                    name=data.get('technique', 'Unknown'),
                    description=data.get('description', r.content),
                    source_film=film_name,
                    scene_context=data.get('scene_context'),
                    camera_setup=data.get('camera'),
                    lighting=data.get('lighting'),
                    emotional_effect=data.get('effect')
                ))
            except json.JSONDecodeError:
                # Plain text result
                techniques.append(FilmTechnique(
                    name=f"Technique from {film_name}",
                    description=r.content[:200],
                    source_film=film_name
                ))
    
    # If no results from memory, return built-in knowledge for common films
    if not techniques:
        techniques = get_builtin_film_knowledge(film_name)
    
    return techniques


def get_builtin_film_knowledge(film_name: str) -> list[FilmTechnique]:
    """
    Built-in knowledge for common film references when memory is empty.
    
    This serves as a fallback and demonstrates what kind of knowledge
    should be ingested via /ingest-movie.
    """
    film_lower = film_name.lower()
    
    # Common film references and their techniques
    FILM_KNOWLEDGE = {
        "blade runner": [
            FilmTechnique(
                name="Blade Runner Noir Lighting",
                description="Heavy use of venetian blind shadows, neon color, and atmospheric haze",
                source_film="Blade Runner (1982)",
                lighting="Low-key with strong motivated sources, blue/orange color palette",
                camera_setup="Slow tracking shots, low angles for oppressive atmosphere",
                emotional_effect="Melancholic, mysterious, existential"
            ),
            FilmTechnique(
                name="Blade Runner Interview Framing",
                description="Extreme close-ups of eyes during interrogation scenes",
                source_film="Blade Runner (1982)",
                camera_setup="ECU on eyes, locked-off, very shallow depth of field",
                lighting="Strong key light from below, rim light separation",
                emotional_effect="Invasive, dehumanizing, clinical"
            )
        ],
        "blade runner 2049": [
            FilmTechnique(
                name="2049 Minimal Composition",
                description="Desolate, geometric framing with single figures in vast spaces",
                source_film="Blade Runner 2049 (2017)",
                camera_setup="Extreme wide shots, centered subjects, symmetrical composition",
                lighting="Diffused, atmospheric, monochromatic color schemes per scene",
                emotional_effect="Isolation, loneliness, existential scale"
            ),
            FilmTechnique(
                name="2049 Hologram Lighting",
                description="Practical holographic light sources that interact with characters",
                source_film="Blade Runner 2049 (2017)",
                lighting="Magenta/cyan holographic glow as key light, minimal fill",
                emotional_effect="Artificial intimacy, technological loneliness"
            )
        ],
        "godfather": [
            FilmTechnique(
                name="Godfather Chiaroscuro",
                description="Half-lit faces representing moral ambiguity",
                source_film="The Godfather (1972)",
                lighting="Single hard source from above, deep shadows on lower face",
                camera_setup="Eye-level, locked-off, long takes",
                emotional_effect="Power, moral complexity, intimacy with danger"
            )
        ],
        "mad max fury road": [
            FilmTechnique(
                name="Fury Road Center Framing",
                description="Action centered in frame to minimize eye movement during chaos",
                source_film="Mad Max: Fury Road (2015)",
                camera_setup="All action centered, rapid cuts, camera on vehicle",
                emotional_effect="Relentless momentum, clarity in chaos"
            )
        ],
        "moonlight": [
            FilmTechnique(
                name="Moonlight Intimate Handheld",
                description="Close, steady handheld that breathes with the character",
                source_film="Moonlight (2016)",
                camera_setup="Handheld MCU/CU, circling the subject, very close",
                lighting="Naturalistic with strong color accents (blue, purple)",
                emotional_effect="Vulnerability, tenderness, presence"
            )
        ]
    }
    
    for key, techniques in FILM_KNOWLEDGE.items():
        if key in film_lower:
            return techniques
    
    return []


def learn_technique(
    technique_name: str,
    description: str,
    source: str,
    metadata: Optional[dict] = None,
    scope: str = MEMORY_SCOPE
) -> bool:
    """
    Store a new technique in memory for future recall.
    
    Called after completing a storyboard to remember what worked.
    """
    content = {
        "type": "storyboard_technique",
        "name": technique_name,
        "description": description,
        "source": source,
        "metadata": metadata or {}
    }
    
    memory_cmd = [
        "python3", str(MEMORY_SKILL_PATH / "run.py"),
        "learn",
        "--content", json.dumps(content),
        "--scope", scope,
        "--source", f"storyboard:{source}"
    ]
    
    try:
        result = subprocess.run(
            memory_cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=MEMORY_SKILL_PATH
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def search_emotional_techniques(emotion: str) -> list[FilmTechnique]:
    """
    Search memory for techniques that evoke a specific emotion.
    """
    results = recall_techniques(f"{emotion} camera lighting techniques")
    
    techniques = []
    for r in results:
        if r.found:
            techniques.append(FilmTechnique(
                name=f"{emotion.title()} Technique",
                description=r.content,
                emotional_effect=emotion
            ))
    
    # Fallback to built-in emotion mappings
    if not techniques:
        techniques = get_builtin_emotion_techniques(emotion)
    
    return techniques


def get_builtin_emotion_techniques(emotion: str) -> list[FilmTechnique]:
    """Built-in techniques for common emotions."""
    
    EMOTION_TECHNIQUES = {
        "tension": FilmTechnique(
            name="Tension Building",
            description="Slow push-in with held breath pacing",
            camera_setup="Locked tripod, slow dolly in, increasingly tight framing",
            lighting="Low-key, practical sources, deep shadows",
            emotional_effect="Dread, anticipation, unease"
        ),
        "fear": FilmTechnique(
            name="Horror Coverage",
            description="Wide lenses close to face, distorted perspectives",
            camera_setup="Wide lens (24mm or less) for CU, handheld, Dutch angles",
            lighting="Under-lighting, motivated by screen/fire, sharp shadows",
            emotional_effect="Vulnerability, disorientation, dread"
        ),
        "love": FilmTechnique(
            name="Romantic Intimacy",
            description="Soft close-ups with shallow depth of field",
            camera_setup="Long lens (85mm+), shallow DOF, slow movements",
            lighting="Soft wrap-around light, warm tones, backlight",
            emotional_effect="Tenderness, connection, beauty"
        ),
        "anger": FilmTechnique(
            name="Confrontation Coverage",
            description="Dynamic camera with aggressive movement",
            camera_setup="Handheld, whip pans, quick push-ins, low angles",
            lighting="Hard light, high contrast, hot spots",
            emotional_effect="Intensity, threat, volatility"
        ),
        "sadness": FilmTechnique(
            name="Melancholic Stillness",
            description="Static frames with isolated subjects",
            camera_setup="Locked-off wide shots, slow zooms out, negative space",
            lighting="Overcast/diffused, desaturated, practical sources",
            emotional_effect="Isolation, weight, reflection"
        ),
        "contemplative": FilmTechnique(
            name="Contemplative Space",
            description="Patient framing with room to breathe",
            camera_setup="Wide shots, long takes, minimal movement",
            lighting="Natural light, gentle, even",
            emotional_effect="Thought, peace, introspection"
        )
    }
    
    emotion_lower = emotion.lower()
    if emotion_lower in EMOTION_TECHNIQUES:
        return [EMOTION_TECHNIQUES[emotion_lower]]
    
    return []


def enhance_suggestions_with_memory(suggestions: list, parsed_scenes: dict) -> list:
    """
    Enhance creative suggestions by searching memory for relevant techniques.
    
    This is called during the suggestion generation phase to add
    learned knowledge to the recommendations.
    """
    enhanced = []
    
    for suggestion in suggestions:
        s_dict = suggestion.to_dict() if hasattr(suggestion, 'to_dict') else suggestion
        
        # If there's a film reference, look it up
        if s_dict.get('reference'):
            techniques = recall_film_reference(s_dict['reference'])
            if techniques:
                s_dict['memory_context'] = [t.to_dict() for t in techniques]
                s_dict['suggestion'] += f"\n\n📚 From my memory of {s_dict['reference']}:\n"
                for t in techniques[:2]:  # Limit to top 2
                    s_dict['suggestion'] += f"  • {t.format_for_suggestion()}\n"
        
        enhanced.append(s_dict)
    
    return enhanced
