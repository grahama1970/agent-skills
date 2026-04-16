"""LLM-powered review layer for /review-paper.

Three modes:
1. Interactive (default): The calling agent (Claude/Pi) IS the LLM reviewer.
   We generate structured review prompts that the agent processes in-context.
2. Gateway (cascade): Uses /assistant gateway for 4-tier cascade
   (heuristic → classifier → GPT → scillm). Best for single papers.
3. Batch (scillm): For corpus-level work across many papers, use scillm/Chutes
   for cheap parallel completions.

The project agent handles single-paper review because it has full context
(persona manifests, prior reviews from /memory, code files for doc-code
alignment).  Gateway mode is the preferred automated path; batch is for
throughput across large corpora.
"""
from __future__ import annotations
import os

import json
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from .models import (
    AnalysisResult,
    DiagnosticsSummary,
    HumanizationReport,
    PaperModel,
    ReviewDimension,
    RevisionItem,
    SectionReview,
)

# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------
SKILLS_DIR = Path(__file__).resolve().parents[2]
_PROMPT_DIR = SKILLS_DIR / "prompt-lab" / "prompts"


def _load_prompt(name: str) -> str:
    path = _PROMPT_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt '{name}' not found at {path}")
    return path.read_text().strip()


# ---------------------------------------------------------------------------
# /assistant gateway via subprocess (skills talk to skills via subprocess)
# ---------------------------------------------------------------------------
_ASSISTANT_RUN_SH = SKILLS_DIR / "assistant" / "run.sh"
_GATEWAY_AVAILABLE = _ASSISTANT_RUN_SH.exists()

if not _GATEWAY_AVAILABLE:
    logger.debug("assistant run.sh not found — gateway cascade unavailable")


def gateway_validate(input_data: dict, task: str, scope: str = "") -> dict:
    """Call /assistant validate via subprocess. Returns parsed JSON result."""
    import subprocess
    input_json = json.dumps(input_data, ensure_ascii=False)
    cmd = [str(_ASSISTANT_RUN_SH), "validate", "--task", task, "--input", input_json]
    if scope:
        cmd.extend(["--scope", scope])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )
    if result.returncode != 0:
        raise RuntimeError(f"assistant validate failed (rc={result.returncode}): {result.stderr[:300]}")
    return json.loads(result.stdout.strip())

# ---------------------------------------------------------------------------
# scillm import (fallback for batch mode)
# ---------------------------------------------------------------------------
SCILLM_DIR = SKILLS_DIR / "scillm"
if str(SCILLM_DIR) not in sys.path:
    sys.path.append(str(SCILLM_DIR))

_SCILLM_AVAILABLE = False
try:
    from batch import quick_completion  # type: ignore[import-untyped]
    _SCILLM_AVAILABLE = True
except ImportError:
    logger.debug("scillm not available — batch LLM mode disabled")

    def quick_completion(prompt: str, **kwargs: Any) -> str:  # type: ignore[misc]
        raise RuntimeError("scillm not available")


# ---------------------------------------------------------------------------
# Prompt templates (shared between interactive and batch modes)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = _load_prompt("review_paper_system_v1")

SECTION_REVIEW_PROMPT = _load_prompt("review_paper_section_review_v1")

CROSS_SECTION_PROMPT = _load_prompt("review_paper_cross_section_v1")


# ---------------------------------------------------------------------------
# Prompt generation for interactive mode (agent IS the reviewer)
# ---------------------------------------------------------------------------

def generate_section_review_prompt(
    paper: PaperModel,
    section_idx: int,
    diagnostics: DiagnosticsSummary,
    humanization: HumanizationReport,
    persona_name: str | None,
) -> str:
    """Build the review prompt for a section — returned to the calling agent."""
    section = paper.sections[section_idx]
    section_text = "\n\n".join(p.text for p in section.paragraphs)
    sentence_count = sum(len(p.sentences) for p in section.paragraphs)
    word_count = sum(p.word_count for p in section.paragraphs)

    return SECTION_REVIEW_PROMPT.format(
        title=paper.title,
        section_title=section.title,
        word_count=word_count,
        sentence_count=sentence_count,
        persona=persona_name or "unassigned",
        sent_mean=diagnostics.sentence_mean,
        sent_stddev=diagnostics.sentence_stddev,
        lex_div=diagnostics.lexical_diversity,
        hedge=diagnostics.hedge_density,
        certainty=diagnostics.certainty_density,
        human_score=humanization.humanization_score,
        ai_signals="; ".join(humanization.ai_signals[:5]) or "none",
        section_text=section_text[:4000],
    )


