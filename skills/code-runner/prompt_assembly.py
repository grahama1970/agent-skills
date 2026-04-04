"""Memory-backed prompt assembly for code-runner.

Builds a single system prompt from a /prompt-lab template with placeholders.
All variable content is injected via string replacement — the LLM sees one
clean document, not appended sections.

Three data sources:
1. Task spec (original request, DoD, allowlist) — immutable anchor
2. Local round history (last 2 rounds) — what just happened
3. /memory recall (similar solved problems) — cross-session learning
"""
from __future__ import annotations

from pathlib import Path


def build_system_prompt(
    task_id: str,
    session_key: str,
    task_desc: str,
    round_num: int,
    dod_desc: str = "",
    allowlist: list[str] | None = None,
    recent_rounds: list[dict] | None = None,
) -> str:
    """Build system prompt — single template, all placeholders filled."""
    _prompt_dir = Path(__file__).resolve().parent.parent / "prompt-lab" / "prompts"
    # v3 (structured edit ops) preferred over v2 (hybrid diff+complete file)
    _system_template = _prompt_dir / "code_runner_system_v3.txt"
    if not _system_template.exists():
        _system_template = _prompt_dir / "code_runner_system_v2.txt"
    if _system_template.exists():
        base = _system_template.read_text().strip()
    else:
        base = (
            "You are a code-fixing agent.\n\n"
            "ORIGINAL REQUEST:\n{original_request}\n\n"
            "DEFINITION OF DONE:\n{definition_of_done}\n\n"
            "EDITABLE FILES:\n{allowlist}\n\n"
            "OUTPUT: Line 1 = JSON {\"summary\":\"...\",\"approach\":\"...\",\"files_changed\":[...]}\n"
            "Line 2 = ---\n"
            "Then ### FILE: blocks with ```diff and ```python blocks.\n\n"
            "{similar_solved_problems}\n\n{last_2_rounds}"
        )

    # 1. Immutable anchors
    base = base.replace("{original_request}", task_desc)
    base = base.replace("{definition_of_done}", dod_desc or "(not specified)")
    allowlist_str = "\n".join(f"  - {f}" for f in (allowlist or []))
    base = base.replace("{allowlist}", allowlist_str or "(no files specified — task must set allowlist or allowlist_optional)")

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
