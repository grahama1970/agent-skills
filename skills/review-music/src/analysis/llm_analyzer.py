"""
LLM Music Theory Analyzer for review-music skill.

Uses chain-of-thought prompting to analyze audio features and generate
structured music theory insights for the Horus persona.
"""
import json
import os
from typing import Dict, Optional

# Try to import LLM clients
try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


# System prompt for music analysis
MUSIC_ANALYSIS_SYSTEM_PROMPT = """You are a music theory expert and audio engineer analyzing musical features.
You provide insightful, technical analysis that connects audio characteristics to emotional and aesthetic qualities.

Your analysis should be:
1. Technical but accessible - explain music theory concepts clearly
2. Specific - reference the exact feature values provided
3. Contextual - connect features to genre, style, and emotional impact
4. Actionable - suggest use cases for the track (scoring, mood setting, etc.)

Always structure your response as JSON with the specified format."""


def format_features_for_prompt(features: Dict) -> str:
    """Format extracted features into a readable prompt section."""
    lines = []

    # Metadata
    meta = features.get("metadata", {})
    if meta.get("duration_seconds"):
        lines.append(f"Duration: {meta['duration_seconds']:.1f} seconds")

    # Rhythm features
    rhythm = features.get("rhythm", {})
    if rhythm:
        lines.append("\n## Rhythm")
        if "bpm" in rhythm:
            lines.append(f"- BPM: {rhythm['bpm']:.1f}")
        if "time_signature" in rhythm:
            lines.append(f"- Time Signature: {rhythm['time_signature']}")
        if "tempo_variance" in rhythm:
            lines.append(f"- Tempo Variance: {rhythm['tempo_variance']:.3f}")
        if "beat_strength" in rhythm:
            lines.append(f"- Beat Strength: {rhythm['beat_strength']:.2f}")

    # Harmony features
    harmony = features.get("harmony", {})
    if harmony:
        lines.append("\n## Harmony")
        if "scale" in harmony:
            lines.append(f"- Key/Scale: {harmony['scale']}")
        if "key_confidence" in harmony:
            lines.append(f"- Key Confidence: {harmony['key_confidence']:.2f}")
        if "harmonic_complexity" in harmony:
            lines.append(f"- Harmonic Complexity: {harmony['harmonic_complexity']:.2f}")
        if "chord_changes_per_minute" in harmony:
            lines.append(f"- Chord Changes/min: {harmony['chord_changes_per_minute']:.1f}")

    # Timbre features
    timbre = features.get("timbre", {})
    if timbre:
        lines.append("\n## Timbre")
        if "brightness" in timbre:
            lines.append(f"- Brightness: {timbre['brightness']}")
        if "texture" in timbre:
            lines.append(f"- Texture: {timbre['texture']}")
        if "spectral_centroid" in timbre:
            lines.append(f"- Spectral Centroid: {timbre['spectral_centroid']:.0f} Hz")
        if "spectral_flatness" in timbre:
            lines.append(f"- Spectral Flatness: {timbre['spectral_flatness']:.3f}")

    # Dynamics features
    dynamics = features.get("dynamics", {})
    if dynamics:
        lines.append("\n## Dynamics")
        if "loudness_integrated" in dynamics:
            lines.append(f"- Integrated Loudness: {dynamics['loudness_integrated']:.1f} LUFS")
        if "dynamic_range" in dynamics:
            lines.append(f"- Dynamic Range: {dynamics['dynamic_range']:.1f} dB")
        if "loudness_range" in dynamics:
            lines.append(f"- Loudness Range (LRA): {dynamics['loudness_range']:.1f} LU")

    # Lyrics
    lyrics = features.get("lyrics", {})
    if lyrics:
        lines.append("\n## Vocals/Lyrics")
        if lyrics.get("is_instrumental"):
            lines.append("- Type: Instrumental (no lyrics detected)")
        else:
            lines.append("- Type: Vocal track")
            if lyrics.get("language"):
                lines.append(f"- Language: {lyrics['language']}")
            if lyrics.get("text"):
                # Truncate long lyrics
                text = lyrics["text"][:500] + "..." if len(lyrics.get("text", "")) > 500 else lyrics.get("text", "")
                lines.append(f"- Lyrics excerpt: {text}")

    return "\n".join(lines)


