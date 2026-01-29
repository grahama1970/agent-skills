"""
Paper Writer Skill - RAG Grounding
Retrieval-Augmented Generation for grounding claims in code and papers.
"""
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer

from config import (
    MEMORY_SCRIPT,
    AgentPersona,
    ProjectAnalysis,
    RAGContext,
)


def build_rag_context(
    project_path: Path,
    analysis: ProjectAnalysis,
    section_key: str = "",
) -> RAGContext:
    """Build RAG context for grounding paper claims.

    Collects:
    1. Code snippets from project
    2. Facts extracted from project analysis
    3. Paper excerpts from memory (if available)
    4. Research findings from dogpile

    Args:
        project_path: Path to the project
        analysis: Project analysis results
        section_key: Optional section key to filter relevance

    Returns:
        RAGContext with all grounding materials
    """
    context = RAGContext(
        code_snippets=[],
        project_facts=[],
        paper_excerpts=[],
        research_facts=[],
        section_constraints={},
    )

    # 1. Extract key code snippets
    context.code_snippets = _extract_code_snippets(project_path, section_key)

    # 2. Convert analysis features to facts
    context.project_facts = _extract_project_facts(analysis)

    # 3. Query memory for relevant paper excerpts
    context.paper_excerpts = _query_memory_for_papers(section_key)

    # 4. Extract research facts from dogpile context
    if analysis.research_context:
        context.research_facts = _parse_research_context(analysis.research_context)

    return context


def _extract_code_snippets(
    project_path: Path,
    section_key: str,
    max_snippets: int = 5,
) -> List[Dict[str, str]]:
    """Extract relevant code snippets from project.

    Args:
        project_path: Path to the project
        section_key: Section key to guide relevance
        max_snippets: Maximum number of snippets

    Returns:
        List of code snippet dicts
    """
    snippets = []

    # Prioritize files based on section
    priority_patterns = {
        "method": ["**/core/*.py", "**/engine/*.py", "**/model*.py"],
        "eval": ["**/test*.py", "**/eval*.py", "**/benchmark*.py"],
        "impl": ["**/main.py", "**/cli.py", "**/app.py"],
        "design": ["**/arch*.py", "**/design*.py", "**/types.py"],
    }

    patterns = priority_patterns.get(section_key, ["**/*.py"])

    for pattern in patterns[:2]:  # Limit patterns
        for py_file in project_path.glob(pattern):
            if py_file.is_file() and py_file.stat().st_size < 50000:  # Skip large files
                try:
                    content = py_file.read_text()
                    # Extract docstrings and key functions
                    snippet = _extract_key_code(content, py_file.name)
                    if snippet:
                        snippets.append({
                            "file": str(py_file.relative_to(project_path)),
                            "content": snippet[:2000],  # Limit size
                            "type": _classify_code(content),
                        })
                        if len(snippets) >= max_snippets:
                            break
                except Exception:
                    pass
        if len(snippets) >= max_snippets:
            break

    return snippets


def _extract_key_code(content: str, filename: str) -> str:
    """Extract key code elements (docstrings, function signatures).

    Args:
        content: File content
        filename: File name

    Returns:
        Extracted code summary
    """
    import re

    parts = [f"# {filename}"]

    # Extract module docstring
    docstring_match = re.search(r'^"""(.+?)"""', content, re.DOTALL)
    if docstring_match:
        parts.append(f'"""{docstring_match.group(1)[:200]}..."""')

    # Extract class and function definitions with docstrings
    class_pattern = re.compile(r'^class\s+(\w+).*?:\s*\n\s*"""(.+?)"""', re.MULTILINE | re.DOTALL)
    for match in class_pattern.finditer(content)[:3]:
        parts.append(f"class {match.group(1)}:\n    \"\"\"{match.group(2)[:100]}...\"\"\"")

    func_pattern = re.compile(r'^def\s+(\w+)\(([^)]*)\).*?:\s*\n\s*"""(.+?)"""', re.MULTILINE | re.DOTALL)
    for match in func_pattern.finditer(content)[:5]:
        parts.append(f"def {match.group(1)}({match.group(2)[:50]}...):\n    \"\"\"{match.group(3)[:100]}...\"\"\"")

    return "\n\n".join(parts)


def _classify_code(content: str) -> str:
    """Classify code type based on content.

    Args:
        content: File content

    Returns:
        Code type string
    """
    content_lower = content.lower()

    if "test" in content_lower or "unittest" in content_lower or "pytest" in content_lower:
        return "test"
    elif "def main" in content_lower or "if __name__" in content_lower:
        return "entry_point"
    elif "class" in content_lower and ("model" in content_lower or "engine" in content_lower):
        return "core_logic"
    elif "@dataclass" in content_lower or "typing" in content_lower:
        return "types"
    else:
        return "utility"


def _extract_project_facts(analysis: ProjectAnalysis) -> List[str]:
    """Convert analysis to factual statements.

    Args:
        analysis: Project analysis

    Returns:
        List of fact strings
    """
    facts = []

    # Extract facts from features
    for feature in analysis.features[:10]:
        if isinstance(feature, dict):
            name = feature.get("feature", feature.get("name", ""))
            desc = feature.get("description", feature.get("evidence", ""))
            if name and desc:
                facts.append(f"The system implements {name}: {desc}")

    # Extract architecture facts
    arch = analysis.architecture
    if arch:
        patterns = arch.get("patterns", [])
        if patterns:
            facts.append(f"Architecture patterns used: {', '.join(patterns[:5])}")

    # Note issues as limitations
    for issue in analysis.issues[:3]:
        if isinstance(issue, dict):
            name = issue.get("issue", issue.get("name", ""))
            if name:
                facts.append(f"Known limitation: {name}")

    return facts


