"""prompter - create-movie.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

import httpx
import json
import os
import subprocess
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path
from rich.console import Console

console = Console()

SKILL_DIR = Path(__file__).parent
PI_SKILLS_DIR = SKILL_DIR.parent

_PROMPT_DIR = PI_SKILLS_DIR / "prompt-lab" / "prompts"


def _load_prompt(name: str) -> str:
    path = _PROMPT_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt '{name}' not found at {path}")
    return path.read_text().strip()


@dataclass
class DreamScene:
    id: int
    visual_prompt: str
    narration: str
    audio_cue: str
    duration: int = 5
    memory_source: Optional[str] = None


SCILLM_URL = "http://localhost:4001"


class DreamPrompter:
    def __init__(self, model_name: str = "scillm"):
        self.model_name = model_name

    def generate_dream_prompts(
        self,
        memories: List[Dict[str, Any]],
        count: int = 5,
        structured_items: Optional[List[dict]] = None,
    ) -> List[DreamScene]:
        """
        Transform raw memories into surreal dream scenes via scillm/Chutes.

        Args:
            memories: List of dicts with 'text', 'type' (backward compat)
            count: Number of scenes to generate
            structured_items: Optional structured residue items with type/weight/source

        Returns:
            List of DreamScene objects
        """
        if not memories and not structured_items:
            return []

        # Build memory text — prefer structured items when available
        if structured_items:
            memory_text = _format_structured_residue(structured_items)
        else:
            memory_text = "\n".join([f"- [{m.get('type')}] {m.get('text')}" for m in memories])

        # Extract sensory summary for differential rendering instructions
        sensory_items = [it for it in (structured_items or []) if it.get("sensory")]
        sensory_block = ""
        if sensory_items:
            sensory_block = """
SENSORY RENDERING RULES (research-backed):
- [touch/temperature/pain] → Render as DIRECT scene content. The dreamer FEELS these.
  Make them physical: "ceramite cold under gauntlets", "heat rippling off the hull".
  These are the most vivid — the body crosses the sleep barrier.
- [smell] → Use to SET EMOTIONAL TONE, not literal objects. Smell modulates mood.
  "The air carries something copper-sweet" (anxiety), "ozone and old books" (curiosity).
- [taste] → RARE vivid anchor. Use sparingly but make it unforgettable.
  One taste in 5 scenes. "Iron on the tongue", "sweetness that shouldn't be there".
- [proprioception] → Body-awareness grounding. "Falling sensation", "limbs too heavy",
  "the dream-body stretching beyond its edges". The sleeping body leaks into the dream.
- Specific substances > generic labels. "Ceramite" not "metal". "Lho-stick smoke" not "smoke".
"""

        prompt = _load_prompt("create_movie_dream_prompter_v1").format(
            memory_text=memory_text,
            sensory_block=sensory_block,
            count=count,
        )

        try:
            console.print("[dim]Consulting the Subconscious (scillm/Chutes)...[/dim]")
            payload = {
                "model": "deepseek-ai/DeepSeek-V3",
                "messages": [{"role": "user", "content": prompt}],
            }
            resp = httpx.post(
                f"{SCILLM_URL}/v1/chat/completions",
                json=payload,
                timeout=60.0,
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"].strip()
            if not raw:
                console.print("[red]scillm returned empty response[/red]")
                return []
            data = json.loads(raw)

            # Handle both list and dict responses
            if isinstance(data, dict):
                # LLM may wrap scenes in an object like {"scenes": [...]}
                for key in ("scenes", "dream_scenes", "items", "results"):
                    if isinstance(data.get(key), list):
                        data = data[key]
                        break
                else:
                    # Take first list value found in the dict
                    for v in data.values():
                        if isinstance(v, list):
                            data = v
                            break

            if not isinstance(data, list):
                console.print(f"[red]Expected JSON list from scillm, got {type(data).__name__}: {list(data.keys()) if isinstance(data, dict) else str(data)[:200]}[/red]")
                return []

            scenes = []
            for i, item in enumerate(data):
                scenes.append(DreamScene(
                    id=i + 1,
                    visual_prompt=item.get("visual_prompt", ""),
                    narration=item.get("narration", ""),
                    audio_cue=item.get("audio_cue", ""),
                    duration=item.get("duration", 5),
                    memory_source=item.get("memory_source"),
                ))
            return scenes

        except httpx.TimeoutException:
            console.print("[red]scillm timed out (60s)[/red]")
            return []
        except Exception as e:
            console.print(f"[red]Dream generation failed: {e}[/red]")
            return []


def _format_structured_residue(items: List[dict]) -> str:
    """Format structured residue items with importance labels for LLM prompt.

    Contradiction-type items get a [TENSION] label to signal the LLM
    that these are unresolved conflicts — the dramatic engine of dreams.
    """
    lines = []
    for item in items:
        item_type = item.get("type", "Unknown")
        text = item.get("text", "")

        if item_type == "Contradiction":
            # Tensions are always high-priority dream material
            lines.append(f"- [TENSION] {text}")
            continue

        weight = item.get("weight", 0.5)
        if weight >= 0.6:
            importance = "HIGH"
        elif weight >= 0.15:
            importance = "MEDIUM"
        else:
            importance = "LOW"

        # Append sensory channels if tagged (e.g., [smell, touch])
        sensory = item.get("sensory", [])
        sensory_hint = f" [senses: {', '.join(sensory)}]" if sensory else ""
        lines.append(f"- [{importance}] {item_type}: {text}{sensory_hint}")
    return "\n".join(lines)


if __name__ == "__main__":
    prompter = DreamPrompter()
    test_memories = [
        {"type": "lesson", "text": "Learning to fly in a lucid dream"},
        {"type": "episode", "text": "Arguments with the shadow self"},
        {"type": "residue", "text": "Forgot to turn off the oven"},
    ]
    scenes = prompter.generate_dream_prompts(test_memories)
    for s in scenes:
        print(f"Scene {s.id}: {s.visual_prompt[:50]}...")