def create_analysis_prompt(features: Dict) -> str:
    """Create the analysis prompt with chain-of-thought structure."""
    features_text = format_features_for_prompt(features)

    return f"""Analyze the following audio features and provide a structured music theory analysis.

# Extracted Audio Features
{features_text}

# Instructions

Think through your analysis step by step:

1. **Tempo & Rhythm Analysis**: Consider the BPM, time signature, and rhythmic complexity.
   What does this tell us about the energy and feel of the track?

2. **Harmonic Analysis**: Examine the key, mode, and harmonic complexity.
   What emotional qualities does this harmonic content suggest?

3. **Timbral Analysis**: Look at the spectral characteristics and texture.
   How would you describe the sonic palette and production style?

4. **Dynamic Analysis**: Consider the loudness and dynamic range.
   What does this reveal about the mix and intended listening context?

5. **Emotional Arc**: Synthesize all features to describe the overall emotional character.

6. **Use Cases**: Suggest specific scenarios where this track would be effective
   (film scoring, game soundtracks, mood playlists, etc.)

# Required Output Format

Respond with a JSON object containing:
{{
  "summary": "2-3 sentence overall description",
  "music_theory": {{
    "tempo_analysis": "Analysis of rhythm and tempo",
    "harmonic_analysis": "Analysis of key, mode, harmony",
    "timbral_analysis": "Analysis of sound texture and spectral content",
    "dynamic_analysis": "Analysis of loudness and dynamics"
  }},
  "production": {{
    "style": "Genre/production style (e.g., 'Epic Orchestral', 'Industrial Metal')",
    "era": "Estimated era/decade influence if apparent",
    "quality_notes": "Production quality observations"
  }},
  "emotional_arc": {{
    "primary_mood": "Main emotional quality",
    "secondary_mood": "Secondary emotional quality",
    "intensity": "low/medium/high",
    "character": "Brief character description (e.g., 'triumphant', 'melancholic')"
  }},
  "use_cases": [
    "Specific use case 1",
    "Specific use case 2",
    "Specific use case 3"
  ],
  "similar_artists": ["Artist 1", "Artist 2", "Artist 3"],
  "confidence": 0.0-1.0
}}

Respond ONLY with the JSON object, no additional text."""


def analyze_with_llm(
    features: Dict,
    provider: str = "anthropic",
    model: Optional[str] = None,
) -> Dict:
    """
    Analyze audio features using an LLM with chain-of-thought prompting.

    Args:
        features: Feature dictionary from extract_all_features()
        provider: LLM provider ("anthropic" or "openai")
        model: Specific model to use (defaults to claude-sonnet-4-20250514 or gpt-4o)

    Returns:
        Dictionary with structured analysis:
        - summary: Brief overall description
        - music_theory: Detailed theory analysis
        - production: Style and production notes
        - emotional_arc: Emotional qualities
        - use_cases: Suggested use cases
        - similar_artists: Related artists
        - confidence: Analysis confidence score
    """
    prompt = create_analysis_prompt(features)

    if provider == "anthropic":
        return _analyze_anthropic(prompt, model)
    elif provider == "openai":
        return _analyze_openai(prompt, model)
    else:
        raise ValueError(f"Unsupported provider: {provider}")


