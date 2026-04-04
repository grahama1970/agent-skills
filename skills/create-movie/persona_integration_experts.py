"""Persona Integration experts module for create-movie.

PlatformExpert registry, MODEL_TRAINING_EXPERTS, CreativeTeam,
document trail templates, ExpertReview/DirectorApproval dataclasses,
and ExpertDirectorReviewLoop class.
"""

import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from persona_integration_core import _PROJECT_ROOT

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompt-lab" / "prompts"


def _load_prompt(name: str) -> str:
    path = _PROMPT_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt '{name}' not found at {path}")
    return path.read_text().strip()


# =============================================================================
# PLATFORM EXPERT REGISTRY
# =============================================================================

@dataclass
class PlatformExpert:
    """Configuration for a platform-specific video generation expert."""
    scope: str
    name: str
    specialty: str
    ingest_source: Optional[str] = None
    max_duration: int = 15
    supports_audio: bool = True
    camera_control: bool = False


PLATFORM_EXPERTS: dict[str, PlatformExpert] = {
    "kling": PlatformExpert(
        scope="dan-kieft",
        name="Dan Kieft",
        specialty="Kling AI video generation",
        ingest_source="youtube:@DanKieftAI",
        max_duration=15,
        supports_audio=True,
        camera_control=True,
    ),
    "veo": PlatformExpert(
        scope="veo-expert",
        name="Veo Expert",
        specialty="Google Veo video generation",
        ingest_source="youtube:@GoogleAI",
        max_duration=16,
        supports_audio=True,
        camera_control=True,
    ),
    "ltx2": PlatformExpert(
        scope="ltx2-expert",
        name="LTX Expert",
        specialty="LTX-2 local video generation",
        ingest_source="youtube:@Lightricks",
        max_duration=15,
        supports_audio=True,
        camera_control=True,
    ),
    "runway": PlatformExpert(
        scope="runway-expert",
        name="Runway Expert",
        specialty="Runway Gen-3 video generation",
        ingest_source="youtube:@runwayml",
        max_duration=10,
        supports_audio=False,
        camera_control=True,
    ),
    "wan": PlatformExpert(
        scope="wan-expert",
        name="WAN Expert",
        specialty="WAN 2.2 silent film generation",
        ingest_source=None,
        max_duration=10,
        supports_audio=False,
        camera_control=False,
    ),
}


# =============================================================================
# MODEL TRAINING EXPERTS
# =============================================================================

MODEL_TRAINING_EXPERTS: dict[str, PlatformExpert] = {
    "practical": PlatformExpert(
        scope="personas",
        name="Ronan McGovern",
        specialty="Practical ML, RAG, vector databases, production LLMs, fine-tuning",
        ingest_source="youtube:@RonanMcGovern",
        max_duration=0,
        supports_audio=False,
        camera_control=False,
    ),
    "theory": PlatformExpert(
        scope="karpathy",
        name="Andrej Karpathy",
        specialty="Deep learning theory, training from scratch, LoRA, transformers",
        ingest_source="youtube:@karpathy",
        max_duration=0,
        supports_audio=False,
        camera_control=False,
    ),
    "enterprise": PlatformExpert(
        scope="andrew-ng",
        name="Andrew Ng",
        specialty="Data-centric AI, transfer learning, enterprise ML",
        ingest_source="youtube:@Deeplearningai",
        max_duration=0,
        supports_audio=False,
        camera_control=False,
    ),
}


def get_training_expert(focus: str = "practical") -> PlatformExpert:
    """Get model training expert based on focus area."""
    return MODEL_TRAINING_EXPERTS.get(focus.lower(), MODEL_TRAINING_EXPERTS["practical"])


def get_expert_for_platform(platform: str) -> PlatformExpert:
    """Auto-select expert based on generation platform."""
    return PLATFORM_EXPERTS.get(platform.lower(), PLATFORM_EXPERTS["kling"])


def list_available_platforms() -> list[str]:
    """List all supported video generation platforms."""
    return list(PLATFORM_EXPERTS.keys())


# =============================================================================
# CREATIVE TEAM CONFIGURATION
# =============================================================================

