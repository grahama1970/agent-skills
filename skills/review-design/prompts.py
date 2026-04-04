"""
Prompt templates for the 3-step design review pipeline.

Step 1: Audit - Analyze screenshots against tokens and reference
Step 2: Judge - Critique the audit findings
Step 3: Finalize - Produce actionable recommendations

All prompts loaded from /prompt-lab/prompts/*.txt files.
"""
from pathlib import Path

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompt-lab" / "prompts"


def _load_prompt(name: str) -> str:
    """Load a validated prompt from /prompt-lab/prompts/{name}.txt."""
    path = _PROMPT_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt '{name}' not found at {path}")
    return path.read_text().strip()


SYSTEM_PROMPT = _load_prompt("review_design_system")
STEP1_AUDIT_PROMPT = _load_prompt("review_design_step1_audit")
STEP2_JUDGE_PROMPT = _load_prompt("review_design_step2_judge")
STEP3_FINALIZE_PROMPT = _load_prompt("review_design_step3_finalize")
_PERSONA_TEMPLATE = _load_prompt("review_design_persona")


def build_persona_system_prompt(persona_name: str, persona_context: str) -> str:
    """Build a system prompt that fuses the base design review expertise with persona identity.

    The persona context (AGENTS.md + memory recall) is injected so the LLM reviews
    from that persona's perspective — their domain expertise, review dimensions,
    relationships, and accumulated QRA knowledge.

    This is NON-NEGOTIABLE. Without this, reviews are generic and useless.
    """
    return SYSTEM_PROMPT + "\n\n" + _PERSONA_TEMPLATE.format(
        persona_name=persona_name,
        persona_context=persona_context,
    )


def format_step1_prompt(tokens_json: str, focus_areas: list[str] | None = None) -> str:
    """Format the Step 1 audit prompt with tokens and focus areas."""
    focus_str = "\n".join(f"- {area}" for area in (focus_areas or [])) or "None specified"
    return STEP1_AUDIT_PROMPT.format(
        tokens_json=tokens_json,
        focus_areas=focus_str
    )


def format_step2_prompt(step1_output: str) -> str:
    """Format the Step 2 judge prompt with Step 1 output."""
    return STEP2_JUDGE_PROMPT.format(step1_output=step1_output)


def format_step3_prompt(step1_output: str, step2_output: str) -> str:
    """Format the Step 3 finalize prompt with previous outputs."""
    return STEP3_FINALIZE_PROMPT.format(
        step1_output=step1_output,
        step2_output=step2_output
    )
