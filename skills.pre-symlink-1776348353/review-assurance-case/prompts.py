"""Prompt templates for the 3-step assurance case review pipeline.

Step 1: Structural Audit — graph topology + programmatic checks
Step 2: Semantic Review — logical soundness, evidence sufficiency, completeness, confidence, context
Step 3: Final Verdict — aggregate findings, score, recommend fixes
"""

# ---------------------------------------------------------------------------
# Step 1: Structural Audit
# ---------------------------------------------------------------------------

STEP1_PROMPT = """You are an assurance case structural auditor. Your job is to examine the structure of an evidence case and identify structural defects.

## ASSURANCE CASE TO REVIEW

{case_content}

## STRUCTURAL CHECKS (S-01 through S-10)

For each check, determine PASS or FAIL with specific evidence:

S-01: Every claim/goal has at least one argument or strategy beneath it.
S-02: Every strategy decomposes into at least one sub-goal or evidence item.
S-03: Every argument chain terminates in evidence (not in unsupported claims).
S-04: No dangling/orphan nodes — every node reachable from top-level goal.
S-05: No circular reasoning — argument graph is a DAG.
S-06: Type-correct connections — claims→arguments, evidence→arguments only.
S-07: No "undeveloped" or "in development" markers remain.
S-08: Every claim has contextual framing (scope, environment, constraints).
S-09: Choice junctions (OR-decompositions) specify M-of-N logic.
S-10: Modular boundaries have interface goals (if case is modular).

## PROCESS CHECKS (P-01 through P-06)

P-01: Assessment methods include examine, interview, AND test (not just documents).
P-02: All evidence artifacts are approved/final (no drafts).
P-03: Tool qualification evidence exists for automated verification tools.
P-04: Review independence is demonstrated at appropriate assurance level.
P-05: Problem reports are closed or dispositioned.
P-06: Case is maintained through lifecycle (not stale from design phase).

## OUTPUT FORMAT

For each check, output:
```
[CHECK_ID] PASS|FAIL — <one-line rationale>
  Evidence: <specific node/section that proves the finding>
```

After all checks, output a STRUCTURAL SUMMARY:
```
## Structural Summary
- Checks passed: N/16
- Critical failures: [list of S-XX or P-XX IDs]
- Structural score: X/10
```
"""

# ---------------------------------------------------------------------------
# Step 2: Semantic Review
# ---------------------------------------------------------------------------

STEP2_PROMPT = """You are an assurance case semantic reviewer specializing in logical soundness, evidence sufficiency, completeness, confidence calibration, and contextual validity. You have deep expertise in GSN (ISO 15026), CAE (Claims-Arguments-Evidence), Assurance 2.0 defeater taxonomy, DO-178C, IEC 61508, ISO 26262, and CMMC.

## ASSURANCE CASE TO REVIEW

{case_content}

## STRUCTURAL AUDIT RESULTS (from Step 1)

{step1_output}

## SEMANTIC CHECKS

### Logical Soundness (L-01 through L-07)
L-01: Are arguments valid inference steps? Do sub-claims + evidence logically entail parent claims?
L-02: Any relevance fallacies? (red herrings, improper authorities, wrong conclusions)
L-03: Any acceptability fallacies? (circular arguments, false dichotomy, faulty analogy, ambiguity)
L-04: Any sufficiency fallacies? (pseudo-precision, hasty generalization, arguing from ignorance, omission of evidence)
L-05: Is each argument type identifiable? (Decomposition, Substitution, Concretion, Calculation, Evidence Incorporation)
L-06: Is deductive vs inductive reasoning properly distinguished?
L-07: Do strategies describe arguments (not just activities)?

### Evidence Sufficiency (E-01 through E-10)
E-01: Does every evidence node reference a concrete, identifiable artifact?
E-02: Is evidence in final form (not drafts)?
E-03: Is evidence provenance recorded (who, when, process, tools)?
E-04: Is evidence relevant to the specific property being claimed?
E-05: Is evidence reliable? (external>internal, direct>indirect, qualified>ad-hoc)
E-06: Is evidence quantity proportional to risk level?
E-07: Is evidence current (not stale from previous version)?
E-08: Are independence requirements met where mandated?
E-09: Does testing evidence cover realistic operational conditions?
E-10: For ML/AI components: training data coverage, robustness, drift addressed?

### Completeness (C-01 through C-10)
C-01: Do all identified threats/hazards have corresponding claims?
C-02: Are all requirements traced bidirectionally (requirement→claim→evidence)?
C-03: Are assumptions explicitly stated as declared elements?
C-04: Are all assumptions justified or validated?
C-05: Are counter-arguments/defeaters identified? (Zero defeaters = suspicious)
C-06: Are all defeaters closed (not open/unresolved)?
C-07: Are residual risks documented with acceptance justification?
C-08: Is framework control coverage complete? (CMMC/DO-178C/ISO 26262)
C-09: Are there missing, incorrect, ambiguous, or outdated requirements?
C-10: Are structural defeaters addressed? (single points of failure, interdependencies)

### Confidence Calibration (CF-01 through CF-06)
CF-01: Are confidence levels stated explicitly with rationale?
CF-02: Does confidence account for: logical + probabilistic + defeaters + residual risks?
CF-03: Any pseudo-precision? (precise numbers without statistical basis)
CF-04: Is verification vs validation confidence distinguished?
CF-05: Is epistemic vs aleatoric uncertainty distinguished?
CF-06: Is ontological uncertainty acknowledged? (claims of completeness without qualification = overconfident)

### Contextual Validity (CX-01 through CX-06)
CX-01: Is operational context explicitly defined? (environment, mission, users, constraints)
CX-02: Is evidence valid for the stated operational context?
CX-03: Are human factors addressed? (operator error modes)
CX-04: Is configuration management traceable? (specific version/config stated)
CX-05: Are environmental factors addressed? (temperature, radiation, EMI)
CX-06: For security cases: are adversarial threats addressed?

## OUTPUT FORMAT

For each check, output:
```
[CHECK_ID] PASS|FAIL|N/A — <one-line rationale>
  Severity: critical|high|medium|low
  Evidence: <specific section/node proving the finding>
  Recommendation: <what to fix if FAIL>
```

After all checks, output:
```
## Semantic Summary
- Logical soundness: X/10
- Evidence sufficiency: X/10
- Completeness: X/10
- Confidence calibration: X/10
- Contextual validity: X/10
- Findings by severity: N critical, N high, N medium, N low
```
"""

