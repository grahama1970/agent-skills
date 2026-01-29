---
name: taxonomy
description: >
  Extract Federated Taxonomy tags from text for multi-hop graph traversal.
  Provides Bridge Attributes (Precision, Resilience, Fragility, Corruption, Loyalty, Stealth)
  and collection-specific tags (lore, operational, sparta) for cross-document relationship discovery.
allowed-tools: [Bash, Read, Write]
triggers:
  - taxonomy
  - extract taxonomy
  - tag content
  - add taxonomy
  - bridge attributes
  - taxonomy tags
metadata:
  short-description: Federated Taxonomy tag extraction for multi-hop graph traversal
  author: "Horus"
  version: "0.1.0"
---

# taxonomy

Extract Federated Taxonomy tags from text for multi-hop graph traversal between collections (Lore, Operational, SPARTA).

## Purpose

The Federated Taxonomy enables **cross-collection multihop traversal** in the knowledge graph. By tagging all content with common Bridge Attributes, documents in different collections can be linked semantically.

## Bridge Attributes (Tier 0 - Conceptual Bridges)

| Bridge | Lore Indicators | Operational Indicators | SPARTA Indicators |
|--------|-----------------|------------------------|-------------------|
| **Precision** | Iron Warriors, Perturabo, calculated, methodical | optimized, efficient, precise, algorithmic | reconnaissance, enumeration, Model |
| **Resilience** | Siege of Terra, Imperial Fists, Dorn, endure | error handling, fault tolerance, redundancy | defense, harden, isolate, restore |
| **Fragility** | Webway, Magnus's Folly, brittle, shattered | technical debt, single point of failure, legacy | vulnerability, weakness, CVE, Exploit |
| **Corruption** | Warp, Chaos, Davin, taint, possession | silent failures, state bugs, memory leaks | compromise, persistence, backdoor, Persist |
| **Loyalty** | Oaths of Moment, Loken, Luna Wolves | security compliance, auth protocols, encryption | authentication, authorization, Detect |
| **Stealth** | Alpha Legion, Alpharius, subterfuge, hidden | logging disabled, audit bypass, undetected | evasion, obfuscation, anti-forensics, Evade |

## Collection Vocabularies

### HLT (Horus Lore Taxonomy)

| Dimension | Values |
|-----------|--------|
| **function** | Catalyst, Subversion, Preservation, Revelation, Confrontation |
| **domain** | Legion, Imperium, Chaos, Primarch, World |
| **thematic_weight** | Betrayal, Tragedy, Honor, Despair |
| **perspective** | Frontline, Political, Psychological, Cosmic |

### Operational (Code/Technical)

| Dimension | Values |
|-----------|--------|
| **function** | Fix, Optimization, Refactor, Hardening, Debug |
| **domain** | Middleware, Frontend, Database, Deployment, Infrastructure |
| **thematic_weight** | Critical, Technical_Debt, Security, Performance |
| **perspective** | Architectural, Operational, Strategic, Internal |

### SPARTA (Security)

| Dimension | Values |
|-----------|--------|
| **function** | Attack, Defend, Detect, Mitigate, Exploit |
| **domain** | Network, Endpoint, Identity, Cloud, Application |
| **thematic_weight** | Critical, High, Medium, Low |
| **perspective** | Offensive, Defensive, Compliance, Risk |

## Quick Start

```bash
cd .pi/skills/taxonomy

# Extract from text (fast keyword mode)
./run.sh extract --text "Error handling code with fault tolerance" --fast

# Extract from file with LLM
./run.sh extract --file document.txt --collection operational

# Get bridge tags only
./run.sh extract --text "The Siege of Terra" --bridges-only --collection lore

# Validate existing tags
./run.sh validate --tags '{"bridge_tags": ["Resilience", "Unknown"]}'
```

## Commands

### `extract` - Extract Taxonomy Tags

```bash
./run.sh extract [OPTIONS]

Options:
  --text, -t TEXT      Text to analyze
  --file, -f PATH      File to read
  --collection, -c     Collection type (lore, operational, sparta)
  --bridges-only, -b   Only output bridge tags
  --fast               Use keyword extraction only (no LLM)
```

### `validate` - Validate Tags Against Vocabulary

```bash
./run.sh validate [OPTIONS]

Options:
  --tags TEXT          JSON string with tags to validate
  --file, -f PATH      JSON file with tags
```

## Output Format

```json
{
  "bridge_tags": ["Resilience", "Precision"],
  "collection_tags": {
    "function": "Hardening",
    "domain": "Infrastructure",
    "thematic_weight": "Security"
  },
  "confidence": 0.85,
  "worth_remembering": true
}
```

## Integration Pattern

All content-producing skills should include taxonomy metadata in their output:

```python
from taxonomy import extract_taxonomy

# After generating content
content = generate_story(...)

# Extract taxonomy for graph integration
taxonomy = extract_taxonomy(content, collection="lore")

# Include in output
result = {
    "content": content,
    "taxonomy": taxonomy,  # Enables multi-hop traversal
    "timestamp": datetime.now().isoformat()
}
```

## Multi-Hop Traversal Example

```
[Lore Document]                    [Lesson]
bridge_tags: ["Resilience"]   →   bridge_tags: ["Resilience"]
"Siege of Terra"                  "Error handling patterns"
        ↘                       ↙
          [Query: "Endurance patterns"]
                    ↓
         Both docs retrieved via
         shared "Resilience" bridge
```

## Environment

| Variable | Purpose |
|----------|---------|
| `TAXONOMY_LLM_ENDPOINT` | Custom LLM endpoint for extraction |
| `TAXONOMY_FAST_MODE` | Default to keyword extraction (no LLM) |

## Related Skills

| Skill | Relationship |
|-------|--------------|
| `/memory` | Stores content with taxonomy for retrieval |
| `/review-story` | Tags story critiques with taxonomy |
| `/create-story` | Tags generated content with taxonomy |
| `/ingest-*` | Tags ingested content with taxonomy |
| `/edge-verifier` | Uses taxonomy for edge verification |

## Implementation Notes

- **LLM extraction** produces candidates that are **validated against known vocabulary**
- Prevents hallucinated tags by filtering to allowed values
- **Keyword fallback** provides fast extraction without LLM
- Bridge Attributes are the PRIMARY connector for cross-collection queries
- Collection tags provide SECONDARY filtering within collections
