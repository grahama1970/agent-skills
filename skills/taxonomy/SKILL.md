---
name: taxonomy
description: >
  Extract Federated Taxonomy tags from text for multi-hop graph traversal.
  Mind tags (8 tactical: Detect/Evade/Exploit/Harden/Isolate/Model/Persist/Restore),
  Heart tags (5 emotional: anger/fear/joy/sadness/trust),
  Intent tags (8 interaction: Navigate/Expand/Filter/Analyze/Compare/Trace/Layout/Persist),
  and collection-specific tags.
  Multi-hop traversal uses grounded MITRE taxonomy (CWE pillars, CAPEC, ATT&CK)
  instead of LLM-generated bridge attributes (removed 2026-03-21).
allowed-tools: [Bash, Read, Write]
triggers:
  - taxonomy
  - extract taxonomy
  - tag content
  - add taxonomy
  - taxonomy tags
  - mind tags
  - heart tags
  - intent tags
metadata:
  short-description: Federated Taxonomy tag extraction for multi-hop graph traversal
  author: "Horus"
  version: "0.3.0"
provides:
  - taxonomy-tagging
composes:
  - memory
  - scillm
  - task-monitor

taxonomy:
  - classification
  - bridging
  - precision
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# taxonomy

Extract Federated Taxonomy tags from text for multi-hop graph traversal between collections.

## Three-Axis Classification (v0.3.0)

| Axis | Output key | Tags | Lives on | Purpose |
|------|-----------|------|----------|---------|
| **Mind** | `mind` | Detect, Evade, Exploit, Harden, Isolate, Model, Persist, Restore | `sparta_qra` | SPARTA tactical scope |
| **Heart** | `heart` | anger, fear, joy, sadness, trust | `lessons` | Emotional scope |
| **Intent** | `intent` | Navigate, Expand, Filter, Analyze, Compare, Trace, Layout, Persist | `lessons` (tagged `intent-training-v2`) | App interaction scope |

Mind and Heart are **orthogonal** — every call emits both keys. The text content determines which tags apply, not the scope.

Intent is a **separate dimension** for UI interaction documents. It enables graph traversal between commands phrased differently (e.g., "zoom in" ↔ "focus on" via shared Navigate tag). Intent tags ONLY go on docs tagged `intent-training-v2`.

### Bridge Attributes — REMOVED

Bridge Attributes (Precision, Resilience, etc.) were **removed** (2026-03-21) — they were ungrounded LLM opinions. Multi-hop traversal now uses:
- **SPARTA scope**: CWE pillar hierarchy, CIA consequences, CAPEC→ATT&CK→SPARTA edges
- **Non-SPARTA scope**: Mind/Heart/Intent tag overlap, collection tags, BM25+cosine via `/recall`
- `bridge_tags` key kept as empty list for backward compatibility

## Prompt Iteration Rule (NON-NEGOTIABLE)

LLM-mode taxonomy extraction prompts MUST be validated through `/prompt-lab` before deployment. NEVER hand-craft taxonomy system prompts in Python strings.

## Output Format

```json
{
  "bridge_tags": [],
  "mind": ["Detect", "Harden"],
  "heart": ["trust"],
  "intent": [],
  "collection_tags": {"function": "Defend", "domain": "Endpoint"},
  "confidence": 0.87,
  "worth_remembering": true
}
```

## Intent Tags (v0.3.0)

8 tags for classifying UI interaction commands:

| Tag | Interactions | Examples |
|-----|-------------|----------|
| **Navigate** | zoom, pan, reset, focus, select, click | "zoom in on auth", "show all nodes" |
| **Expand** | expand neighbors, show connections, N-hop | "expand 2 hops from droid" |
| **Filter** | set perspective, show only, hide, dismiss | "switch to security view" |
| **Analyze** | explain, what is, describe, tell me about | "what does exec_command do?" |
| **Compare** | compare X and Y, relationship between | "what connects these two?" |
| **Trace** | trace execution path, follow data flow | "trace auth call chain" |
| **Layout** | switch layout, toggle progressive | "switch to clustered layout" |
| **Persist** | bookmark, save, remember, learn back | "bookmark this to memory" |

