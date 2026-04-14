# Evidence Case: Compliance Officer Tool

---

## What This Tool Does

This tool helps **compliance officers** find and verify requirements using **Claims-Arguments-Evidence (CAE) trees**. It does NOT make compliance determinations — that's your job. The tool:

1. **Builds CAE trees** showing claim → argument → evidence chains
2. **Surfaces relevant requirements** for a topic you're researching
3. **Shows traceability strength** so you know where to focus verification effort
4. **Flags gaps and issues** in the underlying QRA/requirement data
5. **Provides traceable citations** you can verify against source documents
6. **Exports to GSN/SACM** for formal assurance case documentation

---

## CAE Tree Structure

Every evidence case is a **Claims-Arguments-Evidence tree**:

```
CLAIM (What needs to be verified)
    │
    ├── ARGUMENT (Why we believe the claim)
    │       │
    │       ├── EVIDENCE (SPARTA controls, contextual entities)
    │       └── EVIDENCE
    │
    └── ARGUMENT
            │
            └── EVIDENCE

    FOUND VIA: QRAs (inference layer — how we located the evidence)
```

| Layer | Purpose | Example |
|-------|---------|---------|
| **Claim** | Top-level assertion to verify | "System protects uplinks from jamming" |
| **Argument** | Reasoning connecting evidence to claim | "Per IA-0006, integrity controls mitigate this" |
| **Evidence** | Authoritative artifacts backing the argument | IA-0006 glossary entry (the actual requirement) |
| **Found Via** | Inference layer — how we located evidence | QRAs that matched your question |

---

## Two Use Cases

### Use Case 1: Discovery

**"Find the requirements related to X that I need to verify"**

You have a topic (satellite uplink protection, command authentication, etc.) and need to know which SPARTA controls apply.

### Use Case 2: Targeted Lookup

**"What does Table Y say about Z in accordance with Control X?"**

You have a specific control and need to find what source documents say about a related topic.

Both return CAE trees — discovery builds the tree from topic, lookup builds from control + topic.

---

## How It Works

```
Your Question
     ↓
┌─────────────────────────────────────────┐
│ 1. Extract entities from question       │
│ 2. Lookup glossary (authoritative)      │
│ 3. Fetch crosswalk chains               │
│ 4. Retrieve relevant QRAs via lineage   │
│ 5. Build CAE tree                       │
│ 6. Validate each layer                  │
│ 7. Compute traceability strength        │
└─────────────────────────────────────────┘
     ↓
CAE Tree + Validation Status
```

---

## The Data Layers

### Glossary — Authoritative Definitions (Evidence Layer)

These are the **real framework entities** from SPARTA, CWE, CAPEC, ATT&CK. The glossary is authoritative — these definitions come directly from the frameworks.

| Type | Example | Role in CAE |
|------|---------|-------------|
| **SPARTA Controls** | IA-0006, IA-0007 | **Normative evidence** — requirements you verify against |
| **CWE Weaknesses** | CWE-924 | **Contextual evidence** — what weakness this addresses |
| **CAPEC Patterns** | CAPEC-160 | **Contextual evidence** — attack patterns to consider |

**Key distinction:** SPARTA controls are normative (obligations). CWE/CAPEC entries are contextual (supporting understanding).

### Crosswalks — Framework Mappings (Argument Layer)

Curated mappings between frameworks. These form the **arguments** that connect evidence to claims:

```
CWE-924 (Improper Message Integrity)
    ↓ mitigated_by (strong)
IA-0006 (Secure Command and Control Link)
```

Crosswalks have **mapping strength**:
- **Strong** — direct, curated mapping (can support primary arguments)
- **Medium** — indirect via NIST or ATT&CK intermediate
- **Supplementary** — contextual only, not primary justification

### QRAs — Inference Layer (NOT Evidence)

Question-Rationale-Answer triples are the **search interface** that helps you find requirements. Think of QRAs as an index — they match your natural language question and point to the actual requirements.

```
Your Question: "How do I protect uplinks from jamming?"
         ↓
    QRA matches semantically (qra__rf_jamming_001)
         ↓
    lineage.entity_ids → [IA-0006, IA-0007, CWE-924]
         ↓
    SPARTA Controls (the actual requirements you verify)
```

**QRAs are inference, not evidence.** The compliance officer verifies against **IA-0006** (the requirement), not against **qra__rf_jamming_001** (the search result). QRAs are human-reviewed before entering the system, but they remain the retrieval mechanism, not the authoritative source.

### Lineage — Traceability

