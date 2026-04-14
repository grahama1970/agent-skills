---
name: create-evidence-case
description: >
  Build structured evidence cases using Claims-Arguments-Evidence (CAE) trees.
  AGENT-DRIVEN composable orchestrator: the agent decomposes the question,
  calls existing skills for data collection and verification, then DECIDES
  the verdict. Python runner.py is a thin data collector and persistence layer.
allowed-tools:
  - Bash
  - Read
  - Grep
  - Glob
  - Write
  - Edit
triggers:
  - create-evidence-case
  - evidence case
  - build evidence
  - verify claim
  - evidence tree
metadata:
  short-description: "Composable CAE evidence orchestrator"
  version: "4.3.0"
provides:
  - evidence-case-creation
  - uct-strategy-selection
  - evidence-tree-persistence
  - claim-verdict-grading
  - assurance-case-output
  - oscal-export
  - qra-candidate-quarantine
  - human-review-interview
composes:
  - memory
  - extract-entities
  - assistant
  - taxonomy
  - lean4-prove
  - dogpile
  - edge-verifier
  - cmmc-assessor
  - create-gsn-diagram
  - export-oscal
  - create-figure
  - task-monitor
  - interview
  - prompt-lab
  - analytics
taxonomy:
  - verification
  - evidence
  - quality-assurance
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

**User-facing documentation:** See [COMPLETE_EXAMPLE.md](COMPLETE_EXAMPLE.md) for compliance officer workflow, CAE tree examples, and the tool's role as a research assistant (not compliance oracle).

# /create-evidence-case v4.3 — Composable Orchestrator

Build structured **Claims-Arguments-Evidence (CAE)** trees. This is an **agent-driven** skill — you (the agent) orchestrate existing skills, reason about results, and make all judgment calls. The Python code is a thin data collector.

## INPUT/OUTPUT MODEL (v4.2)

**Input**: Any control from `sparta_controls` (SPARTA, NIST, CWE, CAPEC) OR a raw question.

**Output**: Always a QRA document in `sparta_qra`, regardless of input source.

| Input Source | Example | Output |
|--------------|---------|--------|
| SPARTA control | SA-1 | QRA with `source_framework: "SPARTA"` |
| NIST control | IA-5 | QRA with `source_framework: "NIST-800-53"` |
| CWE | CWE-287 | QRA with `source_framework: "CWE"` |
| Raw question | "What is CWE-287?" | QRA with extracted `source_control_id` |

### QRA Output Tiers

Not every QRA has evidence. The `evidence_case` field being `null` is a **deterministic signal** (no crosswalk edges exist), not a failure.

| Tier | evidence_case | Use Case |
|------|---------------|----------|
| **Informational** | null | Explanation, lookup (no crosswalk edges) |
| **Grounded** | `{chains: [...], formal_proof: null}` | Compliance, audit |
| **Verified** | `{chains: [...], formal_proof: {success: true}}` | Safety-critical, formal methods |

All fields (chains, formal_proof, sacm_ref) live **inside** evidence_case. One null check.

### Entity Extraction → Evidence Case Flow

```
"What is CWE-287?"
       │
       ▼
/extract-entities → "CWE-287" ✓
       │
       ▼
/create-evidence-case
├── Query crosswalk edges in sparta_relationships
├── Has edges → evidence_case: {chains: [...]}
└── No edges  → evidence_case: null (valid output)
       │
       ▼
QRA created in sparta_qra
├── question: "What is CWE-287?"
├── requirement: CWE-287 description
├── answer: Explanation text
├── source_framework: "CWE"
├── source_control_id: "CWE-287"
└── evidence_case: {...} or null  # SELF-CONTAINED: includes chains, proof, sacm_ref
```

### Self-Contained QRA Schema (v4.3)

Every QRA embeds all metadata for downstream consumption. **evidence_case is fully
self-contained** — formal proofs and SACM references live INSIDE it, not at top level.
This ensures traceability in ArangoDB and portability for OSCAL/SACM export.

