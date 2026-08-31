"""Fail-closed visual gate for SVG work rendered at its target size.

This module does not pretend to score aesthetics automatically. It enforces the
contract that a visual SVG task cannot close unless a real rendered screenshot is
present and a reviewer verdict explicitly says the artifact both represents the
stated goal and is attractive at the target size.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class VisualVerdict(BaseModel):
    """Reviewer decision over the rendered target screenshot."""

    model_config = ConfigDict(extra="forbid")

    screenshot_sha256: str
    inspected_screenshot_path: str
    reviewer: str
    represents_goal: bool
    attractive: bool
    issues: list[str] = Field(default_factory=list)
    next_edit: str = ""


class VisualGateReceipt(BaseModel):
    """Receipt consumed by ticket/watchdog loops before a visual task can close."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["create_svg.visual_gate.v1"] = "create_svg.visual_gate.v1"
    status: Literal["PASS", "NOT_READY"]
    svg_path: str
    svg_sha256: str
    screenshot_path: str
    screenshot_sha256: str
    target: str
    target_size: str
    goal: str
    represents_goal: bool
    attractive: bool
    issues: list[str]
    next_edit: str
    proof_scope: str
    does_not_prove: str


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate_visual_gate(
    *,
    svg: Path,
    screenshot: Path,
    target: str,
    target_size: str,
    goal: str,
    verdict: VisualVerdict,
) -> VisualGateReceipt:
    """Build a fail-closed receipt for one rendered SVG screenshot."""

    svg = svg.resolve()
    screenshot = screenshot.resolve()
    if not svg.exists() or not svg.is_file():
        raise FileNotFoundError(f"svg not found: {svg}")
    if not screenshot.exists() or not screenshot.is_file():
        raise FileNotFoundError(f"screenshot not found: {screenshot}")

    observed_screenshot_sha256 = _sha256(screenshot)
    if verdict.screenshot_sha256 != observed_screenshot_sha256:
        raise ValueError(
            "reviewer verdict screenshot_sha256 does not match rendered screenshot; "
            f"expected {observed_screenshot_sha256}, got {verdict.screenshot_sha256}"
        )
    if str(Path(verdict.inspected_screenshot_path).resolve()) != str(screenshot):
        raise ValueError("reviewer verdict inspected_screenshot_path does not match rendered screenshot path")
    if not verdict.reviewer.strip():
        raise ValueError("reviewer is required")

    issues = list(verdict.issues)
    if not verdict.represents_goal and not any("represent" in issue.lower() for issue in issues):
        issues.append("does not yet clearly represent the goal")
    if not verdict.attractive and not any("attractive" in issue.lower() or "visual" in issue.lower() for issue in issues):
        issues.append("not yet attractive at target size")

    status: Literal["PASS", "NOT_READY"] = "PASS" if verdict.represents_goal and verdict.attractive else "NOT_READY"
    return VisualGateReceipt(
        status=status,
        svg_path=str(svg),
        svg_sha256=_sha256(svg),
        screenshot_path=str(screenshot),
        screenshot_sha256=observed_screenshot_sha256,
        target=target,
        target_size=target_size,
        goal=goal,
        represents_goal=verdict.represents_goal,
        attractive=verdict.attractive,
        issues=issues,
        next_edit=verdict.next_edit,
        proof_scope="A real rendered screenshot was inspected for goal representation and visual quality at the named target size.",
        does_not_prove="The SVG is safe, deterministic, deployed, or universally attractive to every viewer; run validate/verify and deployment checks separately.",
    )
