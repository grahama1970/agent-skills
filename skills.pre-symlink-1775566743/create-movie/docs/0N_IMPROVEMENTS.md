# create-movie Improvements (Learned from SPARTA Teaser)

> Lessons learned from the Embry/Horus SPARTA teaser production.

---

## Summary of Gaps

| Gap | Severity | Status |
|-----|----------|--------|
| Expert → Director feedback loop | HIGH | Partially fixed (basic heuristics) |
| Platform-specific expert selection | HIGH | Not implemented |
| Document trail auto-generation | MEDIUM | Not implemented |
| Multi-persona collaboration beyond expert/director | MEDIUM | Not implemented |
| LLM-based review (not just string matching) | MEDIUM | Not implemented |
| Post-production workflow tracking | LOW | Not implemented |
| Cross-project collaboration (agent-inbox) | LOW | Manual only |

---

## 1. Platform-Specific Expert Selection (HIGH PRIORITY)

### Problem
The current `ExpertDirectorReviewLoop` uses a hardcoded `expert_scope` parameter. During SPARTA, we manually knew to use `dan-kieft` for Kling. But what about Veo, LTX-2, or other platforms?

### Solution
Create an expert registry mapping platforms to memory scopes:

```python
PLATFORM_EXPERTS = {
    "kling": {
        "scope": "dan-kieft",
        "name": "Dan Kieft",
        "specialty": "Kling AI video generation",
        "ingest_source": "youtube:@DanKieftAI"
    },
    "veo": {
        "scope": "veo-expert",  # Planned: ingest Google Veo tutorials
        "name": "Veo Expert",
        "specialty": "Google Veo video generation"
    },
    "ltx2": {
        "scope": "ltx2-expert",  # Planned: ingest Lightricks tutorials
        "name": "LTX Expert",
        "specialty": "LTX-2 local video generation"
    },
    "runway": {
        "scope": "runway-expert",
        "name": "Runway Expert",
        "specialty": "Runway Gen-3 video generation"
    }
}

def get_expert_for_platform(platform: str) -> dict:
    """Auto-select expert based on generation platform."""
    return PLATFORM_EXPERTS.get(platform, PLATFORM_EXPERTS["kling"])
```

### Implementation
1. Add `--platform` flag to orchestrator (kling, veo, ltx2, runway)
2. Auto-select expert scope based on platform
3. Add `ingest-expert` command to populate new expert scopes

```bash
# Ingest a new platform expert
./run.sh ingest-expert --platform veo --youtube "@GoogleAI" --query "Veo tutorial"
```

---

## 2. LLM-Based Expert Review (HIGH PRIORITY)

### Problem
Current `run_expert_review()` uses simple string matching heuristics:
```python
if "15 sec" in playbook.lower() and "17 second" in instructions.lower():
    issues.append({"issue": "Duration exceeds limit", ...})
```

This misses nuanced issues Dan Kieft would catch.

### Solution
Use actual LLM to simulate expert persona review:

```python
def run_expert_review_llm(self, instructions: str, expert_lessons: list) -> ExpertReview:
    """Use LLM to simulate expert persona review."""

    # Build expert context from memory
    expert_context = "\n".join([
        f"- {lesson['problem']}: {lesson['solution']}"
        for lesson in expert_lessons
    ])

    prompt = f"""You are {self.expert_name}, an expert in {self.expert_specialty}.

Based on your knowledge:
{expert_context}

Review these generation instructions and identify:
1. Technical issues that will cause problems
2. Questions requiring director decision
3. Recommendations for improvement

Instructions to review:
{instructions}

Respond in JSON format:
{{
  "approved": true/false,
  "issues": [{{"issue": "...", "severity": "high/medium/low", "recommendation": "..."}}],
  "questions": ["Question for director 1", "Question 2"],
  "revised_instructions": "..." (only if changes needed)
}}
"""

    # Use scillm or local LLM for review
    response = self._call_review_llm(prompt)
    return ExpertReview.from_json(response)
```

### Implementation
1. Add `--llm-review` flag to enable LLM-based review
2. Default to heuristic checks, upgrade to LLM when flag set
3. Use `/scillm` or local model to avoid API costs

---

## 3. Document Trail Auto-Generation (MEDIUM PRIORITY)

### Problem
We manually created:
- `KLING_INSTRUCTIONS_V1.md`
- `DAN_KIEFT_REVIEW_V1.md`
- `DAN_TO_WILSON_FEEDBACK.md`
- `WILSON_APPROVAL.md`
- `KLING_INSTRUCTIONS_V2_APPROVED.md`

### Solution
Auto-generate these documents during the review loop:

```python
class ExpertDirectorReviewLoop:
    def generate_document_trail(self):
        """Generate all review documents automatically."""

        docs = {
            f"{self.platform.upper()}_INSTRUCTIONS_V{self.iteration}.md": self.instructions,
            f"{self.expert_id.upper()}_REVIEW_V{self.iteration}.md": self.format_review(),
            f"{self.expert_id.upper()}_TO_{self.director_id.upper()}_FEEDBACK.md": self.format_feedback(),
            f"{self.director_id.upper()}_APPROVAL.md": self.format_approval(),
        }

        if self.approved:
            docs[f"{self.platform.upper()}_INSTRUCTIONS_V{self.iteration}_APPROVED.md"] = self.final_instructions

        for filename, content in docs.items():
            (self.work_dir / filename).write_text(content)
```