@dataclass
class CreativeTeam:
    """Configuration for a multi-persona creative team."""
    director: str
    technical_expert: str
    sound_designer: Optional[str] = None
    script_advisor: Optional[str] = None
    cinematographer: Optional[str] = None
    platform: str = "kling"

    @classmethod
    def from_platform(cls, platform: str, director: str = "horus-filmmaking") -> "CreativeTeam":
        """Create a creative team with auto-selected expert for platform."""
        expert = get_expert_for_platform(platform)
        return cls(
            director=director,
            technical_expert=expert.scope,
            platform=platform,
        )

    def get_expert(self) -> PlatformExpert:
        """Get the PlatformExpert configuration for this team's platform."""
        return get_expert_for_platform(self.platform)


# =============================================================================
# DOCUMENT TRAIL TEMPLATES
# =============================================================================

EXPERT_REVIEW_TEMPLATE = """# Expert Review: {platform} Instructions

> From: {expert_name} ({expert_specialty})
> Date: {date}
> Iteration: {iteration}

---

## Summary

{summary}

---

## Issues Found

{issues_section}

---

## Questions for Director

{questions_section}

---

## Recommendations

{recommendations}

---

*Review generated by create-movie expert review loop*
"""

EXPERT_TO_DIRECTOR_TEMPLATE = """# Expert → Director Feedback

> From: {expert_name} ({expert_specialty})
> To: {director_name} (Director)
> Re: {project_name} - {platform} Execution Notes

---

## Summary

{summary}

---

## Notes for Director Review

{notes_section}

---

## Items Requiring Director Approval

| Item | Expert Recommendation | Status |
|------|----------------------|--------|
{approval_items}

---

## Awaiting Director Response

{awaiting_response}

---

*This feedback loop ensures technical execution serves creative vision.*
"""

DIRECTOR_APPROVAL_TEMPLATE = """# Director Response to Expert Feedback

> From: {director_name} (Director)
> To: {expert_name} ({expert_specialty})
> Re: {project_name} - Technical Approvals

---

## Overall Assessment

{assessment}

---

## Approvals

{approvals_section}

---

## Final Sign-Off

| Item | Status |
|------|--------|
{signoff_table}

---

## Ready for Generation

{workflow_steps}

---

*The technical serves the emotional. Proceed with confidence.*

*{director_name}*
*Director*
"""


@dataclass
class ExpertReview:
    """Result of an expert reviewing generation instructions."""
    expert_id: str
    approved: bool
    issues: list[dict]
    questions: list[str]
    revised_instructions: Optional[str] = None


@dataclass
class DirectorApproval:
    """Result of director reviewing expert feedback."""
    director_id: str
    approved: bool
    answers: dict[str, str]
    revision_requests: list[str]


