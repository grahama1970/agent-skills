"""Core peer review engine with venue-calibrated rubric scoring.

Rubric design is grounded in actual review forms from NeurIPS, ICML, ICLR,
and ACL/ARR (sourced via /dogpile research, Feb 2026). Key design decisions:

1. DECOUPLED overall score: the overall recommendation is a holistic judgment
   informed by but NOT mechanically computed from dimension scores. Real
   venue reviewers make holistic calls (e.g., moderate novelty + immense
   significance = accept). The weighted_signal() is an ADVISORY input to
   the reviewer GPT, not the final score.

2. VENUE-CALIBRATED scales: dimension scores use a 1-4 scale (NeurIPS/ICLR
   convention), overall recommendation uses 1-10 (ICLR convention). This
   matches what real reviewers are trained on.

3. EMPIRICAL NOVELTY split from TECHNICAL NOVELTY (ICLR innovation): a paper
   can have modest technical novelty but groundbreaking empirical results.

4. CONFIDENCE as metadata, not a rubric dimension: 1-5 self-assessment of
   reviewer expertise, used by the meta-review to weight reviewer opinions.

5. SHADOW-OBSERVED WEIGHT LEARNING: rubric weights start from venue norms
   but are tracked in the shadow journal. When the teacher overrides a
   local GPT's overall score, the weight configuration that would have
   produced the teacher's score is logged. Over time, /assistant's
   auto_improve() learns which weights best predict teacher decisions.

Key classes:
    RubricScore: 6-dimension score on 1-4 scale (venue-calibrated)
    SectionReview: Per-section review from a single reviewer
    ReviewResult: Full paper review with decoupled overall score (1-10)
    MetaReview: AC-style aggregation with confidence weighting
    ReviewEngine: Orchestrator running cascade per reviewer per section
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from loguru import logger


# ---------------------------------------------------------------------------
# Decision thresholds (ICLR 1-10 convention)
# ---------------------------------------------------------------------------
# 10: Award quality  |  8: Top 15% accepted  |  6: Marginally above threshold
# 5: Marginally below  |  3: Clear reject  |  1: Trivial or wrong
STRONG_ACCEPT_THRESHOLD = 8.0   # Top 15% of accepted papers
ACCEPT_THRESHOLD = 6.0          # Marginally above acceptance threshold
BORDERLINE_HIGH = 6.0
BORDERLINE_LOW = 5.0
REJECT_THRESHOLD = 5.0

# Default rubric weights (venue-norm starting point, shadow-tuned over time)
# These are the INITIAL weights before shadow observation adjusts them.
DEFAULT_WEIGHTS = {
    "soundness": 0.25,
    "technical_novelty": 0.15,
    "empirical_novelty": 0.15,
    "significance": 0.20,
    "clarity": 0.15,
    "presentation": 0.10,
}


@dataclass
class RubricScore:
    """Six-dimension review score on a 1-4 scale (NeurIPS/ICLR convention).

    Scale semantics per dimension:
        4: Excellent / major contribution / rigorous
        3: Good / solid / minor issues
        2: Weak / some issues / could be addressed
        1: Poor / major flaws / fundamentally broken

    The overall recommendation (1-10) is DECOUPLED from these scores.
    weighted_signal() provides an advisory aggregate, but the reviewer
    GPT or teacher makes the final holistic judgment.
    """

    soundness: float = 2.0         # Are claims correct? Methods valid?
    technical_novelty: float = 2.0  # Are the IDEAS new? (ICLR split)
    empirical_novelty: float = 2.0  # Are the EXPERIMENTS/RESULTS new? (ICLR split)
    significance: float = 2.0      # Does this matter? Who benefits?
    clarity: float = 2.0           # Can it be understood and reproduced?
    presentation: float = 2.0      # Figures, tables, code, formatting

    def weighted_signal(
        self,
        weights: Optional[dict[str, float]] = None,
    ) -> float:
        """Advisory weighted signal on a 1-10 scale.

        Maps 1-4 dimension scores to a 1-10 signal using:
            signal = sum(dim * weight) * (10/4)

        This is NOT the overall score. It is an input to the reviewer's
        holistic judgment. The reviewer GPT may deviate from this signal
        based on qualitative assessment (e.g., fatal flaw in one dimension
        overrides high scores in others).
        """
        w = weights or DEFAULT_WEIGHTS
        raw = sum(
            getattr(self, dim) * w.get(dim, 0.0)
            for dim in [
                "soundness", "technical_novelty", "empirical_novelty",
                "significance", "clarity", "presentation",
            ]
        )
        # Scale from 1-4 range to 1-10 range
        return round(raw * (10.0 / 4.0), 2)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "RubricScore":
        # Accept both old 5-dim format and new 6-dim format
        field_map = {
            "novelty": "technical_novelty",  # backward compat
        }
        mapped = {}
        for k, v in d.items():
            key = field_map.get(k, k)
            if key in cls.__dataclass_fields__:
                mapped[key] = float(v)
        return cls(**mapped)


@dataclass
class SectionReview:
    """Review of a single section by a single reviewer."""

    section_key: str                  # e.g. "abstract", "intro", "eval"
    reviewer_id: str                  # e.g. "reviewer_alpha"
    scores: RubricScore = field(default_factory=RubricScore)
    overall_score: float = 0.0       # DECOUPLED 1-10 holistic judgment
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    code_issues: list[str] = field(default_factory=list)
    confidence: float = 3.0          # 1-5 reviewer self-assessed expertise
    tier_used: float = 2.0           # Which cascade tier produced this review
    latency_ms: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["scores"] = self.scores.to_dict()
        return d


@dataclass
class ReviewResult:
    """Full paper review from a single reviewer persona.

    The overall_score is DECOUPLED: it is the reviewer's holistic
    recommendation on the 1-10 ICLR scale, informed by but not
    mechanically derived from dimension scores. The weighted_signal
    is logged alongside for shadow observation.
    """

    reviewer_id: str
    reviewer_name: str
    paper_dir: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    overall_score: float = 0.0       # Decoupled 1-10 holistic judgment
    weighted_signal: float = 0.0     # Advisory aggregate (for shadow comparison)
    decision: str = ""               # strong_accept, accept, borderline, reject
    confidence: float = 3.0          # 1-5 reviewer expertise self-assessment
    section_reviews: list[SectionReview] = field(default_factory=list)
    summary: str = ""
    major_issues: list[str] = field(default_factory=list)
    minor_issues: list[str] = field(default_factory=list)
    missing_references: list[str] = field(default_factory=list)
    code_quality: str = ""
    tier_distribution: dict[str, int] = field(default_factory=dict)

    def compute_overall(self, weights: Optional[dict[str, float]] = None) -> float:
        """Compute the advisory weighted signal and derive overall score.

        For Tier 0/0.5 (heuristic/classifier), the overall score IS the
        signal since these tiers cannot make holistic judgments.
        For Tier 1.5/2 (GPT/teacher), the overall score comes from the
        model's holistic output, and the signal is logged for comparison.
        """
        if not self.section_reviews:
            return 0.0

        # Compute advisory signal: use MINIMUM section signal, not average.
        # A fatal flaw in one section should not be diluted by passing sections.
        signals = [sr.scores.weighted_signal(weights) for sr in self.section_reviews]
        self.weighted_signal = round(min(signals), 2)

        # If sections have decoupled overall scores (from GPT/teacher), use
        # the minimum — a paper is only as strong as its weakest section.
        holistic_scores = [sr.overall_score for sr in self.section_reviews if sr.overall_score > 0]
        if holistic_scores:
            self.overall_score = round(min(holistic_scores), 2)
        else:
            # Fallback: use advisory signal (heuristic/classifier tiers)
            self.overall_score = self.weighted_signal

        # Confidence: minimum across sections (weakest link)
        confidences = [sr.confidence for sr in self.section_reviews if sr.confidence > 0]
        if confidences:
            self.confidence = min(confidences)

        self.decision = _score_to_decision(self.overall_score)
        return self.overall_score

    def to_dict(self) -> dict:
        d = asdict(self)
        d["section_reviews"] = [sr.to_dict() for sr in self.section_reviews]
        return d

    def save(self, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{self.reviewer_id}_review.json"
        path.write_text(json.dumps(self.to_dict(), indent=2))
        logger.info(f"Saved review to {path}")
        return path


@dataclass
class MetaReview:
    """AC-style aggregated review across all reviewer personas.

    Aggregation follows real venue conventions:
    - Confidence-weighted scoring: high-confidence reviews count more
    - Decisive arguments: a single fatal-flaw review (high confidence)
      can sink a paper even if other reviewers are positive
    - Disagreement flagging: >2 point spread on any dimension triggers
      discussion (in production, this would invoke /argue)
    """

    paper_dir: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    reviewer_scores: dict[str, float] = field(default_factory=dict)
    reviewer_confidences: dict[str, float] = field(default_factory=dict)
    overall_score: float = 0.0       # Confidence-weighted aggregate
    weighted_signal: float = 0.0     # Advisory signal (for shadow comparison)
    decision: str = ""
    consensus_strengths: list[str] = field(default_factory=list)
    consensus_weaknesses: list[str] = field(default_factory=list)
    disagreements: list[str] = field(default_factory=list)
    revision_priority: list[str] = field(default_factory=list)
    shadow_stats: dict = field(default_factory=dict)
    # Shadow weight tracking: what weights would have predicted teacher scores
    shadow_weight_log: dict = field(default_factory=dict)

    @classmethod
    def from_reviews(cls, reviews: list[ReviewResult], paper_dir: str) -> "MetaReview":
        """AC-style aggregation with confidence weighting."""
        meta = cls(paper_dir=paper_dir)

        for r in reviews:
            meta.reviewer_scores[r.reviewer_id] = r.overall_score
            meta.reviewer_confidences[r.reviewer_id] = r.confidence

        # Confidence-weighted overall score
        if meta.reviewer_scores:
            total_weight = 0.0
            weighted_sum = 0.0
            for rid, score in meta.reviewer_scores.items():
                conf = meta.reviewer_confidences.get(rid, 3.0)
                weighted_sum += score * conf
                total_weight += conf
            if total_weight > 0:
                meta.overall_score = round(weighted_sum / total_weight, 2)

            # Also track unweighted signal
            signals = [r.weighted_signal for r in reviews if r.weighted_signal > 0]
            if signals:
                meta.weighted_signal = round(sum(signals) / len(signals), 2)

            meta.decision = _score_to_decision(meta.overall_score)

            # Decisive argument check: if ANY high-confidence reviewer
            # (conf >= 4) gives a score < 4 (clear reject), flag it
            for r in reviews:
                if r.confidence >= 4.0 and r.overall_score < 4.0:
                    meta.disagreements.append(
                        f"DECISIVE: {r.reviewer_id} (conf={r.confidence}) "
                        f"scores {r.overall_score:.1f} — fatal flaw identified"
                    )

        # Consensus strengths/weaknesses (mentioned by ≥2 reviewers)
        all_strengths: dict[str, int] = {}
        all_weaknesses: dict[str, int] = {}
        for r in reviews:
            for sr in r.section_reviews:
                for s in sr.strengths:
                    all_strengths[s] = all_strengths.get(s, 0) + 1
                for w in sr.weaknesses:
                    all_weaknesses[w] = all_weaknesses.get(w, 0) + 1

        meta.consensus_strengths = [s for s, c in all_strengths.items() if c >= 2]
        meta.consensus_weaknesses = [w for w, c in all_weaknesses.items() if c >= 2]

        # Dimension-level disagreements per section (>1 point spread on 1-4 scale)
        # Compare across reviewers for the SAME section, not flattened.
        if len(reviews) >= 2:
            # Collect section keys present across all reviewers
            all_sections: set[str] = set()
            for r in reviews:
                for sr in r.section_reviews:
                    all_sections.add(sr.section_key)

            for section_key in sorted(all_sections):
                for dim in [
                    "soundness", "technical_novelty", "empirical_novelty",
                    "significance", "clarity", "presentation",
                ]:
                    scores = []
                    for r in reviews:
                        for sr in r.section_reviews:
                            if sr.section_key == section_key:
                                scores.append(getattr(sr.scores, dim, 2.0))
                    if len(scores) >= 2 and (max(scores) - min(scores)) > 1.0:
                        meta.disagreements.append(
                            f"{section_key}/{dim}: spread "
                            f"{min(scores):.0f}-{max(scores):.0f} (1-4 scale)"
                        )

        # Revision priorities: weaknesses sorted by frequency
        meta.revision_priority = sorted(
            all_weaknesses.keys(), key=lambda w: all_weaknesses[w], reverse=True
        )[:10]

        return meta

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "meta_review.json"
        path.write_text(json.dumps(self.to_dict(), indent=2))
        logger.info(f"Saved meta-review to {path}")
        return path


class ReviewEngine:
    """Orchestrates multi-persona peer review through the Shadow-LEGO cascade.

    The engine runs each reviewer persona against each section, producing
    independent SectionReviews that are aggregated into ReviewResults and
    finally a MetaReview. Shadow mode tracks two levels of agreement:

    1. SCORE AGREEMENT: Does the local GPT's overall score match the teacher's?
    2. WEIGHT AGREEMENT: Do the advisory weights that best predict the teacher's
       holistic score match the current weight configuration?

    The second level is the "rubric weight learning" loop: as the teacher
    produces holistic scores, /assistant tracks which weight configuration
    would have produced the closest match, gradually tuning the advisory
    weights toward the teacher's implicit preferences.
    """

    SECTION_KEYS = ["abstract", "intro", "related", "design", "impl", "eval", "discussion"]

    def __init__(
        self,
        paper_dir: str | Path,
        reviewer_ids: Optional[list[str]] = None,
        shadow_mode: bool = True,
    ):
        self.paper_dir = Path(paper_dir)
        self.shadow_mode = shadow_mode
        self.reviews_dir = self.paper_dir / "reviews"

        from .reviewer_personas import load_reviewers
        all_reviewers = load_reviewers()
        if reviewer_ids:
            self.reviewers = {k: v for k, v in all_reviewers.items() if k in reviewer_ids}
        else:
            self.reviewers = all_reviewers

        from .cascade_integration import build_review_cascade
        self.cascade = build_review_cascade(shadow_mode=shadow_mode)

        logger.info(
            f"ReviewEngine initialized: {len(self.reviewers)} reviewers, "
            f"shadow_mode={shadow_mode}, paper_dir={self.paper_dir}"
        )

    def _load_section(self, section_key: str) -> str:
        tex_path = self.paper_dir / "sections" / f"{section_key}.tex"
        if tex_path.exists():
            return tex_path.read_text()
        logger.warning(f"Section file not found: {tex_path}")
        return ""

    def _load_references(self) -> str:
        bib_path = self.paper_dir / "references.bib"
        if bib_path.exists():
            return bib_path.read_text()
        return ""

    def review_section(
        self,
        section_key: str,
        reviewer_id: str,
    ) -> SectionReview:
        """Review a single section with a single reviewer via cascade."""
        content = self._load_section(section_key)
        references = self._load_references()
        reviewer = self.reviewers[reviewer_id]

        input_data = {
            "section_key": section_key,
            "content": content,
            "references": references,
            "reviewer_id": reviewer_id,
            "reviewer_persona": reviewer.to_dict(),
            "paper_dir": str(self.paper_dir),
        }

        t0 = time.monotonic()
        tier_result = self.cascade.run(
            input_data=input_data,
            task="peer_review_section",
            scope="peer_review",
        )
        elapsed = (time.monotonic() - t0) * 1000

        review = _parse_tier_result_to_section_review(
            tier_result=tier_result,
            section_key=section_key,
            reviewer_id=reviewer_id,
            latency_ms=elapsed,
        )
        return review

    def review_paper(self, reviewer_id: str) -> ReviewResult:
        """Full paper review from a single reviewer persona."""
        reviewer = self.reviewers[reviewer_id]
        result = ReviewResult(
            reviewer_id=reviewer_id,
            reviewer_name=reviewer.name,
            paper_dir=str(self.paper_dir),
        )

        tier_counts: dict[str, int] = {}
        for section_key in self.SECTION_KEYS:
            content = self._load_section(section_key)
            if not content.strip():
                continue
            sr = self.review_section(section_key, reviewer_id)
            result.section_reviews.append(sr)
            tier_key = f"tier_{sr.tier_used}"
            tier_counts[tier_key] = tier_counts.get(tier_key, 0) + 1

        result.tier_distribution = tier_counts
        result.compute_overall(reviewer.rubric_weights)
        return result

    def run_full_review(self, parallel: bool = False) -> MetaReview:
        """Run all reviewers against all sections, produce meta-review.

        Args:
            parallel: If True, dispatch all reviewers concurrently via
                      scillm API. Each persona runs as an independent
                      request. Falls back to sequential on failure.

        Automatically includes arxiv benchmark eval as context for the
        meta-review, so the Tier 2 reviewer (project agent) has empirical
        reference points when making scoring decisions.
        """
        if parallel:
            try:
                reviews = self._run_parallel_via_subagent()
            except Exception as e:
                logger.warning(f"Parallel review failed ({e}), falling back to sequential")
                reviews = self._run_sequential()
        else:
            reviews = self._run_sequential()

        meta = MetaReview.from_reviews(reviews, str(self.paper_dir))

        # Attach benchmark eval as scoring context for Tier 2
        benchmark_report = self._run_benchmark_eval()
        if benchmark_report:
            meta.shadow_stats["benchmark_eval"] = benchmark_report
            logger.info(
                f"Benchmark eval: structural_score={benchmark_report.get('overall_structural_score', 0):.1f}, "
                f"flags={len(benchmark_report.get('flags', []))}"
            )

        meta.save(self.reviews_dir)

        logger.info(
            f"Meta-review complete: score={meta.overall_score:.2f}, "
            f"decision={meta.decision}, signal={meta.weighted_signal:.2f}"
        )
        return meta

    def _run_sequential(self) -> list[ReviewResult]:
        """Run all reviewers sequentially (original behavior)."""
        reviews: list[ReviewResult] = []
        for reviewer_id in self.reviewers:
            logger.info(f"Running review: {reviewer_id}")
            result = self.review_paper(reviewer_id)
            result.save(self.reviews_dir)
            reviews.append(result)
        return reviews

    def _run_parallel_via_subagent(self) -> list[ReviewResult]:
        """Dispatch all reviewer personas concurrently via scillm."""
        from .subagent_dispatch import run_parallel_review
        return run_parallel_review(
            reviewers=self.reviewers,
            section_keys=self.SECTION_KEYS,
            load_section_fn=self._load_section,
            load_references_fn=self._load_references,
            reviews_dir=self.reviews_dir,
            paper_dir=self.paper_dir,
        )

    def _run_benchmark_eval(self) -> Optional[dict]:
        """Run arxiv benchmark eval and return report dict.

        This automatically scores the paper's structural metrics against
        the embedded arxiv corpus, providing empirical context for the
        project agent (Tier 2) when making scoring decisions.
        """
        try:
            from .benchmarks import ArxivBenchmarks

            benchmarks = ArxivBenchmarks.load()
            if not benchmarks.corpus:
                return None

            # Read full paper tex
            draft_path = self.paper_dir / "draft.tex"
            if not draft_path.exists():
                # Try sections directory
                tex_files = list((self.paper_dir / "sections").glob("*.tex")) if (self.paper_dir / "sections").exists() else []
                if not tex_files:
                    return None
                content = "\n".join(f.read_text() for f in tex_files)
            else:
                content = draft_path.read_text()

            words = len(re.sub(r"\\[a-zA-Z]+\*?\{[^}]*\}", " ", content).split())
            est_pages = max(1, words // 350)
            equations = len(re.findall(r"\\begin\{(?:equation|align)\*?\}", content))
            figures = len(re.findall(r"\\begin\{figure", content))
            tables = len(re.findall(r"\\begin\{table", content))
            footnotes = len(re.findall(r"\\footnote\{", content))

            refs = 0
            bib_path = self.paper_dir / "references.bib"
            if bib_path.exists():
                refs = len(re.findall(r"@\w+\{", bib_path.read_text()))
            # Also count inline \bibitem entries and \cite commands
            refs += len(re.findall(r"\\bibitem", content))
            refs = max(refs, len(re.findall(r"\\cite[tp]?\*?\{", content)))

            paper_metrics = {
                "words": words, "est_pages": est_pages,
                "equations": equations, "figures": figures,
                "tables": tables, "refs": refs, "footnotes": footnotes,
                "eq_per_pg": equations / est_pages,
                "fig_per_pg": figures / est_pages,
                "ref_per_pg": refs / est_pages,
            }

            report = benchmarks.score_paper(paper_metrics, paper_id=self.paper_dir.name)
            return report.to_dict()

        except Exception as e:
            logger.debug(f"Benchmark eval skipped: {e}")
            return None

    def shadow_report(self) -> dict:
        """Return shadow agreement statistics for all reviewer GPTs."""
        if hasattr(self.cascade, "shadow_report"):
            return self.cascade.shadow_report()
        return {}


def _extract_json_from_response(text: str) -> Optional[dict]:
    """Extract JSON object from an LLM response that may contain markdown fences."""
    if not text:
        return None
    # Try raw parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try extracting from markdown code fences
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # Try finding first { to last }
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    return None


def _score_to_decision(score: float) -> str:
    """Map 1-10 overall score to decision label (ICLR convention)."""
    if score >= STRONG_ACCEPT_THRESHOLD:
        return "strong_accept"
    elif score >= ACCEPT_THRESHOLD:
        return "accept"
    elif score >= BORDERLINE_LOW:
        return "borderline"
    elif score >= 3.0:
        return "reject"
    else:
        return "strong_reject"


def _parse_tier_result_to_section_review(
    tier_result,
    section_key: str,
    reviewer_id: str,
    latency_ms: float,
) -> SectionReview:
    """Parse a CascadeRunner TierResult into a structured SectionReview."""
    review = SectionReview(
        section_key=section_key,
        reviewer_id=reviewer_id,
        latency_ms=latency_ms,
        tier_used=tier_result.tier if hasattr(tier_result, "tier") else 2.0,
        confidence=tier_result.confidence if hasattr(tier_result, "confidence") else 0.0,
    )

    result = tier_result.result if hasattr(tier_result, "result") else tier_result
    if isinstance(result, dict):
        if "passed" in result and "scores" not in result:
            # Heuristic tier returns {passed: bool, issues: [...]}
            is_pass = result.get("passed", False)
            base = 3.0 if is_pass else 1.5  # 1-4 scale
            review.scores = RubricScore(
                soundness=base, technical_novelty=base, empirical_novelty=base,
                significance=base, clarity=base, presentation=base,
            )
            review.overall_score = review.scores.weighted_signal()
            review.weaknesses = result.get("issues", [])
        else:
            # GPT/teacher tier returns structured review with scores
            if "scores" in result:
                review.scores = RubricScore.from_dict(result["scores"])
            if "overall_score" in result:
                review.overall_score = float(result["overall_score"])
            if "confidence" in result:
                review.confidence = float(result["confidence"])
            review.strengths = result.get("strengths", [])
            review.weaknesses = result.get("weaknesses", [])
            review.questions = result.get("questions", [])
            review.suggestions = result.get("suggestions", [])
            review.code_issues = result.get("code_issues", [])
    elif isinstance(result, str):
        # Fallback: string result from heuristic
        is_pass = "pass" in result.lower()
        base = 3.0 if is_pass else 1.5
        review.scores = RubricScore(
            soundness=base, technical_novelty=base, empirical_novelty=base,
            significance=base, clarity=base, presentation=base,
        )
        review.overall_score = review.scores.weighted_signal()

    return review