def _analyze_anthropic(prompt: str, model: Optional[str] = None) -> Dict:
    """Call Anthropic API for analysis."""
    if not HAS_ANTHROPIC:
        raise ImportError("anthropic package not installed. Run: pip install anthropic")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    client = anthropic.Anthropic(api_key=api_key)

    model = model or "claude-sonnet-4-20250514"

    response = client.messages.create(
        model=model,
        max_tokens=2000,
        system=MUSIC_ANALYSIS_SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    # Parse JSON response
    response_text = response.content[0].text.strip()
    return _parse_json_response(response_text)


def _analyze_openai(prompt: str, model: Optional[str] = None) -> Dict:
    """Call OpenAI API for analysis."""
    if not HAS_OPENAI:
        raise ImportError("openai package not installed. Run: pip install openai")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")

    client = openai.OpenAI(api_key=api_key)

    model = model or "gpt-4o"

    response = client.chat.completions.create(
        model=model,
        max_tokens=2000,
        messages=[
            {"role": "system", "content": MUSIC_ANALYSIS_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"}
    )

    response_text = response.choices[0].message.content.strip()
    return _parse_json_response(response_text)


def _parse_json_response(text: str) -> Dict:
    """Parse JSON response from LLM, handling markdown code blocks."""
    # Strip markdown code blocks if present
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        # Return error structure
        return {
            "summary": "Analysis failed - could not parse LLM response",
            "music_theory": {},
            "production": {},
            "emotional_arc": {},
            "use_cases": [],
            "similar_artists": [],
            "confidence": 0.0,
            "_error": str(e),
            "_raw_response": text[:500],
        }


def analyze_without_llm(features: Dict) -> Dict:
    """
    Generate a basic analysis without calling an LLM.

    Uses rule-based logic to provide a fallback analysis when no API key is available.
    """
    rhythm = features.get("rhythm", {})
    harmony = features.get("harmony", {})
    timbre = features.get("timbre", {})
    dynamics = features.get("dynamics", {})

    # Determine tempo character
    bpm = rhythm.get("bpm", 100)
    if bpm < 80:
        tempo_char = "slow, deliberate"
    elif bpm < 120:
        tempo_char = "moderate, grounded"
    elif bpm < 150:
        tempo_char = "energetic, driving"
    else:
        tempo_char = "fast, intense"

    # Determine mood from mode
    mode = harmony.get("mode", "major")
    key = harmony.get("key", "C")
    if mode == "minor":
        mood = "melancholic, introspective"
    else:
        mood = "uplifting, optimistic"

    # Determine intensity from dynamics
    loudness = dynamics.get("loudness_integrated", -18)
    if loudness > -12:
        intensity = "high"
    elif loudness > -20:
        intensity = "medium"
    else:
        intensity = "low"

    # Determine texture description
    brightness = timbre.get("brightness", "neutral")
    texture = timbre.get("texture", "layered")

    return {
        "summary": f"A {tempo_char} track in {key} {mode} with {brightness} timbre and {texture} texture.",
        "music_theory": {
            "tempo_analysis": f"At {bpm:.0f} BPM in {rhythm.get('time_signature', '4/4')}, the tempo is {tempo_char}.",
            "harmonic_analysis": f"The track is in {key} {mode}, suggesting a {mood} quality.",
            "timbral_analysis": f"The timbre is {brightness} with a {texture} texture.",
            "dynamic_analysis": f"Integrated loudness of {loudness:.1f} LUFS indicates {intensity} intensity.",
        },
        "production": {
            "style": "Unknown (rule-based analysis)",
            "era": "Unknown",
            "quality_notes": "Analysis performed without LLM - limited style detection",
        },
        "emotional_arc": {
            "primary_mood": mood.split(",")[0].strip(),
            "secondary_mood": mood.split(",")[1].strip() if "," in mood else "neutral",
            "intensity": intensity,
            "character": f"{tempo_char.split(',')[0]} and {mood.split(',')[0]}",
        },
        "use_cases": [
            "Background music",
            "Ambient scoring",
            "Personal listening",
        ],
        "similar_artists": [],
        "confidence": 0.5,  # Lower confidence for rule-based
        "_method": "rule_based",
    }
