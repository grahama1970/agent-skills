"""
Research Bridge for create-storyboard skill.

Integrates with /dogpile for researching filmmaking techniques when:
1. A film reference is mentioned but not in memory
2. A specific technique needs explanation
3. The agent needs to learn about a cinematography concept

Also provides hooks to /memory for storing and recalling learned techniques.
"""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List

# Paths to integrated skills
SKILLS_DIR = Path(__file__).parent.parent
DOGPILE_PATH = SKILLS_DIR / "dogpile"
MEMORY_PATH = SKILLS_DIR / "memory"


@dataclass
class ResearchResult:
    """Result from a research query."""
    query: str
    found: bool
    summary: str
    sources: List[str]
    techniques: List[dict]
    raw_content: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "found": self.found,
            "summary": self.summary,
            "sources": self.sources,
            "techniques": self.techniques
        }


def research_film_techniques(film_name: str, aspect: str = "cinematography") -> ResearchResult:
    """
    Research cinematography techniques from a specific film using /dogpile.
    
    Args:
        film_name: Name of the film to research
        aspect: Specific aspect (cinematography, lighting, camera, editing)
    
    Returns:
        ResearchResult with found techniques
    """
    query = f"{film_name} {aspect} techniques camera shots lighting"
    
    # Call dogpile skill
    dogpile_cmd = [
        "python3", str(DOGPILE_PATH / "run.py"),
        "search",
        "--query", query,
        "--sources", "brave,youtube,arxiv",
        "--format", "json"
    ]
    
    try:
        result = subprocess.run(
            dogpile_cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=DOGPILE_PATH
        )
        
        if result.returncode == 0:
            data = json.loads(result.stdout)
            
            # Extract relevant techniques from results
            techniques = []
            sources = []
            
            for item in data.get('results', []):
                sources.append(item.get('url', item.get('source', 'Unknown')))
                
                # Parse content for technique information
                content = item.get('content', '')
                if any(kw in content.lower() for kw in ['shot', 'camera', 'light', 'frame', 'lens']):
                    techniques.append({
                        "description": content[:500],
                        "source": item.get('source', 'web')
                    })
            
            return ResearchResult(
                query=query,
                found=len(techniques) > 0,
                summary=data.get('summary', f"Research on {film_name} {aspect}"),
                sources=sources[:5],
                techniques=techniques[:3],
                raw_content=result.stdout
            )
        
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as e:
        pass
    
    # Fallback: return empty result
    return ResearchResult(
        query=query,
        found=False,
        summary=f"Could not research {film_name}. Try /dogpile manually.",
        sources=[],
        techniques=[]
    )


def research_technique(technique_name: str) -> ResearchResult:
    """
    Research a specific cinematography technique using /dogpile.
    
    Args:
        technique_name: Name of technique (e.g., "dolly zoom", "chiaroscuro lighting")
    
    Returns:
        ResearchResult with technique explanation and examples
    """
    query = f"cinematography {technique_name} how to when to use film examples"
    
    dogpile_cmd = [
        "python3", str(DOGPILE_PATH / "run.py"),
        "search",
        "--query", query,
        "--sources", "brave,youtube",
        "--format", "json"
    ]
    
    try:
        result = subprocess.run(
            dogpile_cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=DOGPILE_PATH
        )
        
        if result.returncode == 0:
            data = json.loads(result.stdout)
            
            techniques = []
            sources = []
            
            for item in data.get('results', []):
                sources.append(item.get('url', 'Unknown'))
                content = item.get('content', '')
                if content:
                    techniques.append({
                        "description": content[:500],
                        "source": item.get('source', 'web')
                    })
            
            return ResearchResult(
                query=query,
                found=len(techniques) > 0,
                summary=data.get('summary', f"Research on {technique_name}"),
                sources=sources[:5],
                techniques=techniques[:3]
            )
    
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        pass
    
    return ResearchResult(
        query=query,
        found=False,
        summary=f"Could not research {technique_name}. Try /dogpile manually.",
        sources=[],
        techniques=[]
    )


def recall_or_research(topic: str, scope: str = "horus-storyboarding") -> dict:
    """
    First check /memory, then fall back to /dogpile research.
    
    This is the primary interface for the storyboard skill to get information.
    
    Args:
        topic: What to look up (film name, technique, concept)
        scope: Memory scope to search
    
    Returns:
        Dict with source ('memory' or 'research'), content, and action recommendations
    """
    from memory_bridge import recall_techniques
    
    # First, try memory
    memory_results = recall_techniques(topic, scope=scope, limit=3)
    
    if memory_results and any(r.found for r in memory_results):
        # Found in memory
        return {
            "source": "memory",
            "found": True,
            "content": [r.content for r in memory_results if r.found],
            "action": None,
            "message": f"Found '{topic}' in memory from previous learnings."
        }
    
    # Not in memory - offer to research
    return {
        "source": "needs_research",
        "found": False,
        "content": [],
        "action": "research",
        "message": f"'{topic}' not found in memory. Should I research it with /dogpile?",
        "research_query": topic
    }


