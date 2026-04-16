# Evidence Case Validation for QRAs

**Last Updated:** 2026-04-14
**Status:** Implementation complete (Pass 2 lineage integration)

## What We're Trying to Accomplish

### The Problem

QRAs (Question-Rationale-Answer triples) are the atomic units of knowledge in our SPARTA compliance system. But a QRA in isolation is unverifiable:

- Does it actually relate to the security concern being asked about?
- Is it grounded in real framework entities (CWE, SPARTA, ATT&CK)?
- Are there other QRAs that corroborate or complement it?
- Is the answer authoritative or hallucinated?

### The Solution: Evidence Cases

An **Evidence Case** assembles all the contextual data an LLM (or human) needs to **validate** whether a QRA should be trusted as evidence for a compliance decision.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         EVIDENCE CASE STRUCTURE                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Question: "How do I protect satellite uplinks from RF jamming attacks?"    │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ GROUNDING LAYER (Deterministic)                                     │   │
│  ├─────────────────────────────────────────────────────────────────────┤   │
│  │                                                                     │   │
│  │  Entities Extracted:                                                │   │
│  │    • IA-0006 (SPARTA: Secure Command and Control Link)              │   │
│  │    • IA-0007 (SPARTA: Uplink Protection)                            │   │
│  │    • CWE-924 (Improper Enforcement of Message Integrity)            │   │
│  │                                                                     │   │
│  │  Crosswalk Chains:                                                  │   │
│  │    • CWE-924 → IA-0006 (direct SPARTA mapping)                      │   │
│  │    • CWE-924 → NIST SP.800-53:SC-8 → IA-0007 (Heimdall path)        │   │
│  │                                                                     │   │
│  │  Glossary:                                                          │   │
│  │    • IA-0006: "Ensure integrity/authenticity of C2 uplinks..."      │   │
│  │    • IA-0007: "Protect uplink channel from interference..."         │   │
│  │    • CWE-924: "Product does not verify message integrity..."        │   │
│  │                                                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ EVIDENCE LAYER (Lineage-Based)                                      │   │
│  ├─────────────────────────────────────────────────────────────────────┤   │
│  │                                                                     │   │
│  │  Primary QRA:                                                       │   │
│  │    Q: "What techniques mitigate RF jamming on command links?"       │   │
│  │    A: "Frequency hopping, spread spectrum, directional antennas..." │   │
│  │    Lineage:                                                         │   │
│  │      entity_ids: [IA-0006, IA-0007, CWE-924]                        │   │
│  │      related_qra_keys: [qra__abc123, qra__def456, qra__ghi789]      │   │
│  │      shared_techniques_map:                                         │   │
│  │        qra__abc123: [IA-0006, IA-0007]  ← shares both techniques    │   │
│  │        qra__def456: [IA-0006]           ← shares one technique      │   │
│  │                                                                     │   │
│  │  Related QRAs (via lineage):                                        │   │
│  │    [qra__abc123] Q: "How to implement frequency hopping?"           │   │
│  │                  A: "Use MIL-STD-188 compliant spread spectrum..."  │   │
│  │                  shared_techniques: [IA-0006, IA-0007]              │   │
│  │                                                                     │   │
│  │    [qra__def456] Q: "What are C2 link integrity requirements?"      │   │
│  │                  A: "Per SPARTA IA-0006, implement authenticated..." │   │
│  │                  shared_techniques: [IA-0006]                       │   │
│  │                                                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ VALIDATION LAYER (LLM-Gated, Optional)                              │   │
│  ├─────────────────────────────────────────────────────────────────────┤   │
│  │                                                                     │   │
│  │  filter_related_qras() Results:                                     │   │
│  │    Gate 1: aids_user_query           ✓ PASS                         │   │
│  │    Gate 2: addresses_same_concern    ✓ PASS                         │   │
│  │    Gate 3: complements_not_duplicates ✓ PASS                        │   │
│  │    Gate 4: shares_technique_meaningfully ✓ PASS                     │   │
│  │                                                                     │   │
│  │  LLM Decision:                                                      │   │
│  │    action: ANSWER                                                   │   │
│  │    reason: "Strong evidence: crosswalk chains + related QRAs"       │   │
│  │    evidence_strength:                                               │   │
│  │      has_crosswalk_chains: true                                     │   │
│  │      has_prior_qra: true                                            │   │
│  │      has_related_qra: true                                          │   │
│  │      shared_technique_count: 2                                      │   │
│  │                                                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## The Three Passes of Lineage Building

