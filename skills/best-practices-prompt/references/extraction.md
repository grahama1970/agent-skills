# Extraction Prompt Rules (24-36)

Rules for QRA generation, entity extraction, and source-grounded prompts. These supplement the core rules (0-15) in SKILL.md.

**Source:** Codified from CVE prompt review session (2026-04-17) and prior QRA generation incidents.

---

## 10-Gate Review Checklist

Before any extraction prompt goes to `/review-prompt`, verify all 10 gates pass:

| Gate | Question | Failure Mode |
|------|----------|--------------|
| 1 | Does the valid example obey every stated rule? | Example shows CWE label expansion but rules forbid it |
| 2 | Does each requested aspect have a matching pair_type? | Mission mentions "severity context" but no pair_type exists |
| 3 | Does each pair_type map to content the source actually contains? | exploitation_context requires explicit trigger but source lacks it |
| 4 | Are field names and meanings unambiguous? | `control_id` vs `cve_id` mismatch in CVE-specific prompt |
| 5 | Is every answer claim required to map to evidence? | Answer includes mechanism detail but evidence only supports product name |
| 6 | Are paraphrase boundaries operationally defined? | "Conservative paraphrase" without specifying what makes it conservative |
| 7 | Are modality and requirement strength preserved exactly? | Source says "potentially" but answer strengthens to certainty |
| 8 | Are placeholders preserved exactly? | `{control_id}` in system prompt but `{cve_id}` in user prompt |
| 9 | Do insufficiency rules align with permitted sparse outputs? | Rules say "verbatim evidence" but paraphrase is explicitly allowed elsewhere |
| 10 | Does the prompt explicitly prefer fewer pairs over weak pairs? | No explicit sparse preference leads to filler pairs |

**Gate 1 is the most common failure.** Valid examples are written quickly and often violate rules the author just wrote. Review example JSON against every stated constraint.

---

## Rule 24: Evidence Must Cover All Claims (NON-NEGOTIABLE)

### Rule: `extraction-evidence-coverage`

Every factual proposition in an answer MUST be supported by at least one evidence quote. "At least one quote" is not enough — if the answer makes 3 claims, there must be quotes covering all 3.

### WRONG:
```json
{
  "answer": "CVE-2025-14905 is a heap buffer overflow in 389-ds-base affecting the schema_attr_enum_callback function in schema.c",
  "evidence_quotes": [
    {"quote": "A flaw was found in the 389-ds-base server", "relevance": "Product"}
  ]
}
```

**Why invalid:** The evidence supports only the product name. The heap buffer overflow classification and function/file details need their own quotes.

### RIGHT:
```json
{
  "answer": "CVE-2025-14905 is a heap buffer overflow in 389-ds-base affecting the schema_attr_enum_callback function in schema.c",
  "evidence_quotes": [
    {"quote": "A heap buffer overflow vulnerability exists in the `schema_attr_enum_callback` function within the `schema.c` file", "relevance": "Core definition with location"},
    {"quote": "A flaw was found in the 389-ds-base server", "relevance": "Affected product"}
  ]
}
```

### Validator check:
Extract noun phrases and technical artifacts from the answer. Verify each appears in at least one evidence quote or the admissible source text.

---

## Rule 25: No Background Knowledge Expansion (NON-NEGOTIABLE)

### Rule: `extraction-no-background-expansion`

If the source provides a code or identifier, do NOT expand it to a label using background knowledge. CWE-122 stays as "CWE-122" unless the source explicitly says "Heap-based Buffer Overflow".

### WRONG:
```json
{
  "answer": "CVE-2025-14905 is classified as CWE-122 (Heap-based Buffer Overflow).",
  "evidence_quotes": [{"quote": "CWE-122", "relevance": "Weakness ID"}]
}
```

**Why invalid:** The source only provides `CWE-122`. The label "Heap-based Buffer Overflow" is background knowledge.

### RIGHT:
```json
{
  "answer": "CVE-2025-14905 is mapped to CWE-122 in the provided weakness data.",
  "evidence_quotes": [{"quote": "CWE-122", "relevance": "Explicit CWE mapping"}]
}
```

### Common expansion patterns to block:
- CWE IDs → weakness names
- CVE IDs → vulnerability names
- CAPEC IDs → attack pattern names
- NIST control IDs → control names (unless `name` field provided)
- ATT&CK technique IDs → technique names

---

## Rule 26: Pair-Type Trigger Conditions Must Be Explicit (HIGH)

