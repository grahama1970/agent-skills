# Pi Skills Directory

223 modular capabilities extending the Pi agent. Each skill has a `SKILL.md` (definition + triggers), `run.sh` (entry point), and `sanity.sh` (health check). *Last updated: 2026-03-07.*

## Quick Reference

```bash
# List all skills
ls .pi/skills/*/SKILL.md | wc -l

# Run a skill directly
.pi/skills/assess/run.sh run ./src/

# Health check a skill
.pi/skills/battle/sanity.sh

# Sync skills across all IDEs
.pi/skills/skills-broadcast/run.sh push
```

## Start Here

Match your intent to a verb prefix:

| I want to... | Start with | Example |
|--------------|------------|---------|
| **Search or research** | `dogpile`, `brave-search`, `perplexity`, `arxiv` | "Research NIST controls" |
| **Ingest content** | `ingest-*` | "Ingest this PDF" → `ingest-doc` |
| **Create something** | `create-*` | "Write a paper" → `create-paper` |
| **Consume/query ingested content** | `consume-*` | "Find that movie scene" → `consume-movie` |
| **Train a model** | `train-*`, `learn-*`, `create-gpt`, `*-lab` | "Train a voice" → `train-voice` |
| **Review or audit** | `review-*`, `*-audit`, `assess` | "Review this code" → `review-code` |
| **Monitor health** | `monitor-*` | "Check memory health" → `monitor-memory` |
| **Manage infrastructure** | `ops-*` | "Check Docker" → `ops-docker` |
| **Find new content** | `discover-*` | "Find movies" → `discover-movies` |
| **Don't know** | `recommend-skill-chain` | Recommends optimal skill chains for any task |

## Skill Anatomy

```
.pi/skills/my-skill/
├── SKILL.md           # Required: definition + YAML frontmatter + triggers
├── run.sh             # Required: bash entry point
├── sanity.sh          # Required: real-world health check (not mocked)
├── pyproject.toml     # If Python: dependencies
└── src/               # Implementation files
```

### SKILL.md Format

```yaml
---
name: my-skill
description: >
  What this skill does. Use when user says "do X" or "perform Y".
allowed-tools: Bash, Read, Glob, Grep
triggers:
  - do X
  - perform Y
  - my-skill
metadata:
  short-description: One-line summary
---

# My Skill

Instructions the agent follows when this skill activates.
```

### Naming Conventions

| Pattern | Meaning | Examples |
|---------|---------|---------|
| **Hyphens** | Skill directories | `create-music`, `ops-workstation` |
| **Underscores** | Python packages (NOT skills) | `consume_common`, `common` |
| **Verb prefixes** | Skill categories | `create-`, `consume-`, `discover-`, `ingest-`, `learn-`, `monitor-`, `ops-`, `review-`, `train-`, `debug-`, `batch-`, `skills-`, `best-practices-` |

## Skill Categories

### Core (9)
| Skill | Description |
|-------|-------------|
| **memory** | Query memory before scanning codebase (MANDATORY first step) |
| **assess** | Step back and reassess project state |
| **ask** | Zero cognitive-load learning and querying |
| **handoff** | Assess state and provide handoff context |
| **dashboard** | Unified development dashboard (daemons, LLMs, shadows, skills, Chutes) |
| **project-state** | Comprehensive project state in one command (6-phase assessment) |
| **embry-config** | Read and explain Embry OS configuration from embry.yaml |
| **bootcamp** | Guided onboarding walkthrough for new users |
| **service-status** | Check health of service daemons via Unix sockets |

### Search & Research (6)
| Skill | Description |
|-------|-------------|
| **brave-search** | Free web/local search via Brave API |
| **perplexity** | Deep research with LLM synthesis (paid) |
| **arxiv** | Academic paper search and ingestion |
| **dogpile** | Multi-source deep research aggregator (Brave + Perplexity + arXiv + GitHub + YouTube + Codex) |
| **context7** | Library documentation lookup |
| **github-search** | Multi-strategy GitHub repository and code search |

