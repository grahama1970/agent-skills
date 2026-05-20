"""Persona consultation logic for matching questions to stored expertise profiles."""


from .env import load_dotenv_once

load_dotenv_once()
#!/usr/bin/env python3
"""
/ask consult — Generate responses AS a persona.

Persona-generic: works for any of ~200 personas (Brandon, Embry, Jodorowsky, etc.)

Pipeline:
  1. Discover persona (memory → skill files → auto-ingest)
  2. Load persona profile + bridge scores
  3. Retrieve relevant knowledge from persona's scope
  4. Build persona system prompt
  5. Generate response via scillm
  6. Output formatted response
"""

import typer
import httpx
import json
import os
import sys
from pathlib import Path
from typing import Optional

from loguru import logger as log

from .skills_exec import parse_memory_output, run_memory_recall

log.remove()
if os.environ.get("ASK_DEBUG"):
    log.add(sys.stderr, level="DEBUG")
else:
    log.add(sys.stderr, level="INFO")

SKILLS_DIR = Path(__file__).parent.parent
SCILLM_URL = "http://localhost:4001"

# Persona discovery paths
PERSONA_SOURCES = [
    # Skill directories with persona files
    SKILLS_DIR,
    # Media personas
    Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb")) / "media" / "personas",
]


def recall_memory(query: str, scope: str, k: int = 5, timeout: int = 15) -> list:
    """Recall from memory through the memory skill."""
    result = run_memory_recall(query, scope, k=k, timeout=timeout)
    if result["returncode"] != 0:
        log.error("memory recall failed: %s", result["stderr"][:200])
        return []
    return parse_memory_output(result["stdout"])


def discover_persona(name: str) -> Optional[dict]:
    """Discover a persona from memory or skill files.

    Search order:
    1. Memory (scope=personas)
    2. Skill directory persona files (*_PERSONA.md, *_persona.yaml)
    3. personas.yaml in /create-persona
    """
    # 1. Search memory
    log.info(f"Searching memory for persona: {name}")
    results = recall_memory(name, scope="personas", k=3)
    if results:
        for r in results:
            content = r.get("solution", r.get("content", r.get("text", "")))
            if name.lower() in content.lower():
                return {
                    "name": name,
                    "source": "memory",
                    "content": content,
                    "scope": r.get("scope", "personas"),
                }

    # 2. Search skill persona files
    log.info(f"Searching skill dirs for persona files matching: {name}")
    name_lower = name.lower().replace(" ", "_").replace(".", "")
    for source_dir in PERSONA_SOURCES:
        if not source_dir.exists():
            continue
        # Search for *PERSONA.md or *persona.yaml
        for pattern in ["**/*PERSONA*.md", "**/*persona*.yaml", "**/*PERSONA*.yaml"]:
            for f in source_dir.glob(pattern):
                if name_lower in f.stem.lower() or name_lower in f.name.lower():
                    content = f.read_text()
                    return {
                        "name": name,
                        "source": "file",
                        "path": str(f),
                        "content": content,
                        "scope": _detect_scope(f),
                    }

    # 3. Search personas.yaml
    personas_yaml = SKILLS_DIR / "create-persona" / "personas.yaml"
    if personas_yaml.exists():
        try:
            import yaml
            with open(personas_yaml) as f:
                manifest = yaml.safe_load(f)
            # Search all persona groups
            for group_name, personas in manifest.items():
                if group_name == "defaults" or not isinstance(personas, list):
                    continue
                for p in personas:
                    if isinstance(p, dict) and p.get("name", "").lower() == name.lower():
                        return {
                            "name": p["name"],
                            "source": "personas.yaml",
                            "content": json.dumps(p, indent=2),
                            "scope": manifest.get("defaults", {}).get("scope", "personas"),
                            "bridges": p.get("bridges", {}),
                            "expertise": p.get("expertise", []),
                            "goals": p.get("goals", []),
                        }
        except Exception as e:
            log.error(f"personas.yaml parse failed: {e}")

    return None


def _detect_scope(path: Path) -> str:
    """Detect memory scope from file path."""
    path_str = str(path).lower()
    if "sparta" in path_str:
        return "sparta"
    if "lore" in path_str or "horus" in path_str:
        return "lore"
    if "behavioral" in path_str:
        return "behavioral"
    return "personas"


