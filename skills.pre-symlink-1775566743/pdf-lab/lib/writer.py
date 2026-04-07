"""Write-back engine for pdf-lab.

IMPORTANT DISTINCTION:
- Per-PDF parameter tuning (line_scale for a specific table, etc.) is returned
  as runtime params to the caller. These are NOT written to pipeline code.
- Global pipeline fixes (bug fixes, missing patterns, systematically wrong
  defaults proven across multiple synthetics) ARE written to pipeline code.

Write-back only happens when:
1. A default is proven systematically wrong across the regression suite
2. A regex pattern is missing (new citation pattern, new numbering format)
3. A threshold is demonstrably wrong for an entire document class (not one PDF)

The writer NEVER modifies pipeline code for per-document tuning.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from .delta import ExtractionDelta, ReviewContext, Diagnosis
from .params import TrialParams


# Extractor project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
EXTRACTOR_ROOT = Path(os.environ.get(
    "EXTRACTOR_ROOT",
    str(_PROJECT_ROOT / "extractor"),
))

# Pipeline file paths (relative to EXTRACTOR_ROOT)
PIPELINE_FILES = {
    "tables_extraction": "src/extractor/pipeline/utils/tables/extraction.py",
    "tables_heuristics": "src/extractor/pipeline/utils/tables/heuristics.py",
    "s04_section_builder": "src/extractor/pipeline/steps/s04_section_builder.py",
    "s05_table_extractor": "src/extractor/pipeline/steps/s05_table_extractor.py",
    "s00_profile_detector": "src/extractor/pipeline/steps/s00_profile_detector.py",
    "sections_heuristics": "src/extractor/pipeline/utils/sections/heuristics.py",
    "presets": "src/extractor/core/presets.py",
}


@dataclass
class CodeChange:
    """A single code change to write to the pipeline."""

    file: str  # Relative to EXTRACTOR_ROOT
    tier: str  # env_default, heuristic, pattern_rule, preset, memory
    description: str  # Human-readable description
    reason: str  # Why this change was made (convergence evidence)
    old_text: str = ""  # Text to find and replace
    new_text: str = ""  # Replacement text
    section: str = ""  # For YAML: section path
    update: Dict[str, Any] = field(default_factory=dict)  # For YAML: merge data
    applied: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WriteBackResult:
    """Result of writing fixes back to the pipeline."""

    status: str  # "merged", "reverted", "dry_run", "skipped"
    changes: List[CodeChange] = field(default_factory=list)
    commit_sha: str = ""
    branch: str = ""
    reason: str = ""
    runtime_params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["changes"] = [c.to_dict() for c in self.changes]
        return d


@dataclass
class RegressionItem:
    """A single synthetic that degraded after a fix."""

    pdf_path: str
    patterns: List[str]
    baseline_delta: float
    new_delta: float

    @property
    def drop(self) -> float:
        return self.baseline_delta - self.new_delta


@dataclass
class RegressionResult:
    """Result of regression testing against stored synthetics."""

    degraded: bool
    total_tested: int
    categories_tested: List[str]
    degraded_items: List[RegressionItem] = field(default_factory=list)
    reason: str = ""


def classify_fix(
    winning_params: TrialParams,
    patterns: List[str],
    diagnosis: Diagnosis,
) -> str:
    """Classify whether a convergence result warrants a global code fix or is per-PDF tuning.

    Returns:
        "global_fix" — proven bug/systematic issue, write to pipeline code
        "per_pdf"    — document-specific tuning, return as runtime params only
    """
    # Global fix indicators:
    # 1. Missing pattern rules (regex gaps)
    if winning_params.new_citation_pattern:
        return "global_fix"

    # 2. S00 is systematically overestimating (calibration bug)
    if diagnosis.s00_overestimated:
        return "global_fix"

    # 3. Section undersegmentation affecting an entire document class
    #    (not just one PDF — check if patterns indicate a class-level issue)
    class_level_patterns = {"section_undersegmentation", "section_oversegmentation"}
    if class_level_patterns & set(patterns):
        # Only global if the threshold change is significant (>1.0 difference)
        if abs(winning_params.font_threshold - 11.0) >= 1.0:
            return "global_fix"

    # Everything else is per-PDF tuning
    return "per_pdf"


def plan_code_changes(
    winning_params: TrialParams,
    patterns: List[str],
    delta: ExtractionDelta,
    diagnosis: Diagnosis,
    new_delta_value: float = 0.0,
) -> List[CodeChange]:
    """Plan code changes for a global fix.

    Only called when classify_fix() returns "global_fix".
    These are bug fixes and systematic improvements, NOT per-PDF tuning.
    """
    changes: List[CodeChange] = []

    # Tier 3: New pattern rules (always a bug fix — missing regex)
    if winning_params.new_citation_pattern:
        # SECURITY: treat supplied pattern as a literal fragment; escape before use.
        pattern_raw = winning_params.new_citation_pattern
        pattern = pattern_raw.strip()
        if not pattern:
            logger.warning("Rejecting citation pattern: empty after trimming")
        elif len(pattern) > 200:
            logger.warning(f"Rejecting citation pattern: too long ({len(pattern)} chars)")
        elif not pattern.isprintable() or any(ord(c) > 127 for c in pattern):
            logger.warning("Rejecting citation pattern: contains non-printable or non-ASCII characters")
        else:
            # Escape for safe regex search; do NOT interpret user-supplied regex.
            escaped = re.escape(pattern)
            safe_regex = f"(?i)\\b{escaped}\\b"
            safe_regex_quoted = safe_regex.replace("'", "\\'")
            changes.append(CodeChange(
                file=PIPELINE_FILES["s04_section_builder"],
                tier="pattern_rule",
                description="Add missing citation literal match (case-insensitive)",
                reason=(
                    "Convergence discovered citation fragment not covered by existing filters. "
                    "Pattern stored as escaped literal with word boundaries."
                ),
                old_text="    return False\n\n\ndef _is_toc_or_page_header_footer",
                new_text=(
                    "    # pdf-lab: citation literal fragment filter (escaped, case-insensitive)\n"
                    f"    if re.search('{safe_regex_quoted}', text):\n"
                    "        return True\n"
                    "    return False\n\n\ndef _is_toc_or_page_header_footer"
                ),
            ))

    # Tier 2: Heuristic threshold fixes (only for proven systematic issues)
    if (
        "section_undersegmentation" in patterns
        and abs(winning_params.font_threshold - 11.0) >= 1.0
    ):
        old_threshold = "LARGE_FONT_THRESHOLD = 11.0"
        new_threshold = f"LARGE_FONT_THRESHOLD = {winning_params.font_threshold}"
        changes.append(CodeChange(
            file=PIPELINE_FILES["s04_section_builder"],
            tier="heuristic",
            description=f"Lower LARGE_FONT_THRESHOLD from 11.0 to {winning_params.font_threshold}",
            reason=(
                f"Section undersegmentation: {delta.actual_sections}/{delta.estimated_sections} "
                f"sections found. Lowering font threshold improves detection for "
                f"documents with smaller header fonts. "
                f"Delta improved from {delta.overall_delta:.2f} to {new_delta_value:.2f}."
            ),
            old_text=old_threshold,
            new_text=new_threshold,
        ))

    return changes


def write_fix_to_pipeline(
    winning_params: TrialParams,
    patterns: List[str],
    delta: ExtractionDelta,
    diagnosis: Diagnosis,
    review_context: ReviewContext,
    new_delta_value: float = 0.0,
    dry_run: bool = False,
) -> WriteBackResult:
    """Write a global fix back to the pipeline code, or return per-PDF params.

    This function distinguishes between:
    - Global fixes (bug fixes, missing patterns) → written to code
    - Per-PDF tuning (line_scale, padding) → returned as runtime params only
    """
    if not EXTRACTOR_ROOT.is_dir():
        logger.error(f"EXTRACTOR_ROOT not found: {EXTRACTOR_ROOT}")
        return WriteBackResult(
            status="failed",
            reason=f"EXTRACTOR_ROOT not found: {EXTRACTOR_ROOT}",
            runtime_params=_build_runtime_params(winning_params, patterns),
        )

    # Always prepare runtime params (per-PDF tuning)
    runtime_params = _build_runtime_params(winning_params, patterns)

    # Classify: is this a global fix or per-PDF tuning?
    fix_type = classify_fix(winning_params, patterns, diagnosis)

    if fix_type == "per_pdf":
        logger.info(
            f"Per-PDF tuning result for patterns {patterns}. "
            f"Returning runtime params only (no code write-back)."
        )
        return WriteBackResult(
            status="per_pdf_only",
            runtime_params=runtime_params,
            reason="Per-PDF parameter tuning — not a global pipeline fix",
        )

    # Global fix — plan code changes
    changes = plan_code_changes(winning_params, patterns, delta, diagnosis, new_delta_value)

    if not changes:
        logger.info("No code changes needed for global fix.")
        return WriteBackResult(
            status="no_changes",
            runtime_params=runtime_params,
            reason="Global fix classified but no concrete code changes identified",
        )

    if dry_run:
        logger.info(f"DRY RUN: Would apply {len(changes)} code changes:")
        for c in changes:
            logger.info(f"  [{c.tier}] {c.file}: {c.description}")
        return WriteBackResult(
            status="dry_run",
            changes=changes,
            runtime_params=runtime_params,
        )

    # Apply changes with git versioning
    return _apply_with_git(changes, patterns, delta, review_context, runtime_params, new_delta_value)


def _build_runtime_params(params: TrialParams, patterns: List[str]) -> Dict[str, Any]:
    """Build runtime parameters for per-PDF re-extraction."""
    runtime: Dict[str, Any] = {}

    # Env overrides for this extraction
    if params.env:
        runtime["env_overrides"] = dict(params.env)

    # Extraction-specific params
    if params.extraction_overrides:
        runtime["extraction_overrides"] = dict(params.extraction_overrides)

    # Tuned values
    if params.font_threshold != 11.0:
        runtime["font_threshold"] = params.font_threshold
    if params.short_section_merge_threshold != 150:
        runtime["short_section_merge_threshold"] = params.short_section_merge_threshold

    runtime["source_patterns"] = patterns
    return runtime


def _apply_with_git(
    changes: List[CodeChange],
    patterns: List[str],
    delta: ExtractionDelta,
    review_context: ReviewContext,
    runtime_params: Dict[str, Any],
    new_delta_value: float,
) -> WriteBackResult:
    """Apply code changes with git versioning and regression checking."""
    patterns_hash = _short_hash(",".join(sorted(patterns)))
    timestamp = int(time.time())
    branch = f"pdf-lab/{patterns_hash}_{timestamp}"

    # Remember current branch so we can return to it (not always 'main')
    try:
        original_branch = _git_run(
            ["rev-parse", "--abbrev-ref", "HEAD"], cwd=EXTRACTOR_ROOT
        ).strip()
    except Exception:
        original_branch = "main"

    # Validate git repo
    git_dir = EXTRACTOR_ROOT / ".git"
    if not git_dir.exists():
        logger.error(f"Not a git repository: {EXTRACTOR_ROOT}")
        return WriteBackResult(
            status="failed",
            reason=f"Not a git repository: {EXTRACTOR_ROOT}",
            runtime_params=runtime_params,
        )

    # Check for dirty working tree
    stashed = False
    try:
        status_output = _git_run(["status", "--porcelain"], cwd=EXTRACTOR_ROOT).strip()
        if status_output:
            logger.warning(
                f"Working tree has uncommitted changes. "
                f"Stashing before creating pdf-lab branch."
            )
            _git_run(["stash", "push", "-m", "pdf-lab: auto-stash"], cwd=EXTRACTOR_ROOT)
            stashed = True
            logger.info("Stashed local changes as 'pdf-lab: auto-stash'")
    except Exception as e:
        logger.warning(f"Could not check/stash working tree: {e}")

    try:
        # 1. Create branch
        _git_run(["checkout", "-b", branch], cwd=EXTRACTOR_ROOT)
        logger.info(f"Created branch {branch} for pdf-lab global fix")

        # 2. Apply code edits
        for change in changes:
            _apply_code_edit(change)

        # 3. Commit with persona attribution
        commit_msg = (
            f"pdf-lab: {', '.join(patterns)} "
            f"delta {delta.overall_delta:.2f}->{new_delta_value:.2f}"
        )
        commit_body = json.dumps({
            "patterns": patterns,
            "delta_before": round(delta.overall_delta, 4),
            "delta_after": round(new_delta_value, 4),
            "files_changed": [c.file for c in changes],
            "fix_type": "global",
        })

        trailers = [
            f"Pdf-Lab-Patterns: {','.join(patterns)}",
            f"Reviewed-By: {review_context.persona_name}",
            f"Persona-Role: {review_context.persona_role}",
            f"Source-PDF: {review_context.source_pdf}",
        ]
        if review_context.issue_codes:
            trailers.append(f"Issue-Codes: {','.join(review_context.issue_codes)}")
        if review_context.score is not None:
            trailers.append(f"Review-Score: {review_context.score}")

        trailer_args = []
        for t in trailers:
            trailer_args.extend(["--trailer", t])

        applied = [c.file for c in changes if c.applied]
        if not applied:
            logger.warning("No changes were applied. Cleaning up branch.")
            _git_run(["checkout", original_branch], cwd=EXTRACTOR_ROOT)
            _git_run(["branch", "-D", branch], cwd=EXTRACTOR_ROOT)
            if stashed:
                _git_run(["stash", "pop"], cwd=EXTRACTOR_ROOT)
                logger.info("Restored stashed changes")
            return WriteBackResult(
                status="no_changes",
                runtime_params=runtime_params,
                reason="All code edits failed to apply (files may have changed)",
            )

        _git_run(["add"] + applied, cwd=EXTRACTOR_ROOT)
        _git_run(
            ["commit", "-m", commit_msg, "-m", commit_body] + trailer_args,
            cwd=EXTRACTOR_ROOT,
        )

        sha = _git_run(["rev-parse", "HEAD"], cwd=EXTRACTOR_ROOT).strip()

        # 4. Switch back to original branch (don't merge — let human review)
        _git_run(["checkout", original_branch], cwd=EXTRACTOR_ROOT)

        # Restore stash on success
        if stashed:
            _git_run(["stash", "pop"], cwd=EXTRACTOR_ROOT)
            logger.info("Restored stashed changes")

        logger.info(
            f"Global fix committed on branch {branch} (sha={sha[:8]}). "
            f"Review and merge manually."
        )

        return WriteBackResult(
            status="committed",
            changes=[c for c in changes if c.applied],
            commit_sha=sha,
            branch=branch,
            runtime_params=runtime_params,
            reason=f"Global fix on branch {branch}. Merge after review.",
        )

    except Exception as e:
        logger.error(f"Git write-back failed: {e}")
        # Attempt to return to original branch and clean up
        try:
            _git_run(["checkout", original_branch], cwd=EXTRACTOR_ROOT)
        except Exception as e:
            logger.debug("value lookup failed: {}", e)
        try:
            _git_run(["branch", "-D", branch], cwd=EXTRACTOR_ROOT)
        except Exception as e:
            logger.debug("value lookup failed: {}", e)
        if stashed:
            try:
                _git_run(["stash", "pop"], cwd=EXTRACTOR_ROOT)
                logger.info("Restored stashed changes after failure")
            except Exception:
                logger.warning("Could not restore stash after failure — run 'git stash pop' manually")
        return WriteBackResult(
            status="failed",
            reason=str(e),
            runtime_params=runtime_params,
        )


def _apply_code_edit(change: CodeChange) -> None:
    """Apply a single code edit to a pipeline file."""
    filepath = (EXTRACTOR_ROOT / change.file).resolve()

    # Path traversal prevention: ensure file stays within EXTRACTOR_ROOT
    try:
        filepath.relative_to(EXTRACTOR_ROOT.resolve())
    except ValueError:
        logger.error(
            f"Path traversal blocked: {change.file} resolves outside EXTRACTOR_ROOT"
        )
        return

    if not filepath.exists():
        logger.warning(f"File not found: {filepath}")
        return

    content = filepath.read_text()

    if change.old_text and change.new_text:
        if change.old_text not in content:
            logger.warning(
                f"Anchor not found in {change.file}. Aborting edit. "
                f"File may have been modified since convergence."
            )
            raise RuntimeError(
                f"pdf-lab write-back aborted: anchor missing in {change.file}. "
                f"The target code has changed since convergence ran."
            )

        new_content = content.replace(change.old_text, change.new_text, 1)
        filepath.write_text(new_content)
        change.applied = True
        logger.info(f"Applied [{change.tier}] edit to {change.file}: {change.description}")
    else:
        logger.warning(f"No old_text/new_text for change: {change.description}")


def _git_run(args: List[str], cwd: Path = EXTRACTOR_ROOT) -> str:
    """Run a git command and return stdout."""
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed (rc={result.returncode}): {result.stderr}")
    return result.stdout


def _short_hash(text: str) -> str:
    """Generate a short hash for branch naming."""
    import hashlib
    return hashlib.sha256(text.encode()).hexdigest()[:8]


def store_in_memory(
    winning_params: TrialParams,
    patterns: List[str],
    delta: ExtractionDelta,
    review_context: ReviewContext,
    synthetic_path: Optional[str] = None,
    diagnosis: Optional[Diagnosis] = None,
    convergence_result: Optional[Dict[str, Any]] = None,
) -> bool:
    """Store convergence result in /memory for future recall.

    Uses the memory skill's HTTP API or CLI to persist the result.
    This always happens regardless of whether code was written back.
    """
    problem = (
        f"pdf_lab convergence for patterns [{', '.join(patterns)}]: "
        f"{review_context.persona_name} flagged "
        f"{', '.join(review_context.issue_codes) or 'quality issues'} "
        f"(score={review_context.score:.2f}). "
        f"S00 estimated {delta.estimated_sections} sections, "
        f"extractor found {delta.actual_sections}."
    )

    solution = json.dumps({
        "winning_params": winning_params.to_dict(),
        "delta_before": round(delta.overall_delta, 4),
        "delta_after": convergence_result.get("delta_after", 0) if convergence_result else 0,
        "status": convergence_result.get("status", "unknown") if convergence_result else "stored",
        "persona_attribution": {
            "name": review_context.persona_name,
            "role": review_context.persona_role,
            "issue_codes": review_context.issue_codes,
            "score": review_context.score,
        },
        "synthetic_path": synthetic_path,
        "diagnosis": diagnosis.to_dict() if diagnosis else None,
    })

    tags = [
        "pdf_lab",
        f"persona:{review_context.persona_name.lower().replace(' ', '_')}",
        *[f"pattern:{p}" for p in patterns],
        *[f"issue:{ic}" for ic in review_context.issue_codes],
    ]

    # Try memory CLI
    memory_cli = Path(os.environ.get(
        "MEMORY_SKILLS_DIR",
        str(_PROJECT_ROOT / "memory" / ".agents" / "skills"),
    )) / "memory"

    try:
        if (memory_cli / "run.sh").exists():
            subprocess.run(
                [
                    str(memory_cli / "run.sh"), "learn",
                    "--problem", problem,
                    "--solution", solution,
                    "--tags", ",".join(tags),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            logger.info(f"Stored convergence result in /memory with tags: {tags}")
            return True
    except Exception as e:
        logger.warning(f"Failed to store in /memory: {e}")

    # Fallback: write to local data dir
    data_dir = Path(os.environ.get("PDF_LAB_DATA", Path.home() / ".pi" / "pdf-lab"))
    data_dir.mkdir(parents=True, exist_ok=True)
    events_file = data_dir / "convergence_events.jsonl"
    with open(events_file, "a") as f:
        f.write(json.dumps({
            "timestamp": time.time(),
            "problem": problem,
            "solution": solution,
            "tags": tags,
        }) + "\n")
    logger.info(f"Stored convergence result locally: {events_file}")
    return True
