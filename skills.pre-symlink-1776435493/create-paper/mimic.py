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
from loguru import logger


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
        logger.error("No paper IDs provided")
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
        logger.error("No patterns could be extracted")
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


# -------------------------------------------------------------------------
# Interactive MIMIC Functions (from monolith)
# -------------------------------------------------------------------------


def select_exemplar_papers() -> List[Dict[str, Any]]:
    """Interactive selection of exemplar papers to mimic.

    Returns:
        List of exemplar paper dicts with id, title, authors, abstract
    """
    typer.echo("\n=== MIMIC: SELECT EXEMPLAR PAPERS ===\n")

    typer.echo("Choose 2-3 papers whose style you want to mimic:")
    typer.echo("1. Provide arXiv IDs manually")
    typer.echo("2. Search for papers from prestigious sources")
    typer.echo("3. Use pre-curated collections")

    choice = typer.prompt("Your choice (1-3)", type=int, default=1)

    exemplars = []

    if choice == 1:
        exemplars = _select_by_ids()
    elif choice == 2:
        exemplars = _select_by_search()
    elif choice == 3:
        exemplars = _select_from_collections()

    typer.echo(f"\n[OK] Selected {len(exemplars)} exemplar papers")
    for ex in exemplars:
        typer.echo(f"  - {ex['id']}: {ex['title'][:50]}...")

    return exemplars


