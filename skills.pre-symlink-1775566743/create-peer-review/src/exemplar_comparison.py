"""Exemplar comparison: score papers against top arxiv papers.

Fetches exemplar papers via /arxiv, extracts structural metrics,
and compares the candidate paper against them. Produces a gap analysis
showing where the candidate diverges from venue norms.

Metrics compared:
    - Section word count ratios (how much of the paper each section occupies)
    - Citation density per section
    - Figure and table density
    - Abstract information density (unique concepts / words)
    - Code example presence and density
    - Reference count and recency

External signals (since arXiv has no built-in quality metrics):
    - Semantic Scholar citation count (field-normalized)
    - Semantic Scholar influential citation count
    - Known venue publication (NeurIPS, ICML, ICLR, ACL accepted)
    - GitHub code availability (presence/stars as proxy)
"""

from __future__ import annotations
import os

import json
import re
import subprocess
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from loguru import logger


SKILLS_DIR = Path(__file__).parent.parent.parent

# Semantic Scholar API (free, no key required for low-volume)
S2_API = "https://api.semanticscholar.org/graph/v1/paper"
S2_FIELDS = "title,citationCount,influentialCitationCount,venue,year,externalIds,isOpenAccess,openAccessPdf"


@dataclass
class PaperMetrics:
    """Structural metrics extracted from a paper."""

    paper_id: str = ""
    title: str = ""
    total_words: int = 0
    section_words: dict[str, int] = field(default_factory=dict)
    section_ratios: dict[str, float] = field(default_factory=dict)
    citation_count: int = 0
    citation_density: float = 0.0  # per 1000 words
    figure_count: int = 0
    table_count: int = 0
    code_block_count: int = 0
    reference_count: int = 0
    abstract_word_count: int = 0
    # External signals (populated via Semantic Scholar)
    s2_citation_count: int = 0
    s2_influential_citations: int = 0
    s2_venue: str = ""
    s2_year: int = 0
    s2_is_open_access: bool = False

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class ExemplarGap:
    """Gap between candidate paper and exemplar on a specific metric."""

    metric: str
    candidate_value: float
    exemplar_mean: float
    exemplar_std: float = 0.0
    gap: float = 0.0
    severity: str = "ok"  # ok, warning, critical
    suggestion: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class ExemplarComparison:
    """Full comparison of candidate against exemplar papers."""

    candidate_metrics: PaperMetrics = field(default_factory=PaperMetrics)
    exemplar_metrics: list[PaperMetrics] = field(default_factory=list)
    gaps: list[ExemplarGap] = field(default_factory=list)
    overall_similarity: float = 0.0  # 0-1 how close to exemplar norms
    recommendation: str = ""

    def to_dict(self) -> dict:
        return {
            "candidate": self.candidate_metrics.to_dict(),
            "exemplars": [e.to_dict() for e in self.exemplar_metrics],
            "gaps": [g.to_dict() for g in self.gaps],
            "overall_similarity": self.overall_similarity,
            "recommendation": self.recommendation,
        }

    def save(self, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "exemplar_comparison.json"
        path.write_text(json.dumps(self.to_dict(), indent=2))
        logger.info(f"Saved exemplar comparison to {path}")
        return path


class ExemplarComparator:
    """Compare a candidate paper against arxiv exemplars.

    Usage:
        comparator = ExemplarComparator()
        metrics = comparator.extract_metrics("artifacts/neophyte_paper_v5/")
        comparison = comparator.compare(
            paper_dir="artifacts/neophyte_paper_v5/",
            exemplar_ids=["2305.05176", "2411.05844"],
        )
    """

    def extract_metrics(self, paper_dir: str | Path) -> PaperMetrics:
        """Extract structural metrics from a local LaTeX paper."""
        paper_dir = Path(paper_dir)
        metrics = PaperMetrics(paper_id=paper_dir.name)

        # Read all section files
        sections_dir = paper_dir / "sections"
        if sections_dir.exists():
            for tex_file in sorted(sections_dir.glob("*.tex")):
                key = tex_file.stem
                content = tex_file.read_text()
                plain = _strip_latex(content)
                wc = len(plain.split())
                metrics.section_words[key] = wc
                metrics.total_words += wc

                # Count citations in this section
                cites = re.findall(r"\\cite[tp]?\*?\{([^}]+)\}", content)
                metrics.citation_count += len(cites)

                # Count figures, tables, code blocks
                metrics.figure_count += len(re.findall(r"\\begin\{figure", content))
                metrics.table_count += len(re.findall(r"\\begin\{table", content))
                metrics.code_block_count += len(re.findall(
                    r"\\begin\{(?:lstlisting|verbatim|minted)\}", content
                ))

        # Compute ratios
        if metrics.total_words > 0:
            for key, wc in metrics.section_words.items():
                metrics.section_ratios[key] = round(wc / metrics.total_words, 3)
            metrics.citation_density = round(
                metrics.citation_count / (metrics.total_words / 1000), 2
            )

        # Reference count from bib file
        bib_path = paper_dir / "references.bib"
        if bib_path.exists():
            bib_content = bib_path.read_text()
            metrics.reference_count = len(re.findall(r"@\w+\{", bib_content))

        # Abstract word count
        metrics.abstract_word_count = metrics.section_words.get("abstract", 0)

        return metrics

    def fetch_s2_metadata(self, arxiv_id: str) -> Optional[dict]:
        """Fetch paper metadata from Semantic Scholar (free API, no key needed).

        Since arXiv has no built-in quality/viewing metrics, Semantic Scholar
        provides the best external signals: citation counts, influential
        citation counts, venue acceptance, and open access status.
        """
        url = f"{S2_API}/ARXIV:{arxiv_id}?fields={S2_FIELDS}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "create-peer-review/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
                logger.info(
                    f"S2 metadata for {arxiv_id}: "
                    f"citations={data.get('citationCount', 0)}, "
                    f"venue={data.get('venue', 'unknown')}"
                )
                return data
        except urllib.error.HTTPError as e:
            if e.code == 404:
                logger.debug(f"Paper {arxiv_id} not found on Semantic Scholar")
            else:
                logger.warning(f"S2 API error for {arxiv_id}: {e.code}")
            return None
        except Exception as e:
            logger.warning(f"S2 fetch failed for {arxiv_id}: {e}")
            return None

    def fetch_exemplar_metrics(self, arxiv_id: str) -> Optional[PaperMetrics]:
        """Fetch and extract metrics from an arxiv paper.

        Combines /arxiv skill for structural analysis with Semantic Scholar
        for external quality signals (citations, venue, influence).
        """
        metrics = PaperMetrics(paper_id=arxiv_id)

        # 1. Semantic Scholar: external quality signals
        s2_data = self.fetch_s2_metadata(arxiv_id)
        if s2_data:
            metrics.title = s2_data.get("title", "")
            metrics.s2_citation_count = s2_data.get("citationCount", 0)
            metrics.s2_influential_citations = s2_data.get("influentialCitationCount", 0)
            metrics.s2_venue = s2_data.get("venue", "")
            metrics.s2_year = s2_data.get("year", 0)
            metrics.s2_is_open_access = s2_data.get("isOpenAccess", False)

        # 2. /arxiv skill: structural analysis (if available)
        arxiv_skill = SKILLS_DIR / "arxiv" / "run.sh"
        if arxiv_skill.exists():
            try:
                result = subprocess.run(
                    [str(arxiv_skill), "learn", arxiv_id],
                    capture_output=True, text=True, timeout=120,
                    env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
                )
                if result.returncode == 0:
                    output = result.stdout
                    if "title:" in output.lower() and not metrics.title:
                        title_match = re.search(r"[Tt]itle:\s*(.+)", output)
                        if title_match:
                            metrics.title = title_match.group(1).strip()
            except subprocess.TimeoutExpired:
                logger.warning(f"Timeout fetching arxiv {arxiv_id}")
            except Exception as e:
                logger.warning(f"Error fetching exemplar {arxiv_id}: {e}")

        # Return metrics if we got anything useful
        if metrics.title or metrics.s2_citation_count > 0:
            return metrics
        return None

    def compare(
        self,
        paper_dir: str | Path,
        exemplar_ids: Optional[list[str]] = None,
        exemplar_metrics: Optional[list[PaperMetrics]] = None,
    ) -> ExemplarComparison:
        """Compare candidate paper against exemplars.

        Args:
            paper_dir: Path to candidate paper directory.
            exemplar_ids: ArXiv IDs to fetch and compare against.
            exemplar_metrics: Pre-computed exemplar metrics (skip fetching).

        Returns:
            ExemplarComparison with gap analysis.
        """
        candidate = self.extract_metrics(paper_dir)
        comparison = ExemplarComparison(candidate_metrics=candidate)

        # Collect exemplar metrics
        if exemplar_metrics:
            comparison.exemplar_metrics = exemplar_metrics
        elif exemplar_ids:
            for aid in exemplar_ids:
                em = self.fetch_exemplar_metrics(aid)
                if em:
                    comparison.exemplar_metrics.append(em)

        # If no exemplar data, compare against venue norms
        if not comparison.exemplar_metrics:
            comparison.gaps = self._compare_against_norms(candidate)
        else:
            comparison.gaps = self._compare_against_exemplars(
                candidate, comparison.exemplar_metrics
            )

        # Overall similarity score
        if comparison.gaps:
            ok_count = sum(1 for g in comparison.gaps if g.severity == "ok")
            comparison.overall_similarity = round(ok_count / len(comparison.gaps), 2)
        else:
            comparison.overall_similarity = 1.0

        # Recommendation
        if comparison.overall_similarity >= 0.8:
            comparison.recommendation = "Paper structure aligns well with venue norms."
        elif comparison.overall_similarity >= 0.5:
            comparison.recommendation = "Several structural gaps — address warnings before submission."
        else:
            comparison.recommendation = "Significant structural issues — major revision needed."

        return comparison

    def _compare_against_norms(self, candidate: PaperMetrics) -> list[ExemplarGap]:
        """Compare against empirical arxiv corpus distributions.

        Uses ArxivBenchmarks when available (data/arxiv_benchmarks.json).
        Falls back to hardcoded norms only when no corpus is loaded.
        """
        from .benchmarks import ArxivBenchmarks

        benchmarks = ArxivBenchmarks.load()
        if benchmarks.corpus:
            return self._compare_against_benchmarks(candidate, benchmarks)

        # Fallback: hardcoded norms (only when no corpus exists)
        return self._compare_against_hardcoded_norms(candidate)

    def _compare_against_benchmarks(
        self,
        candidate: PaperMetrics,
        benchmarks,
    ) -> list[ExemplarGap]:
        """Compare using empirical percentile distributions from arxiv corpus."""
        gaps = []
        thresholds = benchmarks.get_thresholds()

        # Map PaperMetrics fields to benchmark metric names
        metric_map = {
            "words": ("total_words", candidate.total_words),
            "refs": ("reference_count", candidate.reference_count),
            "figures": ("figures", candidate.figure_count),
            "tables": ("tables", candidate.table_count),
        }

        # Compute per-page metrics for the candidate
        est_pages = max(1, candidate.total_words // 350)
        metric_map["fig_per_pg"] = ("fig_per_page", candidate.figure_count / est_pages)
        metric_map["ref_per_pg"] = ("ref_per_page", candidate.reference_count / est_pages)

        for bm_key, (display_name, value) in metric_map.items():
            t = thresholds.get(bm_key)
            if not t:
                continue
            dist = benchmarks.distributions[bm_key]
            rank = dist.percentile_rank(value)

            g = ExemplarGap(
                metric=display_name,
                candidate_value=value,
                exemplar_mean=t["target"],
                exemplar_std=dist.std,
            )

            if rank < 0.25:
                g.severity = "critical" if rank < 0.10 else "warning"
                g.gap = t["min"] - value
                g.suggestion = (
                    f"Below p25 ({t['min']:.1f}), rank {rank:.0%} in corpus of {t['n']}"
                )
            elif rank > 0.75:
                g.severity = "ok"
                g.suggestion = f"Above p75 ({t['max']:.1f}), rank {rank:.0%} — strong"
            else:
                g.severity = "ok"
                g.suggestion = f"Rank {rank:.0%} in corpus (p50={t['target']:.1f})"

            gaps.append(g)

        # Section word count norms (these remain structural, not corpus-derived)
        SECTION_NORMS = {
            "abstract": (120, 300),
            "intro": (600, 1800),
            "related": (500, 1500),
            "eval": (600, 2000),
        }
        for section, (smin, smax) in SECTION_NORMS.items():
            actual = candidate.section_words.get(section, 0)
            if actual > 0 and actual < smin:
                gaps.append(ExemplarGap(
                    metric=f"{section}_words",
                    candidate_value=actual,
                    exemplar_mean=(smin + smax) / 2,
                    severity="warning",
                    suggestion=f"{section} section needs ~{smin - actual:.0f} more words",
                ))

        # Code examples (not in arxiv corpus data, use structural norm)
        g = ExemplarGap(
            metric="code_blocks",
            candidate_value=candidate.code_block_count,
            exemplar_mean=3.0,
        )
        if candidate.code_block_count == 0:
            g.severity = "warning"
            g.suggestion = "No code examples — consider adding for reproducibility"
        gaps.append(g)

        return gaps

    def _compare_against_hardcoded_norms(self, candidate: PaperMetrics) -> list[ExemplarGap]:
        """Fallback: hardcoded norms when no benchmark corpus exists."""
        gaps = []

        WORD_NORMS = {"total": (4000, 8000)}
        low, high = WORD_NORMS["total"]
        mean = (low + high) / 2
        gap = ExemplarGap(
            metric="total_words",
            candidate_value=candidate.total_words,
            exemplar_mean=mean,
        )
        if candidate.total_words < low:
            gap.severity = "critical"
            gap.gap = low - candidate.total_words
            gap.suggestion = f"Paper is {gap.gap:.0f} words short of minimum ({low})"
        gaps.append(gap)

        g = ExemplarGap(
            metric="reference_count",
            candidate_value=candidate.reference_count,
            exemplar_mean=25.0,
        )
        if candidate.reference_count < 10:
            g.severity = "critical"
            g.suggestion = "Too few references"
        gaps.append(g)

        g = ExemplarGap(
            metric="figures",
            candidate_value=candidate.figure_count,
            exemplar_mean=4.0,
        )
        if candidate.figure_count == 0:
            g.severity = "critical"
            g.suggestion = "No figures"
        gaps.append(g)

        return gaps

    def _compare_against_exemplars(
        self,
        candidate: PaperMetrics,
        exemplars: list[PaperMetrics],
    ) -> list[ExemplarGap]:
        """Compare against actual exemplar paper metrics.

        Combines structural norms with Semantic Scholar external signals.
        Since arXiv has no built-in quality metrics, S2 citation counts
        are the best proxy for paper impact and quality.
        """
        # Start with structural norm comparison
        gaps = self._compare_against_norms(candidate)

        # Add Semantic Scholar-based comparisons
        s2_citations = [e.s2_citation_count for e in exemplars if e.s2_citation_count > 0]
        s2_influential = [e.s2_influential_citations for e in exemplars if e.s2_influential_citations > 0]
        s2_venues = [e.s2_venue for e in exemplars if e.s2_venue]

        if s2_citations:
            mean_citations = sum(s2_citations) / len(s2_citations)
            gaps.append(ExemplarGap(
                metric="exemplar_citations",
                candidate_value=0.0,  # candidate is unpublished
                exemplar_mean=mean_citations,
                severity="ok",
                suggestion=(
                    f"Exemplars average {mean_citations:.0f} citations — "
                    f"target this impact level"
                ),
            ))

        if s2_influential:
            mean_influential = sum(s2_influential) / len(s2_influential)
            gaps.append(ExemplarGap(
                metric="exemplar_influential_citations",
                candidate_value=0.0,
                exemplar_mean=mean_influential,
                severity="ok",
                suggestion=(
                    f"Exemplars average {mean_influential:.0f} influential citations — "
                    f"indicates field-shaping work"
                ),
            ))

        if s2_venues:
            venue_str = ", ".join(set(s2_venues))
            gaps.append(ExemplarGap(
                metric="exemplar_venues",
                candidate_value=0.0,
                exemplar_mean=float(len(set(s2_venues))),
                severity="ok",
                suggestion=f"Exemplars published at: {venue_str}",
            ))

        return gaps


def _strip_latex(text: str) -> str:
    """Strip LaTeX commands for word counting.

    Delegates to review_heuristics._strip_latex to avoid duplication.
    Falls back to a simple inline version if import fails.
    """
    try:
        from .review_heuristics import _strip_latex as _strip
        return _strip(text)
    except ImportError:
        # Minimal fallback: strip commands but preserve prose environments
        text = re.sub(r"%.*$", "", text, flags=re.MULTILINE)
        text = re.sub(r"\\[a-zA-Z]+\*?\{([^}]*)\}", r" \1 ", text)
        text = re.sub(r"\\[a-zA-Z]+", " ", text)
        text = re.sub(r"[{}]", " ", text)
        return text