```python
{
    # Core QRA fields
    "question": str,
    "requirement": str,
    "answer": str,
    "source_framework": str,        # SPARTA, NIST-800-53, CWE, CAPEC
    "source_control_id": str,       # SA-1, IA-5, CWE-287
    "relationship_id": str,         # Links persona variations
    "expertise": str,               # expert, layperson, pm, compliance
    "difficulty": str,              # single_hop, multi_hop, synthesis
    
    # Taxonomy (Mind tags for SPARTA scope)
    "mind": list[str],              # ["Detect", "Harden"]
    
    # Evidence case — SELF-CONTAINED (null if no crosswalk edges)
    # All verification evidence lives here: chains, proof, SACM ref
    "evidence_case": {
        "chains": [...],            # Crosswalk paths (source → hops → target)
        "confidence": float,        # 0.0-1.0 combined confidence
        "methods": list[str],       # ["direct", "mitre_chain", "nist_nvd"]
        
        # Formal proof (null if not verified) — INSIDE evidence_case
        "formal_proof": {
            "success": bool,
            "code": str,            # Lean4 source code
            "attempts": int,
            "errors": list | None,
            "proved_at": int | None,
        } | None,
        
        # SACM reference (null if not exported) — INSIDE evidence_case
        "sacm_ref": {
            "gid": str,             # SACM Goal node GID (lookup key)
            "xml_snippet": str,     # First 500 chars (preview)
            "generated_at": int,
        } | None,
    } | None,
}
```

**Why self-contained?** ISO 26262 and DO-178C refinement checking patterns bundle
verification evidence with the claim. Separate collections would require joins,
lose portability, and break single-document export to OSCAL/SACM XML.

## TRACEABILITY vs VERIFICATION

Matching requirements to controls (via `/match/requirement`) provides **traceability** —
linking related concepts. But traceability alone is NOT SUFFICIENT for certification.

| Level | What it proves | Provides | Sufficient for |
|-------|----------------|----------|----------------|
| **Matching** | "Related concepts" | Traceability | Gap detection, triage |
| **Confidence scoring** | "Probably covers" | Prioritization | Audit prep |
| **Formal proof** | "Functionally entails" | Verification | ISO 26262, DO-178C certification |

**Why matching is insufficient:**
```
Requirement: "shall implement multi-factor authentication for all users"
Control: SV-AC-2 "implement access control mechanisms"

Matching confidence: 0.82
  - Crosswalk chain exists (CWE → NIST → SPARTA)
  - QRA evidence mentions both
  - Semantic similarity is high

Problem: Does SV-AC-2 ACTUALLY cover MFA?
  - Words overlap, but FUNCTIONS might not
  - Control might be narrower/broader than requirement
  - Edge cases might not be addressed
```

**Why formal proofs are needed:**
```
Formal proof (Lean4):
  theorem control_satisfies_requirement :
    ∀ u : User, implements(SV-AC-2, u) → authenticated(u) ∧ factors(u) ≥ 2

  Proof result: success=true
  Meaning: The control ENTAILS the requirement — not just similar words,
           but the control is a valid implementation of the requirement.
```

The `evidence_case.formal_proof` field stores this verification evidence.
Matching builds the edges; formal proofs prove they're functionally valid.

## EXECUTION MODES

| Mode | Engine | When | Latency |
|------|--------|------|---------|
| **Live** | Project agent (you) | Interactive use | ~10-12s (dominated by `/memory recall`) |
| **Batch** | `EvidenceCaseRunner` | Nightly eval, `run_question_bank.py` | ~17s (subprocess classifiers) |

**Live mode**: YOU are the engine. Call `/memory recall` for data, do decomposition + entity analysis + same-technique check + verdict in your reasoning. No `/assistant classify` calls needed — you ARE the classifier. `/lean4-prove` Docker compilation is near-instant.

**Batch mode**: `EvidenceCaseRunner` in `runner.py` proxies for you using `/assistant` classifiers. Use `/scillm` shadow for nightly training data collection (latency acceptable). Run via `run_question_bank.py`.

