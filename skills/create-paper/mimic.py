"""
Paper Writer Skill - MIMIC
Style pattern extraction and mimicking from exemplar papers.
"""
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer

from config import (
    ARXIV_SCRIPT,
    MIMIC_STATE_FILE,
    SCILLM_SCRIPT,
    MimicPatterns,
)


def extract_style_patterns(paper_ids: List[str]) -> Optional[MimicPatterns]:
    """Extract style patterns from exemplar papers for mimicking.

    This is the core of MIMIC - learning structural and stylistic patterns
    from successful papers to guide generation.

    Args:
        paper_ids: List of arXiv paper IDs to learn from

    Returns:
        MimicPatterns or None if extraction fails
    """
    typer.echo("\n=== MIMIC: EXTRACTING STYLE PATTERNS ===\n")

    if not paper_ids:
        typer.echo("[ERROR] No paper IDs provided", err=True)
        return None

    typer.echo(f"Analyzing {len(paper_ids)} exemplar papers...")

    # Collect patterns from each paper
    all_patterns = []
    paper_titles = []

    for paper_id in paper_ids:
        typer.echo(f"\n  [{paper_id}] Fetching and analyzing...")

        # Fetch paper content
        paper_content = _fetch_paper_content(paper_id)
        if not paper_content:
            typer.echo(f"    [WARN] Could not fetch paper {paper_id}")
            continue

        paper_titles.append(paper_content.get("title", paper_id))

        # Extract patterns from this paper
        patterns = _analyze_paper_patterns(paper_content)
        if patterns:
            all_patterns.append(patterns)
            typer.echo(f"    [OK] Extracted patterns")

    if not all_patterns:
        typer.echo("\n[ERROR] No patterns could be extracted", err=True)
        return None

    # Merge patterns from all papers
    merged = _merge_patterns(all_patterns, paper_ids, paper_titles)

    # Save state for later use
    _save_mimic_state(merged)

    typer.echo(f"\n[OK] Extracted patterns from {len(all_patterns)} papers")
    typer.echo(f"    Voice: {merged.voice}")
    typer.echo(f"    Sections: {', '.join(merged.section_order)}")
    typer.echo(f"    Intro length: ~{merged.intro_length} words")

    return merged