### Templates
Create templates in `templates/` directory:
- `expert_review.md.j2`
- `expert_to_director_feedback.md.j2`
- `director_approval.md.j2`

---

## 4. Multi-Persona Collaboration (MEDIUM PRIORITY)

### Problem
SPARTA had 4 personas:
- Director: Dougal Wilson
- Technical Expert: Dan Kieft
- Sound Designer: Ren Klyce
- Script Advisor: Andy Weir

Only expert/director loop is implemented. Klyce's sound notes were manual.

### Solution
Extend the loop to support multiple review phases:

```python
@dataclass
class CreativeTeam:
    director: str  # Memory scope
    technical_expert: str
    sound_designer: Optional[str] = None
    script_advisor: Optional[str] = None
    cinematographer: Optional[str] = None

class MultiPersonaReviewLoop:
    """Extended review loop with multiple specialists."""

    REVIEW_ORDER = [
        ("script_advisor", "script"),      # Review script first
        ("cinematographer", "shot_list"),  # Review visual plan
        ("technical_expert", "instructions"),  # Review generation instructions
        ("sound_designer", "audio_plan"),  # Review audio approach
    ]

    def run_all_reviews(self) -> dict[str, Review]:
        """Run reviews in order, each feeding into the next."""
        reviews = {}
        for role, artifact in self.REVIEW_ORDER:
            if getattr(self.team, role):
                reviews[role] = self.run_persona_review(role, artifact)
                if not reviews[role].approved:
                    # Stop and get director decision
                    break
        return reviews
```

### CLI
```bash
./run.sh create "prompt" \
    --director horus-filmmaking \
    --expert dan-kieft \
    --sound-designer klyce \
    --script-advisor weir
```

---

## 5. Post-Production Workflow Tracking (LOW PRIORITY)

### Problem
Wilson's approval specified a 9-step workflow:
1. Generate Sequence A (Office, 8s)
2. Generate Sequence B (Bedroom, 9s)
3. Import both to DaVinci Resolve
4. Composite UX screenshots
5. Add TTS audio tracks
6. Apply Klyce sound design
7. Apply Wilson color grade
8. Add 2-second fade between sequences
9. Export final teaser

This wasn't tracked anywhere.

### Solution
Generate a `POST_PRODUCTION_CHECKLIST.md` from director approval:

```python
def extract_workflow_from_approval(approval: DirectorApproval) -> list[str]:
    """Parse director approval for workflow steps."""
    # Use LLM to extract numbered steps from approval text
    # Generate checklist with [ ] markers
    pass
```

### Integration with task-monitor
```bash
# Register post-production as tracked task
./run.sh assemble --track-workflow --register-with task-monitor
```

---

## 6. Cross-Project Collaboration (LOW PRIORITY)

### Problem
We used `/agent-inbox` to request UX screenshots from `horus-ui` project. This was manual.

### Solution
Formalize cross-project asset requests:

```python
def request_external_asset(
    target_project: str,
    asset_type: str,  # "screenshot", "audio", "video"
    description: str,
    deadline: Optional[datetime] = None
) -> str:
    """Send asset request via agent-inbox."""

    message = {
        "type": "asset_request",
        "from_project": "pi-mono",
        "from_skill": "create-movie",
        "asset_type": asset_type,
        "description": description,
        "deadline": deadline.isoformat() if deadline else None,
        "callback": f"create-movie:receive_asset"
    }

    return send_to_inbox(target_project, message)
```

### CLI
```bash
./run.sh request-asset \
    --from horus-ui \
    --type screenshot \
    --description "Phone screen showing Horus typing response"
```

---

## Implementation Priority

### Phase 1 (Next Sprint)
1. [ ] Platform-specific expert registry
2. [ ] LLM-based expert review (optional flag)
3. [ ] Document trail auto-generation

### Phase 2 (Future)
4. [ ] Multi-persona collaboration
5. [ ] Post-production workflow tracking
6. [ ] Cross-project asset requests

---

## Files to Modify

| File | Changes |
|------|---------|
| `orchestrator.py` | Add `--platform` flag, expert auto-selection |
| `persona_integration.py` | Add `PLATFORM_EXPERTS` registry, LLM review |
| `templates/` | Create document trail templates |
| `SKILL.md` | Document new flags and workflows |

---

## Testing Criteria

Each improvement should be tested with:

1. **Unit test**: Does the function work in isolation?
2. **Integration test**: Does it work in the full pipeline?
3. **SPARTA replay**: Can we replay SPARTA teaser with improvements?

```bash
# Replay SPARTA with improvements
./run.sh create "SPARTA cybersecurity teaser" \
    --platform kling \
    --llm-review \
    --auto-documents \
    --work-dir /mnt/storage12tb/media/personas/embry/v2/
```

---

*Documented after SPARTA teaser production revealed these gaps.*
