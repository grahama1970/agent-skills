"""Interactive human-in-the-loop escalation for pdf-lab convergence.

When the convergence loop is stuck (no improvement, ambiguous diagnosis,
or extraction errors), this module escalates to the human for guidance
via the /interview and /pdf-screenshot skills.

The human can:
- Confirm or override the detected patterns
- Guide parameter direction (e.g., "tables have thin lines, try lower line_scale")
- Mark the diagnosis as wrong (e.g., "S00 is right, extractor is wrong")
- Skip tuning entirely ("this PDF is fine, no issues")
- Provide free-text hints incorporated into correction context
- Draw/edit bounding boxes on rendered PDF pages
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from .delta import ExtractionDelta, Diagnosis


# Skill paths (configurable via env)
_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent
INTERVIEW_SKILL = Path(os.environ.get(
    "INTERVIEW_SKILL_DIR",
    str(_SKILLS_DIR / "interview"),
))
PDF_SCREENSHOT_SKILL = Path(os.environ.get(
    "PDF_SCREENSHOT_SKILL_DIR",
    str(_SKILLS_DIR / "pdf-screenshot"),
))

# Escalation thresholds
STALL_ITERATIONS = 2  # Escalate after N iterations with no improvement
MIN_DELTA_IMPROVEMENT = 0.02  # Less than this counts as "stalled"


@dataclass
class HumanGuidance:
    """Result of human escalation -- guidance for the convergence loop."""

    escalated: bool = False  # Whether escalation actually happened
    skip_tuning: bool = False  # Human says "stop, this is fine"
    pattern_overrides: List[str] = field(default_factory=list)  # Replace detected patterns
    parameter_hints: Dict[str, Any] = field(default_factory=dict)  # Hints for param search
    free_text: str = ""  # Free-form guidance from human
    diagnosis_wrong: bool = False  # Human says diagnosis is incorrect
    confirmed_patterns: bool = False  # Human confirmed patterns are correct
    bbox_corrections: List[Dict[str, Any]] = field(default_factory=list)  # Annotated regions from bbox pane

    def to_dict(self) -> Dict[str, Any]:
        return {
            "escalated": self.escalated,
            "skip_tuning": self.skip_tuning,
            "pattern_overrides": self.pattern_overrides,
            "parameter_hints": self.parameter_hints,
            "free_text": self.free_text,
            "diagnosis_wrong": self.diagnosis_wrong,
            "confirmed_patterns": self.confirmed_patterns,
            "bbox_corrections": self.bbox_corrections,
        }


def should_escalate(
    iteration: int,
    best_delta: float,
    current_delta: float,
    delta_history: List[float],
    consecutive_errors: int,
    diagnosis: Diagnosis,
) -> bool:
    """Decide whether to escalate to the human.

    Triggers:
    - 2+ iterations with no meaningful improvement
    - Ambiguous diagnosis (no patterns detected despite low delta)
    - 2+ consecutive extraction errors (infrastructure vs PDF issue?)
    """
    # No patterns detected but delta is low -- ambiguous
    if not diagnosis.patterns and len(delta_history) >= 1:
        logger.info("Escalation trigger: no patterns detected despite quality issues")
        return True

    # Stalled: no improvement for STALL_ITERATIONS
    if len(delta_history) >= STALL_ITERATIONS:
        recent = delta_history[-STALL_ITERATIONS:]
        max_recent = max(recent)
        min_recent = min(recent)
        if max_recent - min_recent < MIN_DELTA_IMPROVEMENT:
            logger.info(
                f"Escalation trigger: stalled for {STALL_ITERATIONS} iterations "
                f"(delta range: {min_recent:.3f}-{max_recent:.3f})"
            )
            return True

    # Consecutive errors -- is this an infrastructure problem?
    if consecutive_errors >= 2:
        logger.info(f"Escalation trigger: {consecutive_errors} consecutive extraction errors")
        return True

    return False


def escalate_to_human(
    pdf_path: Path,
    delta: ExtractionDelta,
    diagnosis: Diagnosis,
    trials_so_far: List[Dict[str, Any]],
    iteration: int,
    max_iterations: int,
    consecutive_errors: int = 0,
) -> HumanGuidance:
    """Escalate to the human for guidance via /interview + /pdf-screenshot.

    Returns HumanGuidance that the convergence loop incorporates.
    If skills are unavailable, returns a no-op guidance (escalated=False).
    """
    interview_run = INTERVIEW_SKILL / "run.sh"
    screenshot_run = PDF_SCREENSHOT_SKILL / "run.sh"

    if not interview_run.exists():
        logger.warning(f"Interview skill not found at {INTERVIEW_SKILL}. Skipping escalation.")
        return HumanGuidance(escalated=False)

    # Step 1: Generate PDF screenshots for visual context
    screenshots = capture_screenshots(pdf_path, screenshot_run)

    # Step 2: Build interview questions
    questions = build_questions(
        pdf_path=pdf_path,
        delta=delta,
        diagnosis=diagnosis,
        trials_so_far=trials_so_far,
        iteration=iteration,
        max_iterations=max_iterations,
        consecutive_errors=consecutive_errors,
        screenshots=screenshots,
    )

    # Step 3: Run interview
    try:
        responses = _run_interview(questions, interview_run)
    except Exception as e:
        logger.warning(f"Interview failed: {e}. Continuing without human input.")
        return HumanGuidance(escalated=False)

    if not responses:
        return HumanGuidance(escalated=False)

    # Step 4: Parse responses into guidance
    guidance = parse_responses(responses, diagnosis)
    guidance.escalated = True

    logger.info(
        f"Human guidance received: skip={guidance.skip_tuning}, "
        f"overrides={guidance.pattern_overrides}, "
        f"diagnosis_wrong={guidance.diagnosis_wrong}"
    )

    return guidance


def capture_screenshots(pdf_path: Path, screenshot_run: Path) -> List[str]:
    """Capture first page and a middle page as PNGs for the interview."""
    screenshots: List[str] = []

    if not screenshot_run.exists() or not pdf_path.exists():
        return screenshots

    tmpdir = Path(tempfile.mkdtemp(prefix="pdf_lab_screenshots_"))

    # Always capture page 0 (first page)
    try:
        out_path = tmpdir / f"{pdf_path.stem}_page0.png"
        result = subprocess.run(
            [str(screenshot_run), str(pdf_path), "--page", "0", "--out", str(out_path)],
            capture_output=True,
            text=True,
            timeout=30,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode == 0 and out_path.exists():
            screenshots.append(str(out_path))
    except Exception as e:
        logger.debug(f"Screenshot page 0 failed: {e}")

    # Try to capture a middle page (page 2 or 3) for more context
    for page_num in [2, 3, 1]:
        try:
            out_path = tmpdir / f"{pdf_path.stem}_page{page_num}.png"
            result = subprocess.run(
                [str(screenshot_run), str(pdf_path), "--page", str(page_num), "--out", str(out_path)],
                capture_output=True,
                text=True,
                timeout=30,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            if result.returncode == 0 and out_path.exists():
                screenshots.append(str(out_path))
                break
        except Exception:
            continue

    return screenshots


def build_questions(
    pdf_path: Path,
    delta: ExtractionDelta,
    diagnosis: Diagnosis,
    trials_so_far: List[Dict[str, Any]],
    iteration: int,
    max_iterations: int,
    consecutive_errors: int,
    screenshots: List[str],
) -> Dict[str, Any]:
    """Build the interview questions JSON structure."""
    context_lines = [
        f"PDF: {pdf_path.name}",
        f"Iteration: {iteration}/{max_iterations}",
        f"Current delta: {delta.overall_delta:.2f} (1.0 = perfect)",
        f"Sections: {delta.actual_sections}/{delta.estimated_sections} (delta={delta.section_delta:.2f})",
        f"Tables: {delta.actual_tables}/{delta.estimated_tables} (delta={delta.table_delta:.2f})",
        f"Figures: {delta.actual_figures}/{delta.estimated_figures} (delta={delta.figure_delta:.2f})",
    ]

    if diagnosis.patterns:
        context_lines.append(f"Detected patterns: {', '.join(diagnosis.patterns)}")
    if diagnosis.root_cause:
        context_lines.append(f"Root cause: {diagnosis.root_cause}")
    if diagnosis.s00_overestimated:
        context_lines.append("NOTE: S00 appears to be overestimating section count")
    if consecutive_errors > 0:
        context_lines.append(f"Extraction errors: {consecutive_errors} consecutive failures")

    if trials_so_far:
        best_trial = max(trials_so_far, key=lambda t: t.get("delta", {}).get("overall_delta", 0))
        best_delta_val = best_trial.get("delta", {}).get("overall_delta", 0)
        context_lines.append(f"Best trial so far: delta={best_delta_val:.2f} (iteration {best_trial.get('iteration', '?')})")

    context = "\n".join(context_lines)

    questions: List[Dict[str, Any]] = []

    # Q1: Overall assessment with screenshots
    q1: Dict[str, Any] = {
        "id": "assessment",
        "header": "Assessment",
        "text": (
            "pdf-lab is stuck trying to improve extraction quality for this PDF. "
            "Looking at the document, what's the main issue?"
        ),
        "options": [
            {"label": "Extraction is fine", "description": "The PDF looks correctly extracted. S00 estimates may be wrong."},
            {"label": "Missing sections", "description": "There are section headers the extractor is not detecting."},
            {"label": "Missing tables", "description": "There are tables the extractor is not finding."},
            {"label": "False positives", "description": "The extractor is finding things that aren't really sections/tables."},
            {"label": "Layout issue", "description": "Multi-column, scanned, or unusual layout causing problems."},
        ],
        "multi_select": False,
    }
    if screenshots:
        q1["images"] = screenshots
    questions.append(q1)

    # Q2: Pattern confirmation (only if patterns detected)
    if diagnosis.patterns:
        q2: Dict[str, Any] = {
            "id": "patterns",
            "header": "Patterns",
            "text": (
                f"pdf-lab detected these patterns: {', '.join(diagnosis.patterns)}. "
                "Are these correct?"
            ),
            "options": [
                {"label": "Correct", "description": "The detected patterns match what I see in the PDF."},
                {"label": "Partially correct", "description": "Some patterns are right, but the diagnosis is incomplete."},
                {"label": "Wrong", "description": "The patterns don't match the actual issues."},
            ],
            "multi_select": False,
        }
        questions.append(q2)

    # Q3: Direction hint
    q3: Dict[str, Any] = {
        "id": "direction",
        "header": "Direction",
        "text": "What should pdf-lab try next?",
        "options": [
            {"label": "Continue tuning", "description": "Keep trying different parameters (more iterations)."},
            {"label": "Try different patterns", "description": "The current patterns are wrong -- try a different diagnosis."},
            {"label": "Stop tuning", "description": "This PDF doesn't need tuning. Accept current extraction."},
            {"label": "Skip this PDF", "description": "This PDF is too problematic. Move on."},
        ],
        "multi_select": False,
    }
    questions.append(q3)

    # Bbox annotation questions (one per screenshot page)
    bbox_qs = _build_bbox_questions(delta, diagnosis, screenshots)
    questions.extend(bbox_qs)

    # Q4: Free-text hint (always included)
    q4: Dict[str, Any] = {
        "id": "hint",
        "header": "Hint",
        "text": (
            "Any specific guidance? (e.g., 'tables have very thin lines', "
            "'headers are in 9pt font', 'this is a 2-column layout')"
        ),
        "options": [
            {"label": "No hint", "description": "I don't have specific guidance."},
            {"label": "Table hint", "description": "The tables have specific characteristics (line weight, borders, etc.)."},
            {"label": "Section hint", "description": "The sections have specific formatting (font size, numbering, etc.)."},
        ],
        "multi_select": False,
    }
    questions.append(q4)

    return {
        "title": "pdf-lab: Human Guidance Needed",
        "context": context,
        "questions": questions,
    }


def _run_interview(questions: Dict[str, Any], interview_run: Path) -> Optional[Dict[str, Any]]:
    """Run the /interview skill and return parsed responses."""
    # Write questions to temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", prefix="pdf_lab_interview_", delete=False
    ) as f:
        json.dump(questions, f, indent=2)
        questions_path = f.name

    try:
        result = subprocess.run(
            [str(interview_run), "--file", questions_path, "--json", "--timeout", "300"],
            capture_output=True,
            text=True,
            timeout=330,  # slightly more than interview timeout
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )

        if result.returncode != 0:
            logger.warning(f"Interview exited with code {result.returncode}: {result.stderr}")
            return None

        # Parse JSON output
        output = result.stdout.strip()
        if not output:
            return None

        data = json.loads(output)
        return data.get("responses", {})

    except subprocess.TimeoutExpired:
        logger.warning("Interview timed out (5 min)")
        return None
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse interview output: {e}")
        return None
    finally:
        try:
            Path(questions_path).unlink(missing_ok=True)
        except Exception as e:
            logger.debug("path resolution failed: {}", e)


def parse_responses(
    responses: Dict[str, Any],
    diagnosis: Diagnosis,
) -> HumanGuidance:
    """Parse interview responses into actionable guidance."""
    guidance = HumanGuidance()

    # Parse assessment response
    assessment = responses.get("assessment", {})
    assessment_value = assessment.get("value", "")
    assessment_other = assessment.get("other_text", "")

    if assessment_value == "Extraction is fine":
        guidance.skip_tuning = True
        guidance.diagnosis_wrong = True
    elif assessment_value == "Missing sections":
        if "section_undersegmentation" not in diagnosis.patterns:
            guidance.pattern_overrides = list(diagnosis.patterns) + ["section_undersegmentation"]
    elif assessment_value == "Missing tables":
        if "missed_tables" not in diagnosis.patterns:
            guidance.pattern_overrides = list(diagnosis.patterns) + ["missed_tables"]
    elif assessment_value == "False positives":
        override_patterns = []
        if "false_positive_tables" not in diagnosis.patterns:
            override_patterns.append("false_positive_tables")
        if "section_oversegmentation" not in diagnosis.patterns:
            override_patterns.append("section_oversegmentation")
        guidance.pattern_overrides = override_patterns
    elif assessment_value == "Layout issue":
        if "multi_column" not in diagnosis.patterns:
            guidance.pattern_overrides = list(diagnosis.patterns) + ["multi_column"]

    if assessment_other:
        guidance.free_text = assessment_other

    # Parse pattern confirmation
    patterns_resp = responses.get("patterns", {})
    patterns_value = patterns_resp.get("value", "")
    if patterns_value == "Correct":
        guidance.confirmed_patterns = True
    elif patterns_value == "Wrong":
        guidance.diagnosis_wrong = True

    # Parse direction
    direction = responses.get("direction", {})
    direction_value = direction.get("value", "")
    if direction_value in ("Stop tuning", "Skip this PDF"):
        guidance.skip_tuning = True
    elif direction_value == "Try different patterns":
        guidance.diagnosis_wrong = True

    # Parse hint
    hint = responses.get("hint", {})
    hint_value = hint.get("value", "")
    hint_other = hint.get("other_text", "")

    if hint_other:
        # Free-text hint from "Other" option
        guidance.free_text = (guidance.free_text + " " + hint_other).strip()
        guidance.parameter_hints.update(_parse_hint_text(hint_other))
    elif hint_value == "Table hint":
        guidance.parameter_hints["focus_tables"] = True
    elif hint_value == "Section hint":
        guidance.parameter_hints["focus_sections"] = True

    # Parse bbox annotation responses
    guidance.bbox_corrections = _parse_bbox_responses(responses)

    return guidance


def _parse_hint_text(text: str) -> Dict[str, Any]:
    """Extract parameter hints from free-text human input.

    Simple keyword matching -- not trying to be clever,
    just looking for common patterns humans might mention.
    """
    hints: Dict[str, Any] = {}
    lower = text.lower()

    # Table-related hints
    if "thin line" in lower or "thin border" in lower or "light line" in lower:
        hints["try_lower_line_scale"] = True
    if "no border" in lower or "borderless" in lower:
        hints["try_stream_flavor"] = True
    if "thick line" in lower or "heavy border" in lower:
        hints["try_higher_line_scale"] = True

    # Section-related hints
    if "small font" in lower or "small header" in lower:
        hints["try_lower_font_threshold"] = True
    if "large font" in lower or "big header" in lower:
        hints["try_higher_font_threshold"] = True

    # Layout hints
    if "2 column" in lower or "two column" in lower or "2-column" in lower:
        hints["multi_column"] = True
    if "scanned" in lower or "scan" in lower:
        hints["scanned"] = True

    # Numbering hints
    if "roman" in lower or "numbering" in lower:
        hints["numbering_issue"] = True

    return hints


def _pdf_to_pixel(coord: float, render_dpi: int = 150) -> float:
    """Convert a PDF coordinate (72 DPI) to image pixel coordinate."""
    return coord * (render_dpi / 72.0)


def _pixel_to_pdf(coord: float, render_dpi: int = 150) -> float:
    """Convert an image pixel coordinate back to PDF coordinate (72 DPI)."""
    return coord * (72.0 / render_dpi)


def _build_bbox_questions(
    delta: ExtractionDelta,
    diagnosis: Diagnosis,
    screenshots: List[str],
    render_dpi: int = 150,
) -> List[Dict[str, Any]]:
    """Build bbox_annotation questions with pre-annotations from diagnosis.

    Uses S02 blocks (sections) and S05 tables (tables) to populate
    pre-annotations that the human can edit, delete, or add to.
    """
    questions: List[Dict[str, Any]] = []

    if not screenshots:
        return questions

    # Build pre-annotations from diagnosis blocks
    pre_annotations: List[Dict[str, Any]] = []

    # Add section blocks from diagnosis (if available)
    for block in getattr(diagnosis, "blocks", []):
        block_type = block.get("type", "Section")
        bbox = block.get("bbox")
        page = block.get("page", 0)
        if bbox and len(bbox) == 4:
            pre_annotations.append({
                "type": block_type,
                "bbox": [_pdf_to_pixel(c, render_dpi) for c in bbox],
                "page": page,
            })

    # Add table blocks from diagnosis (if available)
    for table in getattr(diagnosis, "tables", []):
        bbox = table.get("bbox")
        page = table.get("page", 0)
        if bbox and len(bbox) == 4:
            pre_annotations.append({
                "type": "Table",
                "bbox": [_pdf_to_pixel(c, render_dpi) for c in bbox],
                "page": page,
            })

    # Create one bbox question per screenshot (page)
    for i, screenshot in enumerate(screenshots):
        page_annotations = [a for a in pre_annotations if a.get("page", 0) == i]
        q: Dict[str, Any] = {
            "id": f"bbox_page_{i}",
            "header": f"Page {i}",
            "type": "bbox_annotation",
            "text": (
                f"Annotate page {i}: draw bounding boxes around missed tables or sections, "
                "delete false positives, or re-label elements."
            ),
            "images": [screenshot],
            "bbox_labels": [
                {"name": "Table", "color": "#22c55e"},
                {"name": "Section", "color": "#3b82f6"},
                {"name": "Figure", "color": "#f59e0b"},
                {"name": "Delete", "color": "#ef4444"},
            ],
            "pre_annotations": page_annotations,
            "render_dpi": render_dpi,
            "page_num": i,
        }
        questions.append(q)

    return questions


def _parse_bbox_responses(
    responses: Dict[str, Any],
    render_dpi: int = 150,
) -> List[Dict[str, Any]]:
    """Convert pixel-space bbox annotations back to PDF coordinates.

    Returns a list of correction dicts with action/type/bbox/page in PDF space.
    """
    corrections: List[Dict[str, Any]] = []

    for key, resp in responses.items():
        if not key.startswith("bbox_page_"):
            continue

        annotations = resp.get("annotations", [])
        resp_dpi = resp.get("render_dpi", render_dpi)

        for ann in annotations:
            pixel_bbox = ann.get("bbox", [0, 0, 0, 0])
            pdf_bbox = [_pixel_to_pdf(c, resp_dpi) for c in pixel_bbox]
            corrections.append({
                "action": ann.get("action", "keep"),
                "type": ann.get("type", "?"),
                "bbox": [round(c, 1) for c in pdf_bbox],
                "page": ann.get("page", 0),
            })

    return corrections


def apply_human_guidance(
    guidance: HumanGuidance,
    current_patterns: List[str],
    correction_context: Dict[str, Any],
) -> tuple[List[str], Dict[str, Any]]:
    """Apply human guidance to patterns and correction context.

    Returns updated (patterns, correction_context) for the next iteration.
    """
    patterns = list(current_patterns)
    ctx = dict(correction_context)

    # Override patterns if human provided them
    if guidance.pattern_overrides:
        patterns = guidance.pattern_overrides
        logger.info(f"Patterns overridden by human: {patterns}")

    # Apply parameter hints to correction context
    hints = guidance.parameter_hints

    if hints.get("try_lower_line_scale"):
        ctx["table_undercount"] = True
    if hints.get("try_higher_line_scale"):
        ctx["table_overcount"] = True
    if hints.get("try_lower_font_threshold"):
        ctx["section_undercount"] = True
    if hints.get("try_higher_font_threshold"):
        ctx["section_overcount"] = True
    if hints.get("focus_tables"):
        ctx["table_undercount"] = True
    if hints.get("focus_sections"):
        ctx["section_undercount"] = True
    if hints.get("multi_column"):
        if "multi_column" not in patterns:
            patterns.append("multi_column")
    if hints.get("scanned"):
        if "scanned_no_ocr" not in patterns:
            patterns.append("scanned_no_ocr")

    # Apply bbox corrections to correction context
    if guidance.bbox_corrections:
        ctx["annotated_regions"] = guidance.bbox_corrections

    return patterns, ctx


def _count_lines(path: Path) -> int:
    """Count non-empty lines in a file."""
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text().split("\n") if line.strip())