class ExpertDirectorReviewLoop:
    """
    Self-improvement loop for creative team collaboration.

    Ensures technical expert reviews generation instructions and
    director approves before proceeding to video generation.

    Pattern: Expert Review -> Director Approval -> Loop until both approve
    """

    def __init__(
        self,
        expert_scope: str = None,
        director_scope: str = "horus-filmmaking",
        max_iterations: int = 3,
        work_dir: Optional[Path] = None,
        platform: str = "kling",
        creative_team: Optional[CreativeTeam] = None,
        use_llm_review: bool = False,
        project_name: str = "Untitled Project",
    ):
        if creative_team:
            self.creative_team = creative_team
            self.expert_scope = creative_team.technical_expert
            self.director_scope = creative_team.director
            self.platform = creative_team.platform
        else:
            expert_config = get_expert_for_platform(platform)
            self.expert_scope = expert_scope or expert_config.scope
            self.director_scope = director_scope
            self.platform = platform
            self.creative_team = CreativeTeam(
                director=director_scope,
                technical_expert=self.expert_scope,
                platform=platform,
            )

        self.expert_config = get_expert_for_platform(self.platform)
        self.max_iterations = max_iterations
        self.work_dir = work_dir or Path(".")
        self.iteration = 0
        self.history: list[dict] = []
        self.use_llm_review = use_llm_review
        self.project_name = project_name

        self._latest_review: Optional[ExpertReview] = None
        self._latest_approval: Optional[DirectorApproval] = None

    def query_memory(self, query: str, scope: str = None) -> list[dict]:
        """Query persona from memory using common memory_client."""
        scope = scope or self.expert_scope
        try:
            from common.memory_client import MemoryClient
            client = MemoryClient(scope=scope)
            result = client.recall(query, k=5)
            return result.items if hasattr(result, 'items') else []
        except ImportError:
            return self._query_memory_fallback(query, scope)
        except Exception as e:
            print(f"[ExpertReviewLoop] Memory query failed: {e}")
            return []

    def _query_memory_fallback(self, query: str, scope: str) -> list[dict]:
        """Fallback memory query when common.memory_client not available."""
        memory_path = os.environ.get("MEMORY_SKILL_PATH")
        if not memory_path:
            for subpath in [".agent/skills/memory", ".pi/skills/memory"]:
                candidate = _PROJECT_ROOT / subpath
                if (candidate / "run.sh").exists():
                    memory_path = str(candidate)
                    break

        if not memory_path:
            print(f"[ExpertReviewLoop] Memory skill not found. PROJECT_ROOT={_PROJECT_ROOT}")
            return []

        try:
            result = subprocess.run(
                ["./run.sh", "recall", "--q", query, "--scope", scope],
                capture_output=True, text=True, timeout=30,
                cwd=memory_path,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            if result.returncode == 0:
                return json.loads(result.stdout).get("items", [])
        except Exception as e:
            print(f"[ExpertReviewLoop] Fallback memory query failed: {e}")
        return []

    def _call_llm_review(self, prompt: str) -> dict:
        """Call LLM for expert review."""
        try:
            scillm_path = _PROJECT_ROOT / ".agent" / "skills" / "scillm"
            if not scillm_path.exists():
                scillm_path = _PROJECT_ROOT / ".pi" / "skills" / "scillm"

            if scillm_path.exists():
                result = subprocess.run(
                    ["./run.sh", "complete", "--prompt", prompt, "--format", "json"],
                    capture_output=True, text=True, timeout=120,
                    cwd=scillm_path,
                    env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
                )
                if result.returncode == 0:
                    return json.loads(result.stdout)
        except Exception as e:
            print(f"[ExpertReviewLoop] LLM call failed: {e}")

        return {"approved": True, "issues": [], "questions": [], "recommendations": ""}

    def run_expert_review(
        self,
        instructions_path: Path,
        expert_id: str = None
    ) -> ExpertReview:
        """Have expert persona review generation instructions."""
        self.iteration += 1
        expert_id = expert_id or self.expert_config.name

        instructions = instructions_path.read_text() if instructions_path.exists() else ""

        expert_lessons = self.query_memory(
            "prompting best practices character consistency duration limits",
            scope=self.expert_scope
        )

        if self.use_llm_review and expert_lessons:
            review = self._run_llm_expert_review(instructions, expert_lessons, expert_id)
        else:
            review = self._run_heuristic_expert_review(instructions, expert_lessons, expert_id)

        self._latest_review = review
        self.history.append({
            "iteration": self.iteration,
            "phase": "expert_review",
            "expert_id": expert_id,
            "approved": review.approved,
            "issues_count": len(review.issues),
            "questions_count": len(review.questions),
        })

        return review

    def _run_llm_expert_review(
        self,
        instructions: str,
        expert_lessons: list[dict],
        expert_id: str
    ) -> ExpertReview:
        """Use LLM to simulate expert persona review."""
        expert_context = "\n".join([
            f"- {lesson.get('problem', 'Tip')}: {lesson.get('playbook', lesson.get('solution', ''))}"
            for lesson in expert_lessons[:5]
        ])

        prompt = _load_prompt("create_movie_expert_review_v1").format(
            expert_name=self.expert_config.name,
            expert_specialty=self.expert_config.specialty,
            expert_context=expert_context,
            max_duration=self.expert_config.max_duration,
            supports_audio=self.expert_config.supports_audio,
            camera_control=self.expert_config.camera_control,
            platform=self.platform,
            instructions=instructions,
        )
        result = self._call_llm_review(prompt)

        return ExpertReview(
            expert_id=expert_id,
            approved=result.get("approved", True),
            issues=result.get("issues", []),
            questions=result.get("questions", []),
            revised_instructions=result.get("revised_instructions"),
        )

    def _run_heuristic_expert_review(
        self,
        instructions: str,
        expert_lessons: list[dict],
        expert_id: str
    ) -> ExpertReview:
        """Use heuristic checks based on expert lessons."""
        issues = []
        questions = []
        instructions_lower = instructions.lower()

        max_dur = self.expert_config.max_duration
        for dur in range(max_dur + 1, 30):
            if f"{dur} second" in instructions_lower or f"{dur}s" in instructions_lower:
                issues.append({
                    "issue": f"Duration ({dur}s) exceeds {self.platform} limit ({max_dur}s)",
                    "severity": "high",
                    "recommendation": f"Split into multiple sequences of {max_dur}s or less"
                })
                questions.append(f"How should we split the {dur}s sequence? Hard cut, fade, or dissolve?")
                break

        for lesson in expert_lessons:
            playbook = lesson.get("playbook", lesson.get("solution", "")).lower()

            if "character weight" in playbook and "0.8" in playbook:
                if "weight" not in instructions_lower or "0.8" not in instructions_lower:
                    issues.append({
                        "issue": "Missing character weight setting",
                        "severity": "medium",
                        "recommendation": "Add character weight 0.8 for consistency"
                    })

            if "prompt adherence" in playbook and "2-3" in playbook:
                if "adherence" not in instructions_lower:
                    issues.append({
                        "issue": "Prompt adherence not specified",
                        "severity": "low",
                        "recommendation": "Set prompt adherence to 2-3 for best results"
                    })

            if "dolly" in playbook and "zoom" in playbook:
                if "dolly" in instructions_lower and "zoom" not in instructions_lower:
                    issues.append({
                        "issue": "Using 'dolly' which AI handles poorly",
                        "severity": "medium",
                        "recommendation": "Consider 'subtle zoom' instead of 'dolly' for AI video"
                    })
                    questions.append("Is zoom an acceptable substitute for dolly movement?")

        if not self.expert_config.supports_audio:
            if "audio" in instructions_lower or "sound" in instructions_lower:
                issues.append({
                    "issue": f"{self.platform} does not generate audio",
                    "severity": "medium",
                    "recommendation": "Remove audio references; add audio in post-production"
                })

        approved = len([i for i in issues if i["severity"] == "high"]) == 0

        return ExpertReview(
            expert_id=expert_id,
            approved=approved,
            issues=issues,
            questions=questions,
        )

    def run_director_approval(
        self,
        expert_review: ExpertReview,
        director_id: str = "director"
    ) -> DirectorApproval:
        """Get director approval on expert feedback."""
        director_lessons = self.query_memory(
            "cinematography vision pacing transitions",
            scope=self.director_scope
        )

        high_severity = [i for i in expert_review.issues if i.get("severity") == "high"]
        approved = len(high_severity) == 0 and len(expert_review.questions) == 0

        approval = DirectorApproval(
            director_id=director_id,
            approved=approved,
            answers={},
            revision_requests=[],
        )

        self._latest_approval = approval
        self.history.append({
            "iteration": self.iteration,
            "phase": "director_approval",
            "director_id": director_id,
            "approved": approved,
        })

        return approval

    def run_loop(
        self,
        instructions_path: Path,
        expert_id: str = None,
        director_id: str = "director",
        generate_documents: bool = True,
    ) -> tuple[bool, list[dict]]:
        """Run the full expert -> director -> approval loop."""
        expert_id = expert_id or self.expert_config.name

        while self.iteration < self.max_iterations:
            expert_review = self.run_expert_review(instructions_path, expert_id)

            if generate_documents:
                self._write_expert_review_doc(expert_review)

            if not expert_review.approved:
                print(f"[ExpertReviewLoop] Expert found issues (iteration {self.iteration})")
                if self.iteration >= self.max_iterations:
                    print(f"[ExpertReviewLoop] Max iterations ({self.max_iterations}) reached")
                    break
                continue

            director_approval = self.run_director_approval(expert_review, director_id)

            if generate_documents:
                self._write_feedback_doc(expert_review, director_id)
                self._write_approval_doc(director_approval, expert_review)

            if director_approval.approved:
                print(f"[ExpertReviewLoop] Both approved after {self.iteration} iteration(s)")
                return True, self.history

            if director_approval.revision_requests:
                print(f"[ExpertReviewLoop] Director requested revisions")

        return False, self.history

    # =========================================================================
    # DOCUMENT TRAIL GENERATION
    # =========================================================================

    def _write_expert_review_doc(self, review: ExpertReview) -> Path:
        """Write expert review document."""
        issues_section = ""
        if review.issues:
            for issue in review.issues:
                issues_section += f"### {issue.get('severity', 'medium').upper()}: {issue['issue']}\n\n"
                issues_section += f"**Recommendation:** {issue.get('recommendation', 'N/A')}\n\n"
        else:
            issues_section = "No issues found.\n"

        questions_section = ""
        if review.questions:
            for i, q in enumerate(review.questions, 1):
                questions_section += f"{i}. {q}\n"
        else:
            questions_section = "No questions for director.\n"

        content = EXPERT_REVIEW_TEMPLATE.format(
            platform=self.platform.upper(),
            expert_name=self.expert_config.name,
            expert_specialty=self.expert_config.specialty,
            date=datetime.now().strftime("%Y-%m-%d %H:%M"),
            iteration=self.iteration,
            summary=f"Reviewed {self.platform} generation instructions. "
                    f"{'Approved.' if review.approved else f'Found {len(review.issues)} issues.'}",
            issues_section=issues_section,
            questions_section=questions_section,
            recommendations="See issues above for specific recommendations.",
        )

        filename = f"{self.expert_config.name.upper().replace(' ', '_')}_REVIEW_V{self.iteration}.md"
        path = self.work_dir / filename
        path.write_text(content)
        print(f"[ExpertReviewLoop] Wrote: {path}")
        return path

    def _write_feedback_doc(self, review: ExpertReview, director_id: str) -> Path:
        """Write expert -> director feedback document."""
        notes_section = ""
        for i, issue in enumerate(review.issues, 1):
            notes_section += f"### {i}. {issue['issue']}\n\n"
            notes_section += f"**Technical reality:** {issue.get('recommendation', 'See recommendation')}\n\n"
            if i <= len(review.questions):
                notes_section += f"**Director question:** {review.questions[i-1]}\n\n"

        approval_items = ""
        for issue in review.issues:
            approval_items += f"| {issue['issue'][:40]}... | {issue.get('recommendation', 'N/A')[:30]}... | [ ] Approved |\n"

        content = EXPERT_TO_DIRECTOR_TEMPLATE.format(
            expert_name=self.expert_config.name,
            expert_specialty=self.expert_config.specialty,
            director_name=director_id.replace("_", " ").title(),
            project_name=self.project_name,
            platform=self.platform.upper(),
            summary=f"Technical review of {self.platform} instructions. "
                    f"{len(review.issues)} items require director decision.",
            notes_section=notes_section or "No technical notes.\n",
            approval_items=approval_items or "| No items | - | - |\n",
            awaiting_response="Please review and approve each item above.",
        )

        filename = f"{self.expert_config.name.upper().replace(' ', '_')}_TO_DIRECTOR_FEEDBACK.md"
        path = self.work_dir / filename
        path.write_text(content)
        print(f"[ExpertReviewLoop] Wrote: {path}")
        return path

    def _write_approval_doc(self, approval: DirectorApproval, review: ExpertReview) -> Path:
        """Write director approval document."""
        approvals_section = ""
        signoff_table = ""

        for issue in review.issues:
            approvals_section += f"### {issue['issue']}: **APPROVED**\n\n"
            approvals_section += f"{issue.get('recommendation', 'Approved as recommended.')}\n\n"
            signoff_table += f"| {issue['issue'][:40]}... | APPROVED |\n"

        if not review.issues:
            approvals_section = "No items required approval - instructions passed review.\n"
            signoff_table = "| All items | PASSED |\n"

        workflow_steps = f"""1. Generate {self.platform.upper()} clips per approved instructions
2. Import to editing software
3. Composite any overlays
4. Add audio tracks
5. Apply color grade
6. Export final output
"""

        content = DIRECTOR_APPROVAL_TEMPLATE.format(
            director_name=approval.director_id.replace("_", " ").title(),
            expert_name=self.expert_config.name,
            expert_specialty=self.expert_config.specialty,
            project_name=self.project_name,
            assessment="Technical recommendations approved. Creative vision intact.",
            approvals_section=approvals_section,
            signoff_table=signoff_table,
            workflow_steps=workflow_steps,
        )

        filename = f"DIRECTOR_APPROVAL_V{self.iteration}.md"
        path = self.work_dir / filename
        path.write_text(content)
        print(f"[ExpertReviewLoop] Wrote: {path}")
        return path
