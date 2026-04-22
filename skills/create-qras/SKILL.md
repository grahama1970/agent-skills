---
name: create-qras
description: >
  Generate QRA (Question-Reasoning-Answer) pairs from controls, documents, or text.
  Three modes: native (framework definitions), relationship (crosswalk chains), standalone (documents).
triggers:
  - create qras
  - generate qras
  - qra from document
  - qra from control
  - native qra
  - attack qra
  - cwe qra
provides:
  - qra-generation
  - native-qras
  - relationship-qras
  - standalone-qras
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

## Quick Decision: Which Mode Do I Use?

| I want to answer... | Use mode | Example |
|---------------------|----------|---------|
| "What is T1595 Active Scanning?" | `--mode native` | Framework definition from MITRE ATT&CK |
| "How does CWE-287 enable bypass of SPARTA IA-0001?" | `--mode relationship` | Cross-framework mapping with evidence chains |
| "What does this PDF say about satellite security?" | `--mode standalone` | Knowledge extraction from documents |

## Modes (IMPORTANT - read this)

### native - Framework Definitions

**Question type:** "What is X according to [framework]?"

**Use when:** You need authoritative definitions from framework source documentation (ATT&CK, CWE, NIST, CAPEC, D3FEND).

**Output category:** `attack_native`, `cwe_native`, `nist_native`, etc.

```bash
# Generate native QRAs for ATT&CK technique
./run.sh generate --control T1595 --mode native

# Batch generate for all ATT&CK Enterprise techniques
./run.sh generate --framework ATT_CK_Enterprise --mode native --limit 100
```

**What it does:**
1. Loads control document from `sparta_controls`
2. Enriches with URL content from `sparta_url_knowledge` (for thin frameworks)
3. Uses v6 prompt with source admissibility rules, modality preservation
4. Generates 1-6 QRAs per control covering: definition, detection, mitigation, scope, risk

**Category field:** `attack_native`, `cwe_native`, `nist_native`, `capec_native`, `d3fend_native`, `sparta_native`

### relationship - Cross-Framework Mappings

**Question type:** "How does X relate to SPARTA Y?"

**Use when:** You need to explain how a weakness/attack maps to SPARTA countermeasures via crosswalk chains.

**Output category:** `sparta_context` (implicitly, via relationship)

```bash
# Generate relationship QRA for CWE→SPARTA
./run.sh generate --control CWE-79 --mode relationship

# Explicit source→target
./run.sh generate --source CWE-287 --target IA-0001
```

**What it does:**
1. Finds SPARTA targets via `sparta_relationships` edges
2. Calls `/create-evidence-case` for crosswalk chains
3. Generates QRA explaining the relationship with grounded evidence

**Requires:** Source control must have edges to SPARTA in `sparta_relationships`.

### standalone - Document Extraction

**Question type:** "What does this document say about X?"

**Use when:** You need to extract Q&A pairs from URL knowledge documents, PDFs, or fetched web content.

```bash
# Generate from specific document
./run.sh generate --doc url_knowledge_12345 --mode standalone

# Batch from collection
./run.sh generate --collection sparta_url_knowledge --mode standalone --limit 50
```

**What it does:**
1. Loads document content
2. Extracts cybersecurity-relevant Q&A pairs
3. Stores with `qra_type: standalone`

### auto - Detect from Input (default)

When `--mode auto` (default), mode is detected from input:

| Input | Detected Mode | Why |
|-------|--------------|-----|
| `--control CWE-79` | relationship | CWE has crosswalk chains to SPARTA |
| `--control CAPEC-115` | relationship | CAPEC has crosswalk chains to SPARTA |
| `--control T1595` | native | ATT&CK - extract definitions |
| `--control AC-17` | native | NIST - extract definitions |
| `--control SV-AC-2` | native | SPARTA - extract definitions |
| `--doc doc123` | standalone | Document extraction |

## Usage Examples

```bash
# Native: ATT&CK technique definition
./run.sh generate --control T1595 --mode native

# Native: Batch all ATT&CK Enterprise
./run.sh generate --framework ATT_CK_Enterprise --mode native --limit 500

# Relationship: CWE→SPARTA with evidence chains
./run.sh generate --control CWE-287 --mode relationship

# Standalone: From URL knowledge
./run.sh generate --doc url_knowledge_xyz --mode standalone

# Dry run: Preview what would be generated
./run.sh generate --control T1595 --mode native --dry-run

# Dump prompts for human review (no LLM call)
./run.sh generate --control T1595 --mode native --dump-prompts ./review/
```

## Output Schema

All QRAs share a common schema, with mode-specific fields:

