"""
Design pipeline auto-detection and validation for /plan.

Detects whether a plan goal involves UI/design work and enforces the
sequential design pipeline:
  /ux-lab → /review-design → /test-interactions → production-write

Each step MUST be a separate task in a separate Parallel group.
If /review-design or /test-interactions FAILS, the plan must loop
back to /ux-lab — never proceed to production-write.
"""

from __future__ import annotations

import re


# Keywords that signal UI/design work in a plan goal
_UI_KEYWORDS = {
    "view", "views", "component", "components", "tsx", "jsx", "react",
    "dashboard", "redesign", "rewrite", "ui", "ux", "interface", "panel",
    "tab", "tabs", "layout", "widget", "modal", "dialog", "sidebar",
    "toolbar", "overlay", "workbench", "viewer", "renderer", "screen",
    "page", "form", "table view", "list view", "grid view",
}

# Patterns that strongly indicate design work
_UI_PATTERNS = [
    r"\bview\b",
    r"\bcomponent\b",
    r"\b\.tsx\b",
    r"\breact\b",
    r"\bdashboard\b",
    r"\bredesign\b",
    r"\bui\b",
    r"\bux\b",
    r"\btailwind\b",
    r"\bshadcn\b",
]

_CODE_KEYWORDS = {
    "api", "pipeline", "migration", "refactor", "extract", "parse",
    "rust", "python", "cli", "backend", "database", "schema",
}


def detect_plan_type(goal: str) -> str:
    """
    Auto-detect plan type from goal text.

    Returns:
        "design" — UI/visual work requiring /ux-lab → /review-design → /test-interactions pipeline
        "code"   — pure code/infra work (no visual output)
        "hybrid" — mix of both; design pipeline required for UI tasks
    """
    goal_lower = goal.lower()

    ui_hits = sum(1 for kw in _UI_KEYWORDS if kw in goal_lower)
    ui_pattern_hits = sum(1 for p in _UI_PATTERNS if re.search(p, goal_lower))

    if ui_hits >= 3 or ui_pattern_hits >= 2:
        return "design"

    code_hits = sum(1 for kw in _CODE_KEYWORDS if kw in goal_lower)

    if ui_hits >= 1 and code_hits >= 1:
        return "hybrid"

    if ui_hits >= 1:
        return "design"

    return "code"