Every QRA has lineage that traces back to authoritative sources:

```json
{
  "lineage": {
    "entity_ids": ["IA-0006", "IA-0007", "CWE-924"],
    "related_qra_keys": ["qra__freq_hop_002", "qra__c2_integrity_003"],
    "graph_version": "v2"
  }
}
```

---

## Example: Discovery Query

**Your question:** "What requirements apply to protecting satellite command uplinks from RF jamming?"

### CAE Tree Output

```
┌─────────────────────────────────────────────────────────────────────┐
│  CLAIM: Satellite command uplinks are protected from RF jamming     │
│  Status: NEEDS VERIFICATION                                         │
│  Traceability: STRONG                                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ARGUMENT 1: Command link integrity per SPARTA IA-0006              │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Reasoning: IA-0006 requires integrity and authenticity     │   │
│  │  protections for command uplinks, directly addressing the   │   │
│  │  threat of unauthorized command injection.                  │   │
│  │                                                             │   │
│  │  EVIDENCE:                                                  │   │
│  │  ┌─────────────────────────────────────────────────────┐   │   │
│  │  │ [NORMATIVE] IA-0006 — Secure Command and Control    │   │   │
│  │  │ Framework: SPARTA                                   │   │   │
│  │  │ Text: "Ensure the integrity and authenticity of     │   │   │
│  │  │ command and control uplinks through encryption      │   │   │
│  │  │ and authentication mechanisms."                     │   │   │
│  │  │ Source: SPARTA v2025.1, Section IA-0006            │   │   │
│  │  └─────────────────────────────────────────────────────┘   │   │
│  │  ┌─────────────────────────────────────────────────────┐   │   │
│  │  │ [CONTEXTUAL] CWE-924 — Improper Message Integrity   │   │   │
│  │  │ Crosswalk: CWE-924 → IA-0006 (strong, mitigated_by) │   │   │
│  │  └─────────────────────────────────────────────────────┘   │   │
│  │                                                             │   │
│  │  FOUND VIA (inference):                                    │   │
│  │  ┌─────────────────────────────────────────────────────┐   │   │
│  │  │ qra__rf_jamming_001                                 │   │   │
│  │  │ Q: "What techniques mitigate RF jamming?"           │   │   │
│  │  │ → Pointed to: [IA-0006, IA-0007, CWE-924]          │   │   │
│  │  └─────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ARGUMENT 2: Uplink anti-jam protection per SPARTA IA-0007          │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Reasoning: IA-0007 requires protection of uplink channels  │   │
│  │  from interference and jamming through signal processing.   │   │
│  │                                                             │   │
│  │  EVIDENCE:                                                  │   │
│  │  ┌─────────────────────────────────────────────────────┐   │   │
│  │  │ [NORMATIVE] IA-0007 — Uplink Protection             │   │   │
│  │  │ Framework: SPARTA                                   │   │   │
│  │  │ Text: "Protect uplink communication channels from   │   │   │
│  │  │ interference and jamming through signal processing  │   │   │
│  │  │ techniques and frequency management."               │   │   │
│  │  └─────────────────────────────────────────────────────┘   │   │
│  │                                                             │   │
│  │  FOUND VIA (inference):                                    │   │
│  │  ┌─────────────────────────────────────────────────────┐   │   │
│  │  │ qra__freq_hop_002                                   │   │   │
│  │  │ Q: "How to implement frequency hopping for C2?"     │   │   │
│  │  │ → Pointed to: [IA-0006, IA-0007]                   │   │   │
│  │  └─────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ARGUMENT 3: Jamming detection per SPARTA DE-0003                   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Reasoning: DE-0003 requires detection mechanisms for       │   │
│  │  jamming attempts on communication channels.                │   │
│  │  Traceability: MODERATE (supplementary crosswalk only)      │   │
│  │                                                             │   │
│  │  EVIDENCE:                                                  │   │
│  │  ┌─────────────────────────────────────────────────────┐   │   │
│  │  │ [NORMATIVE] DE-0003 — Detect Jamming                │   │   │
│  │  │ Framework: SPARTA                                   │   │   │
│  │  │ Text: "Implement mechanisms to detect jamming or    │   │   │
│  │  │ interference attempts on communication channels."   │   │   │
│  │  └─────────────────────────────────────────────────────┘   │   │
│  │  ┌─────────────────────────────────────────────────────┐   │   │
│  │  │ [CONTEXTUAL] CAPEC-160 → T1498 → DE-0003            │   │   │
│  │  │ Crosswalk: supplementary (attack context only)      │   │   │
│  │  └─────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│  VALIDATION STATUS                                                  │
│                                                                     │
│  Structure Gates:                                                   │
│  ✓ glossary_exists — All entity_ids resolve to glossary entries    │
│  ✓ crosswalk_valid — All crosswalk endpoints exist                 │
│  ✓ lineage_complete — All QRAs have entity_ids populated           │
│  ✓ no_circular_refs — No self-referential chains                   │
│  ✓ minimum_evidence — At least one normative control cited         │
│                                                                     │
│  Provenance Gates:                                                  │
│  ✓ source_version_pinned — SPARTA v2025.1 (pinned)                 │
│  ⚠ mapping_reviewed — 2/3 crosswalks human-reviewed                │
│                                                                     │
│  Overall: PASS (1 warning)                                          │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│  TRACEABILITY SUMMARY                                               │
│                                                                     │
│  Arguments: 3                                                       │
│  - STRONG: 2 (IA-0006, IA-0007)                                    │
│  - MODERATE: 1 (DE-0003)                                           │
│                                                                     │
│  Evidence items: 5                                                  │
│  - Normative: 3 (SPARTA controls — the actual requirements)        │
│  - Contextual: 2 (CWE, CAPEC crosswalks)                           │
│                                                                     │
│  Found via (inference): 3 QRAs                                      │
│  - qra__rf_jamming_001 → [IA-0006, IA-0007, CWE-924]               │
│  - qra__freq_hop_002 → [IA-0006, IA-0007]                          │
│  - qra__jamming_detect_003 → [DE-0003]                             │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### What You Do Next

1. **Review each Argument** — Does the reasoning make sense for your system?
2. **Verify Normative Evidence** — Check SPARTA controls against your implementation
3. **Note Traceability** — DE-0003 is MODERATE, may need additional research
4. **Document your determination** — The tool shows the chain, you make the call

---

## Example: Targeted Lookup Query

**Your question:** "What does the SPARTA Implementation Guide say about command authentication per IA-0006?"

### CAE Tree Output

```
┌─────────────────────────────────────────────────────────────────────┐
│  CLAIM: IA-0006 command authentication requirements are documented  │
│  Status: VERIFIED                                                   │
│  Traceability: STRONG                                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ARGUMENT: SPARTA Implementation Guide specifies authentication     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Reasoning: Section 4.2 of the Implementation Guide         │   │
│  │  provides specific authentication requirements for IA-0006. │   │
│  │                                                             │   │
│  │  EVIDENCE:                                                  │   │
│  │  ┌─────────────────────────────────────────────────────┐   │   │
│  │  │ [NORMATIVE] IA-0006 — Secure Command and Control    │   │   │
│  │  │ Framework: SPARTA                                   │   │   │
│  │  └─────────────────────────────────────────────────────┘   │   │
│  │                                                             │   │
│  │  AUTHORITATIVE SOURCE:                                     │   │
│  │  ┌─────────────────────────────────────────────────────┐   │   │
│  │  │ Document: SPARTA Implementation Guide v2.1          │   │   │
│  │  │ Section:  4.2 — Uplink Security Requirements        │   │   │
│  │  │ Page:     47                                        │   │   │
│  │  │ Version:  2025.1 (pinned)                           │   │   │
│  │  │                                                     │   │   │
│  │  │ "Command authentication shall use cryptographic     │   │   │
│  │  │  message authentication codes (MACs) with minimum   │   │   │
│  │  │  128-bit key strength. Commands shall include       │   │   │
│  │  │  sequence numbers to prevent replay attacks."       │   │   │
│  │  └─────────────────────────────────────────────────────┘   │   │
│  │                                                             │   │
│  │  RETRIEVED VIA:                                            │   │
│  │  - QRA: qra__c2_auth_005                                   │   │
│  │  - Lineage: [IA-0006, CWE-924]                             │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  Addresses IA-0006 requirements:                                    │
│  ✓ Authenticity of command uplinks (MACs)                          │
│  ✓ Authentication mechanisms (cryptographic)                       │
│  ✓ Anti-replay (sequence numbers)                                  │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│  VALIDATION STATUS: PASS                                            │
│  All structure gates passed. Source version pinned.                │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Validation: Finding Bad Data