```json
{
  "_key": "qra_native_t1595_p1_abc123",
  "qra_id": "qra_native_t1595_p1_abc123",
  "run_id": "skill_create_qras_native_1712836800",
  
  "question": "What is T1595 Active Scanning according to MITRE ATT&CK?",
  "reasoning": "The ATT&CK description defines Active Scanning as...",
  "answer": "T1595 Active Scanning is a reconnaissance technique...",
  "evidence_quotes": [
    {"quote": "Adversaries may execute active reconnaissance scans...", "relevance": "Primary definition"}
  ],
  
  "qra_type": "native",
  "category": "attack_native",
  "source_framework": "ATT_CK_Enterprise",
  "source_control_id": "T1595",
  "sparta_linked": false,
  
  "pair_type": "threat_description",
  "confidence": "high",
  "actionable_for": "training",
  
  "prompt_version": "control_to_qra_v6",
  "generator": "skill:create-qras:native",
  "created_at": 1712836800,
  "verdict": "SATISFIED"
}
```

### Mode-Specific Fields

| Field | native | relationship | standalone |
|-------|--------|--------------|------------|
| `qra_type` | "native" | "relationship" | "standalone" |
| `category` | "attack_native", etc. | (sparta_context) | (standalone) |
| `source_framework` | ATT&CK, CWE, etc. | CWE, CAPEC | - |
| `target_framework` | - | SPARTA | - |
| `crosswalk_chain` | - | ["CWE-79", "T1059", "SV-AC-2"] | - |
| `source_doc` | - | - | doc key |
| `sparta_linked` | false | true | false |

## Quality Gates

Every generated QRA is validated:

| Gate | Criteria | Required |
|------|----------|----------|
| `has_question` | Question field exists | Yes |
| `has_reasoning` | Reasoning > 10 words | Yes |
| `has_answer` | Answer > 5 words | Yes |
| `has_evidence` | At least 1 evidence quote | Yes |
| `grounding_verified` | Quotes appear in source | Score >= 0.5 |

QRAs failing gates get `verdict: NEEDS_REVIEW` and should not be used.

## LLM Backend

Uses `/scillm` proxy with `model: "text"`. All models via Chutes API.

| Priority | Model | Timeout | Notes |
|----------|-------|---------|-------|
| 1 | DeepSeek-V3.2-TEE | 300s | Primary |
| 2 | DeepSeek-V3.1-TEE | 300s | First fallback |
| 3 | DeepSeek-R1-0528-TEE | 300s | Reasoning model |
| 4 | Kimi-K2.5-TEE | 180s | Fast alternative |
| 5 | Qwen3-235B-A22B-Thinking | 180s | 100% grounding |
| 6 | Qwen3.5-397B-A17B-TEE | 300s | Last resort |

### How Fallbacks Work

The scillm proxy manages fallbacks dynamically:

1. **Request routing:** Skill requests `model: "text"` → proxy resolves to primary (V3.2-TEE)
2. **Failure detection:** If primary returns 429/503/timeout, proxy automatically tries next in chain
3. **Circuit breaker:** After N consecutive failures, model is temporarily removed from rotation
4. **Recovery:** Circuit breaker resets after cooldown; model rejoins the chain

**Fallback chain is defined in config, not code.** The proxy reads `router_settings.fallbacks` from `proxy_server_config.yaml` and executes the chain. Skills don't know which model actually served the request — they just get the response.

**Resource allocation:** Models are ordered by:
- **Availability** — TEE variants have dedicated capacity, non-TEE share pools
- **Cost** — DeepSeek models are cheapest, Qwen3.5-397B is most expensive
- **Latency** — Smaller models (Kimi-K2.5) respond faster for simple prompts

The proxy tracks real-time concurrency via `/v1/scillm/concurrency` and adjusts effective limits when 429s occur (adaptive backoff).

### Batching (as_completed pattern)

Streaming batch processing for maximum throughput:

1. Fire `chunk_size=4` parallel `/scillm` LLM calls
2. `asyncio.as_completed` processes each result **the moment it returns**
3. Per-result: call `/create-evidence-case` → enrich QRA with `evidence_case` field
4. Store immediately via `store_callback` (crash-safe)

**Key advantage:** Evidence enrichment runs while other LLM calls still in flight.
Not `asyncio.gather` (waits for entire chunk) — `as_completed` (streaming).

- `scillm_metadata` with `batch_id` + `item_id` for automatic resume
- Dynamic `chunk_size` via `/v1/scillm/concurrency`

**Config:** `~/workspace/experiments/scillm/local/proxy_server_config.yaml`

## Manifest Execution Workflow

The recommended workflow for batch QRA generation:

```bash
# 1. Generate review dossier (deterministic checks, prompt inventory, verdict)
./run.sh review sparta_v2_manifest.json

# 2. Check verdict
#    BLOCKED     → fix blocking issues first
#    CANARY_ONLY → proceed with caution, review warnings
#    FULL_RUN_OK → all checks passed

# 3. Run canary batch (limited, dry-run first)
./run.sh manifest sparta_v2_manifest.json --limit 10 --dry-run
./run.sh manifest sparta_v2_manifest.json --limit 10

# 4. Run full batch (after canary validation)
./run.sh manifest sparta_v2_manifest.json
```

### Review Dossier Schema

The `review` command generates a JSON dossier with:

