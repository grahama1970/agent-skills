"""Memory-backed prompt assembly for code-runner.

Builds a single system prompt from a /prompt-lab template with placeholders.
All variable content is injected via string replacement — the LLM sees one
clean document, not appended sections.

Four data sources:
1. Task spec (original request, DoD, allowlist) — immutable anchor
2. Skill documentation (SKILL.md) — deterministically injected, not optional
3. Local round history (last 2 rounds) — what just happened
4. /memory recall (similar solved problems) — cross-session learning
"""
from __future__ import annotations

from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent.parent


def _compile_skill_docs(skill_names: list[str]) -> str:
    """Deterministically read and compile full SKILL.md files.

    This is the trust boundary: the LLM cannot skip reading these docs
    because they are injected directly into its system prompt by code,
    not by the LLM's choice.
    """
    if not skill_names:
        return "(no skills referenced)"

    sections = []
    for name in skill_names:
        skill_md = SKILLS_DIR / name / "SKILL.md"
        if not skill_md.exists():
            sections.append(f"### SKILL: /{name}\n⚠ SKILL.md not found at {skill_md}\n")
            continue

        text = skill_md.read_text()
        # Strip YAML frontmatter — keep only the human-readable docs
        lines = text.splitlines()
        content_start = 0
        if lines and lines[0].strip() == "---":
            for i, line in enumerate(lines[1:], 1):
                if line.strip() == "---":
                    content_start = i + 1
                    break
        content = "\n".join(lines[content_start:])
        sections.append(f"### SKILL: /{name}\n{content}\n")

    return "\n".join(sections)


def build_system_prompt(
    task_id: str,
    session_key: str,
    task_desc: str,
    round_num: int,
    dod_desc: str = "",
    allowlist: list[str] | None = None,
    recent_rounds: list[dict] | None = None,
    skills_used: list[str] | None = None,
) -> str:
    """Build system prompt — single template, all placeholders filled."""
    _prompt_dir = Path(__file__).resolve().parent.parent / "prompt-lab" / "prompts"
    _system_template = _prompt_dir / "code_runner_system_v3.txt"
    if _system_template.exists():
        base = _system_template.read_text().strip()
    else:
        base = (
            "You are a code-fixing agent. Use the provided tools (write_file, edit_file, "
            "read_file, run_command) to make changes.\n\n"
            "ORIGINAL REQUEST:\n{original_request}\n\n"
            "DEFINITION OF DONE:\n{definition_of_done}\n\n"
            "EDITABLE FILES:\n{allowlist}\n\n"
            "{skill_docs}\n\n"
            "{similar_solved_problems}\n\n{last_2_rounds}"
        )

    # 1. Immutable anchors
    base = base.replace("{original_request}", task_desc)
    base = base.replace("{definition_of_done}", dod_desc or "(not specified)")
    allowlist_str = "\n".join(f"  - {f}" for f in (allowlist or []))
    base = base.replace("{allowlist}", allowlist_str or "(no files specified — task must set allowlist or allowlist_optional)")

    # 2. Skill documentation — deterministic injection (trust boundary)
    skill_docs = _compile_skill_docs(skills_used or [])
    base = base.replace("{skill_docs}", skill_docs)

    # 2. Last 2 rounds (local history — what just happened)
    rounds_block = "(first round — no prior history)"
    if recent_rounds:
        last_2 = recent_rounds[-2:]
        lines = []
        for r in last_2:
            lines.append(
                f"  Round {r.get('round', '?')}: "
                f"score={r.get('score', 0):.3f} "
                f"strategy={r.get('strategy', '?')} "
                f"status={r.get('status', '?')} "
                f"errors={r.get('error_count', 0)}"
            )
        rounds_block = "\n".join(lines)
    base = base.replace("{last_2_rounds}", rounds_block)

    # 3. Similar solved problems (from /memory — cross-session)
    from evidence import recall_similar_fixes
    prior = recall_similar_fixes(task_desc, "")

    # Also recall by current error type if we have round history
    error_recall = ""
    if recent_rounds:
        last = recent_rounds[-1]
        err_sev = last.get("error_severity", "")
        err_types = last.get("errors_by_type", {})
        if err_sev and err_sev != "unknown":
            error_prior = recall_similar_fixes(
                f"{err_sev} error {' '.join(err_types.keys())}", err_sev,
            )
            if error_prior and error_prior != prior:
                error_recall = f"\nSimilar errors fixed before:\n{error_prior}"

    combined = (prior or "(no similar solved problems found)") + error_recall
    base = base.replace("{similar_solved_problems}", combined)

    return base