def _fetch_paper_content(paper_id: str) -> Optional[Dict[str, Any]]:
    """Fetch paper content from arXiv.

    Args:
        paper_id: arXiv paper ID

    Returns:
        Paper content dict or None
    """
    if not ARXIV_SCRIPT.exists():
        return None

    try:
        result = subprocess.run(
            [str(ARXIV_SCRIPT), "get", "--id", paper_id],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            items = data.get("items", [])
            if items:
                return items[0]
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    return None


def _analyze_paper_patterns(paper_content: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Analyze a paper to extract style patterns.

    Args:
        paper_content: Paper content dict

    Returns:
        Pattern dict or None
    """
    patterns = {
        "section_order": [],
        "subsection_depth": 2,
        "intro_length": 500,
        "method_sections": [],
        "figure_placement": {},
        "voice": "passive",
        "tense": {},
        "transition_phrases": [],
        "technical_density": 0.3,
        "citation_density": {},
        "intro_structure": [],
        "method_detail_level": "medium",
        "eval_metrics": [],
        "figure_captions": "verbose",
    }

    abstract = paper_content.get("abstract", "")
    if not abstract:
        return None

    # Analyze voice (active vs passive)
    we_count = len(re.findall(r'\bwe\b', abstract, re.IGNORECASE))
    this_paper_count = len(re.findall(r'\bthis paper\b', abstract, re.IGNORECASE))
    patterns["voice"] = "active" if we_count > this_paper_count else "passive"

    # Analyze intro structure from abstract
    sentences = abstract.split(". ")
    if sentences:
        # First sentence is usually problem statement
        patterns["intro_structure"] = ["problem_statement"]
        for s in sentences[1:4]:
            s_lower = s.lower()
            if "we propose" in s_lower or "we present" in s_lower:
                patterns["intro_structure"].append("solution")
            elif "achieve" in s_lower or "result" in s_lower:
                patterns["intro_structure"].append("results")
            elif "evaluate" in s_lower or "experiment" in s_lower:
                patterns["intro_structure"].append("evaluation")

    # Estimate intro length based on abstract
    patterns["intro_length"] = len(abstract.split()) * 4  # Assume intro is 4x abstract

    # Extract transition phrases
    transitions = [
        "Furthermore", "Moreover", "In addition", "Specifically",
        "To address", "We propose", "Our approach", "In contrast",
        "Notably", "Consequently", "To this end", "Building on",
    ]
    patterns["transition_phrases"] = [t for t in transitions if t.lower() in abstract.lower()]

    # Standard section order for ML papers
    patterns["section_order"] = ["abstract", "intro", "related", "method", "eval", "conclusion"]

    # Calculate technical density (rough estimate)
    tech_terms = len(re.findall(r'\b[A-Z]{2,}\b', abstract))  # Acronyms
    total_words = len(abstract.split())
    patterns["technical_density"] = min(0.5, tech_terms / max(1, total_words) * 10)

    return patterns


def _merge_patterns(
    patterns_list: List[Dict[str, Any]],
    paper_ids: List[str],
    paper_titles: List[str],
) -> MimicPatterns:
    """Merge patterns from multiple papers.

    Args:
        patterns_list: List of pattern dicts
        paper_ids: Original paper IDs
        paper_titles: Paper titles

    Returns:
        Merged MimicPatterns
    """
    if not patterns_list:
        # Return defaults
        return MimicPatterns(
            section_order=["abstract", "intro", "related", "method", "eval", "conclusion"],
            subsection_depth=2,
            intro_length=500,
            method_sections=["approach", "algorithm", "implementation"],
            figure_placement={"method": 2, "eval": 3},
            voice="active",
            tense={"intro": "present", "method": "present", "eval": "past"},
            transition_phrases=["We propose", "Furthermore", "To address"],
            technical_density=0.3,
            citation_density={"intro": 0.5, "related": 1.0, "method": 0.3},
            intro_structure=["problem", "motivation", "contribution"],
            method_detail_level="medium",
            eval_metrics=["accuracy", "efficiency"],
            figure_captions="verbose",
            exemplar_ids=paper_ids,
            exemplar_titles=paper_titles,
        )

    # Average/mode for numeric values
    intro_lengths = [p.get("intro_length", 500) for p in patterns_list]
    avg_intro_length = sum(intro_lengths) // len(intro_lengths)

    tech_densities = [p.get("technical_density", 0.3) for p in patterns_list]
    avg_tech_density = sum(tech_densities) / len(tech_densities)

    # Mode for categorical values
    voices = [p.get("voice", "active") for p in patterns_list]
    voice = max(set(voices), key=voices.count)

    # Union for lists
    all_transitions = []
    for p in patterns_list:
        all_transitions.extend(p.get("transition_phrases", []))
    transitions = list(set(all_transitions))[:10]

    # Most common intro structure
    intro_structures = [tuple(p.get("intro_structure", [])) for p in patterns_list]
    intro_structure = list(max(set(intro_structures), key=intro_structures.count)) if intro_structures else ["problem", "solution"]

    return MimicPatterns(
        section_order=patterns_list[0].get("section_order", ["abstract", "intro", "method", "eval"]),
        subsection_depth=2,
        intro_length=avg_intro_length,
        method_sections=["approach", "algorithm", "implementation"],
        figure_placement={"method": 2, "eval": 3},
        voice=voice,
        tense={"intro": "present", "method": "present", "eval": "past"},
        transition_phrases=transitions,
        technical_density=avg_tech_density,
        citation_density={"intro": 0.5, "related": 1.0, "method": 0.3},
        intro_structure=intro_structure,
        method_detail_level="medium",
        eval_metrics=["accuracy", "efficiency"],
        figure_captions="verbose",
        exemplar_ids=paper_ids,
        exemplar_titles=paper_titles,
    )


def _save_mimic_state(patterns: MimicPatterns) -> None:
    """Save MIMIC state to file.

    Args:
        patterns: Patterns to save
    """
    state = {
        "section_order": patterns.section_order,
        "subsection_depth": patterns.subsection_depth,
        "intro_length": patterns.intro_length,
        "method_sections": patterns.method_sections,
        "figure_placement": patterns.figure_placement,
        "voice": patterns.voice,
        "tense": patterns.tense,
        "transition_phrases": patterns.transition_phrases,
        "technical_density": patterns.technical_density,
        "citation_density": patterns.citation_density,
        "intro_structure": patterns.intro_structure,
        "method_detail_level": patterns.method_detail_level,
        "eval_metrics": patterns.eval_metrics,
        "figure_captions": patterns.figure_captions,
        "exemplar_ids": patterns.exemplar_ids,
        "exemplar_titles": patterns.exemplar_titles,
    }
    MIMIC_STATE_FILE.write_text(json.dumps(state, indent=2))


def load_mimic_state() -> Optional[MimicPatterns]:
    """Load saved MIMIC patterns.

    Returns:
        MimicPatterns or None
    """
    if not MIMIC_STATE_FILE.exists():
        return None

    try:
        data = json.loads(MIMIC_STATE_FILE.read_text())
        return MimicPatterns(
            section_order=data.get("section_order", []),
            subsection_depth=data.get("subsection_depth", 2),
            intro_length=data.get("intro_length", 500),
            method_sections=data.get("method_sections", []),
            figure_placement=data.get("figure_placement", {}),
            voice=data.get("voice", "active"),
            tense=data.get("tense", {}),
            transition_phrases=data.get("transition_phrases", []),
            technical_density=data.get("technical_density", 0.3),
            citation_density=data.get("citation_density", {}),
            intro_structure=data.get("intro_structure", []),
            method_detail_level=data.get("method_detail_level", "medium"),
            eval_metrics=data.get("eval_metrics", []),
            figure_captions=data.get("figure_captions", "verbose"),
            exemplar_ids=data.get("exemplar_ids", []),
            exemplar_titles=data.get("exemplar_titles", []),
        )
    except (json.JSONDecodeError, KeyError):
        return None


def apply_mimic_guidance(
    section_prompt: str,
    section_key: str,
    patterns: MimicPatterns,
) -> str:
    """Apply MIMIC patterns to a section generation prompt.

    Args:
        section_prompt: Base prompt for section
        section_key: Section key (intro, method, etc.)
        patterns: MIMIC patterns to apply

    Returns:
        Enhanced prompt with style guidance
    """
    guidance_parts = [section_prompt]

    # Add voice guidance
    guidance_parts.append(f"\n\nSTYLE GUIDANCE (from exemplar papers):")
    guidance_parts.append(f"- Voice: Use {patterns.voice} voice")

    # Add tense guidance
    if section_key in patterns.tense:
        guidance_parts.append(f"- Tense: Use {patterns.tense[section_key]} tense")

    # Add transition phrases
    if patterns.transition_phrases:
        phrases = patterns.transition_phrases[:5]
        guidance_parts.append(f"- Transition phrases to incorporate: {', '.join(phrases)}")

    # Add length guidance for intro
    if section_key == "intro":
        guidance_parts.append(f"- Target length: approximately {patterns.intro_length} words")
        if patterns.intro_structure:
            guidance_parts.append(f"- Structure: {' -> '.join(patterns.intro_structure)}")

    # Add citation guidance
    if section_key in patterns.citation_density:
        density = patterns.citation_density[section_key]
        if density >= 0.5:
            guidance_parts.append("- Include frequent citations to support claims")
        elif density >= 0.3:
            guidance_parts.append("- Include moderate citations for key claims")
        else:
            guidance_parts.append("- Focus on methodology, cite sparingly")

    # Add technical density guidance
    if patterns.technical_density >= 0.4:
        guidance_parts.append("- Use precise technical terminology")
    else:
        guidance_parts.append("- Balance technical terms with accessibility")

    # Reference exemplar papers
    if patterns.exemplar_titles:
        guidance_parts.append(f"\nExemplar papers for style reference: {', '.join(patterns.exemplar_titles[:2])}")

    return "\n".join(guidance_parts)