### Rule: `extraction-explicit-triggers`

Every pair_type definition MUST specify what source content enables it. Actor mentions alone do not enable exploitation_context — explicit methods/vectors/conditions do.

### WRONG:
```
- exploitation_context: Use when the description mentions how the vulnerability is exploited.
```

**Why wrong:** "How it is exploited" is subjective. "Remote attacker" is not exploitation context.

### RIGHT:
```
- exploitation_context:
  Use only if description explicitly states an exploitation method, attack vector, precondition, or triggering condition.
  "Remote attacker" or "local attacker" alone is not enough unless the method, vector, or condition is also explicitly stated.
  Trigger phrases that enable exploitation_context: "via", "through", "by sending", "when", "if", "because", "crafted", "specially crafted".
  Do not infer attack paths.
```

### Include trigger helper functions in the validator:
```python
def can_emit_exploitation_context(description: str) -> bool:
    trigger_markers = [
        "via ", "through ", "by sending", "when ", "if ",
        "by ", "because ", "crafted", "specially crafted"
    ]
    desc = description.lower()
    return any(marker in desc for marker in trigger_markers)
```

---

## Rule 27: Modality Preservation Is Non-Negotiable (NON-NEGOTIABLE)

### Rule: `extraction-preserve-modality`

Hedged language in the source MUST stay hedged in the output. "Potentially" → "potentially", "could" → "could", "may" → "may". Never strengthen to certainty.

### WRONG:
| Source | Answer |
|--------|--------|
| "potentially allowing a remote attacker" | "allows a remote attacker" |
| "could lead to" | "leads to" |
| "may result in" | "results in" |

### RIGHT:
| Source | Answer |
|--------|--------|
| "potentially allowing a remote attacker" | "could potentially allow a remote attacker" |
| "could lead to" | "could lead to" |
| "may result in" | "may result in" |

### Validator check:
Extract modality markers from source. If source contains `{potentially, could, may, might, can}` and answer contains the same claim without the marker, reject.

---

## Rule 28: Metadata Is Not Substantive Content (HIGH)

### Rule: `extraction-metadata-excluded`

Fields marked as "metadata" in the prompt MUST NOT appear in substantive answer content. Status fields, timestamps, version numbers used for administration are not evidence.

### WRONG:
```json
{
  "question": "What does CVE-2025-14905 mean for defenders?",
  "answer": "CVE-2025-14905 is fully analyzed and therefore high confidence for defenders.",
  "evidence_quotes": [{"quote": "Analyzed", "relevance": "Status field"}]
}
```

**Why invalid:** `vuln_status` is metadata. "Analyzed" is an administrative state, not vulnerability substance.

### Explicitly call out metadata fields in the prompt:
```
FIELD USAGE RULES
- vuln_status is metadata only. Do not mention it in any answer.
- last_modified is metadata only. Do not cite as evidence.
```

---

## Rule 29: At Most One Pair Per Pair Type (HIGH)

### Rule: `extraction-one-per-type`

Each pair_type can appear at most once in the output. Multiple CWE IDs go in one weakness_context pair, not N pairs.

### WRONG:
```json
{
  "pairs": [
    {"pair_type": "weakness_context", "answer": "CWE-79"},
    {"pair_type": "weakness_context", "answer": "CWE-89"}
  ]
}
```

### RIGHT:
```json
{
  "pairs": [
    {"pair_type": "weakness_context", "answer": "CVE-2024-99999 is mapped to CWE-79 and CWE-89 in the provided weakness data."}
  ]
}
```

### Validator check:
```python
seen_pair_types = set()
for pair in response.pairs:
    if pair.pair_type in seen_pair_types:
        raise ValueError(f"duplicate pair_type: {pair.pair_type}")
    seen_pair_types.add(pair.pair_type)
```

---

## Rule 30: Pair Types Must Cover Distinct Aspects (HIGH)

### Rule: `extraction-distinct-aspects`

Each pair must contribute unique information. Repeating the same content in different pair_types wastes slots and violates distinctness.

### WRONG:
```json
{
  "pairs": [
    {"pair_type": "vulnerability_description", "answer": "CVE-X is a heap buffer overflow."},
    {"pair_type": "impact_description", "answer": "CVE-X is a heap buffer overflow."}
  ]
}
```

**Why invalid:** The second pair repeats the definition instead of describing consequences.

### Validator check:
Normalize answers and compare. If Jaccard similarity > 0.8, reject for near-duplication.

---

## Rule 31: Control ID Must Appear in Question (HIGH)