### Pass 1: Entity Extraction (`lineage.entity_ids`)

**What it does:** Extracts framework entity IDs from each QRA's question and answer text.

**How:** FlashText keyword processor + crosswalk graph traversal

**Result:**
```json
{
  "lineage": {
    "entity_ids": ["IA-0006", "IA-0007", "CWE-924", "CAPEC-160"],
    "graph_version": "v1"
  }
}
```

**Why it matters:** Without knowing WHICH entities a QRA references, we can't determine if it's relevant to a specific compliance question.

### Pass 2: Related QRA Keys (`lineage.related_qra_keys`)

**What it does:** Finds other QRAs that share the same SPARTA techniques.

**How:** 
1. Build inverted index: SPARTA technique → [qra_keys]
2. For each QRA, lookup its entity_ids in the index
3. Collect all QRA keys that share those techniques
4. Cap at 500 keys per entity (IA-0006 alone appears in 131K+ QRAs)

**Result:**
```json
{
  "lineage": {
    "entity_ids": ["IA-0006", "IA-0007"],
    "related_qra_keys": ["qra__abc123", "qra__def456", "qra__ghi789"],
    "shared_techniques_map": {
      "qra__abc123": ["IA-0006", "IA-0007"],
      "qra__def456": ["IA-0006"],
      "qra__ghi789": ["IA-0007"]
    },
    "graph_version": "v2"
  }
}
```

**Why it matters:** The `shared_techniques_map` tells us WHY QRAs are related — not just that they are. An LLM can now see: "These two QRAs both discuss IA-0006 (Secure C2 Link), so they likely provide complementary evidence."

### Pass 3: LLM Filtering (`filter_related_qras()`)

**What it does:** Applies 4 hard gates to determine if related QRAs actually help answer the question.

**Gates:**
1. **aids_user_query** — Does this QRA help answer what the user asked?
2. **addresses_same_concern** — Does it address the same security concern?
3. **complements_not_duplicates** — Does it add new info (not just repeat)?
4. **shares_technique_meaningfully** — Is the technique overlap substantive?

**Why it matters:** Just because two QRAs share a technique doesn't mean one helps validate the other. Pass 3 ensures we only include QRAs that an LLM judged as actually relevant.

---

## Complete Pipeline Flow

