# Federated Taxonomy

Three-axis classification system for multi-hop graph traversal across ArangoDB collections.

```
          ┌─────────────────────────────────────────┐
          │         Federated Taxonomy               │
          │                                         │
          │   Mind ──── 8 SPARTA tactical tags       │
          │   Heart ─── 5 emotional tags             │
          │   Intent ── 8 UI interaction tags        │
          │                                         │
          │   + collection vocabularies per scope    │
          └─────────────────────────────────────────┘
```

## Why It Exists

Documents in different collections need semantic connections for graph traversal. A security lesson about "GPS spoofing defense" and a QRA about "satellite signal authentication" share tactical context but zero word overlap. Mind tags (`Detect` on both) create edges that `/recall` traverses to find them together.

Same pattern for UI commands: "zoom in on auth" and "focus on auth handler" are the same interaction intent but share no words. Intent tags (`Navigate` on both) create edges for graph traversal.

## The Three Axes

### Mind (tactical)

8 tags from SPARTA framework. Lives on `sparta_qra` documents.

| Tag | Scope |
|-----|-------|
| Detect | Monitoring, scanning, anomaly detection |
| Evade | Stealth, bypass, avoidance |
| Exploit | Attack, compromise, vulnerability exploitation |
| Harden | Protection, patching, compliance |
| Isolate | Segmentation, quarantine, boundary enforcement |
| Model | Assessment, risk analysis, threat modeling |
| Persist | Maintaining access, backup, continuity |
| Restore | Recovery, remediation, incident response |

### Heart (emotional)

5 tags for persona/interpersonal content. Lives on `lessons` documents.

| Tag | Scope |
|-----|-------|
| anger | Frustration, aggression, confrontation |
| fear | Anxiety, threat response, caution |
| joy | Satisfaction, enthusiasm, positive engagement |
| sadness | Loss, disappointment, grief |
| trust | Collaboration, reliability, confidence |

### Intent (interaction)

8 tags for UI command classification. Lives on `lessons` tagged `intent-training-v2`.

| Tag | Scope |
|-----|-------|
| Navigate | Zoom, pan, reset, focus, select, click |
| Expand | Expand neighbors, show connections, N-hop |
| Filter | Set perspective, show only, hide, dismiss |
| Analyze | Explain, what is, describe, tell me about |
| Compare | Compare X and Y, relationship between |
| Trace | Trace path, follow data flow, call chain |
| Layout | Switch layout mode, toggle progressive |
| Persist | Bookmark, save, remember, learn back |

## How It Works

```
Text ──→ /taxonomy extract ──→ { mind: [...], heart: [...], intent: [...] }
                                         │
                                         ▼
                              /taxonomy/batch-tag ──→ ArangoDB
                                         │
                                         ▼
                              similar_to edges in lesson_edges
                                         │
                                         ▼
                              /recall graph traversal finds
                              related docs via shared tags
```

Tags create edges. Edges enable hops. Hops find documents that BM25 alone cannot.

## Quick Start

```bash
cd .pi/skills/taxonomy

# Keyword extraction (fast, no LLM)
./run.sh extract --text "Error handling with fault tolerance" --fast

# With collection context
./run.sh extract --text "GPS spoofing detection" --collection sparta --fast

# Batch tag untagged docs
./run.sh sweep --collection lessons --mode keyword --limit 100
```

## Field Conventions

| Field | Collection | Tags |
|-------|-----------|------|
| `mind` | `sparta_qra` | 8 tactical tags |
| `heart` | `lessons` | 5 emotional tags |
| `intent` | `lessons` (intent-training-v2 only) | 8 interaction tags |

**Do not cross-pollinate.** Mind tags on `lessons` or heart tags on `sparta_qra` breaks graph queries. Intent tags on non-interaction docs creates noise.

## Collection Vocabularies

Beyond the three axes, each scope has domain-specific dimensions:

| Scope | Dimensions |
|-------|-----------|
| **sparta** | function, domain, thematic_weight, perspective, cwe_category |
| **lore** | function, domain, thematic_weight, perspective |
| **operational** | function, domain, thematic_weight, perspective |
| **behavioral** | function, domain, thematic_weight, perspective, emotional_intensity |
| **cinematography** | genre_affinity, emotional_palette, visual_temperature, setting_affinity, lighting_style |

## Multi-Hop Traversal

The taxonomy enables three traversal patterns:

**SPARTA scope** (deterministic, curated):
```
CWE-287 → CAPEC-114 → T1078 → SPARTA control
   (pillar)    (attack)   (technique)   (QRA)
```
All edges are MITRE-curated. No LLM opinions.

**Lessons scope** (tag overlap + similarity):
```
"GPS spoofing defense"     "satellite auth bypass"
     mind: [Detect]    ←→    mind: [Detect, Exploit]
           shared Detect tag = traversable edge
```

**Intent scope** (interaction graph):
```
"zoom in on auth"          "focus on auth handler"
  intent: [Navigate]   ←→   intent: [Navigate]
        shared Navigate tag = similar_to edge
```

## Bridge Attributes — Removed

Bridge Attributes (Precision/Resilience/Fragility/Corruption/Loyalty/Stealth) were removed 2026-03-21. They were ungrounded LLM opinions — the model was inventing semantic connections. The `bridge_tags` key is kept as an empty list for backward compatibility. Do not populate it.

## Composing /taxonomy

```python
import subprocess, json

result = subprocess.run(
    ["./run.sh", "extract", "--text", content, "--fast", "--collection", "sparta"],
    capture_output=True, text=True,
)
taxonomy = json.loads(result.stdout)
# taxonomy = {"mind": ["Detect"], "heart": [], "intent": [], ...}
```

Skills that compose `/taxonomy`: `/monitor-taxonomy`, `/edge-verifier`, `/assistant`, `/ingest-*`, `/review-story`, `/create-story`, `/ask`, `/episodic-archiver`.

## File Structure

```
.pi/skills/taxonomy/
├── SKILL.md                    # Agent instructions
├── README.md                   # This file
├── run.sh                      # Entry point
├── taxonomy.py                 # Core extraction logic
├── taxonomy_sweep.py           # Batch classification
├── train_bridge_text_classifier.py  # Classifier training (legacy)
├── sanity.sh                   # Dependency verification
├── data/                       # Symlink to /mnt/storage12tb
└── docs/                       # Architecture docs
```
