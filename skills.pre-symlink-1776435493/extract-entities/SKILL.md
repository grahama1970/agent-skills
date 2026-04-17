---
name: extract-entities
description: >
  Extract control IDs, domain phrases, taxonomy tags, and relationship data from question text.
  Composes /memory (ArangoDB recall to load sparta_controls vocabulary).
  Returns structured EntityExtractionResult that defines the shape of evidence cases, conversations,
  and QRA reviews before any LLM runs. Zero LLM cost — Flashtext (Aho-Corasick) + RapidFuzz (Levenshtein).
  NO REGEX.
allowed-tools: [Bash, Read]
triggers:
  - extract entities
  - what entities
  - what controls
  - decompose question
  - parse question
metadata:
  short-description: Extract controls, phrases, and relationships from question text
  author: "Horus"
  version: "0.1.0"
provides:
  - entity-extraction
composes:
  - memory
  - taxonomy
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# /extract-entities

Extract control IDs, domain phrases, control metadata, relationship edges, and taxonomy tags from any question text. The extraction result defines the shape of the evidence tree before any gates or LLM calls run.

## Architecture (NO REGEX, NO LLM)

### Why Flashtext Instead of ArangoDB Search?

**ArangoDB text analyzers LEMMATIZE and TOKENIZE input.** "CWE-79" becomes two tokens: `cwe` and `79` (split on hyphen). This breaks exact entity matching.

Flashtext does **exact string matching on raw text** before any tokenization. It finds "CWE-79" as a single unit.

ArangoDB BM25/text search is used in Step 4 for finding **related content** after we already know what entities exist via Flashtext/RapidFuzz.

### The Flow

The extraction flow is purely deterministic:

```
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: Load Vocabulary                                         │
│   /memory recall → get ALL sparta_controls (~8,000 entries)     │
│   → Load control_ids + names into Flashtext KeywordProcessor    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: Flashtext (Aho-Corasick)                                │
│   Run on RAW question text (no tokenization)                    │
│   → Returns exact matches with positions                        │
│   Example: "CWE-79" found at [32:38]                            │
│   These become PROTECTED TERMS                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 3: RapidFuzz (Levenshtein Distance)                        │
│   For unmatched terms that might be typos                       │
│   → "CWE-7" suggests "CWE-79" (distance: 1)                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 4: Hybrid Search (BM25 + Dense)                            │
│   Search question against sparta collections                    │
│   → sparta_qra, sparta_controls, sparta_url_knowledge           │
│   → Returns recall_items (evidence)                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 5: spaCy Noun Phrase Extraction + Truncation               │
│   Extract noun phrases from remaining text                      │
│   (excluding protected terms from Steps 2-3)                    │
│   → "ham sandwiches relate" extracted                           │
│   → Truncate glue words (NLTK POS tagging):                     │
│     - Strip trailing verbs: "relate" (VBP) removed              │
│     - Strip leading articles/prepositions                       │
│   → "ham sandwiches" = cleaned phrase                           │
│   → Check against corpus (recall_items)                         │
│   → "ham sandwiches" = not in corpus = ungrounded               │
│                                                                 │
│   OUTPUT: Same JSON structure as Flashtext entities:            │
│   resolution_map["ham sandwiches"] = {                          │
│     exists: false,                                              │
│     in_corpus: false,                                           │
│     match_type: "noun_phrase"                                   │
│   }                                                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Output: EntityExtractionResult                                  │
│   control_ids: ["CWE-79"]                                       │
│   resolution_map: {                                             │
│     "CWE-79": {exists: true, match_type: "exact"},              │
│     "ham sandwiches": {exists: false, in_corpus: false}         │
│   }                                                             │
│   recall_items: [QRAs about XSS...]                             │
└─────────────────────────────────────────────────────────────────┘
```

**Critical rules:**
- NO REGEX — Flashtext (Aho-Corasick), RapidFuzz (Levenshtein), spaCy (NLP)
- NO LLM — extraction is 100% deterministic
- NO manual tokenization — Flashtext runs on raw text, spaCy handles NLP
- Vocabulary comes from ArangoDB via /memory, not hardcoded lists
- Protected terms (from Flashtext/RapidFuzz) are excluded before spaCy runs

## Usage

