"""Check 9 & 10: Design Board + PNG Evidence enforcement for UI/UX tasks.

Detects tasks that create React/UI components and enforces:
- /create-design-board prerequisite with persona rationale (HTML/CSS → PNG mockup)
- Design convergence loop (designer → critic persona → revise → converge)
- PNG evidence for every pane: mockup PNG + implemented screenshot for /review-design comparison
- Hover states, mouse-over states, animation states must be shown in mockup PNGs
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Re-use Finding from the main module — import at call time to avoid circular
# We accept the same dict shape as other checkers: task dict with body/title/line/name


@dataclass
class Finding:
    """Mirror of review_plan.Finding for standalone use."""
    task: str
    check: str
    grade: str
    message: str
    line: int
    suggestion: str = ""


# Keywords that indicate a task creates UI components
_UI_KEYWORDS = re.compile(
    r"\b(react\s+component|\.tsx|component|view|editor|dashboard|panel|page|"
    r"visualiz|chart|waveform|piano\s*roll|sidebar|toolbar|modal|dialog|"
    r"ux-lab|ux.lab|ui\s+component)\b",
    re.IGNORECASE,
)

# Patterns proving design board compliance
_BOARD_PATTERNS = re.compile(
    r"(create-design-board|design\s+board|Steve.*persona|Steve.*Schoger|"
    r"persona.*rationale|design.*convergence|review-design.*--persona|"
    r"PREREQUISITE.*design\s+board)",
    re.IGNORECASE,
)

# Patterns for persona-driven design convergence loop
_LOOP_PATTERNS = re.compile(
    r"(convergence|self-improvement\s+loop|Steve.*critique|Nico.*critique|"
    r"persona.*review.*iterate|review-design.*converge|round.*tracking|"
    r"side-by-side\s+comparison|rationale.*first\s+person)",
    re.IGNORECASE,
)

# Patterns for PNG evidence
_PNG_PATTERNS = re.compile(
    r"(PNG\s+evidence|headless\s+chrome\s+screenshot|screenshot.*\.png|"
    r"captures/.*\.png|implemented\.png|mockup\.png|HTML/CSS.*PNG|"
    r"html/css.*png|hover\s+state|mouse-over\s+state|animation\s+state)",
    re.IGNORECASE,
)


# Backend patterns that exclude a task from UI checks even if it mentions "endpoint"
_BACKEND_EXCLUDE = re.compile(
    r"\b(express\s+server|api\s+endpoint|POST\s+/api|GET\s+/api|"
    r"server/index\.ts|backend|proxyPost|httpx|fastapi|flask)\b",
    re.IGNORECASE,
)

# Small UI change patterns — skip design board for minor additions
_SMALL_CHANGE = re.compile(
    r"\b(add\s+button|small\s+ui|small\s+change|minor\s+addition|"
    r"add\s+.*button\s+to|extend\s+with)\b",
    re.IGNORECASE,
)

# Pattern reuse — skip design board when following existing component patterns
# (e.g., "same pattern as RecallCard", "reuse GateChain pattern", "follows existing")
# Also skip when using /scillm Gemini for design review (new workflow replaces mockup-lab)
_PATTERN_REUSE = re.compile(
    r"\b(same\s+pattern\s+as|reuse\s+.*pattern|follow.*pattern|"
    r"pattern\s+from|copy.*styling\s+from|match.*style|"
    r"follows\s+existing|existing\s+pattern|scillm.*gemini.*review|"
    r"gemini.*vlm.*review|vlm.*verification)\b",
    re.IGNORECASE,
)


def _is_ui_task(combined: str) -> bool:
    if not _UI_KEYWORDS.search(combined):
        return False
    # Backend-only tasks that happen to mention UI keywords are not UI tasks
    if _BACKEND_EXCLUDE.search(combined) and not re.search(r"\.(tsx|jsx)\b", combined, re.I):
        return False
    return True


def check_design_board(task: dict, findings: list):
    """Check 9: UI tasks must have /create-design-board prerequisite with
    persona rationale and a design convergence loop.

    Small changes (add button, minor addition) skip design board per /plan rules:
    'For small changes (colors, spacing, adding a column), skip step 1 and use
    /ux-lab + /review-design directly.'
    """
    body = task.get("body", "")
    title = task.get("title", "")
    combined = f"{title}\n{body}"
    line = task.get("line", 0)
    name = task.get("name", title[:60])

    if not _is_ui_task(combined):
        return

    # Small UI changes skip design board (per /plan rules)
    if _SMALL_CHANGE.search(combined):
        return

    # Pattern reuse skips design board — component follows existing pattern
    # or uses /scillm Gemini for design review (replaces mockup-lab workflow)
    if _PATTERN_REUSE.search(combined):
        return

    has_board = bool(_BOARD_PATTERNS.search(combined))
    has_loop = bool(_LOOP_PATTERNS.search(combined))

    if not has_board:
        findings.append(Finding(
            task=name,
            check="design-board",
            grade="FAIL",
            message=(
                "UI component task has no /create-design-board prerequisite. "
                "Every pane/component needs an HTML/CSS → PNG mockup designed by "
                "a persona (e.g. Steve Schoger) BEFORE implementation begins."
            ),
            line=line,
            suggestion=(
                "Add PREREQUISITE: /create-design-board with --persona for this "
                "component. Include persona rationale in first person. Gate: PNG "
                "mockup exists with hover states, color tokens, and animation states."
            ),
        ))
    elif not has_loop:
        findings.append(Finding(
            task=name,
            check="design-board",
            grade="WARN",
            message=(
                "UI task references /create-design-board but no design convergence "
                "loop (designer → critic persona → revise → re-review → converge). "
                "One-shot design without critique is insufficient."
            ),
            line=line,
            suggestion=(
                "Add a design convergence loop: designer persona creates mockup, "
                "critic persona (e.g. Nico) reviews via /review-design --persona, "
                "designer revises, iterate until 0 high-severity findings."
            ),
        ))


def check_png_evidence(task: dict, findings: list):
    """Check 10: UI tasks must require PNG screenshots as evidence —
    HTML/CSS mockup PNGs showing colors, hover/animation states,
    plus headless Chrome screenshots of implemented components."""
    body = task.get("body", "")
    title = task.get("title", "")
    combined = f"{title}\n{body}"
    line = task.get("line", 0)
    name = task.get("name", title[:60])

    if not _is_ui_task(combined):
        return

    # Small UI changes skip PNG evidence (per /plan rules)
    if _SMALL_CHANGE.search(combined):
        return

    # Pattern reuse skips PNG evidence — component follows existing pattern
    # or uses /scillm Gemini for design review (replaces mockup-lab workflow)
    if _PATTERN_REUSE.search(combined):
        return

    if not _PNG_PATTERNS.search(combined):
        findings.append(Finding(
            task=name,
            check="png-evidence",
            grade="FAIL",
            message=(
                "UI component task has no PNG evidence requirement. Every pane "
                "and component needs an HTML/CSS mockup PNG showing colors, hover "
                "states, and animation states — plus a headless Chrome screenshot "
                "of the implemented component for /review-design comparison."
            ),
            line=line,
            suggestion=(
                "Add: '**PNG evidence**: headless Chrome screenshot → "
                "captures/{component}/implemented.png' to the task. Gate must "
                "include /review-design comparison of mockup PNG vs implemented PNG."
            ),
        ))


# ─── Check 11: Lab Convergence Enforcement (*-lab convergence skills) ────────────

_LAB_KEYWORDS = re.compile(
    r"\b(\w+-lab|convergence\s+loop|self-improv|headless\s+convergence|"
    r"Phase\s+2.*headless|create.*review.*iterate|tune.*converge)\b",
    re.IGNORECASE,
)

_CONVERGENCE_PATTERNS = re.compile(
    r"(code-runner|scillm|isolated\s+context|"
    r"auto-compact|protected\s+context|context\s+isolation)",
    re.IGNORECASE,
)


def check_lab_subagent(task: dict, findings: list):
    """Check 11: *-lab convergence tasks must use /code-runner or /scillm for
    Phase 2 headless iteration — each review dimension gets its own
    isolated context."""
    body = task.get("body", "")
    title = task.get("title", "")
    combined = f"{title}\n{body}"
    line = task.get("line", 0)
    name = task.get("name", title[:60])

    if not _LAB_KEYWORDS.search(combined):
        return

    if not _CONVERGENCE_PATTERNS.search(combined):
        findings.append(Finding(
            task=name,
            check="lab-subagent",
            grade="WARN",
            message=(
                "Convergence/lab task has no /code-runner or /scillm reference. "
                "All *-lab Phase 2 headless convergence loops should use "
                "/code-runner (iterative, writes files) or /scillm (one-shot). "
                "Each quality dimension gets its own focused context."
            ),
            line=line,
            suggestion=(
                "Add /code-runner to the convergence loop spec. Each review "
                "dimension (e.g. lore/voice/craft/structure) runs in its own "
                "code-runner session. Transcripts persist to JSON."
            ),
        ))
