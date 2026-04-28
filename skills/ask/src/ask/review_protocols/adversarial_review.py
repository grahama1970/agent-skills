"""Protocolized adversarial review state machine primitives.

Personas provide domain lens and voice. Protocol roles provide the bounded job
each participant must perform in the review loop.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..reviewer_specs import select_reviewer_angles, spec_to_participant

DATE_SENSITIVE_TERMS = (
    "in 2026",
    "in 2025",
    "current",
    "currently",
    "latest",
    "recent",
    "today",
    "now",
    "this year",
)

ARGUE_JUDGE_RUBRIC = (
    "evidence_strength",
    "failure_mode_coverage",
    "assumption_quality",
    "target_relevance",
    "falsifiability",
    "implementation_cost_or_risk",
)

ARGUE_VERDICTS = (
    "FOR",
    "AGAINST",
    "NO_CLEAR_WINNER",
    "INSUFFICIENT_EVIDENCE",
)

PROTOCOL_ROLE_PRESETS: dict[str, list[dict[str, str]]] = {
    "adversarial-review": [
        {
            "role": "failure_mode",
            "label": "Failure Mode Analyst",
            "scope": "Identify concrete failure scenarios and operational breakage.",
            "prohibitions": "Do not evaluate style. Do not propose solutions unless tied to a failure.",
        },
        {
            "role": "evidence_auditor",
            "label": "Evidence Auditor",
            "scope": "Check claims against evidence, missing citations, uncertainty, and freshness.",
            "prohibitions": "Do not optimize design. Do not accept unsupported claims.",
        },
        {
            "role": "complexity_minimizer",
            "label": "Complexity Minimizer",
            "scope": "Flag unnecessary complexity, operational drag, and simpler alternatives.",
            "prohibitions": "Do not introduce new architecture unless removing complexity.",
        },
        {
            "role": "forced_adversary",
            "label": "Forced Adversary",
            "scope": "Challenge consensus and produce non-trivial disagreement.",
            "prohibitions": "Do not agree unless no material disagreement exists and explain why.",
        },
    ],
    "peer-review": [
        {
            "role": "soundness_reviewer",
            "label": "Soundness Reviewer",
            "scope": "Evaluate correctness, validity, and missing assumptions.",
            "prohibitions": "Do not judge presentation except where it hides correctness problems.",
        },
        {
            "role": "novelty_reviewer",
            "label": "Novelty Reviewer",
            "scope": "Evaluate what is new, differentiated, or already known.",
            "prohibitions": "Do not overvalue novelty without utility.",
        },
        {
            "role": "significance_reviewer",
            "label": "Significance Reviewer",
            "scope": "Evaluate practical importance, impact, and stakeholder value.",
            "prohibitions": "Do not ignore feasibility or adoption constraints.",
        },
        {
            "role": "adversarial_reviewer",
            "label": "Adversarial Reviewer",
            "scope": "Find holes, abuse cases, and reasons to reject.",
            "prohibitions": "Do not provide generic critique.",
        },
    ],
    "argue": [
        {
            "role": "for",
            "label": "FOR Advocate",
            "scope": "Make the strongest defensible argument for the proposition.",
            "prohibitions": "Do not ignore material weaknesses. Do not rely on unstated evidence.",
        },
        {
            "role": "against",
            "label": "AGAINST Advocate",
            "scope": "Make the strongest defensible argument against the proposition.",
            "prohibitions": "Do not strawman the FOR side. Do not rely on generic skepticism.",
        },
    ],
}


def is_date_sensitive_question(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in DATE_SENSITIVE_TERMS) or bool(re.search(r"\b20[2-9]\d\b", lowered))


def parse_participant_specs(
    raw: str | None,
    *,
    role_preset: str = "adversarial-review",
) -> list[dict[str, Any]]:
    """Parse `Brandon:failure_mode,Margaret:evidence_auditor` specs."""
    if not raw:
        return []
    role_defs = PROTOCOL_ROLE_PRESETS.get(role_preset, PROTOCOL_ROLE_PRESETS["adversarial-review"])
    role_by_name = {role["role"]: role for role in role_defs}
    chunks = [chunk.strip() for chunk in raw.split(",") if chunk.strip()]
    participants: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks):
        persona = chunk
        role_key = ""
        if ":" in chunk:
            persona, role_key = [part.strip() for part in chunk.split(":", 1)]
        else:
            match = re.match(r"(.+?)\s+as\s+(.+)$", chunk, flags=re.IGNORECASE)
            if match:
                persona = match.group(1).strip()
                role_key = _normalize_role_key(match.group(2))
        if not role_key:
            role_key = role_defs[index % len(role_defs)]["role"]
        role = role_by_name.get(role_key) or {
            "role": role_key,
            "label": role_key.replace("_", " ").title(),
            "scope": f"Perform the {role_key.replace('_', ' ')} role.",
            "prohibitions": "Do not freeform outside the assigned protocol role.",
        }
        participants.append(
            {
                "persona": persona.strip(),
                "protocol_role": role["role"],
                "role_label": role["label"],
                "scope": role["scope"],
                "prohibitions": role["prohibitions"],
                "turn_index": index,
            }
        )
    return participants


def normalize_argue_personas(raw: str | None) -> str:
    """Normalize FOR/AGAINST persona specs for argue mode."""
    if not raw or not raw.strip():
        return "Affirmative:for,Devil's Advocate:against"
    chunks = [chunk.strip() for chunk in raw.split(",") if chunk.strip()]
    if not chunks:
        return "Affirmative:for,Devil's Advocate:against"
    if len(chunks) == 1:
        chunks.append("Devil's Advocate")
    normalized: list[str] = []
    for index, chunk in enumerate(chunks[:2]):
        if ":" in chunk:
            persona, role = [part.strip() for part in chunk.split(":", 1)]
            role_key = _normalize_role_key(role)
            if role_key in {"pro", "positive", "affirmative"}:
                role_key = "for"
            elif role_key in {"con", "negative", "devils_advocate", "devil_s_advocate"}:
                role_key = "against"
            normalized.append(f"{persona}:{role_key}")
            continue
        role_key = "for" if index == 0 else "against"
        normalized.append(f"{chunk}:{role_key}")
    return ",".join(normalized)


def build_argue_prompt_payload(
    *,
    base_prompt: str,
    persona_specs: str | None = None,
    rounds: int = 2,
    persist: str = "summary",
) -> dict[str, Any]:
    """Build the full prompt payload used by argue mode for review tests."""
    normalized_personas = normalize_argue_personas(persona_specs)
    participants = parse_participant_specs(normalized_personas, role_preset="argue")
    state: dict[str, Any] = {
        "claims": [],
        "critiques": [],
        "open_issues": [],
        "turns": [],
        "parallel_reviews": [],
        "roundtable_turns": [],
    }
    total_rounds = max(1, rounds)
    total_turns = len(participants) * total_rounds
    turn_prompts = []
    for round_index in range(total_rounds):
        for participant_index, participant in enumerate(participants):
            turn_number = round_index * len(participants) + participant_index + 1
            turn_prompts.append(
                {
                    "turn_number": turn_number,
                    "round": round_index + 1,
                    "persona": participant["persona"],
                    "protocol_role": participant["protocol_role"],
                    "prompt": build_roundtable_turn_prompt(
                        base_prompt=base_prompt,
                        participant=participant,
                        state=state,
                        turn_number=turn_number,
                        total_turns=total_turns,
                        mode="argue",
                    ),
                }
            )
    return {
        "schema_version": "ask.argue.prompt_payload.v1",
        "mode": "argue",
        "base_prompt": base_prompt,
        "personas": normalized_personas,
        "rounds": total_rounds,
        "persist": persist,
        "judge_rubric": list(ARGUE_JUDGE_RUBRIC),
        "verdicts": list(ARGUE_VERDICTS),
        "turn_prompts": turn_prompts,
        "moderator_prompt": build_moderator_prompt(
            base_prompt=base_prompt,
            state=state,
            mode="roundtable:argue",
            persist=persist,
        ),
    }


def default_parallel_participants(
    count: int,
    *,
    focus: str | None = None,
    role_preset: str = "adversarial-review",
) -> list[dict[str, Any]]:
    if role_preset != "argue":
        spec_participants = [
            spec_to_participant(spec, turn_index=index)
            for index, spec in enumerate(select_reviewer_angles("parallel review", focus=focus, count=count))
        ]
        if spec_participants:
            return spec_participants

    role_defs = PROTOCOL_ROLE_PRESETS.get(role_preset, PROTOCOL_ROLE_PRESETS["adversarial-review"])
    focus_items = [item.strip() for item in (focus or "").split(",") if item.strip()]
    participants = []
    for index in range(max(1, count)):
        role = role_defs[index % len(role_defs)]
        persona = focus_items[index] if index < len(focus_items) else role["label"]
        participants.append(
            {
                "persona": persona,
                "protocol_role": role["role"],
                "role_label": role["label"],
                "scope": role["scope"],
                "prohibitions": role["prohibitions"],
                "turn_index": index,
            }
        )
    return participants


def build_roundtable_turn_prompt(
    *,
    base_prompt: str,
    participant: dict[str, Any],
    state: dict[str, Any],
    turn_number: int,
    total_turns: int,
    mode: str,
) -> str:
    transcript = summarize_protocol_transcript(state.get("turns", []), max_chars=14000)
    claims = json.dumps(state.get("claims", []), indent=2)
    critiques = json.dumps(state.get("critiques", []), indent=2)
    if mode == "argue":
        return (
            f"{base_prompt}\n\n"
            "Structured argue protocol:\n"
            f"- Mode: {mode}\n"
            f"- Turn: {turn_number}/{total_turns}\n"
            f"- Persona/domain lens: {participant['persona']}\n"
            f"- Assigned side: {participant['role_label']} ({participant['protocol_role']})\n"
            f"- Role scope: {participant['scope']}\n"
            f"- Role prohibitions: {participant['prohibitions']}\n\n"
            "Shared state before this turn:\n"
            f"Claims:\n{claims}\n\n"
            f"Existing critiques:\n{critiques}\n\n"
            f"Transcript so far:\n{transcript or '[none]'}\n\n"
            "Rules:\n"
            "- Argue only your assigned side, but acknowledge real limits.\n"
            "- Make claims that a neutral judge can score against the rubric.\n"
            "- Directly challenge the strongest opposing claim when one exists.\n"
            "- Separate evidence from inference and assumptions.\n"
            "- Stay inside your assigned FOR/AGAINST role.\n\n"
            "Return JSON only with this schema:\n"
            "{\n"
            '  "speaker": "persona name",\n'
            '  "protocol_role": "for|against",\n'
            '  "claims": [{"id": "C#", "text": "...", "confidence": "high|medium|low", "evidence": "..."}],\n'
            '  "critiques": [{"target_claim": "C# or quote", "issue_type": "evidence_gap|failure_mode|bad_assumption|irrelevance|unfalsifiable|cost_risk", "severity": "high|medium|low", "critique": "...", "proposed_fix": "..."}],\n'
            '  "strongest_point": "...",\n'
            '  "weakest_point": "...",\n'
            '  "open_issues": ["..."]\n'
            "}"
        )
    return (
        f"{base_prompt}\n\n"
        "Structured roundtable protocol:\n"
        f"- Mode: {mode}\n"
        f"- Turn: {turn_number}/{total_turns}\n"
        f"- Persona/domain lens: {participant['persona']}\n"
        f"- Protocol role: {participant['role_label']} ({participant['protocol_role']})\n"
        f"- Role scope: {participant['scope']}\n"
        f"- Role prohibitions: {participant['prohibitions']}\n\n"
        "Shared state before this turn:\n"
        f"Claims:\n{claims}\n\n"
        f"Existing critiques:\n{critiques}\n\n"
        f"Transcript so far:\n{transcript or '[none]'}\n\n"
        "Rules:\n"
        "- Do not produce general opinions.\n"
        "- Anchor every critique to a specific prior claim id or quoted claim.\n"
        "- Add at least one non-trivial disagreement, or explicitly justify why none exists.\n"
        "- Do not repeat an existing critique unless adding new evidence or precision.\n"
        "- Stay inside your protocol role.\n\n"
        "Return JSON only with this schema:\n"
        "{\n"
        '  "speaker": "persona name",\n'
        '  "protocol_role": "role key",\n'
        '  "claims": [{"id": "C#", "text": "...", "confidence": "high|medium|low"}],\n'
        '  "critiques": [{"target_claim": "C# or quote", "issue_type": "ambiguity|contradiction|unsupported|overreach|failure_mode|complexity", "severity": "high|medium|low", "critique": "...", "proposed_fix": "..."}],\n'
        '  "agreements": ["..."],\n'
        '  "open_issues": ["..."]\n'
        "}"
    )


def build_parallel_reviewer_prompt(
    *,
    base_prompt: str,
    participant: dict[str, Any],
    mode: str,
) -> str:
    return (
        f"{base_prompt}\n\n"
        "Independent parallel adversarial review protocol:\n"
        f"- Mode: {mode}\n"
        f"- Persona/domain lens: {participant['persona']}\n"
        f"- Protocol role: {participant['role_label']} ({participant['protocol_role']})\n"
        f"- Role scope: {participant['scope']}\n"
        f"- Role prohibitions: {participant['prohibitions']}\n\n"
        "Rules:\n"
        "- Review independently; do not assume other reviewers will catch anything.\n"
        "- Anchor every critique to a specific claim in the prompt or retrieved context.\n"
        "- Produce at least one non-trivial disagreement or explicitly justify why none exists.\n"
        "- Separate high-severity blockers from lower-severity improvements.\n\n"
        "Return JSON only with this schema:\n"
        "{\n"
        '  "speaker": "persona name",\n'
        '  "protocol_role": "role key",\n'
        '  "summary": "...",\n'
        '  "critiques": [{"target_claim": "quote or claim", "issue_type": "ambiguity|contradiction|unsupported|overreach|failure_mode|complexity", "severity": "high|medium|low", "critique": "...", "proposed_fix": "..."}],\n'
        '  "blocking_findings": ["..."],\n'
        '  "confidence": "high|medium|low"\n'
        "}"
    )


def build_moderator_prompt(
    *,
    base_prompt: str,
    state: dict[str, Any],
    mode: str,
    persist: str,
) -> str:
    prompt_state = state if persist == "full" else _compact_state_for_prompt(state)
    if mode == "roundtable:argue":
        rubric = "\n".join(f"- {item}" for item in ARGUE_JUDGE_RUBRIC)
        verdicts = " | ".join(ARGUE_VERDICTS)
        return (
            f"{base_prompt}\n\n"
            "You are the neutral gpt-5.5 xhigh judge for a two-sided argue protocol.\n"
            f"Mode: {mode}\n"
            f"Persistence policy requested: {persist}\n\n"
            "Protocol state:\n"
            f"{json.dumps(prompt_state, indent=2, default=str)[:24000]}\n\n"
            "Judge rubric:\n"
            f"{rubric}\n\n"
            "Synthesis constraints:\n"
            "- Decide who has the stronger argument under the rubric, not who sounds more confident.\n"
            "- Use INSUFFICIENT_EVIDENCE when neither side provides enough grounded support.\n"
            "- Use NO_CLEAR_WINNER when both sides are comparably strong or trade off on different criteria.\n"
            "- Separate what was proven from what remains an assumption.\n"
            "- Do not introduce new evidence not present in the prompt, retrieved context, or argument turns.\n\n"
            "Return Markdown with sections: Verdict, Rubric Scores, Strongest FOR Argument, "
            "Strongest AGAINST Argument, Decisive Gaps, Project Agent Decision, Confidence.\n"
            "Also include one fenced json block with this schema:\n"
            "{\n"
            f'  "verdict": "{verdicts}",\n'
            '  "winner": "for|against|none",\n'
            '  "rubric_scores": {"<each judge rubric key>": {"for": 0, "against": 0, "winner": "for|against|tie"}},\n'
            '  "decisive_reasons": ["..."],\n'
            '  "confidence": "high|medium|low"\n'
            "}"
        )
    return (
        f"{base_prompt}\n\n"
        "You are the neutral gpt-5.5 xhigh moderator for a structured review protocol.\n"
        f"Mode: {mode}\n"
        f"Persistence policy requested: {persist}\n\n"
        "Protocol state:\n"
        f"{json.dumps(prompt_state, indent=2, default=str)[:24000]}\n\n"
        "Synthesis constraints:\n"
        "- Do not introduce new concepts that were not in the prompt, retrieved context, or reviewer turns.\n"
        "- Address all high-severity issues or explicitly mark them unresolved.\n"
        "- Separate consensus, disagreement, action items, and confidence.\n"
        "- Persistible output should be concise; avoid dumping transient chatter.\n\n"
        "Return a final answer in Markdown with sections: Consensus, Disagreements, High-Severity Issues, "
        "Action Items, Durable Lessons, Unresolved Issues, Confidence."
    )


def parse_protocol_turn(content: str) -> dict[str, Any]:
    """Parse structured JSON turn output; keep raw text when parsing fails."""
    text = content.strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            data.setdefault("raw_content", content)
            data.setdefault("parse_ok", True)
            return data
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start:end + 1])
                if isinstance(data, dict):
                    data.setdefault("raw_content", content)
                    data.setdefault("parse_ok", True)
                    return data
            except json.JSONDecodeError:
                pass
    return {
        "parse_ok": False,
        "raw_content": content,
        "claims": [],
        "critiques": [
            {
                "target_claim": "unparsed turn",
                "issue_type": "format",
                "severity": "medium",
                "critique": "Turn did not return valid JSON.",
                "proposed_fix": "Rerun or inspect raw_content.",
            }
        ],
        "open_issues": ["unparsed turn"],
    }


def parse_argue_verdict_payload(content: str) -> dict[str, Any]:
    """Parse the moderator's fenced or raw argue verdict JSON."""
    text = content.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start:end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return {}