| Field | Description |
|-------|-------------|
| `verdict.status` | `BLOCKED` / `CANARY_ONLY` / `FULL_RUN_OK` |
| `blocking_issues` | Must-fix before execution (duplicate keys, missing prompt_kind) |
| `warnings` | Review before full run (sentinels, existing QRAs) |
| `prompt_inventory` | Hash-versioned prompts with pair_types |
| `db_sanity` | Referential integrity, existing QRA counts |
| `manifest_invariants` | Duplicate job_ids, logical keys, sentinel counts |
| `risky_samples` | Top 20 jobs needing human review |
| `executor` | Timeout, concurrency, crash-safe, as_completed pattern |

### Deterministic Checks

| Check | Verdict | Description |
|-------|---------|-------------|
| duplicate_job_id | BLOCKED | Same job_id appears multiple times |
| duplicate_logical_key | BLOCKED | Same source+target pair duplicated |
| missing_prompt_kind | BLOCKED | Job has no prompt_kind |
| missing_source_control | BLOCKED | Source control not in DB |
| sentinel_rows | WARN | Contains CM-NA, placeholder, TBD |
| existing_qras | WARN | QRAs already exist for control |
| missing_target_control | WARN | Target control not in DB |

### Executor Guarantees

The `manifest` command uses:
- **300s timeout** per LLM call
- **`asyncio.as_completed`** for streaming results
- **`/create-evidence-case`** enrichment per QRA
- **Immediate storage** via `store_callback` (crash-safe)
- **Per-item retry** with exponential backoff (30s, 60s, 90s)

## Prompt Templates

Native prompts live in `prompts/native/` with clean framework-based naming:

```
prompts/native/
├── attack_system.txt    # ATT&CK: threat/technique definitions
├── attack_user.txt
├── capec_system.txt     # CAPEC: attack pattern definitions
├── capec_user.txt
├── cwe_system.txt       # CWE: weakness definitions
├── cwe_user.txt
├── d3fend_system.txt    # D3FEND: defensive technique definitions
├── d3fend_user.txt
├── esa_system.txt       # ESA: space security guideline definitions
├── esa_user.txt
├── nist_system.txt      # NIST: SP 800-53 control definitions
├── nist_user.txt
├── sparta_system.txt    # SPARTA: countermeasure definitions
└── sparta_user.txt
```

| Template | Framework | pair_types |
|----------|-----------|------------|
| `attack_*` | ATT&CK Enterprise | threat_description, detection_methods, mitigation_guidance, scope_clarification |
| `capec_*` | CAPEC | attack_description, execution_flow, prerequisites, mitigation_guidance |
| `cwe_*` | CWE | weakness_description, detection_methods, consequence_description, mitigation_guidance |
| `d3fend_*` | D3FEND | defense_description, implementation_guidance, taxonomy_context, scope_clarification |
| `esa_*` | ESA | guideline_description, implementation_guidance, assessment_criteria, scope_clarification |
| `nist_*` | NIST SP 800-53 | control_description, implementation_guidance, assessment_criteria, scope_clarification |
| `sparta_*` | SPARTA | countermeasure_description, implementation_guidance, assessment_criteria, scope_clarification |

All prompts follow v2 quality standard with:
- Rationale header (not sent to LLM)
- Source admissibility rules
- Modality preservation (should/shall/may/can)
- Valid + invalid output examples
- Maximum 4 pairs, 1 per pair_type

## Common Mistakes

### WRONG: Using relationship mode for ATT&CK definitions
```bash
./run.sh generate --control T1595 --mode relationship
# Fails: ATT&CK techniques don't have SPARTA crosswalk edges
```

### RIGHT: Use native mode for framework definitions
```bash
./run.sh generate --control T1595 --mode native
# Works: Extracts "What is T1595?" from ATT&CK docs
```

### WRONG: Using native mode for CWE→SPARTA mappings
```bash
./run.sh generate --control CWE-79 --mode native
# Works, but misses the point: you get "What is CWE-79?" not "How does CWE-79 relate to SPARTA?"
```

### RIGHT: Use relationship mode for cross-framework QRAs
```bash
./run.sh generate --control CWE-79 --mode relationship
# Works: Generates "How does CWE-79 enable bypass of SPARTA SV-AC-2?"
```

### WRONG: Running batch without --dry-run first
```bash
./run.sh generate --framework ATT_CK_Enterprise --mode native --limit 1000
# Risk: 1000 LLM calls without verification
```

### RIGHT: Preview with dry-run, then run
```bash
./run.sh generate --framework ATT_CK_Enterprise --mode native --limit 5 --dry-run
# Review output, then:
./run.sh generate --framework ATT_CK_Enterprise --mode native --limit 1000
```

## Migration from generate_qras_from_controls.py

The standalone script `scripts/generate_qras_from_controls.py` is deprecated. Use this skill instead:

```bash
# Old:
python scripts/generate_qras_from_controls.py --generate --framework ATT_CK_Enterprise --limit 100

# New:
./run.sh generate --framework ATT_CK_Enterprise --mode native --limit 100
```

The v6 prompt from the script has been ported to `prompts/native_attack_*.txt`.
