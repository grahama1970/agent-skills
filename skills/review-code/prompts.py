"""Review prompts for code-review skill.

Contains all prompt templates for:
- 3-step review pipeline (review-full)
- Coder-Reviewer loop (loop)
"""
from __future__ import annotations


# =============================================================================
# 3-Step Review Pipeline Prompts (review-full command)
# =============================================================================

STEP1_PROMPT = """You are a code review generator. Analyze the repository and branch specified below, then generate:
1. A unified diff that addresses the objectives
2. Any clarifying questions you have about requirements or implementation choices

{request}

---
OUTPUT FORMAT:
First, list any clarifying questions.
Then provide the unified diff in a fenced code block.
"""

STEP2_PROMPT = """You are a code review judge. Review the generated code review below and:
1. Answer any clarifying questions based on the original request context
2. Critique the proposed diff - identify issues, missing cases, logic bugs, or improvements
3. Provide specific feedback for revision

ORIGINAL REQUEST:
{request}

---
PROPOSED SOLUTION:
{step1_output}

---
OUTPUT FORMAT:
## Answers to Clarifying Questions
(Answer each question or state N/A)

## Critique
(Issues found, missing cases, suggestions)

## Feedback for Revision
(Specific actionable items for the final diff)
"""

STEP3_PROMPT = """You are a code review finalizer. Generate the final unified diff incorporating the judge's feedback.

ORIGINAL REQUEST:
{request}

---
INITIAL SOLUTION:
{step1_output}

---
JUDGE FEEDBACK:
{step2_output}

---
OUTPUT FORMAT:
Provide ONLY a single fenced code block containing the final unified diff.
The diff should:
- Address all feedback from the judge
- Apply cleanly to the specified branch
- Include a one-line commit subject on the first line
No commentary before or after the code block.
"""


# =============================================================================
# Coder-Reviewer Loop Prompts (loop command)
# =============================================================================

LOOP_CODER_INIT_PROMPT = """You are the Coder. Analyze the request and generate a Unified Diff solution.

{request}

---
OUTPUT FORMAT:
1. First, list any clarifying questions about requirements or implementation choices.
2. Then provide the unified diff in a fenced code block.

Any commentary must be outside the code block.
"""

LOOP_REVIEWER_PROMPT = """You are the Reviewer. Critique the Coder's proposed solution.

ORIGINAL REQUEST:
{request}

---
PROPOSED SOLUTION:
{coder_output}

---
YOUR TASK:
1. Answer any clarifying questions the Coder raised.
2. Identify logic assumptions, bugs, or missing requirements.
3. **Compare the solution against the ORIGINAL REQUEST** - does it address all objectives? Any drift or hallucinations?
4. Verify if the code meets the Acceptance Criteria.
5. If the solution is solid and ready to ship, respond with EXACTLY "LGTM" on a line by itself at the start of your response.
6. If changes are needed, list them clearly.
7. If YOU have clarifying questions before approving, list them.
8. **CHANGELOG ENTRY**: Provide a single sentence summarizing why this solution failed (e.g., "Failed to handle edge case X"). This will be added to the persistent history.

IMPORTANT: Only say "LGTM" if NO changes are required. Any feedback means another revision is needed.
"""

LOOP_CODER_FIX_PROMPT = """You are the Coder. Fix your solution based on the Reviewer's feedback.

ORIGINAL REQUEST (ground truth - do not drift from this):
{request}

---
CHANGELOG (Previous attempts and failures):
{changelog}

---
YOUR PREVIOUS SOLUTION:
{coder_output}

---
REVIEWER FEEDBACK:
{reviewer_output}

---
OUTPUT FORMAT:
1. First, answer any clarifying questions the Reviewer raised.
2. Then provide the FIXED unified diff in a fenced code block.

IMPORTANT: Ensure your fix still addresses the ORIGINAL REQUEST. Do not introduce scope creep or drift. Avoid repeating mistakes listed in the CHANGELOG.
"""
