"""
Creative Suggestions Module for create-storyboard skill.

Generates filmmaking suggestions with rationale, not just binary questions.
The skill acts as a creative collaborator, proposing techniques and asking
for feedback in natural language.
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class SuggestionCategory(str, Enum):
    """Categories of creative suggestions."""
    CAMERA = "camera"
    LIGHTING = "lighting"
    PACING = "pacing"
    FRAMING = "framing"
    MOVEMENT = "movement"
    TRANSITION = "transition"


@dataclass
class CreativeSuggestion:
    """
    A creative filmmaking suggestion with rationale.
    
    Instead of: "What emotion for Scene 3? [tense/happy/sad]"
    We say: "In Scene 3 where Marcus discovers the letter, I'm thinking 
            we should use a slow push-in to a close-up - it would really 
            sell the emotional weight of that moment. What do you think?"
    """
    id: str
    scene_number: int
    category: SuggestionCategory
    
    # The creative suggestion in natural language
    suggestion: str
    
    # Why this technique works for this scene
    rationale: str
    
    # Specific technique details
    technique: str  # e.g., "slow push-in", "low-key lighting", "Panaflex shot"
    
    # What the agent/user can respond with
    response_options: list[str] = field(default_factory=list)
    
    # Alternative approaches if they disagree
    alternatives: list[str] = field(default_factory=list)
    
    # Reference to learned technique (from /memory)
    reference: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "scene_number": self.scene_number,
            "category": self.category.value,
            "suggestion": self.suggestion,
            "rationale": self.rationale,
            "technique": self.technique,
            "response_options": self.response_options,
            "alternatives": self.alternatives,
            "reference": self.reference
        }
    
    def format_for_conversation(self) -> str:
        """Format as natural conversation for agent/user."""
        lines = [
            f"📍 **Scene {self.scene_number}** - {self.category.value.title()} Suggestion",
            "",
            f"💡 {self.suggestion}",
            "",
            f"📝 *Rationale*: {self.rationale}",
        ]
        
        if self.reference:
            lines.append(f"🎬 *Reference*: {self.reference}")
        
        if self.alternatives:
            lines.append(f"🔄 *Alternatives*: {', '.join(self.alternatives)}")
        
        lines.extend([
            "",
            "What do you think? " + " / ".join(self.response_options)
        ])
        
        return "\n".join(lines)


# Technique library for generating suggestions
CAMERA_TECHNIQUES = {
    "push_in": {
        "name": "Push-In",
        "description": "slowly moving the camera toward the subject",
        "effect": "builds tension and draws the viewer into the emotional moment",
        "best_for": ["emotional", "tense", "revelation"]
    },
    "pull_back": {
        "name": "Pull-Back/Reveal",
        "description": "pulling the camera back to reveal more of the scene",
        "effect": "creates a sense of isolation or reveals surprising context",
        "best_for": ["contemplative", "surprise", "establishing"]
    },
    "dolly_track": {
        "name": "Dolly Track",
        "description": "smooth horizontal camera movement alongside the subject",
        "effect": "adds energy and follows character movement naturally",
        "best_for": ["action", "dialogue", "walking"]
    },
    "handheld": {
        "name": "Handheld",
        "description": "slightly shaky, documentary-style camera work",
        "effect": "creates immediacy and visceral tension",
        "best_for": ["action", "tense", "chaotic"]
    },
    "locked_off": {
        "name": "Locked-Off Static",
        "description": "completely stationary camera",
        "effect": "creates unease through stillness or emphasizes composition",
        "best_for": ["dramatic", "contemplative", "horror"]
    },
    "panaflex": {
        "name": "Panaflex/Panaglide",
        "description": "smooth, floating camera movement",
        "effect": "elegant, dreamlike quality that guides the eye",
        "best_for": ["emotional", "romantic", "establishing"]
    },
    "whip_pan": {
        "name": "Whip Pan",
        "description": "rapid pan between subjects",
        "effect": "creates urgency and connects disparate elements",
        "best_for": ["action", "comedy", "surprise"]
    }
}

LIGHTING_TECHNIQUES = {
    "low_key": {
        "name": "Low-Key Lighting",
        "description": "high contrast with deep shadows",
        "effect": "creates mystery, tension, and noir atmosphere",
        "best_for": ["tense", "mysterious", "dramatic"]
    },
    "high_key": {
        "name": "High-Key Lighting",
        "description": "bright, even illumination with minimal shadows",
        "effect": "creates optimistic, clean, professional feeling",
        "best_for": ["happy", "comedic", "corporate"]
    },
    "practical": {
        "name": "Practical Lighting",
        "description": "light sources visible in frame (lamps, windows, screens)",
        "effect": "naturalistic and grounded in reality",
        "best_for": ["realistic", "intimate", "night_interior"]
    },
    "rim_light": {
        "name": "Rim/Edge Lighting",
        "description": "light from behind creating a glowing outline",
        "effect": "separates subject from background, adds depth",
        "best_for": ["dramatic", "heroic", "mysterious"]
    },
    "chiaroscuro": {
        "name": "Chiaroscuro",
        "description": "dramatic contrast between light and dark",
        "effect": "Renaissance painting quality, moral ambiguity",
        "best_for": ["dramatic", "conflicted", "moral"]
    }
}

SHOT_RATIONALES = {
    "EWS": "establishes the world and makes the character feel small within it",
    "WS": "shows the full body and environment, giving context to actions",
    "FS": "captures full body language while maintaining intimacy",
    "MWS": "balances character and environment, great for dialogue scenes",
    "MS": "our workhorse shot - intimate enough to read emotion, wide enough for gesture",
    "MCU": "focuses on the face while keeping some body language visible",
    "CU": "demands emotional attention - we see every micro-expression",
    "ECU": "overwhelming intimacy - use sparingly for maximum impact",
    "OTS": "places us in the conversation, creating a sense of presence",
    "POV": "puts the audience directly in the character's perspective",
    "2S": "unifies characters in the same frame, showing their relationship"
}


def analyze_scene_for_suggestions(scene: dict, scene_number: int) -> list[CreativeSuggestion]:
    """
    Analyze a scene and generate creative filmmaking suggestions.
    
    This is the heart of the collaborative experience - the skill
    acts like a cinematographer offering ideas.
    """
    suggestions = []
    elements = scene.get('elements', [])
    notes = scene.get('notes', {})
    heading = scene.get('heading', {})
    location = heading.get('location', 'Unknown Location')
    time_of_day = heading.get('time', 'DAY')
    int_ext = heading.get('int_ext', 'INT.')
    
    # Analyze scene content
    dialogue_lines = [e for e in elements if e.get('type') == 'dialogue']
    action_blocks = [e for e in elements if e.get('type') == 'action']
    
    # Extract character names and emotions from dialogue
    characters = set()
    emotional_words = []
    for d in dialogue_lines:
        characters.add(d.get('character', 'UNKNOWN'))
        text = d.get('text', '').lower()
        if any(w in text for w in ['fear', 'scared', 'afraid', 'terrified']):
            emotional_words.append('fear')
        if any(w in text for w in ['love', 'heart', 'forever', 'always']):
            emotional_words.append('love')
        if any(w in text for w in ['angry', 'furious', 'rage', 'hate']):
            emotional_words.append('anger')
    
    # Check for action in action blocks
    action_text = ' '.join(a.get('text', '') for a in action_blocks).lower()
    has_movement = any(w in action_text for w in ['enters', 'walks', 'runs', 'moves', 'crosses'])
    has_tension = any(w in action_text for w in ['slowly', 'cautiously', 'nervous', 'tense', 'fear'])
    has_revelation = any(w in action_text for w in ['discovers', 'finds', 'realizes', 'sees', 'notices'])
    
    # Generate camera suggestion based on scene dynamics
    if has_tension and len(dialogue_lines) <= 2:
        suggestions.append(CreativeSuggestion(
            id=f"camera_s{scene_number}",
            scene_number=scene_number,
            category=SuggestionCategory.CAMERA,
            suggestion=f"For Scene {scene_number} in the {location}, I'm thinking we should use a slow push-in as the tension builds. It would really draw the audience into the character's anxiety.",
            rationale="The cautious movement and sparse dialogue suggest building dread - a push-in amplifies this without words.",
            technique="slow push-in to MCU",
            response_options=["sounds good", "prefer static", "let's try handheld", "suggest something else"],
            alternatives=["locked-off static for uncomfortable stillness", "handheld for visceral unease"]
        ))
    
    elif has_movement and len(characters) >= 2:
        suggestions.append(CreativeSuggestion(
            id=f"camera_s{scene_number}",
            scene_number=scene_number,
            category=SuggestionCategory.CAMERA,
            suggestion=f"I notice Scene {scene_number} has {len(characters)} characters moving through the {location}. A dolly track alongside them would keep the energy up while we follow the conversation. What do you think?",
            rationale="Multiple characters in motion benefit from camera movement that matches their energy without being distracting.",
            technique="dolly track with 2-shots",
            response_options=["yes, track with them", "prefer static coverage", "use Steadicam instead"],
            alternatives=["Steadicam for more fluid movement", "static master with cut-ins"]
        ))
    
    elif has_revelation:
        suggestions.append(CreativeSuggestion(
            id=f"camera_s{scene_number}",
            scene_number=scene_number,
            category=SuggestionCategory.CAMERA,
            suggestion=f"Scene {scene_number} has a discovery moment. I'd love to do a slow push-in to an extreme close-up right as the realization hits - it makes the audience feel the weight of the moment.",
            rationale="Revelation moments benefit from the camera physically moving closer, mimicking how we lean in when something important happens.",
            technique="push-in to ECU",
            response_options=["perfect for this moment", "too dramatic, use MCU", "stay wider"],
            alternatives=["reaction shot after reveal", "POV of what they're seeing"]
        ))
    
    # Generate lighting suggestion based on time/location
    if time_of_day.upper() == 'NIGHT' and int_ext == 'INT.':
        light_technique = LIGHTING_TECHNIQUES['practical']
        suggestions.append(CreativeSuggestion(
            id=f"lighting_s{scene_number}",
            scene_number=scene_number,
            category=SuggestionCategory.LIGHTING,
            suggestion=f"For the night interior in Scene {scene_number}, I'm picturing practical lighting - maybe just a desk lamp or window light. It keeps things grounded and intimate. Would that work for the mood you're going for?",
            rationale="Night interiors with practical sources feel more realistic and create natural pools of light and shadow.",
            technique="practical lighting with motivated sources",
            response_options=["yes, keep it naturalistic", "go darker/moodier", "brighter for safety"],
            alternatives=["low-key noir lighting", "single motivated source"]
        ))
    
    # Check for existing references and offer to expand
    for ref in notes.get('references', []):
        suggestions.append(CreativeSuggestion(
            id=f"ref_s{scene_number}",
            scene_number=scene_number,
            category=SuggestionCategory.FRAMING,
            suggestion=f"I see you've referenced '{ref}' for Scene {scene_number}. I could search my memory for specific techniques from that film - the color grading, the shot composition, the pacing. Should I pull those details?",
            rationale=f"The reference to {ref} gives us a visual language to draw from.",
            technique=f"reference: {ref}",
            response_options=["yes, search memory", "just inspiration, don't copy", "skip references"],
            reference=ref
        ))
    
    # Pacing suggestion for long scenes
    if len(elements) > 8:
        suggestions.append(CreativeSuggestion(
            id=f"pacing_s{scene_number}",
            scene_number=scene_number,
            category=SuggestionCategory.PACING,
            suggestion=f"Scene {scene_number} is pretty substantial ({len(elements)} beats). I'm thinking we break it into 3-4 distinct shots with clear rhythm - establish, develop, turn, resolve. That way it breathes without dragging. Thoughts?",
            rationale="Long scenes benefit from internal structure to maintain audience engagement.",
            technique="rhythmic shot progression",
            response_options=["structure it", "let it flow naturally", "tighten the scene first"],
            alternatives=["single oner", "more cuts for energy"]
        ))
    
    return suggestions


def format_suggestions_for_conversation(suggestions: list[CreativeSuggestion]) -> str:
    """Format all suggestions as a creative conversation."""
    if not suggestions:
        return "No specific suggestions - I'll use standard coverage for these scenes.\n"
    
    lines = [
        "",
        "=" * 60,
        "🎬 CREATIVE SUGGESTIONS",
        "=" * 60,
        "",
        "Here's what I'm thinking for the visual approach:",
        ""
    ]
    
    for i, s in enumerate(suggestions, 1):
        lines.append(f"### {i}. Scene {s.scene_number} - {s.category.value.title()}")
        lines.append("")
        lines.append(f"💡 {s.suggestion}")
        lines.append("")
        lines.append(f"   *Why*: {s.rationale}")
        if s.alternatives:
            lines.append(f"   *Or*: {', '.join(s.alternatives)}")
        lines.append("")
        lines.append(f"   → {' / '.join(s.response_options)}")
        lines.append("")
    
    lines.extend([
        "=" * 60,
        "Reply with your thoughts on each, or just say 'looks good' to proceed.",
        "=" * 60,
        ""
    ])
    
    return "\n".join(lines)