```
                              ┌─────────────────┐
                              │    Question     │
                              │  or Control ID  │
                              └────────┬────────┘
                                       │
                    ╔══════════════════╧══════════════════╗
                    ║        DETERMINISTIC PHASE          ║
                    ╚══════════════════╤══════════════════╝
                                       │
                              ┌────────▼────────┐
                              │ /extract-entities│
                              │ FlashText + NER │
                              └────────┬────────┘
                                       │
                              ┌────────▼────────┐
                              │  Graph Traversal │
                              │ Crosswalk chains │
                              └────────┬────────┘
                                       │
                              ┌────────▼────────┐
                              │  Build Glossary  │
                              │ Entity definitions│
                              └────────┬────────┘
                                       │
                              ┌────────▼────────┐
                              │ Hybrid QRA Recall│
                              │ BM25 + cosine    │
                              └────────┬────────┘
                                       │
                              ┌────────▼────────┐
                              │ Lineage Lookup   │
                              │ related_qra_keys │
                              │ shared_techniques│
                              └────────┬────────┘
                                       │
                              ┌────────▼────────┐
                              │ Fetch Related    │
                              │ QRAs by _key     │
                              └────────┬────────┘
                                       │
                         ┌─────────────┴─────────────┐
                         │    has_evidence?          │
                         └─────────────┬─────────────┘
                                       │
                    ╔══════════════════╧══════════════════╗
                    ║      LLM-EXPENSIVE PHASE            ║
                    ║      (if enable_llm=true)           ║
                    ╚══════════════════╤══════════════════╝
                                       │
                              ┌────────▼────────┐
                              │filter_related_qras│
                              │   4 hard gates   │
                              └────────┬────────┘
                                       │
                              ┌────────▼────────┐
                              │  LLM Decision   │
                              │ANSWER│DEFLECT│CLARIFY│
                              └────────┬────────┘
                                       │
                    ╔══════════════════╧══════════════════╗
                    ║           OUTPUT TIERS              ║
                    ╚══════════════════╤══════════════════╝
                                       │
            ┌──────────────────────────┼──────────────────────────┐
            │                          │                          │
    ┌───────▼───────┐         ┌───────▼───────┐         ┌───────▼───────┐
    │    TIER 1     │         │    TIER 2     │         │    TIER 3     │
    │ Informational │         │   Grounded    │         │   Verified    │
    │    (null)     │         │  chains only  │         │ chains+proof  │
    │               │         │               │         │    +SACM      │
    │ No evidence   │         │ Crosswalk +   │         │ LLM-filtered  │
    │ found         │         │ related QRAs  │         │ + formal proof│
    └───────────────┘         └───────────────┘         └───────────────┘
```

---

## Example Evidence Case Response

```json
{
  "question_text": "How do I protect satellite uplinks from RF jamming?",
  "review_status": "passed",
  
  "glossary": [
    {
      "id": "IA-0006",
      "name": "Secure Command and Control Link",
      "framework": "SPARTA",
      "type": "countermeasure",
      "description": "Ensure the integrity and authenticity of command and control uplinks through encryption and authentication mechanisms."
    },
    {
      "id": "CWE-924",
      "name": "Improper Enforcement of Message Integrity",
      "framework": "CWE",
      "type": "weakness",
      "description": "The product does not properly verify that a message was transmitted intact."
    }
  ],
  
  "crosswalk_chains": [
    {
      "from": "CWE-924",
      "from_framework": "CWE",
      "to_framework": "SPARTA",
      "hops": [
        {"id": "IA-0006", "name": "Secure C2 Link", "framework": "SPARTA"}
      ]
    },
    {
      "from": "CWE-924",
      "from_framework": "CWE",
      "to_framework": "SPARTA",
      "relationship": "via_nist",
      "hops": [
        {"id": "SC-8", "name": "Transmission Confidentiality", "framework": "NIST"},
        {"id": "IA-0007", "name": "Uplink Protection", "framework": "SPARTA"}
      ]
    }
  ],
  
  "prior_qra_evidence": [
    {
      "_key": "qra__rf_jamming_001",
      "citation_id": "IA-0006",
      "question": "What techniques mitigate RF jamming on command links?",
      "answer": "Frequency hopping (MIL-STD-188), spread spectrum modulation, directional antennas with null steering, and encrypted command authentication per SPARTA IA-0006.",
      "lineage": {
        "entity_ids": ["IA-0006", "IA-0007", "CWE-924"],
        "related_qra_keys": ["qra__freq_hop_002", "qra__c2_integrity_003"],
        "shared_techniques_map": {
          "qra__freq_hop_002": ["IA-0006", "IA-0007"],
          "qra__c2_integrity_003": ["IA-0006"]
        }
      }
    }
  ],
  
  "related_qra_evidence": [
    {
      "_key": "qra__freq_hop_002",
      "question": "How to implement frequency hopping for satellite C2?",
      "answer": "Use MIL-STD-188-compliant spread spectrum with cryptographically secure hop sequences. Ensure synchronization via GPS timing reference.",
      "control_id": "IA-0006",
      "shared_techniques": ["IA-0006", "IA-0007"],
      "gate_passed": true
    },
    {
      "_key": "qra__c2_integrity_003",
      "question": "What are command link integrity requirements for SPARTA compliance?",
      "answer": "Per SPARTA IA-0006, implement authenticated encryption (AES-GCM or ChaCha20-Poly1305) with anti-replay protection via sequence numbers.",
      "control_id": "IA-0006",
      "shared_techniques": ["IA-0006"],
      "gate_passed": true
    }
  ],
  
  "shared_techniques_summary": {
    "IA-0006": ["qra__freq_hop_002", "qra__c2_integrity_003"],
    "IA-0007": ["qra__freq_hop_002"]
  },
  
  "llm_filter_results": {
    "candidates_evaluated": 3,
    "candidates_passed": 2,
    "model": "deepseek-ai/DeepSeek-V3"
  },
  
  "llm_decision": {
    "action": "ANSWER",
    "reason": "Strong evidence: crosswalk chains + related QRAs with shared techniques",
    "evidence_strength": {
      "has_crosswalk_chains": true,
      "has_prior_qra": true,
      "has_related_qra": true,
      "shared_technique_count": 2
    }
  },
  
  "cwe_record": {
    "control_id": "CWE-924",
    "description": "The product does not properly verify that a message was transmitted intact.",
    "extended_description": "This can allow attackers to modify messages in transit without detection."
  },
  
  "target_records": [
    {
      "control_id": "IA-0006",
      "framework": "SPARTA",
      "description": "Ensure integrity and authenticity of C2 uplinks"
    },
    {
      "control_id": "IA-0007",
      "framework": "SPARTA", 
      "description": "Protect uplink channel from interference and jamming"
    }
  ]
}
```