The tool identifies QRAs and requirements with problems at each CAE layer:

### Structure Gates (Basic Data Integrity)

| Gate | What It Checks | CAE Layer |
|------|----------------|-----------|
| `glossary_exists` | Do lineage.entity_ids point to real glossary entries? | Evidence |
| `crosswalk_valid` | Do crosswalk endpoints exist? | Argument |
| `lineage_complete` | Does QRA have entity_ids populated? | Evidence |
| `no_circular_refs` | No self-referential chains? | Argument |
| `minimum_evidence` | At least one normative control cited? | Evidence |
| `claim_well_formed` | Is the claim specific and verifiable? | Claim |

### Provenance Gates (Source Trust)

| Gate | What It Checks | CAE Layer |
|------|----------------|-----------|
| `source_version_pinned` | Is the source document version locked? | Evidence |
| `source_excerpt_exists` | Does the quoted text exist in the source? | Evidence |
| `mapping_reviewed` | Has the crosswalk been human-reviewed? | Argument |
| `normative_vs_contextual` | Are SPARTA controls marked normative? | Evidence |

### Validation Output

```json
{
  "claim": "Satellite command uplinks are protected from RF jamming",
  "status": "PASS",
  "traceability": "STRONG",
  "gates": {
    "structure": {
      "glossary_exists": {"passed": true},
      "crosswalk_valid": {"passed": true},
      "lineage_complete": {"passed": true},
      "no_circular_refs": {"passed": true},
      "minimum_evidence": {"passed": true, "normative_count": 3}
    },
    "provenance": {
      "source_version_pinned": {"passed": true, "version": "2025.1"},
      "mapping_reviewed": {"passed": false, "reviewed": 2, "total": 3}
    }
  },
  "arguments": [
    {
      "control_id": "IA-0006",
      "traceability": "STRONG",
      "evidence_count": 3
    },
    {
      "control_id": "IA-0007", 
      "traceability": "STRONG",
      "evidence_count": 2
    },
    {
      "control_id": "DE-0003",
      "traceability": "MODERATE",
      "evidence_count": 2,
      "warning": "supplementary crosswalk only"
    }
  ]
}
```