## CORE PRINCIPLE

Entities from different sentence components must resolve to the **same SPARTA technique**. If they don't, the question spans unrelated domains and the verdict is INCONCLUSIVE.

## HOW IT WORKS — 7-Step Agent Flow

### Step 1: Sentence Decomposition (Agent)

Parse the question into Given/Then components. This is native LM capability — no tool needed.

```
Question: "Given the F-36's use of third-party FPGA vendors, which SPARTA
           supply chain attack vectors should we prioritize in our CMMC
           Level 3 compliance audits?"

Given (context/constraints):
  - F-36                        → project context
  - third-party FPGA vendors    → SPARTA controls term

Then (search targets/threats):
  - SPARTA supply chain attack vectors  → SPARTA controls term
  - CMMC Level 3 compliance audits      → framework mapping term
```

Each component becomes a separate query. The sentence structure tells you how they relate: "Given X, which Y should we Z?" means X constrains the search for Y in the context of Z.

### Step 2: Per-Component QRA Retrieval (Parallel)

For EACH component, query `/memory recall`:

```bash
# Per-component recall — use --collections sparta_qra
.claude/skills/memory/run.sh recall --q "<component>" --collections sparta_qra --k 10
```

Run these in PARALLEL — one subprocess per component. QRAs have `control_id`, `tactical_tags`, `question`, `answer` fields.

### Step 3: Entity Extraction + Grounding Verification (CRITICAL)

Extract entities and check grounding from the FULL question. In batch mode, `collect_entities()` calls `extract_entities()` directly (no subprocess). In live mode, you can call:

```bash
.claude/skills/extract-entities/run.sh extract --json "<full question>"
```

The result includes an `agent_view()` with these key fields:

```json
{
  "headline": "2 controls resolved; 1 fabricated ID(s)",
  "grounding_ok": false,
  "controls": [
    {"control_id": "SV-AC-2", "name": "...", "confidence": 1.0, "match_type": "exact", "qra_count": 44}
  ],
  "warnings": [
    {"term": "X23-MUSTARD", "category": "fabricated_id", "confidence": 0.0, "detail": "No match in corpus..."},
    {"term": "decoherence", "category": "not_in_corpus", "confidence": 0.0, "detail": "Term not found..."}
  ]
}
```

**Read `grounding_ok` first.** If `false`, check `warnings`:

| Warning category | Meaning | Your action |
|-----------------|---------|-------------|
| `fabricated_id` | ID-like term with 0 matches in 8,979+ controls | Strong signal — question's premise is likely fabricated |
| `not_in_corpus` | Term doesn't appear anywhere in domain corpus | Check if it's a real concept outside SPARTA scope |
| `misspelling` | Close to a known term (edit distance) | Proceed with correction noted |

**Per-control `confidence` scores:**

| Score | Meaning |
|-------|---------|
| 1.0 | Exact control_id match with QRAs |
| 0.9 | Exact match, no QRAs yet |
| 0.7-0.85 | Fuzzy ID match (probable typo) |
| 0.4-0.8 | Phrase grounded via hybrid search word overlap |
| 0.0 | Unresolved — fabricated, misspelled, or not in corpus |

This is what prevents false positives on adversarial questions. Semantic search will ALWAYS find *something* for security-adjacent keywords. Grounding evidence shows whether the *specific entities claimed by the question* actually exist.

### Step 4: Same-Technique Check (Agent — CRITICAL)

Read the per-component recall results and extracted entities. Ask:

**Do entities from different components resolve to the SAME technique?**

- Check `tactical_tags` across components — do they cluster into 1-2 techniques?
- Check `related_pairs` from /extract-entities — do cross-component edges exist?
- If components share technique relationships → coherent question
- If entities exist but have no shared technique → spans unrelated domains

This is THE critical judgment. Components must bridge through a shared technique for the evidence to be coherent.

### Step 5: Clarification (Skill)

