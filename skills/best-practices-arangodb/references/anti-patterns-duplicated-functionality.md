# Anti-Patterns: Duplicated Functionality (NEVER DO THESE)

These are real patterns that were found and removed from this codebase. They all duplicate what ArangoDB already does.

## 1. Python Stop Word Lists

```python
# REMOVED — ArangoDB text_en handles this
_ENGLISH_STOP_WORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "must", "can", "could", "of", "at", "by",
    "for", "with", "about", "against", "between", "through", "during",
    "before", "after", "above", "below", "to", "from", "up", "down",
    "in", "out", "on", "off", "over", "under", "again", "further",
    "then", "once", "here", "there", "when", "where", "why", "how",
    "all", "both", "each", "few", "more", "most", "other", "some",
    "such", "no", "nor", "not", "only", "own", "same", "so", "than",
    "too", "very", "just", "because", "as", "until", "while",
    "but", "and", "or", "if", "it", "its", "this", "that", "these",
    "those", "i", "me", "my", "we", "our", "you", "your", "he", "him",
    "his", "she", "her", "they", "them", "their", "what", "which", "who",
})
# FIX: Delete this. Use TOKENS(@query, 'text_en') — stop words removed automatically.
```

## 2. Python Suffix Stripping (Poor Man's Stemming)

```python
# REMOVED — ArangoDB text_en uses Snowball stemmer
def _stem_word(word: str) -> str:
    for suffix in ("tion", "sion", "ment", "ness", "ing", "ed", "ly", "er", "est", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) > 2:
            return word[:-len(suffix)]
    return word
# FIX: Delete this. text_en stems properly: "recommendations" → "recommend", not "recommenda".
```

## 3. Regex-Based Framework Classification

```python
# REMOVED — ArangoDB sparta_controls knows definitively
def detect_framework(control_id: str) -> str:
    if control_id.startswith("SV-"): return "SPARTA"
    if control_id.startswith("CWE-"): return "CWE"
    if re.match(r"^AC-\d", control_id): return "NIST"  # WRONG: AC-1 could be NIST OR SPARTA
    if control_id.startswith("D3"): return "D3FEND"
    return "UNKNOWN"
# FIX: Query sparta_controls WHERE control_id == @cid RETURN source_framework
```

## 4. Hardcoded Domain Term Dictionaries

```python
# REMOVED — domain_terms and taxonomy_vocabulary collections are the source of truth
BRIDGE_KEYWORDS = {
    "Precision": ["precise", "timing", "navigation", "sensor", "calibrat"],
    "Resilience": ["recover", "redundan", "fault", "graceful", "degrad"],
    "Fragility": ["vulnerab", "weakness", "attack surface", "single point"],
    "Corruption": ["tamper", "spoof", "integrit", "unauthoriz"],
    "Loyalty": ["trust", "authent", "insider", "access control"],
    "Stealth": ["evasion", "persist", "covert", "detection avoidance"],
}
# FIX: Query taxonomy_vocabulary WHERE category IN ['bridge_keyword', 'bridge_keyword_extended']
# DB-backed cache pattern: _get_bridge_keywords() with module-level cache
```

## 5. Python-Side Cosine Similarity Over All Documents

```python
# REMOVED — brute-force embedding scan
import numpy as np
all_docs = list(db.aql.execute("FOR d IN sparta_qra RETURN {_key: d._key, emb: d.embedding}"))
query_emb = get_embedding(query)
scores = [(d["_key"], np.dot(query_emb, d["emb"])) for d in all_docs]  # 90K+ iterations
top_k = sorted(scores, key=lambda x: -x[1])[:10]
# FIX: Two-stage BM25 top-100 → cosine rerank on 100 candidates only (rule 6)
```

## 6. OOD (Out-of-Domain) Term Lists in Python

```python
# REMOVED — domain_terms collection with category='ood_marker'
_OOD_TERMS = frozenset({
    "recipe", "weather", "sports", "movie", "music", "game",
    "restaurant", "hotel", "flight", "shopping", "fashion",
    "celebrity", "gossip", "horoscope", "lottery",
})
# FIX: Query domain_terms WHERE category == 'ood_marker' RETURN LOWER(term)
```

## 7. Known Non-Control ID Lists in Python

```python
# REMOVED — domain_terms collection with category='known_acronym'
_KNOWN_NON_CONTROL_IDS = frozenset({
    "FADEC", "C4ISR", "SCADA", "FPGA", "COTS", "MISRA", "CMMC",
    "DISA", "STIG", "ITAR", "NIST", "ARP4761", "DO-178C", "F-36",
})
# FIX: Query domain_terms WHERE category IN ['known_acronym', 'standard_id', 'platform_id']
```

## Why These Matter

Every hardcoded list:
1. **Goes stale** — new terms added to DB are invisible to Python code
2. **Fragments truth** — two sources of authority for the same data
3. **Blocks extensibility** — adding a new framework requires code change + deploy, not just a DB insert
4. **Breaks tests** — hardcoded lists become test fixtures that diverge from production data
