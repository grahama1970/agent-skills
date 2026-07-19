"""Select the best dream-idea candidate.

Default: call scillm one-shot to reason about theory-of-mind fit and impact.
Fallback: highest impact_score.
"""
from __future__ import annotations

import importlib.util as _ilu
from pathlib import Path
from typing import Any

# Route model inference through the sanctioned Tau text-reasoning node
# (only /tau may reach /scillm); no direct scillm POST here.
_ADAPTER_PATH = Path(__file__).resolve().parents[2] / "scripts" / "tau_text_reasoning_adapter.py"
_aspec = _ilu.spec_from_file_location("tau_text_reasoning_adapter", _ADAPTER_PATH)
assert _aspec and _aspec.loader
tau_adapter = _ilu.module_from_spec(_aspec)
_aspec.loader.exec_module(tau_adapter)

# Caller-defined JSON output contract (hash-recorded by the Tau node).
_SELECTION_OUTPUT_CONTRACT = {"selected_candidate_id": "str", "reason": "str"}


def _build_selection_prompt(
    candidates: list[dict[str, Any]],
    persona_ids: list[str],
    about: str | None,
) -> str:
    """Build a prompt asking the subagent to pick the best candidate."""
    about_line = f"The dream should be about: {about}\n" if about else ""
    candidate_text = "\n\n".join(
        f"CANDIDATE {c['candidate_id']}:\n"
        f"  idea: {c['idea']}\n"
        f"  impact_score: {c['impact_score']}\n"
        f"  source_memory_ids: {c.get('source_memory_ids', [])}\n"
        f"  collection: {c.get('collection', '')}"
        for c in candidates
    )

    return (
        "You are selecting a dream idea for a persona-dream pipeline.\n\n"
        f"Persona(s): {', '.join(persona_ids)}\n"
        f"{about_line}"
        "Consider theory-of-mind fit, emotional intensity, dreamability, and whether the idea "
        "would naturally occupy this persona's mind. Do not always pick the most recent memory; "
        "prefer impactful, emotionally charged, or thematically rich material.\n\n"
        f"{candidate_text}\n\n"
        "Reply with ONLY a JSON object in this exact shape:\n"
        '{"selected_candidate_id": "idea_N", "reason": "..."}'
    )


def _select_by_impact(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic fallback: pick candidate with highest impact_score."""
    best = max(candidates, key=lambda c: c.get("impact_score", 0.0))
    return {
        "selected_candidate_id": best["candidate_id"],
        "reason": "Highest impact_score (deterministic fallback).",
    }


def select_best_candidate(
    candidates: list[dict[str, Any]],
    *,
    persona_ids: list[str],
    about: str | None = None,
    selector: str = "scillm",
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Return {selected_candidate_id, reason}. Falls back to impact on error."""
    if not candidates:
        raise ValueError("No candidates to select from")
    if len(candidates) == 1 or selector == "impact":
        return _select_by_impact(candidates)

    prompt = _build_selection_prompt(candidates, persona_ids, about)
    try:
        # Route through Tau (only /tau may reach /scillm). The node returns the
        # selection as a parsed JSON object.
        parsed, _receipt = tau_adapter.dispatch_text_reasoning(
            prompt,
            role="persona-dream-s01-idea-selector",
            output_contract=_SELECTION_OUTPUT_CONTRACT,
            caller_skill="persona-dream-s01-idea",
            timeout_s=timeout,
        )
        if not isinstance(parsed, dict):
            raise ValueError("Tau text node returned no selection JSON")
        selected_id = parsed.get("selected_candidate_id")
        if selected_id not in {c["candidate_id"] for c in candidates}:
            raise ValueError(f"scillm returned unknown candidate id: {selected_id}")
        return {
            "selected_candidate_id": selected_id,
            "reason": parsed.get("reason", "selected by subagent"),
        }
    except Exception as exc:
        # Fail closed: deterministic fallback, but mark that subagent failed
        result = _select_by_impact(candidates)
        result["subagent_error"] = str(exc)
        result["reason"] += f" (subillm selection failed: {exc}; fell back to impact)"
        return result