---

## Validation Criteria

An LLM (or human reviewer) evaluates the evidence case against these criteria:

### 1. Grounding Validation
- **Are entities correctly identified?** Check glossary against question text
- **Are crosswalk chains valid?** Follow the hops from source to target framework
- **Is the framework coverage complete?** CWE → NIST → SPARTA paths exist?

### 2. QRA Quality Validation  
- **Does the primary QRA answer the question?** Compare question_text to QRA.question
- **Is the answer substantive?** Not a redirect or "see also" response
- **Are entity_ids in lineage actually mentioned?** grep for IDs in Q&A text

### 3. Related QRA Validation
- **Do shared_techniques make sense?** The technique overlap should be domain-relevant
- **Did related QRAs pass LLM gates?** Check gate_passed and llm_filter_results
- **Do related QRAs add new information?** Not just paraphrases of primary

### 4. Decision Validation
- **Is ANSWER appropriate?** Evidence strength should justify answering
- **Should it CLARIFY instead?** If evidence is thin, clarification is honest
- **Is DEFLECT warranted?** Only for truly off-topic queries

---

## API Usage

### Basic Evidence Case (Deterministic Only)
```bash
curl -X POST http://localhost:8602/build-evidence-case \
  -H "Content-Type: application/json" \
  -d '{
    "question": "How do I protect satellite uplinks from RF jamming?",
    "enable_llm": false
  }'
```

### Full Evidence Case (With LLM Filtering)
```bash
curl -X POST http://localhost:8602/build-evidence-case \
  -H "Content-Type: application/json" \
  -d '{
    "question": "How do I protect satellite uplinks from RF jamming?",
    "enable_llm": true,
    "max_related_qras": 30
  }'
```

### Batch Mode (For Lineage Backfill)
```bash
curl -X POST http://localhost:8602/build-evidence-case \
  -H "Content-Type: application/json" \
  -d '{
    "question": "CWE-924 implications",
    "source_id": "CWE-924",
    "skip_qra_recall": true
  }'
```

---

## Key Files

| File | Purpose |
|------|---------|
| `src/graph_memory/service/app/_entities.py` | Evidence case endpoint + entity resolution |
| `src/graph_memory/maintenance/lineage_backfill.py` | Pass 1-2 lineage population |
| `src/graph_memory/inference/filter_related_qras.py` | Pass 3 LLM filtering (4 gates) |
| `src/graph_memory/hybrid_search/_sparta.py` | BM25+cosine QRA recall |