# ---------------------------------------------------------------------------
# Step 3: Final Verdict
# ---------------------------------------------------------------------------

STEP3_PROMPT = """You are an assurance case assessment lead producing the final review verdict. You have the structural audit and semantic review results.

## ASSURANCE CASE

{case_content}

## STEP 1: STRUCTURAL AUDIT

{step1_output}

## STEP 2: SEMANTIC REVIEW

{step2_output}

## YOUR TASK

Produce the FINAL REVIEW REPORT with:

### 1. Executive Summary (2-3 sentences)
What is this assurance case about? Is it adequate?

### 2. Verdict
One of:
- **ADEQUATE** — All critical checks pass, evidence chain is traceable, defeaters addressed. Ready for audit.
- **NEEDS_WORK** — No critical structural failures, but significant gaps in evidence or completeness. Fixable.
- **INADEQUATE** — Critical structural defects, circular reasoning, missing evidence chains, or fundamental logical gaps.

### 3. Category Scores (0-10 each)
| Category | Score | Key Findings |
|----------|-------|-------------|
| Structural Integrity | X/10 | ... |
| Logical Soundness | X/10 | ... |
| Evidence Sufficiency | X/10 | ... |
| Completeness | X/10 | ... |
| Confidence Calibration | X/10 | ... |
| Contextual Validity | X/10 | ... |
| Process Compliance | X/10 | ... |

### 4. Critical Findings (must fix)
Numbered list of critical/high severity findings with:
- Check ID
- What's wrong
- Specific fix recommendation

### 5. Strengths
What the case does well.

### 6. Defeater Analysis
- Identified defeaters and whether they're adequately addressed
- Missing defeaters that should be considered
- Residual risks that need documentation

### 7. Recommendations (prioritized)
1. [Critical] ...
2. [High] ...
3. [Medium] ...

### 8. Comparison with Prior Reviews
If prior review data was provided, note:
- What improved since last review
- What regressed
- Recurring issues

OUTPUT the complete review report in markdown.
"""

# ---------------------------------------------------------------------------
# Context bridging template (for stateless providers)
# ---------------------------------------------------------------------------

CONTEXT_BRIDGE_STEP2 = """## PRIOR CONTEXT (from structural audit)

The following structural audit was performed on this assurance case:

{step1_output}

---

Now perform the semantic review:

{step2_prompt}
"""

CONTEXT_BRIDGE_STEP3 = """## PRIOR CONTEXT

### Structural Audit Results:
{step1_output}

### Semantic Review Results:
{step2_output}

---

Now produce the final verdict:

{step3_prompt}
"""
