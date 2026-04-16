---
name: best-practices-prompt
description: >
  Rules for writing clear, testable LLM prompts. Eliminates vagueness, enforces concrete output specs,
  grounding in source material, and deterministic verifiability. Gate before /review-prompt.
triggers:
  - best practices prompt
  - prompt conventions
  - write prompt
  - prompt writing
  - improve prompt
  - prompt quality
  - vague prompt
  - prompt review prep
license: MIT
metadata:
  prompt_types:
    - system prompts
    - skill prompts
    - extraction prompts
    - classification prompts
    - generation prompts

provides:
  - best-practices-prompt
composes:
  - review-prompt
  - prompt-lab

taxonomy:
  - prompt-engineering
  - llm
---

# Prompt Best Practices (Project Skill)

This skill is a curated set of rules for writing LLM prompts in this repo. Every prompt — system prompts, skill prompts, extraction templates, generation instructions — MUST pass these rules before going to `/review-prompt`.

**The core problem:** Agents write vague, hand-wavy prompts that sound reasonable but produce garbage output. "Analyze the document and extract relevant information" is not a prompt — it is a wish. This skill exists to kill that pattern.

## When to Apply

Use this skill whenever you:
- write a new system prompt or skill prompt template
- modify an existing prompt in a `.txt`, `.md`, or inline Python string
- build prompts for `/scillm`, `/code-runner`, `/prompt-lab`, or any LLM call
- prepare a prompt for `/review-prompt` review

## Categories (priority order)

1. Clarity (CRITICAL): `clarity-` — every sentence must have one unambiguous meaning
2. Specificity (CRITICAL): `specificity-` — concrete nouns, verbs, quantities, formats
3. Output Specification (HIGH): `output-` — exact schema, format, and constraints
4. Grounding (HIGH): `grounding-` — reference real data, files, schemas, examples
5. Structure (MEDIUM): `structure-` — logical ordering, sections, progressive disclosure
6. Testability (MEDIUM): `testability-` — how do you know the output is correct?
7. Efficiency (LOW): `efficiency-` — token budget, context window management

## Compliance Prompt Rules (STOP — read these first if writing SPARTA/NIST/CWE prompts)

These rules apply to ANY prompt that operates on cross-framework compliance data (evidence cases, crosswalk chains, control glossaries, QRA results). Violations cause 0% accuracy.