def validate_design_pipeline(content: str) -> list[str]:
    """
    Validate that a design-type plan enforces the sequential design pipeline.

    Returns list of FAIL-grade issues. Empty list = passes.
    """
    issues: list[str] = []

    task_blocks = re.findall(
        r'(?:- \[[ x]\] \*\*(?:Task\s+)?[\d.]+\*\*[^\n]*\n(?:  [^\n]*\n)*)',
        content,
    )

    design_tasks = []
    for block in task_blocks:
        block_lower = block.lower()
        step_type = None
        if "/ux-lab" in block_lower or ("ux-lab" in block_lower and "draft" in block_lower):
            step_type = "ux-lab"
        elif "/review-design" in block_lower:
            step_type = "review-design"
        elif "/test-interactions" in block_lower:
            step_type = "test-interactions"
        elif "production" in block_lower and ("tsx" in block_lower or "write" in block_lower):
            step_type = "production-write"

        if step_type:
            pg_match = re.search(r'Parallel:\s*(\d+)', block)
            parallel_group = int(pg_match.group(1)) if pg_match else None

            dep_match = re.search(r'Dependencies:\s*(.+)', block)
            deps = dep_match.group(1).strip() if dep_match else "none"

            design_tasks.append({
                "type": step_type,
                "parallel_group": parallel_group,
                "dependencies": deps,
                "block": block.strip()[:80],
            })

    if not design_tasks:
        return issues

    # Check 1: Each design step must be a SEPARATE task
    step_types_found = [t["type"] for t in design_tasks]
    for required in ["review-design", "test-interactions"]:
        if required not in step_types_found:
            issues.append(
                f"FAIL: Design pipeline missing /{required} task. "
                f"UI plans MUST include /ux-lab → /review-design → /test-interactions → production-write"
            )

    # Check 2: No two design steps in the same parallel group
    pg_to_types: dict[int | None, list[str]] = {}
    for t in design_tasks:
        pg = t["parallel_group"]
        if pg not in pg_to_types:
            pg_to_types[pg] = []
        pg_to_types[pg].append(t["type"])

    for pg, types in pg_to_types.items():
        if len(types) > 1:
            issues.append(
                f"FAIL: Design pipeline steps {types} share Parallel group {pg}. "
                f"Each step MUST be in a SEPARATE Parallel group to prevent /orchestrate from collapsing them."
            )

    # Check 3: production-write must depend on test-interactions
    for t in design_tasks:
        if t["type"] == "production-write":
            deps_lower = t["dependencies"].lower()
            if "test-interactions" not in deps_lower and deps_lower != "none":
                has_interaction_dep = False
                for other in design_tasks:
                    if other["type"] == "test-interactions":
                        task_id_match = re.search(r'Task\s+([\d.]+)', other["block"])
                        if task_id_match and task_id_match.group(1) in deps_lower:
                            has_interaction_dep = True
                if not has_interaction_dep:
                    issues.append(
                        f"FAIL: Production-write task does not depend on /test-interactions. "
                        f"Production TSX MUST NOT be written until /test-interactions passes."
                    )

    # Check 4: review-design and test-interactions must specify --persona
    for t in design_tasks:
        if t["type"] in ("review-design", "test-interactions"):
            if "--persona" not in t["block"].lower() and "persona" not in t["block"].lower():
                issues.append(
                    f"FAIL: /{t['type']} task does not specify --persona. "
                    f"Design review MUST include persona evaluation."
                )

    return issues


def validate_retrigger_on_failure(content: str) -> list[str]:
    """
    Check that design plans include re-trigger instructions for failed gates.

    /review-design and /test-interactions are BLOCKING gates. If they fail,
    the plan must loop back to /ux-lab, not proceed to production-write.
    """
    warnings: list[str] = []
    content_lower = content.lower()

    has_review = "/review-design" in content_lower
    has_interactions = "/test-interactions" in content_lower

    if has_review or has_interactions:
        retrigger_patterns = [
            r"re-?trigger",
            r"loop\s*back",
            r"iterate.*until.*pass",
            r"retry.*fail",
            r"on\s*fail.*return\s*to",
            r"if.*fail.*re-?run",
            r"max.?retries",
            r"convergence",
            r"on\s*failure",
        ]
        has_retrigger = any(re.search(p, content_lower) for p in retrigger_patterns)
        if not has_retrigger:
            warnings.append(
                "WARN: Design plan has /review-design or /test-interactions but no "
                "re-trigger/retry instructions. If these gates FAIL, the plan should "
                "loop back to /ux-lab for iteration, not proceed to production-write. "
                "Add: 'On failure: re-trigger /ux-lab iteration (max 3 rounds)'"
            )

    return warnings


def design_pipeline_header(plan_type: str) -> list[str]:
    """Generate the design pipeline reminder lines for task file output."""
    if plan_type not in ("design", "hybrid"):
        return []
    return [
        "## Design Pipeline (ENFORCED)",
        "",
        "This plan contains UI work. The following sequential pipeline is **mandatory**:",
        "",
        "1. `/ux-lab` — Write TSX draft in workbench",
        "2. `/review-design --persona <name>` — Playwright screenshots + persona evaluation (**BLOCKING**)",
        "3. `/test-interactions --persona <name>` — Playwright interaction tests (**BLOCKING**)",
        "4. Production TSX — ONLY after steps 2 and 3 pass",
        "",
        "**On failure**: If `/review-design` or `/test-interactions` FAILS, loop back to `/ux-lab`.",
        "Do NOT proceed to production-write. Max 3 iteration rounds per view.",
        "",
    ]