---

## Traceability Strength Levels

**Note:** Traceability measures how well the system retrieved and linked to controls. It does NOT measure how strong the actual compliance evidence is for your specific context.

| Level | Criteria | Your Action |
|-------|----------|-------------|
| **STRONG** | 2+ QRAs, direct crosswalk, all gates pass | Standard verification |
| **MODERATE** | 1 QRA or indirect crosswalk | May need additional research |
| **WEAK** | No QRAs, supplementary crosswalk only | Investigate further |
| **INSUFFICIENT** | No normative controls found | Cannot build CAE tree |

### Per-Argument Traceability

Each argument in the CAE tree has its own traceability rating:

```
Argument 1 (IA-0006): STRONG
  - 2 QRAs reference this control
  - Direct crosswalk from CWE-924
  - All evidence gates pass

Argument 3 (DE-0003): MODERATE  
  - 1 QRA references this control
  - Supplementary crosswalk only (CAPEC → ATT&CK → SPARTA)
  - Consider additional research
```

---

## CAE Tree Export Formats

The tool supports export to formal assurance case formats:

| Format | Use Case |
|--------|----------|
| **JSON** | API consumption, programmatic access |
| **GSN** | Goal Structured Notation diagrams |
| **SACM** | Structured Assurance Case Metamodel (XML) |
| **Markdown** | Human-readable documentation |

### GSN Export Example

```
┌─────────────────────┐
│ G1: Uplinks        │  ← CLAIM (Goal)
│ protected from     │
│ RF jamming         │
└─────────┬──────────┘
          │
    ┌─────┴─────┐
    │           │
┌───┴───┐   ┌───┴───┐
│ S1:   │   │ S2:   │   ← ARGUMENTS (Strategies)
│ IA-0006│   │IA-0007│
│ integrity│ │anti-jam│
└───┬───┘   └───┬───┘
    │           │
┌───┴───┐   ┌───┴───┐
│ Sn1:  │   │ Sn2:  │   ← EVIDENCE (Solutions)
│SPARTA │   │SPARTA │
│control│   │control│
└───────┘   └───────┘

(QRAs are inference — they helped FIND the controls, not shown in GSN)
```

---

## What the Tool Does NOT Do

| The Tool Does | You Do |
|---------------|--------|
| Build CAE trees with claim → argument → evidence | Decide if arguments are sound for your context |
| Show traceability strength per argument | Judge if evidence is sufficient |
| Cite authoritative sources | Verify citations against source docs |
| Flag data quality issues | Fix or escalate bad data |
| Export to GSN/SACM | Review and approve assurance cases |

**The tool is a research assistant.** It builds the CAE structure and shows you where the evidence is strong or weak. Compliance determination is your professional judgment.