### Rule: `extraction-id-in-question`

Every question MUST contain the exact control/CVE/CWE ID. "What is this vulnerability?" fails; "What is CVE-2025-14905?" passes.

### WRONG:
```json
{"question": "What is this heap buffer overflow vulnerability?"}
```

### RIGHT:
```json
{"question": "What is CVE-2025-14905 according to NVD?"}
```

### Validator check:
```python
if pair.control_id not in pair.question:
    raise ValueError("question must contain exact control_id")
```

---

## Rule 32: Valid Examples Must Pass All Stated Rules (NON-NEGOTIABLE)

### Rule: `extraction-example-rule-consistency`

Before finalizing a prompt, systematically check the valid example against every rule. This is Gate 1 of the 10-gate checklist. Most prompt failures come from examples that violate their own rules.

### Checklist:
- [ ] Does the example evidence cover all answer claims? (Rule 24)
- [ ] Does the example expand any IDs without source text? (Rule 25)
- [ ] Does each pair_type have source text that triggers it? (Rule 26)
- [ ] Is all hedged language preserved? (Rule 27)
- [ ] Does any answer use metadata fields? (Rule 28)
- [ ] Is there at most one pair per pair_type? (Rule 29)
- [ ] Are pairs distinct in content? (Rule 30)
- [ ] Does every question contain the control ID? (Rule 31)

---

## Rule 33: Invalid Examples Must Teach Specific Failures (HIGH)

### Rule: `extraction-invalid-examples-specific`

Invalid examples must show WHY they're invalid with the specific rule violated. Generic "this is wrong" teaches nothing.

### WRONG:
```
### Invalid Example:
{"answer": "CVE-X has a CVSS score of 9.8"}

WHY INVALID: This is not supported.
```

### RIGHT:
```
### Invalid Example 3: Invented CVSS score
{
  "pairs": [
    {"answer": "CVE-2025-14905 has a CVSS score of 9.8 (Critical)."}
  ]
}

WHY INVALID:
CVSS score is not present in the admissible source fields. The prompt's DO NOT USE list explicitly forbids "CVSS scores unless explicitly present in description."
```

### Invalid example categories to cover:
1. Background knowledge expansion (CWE label from ID)
2. Actor-only exploitation context ("remote attacker" without method)
3. Affected detail over-claims (function/file without evidence)
4. Metadata as substance (vuln_status in answer)
5. Duplicate pair types (same aspect twice)
6. Invented severity ("critical" inferred from consequences)
7. Evidence coverage gaps (claims without quotes)

---

## Rule 34: Three Layers Must Agree (NON-NEGOTIABLE)

### Rule: `extraction-three-layer-agreement`

The prompt, examples, and validator must enforce the same boundaries. If the prompt forbids CWE label expansion but the validator doesn't check for it, the rule has no teeth.

### The three layers:
1. **Written rules** — prose instructions in the prompt
2. **Valid/invalid examples** — concrete demonstrations
3. **Pydantic validator** — runtime enforcement

### Agreement checklist:
| Rule | In Prompt | In Example | In Validator |
|------|-----------|------------|--------------|
| No CWE expansion | "Do not expand CWE IDs" | Invalid example shows expansion | `if "(" in answer and "CWE-" in answer: reject` |
| Evidence coverage | "Every claim must have evidence" | Valid example has quote per claim | Token extraction + coverage check |
| One per pair_type | "At most one pair per pair_type" | Valid example has 4 unique types | `seen_pair_types` dedup check |

### If a layer is missing, the rule will be violated:
- Prompt says it but no example → LLM ignores it
- Example shows it but validator doesn't check → violations slip through
- Validator checks but prompt doesn't explain → LLM doesn't know the rule

---

## Rule 35: Field Names Should Match Domain (MEDIUM)

### Rule: `extraction-domain-field-names`

Use domain-specific field names, not generic ones inherited from a broader system. `cve_id` in a CVE prompt, not `control_id`.

### WRONG:
```
# CVE-specific prompt using generic field name
cve_id: {control_id}
```

### RIGHT:
```
# CVE-specific prompt using CVE field name
cve_id: {cve_id}
```

### Why this matters:
- Reduces mental translation for reviewers
- Makes prompt inheritance explicit (if you copy a generic prompt, rename fields)
- Prevents placeholder mismatches between system and user prompts

---

## Rule 36: Sparse Output Preference Must Be Explicit (MEDIUM)

### Rule: `extraction-sparse-preference`