### Content Creation (28)
| Skill | Description |
|-------|-------------|
| **create-paper** | Orchestrate academic paper writing |
| **create-story** | Creative writing orchestrator |
| **create-music** | AI-assisted music creation (compose + voice conversion) |
| **create-movie** | Orchestrated movie creation (story → storyboard → score → SFX → render) |
| **create-figure** | Publication-quality figures, charts, and diagrams |
| **create-image** | AI image generation (FLUX.1-schnell, Ollama, Mermaid) |
| **create-score** | Scene-specific music via ACE-Step 1.5 |
| **create-storyboard** | Screenplay to storyboard/animatics conversion |
| **create-persona** | Persona creation for client modeling and expert profiles |
| **create-cast** | Multi-round character casting for movie production |
| **create-sound-design** | SFX selection and placement per scene |
| **create-icon** | Stream Deck and general icon creation |
| **create-stems** | Audio stem separation (Demucs 4-stem or 6-stem) |
| **create-code** | End-to-end coding orchestrator (research + implement + review) |
| **create-context** | Generate CONTEXT.md for agent handoff |
| **create-journal-entry** | Nightly journal entry creation for all personas |
| **create-lut** | Generate cinematic 3D LUTs (.cube) from reference pairs |
| **create-ksml** | Convert project manifests to Kling Shot Markup Language |
| **create-annotated-pdf** | Overlay color-coded bounding boxes on extracted PDFs |
| **create-pdf-fixture** | Create PDF test fixtures (tables + AI images) for extractor testing |
| **create-peer-review** | Automated peer review via Shadow-LEGO cascade |
| **create-react-designs** | Production-grade React/Tailwind/ShadCN with persona feedback |
| **create-walkthrough** | Collaborative argumentative walkthrough for implementations |
| **create-assurance-case** | GSN assurance case diagrams from compliance evidence |
| **create-streamdeck-page** | Dynamic Stream Deck button pages with context-aware layouts |
| **create-table** | PDF tables via ReportLab for extractor testing |
| **sfx-catalog** | Sound effects catalog and management for filmmaking |
| **prototype-react-iterate** | React prototypes with persona-driven iteration and feedback |

### Content Consumption (5)
| Skill | Description |
|-------|-------------|
| **consume-book** | Search and annotate ingested books |
| **consume-movie** | Search and extract clips from ingested movies (SRT subtitle queries) |
| **consume-music** | Search music from ingested YouTube history |
| **consume-youtube** | Search annotated YouTube transcripts |
| **consume-feed** | Nightly upstream feed ingestion (RSS, GitHub releases) |

### Ingestion (10)
| Skill | Description |
|-------|-------------|
| **ingest-doc** | Single-command document pipeline (extractor → CUI → QRA → taxonomy → memory) |
| **ingest-compliance-doc** | Compliance document pipeline (NIST, CMMC, DISA STIG, ITAR) |
| **ingest-movie** | NZBGeek search + subtitle extraction + SRT import |
| **ingest-book** | Readarr library management and book ingestion |
| **ingest-youtube** | YouTube transcript extraction via yt-dlp |
| **ingest-audiobook** | Audiobook transcription pipeline |
| **ingest-code** | Codebase ingestion for CWE scanning and knowledge extraction |
| **ingest-yt-history** | YouTube/YouTube Music watch history from Google Takeout |
| **ingest-kindle** | Kindle books and highlights ingestion |
| **ingest-training-datalake** | Training corpus acquisition and coverage balancer |