Intent tags create `similar_to` edges in `lesson_edges`, enabling `/recall` to find semantically equivalent commands through graph traversal even with zero word overlap.

## Collection Vocabularies

### SPARTA (Security)

| Dimension | Values |
|-----------|--------|
| **function** | Attack, Defend, Detect, Mitigate, Exploit |
| **domain** | Network, Endpoint, Identity, Cloud, Application |
| **thematic_weight** | Critical, High, Medium, Low |
| **perspective** | Offensive, Defensive, Compliance, Risk |

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

### Behavioral (Psychology/Neuroscience)

| Dimension | Values |
|-----------|--------|
| **function** | Mechanism, Adaptation, Regulation, Development, Pathology |
| **domain** | Neuroscience, Endocrine, Evolution, Social, Clinical |
| **thematic_weight** | Aggression, Stress, Cooperation, Cognition, Emotion |
| **perspective** | Biological, Evolutionary, Cultural, Individual, Population |
| **emotional_intensity** | Low, Moderate, High, Extreme |

### Cinematography (Visual/Creative)

| Dimension | Values |
|-----------|--------|
| **genre_affinity** | Horror, Thriller, Drama, Comedy, Action, SciFi, Period, Documentary, Noir, Western, War, Romance, Fantasy |
| **emotional_palette** | Dread, Intimacy, Grandeur, Melancholy, Joy, Tension, Wonder, Unease, Isolation, Warmth, Clinical, Romantic |
| **visual_temperature** | Cold, Warm, Neutral, Expressionistic, Naturalistic, Desaturated, Saturated, Monochromatic |

## Commands

### `extract` - Extract Taxonomy Tags

```bash
./run.sh extract [OPTIONS]

Options:
  --text, -t TEXT      Text to analyze
  --file, -f PATH      File to read
  --collection, -c     Collection type (lore, operational, sparta, behavioral)
  --fast               Use keyword extraction only (no LLM)
```

### `validate` - Validate Tags Against Vocabulary

```bash
./run.sh validate --tags '{"mind": ["Detect"], "heart": ["trust"]}'
```

### `sweep` - Batch-classify untagged lessons

```bash
./run.sh sweep [OPTIONS]

Options:
  --collection TEXT     ArangoDB collection (default: lessons)
  --mode               keyword|llm|classifier (default: keyword)
  --scope TEXT          Optional scope filter
  --limit INT          Max documents per run (default: 500)
  --dry-run            Preview only, don't update
```

## Environment

| Variable | Purpose |
|----------|---------|
| `TAXONOMY_LLM_ENDPOINT` | Custom LLM endpoint for extraction |
| `TAXONOMY_FAST_MODE` | Default to keyword extraction (no LLM) |
| `EMBEDDING_SERVICE_URL` | Embedding service URL for classifier mode |

## Common Mistakes

```bash
# WRONG: Confuse heart vs mind vs intent fields
# mind = 8 SPARTA tactical tags (on sparta_qra docs)
# heart = 5 emotional tags (on lessons docs)
# intent = 8 interaction tags (on lessons with intent-training-v2)
# Putting heart tags on sparta_qra breaks graph queries

# WRONG: Put intent tags on non-interaction docs
# Intent tags ONLY go on docs tagged intent-training-v2

# WRONG: Use LLM extraction without /prompt-lab validation
./run.sh extract --file document.txt --collection sparta
# RIGHT: Use --fast unless prompt validated via /prompt-lab
./run.sh extract --file document.txt --collection sparta --fast
```

## Related Skills

| Skill | Relationship |
|-------|--------------|
| `/memory` | Stores content with taxonomy for retrieval |
| `/monitor-taxonomy` | Validates tag quality via 3-tier cascade |
| `/edge-verifier` | Uses taxonomy for edge verification |
| `/assistant` | Routes validation through taxonomy taggers |
| `/ingest-*` | Tags ingested content with taxonomy |