```bash
# Extract entities from a question
./run.sh extract "What does radar spoofing have to do with SV-AC-2 and CWE-89?"

# Include taxonomy bridge attributes
./run.sh extract --taxonomy "How do NIST 800-171 requirements align with SPARTA defenses?"

# JSON output for piping
./run.sh extract --json "Tell me about Control SV-CF-1 as it relates to D3FEND"

# Resolve entities from free text (NLP mode, default)
./run.sh resolve "radar spoofing impacts sensor fusion"

# Resolve entities from delimited tokens (auto: comma/semicolon/whitespace)
./run.sh resolve --delimiter auto "SV-AC-2, CWE-89 radar_spoofing"

# Resolve entities from custom delimiter-separated tokens
./run.sh resolve --delimiter "|" "SV-AC-2|CWE-89|unknown_token"
```

`resolve --delimiter` modes:
- `nlp` (default): FlashText + fuzzy matching against collection dictionary
- `auto`: split input by commas, semicolons, and whitespace, then lookup each token via `/list`
- custom string: split on the provided delimiter, then lookup each token via `/list`

### Default stdin mode (no subcommand)

When invoked without a subcommand, the script reads from stdin. Use `--delimiter` to
control entity extraction mode and `--collection` to target any ArangoDB collection.

```bash
# Delimiter mode: split tokens, lookup each by control_id filter
echo "CA-7,PM-6,REC-0001" | python3 extract_entities.py \
  --delimiter auto --collection sparta_controls

# NLP mode (default when --delimiter is omitted): FlashText + fuzzy over collection
echo "What countermeasures for supply chain?" | python3 extract_entities.py \
  --collection sparta_controls
```

**Stdin flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--delimiter` / `-d` | *(omit for NLP)* | `auto` splits on `,;` + whitespace; any other string is used as literal delimiter |
| `--collection` / `-c` | `sparta_controls` | ArangoDB collection to match against |
| `--name-field` | `name` | Field containing human-readable entity name |
| `--label-field` | `control_id` | Field used as display label (e.g. `control_id`) |
| `--framework-field` | `source_framework` | Field containing framework name |
| `--type-field` | `node_type` | Field containing entity type |
| `--limit` | `500` | Max entity docs loaded for NLP FlashText dictionary |
| `--scope` | *(empty)* | Scope filter for `/recall` enrichment (NLP mode only) |

**Delimiter mode lookup:** For each token, first issues
`POST /list {"collection": …, "limit": 1, "filters": {"control_id": token}, "return_fields": ["control_id", "name", "source_framework"]}`.
Falls back to `q`-based search with exact name/label match if the filter returns nothing.

**Output shape (both modes):**

```json
{
  "text": "CA-7,PM-6,REC-0001",
  "collection": "sparta_controls",
  "delimiter": "auto",
  "entity_count": 3,
  "entities": [
    {"token": "CA-7",     "id": "…", "name": "Continuous Monitoring", "label": "CA-7", "framework": "NIST", "exists": true},
    {"token": "PM-6",     "id": "…", "name": "…",                     "label": "PM-6", "framework": "NIST", "exists": true},
    {"token": "REC-0001", "id": "",  "name": "REC-0001",              "label": "",      "framework": "",     "exists": false}
  ],
  "entity_names": ["Continuous Monitoring", "…", "REC-0001"],
  "entity_ids": ["sparta_controls/…", "sparta_controls/…"]
}
```

## Output

```json
{
  "control_ids": ["SV-AC-2", "CWE-89"],
  "phrases": ["radar spoofing"],
  "phrase_controls": ["SV-CF-1", "SV-CF-3"],
  "all_control_ids": ["CWE-89", "SV-AC-2", "SV-CF-1", "SV-CF-3"],
  "control_metadata": [
    {"control_id": "SV-AC-2", "name": "Access Control", "framework": "SPARTA", "domain": "..."}
  ],
  "related_pairs": [
    {"source": "SV-AC-2", "target": "SV-CF-1", "method": "mitigates"}
  ],
  "taxonomy_tags": {"sparta": ["Signal_Manipulation"], "behavioral": ["Corruption"]},
  "unresolved_terms": [
    {"term": "X23-MUSTARD", "type": "id_like", "exists": false,
     "reason": "no_match_in_sparta_controls", "closest_match": "CM0028", "distance": 0.85}
  ],
  "resolution_map": {
    "SV-AC-2": {"exists": true, "match_type": "exact", "control_id": "SV-AC-2",
                "name": "Access Control", "qra_count": 14},
    "X23-MUSTARD": {"exists": false, "reason": "no_match_in_sparta_controls",
                    "closest_match": "CM0028", "distance": 0.85}
  }
}
```

### Grounding Evidence Fields (v4.3)

- **`unresolved_terms`**: Terms from the question that look like entity references but didn't resolve against `sparta_controls`. Each entry has `term`, `type` (id_like, phrase, text_fragment), and optionally `closest_match`/`distance` for fuzzy near-misses.
- **`resolution_map`**: Per-candidate term resolution status. Shows what resolved (`exists: true` with control_id, name, qra_count) and what didn't (`exists: false` with reason). The agent reads this to decide if the question's premise is grounded or fabricated.
```