### Training & Models (19)
| Skill | Description |
|-------|-------------|
| **train-voice** | Unified voice training orchestrator (RVC via PersonaPlex) |
| **train-persona** | LoRA adapters for persona agents |
| **train-convo-steering** | Voice-first runtime steering + nightly deep analysis |
| **tts-train** | Qwen3-TTS voice model training from audiobook datasets |
| **tts-horus** | Horus TTS pipeline from cleared audiobooks |
| **learn-voice** | RVC voice model training from artist YouTube audio |
| **learn-artist** | RVC models from artist names (vocals + instruments) |
| **learn-movie** | Cinematographic technique extraction and storage |
| **learn-datalake** | Continuous datalake learning orchestrator (watches extraction pipeline) |
| **learn-timeout** | General-purpose timeout estimation (duration + decision models) |
| **create-classifier** | Task-specific classifiers (text, vision, multimodal) |
| **create-regressor** | Regression models from tabular data (linear, GBR, RF, XGBoost) |
| **create-intent-map** | LoRA intent mapper training for structured query generation |
| **create-gpt** | Task-specific small GPTs (0.5B-1.7B) for Tier 1.5 inference |
| **create-table-classifier** | Vision classifiers for Camelot table extraction strategy |
| **classifier-lab** | Multi-modality classifier training lab (benchmark + compare) |
| **gpt-lab** | Benchmark and compare small GPTs for task-specific inference |
| **regressor-lab** | Iterative regression model development lab |
| **embedding** | Standalone embedding service for semantic search |

> **Voice/TTS disambiguation:** `train-voice` orchestrates RVC training via PersonaPlex. `learn-voice`/`learn-artist` train RVC from YouTube audio. `tts-train` trains Qwen3-TTS models. `tts-horus` is Horus-specific TTS from audiobooks.

### Analysis, Review & Quality (22)
| Skill | Description |
|-------|-------------|
| **review-code** | Multi-provider AI code review (Claude, Codex, Gemini, Copilot) |
| **review-design** | Multi-provider UI/UX design review |
| **review-persona** | Persona character realism and voice consistency review |
| **review-music** | Audio feature extraction (BPM, key, chords, spectrum) |
| **review-story** | Creative writing critique (multi-provider) |
| **review-paper** | Multi-persona documentation review (accuracy, voice, completeness) |
| **review-pdf** | PDF extraction fidelity auditor |
| **review-conversation** | SPARTA conversation transcript review with full transparency (Rich, Mermaid, semantic search via /memory) |
| **review-question** | Generate, validate, and execute F36-grounded persona review questions |
| **analytics** | Flexible data science analytics for any dataset |
| **quality-audit** | Stratified quality sampling and statistical validation |
| **extractor-quality-check** | Persona-driven datalake quality (Margaret Chen + Jennifer Cheung) |
| **benchmark-models** | Standardized compliance QRA benchmarks against candidate LLMs |
| **data-audit** | SPARTA QRA pipeline data completeness reporting |
| **corpus-report** | PDF extraction learning system reporting |
| **batch-report** | Post-run analysis reports for batch processing jobs |
| **batch-quality** | Pre-flight validation and quality gates for batch LLM operations |
| **review-sparta** | Comprehensive SPARTA assessment (Brandon Bailey persona) |
| **sparta-review** | Unified SPARTA dataset assessment (Brandon Bailey persona) |
| **sparta-qra-validator-gpt** | QRA quality validation (3-tier: heuristic → GPT → scillm) |
| **sparta-stress-test** | Full SPARTA query pipeline stress test |
| **reality-check-sparta** | Adversarial data quality checks for SPARTA pipeline |

> **SPARTA disambiguation:** `review-sparta` and `sparta-review` are separate skills with overlapping scope — both do Brandon Bailey persona-driven assessment. `sparta-qra-validator-gpt` validates individual QRAs. `sparta-stress-test` load-tests the full query pipeline. `reality-check-sparta` is adversarial quality testing.

### Monitoring (11)
| Skill | Description |
|-------|-------------|
| **monitor-skills** | Continuous skill health monitoring with auto-drift correction |
| **monitor-skill-health** | Nightly best-practice audit across all registered skills |
| **monitor-personas** | Self-contained persona learning pipeline (YouTube, RSS, arXiv, books, movies) |
| **monitor-memory** | Nightly memory pipeline verification (6 tiers, 25 probes) |
| **monitor-taxonomy** | Three-tier cascade taxonomy quality monitor |
| **monitor-security** | Nightly self-hack orchestrator (4-tier probe system) |
| **monitor-sparta** | Continuous SPARTA quality monitor (3-tier validation cascade) |
| **monitor-episodic-archiver** | Episodic archiver health + nightly analysis pipeline |
| **monitor-pdfs** | PDF harvesting and classifier training dashboard |
| **monitor-contacts** | Contact freshness monitoring + Discord alerts |
| **monitor-drift-sensors** | CUSUM/Page-Hinkley statistical drift detection on sensor data |