def build_persona_prompts(
    persona: dict, question: str, context: str = "",
    dream_context: Optional[dict] = None,
) -> tuple:
    """Build system + user prompts for persona consultation.

    Returns (system_prompt, user_prompt) tuple. System prompt contains the
    persona identity/character sheet. User prompt contains the question + context.
    """
    name = persona["name"]
    content = persona.get("content", "")
    bridges = persona.get("bridges", {})
    expertise = persona.get("expertise", [])
    goals = persona.get("goals", [])

    # System prompt: persona identity
    sys_parts = [f"You are {name}. Respond AS {name}, in their authentic voice."]
    sys_parts.append("Do not break character. Do not explain that you are role-playing.")
    sys_parts.append("")

    if expertise:
        sys_parts.append("## Expertise")
        for e in expertise[:10]:
            sys_parts.append(f"- {e}")
        sys_parts.append("")

    if goals:
        sys_parts.append("## Goals & Priorities")
        for g in goals[:8]:
            sys_parts.append(f"- {g}")
        sys_parts.append("")

    if bridges:
        sys_parts.append("## Personality Dimensions (Bridge Attributes)")
        for bridge, score in sorted(bridges.items(), key=lambda x: -x[1]):
            intensity = "strong" if score >= 0.8 else ("moderate" if score >= 0.5 else "mild")
            sys_parts.append(f"- {bridge}: {intensity} ({score})")
        sys_parts.append("")

    if content and len(content) > 100:
        truncated = content[:2000]
        if len(content) > 2000:
            truncated += "\n[...truncated]"
        sys_parts.append("## Character Reference")
        sys_parts.append(truncated)
        sys_parts.append("")

    if dream_context:
        sys_parts.append("## Recent Dream")
        sys_parts.append(f"You recently dreamed: {dream_context['text']}")
        sys_parts.append(f"This dream left you feeling {dream_context['mood']}. It lingers at the edges of your awareness.")
        sys_parts.append("You may reference this dream if the conversation touches on related themes, or if making small talk. Do not force it into every response.")
        sys_parts.append("")

    # User prompt: context + question
    user_parts = []
    if context:
        user_parts.append("## Relevant Knowledge (for grounding your response)")
        user_parts.append(context)
        user_parts.append("")

    user_parts.append(question)

    return "\n".join(sys_parts), "\n".join(user_parts)


def generate_response(user_prompt: str, system_prompt: str = "", timeout: int = 60) -> Optional[str]:
    """Generate response via scillm HTTP proxy with optional system prompt."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt[:4000]})
    messages.append({"role": "user", "content": user_prompt[:4000]})

    try:
        payload = {"model": "deepseek-ai/DeepSeek-V3", "messages": messages}
        resp = httpx.post(
            f"{SCILLM_URL}/v1/chat/completions",
            json=payload,
            timeout=float(timeout),
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return content.strip() if content else None
    except httpx.HTTPStatusError as e:
        log.error(f"scillm HTTP error: {e.response.status_code}")
        return None
    except httpx.TimeoutException:
        log.error(f"scillm timed out after {timeout}s")
        return None
    except Exception as e:
        log.error(f"scillm error: {e}")
        return None


def retrieve_context(persona: dict, question: str) -> str:
    """Retrieve relevant knowledge for grounding the persona's response."""
    scope = persona.get("scope", "personas")
    results = recall_memory(question, scope=scope, k=5)

    if not results:
        # Try broader search
        results = recall_memory(question, scope="personas", k=3)

    if not results:
        return ""

    context_parts = []
    for r in results[:5]:
        problem = r.get("problem", "")
        solution = r.get("solution", r.get("content", r.get("text", "")))
        if solution:
            context_parts.append(solution[:500])

    return "\n---\n".join(context_parts)


def recall_dream_context(persona_name: str) -> Optional[dict]:
    """Recall the most recent dream reflection for a persona.

    Returns dict with text, mood, scope — or None if no dreams found.
    """
    scope = f"{persona_name.lower().replace(' ', '-')}-dream-journals"
    results = recall_memory(f"Dream reflection", scope=scope, k=1)
    if not results:
        return None

    entry = results[0]
    text = entry.get("solution", entry.get("content", entry.get("text", "")))
    if not text or len(text) < 20:
        return None

    # Extract mood from tags or bridge keywords
    tags = entry.get("tags", "")
    mood = "contemplative"
    for bridge, bridge_mood in [
        ("Fragility", "wistful"), ("Resilience", "hopeful"),
        ("Corruption", "haunted"), ("Loyalty", "contemplative"),
        ("Stealth", "curious"), ("Precision", "focused"),
    ]:
        if bridge.lower() in tags.lower() or bridge.lower() in text.lower():
            mood = bridge_mood
            break

    return {"text": text[:300], "mood": mood, "scope": scope}


