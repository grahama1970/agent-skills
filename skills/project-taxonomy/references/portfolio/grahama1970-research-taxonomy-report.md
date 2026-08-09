# Research Portfolio Taxonomy for `grahama1970`

**Generated:** 2026-08-07  
**Repository activity window:** 2026-07-07 through 2026-08-07  
**Agent Skills inventory snapshot:** commit `5cc00692d`, as of 2026-08-06  
**Scope:** 14 repositories active in the window and 338 current skill directories.

## Executive recommendation

Use **Evidence-Bearing AI Systems** as the portfolio umbrella:

> **Build AI systems whose claims, actions, memories, and generated artifacts carry inspectable lineage—and whose authority remains bounded.**

Adopt a **multi-axis taxonomy** rather than one flat tag list:

1. **Program family** — broad portfolio roll-up.
2. **Primary research area** — exactly one stable answer to “what research question does this system principally advance?”
3. **Secondary research area** — zero or one meaningful cross-area contribution.
4. **Methods** — reusable techniques such as provenance, zero-trust, formal verification, graph retrieval, or blinded evaluation.
5. **System role** — control plane, parser engine, memory substrate, speech renderer, workbench, and so on.
6. **Domain** — documents, space cyber, voice, software engineering, creative media.
7. **Portfolio class** — research-owning, adapted platform, support fixture, public projection, or collateral.
8. **Lifecycle/evidence posture** — status and what has actually been proved.

This prevents “graph,” “review,” “agent,” “voice,” or “security” from becoming overloaded labels that mean area, method, role, and domain simultaneously.

## Why the current map should change

The current site map is directionally strong, but its five areas are too coarse for the current portfolio. It combines orchestration with model infrastructure, memory with voice/persona, and extraction with research synthesis. Its skill counts are produced by substring matching, so generic words such as `agent`, `review`, `eval`, or `voice` can inflate unrelated areas.

Keep the existing action-oriented skill categories—`create`, `ingest`, `extract`, `review`, `monitor`, `ops`, and similar—as **operational categories**. They answer “what action does this skill perform?” The new research taxonomy answers “what durable research question does it advance?” Both are useful; neither should replace the other.

## Program families

| Program family | Portfolio thesis | Research areas |
| --- | --- | --- |
| Autonomous Systems Foundations | Control planes, memory, and model infrastructure for bounded, inspectable agent work. | Agent Systems & Orchestration, Memory & Knowledge Systems, Model Infrastructure & Learning |
| Evidence & Assurance Systems | Acquisition, analysis, attack/defense, governance, and proof systems that preserve source and authority boundaries. | Extraction & Document Intelligence, Research Intelligence & Evidence Synthesis, Security, Hacking & Adaptive Defense, Compliance, Governance & Assurance, Verification, Evaluation & Formal Methods |
| Human-Centered & Generative AI | Voice, persona, multimodal interaction, and creative generation with measurable lineage and human review. | Multimodal, Voice & Persona Systems, Generative Media & Creative Systems |

## Canonical research areas

| Label slug | Display name | Family | Core research question | Skill census | Current exemplars |
| --- | --- | --- | --- | --- | --- |
| `agent-systems` | Agent Systems & Orchestration | Autonomous Systems Foundations | How can untrusted agents and tools be coordinated without losing the human goal, execution state, stop conditions, or replayability? | 45 (34 capability / 11 support) | tau, agent-skills, surf, ask |
| `memory` | Memory & Knowledge Systems | Autonomous Systems Foundations | How can agents recall durable, scoped, provenance-linked knowledge without mistaking retrieval relevance for truth or authority? | 23 (17 capability / 6 support) | graph-memory-operator, memory, episodic-archiver |
| `extraction` | Extraction & Document Intelligence | Evidence & Assurance Systems | How can heterogeneous files and unstable sources become structurally faithful, hash-bound artifacts with truthful terminal outcomes? | 28 (27 capability / 1 support) | fetcher, pdf_oxide, extractor |
| `research-intelligence` | Research Intelligence & Evidence Synthesis | Evidence & Assurance Systems | How can multi-source discovery and synthesis expose citations, coverage, uncertainty, and failed or degraded sources? | 24 (20 capability / 4 support) | dogpile, brave-search, arxiv, github-search |
| `security-hacking` | Security, Hacking & Adaptive Defense | Evidence & Assurance Systems | How can authorized attacks and defenses co-evolve in isolation and be selected by deterministic runtime evidence? | 10 (6 capability / 4 support) | battle, hack, thunderdome, anvil |
| `compliance-assurance` | Compliance, Governance & Assurance | Evidence & Assurance Systems | How can controls, requirements, mappings, evidence, and review state remain distinct until an authorized human signs off? | 22 (19 capability / 3 support) | sparta, sparta-public, create-evidence-case, cmmc-assessor |
| `verification` | Verification, Evaluation & Formal Methods | Evidence & Assurance Systems | How can claims, code, prompts, models, and workflows be tested against executable, reproducible, adversarial, negative, or formal gates? | 42 (39 capability / 3 support) | agentic-evals, lean4-prove, debugger, quality-audit |
| `model-systems` | Model Infrastructure & Learning | Autonomous Systems Foundations | How can heterogeneous models and providers be routed, retried, benchmarked, trained, and exposed through stable typed interfaces? | 18 (10 capability / 8 support) | scillm, prompt-lab, benchmark-models |
| `voice-persona` | Multimodal, Voice & Persona Systems | Human-Centered & Generative AI | How can speech, video, affect, persona continuity, and real-time interaction be measurable, interruptible, and provenance-linked? | 29 (23 capability / 6 support) | RealtimeSTT, chatterbox, persona-dream, watch |
| `creative-media` | Generative Media & Creative Systems | Human-Centered & Generative AI | How can image, video, music, story, and design generation become reproducible, reviewable creative workflows rather than one-off prompts? | 64 (58 capability / 6 support) | create-image, create-movie, create-music, pitchdeck |

