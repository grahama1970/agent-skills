# /taxonomy Walkthrough: How Mind Tags Get Assigned

> Entity extraction is `/extract-entities`' job (flashtext + ArangoDB).
> `/taxonomy` looks up Mind tags for pre-extracted control IDs. No regex.

---

## The Two Jobs

| Skill | Job | Tool | Output |
|-------|-----|------|--------|
| `/extract-entities` | Find control IDs in text | flashtext (Aho-Corasick) + ArangoDB | `control_ids: ["CWE-119", "REC-0001"]` |
| `/taxonomy` | Look up Mind tags for those IDs | ArangoDB `sparta_controls` lookup | `mind: ["Exploit", "Harden", "Model"]` |

```
Text → /extract-entities (flashtext) → control_ids → /taxonomy (ArangoDB lookup) → mind tags
```

---

## Step-by-Step: /extract-entities

Input:
```
"How should we apply formal verification to protect against CWE-119
 buffer overflow in the F-36's FADEC firmware, given SPARTA REC-0001
 reconnaissance risks?"
```

1. **flashtext (Aho-Corasick)** — Loads all 11,620 control names from `sparta_controls` into a `KeywordProcessor`. Scans text in O(n). Matches against the *actual ArangoDB vocabulary* — no regex. If a control exists in the corpus and appears in the text, flashtext finds it.
2. **RapidFuzz fallback** — If flashtext finds nothing, fuzzy matching catches typos ("CWE-7" → "CWE-79", score 80+).
3. **Verify via /memory daemon** — httpx to `/list` endpoint confirms each flashtext match exists and gets metadata (framework, etc.). No bespoke AQL — the daemon handles DB queries internally.
4. **Hybrid search** — BM25 + semantic for related items not mentioned by exact name
5. **Spellcheck + corpus membership** — Concurrent with Step 4. Classifies remaining phrases as domain vocab, misspellings, or fabricated.

> **Why not regex?** Control IDs get mangled by lemmatization and NLP tokenization.
> Regex is extremely brittle — only flashtext matching against the real corpus is reliable.

Output:
```json
{
  "control_ids": ["CWE-119", "REC-0001"],
  "grounding_ok": true,
  "resolution_map": {
    "CWE-119": {"exists": true, "match_type": "exact", "confidence": 1.0},
    "REC-0001": {"exists": true, "match_type": "exact", "confidence": 1.0}
  }
}
```

---

## Step-by-Step: /taxonomy

Input: pre-extracted `control_ids` from above.

```python
extract_taxonomy(
    text="How should we apply formal verification...",
    collection="sparta",
    fast=True,
    control_ids=["CWE-119", "REC-0001"],
)
```

### Tier 0: Look up mind tags (~5ms)

For each control ID, query `sparta_controls` and read the stored `mind` field:

```
CWE-119 → POST /list {filters: {control_id: "CWE-119"}}
         → mind: ["Exploit", "Harden"]

REC-0001 → POST /list {filters: {control_id: "REC-0001"}}
          → mind: ["Model"]
```

Set union: `["Exploit", "Harden"] ∪ ["Model"] = ["Exploit", "Harden", "Model"]`

### Tier 0.5: DistilBERT classifier (~3ms)

Predicts Mind tags from text content. **Only used if confidence ≥ 95%** — the classifier must be near-certain. Below that, the system trusts T0 deterministic lookups or falls through to T2.

This follows the **Sensai Cascade**: most cases are deterministic (T0), classifiers only contribute when near-certain (T0.5 at ≥95%), and Claude (T2) handles the grey zone.

### Tier 2: LLM — grey zone only

Only fires when T0 and T0.5 are both insufficient. The LLM (Claude Sonnet) makes the judgment call on ambiguous cases. Skipped in `fast=True` mode.

### Heart dimension (always runs)

Keyword scan for emotional tags (anger, fear, joy, sadness, trust).

### Result

```json
{
  "mind": ["Exploit", "Harden", "Model"],
  "heart": [],
  "method": "fast+refs",
  "confidence": 0.3
}
```

---

## Where Do Mind Tags on Controls Come From?

They're pre-computed at **ingestion time** by the SPARTA pipeline (`01c_load_capec.py`).

### CWE-117 (Log Injection) — Full Chain

```
Step 1: CAPEC XML lists attack patterns for CWE-117
        CAPEC-268 → CWE-117  (curated:CAPEC→CWE)
        CAPEC-81  → CWE-117
        CAPEC-93  → CWE-117

Step 2: CAPEC XML lists ATT&CK techniques for CAPEC-268
        CAPEC-268 → T1070     (curated:CAPEC→ATT&CK)
        CAPEC-268 → T1562.002
        CAPEC-268 → T1562.003
        CAPEC-268 → T1562.008

Step 3: Compute shortcut edges
        CWE-117 → T1070     (derived:CWE→CAPEC→ATT&CK)
        CWE-117 → T1562.002
        CWE-117 → T1562.003
        CWE-117 → T1562.008

Step 4: Map ATT&CK tactics to Mind tags
        T1070     → defense-evasion → Evade
        T1562.002 → defense-evasion → Evade

Step 5: Store on CWE-117 document
        mind: ["Evade", "Exploit", "Harden"]
```

At query time, `/taxonomy` just reads `mind` from the document. No chain traversal.

---

## Works for ALL Frameworks

`derive_mind_from_control_ids()` looks up any control ID in `sparta_controls`:

| Framework | Count | Example | Mind Tags |
|-----------|-------|---------|-----------|
| SPARTA | 553 | `REC-0001` | `[Model]` |
| CWE | 969 | `CWE-119` | `[Exploit, Harden]` |
| ATT&CK | 1,778 | `T1070` | (via tactic mapping) |
| CAPEC | 615 | `CAPEC-268` | `[Evade]` |
| D3FEND | 424 | `D3-ACA` | `[Evade, Exploit, Harden, Model, Persist]` |

Live test:
```python
derive_mind_from_control_ids(["CWE-79", "CWE-119", "REC-0001"])
→ ["Evade", "Exploit", "Harden", "Model"]

derive_mind_from_control_ids(["D3-ACA"])
→ ["Evade", "Exploit", "Harden", "Model", "Persist"]
```

---

## Downstream Usage

### /create-evidence-case — Technique Bridge Gate
```python
mind_overlap = mind_sets[0] & mind_sets[1]
# CWE-119: {Exploit, Harden}  ∩  D3-ACA: {Evade, Exploit, Harden, Model, Persist}
# = {Exploit, Harden} → related = True
```

### 08b_score_relationships.py — Gate 3
```python
mind_jaccard = len(mind_inter) / len(mind_union)
gate3 = len(mind_inter) > 0  # At least one shared Mind tag
```

### /memory — At document insertion
```python
result = extract_taxonomy(text, collection=scope, control_ids=extracted_ids)
doc["mind"] = result["mind"]
```