Every extraction prompt must explicitly state that fewer strong pairs are better than more weak pairs. Without this, LLMs fill available slots with filler.

### Required language:
```
Prefer fewer pairs over weak pairs.
Prefer 2 strong pairs over 4 weak pairs.
Do not create a pair just to fill an available pair_type slot.
```

### Validator support:
Set `max_length=4` on the pairs field but don't require 4. Check for near-duplicate answers and reject.

---

## Pydantic Validator Patterns

### Basic schema with enforcement:

```python
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict, model_validator

class PairType(str, Enum):
    vulnerability_description = "vulnerability_description"
    weakness_context = "weakness_context"
    impact_description = "impact_description"
    exploitation_context = "exploitation_context"
    affected_context = "affected_context"

class Confidence(str, Enum):
    high = "high"
    medium = "medium"

class EvidenceQuote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quote: str = Field(min_length=1, max_length=500)
    relevance: str = Field(min_length=1, max_length=200)

class QRAPair(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=300)
    reasoning: str = Field(min_length=1, max_length=200)
    answer: str = Field(min_length=1, max_length=600)
    pair_type: PairType
    cve_id: str = Field(min_length=1, max_length=64)
    evidence_quotes: List[EvidenceQuote] = Field(min_length=1)
    confidence: Confidence
    actionable_for: str

class ControlQRAResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pairs: List[QRAPair] = Field(max_length=4)
    skipped_reason: Optional[str] = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def validate_global_constraints(self):
        if self.pairs and self.skipped_reason is not None:
            raise ValueError("skipped_reason must be null when pairs are present")
        if not self.pairs and not self.skipped_reason:
            raise ValueError("skipped_reason is required when pairs is empty")
        
        seen_pair_types = set()
        for pair in self.pairs:
            if pair.pair_type in seen_pair_types:
                raise ValueError(f"duplicate pair_type: {pair.pair_type}")
            seen_pair_types.add(pair.pair_type)
            
            if pair.cve_id not in pair.question:
                raise ValueError("question must contain exact cve_id")
        
        return self
```

### Post-parse semantic checks (beyond Pydantic):

```python
def can_emit_weakness_context(weaknesses: list[str]) -> bool:
    return bool(weaknesses)

def can_emit_impact_description(description: str) -> bool:
    impact_markers = [
        "denial of service", "dos", "remote code execution", "rce",
        "information disclosure", "privilege escalation", "execute arbitrary",
        "cause a crash", "memory corruption", "data leak", "bypass"
    ]
    desc = description.lower()
    return any(marker in desc for marker in impact_markers)

def can_emit_exploitation_context(description: str) -> bool:
    trigger_markers = [
        "via ", "through ", "by sending", "when ", "if ",
        "by ", "because ", "crafted", "specially crafted"
    ]
    desc = description.lower()
    return any(marker in desc for marker in trigger_markers)

def can_emit_affected_context(description: str) -> bool:
    affected_markers = [
        "affected", "in the ", "a flaw was found in", "exists in",
        "component", "function", "file", "version", "before ", "through "
    ]
    desc = description.lower()
    return any(marker in desc for marker in affected_markers)

def check_no_cwe_expansion(answer: str, weaknesses: list[str]) -> bool:
    """Reject if answer contains CWE label expansion."""
    import re
    cwe_with_label = re.search(r'CWE-\d+\s*\([^)]+\)', answer)
    if cwe_with_label:
        label = cwe_with_label.group()
        # Check if the full label (with parenthetical) appears in source
        for w in weaknesses:
            if label in w:
                return True
        return False  # Expansion not in source
    return True

def check_evidence_coverage(answer: str, evidence_quotes: list[dict]) -> bool:
    """Verify all technical terms in answer appear in evidence."""
    import re
    # Extract technical terms (backticked items, version numbers, file names)
    terms = re.findall(r'`[^`]+`|[\w.-]+\.c|[\w.-]+\.py|\d+\.\d+', answer)
    evidence_text = ' '.join(q['quote'] for q in evidence_quotes)
    for term in terms:
        term_clean = term.strip('`')
        if term_clean not in evidence_text:
            return False
    return True
```

---

## Integration with /review-prompt

When `/review-prompt` evaluates an extraction prompt:

1. Load the 10-gate checklist (this document)
2. Parse valid example from prompt
3. Check each gate against the example
4. Report gate failures before LLM review begins
5. LLM review focuses on semantic quality, not structural violations

This prevents wasting LLM tokens on prompts that fail basic structural checks.