### Area boundaries

#### `agent-systems` — Agent Systems & Orchestration

**Includes:** DAG and loop runtimes, bounded subagents, browser transport, handoffs, scheduling, goal preservation, human approval gates.  
**Boundary to preserve:** Owns coordination and admissibility—not model-provider semantics or domain decision authority.

#### `memory` — Memory & Knowledge Systems

**Includes:** graph memory, vector and lexical retrieval, intent routing, episodic memory, project state, knowledge lifecycle.  
**Boundary to preserve:** Owns retrieval, routing, and memory state; relevance does not itself establish claim support.

#### `extraction` — Extraction & Document Intelligence

**Includes:** source acquisition, PDF parsing, OCR, layout and table analysis, document normalization, route selection.  
**Boundary to preserve:** Owns acquisition and structural extraction—not the final semantic conclusion or approval.

#### `research-intelligence` — Research Intelligence & Evidence Synthesis

**Includes:** web, code, paper, feed, and video discovery, source comparison, grounded synthesis, coverage reporting.  
**Boundary to preserve:** Research output is evidence and design input—not runtime proof, compliance credit, or execution success.

#### `security-hacking` — Security, Hacking & Adaptive Defense

**Includes:** authorized hacking, red/blue competition, adaptive lineage, exploit and patch replay, sandboxed targets.  
**Boundary to preserve:** Only authorized, isolated targets; runtime/Judge evidence outranks LLM plausibility.

#### `compliance-assurance` — Compliance, Governance & Assurance

**Includes:** compliance frameworks, evidence and assurance cases, OSCAL, policy gates, control mappings, human review.  
**Boundary to preserve:** Models may navigate and explain; people and governed authorities decide.

#### `verification` — Verification, Evaluation & Formal Methods

**Includes:** agentic evals, formal proof, debugging, benchmarks, regression, readiness scoring, negative controls.  
**Boundary to preserve:** A proof establishes only its declared gate and conditions; it must carry explicit non-claims.

#### `model-systems` — Model Infrastructure & Learning

**Includes:** model gateways, provider routing, inference, training, prompt systems, capability and readiness probes.  
**Boundary to preserve:** Owns model capability and transport—not workflow admissibility, factual authority, or human-facing final claims.

#### `voice-persona` — Multimodal, Voice & Persona Systems

**Includes:** speech ingress and egress, wake/listen loops, video memory, persona continuity, affect and delivery, interaction UX.  
**Boundary to preserve:** Sensors and renderers do not own answer meaning, durable identity, memory promotion, or authority.

#### `creative-media` — Generative Media & Creative Systems

**Includes:** image and movie generation, music and sound, story and storyboard, design systems, creative review and iteration.  
**Boundary to preserve:** Generated media is a creative artifact, not evidence of an external factual claim; provenance and human review remain explicit.

## Recent repository classification

The recommended portfolio accounting yields:

- **10 research-owning lines**, including adapted upstream components counted only for their local research delta.
- **1 adapted platform** (`pi-mono`) used as substrate rather than counted as an original research line.
- **1 evaluation fixture** (`watchdog-probe`).
- **1 public projection** (`sparta-public`).
- **1 portfolio/career workflow** (`resume`).

