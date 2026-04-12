---
name: create-qras
description: >
  Generate QRA (Question-Reasoning-Answer) pairs from controls, documents, or text.
  Supports relationship QRAs (CWE→SPARTA) and standalone QRAs (from URL knowledge).
  Uses /create-evidence-case for crosswalk chains and /scillm for generation.
triggers:
  - create qras
  - generate qras
  - qra from document
  - qra from control
  - standalone qra
provides:
  - qra-generation
  - relationship-qras
  - standalone-qras
  - corpus-qras
composes:
  - memory
  - scillm
  - create-evidence-case
taxonomy:
  - knowledge
  - extraction
  - compliance
---

# /create-qras

Generate QRA pairs from any source: controls, documents, or raw text.

## QRA Types

| Type | Source | Use Case |
|------|--------|----------|
| **relationship** | CWE-79 → SV-AC-2 | Cross-framework mappings (CWE/CAPEC/ATT&CK → SPARTA) |
| **independent** | AC-17, SV-AC-2 | NIST/MITRE/SPARTA controls without technique mapping |
| **standalone** | sparta_url_knowledge doc | Knowledge extraction from PDFs/URLs |
| **corpus** | Any text | Free-form QRA generation |

## Usage

```bash
# Relationship QRA: generate from control ID (CWE/CAPEC/ATT&CK auto-detected)
./run.sh generate --control CWE-79
./run.sh generate --control CAPEC-115

# Relationship QRA: specific source → target
./run.sh generate --source CWE-79 --target SV-AC-2

# Independent QRA: NIST/MITRE controls (no crosswalk needed)
./run.sh generate --control AC-17
./run.sh generate --control SV-AC-2
./run.sh generate --framework nist --limit 100

# Standalone QRA: from URL knowledge document
./run.sh generate --doc <doc_key>
./run.sh generate --collection sparta_url_knowledge --limit 50

# Corpus QRA: from raw text
./run.sh generate --text "Zero trust requires continuous verification..."

# Batch mode (legacy compatibility)
./run.sh generate --framework cwe --limit 50

# Options
--dry-run         # Show what would be generated, don't store
--no-verify       # Skip /create-evidence-case verification
--store           # Store to sparta_qra (default: true)
--output FILE     # Write results to JSON file
--dump-prompts DIR  # Save prompts to dir for human review (no LLM call)
```

## Quality Workflow (REQUIRED for batch runs)

Before running large batches, validate prompts with humans:

```bash
# Step 1: Pre-flight check - dump prompts for human review
python3 generator.py preflight --output-dir ./review_prompts

# Step 2: Open prompts in ./review_prompts/ and paste into Claude.ai/ChatGPT
#         Verify output quality matches expectations in fixtures/

# Step 3: Run automated evaluation against ground truth
python3 generator.py preflight --run-eval

# Step 4: Only proceed with batch if preflight passes
python3 generator.py generate --framework cwe --limit 500
```

### Quality Gates

Every generated QRA is scored on:

| Gate | Criteria | Threshold |
|------|----------|-----------|
| `has_question` | Question field exists | required |
| `has_reasoning` | Reasoning > 10 words | required |
| `has_answer` | Answer > 5 words | required |
| `has_evidence` | ≥2 evidence quotes | required |
| `grounding_verified` | Quotes appear in source | score ≥ 0.5 |

QRAs with `verdict: NEEDS_REVIEW` failed quality gates and should not be stored.

### Ground Truth Fixtures

Located in `fixtures/cwe_relationship_ground_truth.json`:

```json
{
  "id": "cwe287_ia0001",
  "source_control": "CWE-287",
  "target_control": "IA-0001",
  "expected_question_contains": ["CWE-287", "authentication"],
  "expected_reasoning_contains": ["improper", "bypass"],
  "expected_answer_contains": ["authentication", "verification"],
  "min_evidence_quotes": 2
}
```

Add new fixtures for any control pair before batch generation.

## How It Works

### Prompt Templates (via /prompt-lab)

All prompts are loaded from `/prompt-lab/prompts/qra/`:

| Template | Use Case |
|----------|----------|
| `cwe_relationship.txt` | CWE→SPARTA with crosswalk evidence |
| `capec_relationship.txt` | CAPEC→target with bridge evidence |
| `independent.txt` | NIST/MITRE controls (no crosswalk) |
| `standalone.txt` | URL knowledge documents |

Edit prompts in prompt-lab, not in generator.py.

### Relationship QRAs

```
Control ID (e.g., CWE-79)
         ↓
POST /create-evidence-case
         ↓
Extract: resolved_entities, crosswalk_chains
         ↓
Load prompt template from /prompt-lab
         ↓
For each valid target:
    Build evidence payload
    Call /scillm for QRA generation
    Verify via deterministic gates
         ↓
Store to sparta_qra with qra_type="relationship", sparta_linked=true
```

### Standalone QRAs

```
Document (sparta_url_knowledge, PDF extract, etc.)
         ↓
Extract content + metadata
         ↓
Call /scillm with standalone prompt
    (no crosswalk needed)
         ↓
Verify: evidence_quotes present, cybersecurity-relevant
         ↓
Store to sparta_qra with qra_type="standalone"
```

## Output Schema