Ask `/memory clarify` to explain which entities are related and which aren't:

```bash
# Clarify entity relationships
.claude/skills/memory/run.sh clarify --q "<question>"
```

This returns structured disambiguation: related entities, unrelated entities, suggested decompositions. Read this to confirm or revise your same-technique assessment.

### Step 6: Formal Verification (Skill)

Formalize the evidence chain as a theorem and attempt proof:

```bash
# Formalize and verify the evidence chain
.claude/skills/lean4-prove/run.sh --requirement "<formal claim derived from evidence>"
```

The formal claim should express: "Given [components from recall], [technique bridge] implies [verdict]."
- Proof succeeds → strong formal backing for SATISFIED
- Proof fails → confirms gap, supports INCONCLUSIVE
- Explicitly not formalizable (or low-confidence formalizability) → skip gate with no penalty
- Provability classifier unavailable → Gate 5 is blocked, so do not return SATISFIED

### Step 7: Final Verdict + Report (Agent)

Synthesize all results into a verdict:

- **SATISFIED**: All components resolve, same technique bridge confirmed, QRAs address the question. Proof success strengthens this.
- **INCONCLUSIVE**: Some components covered, others need research. OR entities exist but don't share a technique. Proof failure confirms gap.
- **NOT_SATISFIED**: Components don't resolve, off-topic, or no entities found.

Persist the case:

```python
from runner import EvidenceCaseStore2

store = EvidenceCaseStore2()
store.persist_case(
    question="...",
    category="compliance",
    verdict_state="satisfied",
    grade="A+",
    score=1.0,
    gates=[...],
    evidence_items=qra_items,
    answer="...",
    technique_groups={"Harden": 5, "Detect": 3},
    sub_claims=["[supply chain] ...", "[CMMC L3] ..."],
    control_ids=["SR-3(2)", "SA-8", "SI-3"],
    decomposition=decomposition_node.to_dict(),
)
```

## CONDITIONAL BRANCHES

### If INCONCLUSIVE → Tier 3 Research

When recall is sparse or entities don't bridge, use `/dogpile` for Tier 3 research:

```bash
# Research gap areas
.claude/skills/dogpile/run.sh search "<gap query>" --auto-preset
```

Re-evaluate with new evidence. If still inconclusive, report the gaps.

### If Question Involves CMMC → Framework Mapping

When the question references CMMC, add compliance mapping:

```bash
# CMMC assessment
.claude/skills/cmmc-assessor/run.sh assess --level 3 --family <family>
```

### After Verdict → Assurance Case + OSCAL Export

For SATISFIED or INCONCLUSIVE verdicts with sufficient evidence:

```bash
# GSN diagram (ISO 15026)
.claude/skills/create-gsn-diagram/run.sh render --control <primary_control_id>

# OSCAL JSON export for auditors
.claude/skills/export-oscal/run.sh export --framework NIST-800-171
```

### Cross-Component Edge Verification

When entity relationships need validation:

```bash
# Verify edges between entities
.claude/skills/edge-verifier/run.sh verify --source_id <ID> --text "<content>"
```

### Topic Classification

For initial on-topic/off-topic filtering:

```bash
# Classify topic
.claude/skills/assistant/run.sh classify --task topic-classifier --text "<question>"
```

### Visualization

For metric charts and report figures:

```bash
# Generate charts
.claude/skills/create-figure/run.sh metrics --input <data.json> --output <path>
```

## DATA COLLECTION FUNCTIONS

The runner provides thin subprocess wrappers for each skill:

```python
from runner import (
    # Data collection
    collect_recall,        # /memory recall → QRA items
    collect_entities,      # /extract-entities → control_ids, related_pairs
    collect_topic,         # /assistant classify → on_topic, category
    collect_clarify,       # /memory clarify → disambiguation
    collect_lean4_proof,   # /lean4-prove → proof result
    collect_dogpile,       # /dogpile search → Tier 3 research
    collect_cmmc,          # /cmmc-assessor → CMMC mapping
    collect_edge_verify,   # /edge-verifier → edge validation
    group_by_technique,    # Group QRAs by tactical_tags
    # QRA quarantine + human review
    quarantine_as_candidate_qra,    # SATISFIED → staging collection
    generate_gap_review_questions,  # INCONCLUSIVE → gap review form
    promote_candidate_qra,          # Approved → sparta_qra
    reject_candidate_qra,           # Rejected → rejected_qras (GRPO)
    process_interview_result,       # Process /interview responses
)
```

## WHAT YOU MUST NOT DO

- **Do NOT regex-parse control IDs** — read structured fields from recall results
- **Do NOT use stopword lists** — you understand language, use that
- **runner.py uses direct graph_memory imports** — subprocess is only fallback when imports fail
- **Do NOT auto-pass verdicts** — if you can't tell whether evidence is coherent, say INCONCLUSIVE
- **Do NOT write deterministic if/else for coverage** — language is too variable, YOU decide
- **Do NOT assume one QRA matches the full question** — decompose and query per component
- **Do NOT skip the same-technique check** — this is the core criterion

See [EXAMPLES.md](references/EXAMPLES.md) for worked examples of SATISFIED and INCONCLUSIVE verdicts.

---

See [POST_VERDICT.md](references/POST_VERDICT.md) for QRA quarantine, human review, promotion/rejection, and the QRA lifecycle flow.

---

# Returns: {"candidate_id": "EC-9670e932", "interview_file": "...", "status": "pending_review"}
```

This writes to `sparta_qra_candidates` collection and generates an `/interview` review form.

**Human review via /interview:**

```bash
# Launch review form in browser
.claude/skills/interview/run.sh --file <interview_file> --mode html
```

The review form asks:
1. Is the synthesized answer accurate?
2. Edit the answer if needed
3. Confirm control IDs
4. Confirm tactical tags
5. Final decision: approve / approve_with_edits / reject / defer

**Process the review result:**

```python
from runner import process_interview_result

result = process_interview_result("EC-9670e932", interview_result)
# approve → promotes to sparta_qra
# reject → moves to rejected_qras (GRPO training data)
# defer → stays as pending_review
```

### INCONCLUSIVE → Gap Review

When INCONCLUSIVE, generate a gap review form:

```python
from runner import generate_gap_review_questions

interview_file = generate_gap_review_questions(
    question="Given the F-36's use of FPGA vendors...",
    case_result=case_result,
    clarify_result=clarify_result,
)
```

The gap review asks:
1. Real gap or false gap?
2. Action: /dogpile research, adjust thresholds, manual QRA, or ignore

### Promotion/Rejection Functions

```python
from runner import promote_candidate_qra, reject_candidate_qra

# After human approves
promote_candidate_qra("EC-9670e932", edited_answer="...")  # → sparta_qra

# After human rejects (kept for GRPO training)
reject_candidate_qra("EC-9670e932", reason="Answer conflates HW and SW supply chain")
```

### QRA Lifecycle Flow

```
/create-evidence-case SATISFIED
  → quarantine_as_candidate_qra()
    → sparta_qra_candidates collection
    → /interview review form generated
      → Human reviews in browser/TUI
        → APPROVED → promote_candidate_qra() → sparta_qra
        → EDITED  → promote_candidate_qra(edited_answer) → sparta_qra
        → REJECTED → reject_candidate_qra(reason) → rejected_qras (GRPO)
        → DEFERRED → stays pending

/create-evidence-case INCONCLUSIVE
  → generate_gap_review_questions()
    → /interview gap review form
      → REAL GAP → /dogpile research task
      → FALSE GAP → adjust technique bridge thresholds
