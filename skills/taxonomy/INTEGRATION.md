# Taxonomy Integration Guide

How to integrate Federated Taxonomy into skills for multi-hop graph traversal.

## Why Integrate Taxonomy?

The Federated Taxonomy enables **cross-collection multihop traversal** in the knowledge graph. By tagging all content with Bridge Attributes, documents in different collections can be linked semantically:

```
[Lore Document]                    [Code Lesson]
bridge_tags: ["Resilience"]   →   bridge_tags: ["Resilience"]
"Siege of Terra"                  "Error handling patterns"
        ↘                       ↙
          [Query: "Endurance patterns"]
                    ↓
         Both docs retrieved via
         shared "Resilience" bridge
```

## Quick Integration

### 1. Import the Taxonomy Module

```python
import sys
from pathlib import Path

# Add taxonomy skill to path
sys.path.insert(0, str(Path(__file__).parent.parent / "taxonomy"))

try:
    from taxonomy import extract_taxonomy
except ImportError:
    # Fallback - minimal keyword extraction
    def extract_taxonomy(text: str, collection: str = "operational", fast: bool = True):
        return {"bridge_tags": [], "collection_tags": {}, "confidence": 0.0, "worth_remembering": False}
```

### 2. Extract Taxonomy from Content

```python
# After generating/processing content
content = your_skill_output()

# Extract taxonomy (use fast=True for keyword-only, fast=False for LLM)
taxonomy = extract_taxonomy(
    text=content,
    collection="lore",  # or "operational" or "sparta"
    fast=True
)

# Include in output
result = {
    "content": content,
    "taxonomy": taxonomy,  # Enables multi-hop retrieval
    "timestamp": datetime.now().isoformat()
}
```

### 3. Choose the Right Collection

| Collection | Use For | Example Skills |
|------------|---------|----------------|
| `lore` | Horus persona content, stories, narratives | create-story, review-story, ingest-movie |
| `operational` | Code, technical documentation, lessons | review-code, memory (lessons) |
| `sparta` | Security content, vulnerabilities, threats | security-scan, hack, ops-compliance |

## Output Format

All taxonomy-enabled skills should output:

```json
{
  "content": "...",
  "other_fields": "...",

  "taxonomy": {
    "bridge_tags": ["Resilience", "Loyalty"],
    "collection_tags": {
      "function": "Preservation",
      "domain": "Legion"
    },
    "confidence": 0.75,
    "worth_remembering": true
  }
}
```

## Bridge Attributes Reference

| Bridge | When To Tag |
|--------|-------------|
| **Precision** | Optimization, efficiency, calculated approaches, algorithmic solutions |
| **Resilience** | Error handling, fault tolerance, endurance, recovery patterns |
| **Fragility** | Technical debt, vulnerabilities, brittle code, weaknesses |
| **Corruption** | Silent failures, state bugs, compromise, data integrity issues |
| **Loyalty** | Security, authentication, trust, compliance, access control |
| **Stealth** | Hidden behavior, evasion, undetected issues, logging gaps |

## Skills That Should Integrate Taxonomy

### Content Creation Skills
- `create-story` - Tag generated stories
- `create-movie` - Tag movie scripts and metadata
- `create-figure` - Tag visualization context

### Ingestion Skills
- `ingest-movie` - Tag extracted emotional cues
- `ingest-youtube` - Tag transcript content
- `ingest-book` - Tag book metadata
- `ingest-audiobook` - Tag transcription content

### Review Skills
- `review-story` - Tag critiques (DONE)
- `review-code` - Tag code review findings
- `review-paper` - Tag paper analysis

### Research Skills
- `dogpile` - Tag research findings
- `arxiv` - Tag paper metadata
- `perplexity` - Tag AI-synthesized answers

### Memory/Storage Skills
- `memory` - Store with taxonomy for retrieval
- `episodic-archiver` - Archive with taxonomy

## Synthesis Pattern

When aggregating multiple outputs (e.g., multi-provider reviews), combine taxonomy:

```python
def synthesize_taxonomy(items: list[dict]) -> dict:
    """Combine taxonomy from multiple sources."""
    all_bridge_tags = set()
    all_collection_tags = {}

    for item in items:
        taxonomy = item.get("taxonomy", {})
        for tag in taxonomy.get("bridge_tags", []):
            all_bridge_tags.add(tag)
        for dim, val in taxonomy.get("collection_tags", {}).items():
            if dim not in all_collection_tags:
                all_collection_tags[dim] = set()
            all_collection_tags[dim].add(val)

    return {
        "bridge_tags": list(all_bridge_tags),
        "collection_tags": {k: list(v) for k, v in all_collection_tags.items()},
        "confidence": sum(i.get("taxonomy", {}).get("confidence", 0) for i in items) / len(items),
        "worth_remembering": len(all_bridge_tags) > 0
    }
```

## Testing Taxonomy Integration

```bash
# Test your skill's taxonomy output
your_skill_output.json | jq '.taxonomy'

# Should show:
# {
#   "bridge_tags": ["Resilience", ...],
#   "collection_tags": {...},
#   "confidence": 0.75,
#   "worth_remembering": true
# }

# Verify bridge tags are valid
your_skill_output.json | jq '.taxonomy.bridge_tags[]' | \
  xargs -I {} bash -c 'grep -q {} <<< "Precision Resilience Fragility Corruption Loyalty Stealth" && echo "✓ {}" || echo "✗ {} INVALID"'
```

## Validation

Use the taxonomy skill to validate tags:

```bash
.pi/skills/taxonomy/run.sh validate --tags '{"bridge_tags": ["Resilience", "Unknown"]}'
# Returns only valid tags: {"bridge_tags": ["Resilience"], ...}
```

## Performance Notes

- **fast=True**: Uses keyword extraction only, ~1ms per call
- **fast=False**: Uses LLM extraction, ~2-5s per call but more accurate
- Use `fast=True` for bulk processing, `fast=False` for important documents
- Set `TAXONOMY_FAST_MODE=1` environment variable to force keyword-only globally