| Rule | What it prevents | Link |
|------|-----------------|------|
| `grounding-match-pipeline-schema` | Prompt invents its own schema instead of using the pipeline's actual output fields. Result: model can't parse the payload. | [Rule 15](#rule-15) |
| `grounding-vocabulary-control` | Prompt says "different framework" without listing valid frameworks or telling the model how to identify them. Result: model guesses wrong. | [Rule 6](#rule-6) |
| `grounding-cite-source-fields` | Prompt says "use the glossary" without naming `glossary[].framework`, `glossary[].description`. Result: model uses wrong fields. | [Rule 10](#rule-10) |

**Before writing a compliance prompt:**
1. Find the function that produces the payload (e.g., `_build_evidence_case()` in `runner.py`)
2. Read its output — field names, types, nesting, framework identifiers
3. Use those exact field paths in the prompt
4. Include the framework closed vocabulary: SPARTA, CWE, NIST, CAPEC, ATT&CK, D3FEND

## Prompt Type Routing

Load specialized rulesets based on prompt type:

| Writing a... | Load this reference | Key rules |
|--------------|---------------------|-----------|
| **Extraction prompt** (QRA, entity, control extraction) | [`references/extraction.md`](references/extraction.md) | 24-36: source admissibility, distinctness, modality preservation |
| **Inference/filter prompt** (classification, ranking, JSON output) | [`references/inference-time.md`](references/inference-time.md) | 16-23: format anchor, anti-MCQ, gates vs ranking, Pydantic patterns |
| **Any prompt** | Core rules below | 0-15: no weasel words, concrete nouns, schema, examples |
| **Debugging failures** | [`references/incidents.md`](references/incidents.md) | Pattern library of past prompt failures |

## Quick Reference (Core Rules 0-15)

| Rule | Code | One-liner |
|------|------|-----------|
| 0 | `structure-rationale-header` | Every prompt starts with Purpose/Consumer/Why header |
| 1 | `clarity-no-weasel-words` | No "relevant", "appropriate", "ensure", "comprehensive" |
| 2 | `specificity-name-the-format` | Exact JSON schema, not "return JSON" |
| 3 | `output-show-one-example` | Full input→output example, not fragments |
| 4 | `clarity-imperative-voice` | "Extract X" not "you should try to extract X" |
| 5 | `structure-task-before-context` | State task, THEN provide context |
| 6 | `grounding-vocabulary-control` | List ALL valid categories explicitly |
| 7 | `output-rejection-criteria` | Tell model what makes output WRONG |
| 8 | `specificity-concrete-nouns` | "control ID, title, page" not "the information" |
| 9 | `specificity-quantity-not-quality` | "2-3 sentences" not "brief summary" |
| 10 | `grounding-cite-source-fields` | Name exact field paths: `doc.lineage.entity_ids` |
| 11 | `structure-one-task` | One prompt = one task, chain for complex work |
| 12 | `structure-schema-last` | Output schema at END, right before generation |
| 13 | `output-nothing-but` | "Return ONLY this JSON, no other text" |
| 14 | `testability-deterministic-check` | Define how to verify output is correct |
| 15 | `grounding-match-pipeline-schema` | Prompt schema must match pipeline payload (compliance) |

---

## Rule 0: Every Prompt Must Have a Rationale Header (NON-NEGOTIABLE)

### Rule: `structure-rationale-header`

Every prompt file MUST begin with a rationale block that answers three questions before the prompt itself starts. This block is for humans reviewing the prompt — it is NOT sent to the LLM.

```
# RATIONALE (not sent to LLM)
# Purpose: What does this prompt produce? (e.g., "Extracts CWE→SPARTA crosswalk chains from evidence cases")
# Consumer: What system/skill receives the output? (e.g., "SPARTA Explorer NLG pipeline, step 4")
# Why this matters: What breaks if this prompt is wrong? (e.g., "Users get hallucinated attack paths")
```

### Why this is Rule 0

Without rationale, prompts become orphans. Six months later, nobody knows:
- **What** the prompt is for — is it extraction? classification? generation?
- **Who** consumes the output — a Pydantic model? a human? another LLM?
- **Why** it exists — what user-facing behavior depends on it?

This is how "word salad" prompts survive: nobody can tell if the prompt is wrong because nobody knows what right looks like. The rationale makes the prompt auditable — a reviewer can check "does this prompt actually produce what the rationale says it should?"

### WRONG:
```
You are a cybersecurity analyst producing actionable insights
from cross-framework evidence.
[... 50 lines of instructions ...]
```

### RIGHT:
```
# RATIONALE (not sent to LLM)
# Purpose: Generate structured cybersecurity analysis from SPARTA evidence cases
# Consumer: SPARTA Explorer API → /api/query response → "answer" field
# Why this matters: This is the user-facing answer. Bad output = user sees nonsense.
# Input: EVIDENCE_CASE JSON with glossary, crosswalk_chains, prior_qra_evidence
# Output: JSON with decision, answer, citations. Validated by EvidenceCaseResponse Pydantic model.
# Last reviewed: 2026-04-09 by Graham

You are a NIST/SPARTA cross-framework evidence analyst.

Task: Given an EVIDENCE_CASE, produce a structured cybersecurity analysis...
```

### What belongs in the rationale:
- **Purpose** — one sentence: what does this prompt do
- **Consumer** — what code/system receives the output (skill name, API endpoint, Pydantic model)
- **Why this matters** — what breaks if the output is wrong
- **Input** — what data the prompt receives (field names, not vibes)
- **Output** — schema name or format spec
- **Last reviewed** — date and person, so staleness is visible

### How agents should handle the rationale:
When calling `run.sh review`, the rationale block (lines starting with `#`) is parsed separately and shown in the review page header — not mixed into the prompt body. When the prompt is sent to the LLM, strip lines starting with `# RATIONALE` through the first non-comment line.

---

## Rule 1: No Weasel Words (NON-NEGOTIABLE)

### Rule: `clarity-no-weasel-words`

Weasel words are adjectives and adverbs that feel meaningful but carry zero information for an LLM. They are the #1 source of vague prompts. If a human reader could reasonably ask "what do you mean by that?", it is a weasel word.

**Banned words and what to replace them with:**

| Weasel Word | Why It Fails | Replace With |
|-------------|-------------|-------------|
| "relevant" | Relevant to what? | Name the specific fields or criteria |
| "appropriate" | By whose standard? | State the standard explicitly |
| "comprehensive" | How comprehensive? | "All X" or "at least N" |
| "thorough" | Unmeasurable | Enumerate what must be checked |
| "important" | Important how? | State the consequence of missing it |
| "ensure" | Not an action verb | "Check that X. If not, do Y." |
| "consider" | Does not commit to action | "If X, then Y. Otherwise Z." |
| "properly" | Properly by what definition? | State the exact criteria |
| "meaningful" | Subjective | Define the threshold |
| "high-quality" | Unmeasurable | List the quality criteria explicitly |
| "as needed" | Who decides? | State the condition: "if X, then Y" |
| "various" | How many? Which ones? | List them or say "all" |
| "leverage" | Corporate jargon for "use" | "use" |
| "utilize" | Same | "use" |

### WRONG:
```
Analyze the document and extract relevant information.
Ensure comprehensive coverage of important topics.
Provide appropriate responses as needed.
```

### RIGHT:
```
Extract every person name, organization, and date from the document.
Return them as a JSON array of objects: {"entity": "...", "type": "person|org|date", "page": N}.
If no entities are found on a page, omit that page from the output.
```

### Why this matters

On 2026-03-22, a QRA extraction prompt using "extract relevant security controls" produced 40% hallucinated controls because "relevant" gave the LLM permission to invent plausible-sounding controls. Replacing it with "extract only controls whose ID appears verbatim in the source text" dropped hallucinations to 2%.

---

## Rule 2: Name the Output Format Exactly (NON-NEGOTIABLE)

### Rule: `specificity-name-the-format`

Every prompt that expects structured output MUST specify the exact format. Not "return JSON" — return the exact JSON schema with field names, types, and constraints.

### WRONG:
```
Return the results as JSON.
```

```
Output a structured response with the key findings.
```

### RIGHT:
```
Return a JSON object with this exact schema:
{
  "controls": [
    {
      "id": "string — e.g. 'AC-2', 'SI-4'. Must match regex ^[A-Z]{2}-\\d+$",
      "title": "string — the control title from the source, verbatim",
      "source_page": "integer — 1-indexed page number where this control appears",
      "confidence": "float 0.0-1.0 — 1.0 if quoted verbatim, 0.7 if paraphrased"
    }
  ],
  "document_title": "string — from the PDF metadata or first heading",
  "total_pages_scanned": "integer"
}

Do not add fields not listed above.
Do not nest objects deeper than shown.
If a field cannot be determined, use null — never omit the key.
```

### Why this matters

"Return JSON" gives the LLM freedom to invent any schema. Every downstream consumer then needs to handle N possible shapes. Specifying the schema upfront means the output is parseable by a fixed Pydantic model — no guessing, no `get()` with fallbacks, no "try these 3 field names".

---

## Rule 3: Show One Complete Input/Output Example (NON-NEGOTIABLE)

### Rule: `output-show-one-example`

Every prompt that produces structured output MUST include at least one complete input/output example. Not a fragment — the full input and the full expected output.

### WRONG:
```
Extract entities from the text.
For example, you might find names like "John Smith".
```

### RIGHT:
```
## Example

Input text:
"On March 15, 2026, Dr. Sarah Chen from NIST published SP 800-171 Rev 3."

Expected output:
{
  "entities": [
    {"text": "March 15, 2026", "type": "date", "start_char": 3, "end_char": 17},
    {"text": "Dr. Sarah Chen", "type": "person", "start_char": 19, "end_char": 33},
    {"text": "NIST", "type": "organization", "start_char": 39, "end_char": 43},
    {"text": "SP 800-171 Rev 3", "type": "document_id", "start_char": 54, "end_char": 70}
  ]
}

Note: start_char and end_char are 0-indexed byte offsets into the input string.
```

### Why this matters

Examples are worth 100 lines of instruction. The LLM learns the output shape, the level of detail expected, the naming conventions, and the edge cases from a single concrete example. Without an example, each instruction sentence is another opportunity for misinterpretation.

---

## Rule 4: Imperative Voice, Not Descriptive (HIGH)

### Rule: `clarity-imperative-voice`

Prompts are instructions, not descriptions. Use imperative verbs ("extract", "return", "list", "check") not descriptive language ("you should", "it would be good to", "the system is expected to").

### WRONG:
```
You are a helpful assistant that analyzes documents.
You should try to find security controls and it would be
good to return them in a structured format. The system is
expected to handle edge cases appropriately.
```

### RIGHT:
```
You are a NIST SP 800-53 control extractor.

Task: Extract every security control reference from the input document.

Steps:
1. Scan each page for control IDs matching the pattern [A-Z]{2}-\d+ (e.g., AC-2, SI-4).
2. For each match, extract the control ID, the surrounding sentence, and the page number.
3. Return the results as a JSON array (schema below).

If a page contains no control references, skip it.
If a control ID appears multiple times, include every occurrence with its page number.
```

---

## Rule 5: Task Before Context (HIGH)

### Rule: `structure-task-before-context`

State what you want the LLM to do BEFORE providing the context it needs to do it. Humans read top-to-bottom. If you dump 2000 tokens of context before stating the task, the LLM has no frame for what matters in that context.

### WRONG:
```
Here is a 500-line document about network security policies at Acme Corp.
The document covers firewalls, VPNs, access control, and incident response.
It was written in 2024 and updated in 2025.
[... 2000 tokens of context ...]

Extract the access control policies.
```

### RIGHT:
```
Task: Extract every access control policy from the document below.
Return each policy as: {"policy_id": "...", "description": "...", "page": N}

Context: The document is Acme Corp's network security policy (2024, updated 2025).
Only extract from sections titled "Access Control" or "AC-*".
Ignore firewall rules, VPN configs, and incident response procedures.

<document>
[... document content ...]
</document>
```

---

## Rule 6: Vocabulary Control (HIGH)

### Rule: `grounding-vocabulary-control`

If the prompt expects the LLM to classify, tag, or categorize, provide the **complete closed vocabulary** in the prompt. Never say "categorize into appropriate categories" — list every valid category.

### WRONG:
```
Classify each finding by severity.
```

### RIGHT:
```
Classify each finding into exactly one severity level:
- "critical": exploitable without authentication, data loss or RCE
- "high": exploitable with low-privilege access, significant impact
- "medium": requires specific conditions, moderate impact
- "low": informational, no direct exploit path
- "info": observation only, no security impact

Use these exact strings. Do not invent new severity levels.
If unsure between two levels, choose the higher severity.
```

### Why this matters

Without a closed vocabulary, LLMs invent plausible-sounding categories: "Critical", "CRITICAL", "Severe", "Very High", "P0". Every downstream consumer breaks. This is the same pattern that `/prompt-lab`'s self-correction loop fixes — but prevention is cheaper than correction.

---

## Rule 7: Rejection Criteria (HIGH)

### Rule: `output-rejection-criteria`

Tell the LLM what makes output WRONG, not just what makes it right. LLMs are biased toward producing *something* — they will hallucinate rather than return empty. Explicit rejection criteria give the LLM permission to say "nothing found".

### WRONG:
```
Extract all security vulnerabilities from the document.
```

### RIGHT:
```
Extract security vulnerabilities from the document.

A valid vulnerability MUST have ALL of:
1. A CVE ID, CWE ID, or specific software version mentioned
2. A description of the attack vector or impact
3. Traceable to a specific sentence in the source

Do NOT include:
- General security advice ("keep software updated")
- Hypothetical risks not tied to a specific finding
- Controls or mitigations (those are separate)

If the document contains no vulnerabilities meeting these criteria, return:
{"vulnerabilities": [], "note": "No vulnerabilities found matching criteria"}
```

---

## Rule 8: Concrete Nouns Over Abstract Concepts (CRITICAL)

### Rule: `specificity-concrete-nouns`

Replace every abstract noun with the concrete thing you actually mean. "Information" could mean anything — say "the control ID, title, and description" instead.

| Abstract | Concrete |
|----------|----------|
| "the information" | "the control ID, title, and source page" |
| "the data" | "the JSON array from `data.entities`" |
| "the results" | "the list of matched CVE IDs" |
| "the content" | "the text between `<document>` tags" |
| "the context" | "the 3 preceding sentences" |
| "the output" | "the JSON object matching the schema above" |
| "the document" | "the PDF text extracted by `/extract-pdf`" |
| "the findings" | "each row in the vulnerability table" |

---

## Rule 9: Quantities Not Qualities (MEDIUM)

### Rule: `specificity-quantity-not-quality`

Replace qualitative instructions with quantitative ones. "A brief summary" is subjective — "a summary of 2-3 sentences" is testable.

| Qualitative | Quantitative |
|-------------|-------------|
| "brief summary" | "2-3 sentence summary" |
| "detailed analysis" | "analysis covering at least: X, Y, and Z" |
| "a few examples" | "exactly 3 examples" |
| "keep it short" | "max 100 words" |
| "in depth" | "at least 500 words covering A, B, C" |
| "the most important" | "the top 5 by frequency" |
| "recent" | "from the last 30 days" |

---

## Rule 10: Cite Source Fields, Not Vibes (HIGH)

### Rule: `grounding-cite-source-fields`

When the prompt references input data, name the exact field paths, column names, or tag names. Never say "use the relevant fields from the input".

### WRONG:
```
Using the metadata from the document, generate a summary.
```

### RIGHT:
```
Using these fields from the input JSON:
- `document.title` — use as the summary heading
- `document.abstract` — base the summary on this text
- `document.authors[].name` — list in the "Authors" field
- `document.published_date` — format as YYYY-MM-DD

Ignore all other fields.
```

---

## Rule 11: One Prompt, One Task (MEDIUM)

### Rule: `structure-one-task`

A prompt should do one thing well. If you need extraction AND classification AND summarization, use three prompts chained together — not one mega-prompt that tries to do everything.

### WRONG:
```
Read this document. Extract all entities. Classify them by type.
Generate a summary. Identify security risks. Rate each risk.
Create a remediation plan. Format everything as a report.
```

### RIGHT:
```
# Prompt 1 (extraction)
Extract every entity from the document. Return as JSON array.

# Prompt 2 (classification) — receives output of Prompt 1
Classify each entity by type. Valid types: person, org, date, control_id.

# Prompt 3 (risk assessment) — receives output of Prompt 2
For each control_id entity, assess whether the document describes a gap.
```

**Exception:** Simple two-step tasks (extract + format) can share a prompt if the output schema covers both steps.

---

## Rule 12: Output Schema Goes Last, Not First (HIGH)

### Rule: `structure-schema-last`

Place the output schema and format instructions at the END of the prompt, immediately before the LLM generates. Long context (500+ tokens of instructions or input data) causes models to lose track of formatting instructions placed at the top. The schema is the last thing the model sees before generating — it stays in working memory.

### WRONG:
```
Return a JSON array of objects with keys: id, title, page.

You are a control extractor. The document below contains NIST controls.
[... 2000 tokens of context and instructions ...]
Extract all controls.
```

### RIGHT:
```
You are a control extractor.

Task: Extract all NIST controls from the document below.
[... context and instructions ...]

Constraints:
- Only include controls whose ID appears verbatim in the text
- Do not add commentary outside the JSON

Output format — return ONLY this JSON, no other text:
[{"id": "AC-2", "title": "Account Management", "page": 3}]
```

### Why this matters

Research from Lakera, Palantir, and PromptingGuide.ai confirms: output schema instructions placed early in long prompts get "forgotten" — the model reverts to freeform text. Placing the schema last means it is the freshest instruction in the model's attention window when generation begins.

---

## Rule 13: Explicit Negative Instructions for Clean Output (HIGH)

### Rule: `output-nothing-but`

When you need raw structured output (JSON, CSV, XML), include an explicit "output NOTHING but" instruction. Without it, LLMs add commentary: "Here is your JSON:", "I found the following:", "Let me analyze this...". This breaks every downstream parser.

### WRONG:
```
Return the extracted entities as JSON.
```

### RIGHT:
```
Output NOTHING but the raw JSON array. No commentary, no markdown fencing,
no "Here is" preamble, no explanation after the JSON. Start with [ and end with ].
```

### When NOT to use this rule:
- When the prompt is for human-readable output (summaries, explanations)
- When you're using a structured output API that enforces schema (e.g., OpenAI function calling, Anthropic tool use)

---

## Rule 14: Constraints After Task (MEDIUM)

### Rule: `structure-constraints-after-task`

Put constraints, edge cases, and "do not" instructions AFTER the main task and format spec. Constraints are modifiers on a task the LLM already understands — they are meaningless without the task context.

### Canonical prompt structure:
```
## Role
[1 sentence: who the LLM is acting as]

## Task
[What to do — imperative voice, concrete nouns]

## Context
[Input data, source material, delimited with tags]

## Constraints
- Do not include X
- If Y, then Z
- Max N items
- Prefer A over B when ambiguous

## Output Format
[Exact schema — placed LAST per Rule 12]
```

---

## Rule 13: Every Prompt Must Be Testable (MEDIUM)

### Rule: `testability-deterministic-check`

Before writing a prompt, answer: "How will I verify the output is correct?" If the answer is "I'll read it and see if it looks right" — the prompt is too vague. Good prompts produce output that can be checked by code.

**Testable prompt outputs:**
- JSON that validates against a Pydantic model
- Entity lists checkable against source text (do the entities appear verbatim?)
- Classifications checkable against a ground truth set
- Counts verifiable by grep/regex on the source

**Untestable prompt outputs (rewrite these):**
- "A good summary" — good by what metric?
- "Relevant insights" — relevant to whom?
- "Appropriate recommendations" — who judges?

### Integration with `/prompt-lab`

Every prompt template stored in `/prompt-lab` MUST have a corresponding ground truth file. If you can't create ground truth, your prompt is too subjective — break it into testable sub-tasks.

---

## Rule 14: No Redundant Preamble (LOW)

### Rule: `efficiency-no-preamble`

Do not waste tokens on pleasantries, meta-commentary, or restating what the LLM already knows about itself.

### WRONG:
```
You are a highly capable AI assistant with expertise in many fields.
Your goal is to help the user by providing accurate and helpful responses.
Please carefully read the following document and use your best judgment
to analyze it thoroughly. Take your time and think step by step.
I'm going to provide you with a document that I'd like you to analyze.
This is an important task and I appreciate your help with it.
```

### RIGHT:
```
You are a NIST SP 800-53 control extractor.
Extract control IDs from the document below.
```

The 6-line preamble adds zero information. The 2-line version tells the LLM exactly what role it plays and what to do.

---

## Prompt Template Checklist

Before sending any prompt to `/review-prompt`, verify:

- [ ] **Rationale header** — Purpose, Consumer, Why this matters, Input, Output, Last reviewed
- [ ] **No weasel words** — grep for: relevant, appropriate, comprehensive, thorough, ensure, consider, properly, meaningful, various, as needed
- [ ] **Output format specified** — exact JSON schema or markdown structure with field names and types
- [ ] **At least one example** — complete input/output pair, not a fragment
- [ ] **Imperative voice** — starts with a verb, not "you should"
- [ ] **Task before context** — the LLM knows what to do before seeing the data
- [ ] **Closed vocabulary** — every classification/tag has an explicit list of valid values
- [ ] **Rejection criteria** — the prompt defines what makes output WRONG
- [ ] **Concrete nouns** — no "the information", "the data", "the results"
- [ ] **Quantities not qualities** — "2-3 sentences" not "brief"
- [ ] **Source fields cited** — exact field paths, not "the relevant fields"
- [ ] **Single task** — does one thing; chain prompts for multi-step workflows
- [ ] **Testable output** — can be validated by code, not just human reading
- [ ] **No preamble fluff** — no "you are a helpful assistant" padding

## Common Mistakes

### WRONG: Abstract task description
```
Analyze the document and provide insights about the security posture.
```

### RIGHT: Concrete extraction with schema
```
Extract every security control gap from the document.
A gap is: a control ID (e.g., AC-2) mentioned as "not implemented",
"partially implemented", or "planned".

Return as JSON:
[{"control_id": "AC-2", "status": "not_implemented", "evidence": "quote from doc", "page": 3}]

If no gaps found, return [].
```

### WRONG: Hoping the LLM figures out the format
```
Summarize the key points of this paper.
```

### RIGHT: Specifying format and scope
```
Write a 3-sentence summary of this paper covering:
1. The problem statement (sentence 1)
2. The method or approach (sentence 2)
3. The main result with a number if available (sentence 3)

Use present tense. Do not start any sentence with "This paper".
```

### WRONG: Dumping everything into one prompt
```python
PROMPT = f"""You are an expert. Here is {doc}. Extract entities, classify them,
find relationships, generate QRAs, assess quality, and format as a report.
Make sure everything is accurate and comprehensive."""
```

### RIGHT: Chained prompts via skill composition
```python
# Step 1: /extract-entities
entities = extract(doc)
# Step 2: /taxonomy
tagged = classify(entities)
# Step 3: /doc2qra
qras = generate_qras(doc, tagged)
# Each step has its own focused, testable prompt
```

### WRONG: Inline Python string prompts without version control
```python
response = llm.chat("Analyze this and give me the important stuff: " + text)
```

### RIGHT: Template file tested through /prompt-lab
```python
template = Path("prompts/control_extractor_v3.txt").read_text()
response = scillm.call(template.format(document=text))
# Template tested: ./run.sh eval --prompt control_extractor_v3 --model deepseek
```

---

## Rule 15: Compliance Prompts Must Match Pipeline Payload Schema (NON-NEGOTIABLE)

### Rule: `grounding-match-pipeline-schema`

When a prompt operates on a domain payload produced by a pipeline (evidence cases, crosswalk chains, control glossaries, QRA results), the prompt MUST reference the exact field structure the pipeline produces. Do NOT reinvent the schema.

### WRONG:
```
# Prompt references a flat glossary dict the author invented
glossary = {"SV-AC-2": {"description": "..."}}
```
When the pipeline actually produces:
```python
glossary = [{"id": "SV-AC-2", "framework": "SPARTA", "type": "space_threat", "description": "..."}]
```

### RIGHT:
```
# Prompt references the exact schema from _build_evidence_case():
# glossary[]: array of objects, each with:
#   - id: control ID (e.g., "SV-AC-2", "CM0033")
#   - framework: source framework (e.g., "SPARTA", "CWE", "NIST", "CAPEC")
#   - type: entity type (e.g., "space_threat", "countermeasure")
#   - description: full text description from sparta_controls
#   - consequences: impact description (may be empty)
#   - supporting_knowledge: array of URL-sourced knowledge (may be empty)
#
# crosswalk_chains[]: array of objects, each with:
#   - from: source control ID
#   - from_framework: source framework name
#   - to_framework: target framework name
#   - hops[]: array of {id, name, framework, description}
```

### How to comply:
1. Find the function that produces the payload (e.g., `_build_evidence_case()` in `runner.py`)
2. Read its output schema — field names, types, nesting
3. Reference those exact field paths in the prompt (e.g., `glossary[].framework`, not "the framework")
4. Include a complete example using the real schema, not an abbreviated version you made up

### Why this matters

On 2026-04-09, a crosswalk question generation prompt used a flat glossary dict `{"SV-AC-2": {"description": "..."}}` without `framework` fields. The pipeline's `_build_evidence_case()` produces `[{"id": "SV-AC-2", "framework": "SPARTA", ...}]` with framework identification. Result: 0/86 questions were answerable because the LLM couldn't identify which framework each control belonged to and generated questions that the pipeline classified as `inconclusive`. The prompt was rewritten 3 times before this was caught.

---


---

## Integration

| Skill | Role |
|-------|------|
| `/best-practices-prompt` | Rules for writing prompts (this skill — apply BEFORE writing) |
| `/review-prompt` | Multi-model review of written prompts (apply AFTER writing) |
| `/prompt-lab` | Test prompts against ground truth (apply AFTER review) |
| `/code-runner` | Consumer of prompts — benefits from clear prompts |
| `/scillm` | LLM backend — receives the prompts |

**Workflow:** Write prompt (apply these rules) → `/review-prompt` (multi-model review) → `/prompt-lab` (test against ground truth) → deploy

## Specialized References

For detailed rules beyond the core 0-15, see:

- **[references/inference-time.md](references/inference-time.md)** — Rules 16-23 for classification, filtering, JSON output prompts
- **[references/extraction.md](references/extraction.md)** — Rules 24-36 for QRA generation, entity extraction, source grounding
- **[references/incidents.md](references/incidents.md)** — Pattern library of past prompt failures with fixes