def generate_cross_section_prompt(
    paper: PaperModel,
    section_reviews: list[SectionReview],
    cross_score: float,
    cross_issues: list[str],
) -> str:
    """Build the cross-section review prompt — returned to the calling agent."""
    summaries = []
    for sr in section_reviews:
        top_issues = sr.issues[:3] if sr.issues else ["none"]
        summaries.append(
            f"- {sr.section_title} (score={sr.weighted_score:.1f}): "
            f"issues={'; '.join(top_issues)}"
        )

    return CROSS_SECTION_PROMPT.format(
        title=paper.title,
        section_summaries="\n".join(summaries),
        cross_score=cross_score,
        cross_issues="; ".join(cross_issues) or "none",
    )


def generate_review_prompts(result: AnalysisResult) -> dict[str, str]:
    """Generate all review prompts for the calling agent.

    Returns a dict mapping prompt names to prompt text:
    - "system": system prompt
    - "section:<title>": per-section review prompt
    - "cross_section": cross-section consistency prompt

    The calling agent (Claude/Pi) processes these and returns JSON responses.
    """
    paper = result.paper
    persona_map: dict[str, str] = {}
    for pa in result.persona_alignment:
        if pa.intended_persona:
            persona_map[pa.section_id] = pa.intended_persona

    prompts: dict[str, str] = {"system": SYSTEM_PROMPT}

    for i, section in enumerate(paper.sections):
        persona_name = persona_map.get(section.id)
        key = f"section:{section.title}"
        prompts[key] = generate_section_review_prompt(
            paper, i, result.diagnostics, result.humanization, persona_name,
        )

    return prompts


# ---------------------------------------------------------------------------
# Response parsing (shared between interactive and batch modes)
# ---------------------------------------------------------------------------

def parse_section_review(
    section_id: str,
    section_title: str,
    persona_name: str | None,
    raw_json: str,
) -> SectionReview:
    """Parse an LLM JSON response into a SectionReview."""
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse LLM response for {}: {}", section_title, exc)
        return SectionReview(
            section_id=section_id,
            section_title=section_title,
            persona=persona_name,
            issues=[f"LLM response parse error: {exc}"],
        )

    dimensions: list[ReviewDimension] = []
    weights = {
        "accuracy": 0.30, "voice": 0.25, "completeness": 0.25,
        "clarity": 0.15, "humanness": 0.05,
    }
    all_issues: list[str] = []
    all_strengths: list[str] = []

    for dim_name, weight in weights.items():
        dim_data = data.get(dim_name, {})
        score = float(dim_data.get("score", 5))
        issues = dim_data.get("issues", [])
        strengths = dim_data.get("strengths", [])
        dimensions.append(ReviewDimension(
            name=dim_name, score=score, weight=weight,
            issues=issues, strengths=strengths,
        ))
        all_issues.extend(f"[{dim_name}] {i}" for i in issues)
        all_strengths.extend(f"[{dim_name}] {s}" for s in strengths)

    for flag in data.get("contradiction_flags", []):
        all_issues.append(f"[contradiction] {flag}")
    for flag in data.get("buzzword_flags", []):
        all_issues.append(f"[buzzword] {flag}")

    weighted_score = sum(d.score * d.weight for d in dimensions)

    return SectionReview(
        section_id=section_id,
        section_title=section_title,
        persona=persona_name,
        dimensions=dimensions,
        weighted_score=round(weighted_score, 2),
        issues=all_issues,
        strengths=all_strengths,
    )


def parse_cross_section_review(
    raw_json: str,
) -> tuple[float, list[str], list[RevisionItem]]:
    """Parse an LLM cross-section review response."""
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse cross-section response: {}", exc)
        return 0.0, [f"LLM cross-review parse error: {exc}"], []

    overall = float(data.get("overall_score", 5))
    extra_issues: list[str] = []
    extra_items: list[RevisionItem] = []

    for c in data.get("contradictions", []):
        extra_issues.append(f"[contradiction] {c}")
        extra_items.append(RevisionItem(
            priority=1, target="paper", category="contradiction",
            issue=c, action="resolve the contradicting claims",
        ))
    for v in data.get("voice_drift", []):
        extra_issues.append(f"[voice-drift] {v}")
    for m in data.get("missing_connections", []):
        extra_issues.append(f"[missing-connection] {m}")
        extra_items.append(RevisionItem(
            priority=2, target="paper", category="coherence",
            issue=m, action="add supporting evidence or cross-reference",
        ))

    aca = data.get("abstract_conclusion_alignment", {})
    if not aca.get("aligned", True):
        for issue in aca.get("issues", []):
            extra_issues.append(f"[abstract-conclusion] {issue}")
            extra_items.append(RevisionItem(
                priority=1, target="paper", category="alignment",
                issue=issue,
                action="align abstract claims with conclusion findings",
            ))

    return overall, extra_issues, extra_items