---

## Summary

This tool helps compliance officers:

1. **Build CAE trees** — Claim → Argument → Evidence structure
2. **Find requirements** — "What SPARTA controls apply to X?"
3. **Lookup specifics** — "What does source Y say about Z per control X?"
4. **Assess traceability** — Strong, moderate, or weak per argument?
5. **Trust the data** — Validation flags broken chains and missing evidence
6. **Export formally** — GSN/SACM for audit documentation

The glossary (SPARTA controls) provides normative evidence. Crosswalks form arguments. QRAs help retrieve relevant material. You make the compliance determination.

**No one trusts an AI to bless compliance. This tool builds the evidence case for you to verify.**

---

## Implementation Decisions (Resolved)

The following decisions were made based on Codex architectural review (2026-04-14):

### 1. Traceability Strength Thresholds

**DECISION: Confirmed with refinement**

| Level | QRAs Found | Crosswalk Type | Gates | Rationale |
|-------|------------|----------------|-------|-----------|
| STRONG | 2+ | Direct | All pass | Multiple retrieval paths + direct mapping = high confidence |
| MODERATE | 1 | Indirect (via NIST/ATT&CK) | All pass | Single path or indirect mapping = verify further |
| WEAK | 0 | Supplementary only | All pass | No QRA support = investigate why |
| INSUFFICIENT | - | - | Fails `minimum_evidence` | Cannot build valid CAE tree |

**Refinement:** MODERATE requires at least 1 QRA OR a direct crosswalk. An indirect crosswalk alone without QRA support is WEAK — the system found a path but no human-reviewed QRA covered it.

### 2. Provenance Gate Data Availability

**DECISION: Option A with fallback to C**

For v1, add these fields to the schema via migration:

| Gate | Required Field | Collection | Migration |
|------|----------------|------------|-----------|
| `source_version_pinned` | `source_version` | `sparta_controls` | Add field, default "2025.1" |
| `mapping_reviewed` | `review_status` | `sparta_relationships` | Add field, default "needs_review" |
| `normative_vs_contextual` | `authority_class` | `sparta_controls` | Add field, populate via script |

**Fallback inference:** When fields are missing (legacy data), infer:
- SPARTA controls → `normative`
- CWE/CAPEC/ATT&CK → `contextual`
- Unknown framework → `contextual` (fail safe)

### 3. Targeted Lookup Input Format

**DECISION: Explicit parameters canonical, NL for UX**

The canonical endpoint format uses explicit parameters:
```json
{
  "question": "What does Table 4.2 say about authentication?",
  "control_id": "IA-0006",
  "source_filter": "Implementation Guide"
}
```

Natural language queries ("What does the SPARTA Implementation Guide say about command authentication per IA-0006?") are accepted and entity-extracted into explicit parameters. The extraction happens at the API boundary, not inside the evidence builder.

**Rationale:** Explicit parameters are deterministic and testable. NL extraction is a UX convenience layer that calls the same canonical backend.

### 4. CAE Claim Generation

**DECISION: Option B — Derived cautious claim**

Claims are derived from the question using conservative templates:

| Query Type | Template | Example |
|------------|----------|---------|
| Discovery | "[Topic] requirements are identified" | "Satellite uplink protection requirements are identified" |
| Targeted | "[Control] requirements regarding [topic] are documented" | "IA-0006 requirements regarding authentication are documented" |

**NOT used:** User-provided claims or control-centric claims like "IA-0006 is satisfied." The tool surfaces requirements for verification — it does not assert compliance.

**Claim status is always `NEEDS VERIFICATION`** unless the user explicitly overrides after review.

### 5. GSN/SACM Export

**DECISION: Design now, ship later**

For v1:
- CAE tree JSON output includes GSN-compatible structure (Goals, Strategies, Solutions)
- Field names align with GSN terminology where possible
- No actual GSN diagram generation in v1

For v2:
- Add `--format gsn` flag that calls `/create-gsn-diagram`
- Add `--format sacm` flag that exports SACM XML
- CAE tree becomes the single source of truth for both

**Rationale:** The existing `/create-gsn-diagram` skill handles rendering. The evidence case builder focuses on building the CAE structure. Integration is a wiring task, not an architectural one.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-04-14 | Initial CAE tree structure, compliance officer framing |
| 1.1 | 2026-04-14 | Clarified QRAs as inference layer, not evidence |
| 1.2 | 2026-04-14 | Added outstanding implementation questions |
| 1.3 | 2026-04-14 | Resolved implementation questions per Codex review |