| Repository | Primary | Secondary | Portfolio class | Counting rule | Boundary to preserve |
| --- | --- | --- | --- | --- | --- |
| `grahama1970/agent-skills` | agent-systems | verification | research-platform | count | Defines reusable capability and worker contracts; individual skills do not become separate portfolio projects unless they have an independent research question and proof surface. |
| `grahama1970/extractor` | extraction | verification | research-system | count | Extractor owns route selection, recovery, validation, and the truthful result envelope; PDF accuracy belongs to pdf_oxide and model-mediated enrichment belongs behind Tau. |
| `grahama1970/pdf_oxide` | extraction | verification | adapted-research-component | count-local-delta-only | Owns deterministic PDF extraction and structural fidelity; it does not own application routing, model policy, or downstream claim authority. |
| `grahama1970/fetcher` | extraction | research-intelligence | research-component | count | Acquires and fingerprints unstable source material; retrieval success or change detection does not prove a downstream semantic claim. |
| `grahama1970/sparta` | compliance-assurance | memory | application-workbench | count | The model helps navigate; governed evidence and authorized people decide. Relevance is not support, and candidate visibility is not compliance credit. |
| `grahama1970/graph-memory-operator` | memory | compliance-assurance | research-infrastructure | count | Owns memory state, source policy, recall, and route products; retrieval relevance does not confer claim support or approval authority. |
| `grahama1970/watchdog-probe` | verification | — | evaluation-fixture | exclude-evaluation-fixture | Exists to test another system's lifecycle and closure behavior; it is not an independent research program. |
| `grahama1970/pi-mono` | agent-systems | voice-persona | adapted-platform | exclude-adapted-platform | Treat the upstream platform as implementation substrate; portfolio novelty claims attach only to the local delta and its evidence. |
| `grahama1970/resume` | — | — | portfolio-collateral | exclude-portfolio-collateral | Communicates and packages evidence about the research portfolio; it is not itself a research area. |
| `grahama1970/sparta-public` | compliance-assurance | — | public-projection | exclude-public-projection | Inherits Sparta's research area but contains the public projection rather than an independent implementation or research line. |
| `grahama1970/scillm` | model-systems | agent-systems | research-infrastructure | count | Owns model/provider capability and transport; Tau owns delegated workflow control and admissibility, while planners and humans own final claims. |
| `grahama1970/RealtimeSTT` | voice-persona | verification | adapted-research-component | count-local-delta-only | Transcribes and emits ingress evidence; it does not own meaning, memory, final answers, persona identity, or rendered voice. |
| `grahama1970/chatterbox` | voice-persona | verification | adapted-research-component | count-local-delta-only | Chatterbox is the renderer; memory, QRA trust, reasoning, and emotional-steering decisions belong to the coordinator and memory pipeline. |
| `grahama1970/tau` | agent-systems | verification | research-system | count | Agents propose; Tau decides what is admissible; humans retain the goal and all high-risk approval authority. |

## Skill census

The 338-skill bootstrap classification produces:

- **305 skills with a subject research area**.
- **33 pure support/operations skills** with no research-area assignment.
- **253 research capabilities**.
- **85 support enablers**; 52 inherit a subject area and 33 are pure support.
- **315 high-confidence assignments**.
- **23 medium-confidence assignments** retained in a human-review queue.
- **287 skills with a sanity check** in the source inventory.

| Research area | All assigned | Research capabilities | Support enablers | Sanity checks | Medium-confidence |
| --- | --- | --- | --- | --- | --- |
| Agent Systems & Orchestration | 45 | 34 | 11 | 38 | 1 |
| Memory & Knowledge Systems | 23 | 17 | 6 | 22 | 1 |
| Extraction & Document Intelligence | 28 | 27 | 1 | 26 | 6 |
| Research Intelligence & Evidence Synthesis | 24 | 20 | 4 | 22 | 1 |
| Security, Hacking & Adaptive Defense | 10 | 6 | 4 | 8 | 1 |
| Compliance, Governance & Assurance | 22 | 19 | 3 | 16 | 1 |
| Verification, Evaluation & Formal Methods | 42 | 39 | 3 | 39 | 5 |
| Model Infrastructure & Learning | 18 | 10 | 8 | 16 | 2 |
| Multimodal, Voice & Persona Systems | 29 | 23 | 6 | 23 | 1 |
| Generative Media & Creative Systems | 64 | 58 | 6 | 51 | 4 |
| Pure Supporting Infrastructure & Operations | 33 | 0 | 33 | 26 | 0 |

The CSV is a **bootstrap classification**, not an assertion that every name-derived assignment is semantically final. The medium-confidence queue exists specifically to prevent false precision.

## Label grammar

Use controlled prefixes:

```text
family: autonomous-systems
area: extraction
method: provenance
portfolio: research-owning
status: active
evidence: live-proof
```

Recommended issue/PR discipline:

- Require exactly one `area:*` label on research work.
- Use `method:*` only when the method is materially part of the work.
- Apply `evidence:*` only when a retained receipt supports it.
- Use `portfolio:*` mainly for repository governance and portfolio accounting.
- Put persistent role/domain/origin metadata in the YAML registry or repository topics rather than multiplying issue labels.

Recommended repository topics use a compact form:

```text
ra-agent-systems
ra-memory
ra-extraction
ra-research-intelligence
ra-security-hacking
ra-compliance-assurance
ra-verification
ra-model-systems
ra-voice-persona
ra-creative-media
```

## Portfolio-counting rules

1. A research-owning system has an independent research question, a boundary to preserve, and a proof surface.
2. Public projections, documentation mirrors, test fixtures, and career material inherit context but do not count as separate research lines.
3. Upstream forks and adapted platforms count only the local research delta; upstream baseline capability is credited separately.
4. A shared platform such as `agent-skills` counts once. Its 338 skills are capabilities, not 338 independent projects.
5. A method is never a research area by itself. `provenance`, `zero-trust`, `graph`, `multimodal`, and `formal-verification` are method labels.
6. A domain is never authority. `space-cyber`, `voice`, `documents`, or `aerospace` indicate application context.
7. Retrieval, extraction, research, and rendering do not create factual or approval authority.
8. Every repository classification must include a one-sentence **boundary to preserve**.
9. Taxonomy changes are versioned and reviewed quarterly or whenever the repository’s core research question changes.
10. Website counts must be generated from explicit registry metadata—not substring matching.

## Migration from the current five-area map

| Current area | Recommended destination | Why |
| --- | --- | --- |
| Agentic pipelines | Agent Systems + Model Systems + Verification | Separates orchestration, provider infrastructure, and proof. |
| Agentic memory | Memory + Voice/Persona | Separates durable knowledge from multimodal persona behavior. |
| Extraction & evidence | Extraction + Research Intelligence | Separates source/structure processing from discovery and synthesis. |
| Compliance & governance | Compliance & Assurance | Retain, with a clearer human-authority boundary. |
| Adaptive lineage hacking | Security, Hacking & Adaptive Defense | Retain adaptive lineage while making authorization and isolation explicit. |
| No current equivalent | Creative Media | Recognizes the largest skill cluster without confusing creation with evidence. |

## Implementation sequence

### 1. Commit one authoritative registry

Place `research-taxonomy.yaml` in a central portfolio location, preferably:

```text
agent-skills/portfolio/research-taxonomy.yaml
```

The registry should be the only authority for portfolio counts, project-area membership, and boundaries.

### 2. Add a small per-repository pointer

Each repository can optionally carry:

```text
.research/classification.yaml
```

containing only its registry ID, primary area, methods, role, and boundary. A CI check should compare it with the central registry.

### 3. Replace keyword counts

Refactor `site/scripts/gen_research_map.py` to read explicit project and skill classification data. Keyword inference can remain a lint suggestion for new skills, but never the rendered authority.

### 4. Validate in CI

Run:

```bash
python validate-research-taxonomy.py research-taxonomy.json
```

Then validate each project record against `research-project-classification.schema.json`.

### 5. Apply GitHub labels and topics

Use `github-labels.csv` to create the controlled label vocabulary and `repository-topics.csv` to set persistent repository topics. Start with area, portfolio, status, and evidence labels; add method labels selectively.

### 6. Resolve the medium-confidence queue

Review `skill-classification-review-queue.csv`, update the authoritative registry, and eliminate rule-derived ambiguity over time.

## Files in this package

- `research-taxonomy.yaml` / `.json` — authoritative proposed registry.
- `research-project-classification.schema.json` — CI-ready project record schema.
- `validate-research-taxonomy.py` — dependency-free invariant validator.
- `project-classification.csv` — all 14 recent repositories.
- `repository-topics.csv` — suggested GitHub topics.
- `github-labels.csv` — controlled GitHub label vocabulary.
- `skill-classification.csv` / `.json` — all 338 skills.
- `skill-classification-review-queue.csv` — 23 medium-confidence assignments.
- `skill-area-summary.csv` — area counts.
- `skill-area-by-operation-matrix.csv` — research area × existing operational prefix.
- `SOURCE_NOTES.md` — source snapshot and interpretation notes.

## Bottom line

The strongest portfolio structure is not a longer flat list of nouns. It is a governed classification system:

```text
Evidence-Bearing AI Systems
  -> 3 program families
     -> 10 primary research areas
        -> methods, roles, domains, maturity, evidence, and boundaries
```

That structure makes the portfolio legible without flattening the distinctions that are central to the work: extraction is not research synthesis; retrieval is not proof; rendering is not reasoning; model transport is not orchestration; and AI assistance is not human authority.