def _select_by_ids() -> List[Dict[str, Any]]:
    """Select exemplars by entering arXiv IDs.

    Returns:
        List of exemplar dicts
    """
    typer.echo("\nEnter arXiv IDs (comma-separated):")
    typer.echo("Example: 2401.12345, 2310.09876, 2312.54321")
    ids_input = typer.prompt("arXiv IDs")
    paper_ids = [p.strip() for p in ids_input.split(",")]

    exemplars = []
    if ARXIV_SCRIPT.exists():
        for paper_id in paper_ids[:3]:
            typer.echo(f"  Fetching: {paper_id}...")
            try:
                result = subprocess.run(
                    [str(ARXIV_SCRIPT), "get", "--id", paper_id],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode == 0:
                    data = json.loads(result.stdout)
                    items = data.get("items", [])
                    if items:
                        item = items[0]
                        exemplars.append({
                            "id": paper_id,
                            "title": item.get("title", "Unknown"),
                            "authors": item.get("authors", []),
                            "abstract": item.get("abstract", ""),
                            "published": item.get("published", ""),
                        })
                        typer.echo(f"    [OK] {item.get('title', 'Unknown')[:50]}...")
            except Exception as e:
                logger.error(f"{e}")
    else:
        for paper_id in paper_ids[:3]:
            exemplars.append({"id": paper_id, "title": "Unknown", "authors": [], "abstract": ""})

    return exemplars


def _select_by_search() -> List[Dict[str, Any]]:
    """Select exemplars by searching arXiv.

    Returns:
        List of exemplar dicts
    """
    typer.echo("\nSearching papers from prestigious sources...")
    query = typer.prompt("Search query", default="agent memory systems")

    exemplars = []
    if ARXIV_SCRIPT.exists():
        try:
            result = subprocess.run(
                [str(ARXIV_SCRIPT), "search", "--query", query, "--max-results", "20"],
                capture_output=True, text=True, timeout=90,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                items = data.get("items", [])

                typer.echo(f"\nFound {len(items)} papers:\n")
                for i, item in enumerate(items[:15], 1):
                    typer.echo(f"[{i}] {item.get('title', 'Unknown')[:60]}...")
                    typer.echo(f"    Authors: {', '.join(item.get('authors', [])[:3])}")
                    typer.echo()

                selection = typer.prompt("Select 2-3 papers (comma-separated numbers)")
                indices = [int(n.strip()) - 1 for n in selection.split(",")]

                for idx in indices[:3]:
                    if 0 <= idx < len(items):
                        item = items[idx]
                        exemplars.append({
                            "id": item.get("id", ""),
                            "title": item.get("title", "Unknown"),
                            "authors": item.get("authors", []),
                            "abstract": item.get("abstract", ""),
                            "published": item.get("published", ""),
                        })
        except Exception as e:
            logger.error(f"Search failed: {e}")

    return exemplars


def _select_from_collections() -> List[Dict[str, Any]]:
    """Select exemplars from pre-curated collections.

    Returns:
        List of exemplar dicts
    """
    typer.echo("\nPre-curated collections:")
    typer.echo("1. Agent Systems (ReAct, AutoGPT, Voyager)")
    typer.echo("2. Memory Systems (MemGPT, Reflexion)")
    typer.echo("3. Tool Use (Toolformer, Gorilla)")
    typer.echo("4. Code Generation (CodeGen, StarCoder)")

    collection = typer.prompt("Select collection (1-4)", type=int, default=1)

    collections = {
        1: ["2210.03629", "2303.11366", "2305.16291"],
        2: ["2310.08560", "2303.11366"],
        3: ["2302.04761", "2305.15334"],
        4: ["2203.13474", "2305.06161"],
    }

    paper_ids = collections.get(collection, collections[1])
    exemplars = []

    if ARXIV_SCRIPT.exists():
        for paper_id in paper_ids:
            typer.echo(f"  Fetching: {paper_id}...")
            try:
                result = subprocess.run(
                    [str(ARXIV_SCRIPT), "get", "--id", paper_id],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode == 0:
                    data = json.loads(result.stdout)
                    items = data.get("items", [])
                    if items:
                        item = items[0]
                        exemplars.append({
                            "id": paper_id,
                            "title": item.get("title", "Unknown"),
                            "authors": item.get("authors", []),
                            "abstract": item.get("abstract", ""),
                        })
                        typer.echo(f"    [OK] {item.get('title', 'Unknown')[:50]}...")
            except Exception:
                exemplars.append({"id": paper_id, "title": "Unknown", "authors": [], "abstract": ""})

    return exemplars


def analyze_exemplars(exemplars: List[Dict[str, Any]]) -> MimicPatterns:
    """Analyze exemplar papers to extract structure, style, and content patterns.

    Args:
        exemplars: List of exemplar paper dicts

    Returns:
        MimicPatterns object with extracted patterns
    """
    typer.echo("\n=== MIMIC: ANALYZING EXEMPLARS ===\n")

    # Default patterns (based on common CS paper conventions)
    patterns = MimicPatterns(
        section_order=["Abstract", "Introduction", "Background", "Method", "Evaluation", "Related Work", "Conclusion"],
        subsection_depth=2,
        intro_length=1500,
        method_sections=["Overview", "Algorithm", "Implementation"],
        figure_placement={"intro": 0, "method": 2, "eval": 3},
        voice="active",
        tense={"intro": "present", "method": "present", "eval": "past", "related": "present"},
        transition_phrases=[
            "To address this challenge, we...",
            "Our key insight is that...",
            "The intuition behind this approach...",
            "Unlike prior work, our method...",
            "We evaluate our approach on...",
        ],
        technical_density=0.40,
        citation_density={"intro": 0.8, "related": 2.0, "method": 0.3, "eval": 0.5},
        intro_structure=[
            "Problem statement (2-3 sentences)",
            "Motivation with real-world example",
            "Existing limitations (1 paragraph)",
            "Our contributions (numbered list)",
            "Paper organization",
        ],
        method_detail_level="high",
        eval_metrics=["accuracy", "latency", "comparison_with_baselines"],
        figure_captions="verbose",
        exemplar_ids=[ex.get("id", "") for ex in exemplars],
        exemplar_titles=[ex.get("title", "") for ex in exemplars],
    )

    # If we have actual paper content, analyze it using LLM
    if SCILLM_SCRIPT.exists() and exemplars:
        _enhance_patterns_with_llm(patterns, exemplars)

    # Show analysis summary
    typer.echo("\n--- ANALYSIS SUMMARY ---")
    typer.echo(f"Section order: {' -> '.join(patterns.section_order[:4])}...")
    typer.echo(f"Voice: {patterns.voice}")
    typer.echo(f"Technical density: {patterns.technical_density:.0%}")
    typer.echo(f"Intro structure: {len(patterns.intro_structure)} components")
    typer.echo(f"Transition phrases: {len(patterns.transition_phrases)} learned")

    if not typer.confirm("\nUse these patterns for paper generation?"):
        typer.echo("Patterns not saved. Re-run with different exemplars.")
        raise typer.Exit(0)

    return patterns


def _enhance_patterns_with_llm(patterns: MimicPatterns, exemplars: List[Dict[str, Any]]) -> None:
    """Enhance MIMIC patterns using LLM analysis of exemplar abstracts.

    Modifies patterns in place.

    Args:
        patterns: MimicPatterns to enhance
        exemplars: List of exemplar paper dicts
    """
    typer.echo("Analyzing exemplar papers using LLM...")

    abstracts = "\n\n".join([
        f"Paper: {ex.get('title', 'Unknown')}\nAbstract: {ex.get('abstract', 'N/A')[:500]}"
        for ex in exemplars
    ])

    analysis_prompt = f"""Analyze these academic paper abstracts and extract writing patterns:

{abstracts}

Extract the following patterns:
1. Writing voice (active vs passive)
2. Common transition phrases
3. Introduction structure pattern
4. Technical density (high/medium/low)
5. How contributions are presented

Format as JSON with keys: voice, transitions, intro_pattern, density, contribution_style
"""
    try:
        result = subprocess.run(
            [str(SCILLM_SCRIPT), "batch", "single", analysis_prompt[:4000]],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0 and result.stdout.strip():
            typer.echo("  [OK] LLM analysis complete")
            output = result.stdout
            json_start = output.find("{")
            json_end = output.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                try:
                    analysis = json.loads(output[json_start:json_end])
                    if "voice" in analysis:
                        patterns.voice = analysis["voice"]
                    if "transitions" in analysis:
                        patterns.transition_phrases = analysis["transitions"][:5]
                    if "density" in analysis:
                        density_map = {"high": 0.5, "medium": 0.4, "low": 0.3}
                        patterns.technical_density = density_map.get(analysis["density"], 0.4)
                except json.JSONDecodeError:
                    logger.warning("Could not parse LLM JSON, using defaults")
    except Exception as e:
        logger.warning(f"LLM analysis failed: {e}")


def store_mimic_patterns(patterns: MimicPatterns) -> None:
    """Save MIMIC patterns to state file.

    Alias for _save_mimic_state for backward compatibility.

    Args:
        patterns: Patterns to save
    """
    _save_mimic_state(patterns)
    typer.echo(f"[OK] Patterns saved to {MIMIC_STATE_FILE}")


def load_mimic_patterns() -> Optional[MimicPatterns]:
    """Load MIMIC patterns from state file if exists.

    Alias for load_mimic_state for backward compatibility.

    Returns:
        MimicPatterns or None
    """
    return load_mimic_state()


def apply_style_transfer(
    content: str,
    section_key: str,
    patterns: MimicPatterns,
) -> str:
    """Apply MIMIC style patterns to generated content.

    Args:
        content: Generated section content
        section_key: Section identifier (e.g., 'intro', 'method')
        patterns: MIMIC patterns to apply

    Returns:
        Style-transferred content
    """
    if not SCILLM_SCRIPT.exists():
        return content

    style_prompt = f"""Apply the following writing style to this academic text:

Style Guidelines:
- Voice: {patterns.voice} voice (convert any passive sentences)
- Tense: {patterns.tense.get(section_key, 'present')} tense
- Add transition phrases like: {', '.join(patterns.transition_phrases[:3])}
- Technical density: {patterns.technical_density:.0%} (adjust jargon level)

Original Text:
{content[:3000]}

Rewrite the text following these style guidelines. Preserve the meaning and key information.
Output ONLY the rewritten text, no explanations.
"""

    try:
        result = subprocess.run(
            [str(SCILLM_SCRIPT), "batch", "single", style_prompt],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception as e:
        logger.debug("value extraction failed: {}", e)

    return content


def validate_against_exemplars(
    generated_path: Path,
    patterns: MimicPatterns,
) -> Dict[str, Any]:
    """Validate generated paper against exemplar metrics.

    Args:
        generated_path: Path to generated paper directory
        patterns: MIMIC patterns to compare against

    Returns:
        Validation report dict
    """
    report = {
        "structure": {"match": True, "issues": []},
        "style": {"match": True, "issues": []},
        "content": {"match": True, "issues": []},
        "recommendations": [],
    }

    # Check section files exist
    sections_dir = generated_path / "sections"
    if not sections_dir.exists():
        report["structure"]["match"] = False
        report["structure"]["issues"].append("Sections directory not found")
        return report

    # Check structure
    expected_sections = ["abstract", "intro", "related", "design", "impl", "eval", "discussion"]
    for section in expected_sections:
        section_file = sections_dir / f"{section}.tex"
        if not section_file.exists():
            report["structure"]["issues"].append(f"Missing section: {section}")
            report["structure"]["match"] = False

    # Count words in intro
    intro_file = sections_dir / "intro.tex"
    if intro_file.exists():
        intro_content = intro_file.read_text()
        word_count = len(intro_content.split())
        if abs(word_count - patterns.intro_length) > 500:
            report["style"]["issues"].append(
                f"Intro length: {word_count} words (target: {patterns.intro_length})"
            )
            report["recommendations"].append(
                f"Adjust intro length by {patterns.intro_length - word_count:+d} words"
            )

    # Check for figures
    figures_dir = generated_path / "figures"
    if figures_dir.exists():
        figure_count = len(list(figures_dir.glob("*.pdf"))) + len(list(figures_dir.glob("*.png")))
        expected_figures = sum(patterns.figure_placement.values())
        if figure_count < expected_figures:
            report["content"]["issues"].append(
                f"Figures: {figure_count} (target: {expected_figures})"
            )
            report["recommendations"].append(
                f"Add {expected_figures - figure_count} more figures"
            )

    return report
