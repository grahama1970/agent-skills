"""Tier 0: Heuristic peer review checks.

Fast, deterministic checks that catch obvious quality issues without
invoking any model. These run in microseconds and resolve trivially
good or bad sections.

Checks:
    - Word count within venue-appropriate range
    - Citation density (citations per 1000 words)
    - LaTeX compilation indicators (balanced braces, valid environments)
    - Forbidden phrases ("clearly", "obviously", "it is well known")
    - Code example presence and basic validity
    - Figure/table reference consistency
    - Section balance (no section dominates excessively)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Section word count targets (arxiv methodology paper conventions)
# ---------------------------------------------------------------------------
SECTION_TARGETS = {
    "abstract": {"min": 120, "max": 300},
    "intro": {"min": 600, "max": 1800},
    "related": {"min": 500, "max": 1500},
    "design": {"min": 700, "max": 2000},
    "impl": {"min": 500, "max": 1500},
    "eval": {"min": 600, "max": 2000},
    "discussion": {"min": 400, "max": 1200},
}

# Phrases that weaken academic writing
FORBIDDEN_PHRASES = [
    r"\bclearly\b",
    r"\bobviously\b",
    r"\bit is well known\b",
    r"\btrivially\b",
    r"\bas everyone knows\b",
    r"\bneedless to say\b",
    r"\bof course\b",
    r"\bsimply put\b",
    r"\bbasically\b",
]

# LaTeX citation patterns
CITE_PATTERN = re.compile(r"\\cite[tp]?\*?\{([^}]+)\}")
FIGURE_REF_PATTERN = re.compile(r"\\ref\{fig:([^}]+)\}")
TABLE_REF_PATTERN = re.compile(r"\\ref\{tab:([^}]+)\}")
FIGURE_LABEL_PATTERN = re.compile(r"\\label\{fig:([^}]+)\}")
TABLE_LABEL_PATTERN = re.compile(r"\\label\{tab:([^}]+)\}")

# Code listing patterns
CODE_PATTERNS = [
    re.compile(r"\\begin\{lstlisting\}"),
    re.compile(r"\\begin\{verbatim\}"),
    re.compile(r"\\begin\{minted\}"),
    re.compile(r"```"),  # markdown-style in some templates
]


@dataclass
class HeuristicResult:
    """Result from heuristic review of a section."""

    section_key: str
    passed: bool = True
    word_count: int = 0
    word_count_ok: bool = True
    citation_count: int = 0
    citation_density: float = 0.0  # citations per 1000 words
    citation_density_ok: bool = True
    forbidden_phrases_found: list[str] = field(default_factory=list)
    has_code_examples: bool = False
    code_example_count: int = 0
    latex_issues: list[str] = field(default_factory=list)
    figure_refs_ok: bool = True
    table_refs_ok: bool = True
    issues: list[str] = field(default_factory=list)
    score: float = 7.0  # Default passing score

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


class HeuristicReviewer:
    """Tier 0: Deterministic heuristic checks for paper quality.

    Runs in microseconds. Returns a HeuristicResult with pass/fail
    and a coarse quality score. Used as the first tier in the
    peer review cascade.

    Usage:
        reviewer = HeuristicReviewer()
        result = reviewer.review_section("eval", content, references)
        if result.passed:
            print(f"Section passes heuristics: score={result.score}")
    """

    def __init__(self, strict: bool = False):
        self.strict = strict

    def review_section(
        self,
        section_key: str,
        content: str,
        references: str = "",
        full_paper: Optional[dict[str, str]] = None,
    ) -> HeuristicResult:
        """Run all heuristic checks on a section."""
        result = HeuristicResult(section_key=section_key)

        # Strip LaTeX commands for word counting
        plain = _strip_latex(content)
        result.word_count = len(plain.split())

        # Word count check
        targets = SECTION_TARGETS.get(section_key, {"min": 200, "max": 2000})
        if result.word_count < targets["min"]:
            result.word_count_ok = False
            result.issues.append(
                f"Word count {result.word_count} below minimum {targets['min']}"
            )
        elif result.word_count > targets["max"]:
            result.word_count_ok = False
            result.issues.append(
                f"Word count {result.word_count} above maximum {targets['max']}"
            )

        # Citation density
        citations = CITE_PATTERN.findall(content)
        result.citation_count = len(citations)
        if result.word_count > 0:
            result.citation_density = round(
                result.citation_count / (result.word_count / 1000), 2
            )

        # Check citation density for non-abstract sections
        if section_key not in ("abstract",) and result.word_count > 200:
            if result.citation_density < 1.0:
                result.citation_density_ok = False
                result.issues.append(
                    f"Low citation density: {result.citation_density}/1K words"
                )

        # Verify cited references exist in bib (Fix #4: parse bib keys properly)
        if references:
            bib_keys = set(re.findall(r"@\w+\{(\w+)", references))
            for cite_group in citations:
                for cite_key in cite_group.split(","):
                    cite_key = cite_key.strip()
                    if cite_key and cite_key not in bib_keys:
                        result.issues.append(f"Citation '{cite_key}' not found in references.bib")

        # Forbidden phrases
        for pattern in FORBIDDEN_PHRASES:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                result.forbidden_phrases_found.extend(matches)

        if result.forbidden_phrases_found:
            result.issues.append(
                f"Forbidden phrases: {', '.join(result.forbidden_phrases_found)}"
            )

        # Code examples
        for pat in CODE_PATTERNS:
            result.code_example_count += len(pat.findall(content))
        result.has_code_examples = result.code_example_count > 0

        # For impl and eval sections, code examples are expected
        if section_key in ("impl", "eval", "design") and not result.has_code_examples:
            result.issues.append(f"No code examples in {section_key} section")

        # LaTeX balance checks
        latex_issues = _check_latex_balance(content)
        result.latex_issues = latex_issues
        if latex_issues:
            result.issues.extend(latex_issues)

        # Figure/table reference consistency
        if full_paper:
            all_content = "\n".join(full_paper.values())
            fig_refs = set(FIGURE_REF_PATTERN.findall(all_content))
            fig_labels = set(FIGURE_LABEL_PATTERN.findall(all_content))
            orphan_refs = fig_refs - fig_labels
            if orphan_refs:
                result.figure_refs_ok = False
                result.issues.append(f"Orphan figure refs: {orphan_refs}")

            tab_refs = set(TABLE_REF_PATTERN.findall(all_content))
            tab_labels = set(TABLE_LABEL_PATTERN.findall(all_content))
            orphan_tab_refs = tab_refs - tab_labels
            if orphan_tab_refs:
                result.table_refs_ok = False
                result.issues.append(f"Orphan table refs: {orphan_tab_refs}")

        # Compute score
        result.passed = len(result.issues) == 0
        if result.issues:
            # Deduct 0.5 per issue, floor at 2.0
            result.score = max(2.0, 7.0 - 0.5 * len(result.issues))
        else:
            result.score = 7.5

        return result

    def review_paper(
        self,
        sections: dict[str, str],
        references: str = "",
    ) -> dict[str, HeuristicResult]:
        """Review all sections, checking cross-section consistency."""
        results = {}
        for key, content in sections.items():
            results[key] = self.review_section(
                key, content, references, full_paper=sections
            )

        # Section balance check: no section should be >40% of total words
        total_words = sum(r.word_count for r in results.values())
        if total_words > 0:
            for key, r in results.items():
                ratio = r.word_count / total_words
                if ratio > 0.40:
                    r.issues.append(
                        f"Section '{key}' is {ratio:.0%} of paper — may be unbalanced"
                    )
                    r.passed = False

        return results


def _strip_latex(text: str) -> str:
    """Strip LaTeX commands for approximate word counting.

    Preserves prose inside list environments (itemize, enumerate, description)
    since those contain countable words. Only strips non-prose environments
    like equations, figures, tables, and code listings.
    """
    # Remove comments
    text = re.sub(r"%.*$", "", text, flags=re.MULTILINE)
    # Strip non-prose environments (equations, figures, tables, code)
    # but preserve itemize/enumerate/description which contain countable prose.
    _NON_PROSE = (
        "equation", "equation*", "align", "align*", "gather", "gather*",
        "figure", "figure*", "table", "table*", "tikzpicture",
        "lstlisting", "verbatim", "minted",
    )
    for env in _NON_PROSE:
        text = re.sub(
            rf"\\begin\{{{re.escape(env)}\}}.*?\\end\{{{re.escape(env)}\}}",
            " ", text, flags=re.DOTALL,
        )
    # Remove commands with arguments (e.g. \textbf{word} → word)
    text = re.sub(r"\\[a-zA-Z]+\*?\{([^}]*)\}", r" \1 ", text)
    # Remove standalone commands (e.g. \item, \par)
    text = re.sub(r"\\[a-zA-Z]+", " ", text)
    # Remove braces
    text = re.sub(r"[{}]", " ", text)
    return text


def _check_latex_balance(text: str) -> list[str]:
    """Check for unbalanced LaTeX constructs."""
    issues = []

    # Balanced braces
    depth = 0
    for ch in text:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        if depth < 0:
            issues.append("Unbalanced closing brace '}'")
            break
    if depth > 0:
        issues.append(f"Unbalanced opening braces: {depth} unclosed")

    # Balanced begin/end
    begins = re.findall(r"\\begin\{(\w+)\}", text)
    ends = re.findall(r"\\end\{(\w+)\}", text)
    for env in set(begins):
        bc = begins.count(env)
        ec = ends.count(env)
        if bc != ec:
            issues.append(f"Unbalanced environment '{env}': {bc} begins, {ec} ends")

    return issues