def merge_llm_reviews(
    result: AnalysisResult,
    section_reviews: list[SectionReview],
    overall_score: float,
    cross_issues: list[str],
    cross_items: list[RevisionItem],
) -> AnalysisResult:
    """Merge LLM review results into the AnalysisResult."""
    result.section_reviews = section_reviews

    if overall_score > 0:
        result.overall_score = overall_score
    else:
        scores = [
            sr.weighted_score for sr in section_reviews if sr.weighted_score > 0
        ]
        result.overall_score = round(sum(scores) / max(1, len(scores)), 2)

    result.cross_persona_issues.extend(cross_issues)
    result.revision_plan.extend(cross_items)
    result.revision_plan.sort(key=lambda x: (x.priority, x.category, x.target))
    return result


# ---------------------------------------------------------------------------
# Batch mode (scillm — cheap parallel calls for corpus work)
# ---------------------------------------------------------------------------

def gateway_available() -> bool:
    """Check if the /assistant gateway cascade is available."""
    return _GATEWAY_AVAILABLE


def scillm_available() -> bool:
    """Check if scillm batch mode can run."""
    return _SCILLM_AVAILABLE


def run_gateway_llm_review(result: AnalysisResult) -> AnalysisResult:
    """Run LLM review via /assistant gateway (4-tier cascade).

    Preferred path for single-paper review. Uses paper-section-reviewer task
    registered in /assistant model_registry.json, which routes through:
    Tier 0 (heuristic) → Tier 0.5 (ai-text-detector) → Tier 1.5 (GPT) → Tier 2 (scillm).
    """
    if not _GATEWAY_AVAILABLE:
        logger.warning("assistant gateway not available — falling back to batch mode")
        return run_batch_llm_review(result)

    paper = result.paper
    persona_map: dict[str, str] = {}
    for pa in result.persona_alignment:
        if pa.intended_persona:
            persona_map[pa.section_id] = pa.intended_persona

    logger.info("Running gateway LLM review on {} sections", len(paper.sections))
    section_reviews: list[SectionReview] = []

    for i, section in enumerate(paper.sections):
        persona_name = persona_map.get(section.id)
        section_text = "\n\n".join(p.text for p in section.paragraphs)[:4000]
        word_count = sum(p.word_count for p in section.paragraphs)
        sentence_count = sum(len(p.sentences) for p in section.paragraphs)

        input_data = {
            "title": paper.title,
            "section_title": section.title,
            "section_text": section_text,
            "word_count": word_count,
            "sentence_count": sentence_count,
            "persona": persona_name or "unassigned",
            "humanization_score": result.humanization.humanization_score,
            "ai_signals": result.humanization.ai_signals[:5],
            "sentence_mean": result.diagnostics.sentence_mean,
            "sentence_stddev": result.diagnostics.sentence_stddev,
            "lexical_diversity": result.diagnostics.lexical_diversity,
        }

        try:
            gw_result = gateway_validate(
                input_data,
                task="paper-section-reviewer",
                scope=persona_name or "",
            )
            # gateway returns full TierResult as JSON dict
            raw = gw_result.get("result", gw_result)
            raw_json = json.dumps(raw) if isinstance(raw, dict) else str(raw)
            tier_name = gw_result.get("tier", "?")
        except Exception as exc:
            logger.warning("Gateway review failed for {}: {}", section.title, exc)
            raw_json = json.dumps({})
            tier_name = "error"

        sr = parse_section_review(section.id, section.title, persona_name, raw_json)
        section_reviews.append(sr)
        logger.info(
            "  {} — score={:.1f}, {} issues (tier={})",
            section.title, sr.weighted_score, len(sr.issues), tier_name,
        )

    # Cross-section review via scillm (gateway doesn't have a cross-section task)
    cross_prompt = generate_cross_section_prompt(
        paper, section_reviews,
        result.cross_persona_consistency,
        result.cross_persona_issues,
    )
    overall, extra_issues, extra_items = 0.0, [], []
    if _SCILLM_AVAILABLE:
        try:
            cross_raw = quick_completion(
                cross_prompt,
                system=SYSTEM_PROMPT,
                json_mode=True,
                max_tokens=1200,
                temperature=0.3,
                timeout=45,
            )
            overall, extra_issues, extra_items = parse_cross_section_review(cross_raw)
        except Exception as exc:
            logger.warning("Cross-section review failed: {}", exc)

    return merge_llm_reviews(result, section_reviews, overall, extra_issues, extra_items)


