## QRA Evaluation (Roadmap)

Prompt-lab currently supports taxonomy classification. Based on real-world usage in SPARTA QRA generation, the following enhancements are planned:

### Current Limitations

- Only evaluates conceptual/tactical tag F1 scores
- No citation grounding validation
- No multi-item response support (QRA generates 4-7 items per input)
- No hallucination detection
- No question type diversity metrics

### Planned Features

**QRA Evaluation Mode:**

```bash
./run.sh eval-qra --prompt qra_v2 --model deepseek --cases 5
```

**New Metrics:**

- Citation grounding rate (% of citations that match source text verbatim)
- Question type distribution (simple/medium/complex/reversal_curse)
- Persona distribution (lay_person/project_manager/cybersecurity_expert)
- Hallucination count (citations not found in source)
- Duplicate answer detection
- Confidence distribution (strong/partial/inference)

**Citation Grounding Validation:**
Uses rapidfuzz to verify every citation is an exact verbatim excerpt from source text:

```python
def validate_citation(citation: str, source_text: str, threshold: float = 0.85) -> bool:
    from rapidfuzz import fuzz
    return fuzz.partial_ratio(citation.lower(), source_text.lower()) >= threshold * 100
```

### Key Learnings from SPARTA QRA Generation

**What Worked:**

| Technique                                      | Outcome                                              |
| ---------------------------------------------- | ---------------------------------------------------- |
| "Think like a LEGAL LLM - cite precedent"      | Enforced verbatim citation behavior                  |
| "STRICT GROUNDING - if not in text, don't add" | Eliminated hallucinated mitigation advice            |
| "Generate ALL reasonable questions"            | Increased diversity from 1-2 to 4-7 QRAs per input   |
| "Each extracts DIFFERENT information"          | Reduced duplicate answers                            |
| "EXACT verbatim excerpt" for citations         | Stopped control ID citations, enforced text snippets |

**What Didn't Work:**

| Anti-Pattern                       | Problem                                 |
| ---------------------------------- | --------------------------------------- |
| Template examples in prompts       | Caused repetitive outputs               |
| Generic "be grounded" instructions | Too vague, still hallucinated           |
| "Generate ONE per type"            | Limited coverage of source material     |
| No deduplication guidance          | Repeated same answer in different words |
| "Citation: [CONTROL_ID]"           | Generated IDs instead of text excerpts  |

### Refined QRA Prompt Template

The following prompt pattern generates properly grounded QRAs:

```
You are a space-based cybersecurity expert generating Question-Reasoning-Answer pairs
for SPARTA. Think like a LEGAL LLM: every claim MUST cite precedent from the provided text.

STRICT GROUNDING RULE: If information is NOT in the provided text, you CANNOT include
it in your answer. Do NOT add external knowledge, mitigation advice, or implications
not directly stated.

Return JSON: {"items": [{"question": "...",
  "question_type": "simple|medium|complex|reversal_curse",
  "questioner_persona": "lay_person|project_manager|cybersecurity_expert",
  "reasoning": "...", "answer": "...",
  "citations": ["EXACT verbatim excerpt from text"],
  "confidence": "strong|partial",
  "conceptual_tags": [], "tactical_tags": []}]}

GENERATE ALL REASONABLE NON-DUPLICATE QUESTIONS:
- Simple, Medium, Complex levels + Reversal curse where applicable
- Each extracts DIFFERENT information from the text
- NEVER add information not in the source text

TAXONOMY: C=[Corruption,Fragility,Loyalty,Precision,Resilience,Stealth],
T=[Detect,Evade,Exploit,Harden,Isolate,Model,Persist,Restore]
```

### Implementation Status

- [x] Create [`citation_validator.py`](citation_validator.py) with rapidfuzz
- [x] Add `QRAEvalSummary`, `QRAGroundedTestCase`, `QRAGroundedResult` dataclasses to [`evaluation.py`](evaluation.py)
- [x] Create [`ground_truth/qra_grounded.json`](ground_truth/qra_grounded.json) schema
- [x] Create example prompt [`prompts/qra_grounded_v1.txt`](prompts/qra_grounded_v1.txt)
- [x] Add `load_qra_grounded_truth()` function to [`evaluation.py`](evaluation.py)
- [x] Add `eval-qra` command to [`prompt_lab.py`](prompt_lab.py) CLI
- [x] [`run.sh`](run.sh) automatically supports eval-qra (passes all args to CLI)
- [x] QRA-specific metrics in evaluation output

### Files Added

- [`citation_validator.py`](citation_validator.py) - Citation grounding validation with rapidfuzz fuzzy matching
- [`ground_truth/qra_grounded.json`](ground_truth/qra_grounded.json) - Schema with source_text and citation requirements
- [`prompts/qra_grounded_v1.txt`](prompts/qra_grounded_v1.txt) - Working prompt template from SPARTA production use

### Usage

The `eval-qra` command is now available:

```bash
