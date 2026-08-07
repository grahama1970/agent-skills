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
disciplines:
  - memory-knowledge
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# taxonomy

Extract Federated Taxonomy tags from text for multi-hop graph traversal between collections.

## Four-Axis Classification (v0.4.0)

| Axis | Output key | Tags | Lives on | Purpose |
|------|-----------|------|----------|---------|
| **Mind** | `mind` | Detect, Evade, Exploit, Harden, Isolate, Model, Persist, Restore | `sparta_qra`, `skill_chains` | SPARTA tactical scope |
| **Heart** | `heart` | anger, fear, joy, sadness, trust | `lessons` (persona/lore) | Emotional scope |
| **Code** | `code` | extraction, research, security, training, creation, monitoring, review, memory_op, voice, media | `skill_chains` | Coding workflow type |
| **Intent** | `intent` | Navigate, Expand, Filter, Analyze, Compare, Trace, Layout, Persist | `app_actions` | App interaction scope |

### Axis Routing — NOT all axes apply to all collections

Each collection gets ONLY the axes that make sense for it. Putting heart tags
on compliance data is noise. Putting code tags on persona journals is noise.

| Collection | mind | heart | code | intent |
|------------|------|-------|------|--------|
| `sparta_qra` | ✅ | ❌ | ❌ | ❌ |
| `skill_chains` | ✅ | ❌ | ✅ | ❌ |
| `lessons` (persona/lore) | ❌ | ✅ | ❌ | ❌ |
| `lessons` (operational) | ✅ | ❌ | ✅ | ❌ |
| `app_actions` | ❌ | ❌ | ❌ | ✅ |
| `checkpoints` | ❌ | ❌ | ✅ | ❌ |
| `horus_lore` | ❌ | ✅ | ❌ | ❌ |

The collection determines which axes `/taxonomy` applies. **Do not tag everything
with everything.**

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
  "code": ["extraction", "review"],
  "intent": [],
  "collection_tags": {"function": "Defend", "domain": "Endpoint"},
  "confidence": 0.87,
  "worth_remembering": true
}
```

## Code Tags (v0.4.0)

10 tags for classifying coding workflow type. Used on `skill_chains` and operational `lessons`.
Enables graph traversal between skill chains that do similar work.

| Tag | Keywords | Examples |
|-----|----------|----------|
| **extraction** | extract, parse, ingest, convert, pdf | "extract tables from PDF" |
| **research** | search, find, discover, arxiv, paper, dogpile | "research SPARTA framework" |
| **security** | hack, scan, vulnerability, pentest, audit | "run security scan" |
| **training** | train, fine-tune, qlora, lora, classifier | "train intent mapper" |
| **creation** | create, generate, build, scaffold, write | "create new skill" |
| **monitoring** | monitor, watch, track, alert, check | "monitor codebase health" |
| **review** | review, assess, evaluate, quality, validate | "review code changes" |
| **memory_op** | learn, recall, remember, store | "store lesson to memory" |
| **voice** | voice, tts, rvc, audio, speech | "train voice model" |
| **media** | video, movie, image, storyboard, youtube | "create storyboard" |

Code tags are **keyword-classified** (no LLM) via word boundary matching against
the task description. The classifier already exists in `skill_chains.classify_task()`.

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