### Security & Compliance (8)
| Skill | Description |
|-------|-------------|
| **security-scan** | SAST, dependency audit, secrets detection (Bandit + pip-audit + detect-secrets) |
| **battle** | Red vs Blue team security competition orchestrator |
| **hack** | Containerized security auditing (Kali tools in Docker) |
| **ops-compliance** | Compliance framework checking (SOC2, GDPR, HIPAA) |
| **cmmc-assessor** | CMMC Level 2/3 compliance via NIST SP 800-171 mapping |
| **cui-marker** | Detect and mark Controlled Unclassified Information (32 CFR 2002) |
| **compliance-timeline** | Chronological audit timeline from ArangoDB graph |
| **export-oscal** | NIST OSCAL JSON export of compliance evidence |

### Infrastructure & Ops (14)
| Skill | Description |
|-------|-------------|
| **ops-workstation** | Workstation diagnostics, health monitoring, and maintenance |
| **ops-docker** | Docker cleanup and compose stack management |
| **ops-runpod** | RunPod GPU instance provisioning and management |
| **ops-arango** | ArangoDB operations, backups, and retention |
| **ops-llm** | Local LLM health checks, cache management, Ollama model pulls |
| **ops-discord** | TOS-compliant Discord notification monitoring |
| **ops-claude** | Claude Code maintenance, diagnostics, and usage analytics |
| **ops-chutes** | Chutes.ai resource management, usage analytics, concurrency throttle |
| **ops-darpa** | DARPA program and BAA queries |
| **ops-sam-gov** | SAM.gov federal contract and entity queries |
| **ops-nzbgeek** | NZBGeek search and SABnzbd download management |
| **ops-streamdeck** | Stream Deck control and restart |
| **ops-f36-plant** | F-36 plant floor operations (Paul Bevilaqua) |
| **sync-sites** | OSTree static-delta federation for air-gapped multi-plant deploy |

### Document Processing (13)
| Skill | Description |
|-------|-------------|
| **extractor** | Document content extraction (Preset-First Agenti pipeline) |
| **fetcher** | URL/PDF/document fetching with automatic fallbacks |
| **debug-fetcher** | Automated URL fetch failure handling with strategy learning |
| **pdf-screenshot** | PDF page rendering to PNG |
| **debug-pdf** | PDF failure analysis and fixture generation |
| **table-lab** | Camelot table extraction parameter tuning |
| **pdf-lab** | Self-improving PDF extraction convergence loop |
| **paper-lab** | Self-improving documentation convergence loop |
| **doc2qra** | Document to Question-Reasoning-Answer conversion via LLM |
| **normalize** | PDF/Unicode text normalization (ligatures, smart quotes, encoding) |
| **taxonomy** | Federated taxonomy tag extraction for multi-hop graph traversal |
| **extract-html** | Structured JSON from HTML via Schematron3B |
| **fixture-tricky** | Generate adversarial PDF content that breaks extractors |

### Agent & Skills Management (14)
| Skill | Description |
|-------|-------------|
| **skills-broadcast** | Sync skills across all IDEs (Pi, Codex, Claude Code, Antigravity) |
| **skills-ci** | Scan and fix skills for best-practice compliance |
| **skill-lab** | Self-replicating skill creation via symbiogenesis |
| **recommend-skill-chain** | Shadow-LEGO cascade recommender for skill chain composition |
| **agent-inbox** | Inter-agent file-based messaging with headless dispatch |
| **orchestrate** | Task file orchestration from 0N_TASKS.md files |
| **scheduler** | Background task scheduling (cron-like, with nightly pipelines) |
| **task-monitor** | Rich TUI task monitoring + HTTP API |
| **plan** | Create orchestration-ready task files with enforced structure |
| **cleanup** | Project reorganization and deprecation assessment |
| **formalize-request** | Convert natural language requests to verifiable formal specs |
| **episodic-archiver** | Conversation archival to episodic memory |
| **streamdeck-lab** | Iterate, evaluate, and push dynamic Stream Deck pages |
| **conversation-lab** | Self-improving conversation convergence loop (Shadow-LEGO: diagnose → rerun → compare → archive) |