## Composability

Used by:
- `/create-evidence-case` — Gate 2 calls this to define the tree shape
- Conversation pipeline — entity gate before Brandon answers
- `/sparta-stress-test` — validates entity extraction accuracy
- `/review-question` — checks if question entities are answerable
- Any future skill that needs to know "what controls/phrases are in this text"

Backend: `graph_memory.entity_extraction.extract_entities()` — not a silo.

## Common Mistakes

### WRONG: Using regex to parse control IDs from free text
```python
import re
ids = re.findall(r'[A-Z]{2}-\d+', text)  # misses fuzzy matches, no grounding check
```

### RIGHT: Use extract-entities for structured extraction with grounding
```bash
./run.sh extract --json "What about SV-AC-2 and CWE-89?"
# Returns: control_ids, confidence, resolution_map, unresolved_terms
```

### WRONG: Trusting all extracted entities without checking grounding_ok
```python
entities = extract(question)
proceed(entities)  # some may be fabricated!
```

### RIGHT: Check grounding_ok and warnings before proceeding
```python
result = extract(question)
if not result["grounding_ok"]:
    # Check warnings for fabricated_id, not_in_corpus
    for w in result["warnings"]:
        if w["category"] == "fabricated_id":
            flag_adversarial(question)
```

### WRONG: Using NLP mode for delimiter-separated token lists
```bash
echo "CA-7,PM-6,REC-0001" | python3 extract_entities.py  # NLP mode, loses structure
```

### RIGHT: Use --delimiter for token lists
```bash
echo "CA-7,PM-6,REC-0001" | python3 extract_entities.py --delimiter auto
```

## Resolve Output

`/extract-entities resolve` returns:
- `entities`: list of per-match or per-token objects
- Each entity includes `id`, `name`, `label`, `framework`, `exists`
- In delimiter modes, each input token is looked up via `/list` and returned with `exists: true|false`

## Framework Reference (sparta_controls)

Entities are stored in `sparta_controls` with `source_framework` indicating origin.

### Frameworks in sparta_controls

| Framework | ID Pattern | Count | Has crosswalk to SPARTA? |
|-----------|------------|-------|--------------------------|
| `SPARTA` | `DE-*`, `EX-*`, `IA-*`, `CM*`, `ARFS-*` | 500+ | (is SPARTA) |
| `CWE` | `CWE-*` | 964 | Yes (2,825+ direct edges) |
| `NIST` | `AC-*`, `SI-*`, `CM-*`, etc. | 1,000+ | Yes (NIST→SPARTA edges) |
| `CAPEC` | `CAPEC-*` | 615 | Yes (via ATT&CK) |
| `ATT&CK` | `T*` | 700+ | Yes (sparse) |
| `ISO` | `A.*`, numeric | 100+ | No |
| `D3FEND` | `D3-*` | 200+ | No |

### Key Fields by Framework

| Framework | Key Fields | Use |
|-----------|------------|-----|
| CWE | `nist_control_ids`, `capec_ids`, `pillar_cwe` | Crosswalk lookups |
| SPARTA | `cwe_class_ids`, `tor_threats` | CWE mapping, NIST links |
| NIST | `related_controls` | Enhancement hierarchy |
| CAPEC | `attack_technique_ids` | ATT&CK links |

### Crosswalk Edge Casing (CRITICAL for /list filters)

When querying `sparta_relationships` for crosswalk chains:

| Edge Type | source_framework | target_framework |
|-----------|-----------------|------------------|
| CWE→SPARTA | `"CWE"` | `"SPARTA"` (uppercase) |
| NIST→SPARTA | `"nist"` | `"sparta"` (lowercase) |
| CAPEC→CWE | `"CAPEC"` | `"CWE"` |
| CWE→CWE | `"cwe"` | `"cwe"` (lowercase) |

**Always check both `"sparta"` and `"SPARTA"`** when filtering for SPARTA targets.
