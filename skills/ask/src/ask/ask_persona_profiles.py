"""Persona profile recall and formatting for ask oracle mode."""

import json
from typing import Optional

from .skills_exec import parse_memory_output, run_memory_recall

def _load_oracle_persona_profiles(
    persona: Optional[str],
    peer: Optional[str],
    consult_personas: list[dict],
    persona_scope: str,
) -> dict[str, dict]:
    """Load actual stored persona profiles for oracle roles."""
    names: list[str] = []
    for name in [persona, peer]:
        if name:
            names.append(name)
    for item in consult_personas:
        name = item.get("name")
        if name:
            names.append(str(name))

    profiles: dict[str, dict] = {}
    seen: set[str] = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        profile = _recall_persona_profile(name, persona_scope)
        if profile:
            profiles[name] = profile
    return profiles


def _recall_persona_profile(name: str, persona_scope: str) -> dict | None:
    """Recall the best stored persona profile for a name or alias."""
    queries = [
        f"Persona: {name}",
        f"Persona profile: {name}",
        f"{name} persona profile",
        f"{name} persona lore",
        f"{name} persona lessons",
        f"{name} lessons learned",
    ]
    scopes = [persona_scope, ""]
    for scope in scopes:
        for query in queries:
            recall_result = run_memory_recall(query, scope, k=3, timeout=15)
            if recall_result["returncode"] != 0:
                continue
            items = parse_memory_output(recall_result["stdout"])
            profile = _extract_persona_profile(name, items)
            if profile:
                return profile
    return None


def _extract_persona_profile(name: str, items: list[dict]) -> dict | None:
    """Extract a profile object from memory recall results."""
    name_lower = name.lower()
    for item in items:
        problem = str(item.get("problem", "")).lower()
        tags = [str(tag).lower() for tag in item.get("tags", []) if isinstance(tag, str)]
        solution = item.get("solution", "")
        if "persona" not in problem and "persona" not in tags:
            continue
        if name_lower.split()[0] not in problem and not any(name_lower.split()[0] in tag for tag in tags):
            continue
        if isinstance(solution, str):
            try:
                parsed = json.loads(solution)
            except json.JSONDecodeError:
                parsed = {"raw": solution}
        elif isinstance(solution, dict):
            parsed = solution
        else:
            parsed = {"raw": str(solution)}
        parsed["_memory_problem"] = item.get("problem", "")
        parsed["_memory_scope"] = item.get("scope", "")
        return parsed
    return None


def _format_persona_profile_for_prompt(label: str, profile: dict) -> str:
    """Render a bounded persona profile for oracle prompts."""
    keep_keys = [
        "name",
        "aliases",
        "role",
        "organization",
        "domain",
        "expertise",
        "communication_style",
        "preferred_format",
        "goals",
        "concerns",
        "constraints",
        "bridge_weights",
        "scope",
        "tags",
    ]
    compact = {key: profile[key] for key in keep_keys if key in profile and profile[key]}
    if not compact and profile.get("raw"):
        return f"Stored persona profile for {label}:\n{str(profile['raw'])[:4000]}"
    return f"Stored persona profile for {label}:\n{json.dumps(compact, indent=2, default=str)[:4000]}"


def _format_persona_suggestion(personas: list[dict]) -> str:
    """Format persona recommendations without re-querying memory."""
    if not personas:
        return ""
    lines = ["\n  Suggested personas to consult:"]
    for persona in personas:
        bridge_str = ", ".join(persona["bridges"]) if persona["bridges"] else "domain match"
        lines.append(f"    - {persona['name']} ({persona.get('role', 'expert')}) [{bridge_str}]")
    return "\n".join(lines)