---

## Metrics

| Metric | Current Value | Target |
|--------|---------------|--------|
| QRAs with lineage.entity_ids | 230K | 230K |
| QRAs with lineage.related_qra_keys | ~100K (43% done) | 230K |
| Average related_qra_keys per QRA | 15-30 | 20-50 |
| LLM filter pass rate | ~60-70% | 50-80% |
| Evidence case latency (no LLM) | <500ms | <1s |
| Evidence case latency (with LLM) | 2-5s | <10s |

---

---

## Complete LLM Prompt Example

This section shows the **exact prompt** sent to the LLM when `enable_llm=true`. This is what the LLM sees and must respond to.

### System Prompt (Always Sent)

```
You are a SPARTA compliance expert assistant. Your role is to help users understand space system security requirements by providing grounded, authoritative answers.

You have access to an evidence case containing:
- Glossary: Definitions of relevant security entities (CWE, SPARTA, ATT&CK, CAPEC)
- Crosswalk Chains: Mappings between frameworks (e.g., CWE-924 → IA-0006)
- QRA Evidence: Question-Rationale-Answer triples from the knowledge base
- Related QRAs: Additional QRAs that share SPARTA techniques with the primary evidence

CRITICAL RULES:
1. Only cite entities that appear in the glossary or crosswalk chains
2. Only make claims supported by the QRA evidence
3. If evidence is insufficient, say so — do not hallucinate
4. Prefer specific, actionable guidance over vague generalities
5. When citing SPARTA controls, use the format "SPARTA IA-0006" or similar

OUTPUT FORMAT: Return valid JSON matching the schema below.
```

### User Prompt (ANSWER Action)

```
Based on the evidence case below, synthesize a grounded answer to the user's question.

## User Question
How do I protect satellite command uplinks from RF jamming attacks?

## Glossary (Entity Definitions)
- IA-0006 (SPARTA): Ensure the integrity and authenticity of command and control uplinks through encryption and authentication mechanisms. Implement secure protocols that verify the source of commands before execution.
- IA-0007 (SPARTA): Protect uplink communication channels from interference and jamming through signal processing techniques, frequency management, and physical layer security measures.
- CWE-924 (CWE): Improper Enforcement of Message Integrity During Transmission in a Communication Channel - The product does not adequately verify that a message was not modified during transmission, which can allow attackers to modify critical data or commands.
- CM-0011 (SPARTA): Implement spread spectrum techniques such as frequency hopping or direct sequence spread spectrum to increase resistance to jamming and interception.
- CAPEC-160 (CAPEC): Exploitation of Continuous Variable Transmission - An adversary manipulates the continuous transmission of data over a communication channel to intercept, modify, or disrupt the flow of information.

## Crosswalk Chains (Framework Mappings)
- CWE-924 (CWE) → IA-0006 (SPARTA: Secure Command and Control Link)
- CWE-924 (CWE) → SC-8 (NIST: Transmission Confidentiality and Integrity) → IA-0007 (SPARTA: Uplink Protection)
- CAPEC-160 (CAPEC) → T1498 (ATT&CK: Network Denial of Service) → DE-0003 (SPARTA: Detect Jamming)

## Primary QRA Evidence
- Q: What techniques mitigate RF jamming on command links?
  A: Frequency hopping (MIL-STD-188), spread spectrum modulation, directional antennas with null steering, and encrypted command authentication per SPARTA IA-0006. Additionally, implement signal strength monitoring to detect jamming attempts early.
- Q: How should satellite operators implement command link integrity per SPARTA?
  A: Per SPARTA IA-0006, implement authenticated encryption (AES-GCM or ChaCha20-Poly1305) with anti-replay protection via sequence numbers. Ensure all command messages include cryptographic authentication tags that verify both origin and integrity.

## Related QRA Evidence (Shared SPARTA Techniques)
- Q: How to implement frequency hopping for satellite C2?
  A: Use MIL-STD-188-compliant spread spectrum with cryptographically secure hop sequences. Ensure synchronization via GPS timing reference or pre-shared hop tables. Consider TRANSEC (transmission security) modes for military-grade protection.
  [shares: IA-0006, IA-0007]
- Q: What are the detection mechanisms for uplink jamming?
  A: Implement AGC (Automatic Gain Control) monitoring, noise floor analysis, and bit error rate tracking. Per SPARTA DE-0003, operators should have automated alerts when signal-to-noise ratio degrades below operational thresholds.
  [shares: IA-0007]

## Shared Techniques Summary
{
  "IA-0006": ["qra__freq_hop_002", "qra__c2_integrity_003"],
  "IA-0007": ["qra__freq_hop_002", "qra__jamming_detect_004"]
}

---

Synthesize an answer that:
1. Directly addresses the user's question
2. Cites specific entities from the glossary (by ID)
3. References QRA evidence where applicable
4. Acknowledges any limitations in the evidence

Return JSON:
{
  "content": "Your synthesized answer here...",
  "citations": ["IA-0006", "CWE-924"],
  "confidence": "high" | "medium" | "low",
  "caveats": ["Any important limitations"]
}
```