def research_and_store(topic: str, scope: str = "horus-storyboarding") -> dict:
    """
    Research a topic with /dogpile and store results in /memory.
    
    This is called when the agent confirms they want to research.
    """
    from memory_bridge import learn_technique
    
    # Determine if this is a film or a technique
    if any(word in topic.lower() for word in ['shot', 'lighting', 'camera', 'movement', 'framing']):
        result = research_technique(topic)
    else:
        result = research_film_techniques(topic)
    
    if result.found:
        # Store in memory for future recall
        for i, tech in enumerate(result.techniques):
            learn_technique(
                technique_name=f"{topic} technique {i+1}",
                description=tech.get('description', ''),
                source=f"dogpile:{tech.get('source', 'web')}",
                metadata={"research_query": result.query},
                scope=scope
            )
        
        return {
            "source": "research",
            "found": True,
            "content": result.techniques,
            "sources": result.sources,
            "message": f"Researched '{topic}' and stored {len(result.techniques)} techniques in memory.",
            "stored_in_memory": True
        }
    
    return {
        "source": "research",
        "found": False,
        "content": [],
        "message": f"Could not find information about '{topic}'. Try a more specific search.",
        "stored_in_memory": False
    }


def generate_research_questions(parsed_scenes: dict) -> list[dict]:
    """
    Analyze scenes and generate research questions for unknown references.
    
    Returns questions that can be presented in the collaboration loop.
    """
    questions = []
    
    for scene in parsed_scenes.get('scenes', []):
        notes = scene.get('notes', {})
        scene_num = scene.get('number', 1)
        
        # Check for film references
        for ref in notes.get('references', []):
            lookup = recall_or_research(ref)
            
            if not lookup['found']:
                questions.append({
                    "id": f"research_s{scene_num}_{len(questions)}",
                    "scene_number": scene_num,
                    "type": "research_offer",
                    "question": f"Scene {scene_num} references '{ref}' but I don't have it in memory. Should I research this with /dogpile to learn the cinematography techniques used?",
                    "options": ["yes_research", "no_skip", "i_will_describe"],
                    "topic": ref,
                    "context": lookup['message']
                })
        
        # Check for unfamiliar techniques mentioned
        for camera_note in notes.get('camera', []):
            # Check if it's a technique we might not know
            unknown_techniques = extract_unknown_techniques(camera_note)
            for tech in unknown_techniques:
                questions.append({
                    "id": f"research_tech_s{scene_num}_{len(questions)}",
                    "scene_number": scene_num,
                    "type": "research_offer",
                    "question": f"Scene {scene_num} mentions '{tech}'. Should I research this technique to understand when and how to use it effectively?",
                    "options": ["yes_research", "no_i_know_it", "skip"],
                    "topic": tech
                })
    
    return questions


def extract_unknown_techniques(camera_note: str) -> list[str]:
    """
    Extract technique names from a camera note that might need research.
    """
    # Common techniques we already know (in shot_taxonomy and creative_suggestions)
    KNOWN_TECHNIQUES = {
        'push in', 'pull back', 'dolly', 'track', 'pan', 'tilt', 'zoom',
        'handheld', 'steadicam', 'static', 'locked off', 'whip pan',
        'close up', 'wide shot', 'medium shot', 'establishing',
        'low key', 'high key', 'practical', 'rim light', 'backlight'
    }
    
    # Look for technique-like phrases not in our known set
    unknown = []
    note_lower = camera_note.lower()
    
    # Simple heuristic: look for capitalized terms or quoted phrases
    import re
    
    # Find quoted terms
    quoted = re.findall(r'"([^"]+)"', camera_note)
    quoted += re.findall(r"'([^']+)'", camera_note)
    
    for term in quoted:
        if term.lower() not in KNOWN_TECHNIQUES:
            unknown.append(term)
    
    # Find terms that look like technique names (e.g., "Vertigo shot")
    technique_pattern = re.findall(r'\b([A-Z][a-z]+(?:\s+[a-z]+)*\s+(?:shot|move|movement|effect|technique|lighting))\b', camera_note)
    for term in technique_pattern:
        if term.lower() not in KNOWN_TECHNIQUES:
            unknown.append(term)
    
    return unknown[:3]  # Limit to 3 per note


def format_research_for_suggestion(result: ResearchResult) -> str:
    """Format research results as a creative suggestion."""
    if not result.found:
        return f"I couldn't find detailed information about '{result.query}'. You might want to describe what you're looking for."
    
    lines = [
        f"📚 **Research Results for '{result.query}'**",
        "",
        f"{result.summary}",
        ""
    ]
    
    for i, tech in enumerate(result.techniques, 1):
        lines.append(f"**{i}.** {tech.get('description', '')[:200]}...")
        if tech.get('source'):
            lines.append(f"   *Source: {tech['source']}*")
        lines.append("")
    
    if result.sources:
        lines.append("*References:*")
        for src in result.sources[:3]:
            lines.append(f"  - {src}")
    
    return "\n".join(lines)