def format_response(name: str, response: str, source: str = "") -> str:
    """Format the persona's response for output."""
    lines = [
        f"── {name}'s Response ──",
        "",
        response,
        "",
    ]
    if source:
        lines.append(f"[Source: {source}]")
    return "\n".join(lines)


def consult(
    persona_name: str,
    question: str,
    also_ask: Optional[list] = None,
    context: str = "",
    json_output: bool = False,
    debug: bool = False,
):
    """Main consult function - works for any persona."""
    if debug:
        log.remove()
        log.add(sys.stderr, level="DEBUG")

    responses = []

    # Process primary persona
    persona = discover_persona(persona_name)
    if not persona:
        print(f"Persona not found: {persona_name}", file=sys.stderr)
        print(f"Searched: memory (scope=personas), skill dirs, personas.yaml", file=sys.stderr)
        sys.exit(1)

    log.info(f"Found persona: {persona['name']} (source: {persona.get('source', '?')})")

    # Retrieve grounding context
    grounding = retrieve_context(persona, question)
    if context:
        grounding = context + "\n---\n" + grounding if grounding else context

    # Recall dream context for persona
    dream_ctx = recall_dream_context(persona_name)
    if dream_ctx:
        log.debug(f"Dream context found for {persona_name}: {dream_ctx['mood']} mood")
    else:
        log.debug(f"No dream context for {persona_name}")

    # Build system + user prompts and generate
    sys_prompt, user_prompt = build_persona_prompts(persona, question, grounding, dream_context=dream_ctx)
    log.debug(f"System prompt: {len(sys_prompt)} chars, User prompt: {len(user_prompt)} chars")

    response = generate_response(user_prompt, system_prompt=sys_prompt)
    if response:
        responses.append({
            "persona": persona["name"],
            "response": response,
            "source": persona.get("source", "unknown"),
            "scope": persona.get("scope", "personas"),
        })
    else:
        responses.append({
            "persona": persona["name"],
            "response": "[Generation failed - check scillm availability]",
            "source": persona.get("source", "unknown"),
            "error": True,
        })

    # Process additional personas (--also-ask)
    if also_ask:
        for other_name in also_ask:
            other_name = other_name.strip()
            if not other_name:
                continue

            other_persona = discover_persona(other_name)
            if not other_persona:
                responses.append({
                    "persona": other_name,
                    "response": f"[Persona not found: {other_name}]",
                    "error": True,
                })
                continue

            other_grounding = retrieve_context(other_persona, question)
            other_dream = recall_dream_context(other_name)
            other_sys, other_user = build_persona_prompts(other_persona, question, other_grounding, dream_context=other_dream)
            other_response = generate_response(other_user, system_prompt=other_sys)

            responses.append({
                "persona": other_persona["name"],
                "response": other_response or "[Generation failed]",
                "source": other_persona.get("source", "unknown"),
                "scope": other_persona.get("scope", "personas"),
                "error": other_response is None,
            })

    # Output
    if json_output:
        print(json.dumps({"responses": responses}, indent=2))
    else:
        for r in responses:
            print(format_response(
                r["persona"],
                r["response"],
                source=r.get("source", ""),
            ))
            print()


app = typer.Typer(help="Consult a persona")


@app.command()
def main(
    persona: str = typer.Argument(help="Persona name"),
    question: str = typer.Argument(help="Question to ask"),
    also_ask: str = typer.Option(None, help="Comma-separated additional personas"),
    context: str = typer.Option("", help="Additional context"),
    json_output: bool = typer.Option(False, help=""),
    debug: bool = typer.Option(False, help=""),
):
    also_ask = [n.strip() for n in also_ask.split(",")] if also_ask else None

    consult(
        persona_name=persona,
        question=question,
        also_ask=also_ask,
        context=context,
        json_output=json_output,
        debug=debug,
    )


if __name__ == "__main__":
    app()