### Expected LLM Response (ANSWER)

```json
{
  "content": "To protect satellite command uplinks from RF jamming attacks, implement a defense-in-depth approach combining multiple SPARTA controls:\n\n**1. Spread Spectrum Techniques (CM-0011)**\nImplement frequency hopping using MIL-STD-188-compliant spread spectrum with cryptographically secure hop sequences. This makes jamming significantly more difficult as the attacker must jam across a wide frequency range. Synchronize hop timing via GPS reference or pre-shared tables.\n\n**2. Command Link Integrity (IA-0006)**\nPer SPARTA IA-0006, all command messages must use authenticated encryption (AES-GCM or ChaCha20-Poly1305) with anti-replay protection via sequence numbers. This ensures that even if an attacker intercepts transmissions, they cannot forge valid commands.\n\n**3. Physical Layer Protection (IA-0007)**\nProtect the uplink channel through:\n- Directional antennas with null steering toward jamming sources\n- Signal strength monitoring and AGC analysis\n- Bit error rate tracking to detect degradation\n\n**4. Detection and Response (DE-0003)**\nImplement automated jamming detection with alerts when signal-to-noise ratio drops below operational thresholds. Have contingency procedures for switching to backup frequencies or communication paths.\n\nThis approach addresses CWE-924 (message integrity) through cryptographic authentication and CAPEC-160 (transmission exploitation) through spread spectrum and monitoring.",
  "citations": ["IA-0006", "IA-0007", "CM-0011", "DE-0003", "CWE-924", "CAPEC-160"],
  "confidence": "high",
  "caveats": [
    "Specific implementation details depend on satellite bus and ground segment architecture",
    "Military-grade TRANSEC modes may require additional licensing and certification"
  ]
}
```

---

### User Prompt (CLARIFY Action)

When evidence is insufficient, the LLM receives this prompt:

```
The user's question lacks sufficient grounding evidence. Generate clarifying questions to help refine the query.

## User Question
How do I secure my satellite?

## Available Glossary (What We Know About)
- IA-0006 (SPARTA): Secure Command and Control Link
- IA-0007 (SPARTA): Uplink Protection
- DE-0003 (SPARTA): Detect Jamming
- REC-0001 (SPARTA): Secure Recovery Procedures

## Evidence Status
- Crosswalk chains found: False
- QRA evidence found: False
- Related QRAs found: False

---

Generate 2-3 clarifying questions that would help narrow down the query to something we can answer with our SPARTA compliance knowledge base.

Return JSON:
{
  "questions": ["Clarifying question 1?", "Clarifying question 2?"],
  "reason": "Why we need clarification",
  "suggestions": ["Example: How do I protect satellite C2 links from jamming?"]
}
```

### Expected LLM Response (CLARIFY)