def rewrite_flagged_sentences(result: AnalysisResult) -> str:
    """Rewrite AI-flagged sentences using the humanization-rewriter task.

    Walks through sections, identifies sentences flagged by diagnostics,
    and rewrites them through the /assistant gateway cascade.

    Returns the rewritten full text (fact-safe — only flagged sentences change).
    """
    if not _GATEWAY_AVAILABLE:
        logger.warning("Gateway not available — returning raw text unchanged")
        return result.paper.raw_text

    paper = result.paper
    rewritten_sections: list[str] = []

    for section in paper.sections:
        section_parts: list[str] = []
        for para in section.paragraphs:
            rewritten_sentences: list[str] = []
            for sent in para.sentences:
                # Only rewrite if the paper has AI signals
                if result.humanization.humanization_score >= 0.8:
                    rewritten_sentences.append(sent.text)
                    continue

                input_data = {
                    "sentence": sent.text,
                    "section_title": section.title,
                    "ai_signals": result.humanization.ai_signals[:3],
                    "persona": "unassigned",
                }
                try:
                    gw_result = gateway_validate(
                        input_data,
                        task="humanization-rewriter",
                    )
                    raw = gw_result.get("result", gw_result)
                    if isinstance(raw, dict) and raw.get("facts_preserved", False):
                        rewritten_sentences.append(raw.get("rewritten", sent.text))
                    else:
                        rewritten_sentences.append(sent.text)
                except Exception:
                    rewritten_sentences.append(sent.text)

            section_parts.append(" ".join(rewritten_sentences))
        rewritten_sections.append("\n\n".join(section_parts))

    return "\n\n".join(rewritten_sections)


def run_batch_llm_review(result: AnalysisResult) -> AnalysisResult:
    """Run LLM review via scillm (batch mode for corpus-level work).

    For single-paper interactive review, use generate_review_prompts() instead
    and let the calling agent (Claude/Pi) process the prompts directly.
    """
    if not _SCILLM_AVAILABLE:
        logger.warning("scillm not available — skipping batch LLM review")
        return result

    paper = result.paper
    persona_map: dict[str, str] = {}
    for pa in result.persona_alignment:
        if pa.intended_persona:
            persona_map[pa.section_id] = pa.intended_persona

    logger.info("Running batch LLM review on {} sections via scillm", len(paper.sections))
    section_reviews: list[SectionReview] = []

    for i, section in enumerate(paper.sections):
        persona_name = persona_map.get(section.id)
        prompt = generate_section_review_prompt(
            paper, i, result.diagnostics, result.humanization, persona_name,
        )
        try:
            raw = quick_completion(
                prompt,
                system=SYSTEM_PROMPT,
                json_mode=True,
                max_tokens=1500,
                temperature=0.3,
                timeout=45,
            )
        except Exception as exc:
            logger.warning("scillm review failed for {}: {}", section.title, exc)
            raw = json.dumps({})

        sr = parse_section_review(section.id, section.title, persona_name, raw)
        section_reviews.append(sr)
        logger.info(
            "  {} — score={:.1f}, {} issues",
            section.title, sr.weighted_score, len(sr.issues),
        )

    # Cross-section review
    cross_prompt = generate_cross_section_prompt(
        paper, section_reviews,
        result.cross_persona_consistency,
        result.cross_persona_issues,
    )
    try:
        cross_raw = quick_completion(
            cross_prompt,
            system=SYSTEM_PROMPT,
            json_mode=True,
            max_tokens=1200,
            temperature=0.3,
            timeout=45,
        )
    except Exception as exc:
        logger.warning("scillm cross-section review failed: {}", exc)
        cross_raw = json.dumps({})

    overall, extra_issues, extra_items = parse_cross_section_review(cross_raw)
    return merge_llm_reviews(result, section_reviews, overall, extra_issues, extra_items)