```json
{
  "_key": "qra_cwe79_svac2_abc123",
  "qra_id": "qra_cwe79_svac2_abc123",
  "run_id": "skill_create_qras_1712836800",
  "question": "How does XSS weakness enable access control bypass?",
  "reasoning": "CWE-79 describes... SV-AC-2 requires...",
  "answer": "XSS can bypass access controls by...",
  "evidence_quotes": ["exact quote from source"],
  
  "qra_type": "relationship",
  "source_framework": "CWE",
  "source_control_id": "CWE-79",
  "target_framework": "SPARTA",
  "target_control_id": "SV-AC-2",
  "crosswalk_chain": ["CWE-79", "CAPEC-86", "T1059", "SV-AC-2"],
  "sparta_linked": true,
  
  "verdict": "SATISFIED",
  "gate_result": "gates_passed",
  "created_at": 1712836800,
  "generator": "skill:create-qras"
}
```

For independent QRAs (NIST/MITRE controls):

```json
{
  "_key": "qra_independent_ac17_abc123",
  "qra_id": "qra_independent_ac17_abc123",
  "run_id": "skill_create_qras_1712836800",
  "question": "How should an organization implement remote access controls?",
  "reasoning": "AC-17 requires organizations to...",
  "answer": "Organizations should establish remote access policies...",
  "evidence_quotes": ["exact quote from control description"],
  
  "qra_type": "independent",
  "source_framework": "NIST",
  "source_control_id": "AC-17",
  "sparta_linked": false,
  
  "verdict": "SATISFIED",
  "created_at": 1712836800,
  "generator": "skill:create-qras"
}
```

For standalone QRAs (from documents):

```json
{
  "_key": "qra_standalone_doc123_abc",
  "qra_id": "qra_standalone_doc123_abc",
  "run_id": "skill_create_qras_1712836800",
  "question": "What are indicators of satellite ground station compromise?",
  "reasoning": "The document describes...",
  "answer": "Key indicators include...",
  "evidence_quotes": ["exact quote from document"],
  
  "qra_type": "standalone",
  "source_doc": "url_knowledge_doc123",
  "source_url": "https://cisa.gov/...",
  "source_title": "Satellite Security Guidelines",
  "sparta_linked": false,
  
  "verdict": "SATISFIED",
  "created_at": 1712836800,
  "generator": "skill:create-qras"
}
```

## Crosswalk Paths (CWE → SPARTA)

Two paths connect CWE weaknesses to SPARTA countermeasures. Both use `sparta_relationships` edges.

| Path | Hops | Data Source | Edge Filter |
|------|------|-------------|-------------|
| **Direct** | 1 | SPARTA v3.1 `cwe_class_ids` | `source_control_id=CWE-*, target_framework=SPARTA` |
| **NIST 2-hop** | 2 | Heimdall `nist_control_ids` | `source_control_id=SI-10, target_framework=sparta` |

### Direct Path (2,825+ CWE→SPARTA edges)

SPARTA Techniques have `cwe_class_ids` listing mapped CWEs. Step 08 creates edges:
- `source_framework: "CWE"`, `target_framework: "SPARTA"` (uppercase)
- Example: CWE-287 → DE-0001, CWE-287 → IA-0001

```python
# Find SPARTA targets for CWE-287
resp = client.post("/list", json={
    "collection": "sparta_relationships",
    "limit": 50,
    "filters": {"source_control_id": "CWE-287", "target_framework": "SPARTA"}
})
```

### NIST 2-hop Path (for unmapped CWEs)

CWEs have `nist_control_ids` from MITRE Heimdall. NIST→SPARTA edges exist:
- `source_framework: "nist"`, `target_framework: "sparta"` (lowercase!)
- Example: CWE-79 → SI-10 (field) → CM0001 (edge)

```python
# CWE-79 has nist_control_ids: ['SI-10']
# Find SPARTA targets via SI-10
resp = client.post("/list", json={
    "collection": "sparta_relationships",
    "limit": 50,
    "filters": {"source_control_id": "SI-10", "target_framework": "sparta"}  # lowercase!
})
```

### Framework Casing (CRITICAL)

| Edge Type | source_framework | target_framework |
|-----------|-----------------|------------------|
| CWE→SPARTA | `"CWE"` | `"SPARTA"` (uppercase) |
| NIST→SPARTA | `"nist"` | `"sparta"` (lowercase) |
| CAPEC→CWE | `"CAPEC"` | `"CWE"` |

**Always check both cases** when filtering `target_framework` for SPARTA.

## Deterministic Gates

For relationship QRAs:
- `entity_resolved` — at least one entity extracted
- `has_crosswalk` — chain exists between source and target
- `same_domain` — both entities are cybersecurity-related

For standalone QRAs:
- `has_evidence` — evidence_quotes are present
- `quote_grounded` — quotes appear in source document
- `cybersecurity_relevant` — topic is security-related

## Integration with Existing Scripts

The legacy `generate_cwe_qras.py` and `generate_capec_qras.py` can be replaced with:

```bash
# Instead of: python scripts/generate_cwe_qras.py --generate --limit 50
./run.sh generate --framework cwe --limit 50

# Instead of: python scripts/generate_capec_qras.py --control-id CAPEC-115
./run.sh generate --control CAPEC-115
```

## Common Mistakes

### WRONG: Generate QRAs without verification
```bash
./run.sh generate --control CWE-79 --no-verify
# → May produce ungrounded QRAs
```

### RIGHT: Let verification filter bad QRAs
```bash
./run.sh generate --control CWE-79
# → Uses /create-evidence-case gates, only stores verified QRAs
```

### WRONG: Generate standalone QRAs from relationship sources
```bash
./run.sh generate --doc sparta_controls/SV-AC-2
# → Controls should use relationship mode
```

### RIGHT: Use appropriate mode for source type
```bash
./run.sh generate --control SV-AC-2           # relationship
./run.sh generate --doc sparta_url_knowledge/doc123  # standalone
```