```

## Graph Model

- **ClaimNode**: Root question with verdict
- **DecompositionNode**: Given/Then structure with component queries (new in v4)
- **StrategyNode**: Verification approach (always "agent_driven" in v4)
- **EvidenceNode**: Individual QRA or skill result supporting the answer
- **VerdictNode**: Final judgment citing evidence


See [EXAMPLES.md](references/EXAMPLES.md) for the 50-question stress test, plausibility prompt optimization, and standards alignment.

## Common Mistakes

### WRONG: Regex-parsing control IDs from recall results
```python
import re
ids = re.findall(r'[A-Z]{2}-\d+', result_text)  # fragile regex
```

### RIGHT: Read structured fields from recall results
```python
control_ids = [qra["control_id"] for qra in recall_results]
```

### WRONG: Skipping the same-technique check and auto-passing
```python
if len(recall_results) > 0:
    verdict = "SATISFIED"  # entities exist but may span unrelated domains!
```

### RIGHT: Verify entities from different components share a technique
```python
# Check tactical_tags cluster into 1-2 techniques across components
# Check related_pairs for cross-component edges
# If no shared technique -> INCONCLUSIVE
```

### WRONG: Using /memory recall without specifying collections
```bash
.claude/skills/memory/run.sh recall --q "firmware tampering"  # searches everything
```

### RIGHT: Scope recall to sparta_qra collection
```bash
.claude/skills/memory/run.sh recall --q "firmware tampering" --collections sparta_qra --k 10
```

## Crosswalk Edge Reference (sparta_relationships)

When querying crosswalk chains, edges are stored in `sparta_relationships` with specific framework casing.

### Edge Types and Casing (CRITICAL)

| Edge Type | source_framework | target_framework | Count |
|-----------|-----------------|------------------|-------|
| CWE→SPARTA | `"CWE"` | `"SPARTA"` (uppercase) | 2,825+ |
| NIST→SPARTA | `"nist"` | `"sparta"` (lowercase) | 289+ per NIST |
| CAPEC→CWE | `"CAPEC"` | `"CWE"` | 1,212+ |
| CWE→CWE | `"cwe"` | `"cwe"` (lowercase) | parent/child |

**Always check both cases** when filtering for SPARTA targets:
```python
for tf_case in ["sparta", "SPARTA"]:
    resp = client.post("/list", json={
        "collection": "sparta_relationships",
        "filters": {"source_control_id": control_id, "target_framework": tf_case}
    })
```

### Crosswalk Lookup Paths

| Start | Path | Data Source |
|-------|------|-------------|
| CWE | CWE→SPARTA (direct edge) | SPARTA v3.1 `cwe_class_ids` |
| CWE | CWE→NIST→SPARTA (2-hop) | Heimdall `nist_control_ids` field + NIST→SPARTA edges |
| CWE | CWE→CAPEC→ATT&CK→SPARTA (4-hop) | MITRE curated `capec_ids`, `attack_technique_ids` |

### Key Document Fields

| Collection | Field | Contains |
|------------|-------|----------|
| `sparta_controls` (CWE) | `nist_control_ids` | NIST control IDs from Heimdall mapping |
| `sparta_controls` (CWE) | `capec_ids` | CAPEC attack pattern IDs |
| `sparta_controls` (SPARTA) | `cwe_class_ids` | CWE IDs this technique addresses |
| `sparta_controls` (any) | `source_framework` | Framework name (SPARTA, CWE, NIST, etc.) |

### Example: Finding SPARTA Targets for CWE-287

```python
# Path 1: Direct CWE→SPARTA edges (preferred)
resp = client.post("/list", json={
    "collection": "sparta_relationships",
    "filters": {"source_control_id": "CWE-287", "target_framework": "SPARTA"}
})
# Returns: DE-0001, IA-0001, etc.

# Path 2: NIST 2-hop (for unmapped CWEs like CWE-79)
cwe = fetch_control("CWE-79")  # nist_control_ids: ['SI-10']
for nist_id in cwe["nist_control_ids"]:
    resp = client.post("/list", json={
        "collection": "sparta_relationships",
        "filters": {"source_control_id": nist_id, "target_framework": "sparta"}  # lowercase!
    })
    # Returns: CM0001, CM0002, etc.
```