```json
{
  "questions": [
    "Which aspect of satellite security are you most concerned about — command link protection, telemetry security, payload data encryption, or physical access control?",
    "Are you focused on a specific threat type such as jamming, spoofing, interception, or cyber intrusion?",
    "Is this for a commercial, civil, or defense satellite system? Different compliance frameworks may apply."
  ],
  "reason": "The question 'How do I secure my satellite?' is too broad to provide specific, actionable guidance. SPARTA covers over 100 controls across multiple security domains. Narrowing to a specific concern will allow us to provide grounded recommendations with relevant crosswalk mappings.",
  "suggestions": [
    "How do I protect satellite command uplinks from RF jamming?",
    "What encryption should I use for satellite telemetry per SPARTA?",
    "How do I implement secure boot for satellite flight software?"
  ]
}
```

---

### User Prompt (DEFLECT Action)

When the query is off-topic:

```
The user's question appears to be outside the scope of SPARTA compliance and space system security. Generate a helpful redirect.

## User Question
What's the best pizza in New York?

## In-Scope Topics (What This System Covers)
- SPARTA framework controls and countermeasures
- Space system security requirements
- CWE weaknesses relevant to space systems
- ATT&CK techniques targeting space infrastructure
- Compliance mapping between security frameworks

---

Generate a polite redirect that:
1. Acknowledges the question
2. Explains what this system covers
3. Suggests how to rephrase if there's a space security angle

Return JSON:
{
  "message": "Your redirect message here...",
  "in_scope_topics": ["SPARTA controls", "Space system security", "CWE mappings"]
}
```

### Expected LLM Response (DEFLECT)

```json
{
  "message": "I appreciate the question, but I'm specialized in SPARTA compliance and space system security — pizza recommendations are outside my expertise! I can help you with things like:\n\n• Protecting satellite command links from jamming or spoofing\n• Mapping CWE weaknesses to SPARTA countermeasures\n• Understanding ATT&CK techniques that target space infrastructure\n• Compliance requirements for satellite ground segments\n\nIf you have any space security questions, I'm here to help!",
  "in_scope_topics": [
    "SPARTA framework controls",
    "Satellite command and control security",
    "Space system vulnerability analysis",
    "Security framework crosswalks (CWE, CAPEC, ATT&CK, NIST)"
  ]
}
```

---

## Complete Evidence Case API Response

This is the **full JSON response** returned by `/create-evidence-case` with `enable_llm=true`:

```json
{
  "question_text": "How do I protect satellite command uplinks from RF jamming attacks?",
  "review_status": "passed",
  
  "glossary": [
    {
      "id": "IA-0006",
      "name": "Secure Command and Control Link",
      "framework": "SPARTA",
      "type": "countermeasure",
      "description": "Ensure the integrity and authenticity of command and control uplinks through encryption and authentication mechanisms."
    },
    {
      "id": "IA-0007",
      "name": "Uplink Protection",
      "framework": "SPARTA",
      "type": "countermeasure",
      "description": "Protect uplink communication channels from interference and jamming through signal processing techniques."
    },
    {
      "id": "CWE-924",
      "name": "Improper Enforcement of Message Integrity",
      "framework": "CWE",
      "type": "weakness",
      "description": "The product does not adequately verify that a message was not modified during transmission."
    },
    {
      "id": "CM-0011",
      "name": "Spread Spectrum Implementation",
      "framework": "SPARTA",
      "type": "countermeasure",
      "description": "Implement spread spectrum techniques to increase resistance to jamming and interception."
    }
  ],
  
  "crosswalk_chains": [
    {
      "from": "CWE-924",
      "from_framework": "CWE",
      "to_framework": "SPARTA",
      "hops": [
        {"id": "IA-0006", "name": "Secure C2 Link", "framework": "SPARTA", "description": "..."}
      ]
    },
    {
      "from": "CWE-924",
      "from_framework": "CWE",
      "to_framework": "SPARTA",
      "relationship": "via_nist",
      "hops": [
        {"id": "SC-8", "name": "Transmission Confidentiality", "framework": "NIST", "description": "..."},
        {"id": "IA-0007", "name": "Uplink Protection", "framework": "SPARTA", "description": "..."}
      ]
    }
  ],
  
  "prior_qra_evidence": [
    {
      "_key": "qra__rf_jamming_001",
      "citation_id": "IA-0006",
      "question": "What techniques mitigate RF jamming on command links?",
      "answer": "Frequency hopping (MIL-STD-188), spread spectrum modulation, directional antennas with null steering...",
      "lineage": {
        "entity_ids": ["IA-0006", "IA-0007", "CWE-924"],
        "related_qra_keys": ["qra__freq_hop_002", "qra__c2_integrity_003"],
        "shared_techniques_map": {
          "qra__freq_hop_002": ["IA-0006", "IA-0007"],
          "qra__c2_integrity_003": ["IA-0006"]
        },
        "graph_version": "v2"
      }
    }
  ],
  
  "related_qra_evidence": [
    {
      "_key": "qra__freq_hop_002",
      "question": "How to implement frequency hopping for satellite C2?",
      "answer": "Use MIL-STD-188-compliant spread spectrum with cryptographically secure hop sequences...",
      "control_id": "IA-0006",
      "shared_techniques": ["IA-0006", "IA-0007"],
      "gate_passed": true
    },
    {
      "_key": "qra__c2_integrity_003",
      "question": "What are command link integrity requirements for SPARTA compliance?",
      "answer": "Per SPARTA IA-0006, implement authenticated encryption (AES-GCM or ChaCha20-Poly1305)...",
      "control_id": "IA-0006",
      "shared_techniques": ["IA-0006"],
      "gate_passed": true
    }
  ],
  
  "shared_techniques_summary": {
    "IA-0006": ["qra__freq_hop_002", "qra__c2_integrity_003"],
    "IA-0007": ["qra__freq_hop_002"]
  },
  
  "llm_filter_results": {
    "candidates_evaluated": 3,
    "candidates_passed": 2,
    "model": "deepseek-ai/DeepSeek-V3"
  },
  
  "llm_decision": {
    "action": "ANSWER",
    "reason": "Strong evidence: crosswalk chains + related QRAs with shared techniques",
    "evidence_strength": {
      "has_crosswalk_chains": true,
      "has_prior_qra": true,
      "has_related_qra": true,
      "shared_technique_count": 2
    }
  },
  
  "llm_response": {
    "action": "ANSWER",
    "answer": {
      "content": "To protect satellite command uplinks from RF jamming attacks, implement a defense-in-depth approach combining multiple SPARTA controls:\n\n**1. Spread Spectrum Techniques (CM-0011)**\nImplement frequency hopping using MIL-STD-188-compliant spread spectrum...\n\n**2. Command Link Integrity (IA-0006)**\nPer SPARTA IA-0006, all command messages must use authenticated encryption...\n\n**3. Physical Layer Protection (IA-0007)**\nProtect the uplink channel through directional antennas with null steering...",
      "citations": ["IA-0006", "IA-0007", "CM-0011", "DE-0003", "CWE-924"],
      "confidence": "high",
      "caveats": [
        "Specific implementation details depend on satellite bus architecture",
        "Military-grade TRANSEC modes may require additional licensing"
      ]
    },
    "model": "deepseek-ai/DeepSeek-V3",
    "latency_ms": 3420
  },
  
  "cwe_record": {
    "control_id": "CWE-924",
    "description": "Improper Enforcement of Message Integrity During Transmission",
    "extended_description": "The product does not adequately verify that a message was not modified during transmission."
  },
  
  "target_records": [
    {"control_id": "IA-0006", "framework": "SPARTA", "description": "Secure Command and Control Link"},
    {"control_id": "IA-0007", "framework": "SPARTA", "description": "Uplink Protection"}
  ]
}
```

---

## Future Work

1. **Pass 4: Formal Verification** — Lean4 proofs for crosswalk chain validity
2. **SACM Integration** — Structured Assurance Case Metamodel output
3. **Confidence Scoring** — Numeric confidence based on evidence strength
4. **Incremental Lineage** — Update lineage when new QRAs are added