def validate_argue_verdict_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate the deterministic JSON gate for an argue moderator verdict."""
    errors: list[str] = []
    verdict = str(payload.get("verdict", "")).strip()
    winner = str(payload.get("winner", "")).strip()
    confidence = str(payload.get("confidence", "")).strip()
    decisive_reasons = payload.get("decisive_reasons")
    rubric_scores = payload.get("rubric_scores")

    if verdict not in ARGUE_VERDICTS:
        errors.append("verdict must be one of ARGUE_VERDICTS")
    if winner not in {"for", "against", "none"}:
        errors.append("winner must be for, against, or none")
    if confidence not in {"high", "medium", "low"}:
        errors.append("confidence must be high, medium, or low")
    if not isinstance(decisive_reasons, list) or not all(isinstance(item, str) for item in decisive_reasons):
        errors.append("decisive_reasons must be a list of strings")
    if verdict in {"FOR", "AGAINST"} and not decisive_reasons:
        errors.append("FOR/AGAINST verdicts require decisive_reasons")

    expected_winner = {
        "FOR": "for",
        "AGAINST": "against",
        "NO_CLEAR_WINNER": "none",
        "INSUFFICIENT_EVIDENCE": "none",
    }.get(verdict)
    if expected_winner and winner != expected_winner:
        errors.append(f"{verdict} verdict requires winner={expected_winner}")

    if not isinstance(rubric_scores, dict):
        errors.append("rubric_scores must be an object")
        rubric_scores = {}

    for rubric_key in ARGUE_JUDGE_RUBRIC:
        score = rubric_scores.get(rubric_key) if isinstance(rubric_scores, dict) else None
        if not isinstance(score, dict):
            errors.append(f"missing rubric_scores.{rubric_key}")
            continue
        for side in ("for", "against"):
            value = score.get(side)
            if not isinstance(value, (int, float)) or value < 0 or value > 5:
                errors.append(f"rubric_scores.{rubric_key}.{side} must be a number from 0 to 5")
        if score.get("winner") not in {"for", "against", "tie"}:
            errors.append(f"rubric_scores.{rubric_key}.winner must be for, against, or tie")

    evidence_score = rubric_scores.get("evidence_strength", {}) if isinstance(rubric_scores, dict) else {}
    if (
        verdict in {"FOR", "AGAINST"}
        and isinstance(evidence_score, dict)
        and evidence_score.get(winner, 0) <= 0
    ):
        errors.append("FOR/AGAINST verdict requires positive evidence_strength for the winning side")

    return {"valid": not errors, "errors": errors}


def summarize_protocol_transcript(turns: list[dict[str, Any]], max_chars: int = 12000) -> str:
    sections = []
    for turn in turns:
        speaker = turn.get("speaker") or turn.get("persona") or "unknown"
        role = turn.get("protocol_role", "")
        content = turn.get("raw_content") or json.dumps(turn, default=str)
        sections.append(f"{speaker} ({role}):\n{content}")
    text = "\n\n".join(sections)
    return text if len(text) <= max_chars else text[-max_chars:]


def _normalize_role_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _compact_state_for_prompt(state: dict[str, Any]) -> dict[str, Any]:
    """Drop raw transcripts from moderator prompt in summary mode."""
    return {
        "claims": state.get("claims", [])[:40],
        "critiques": state.get("critiques", [])[:80],
        "open_issues": state.get("open_issues", [])[:40],
        "parallel_reviews": [
            {
                "persona": turn.get("persona") or turn.get("speaker"),
                "protocol_role": turn.get("protocol_role"),
                "summary": turn.get("summary", ""),
                "blocking_findings": turn.get("blocking_findings", [])[:10],
                "critiques": (turn.get("critiques") or [])[:10],
                "confidence": turn.get("confidence", ""),
            }
            for turn in state.get("parallel_reviews", [])
        ],
        "roundtable_turns": [
            {
                "persona": turn.get("persona") or turn.get("speaker"),
                "protocol_role": turn.get("protocol_role"),
                "claims": (turn.get("claims") or [])[:10],
                "critiques": (turn.get("critiques") or [])[:10],
                "agreements": (turn.get("agreements") or [])[:5],
                "open_issues": (turn.get("open_issues") or [])[:10],
            }
            for turn in state.get("roundtable_turns", [])
        ],
    }
