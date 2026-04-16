"""Collaborative interview gates for /plan.

Pre-plan discovery and post-plan review interviews that force the agent
to read skill code, run real examples, and ask questions BEFORE writing
any YAML. Composes /interview for the UX.

This module exists because plan.py hit the 800-line limit.
"""
from __future__ import annotations
import os

import subprocess
import sys
from pathlib import Path
from typing import Any

from loguru import logger

SKILLS_DIR = Path(__file__).parent.parent

# ---------------------------------------------------------------------------
# Question definitions
# ---------------------------------------------------------------------------

PRE_PLAN_QUESTIONS: list[dict[str, Any]] = [
    {
        "id": "skills_composed",
        "header": "Skills",
        "text": "Which existing skills does this plan compose? List every skill name (e.g. /create-evidence-case, /learn-datalake).",
        "type": "text",
    },
    {
        "id": "code_read",
        "header": "Code Read",
        "text": "For each skill listed above, which .py files have you read? List file paths.",
        "type": "text",
    },
    {
        "id": "real_example",
        "header": "Example",
        "text": "Run one real example of the primary skill and paste the output (or key excerpt).",
        "type": "text",
    },
    {
        "id": "contracts",
        "header": "Contracts",
        "text": "What is the input/output contract of each skill you are composing?",
        "type": "text",
    },
    {
        "id": "questions",
        "header": "Questions",
        "text": "What questions do you have for the human before writing the plan?",
        "type": "text",
    },
]

POST_PLAN_QUESTIONS: list[dict[str, Any]] = [
    {
        "id": "plan_approval",
        "header": "Approve",
        "text": "The plan YAML has been written. Review and decide:",
        "options": [
            {"label": "Approve — proceed to /orchestrate", "description": "Plan is correct, execute it"},
            {"label": "Amend — I have changes", "description": "Edit tasks before executing"},
            {"label": "Reject — start over", "description": "Plan is fundamentally wrong"},
        ],
    },
    {
        "id": "run_review_plan",
        "header": "Review",
        "text": "Run /review-plan for formal validation?",
        "options": [
            {"label": "Yes — run /review-plan", "description": "Full validation: claims, routing, blind tests, overlap"},
            {"label": "No — skip formal review", "description": "Pre-plan interview covered enough"},
        ],
    },
    {
        "id": "generate_diagram",
        "header": "Diagram",
        "text": "Generate a visual diagram of the plan?",
        "options": [
            {"label": "Mermaid DAG", "description": "Generate Mermaid flowchart showing task dependencies and waves"},
            {"label": "/create-walkthrough", "description": "Generate a full argumentative walkthrough with Mermaid diagrams and structured tables"},
            {"label": "Both", "description": "Mermaid DAG + full walkthrough"},
            {"label": "Skip", "description": "No diagram needed"},
        ],
    },
    {
        "id": "amendments",
        "header": "Amend",
        "text": "Any tasks to add, remove, or change? (Leave blank if none)",
        "type": "text",
    },
]


# ---------------------------------------------------------------------------
# Interview runners
# ---------------------------------------------------------------------------

def run_pre_plan_interview(goal: str, plan_type: str) -> dict | None:
    """Run the pre-plan discovery interview. BLOCKING.

    Forces the agent to read skill code, run real examples, and ask
    questions BEFORE writing any YAML. Returns interview result or
    None if /interview is unavailable.
    """
    try:
        interview_skill = SKILLS_DIR / "interview"
        if not interview_skill.exists():
            logger.warning("/interview skill not found — skipping pre-plan interview")
            return None

        sys.path.insert(0, str(interview_skill.parent))
        from interview import Interview, Question

        questions = [Question(**q) for q in PRE_PLAN_QUESTIONS]
        iv = Interview(
            title=f"Plan Discovery: {goal[:60]}",
            context=f"Goal: {goal}\nPlan type: {plan_type}\n\nAnswer these questions BEFORE writing any YAML.",
        )
        return iv.run(questions, mode="auto", timeout=900)
    except Exception as exc:
        logger.warning("Pre-plan interview failed: {} — proceeding without", exc)
        return None


def run_post_plan_interview(plan_path: Path) -> dict | None:
    """Run the post-plan review interview. BLOCKING.

    Presents the plan to the human for approval. Optionally runs
    /review-plan if the human chooses. Returns interview result or None.
    """
    try:
        interview_skill = SKILLS_DIR / "interview"
        if not interview_skill.exists():
            return None

        sys.path.insert(0, str(interview_skill.parent))
        from interview import Interview, Question

        questions = [Question(**q) for q in POST_PLAN_QUESTIONS]
        iv = Interview(
            title=f"Plan Review: {plan_path.name}",
            context=f"Plan written to {plan_path}. Review before execution.",
        )
        result = iv.run(questions, mode="auto", timeout=600)

        responses = result.get("responses", {})

        # If human chose to run /review-plan, do it
        review_choice = responses.get("run_review_plan", {}).get("value", "")
        if "Yes" in str(review_choice):
            review_plan_skill = SKILLS_DIR / "review-plan" / "run.sh"
            if review_plan_skill.exists():
                print("\n── Running /review-plan ──")
                subprocess.run(
                    [str(review_plan_skill), "review", str(plan_path)],
                    capture_output=False, text=True, timeout=120,
                    env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
                )

        # If human chose to generate a diagram, do it
        diagram_choice = responses.get("generate_diagram", {}).get("value", "")
        if "Mermaid" in str(diagram_choice) or "Both" in str(diagram_choice):
            print("\n── Mermaid DAG ──")
            plan_py = Path(__file__).parent / "plan.py"
            subprocess.run(
                [sys.executable, str(plan_py), "--mermaid", str(plan_path)],
                capture_output=False, text=True, timeout=30,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
        if "walkthrough" in str(diagram_choice).lower() or "Both" in str(diagram_choice):
            walkthrough_skill = SKILLS_DIR / "create-walkthrough" / "run.sh"
            if walkthrough_skill.exists():
                print("\n── Running /create-walkthrough ──")
                subprocess.run(
                    [str(walkthrough_skill), str(plan_path)],
                    capture_output=False, text=True, timeout=120,
                    env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
                )

        return result
    except Exception as exc:
        logger.warning("Post-plan interview failed: {} — proceeding without", exc)
        return None