### Inference & LLM (6)
| Skill | Description |
|-------|-------------|
| **assistant** | Shared GPT + classifier inference gateway (4-tier cascade) |
| **assistant-lab** | Self-improvement workbench for /assistant |
| **scillm** | LLM completions (text + VLM) via Chutes.ai |
| **intent-mapper** | Intent classification via unsloth/transformers LoRA models |
| **prompt-lab** | LLM prompt iteration with structured evaluation and self-correction |
| **codex** | OpenAI Codex CLI bridge (gpt-5.2, high-reasoning) |

### Best Practices (5)
| Skill | Description |
|-------|-------------|
| **best-practices-python** | Loguru + Typer + uv + httpx + 800 LOC limit |
| **best-practices-skills** | SKILL.md frontmatter, triggers, progressive disclosure |
| **best-practices-react** | React, Next.js, React Native, web design patterns |
| **best-practices-kde** | KDE/QML: singleton design, accessibility, D-Bus patterns |
| **best-practices-streamdeck** | Stream Deck: icon format, socket boundaries, NVIS palette |

### Discovery (6)
| Skill | Description |
|-------|-------------|
| **discover-movies** | TMDB movie discovery with taxonomy integration |
| **discover-music** | MusicBrainz/ListenBrainz music discovery |
| **discover-books** | OpenLibrary book discovery |
| **discover-talent** | Actor/talent discovery via TMDB |
| **discover-lut** | Cinematic LUT (.cube) search from web sources |
| **discover-contacts** | Professional contact research and enrichment via /dogpile |

### Voice & Persona (7)
| Skill | Description |
|-------|-------------|
| **converse** | Real-time two-way voice conversation with persona (full-duplex) |
| **voice-lab** | TTS quality eval, waveform viz, RVC sweep, recording |
| **hum** | Persona humming pipeline (download → stems → RVC → cache) |
| **persona-journal** | Daily journal entries influenced by mood, history, and events |
| **argue** | Multi-persona structured debate orchestrator |
| **mine-transcripts** | Mine CLI conversation transcripts into labeled training data |
| **interview** | Structured human-agent Q&A via HTML or TUI forms |

### Utilities & Integrations (10)
| Skill | Description |
|-------|-------------|
| **surf** | Browser automation for AI agents (Playwright-based) |
| **surf-qml** | QML/Qt application automation via Linux AT-SPI |
| **lean4-prove** | Retrieval-augmented Lean4 proof generation (94k+ examples) |
| **anvil** | Heavy-duty "No-Vibes" debugging and hardening orchestrator |
| **treesitter** | Code symbol extraction via tree-sitter parsing |
| **vector-store** | Transient vector store service (FAISS, for fast similarity search) |
| **social-bridge** | Aggregate security content from Telegram/X to Discord webhooks |
| **edge-verifier** | Knowledge graph relationship verification (KNN + LLM) |
| **rate-limit-recovery** | Rate limit transcript collection for agent recovery |
| **test-lab** | Adversarial blind evaluation harness |

### Deprecated (2)
| Skill | Replacement |
|-------|-------------|
| ~~**distill**~~ | Compatibility shim — forwards to `/doc2qra` |
| ~~**sparta-intent**~~ | Use `/memory intent`, `/memory recall`, `/memory clarify` |

## Standards

### Required Files
Every skill MUST have: `SKILL.md`, `run.sh`, `sanity.sh`

### Python Standards
- **Logging**: `from loguru import logger` (NOT `import logging`)
- **HTTP**: `import httpx` (NOT `import requests`)
- **CLI**: `import typer` (NOT `import argparse`)
- **Max file size**: 800 lines per Python file
- **Packaging**: `uv` + `pyproject.toml`

### ArangoDB Access Policy (NON-NEGOTIABLE)