def _query_memory_for_papers(section_key: str, max_results: int = 5) -> List[Dict[str, str]]:
    """Query memory skill for relevant paper excerpts.

    Args:
        section_key: Section key to guide query
        max_results: Maximum results

    Returns:
        List of paper excerpt dicts
    """
    excerpts = []

    if not MEMORY_SCRIPT.exists():
        return excerpts

    # Build query based on section
    section_queries = {
        "intro": "problem statement motivation",
        "related": "prior work approaches",
        "method": "methodology algorithm approach",
        "eval": "evaluation experiments results",
        "discussion": "limitations future work",
    }

    query = section_queries.get(section_key, "research approach")

    try:
        result = subprocess.run(
            [str(MEMORY_SCRIPT), "recall", query, "--limit", str(max_results)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            # Parse memory output (assuming JSON or structured text)
            try:
                data = json.loads(result.stdout)
                for item in data.get("results", [])[:max_results]:
                    excerpts.append({
                        "paper_id": item.get("source", "unknown"),
                        "excerpt": item.get("content", "")[:500],
                        "topic": section_key,
                    })
            except json.JSONDecodeError:
                # Fallback: treat output as plain text
                if result.stdout.strip():
                    excerpts.append({
                        "paper_id": "memory",
                        "excerpt": result.stdout[:500],
                        "topic": section_key,
                    })
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass

    return excerpts


def _parse_research_context(research_context: str) -> List[str]:
    """Parse research context into factual statements.

    Args:
        research_context: Combined research output from dogpile

    Returns:
        List of research facts
    """
    facts = []

    # Split by sections (## headers)
    sections = research_context.split("## ")
    for section in sections[1:]:  # Skip empty first part
        lines = section.strip().split("\n")
        if lines:
            topic = lines[0].strip()
            # Extract key findings (lines starting with - or *)
            for line in lines[1:]:
                line = line.strip()
                if line.startswith(("-", "*")) and len(line) > 10:
                    facts.append(f"Research finding ({topic[:20]}): {line[1:].strip()}")

    return facts[:10]  # Limit to 10 facts


def build_persona_prompt(
    base_prompt: str,
    persona: Optional[AgentPersona],
    persona_strength: float = 1.0,
) -> str:
    """Build a prompt with persona guidance integrated.

    Args:
        base_prompt: Base prompt content
        persona: Optional persona to apply
        persona_strength: 0.0 to 1.0 intensity

    Returns:
        Prompt with persona guidance
    """
    if not persona or persona_strength < 0.1:
        return base_prompt

    # Build persona guidance based on strength
    guidance_parts = []

    if persona_strength >= 0.3:
        # Add voice guidance
        guidance_parts.append(f"Voice: {persona.voice}")

    if persona_strength >= 0.5:
        # Add writing principles
        principles = persona.writing_principles[:int(3 + persona_strength * 4)]
        if principles:
            guidance_parts.append("Writing principles:")
            for p in principles:
                guidance_parts.append(f"  - {p}")

    if persona_strength >= 0.7:
        # Add characteristic phrases to use
        phrases = persona.characteristic_phrases[:5]
        if phrases:
            guidance_parts.append("Characteristic phrases to incorporate:")
            for p in phrases:
                guidance_parts.append(f"  - \"{p}\"")

    if persona_strength >= 0.9:
        # Add forbidden phrases
        if persona.forbidden_phrases:
            guidance_parts.append("NEVER use these phrases:")
            for p in persona.forbidden_phrases[:5]:
                guidance_parts.append(f"  - \"{p}\"")

    # Add persona identification if at full strength
    if persona_strength >= 1.0:
        guidance_parts.insert(0, f"You are {persona.name}. {persona.authority_source}")

    persona_guidance = "\n".join(guidance_parts)

    return f"{base_prompt}\n\n---\nPersona Guidance (strength: {persona_strength:.1f}):\n{persona_guidance}"


def verify_claim(
    claim_text: str,
    rag_context: RAGContext,
) -> Dict[str, Any]:
    """Verify a claim against RAG context.

    Args:
        claim_text: The claim to verify
        rag_context: RAG context with evidence

    Returns:
        Verification result dict
    """
    result = {
        "claim": claim_text,
        "support_level": "Unsupported",
        "evidence": [],
        "suggestions": [],
    }

    claim_lower = claim_text.lower()

    # Check code snippets for support
    for snippet in rag_context.code_snippets:
        if any(word in snippet["content"].lower() for word in claim_lower.split()[:5]):
            result["evidence"].append(f"Code: {snippet['file']}")

    # Check project facts for support
    for fact in rag_context.project_facts:
        if any(word in fact.lower() for word in claim_lower.split()[:5]):
            result["evidence"].append(f"Fact: {fact[:50]}...")

    # Check research facts for support
    for fact in rag_context.research_facts:
        if any(word in fact.lower() for word in claim_lower.split()[:5]):
            result["evidence"].append(f"Research: {fact[:50]}...")

    # Determine support level
    if len(result["evidence"]) >= 3:
        result["support_level"] = "Supported"
    elif len(result["evidence"]) >= 1:
        result["support_level"] = "Partially Supported"
    else:
        result["support_level"] = "Unsupported"
        result["suggestions"].append("Add citation or code reference to support this claim")

    return result