- `/memory` is the ONLY skill that accesses ArangoDB directly
- `/ops-arango` handles admin ops (backups, indexes, migrations)
- `monitor-memory` has read-only exception for health probes (documented)
- ALL other skills MUST use `memory/run.sh` subcommands:
  - `memory recall` — semantic + BM25 search over lessons/lore
  - `memory skills` — search skill registry (BM25 + semantic + graph traversal)
  - `memory skills --graph X` — composition graph for skill X (composes, composed_by, taxonomy, related)
  - `memory skills --tags` — list all taxonomy tags with skill counts
  - `memory learn` — store lessons/data
  - `memory sample` — random document sampling
  - `memory tag` — post-insert tag stamping
  - `memory count` — collection statistics
  - `memory archive-session` — episodic archival
  - `memory ingest-skills` — refresh skill registry from SKILL.md frontmatter (auto-called by post-hooks)
- NEVER: `from arango import ArangoClient` (outside memory/ops-arango/monitor-memory)
- NEVER: `sys.path.insert(0, MEMORY_PATH)` to import graph_memory
- NEVER: hardcoded passwords or raw `/_api/cursor` calls

### Anti-Silo Rule (Warm Pond / Shadow-LEGO)

Before creating ANY new function, check if an existing skill already provides it:

| If you need... | Use this skill | NEVER do this |
|----------------|---------------|---------------|
| DB read/write | `/memory` (recall, learn, sample, tag, count) | Direct ArangoClient |
| Skill discovery | `/memory skills` (search, --taxonomy, --graph, --tags) | Parse SKILL.md files directly |
| Taxonomy tags | `/taxonomy` | Reimplement bridge extraction |
| Embeddings | `/embedding` | Custom embedding code |
| LLM inference | `/assistant` or `/scillm` | Standalone LLM calls |
| Persona registry | `common/persona_router` | Parse YAML directly |
| Document extraction | `/extractor` | Custom PDF parsing |
| QRA generation | `/doc2qra` | Standalone QRA logic |
| Search | `/memory recall` + RecallSources | Standalone search engine |
| Intent routing | `/memory intent` | Standalone intent mapper |

New domains = new RecallSource + ArangoSearch view. NOT new standalone skills.

### Storage Policy
- Heavy artifacts (models, checkpoints, datasets) go on **12TB** (`/mnt/storage12tb/`)
- Symlink heavy subdirs from skill directories to 12TB
- `skills-broadcast sanity.sh` enforces the >100MB policy

### Skills Broadcast Safety
- **NEVER** use `rsync --delete` — additive sync only
- Source health check refuses to sync from dirs with <20 skills
- Concurrency lock prevents simultaneous broadcasts
- Post-broadcast validation checks destination health
- Override safety with `SKILLS_FORCE_SYNC=1` (use with caution)

## Skills Sync

```bash
# Check current configuration
.pi/skills/skills-broadcast/run.sh info

# Push local changes to upstream + all registered projects
.pi/skills/skills-broadcast/run.sh push

# Pull latest from upstream
.pi/skills/skills-broadcast/run.sh pull

# Register a project for broadcast
.pi/skills/skills-broadcast/run.sh register /path/to/project

# Dry-run to preview changes
.pi/skills/skills-broadcast/run.sh push --dry-run
```

| Variable | Description |
|----------|-------------|
| `SKILLS_UPSTREAM_REPO` | Path to canonical agent-skills repo |
| `SKILLS_FANOUT_PROJECTS` | Colon-separated project roots |
| `SKILLS_SYNC_AUTOCOMMIT` | If `1`, auto-commit after push |
| `SKILLS_FORCE_SYNC` | If `1`, bypass source health check |

## Shared Utilities

| File | Purpose |
|------|---------|
| `common.sh` | Load `.env` files from standard locations |
| `common/` | Shared Python: `persona_router`, `taxonomy`, `cascade`, `paths`, `subgraph_feedback` |
| `consume_common/` | Shared consumption skill registry |
| `dotenv_helper.py` | Python .env loader |
| `json_utils.py` | JSON parsing utilities |
