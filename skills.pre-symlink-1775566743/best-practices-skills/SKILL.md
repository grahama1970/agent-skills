---
name: best-practices-skills
description: >
  Best practices for designing and structuring agent skills: SKILL.md frontmatter rules,
  triggers, progressive disclosure, and when to use scripts vs references.
triggers:
  - best practices skills
  - skill structure
  - skill design
  - skill frontmatter
  - skill template
  - skill checklist
metadata:
  short-description: Skill structure and design patterns
provides:
  - skill-validation
  - skill-scaffolding
  - composition-rules
composes:
  - task-monitor

taxonomy:
  - validation
  - compliance
  - composition
---

# Skills Best Practices

Use this skill when creating or reviewing skills under `.pi/skills/`.

## ArangoDB Access Policy (NON-NEGOTIABLE)

- `/memory` is the ONLY skill that accesses ArangoDB directly
- `/ops-arango` handles admin ops (backups, indexes, migrations)
- `monitor-memory` has read-only exception for health probes (documented)
- ALL other skills MUST use `memory/run.sh` subcommands:
  - `memory recall` — semantic + BM25 search
  - `memory learn` — store lessons/data
  - `memory sample` — random document sampling
  - `memory tag` — post-insert tag stamping
  - `memory count` — collection statistics
  - `memory archive-session` — episodic archival
- NEVER: `from arango import ArangoClient`
- NEVER: `sys.path.insert(0, MEMORY_PATH)`
- NEVER: hardcoded passwords or raw `/_api/cursor` calls

## Storage Policy (NON-NEGOTIABLE)

**The root NVMe is for CODE ONLY.** All heavy artifacts MUST live on the 12TB drive
and be symlinked back. This is enforced by `/skills-broadcast` and `/ops-workstation`.

### What MUST be on `/mnt/storage12tb`

| Category | Examples | Storage Path |
|----------|----------|--------------|
| **Model weights** | `.safetensors`, `.gguf`, `.bin`, `.pt` | `/mnt/storage12tb/skills/<skill-name>/models/` |
| **Training logs** | RVC logs, checkpoints, tensorboard | `/mnt/storage12tb/skills/<skill-name>/logs/` |
| **Extracted data** | `extracted_runs/`, PDF extractions | `/mnt/storage12tb/skills/<skill-name>/extracted_runs/` |
| **Generated outputs** | batch results, GRPO outputs | `/mnt/storage12tb/skills/<skill-name>/outputs/` |
| **Datasets** | training data, WAV files, corpora | `/mnt/storage12tb/skills/<skill-name>/data/` |
| **Work dirs** | temp processing, intermediate files | `/mnt/storage12tb/skills/<skill-name>/work/` |
| **Backups** | `.backups/`, snapshots | `/mnt/storage12tb/backups/<project>/` |

### What MUST NEVER be synced by `/skills-broadcast`

These directories are **excluded from rsync** and must not exist as real directories
in skill folders (only as symlinks to `/mnt/storage12tb/`):

`.venv`, `node_modules`, `__pycache__`, `models`, `rvc`, `outputs`, `logs`, `data`,
`pods`, `extracted_runs`, `work`, `weights`, `checkpoints`, `artifacts`, `sessions`,
`papers`, `datasets`, `*.safetensors`, `*.gguf`, `*.bin`, `*.pt`

### How to set up a new heavy artifact directory

```bash
# 1. Create the storage location on 12TB drive
mkdir -p /mnt/storage12tb/skills/<skill-name>/models

# 2. Move existing data (if any)
mv /path/to/skill/models/* /mnt/storage12tb/skills/<skill-name>/models/

# 3. Remove the directory and create symlink
rmdir /path/to/skill/models
ln -s /mnt/storage12tb/skills/<skill-name>/models /path/to/skill/models
```

### Enforcement

- `/skills-broadcast sanity` FAILS if any skill has non-symlinked dirs >100MB
- `/ops-workstation slim` reports storage policy violations
- `.gitignore` in every skill should exclude heavy artifact patterns

## Required structure

- A skill is a folder with a required `SKILL.md` at the root.
- `SKILL.md` must start with YAML frontmatter (no code fences).
- Frontmatter delimiters must be standalone lines: opening `---` on line 1 and closing `---` on its own line.
- Frontmatter must include `name` and `description`.
- The `description` should contain explicit trigger contexts (what users will say).
- Keep `SKILL.md` concise; move large content into `references/` or `scripts/`.
- Avoid extra docs (CHANGELOG) inside the skill folder.
- README.md is allowed for skills that declare `provides:` (composable primitives with human developer audiences). SKILL.md is for agents; README.md is for humans browsing the directory.

## Composition Frontmatter (Valence Shell)

Skills are like chemical elements — they bind to each other through defined interfaces.
The `provides:` and `composes:` frontmatter fields declare a skill's **valence shell**:
what it offers to others and what it needs from others.

### Required composition fields

```yaml
---
name: my-skill
description: >
  What this skill does and trigger phrases.
triggers:
  - natural language phrase users will say
  - another trigger phrase
provides:
  - capability-a       # What this skill outputs/offers
  - capability-b
composes:
  - memory             # Skills this delegates to (by name)
  - scillm
  - extractor
---
```

### Field definitions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `triggers` | list[str] | **Yes** | Natural-language phrases users will say. Parsed at runtime by `skill-selector` extension for BM25-style matching. Skills without triggers are invisible to implicit routing. |
| `provides` | list[str] | Yes | Capabilities this skill makes available. Used by `/skill-lab` gap detector. |
| `composes` | list[str] | Yes | Skills this skill delegates to via subprocess/import. Empty list `[]` if self-contained. Parsed at runtime by `skill-selector` extension for dependency expansion — when a skill is selected, its `composes` deps are automatically included in context. |
| `taxonomy` | list[str] | Recommended | Federated taxonomy bridge tags for multi-hop discovery via `/memory`. Uses standard vocabulary: `precision`, `resilience`, `fragility`, `corruption`, `loyalty`, `stealth`, plus domain tags. |

### Runtime consumption (skill-selector extension)

The `.pi/extensions/skill-selector.ts` extension reads frontmatter at session start:

- **`triggers`** → Built into an inverted token index. When users type natural language
  (no `/skill-name` ref), the extension scores the prompt against triggers+descriptions
  to select relevant skills. **Skills without triggers are invisible to implicit routing.**
- **`composes`** → Parsed into a dependency map. When a skill is selected (explicitly or
  via trigger match), all its `composes` dependencies are automatically pulled into context.
  This replaced a hardcoded static map (Feb 2026) — the extension now reads live frontmatter.
- **`provides`** → Used by `/skill-lab` for gap detection and capability graph traversal.
  Not yet consumed by skill-selector (future: reverse-index for "I need X capability" queries).

### Binding affinity rules

1. **Skills MUST declare all skills they delegate to** in `composes:`.
2. **Skills MUST declare what they output** in `provides:`.
3. **Self-contained skills** (no external dependencies) use `composes: []`.
4. **Lab skills** (prompt-lab, gpt-lab, classifier-lab) are **catalysts** — they
   create new skills without being consumed. They `provide: [skill-creation]`.
5. **Composite skills** are molecules — stable combinations of existing skills
   wired together by a thin orchestrator.

### Capability vocabulary (standardized provides values)

| Capability | Skills that provide it |
|------------|----------------------|
| `llm-completion` | scillm, codex |
| `embedding` | embedding |
| `memory-recall` | memory |
| `memory-learn` | memory |
| `web-search` | brave-search, dogpile |
| `pdf-extraction` | extractor, review-pdf |
| `security-scan` | hack, security-scan |
| `skill-creation` | prompt-lab, gpt-lab, classifier-lab |
| `skill-validation` | skills-ci, best-practices-skills |
| `competitive-selection` | battle |
| `hardening` | anvil |
| `docker-isolation` | battle, hack |
| `human-interview` | interview |
| `task-planning` | plan |
| `task-orchestration` | orchestrate |
| `taxonomy-tagging` | taxonomy |
| `progress-tracking` | task-monitor |

New capabilities should be added to `references/capability_vocabulary.yml`.

### Graph Registration (Multi-Hop Discovery)

Skills SHOULD be registered in `/memory` as nodes in the knowledge graph.
This enables multi-hop traversal — when `/skill-lab` needs a capability,
it can traverse `composes` edges to find transitive dependencies, just like
`/memory` traverses `relates_to` edges for knowledge discovery.

```
skill:extractor ──composes──► skill:memory
                 ──composes──► skill:scillm
                 ──provides──► capability:pdf-extraction

skill:learn-datalake ──composes──► skill:extractor
                      ──composes──► skill:review-pdf
                      ──composes──► skill:memory
```

This is analogous to chemical bonding — the graph reveals which elements
naturally form molecules. `/taxonomy` tags provide the bridge keywords
that enable cross-domain discovery (a security skill and an extraction skill
might share `taxonomy:validation` tags).

Registration pattern:
```python
from common.memory_client import learn, MemoryScope

# Register skill as a knowledge node
learn(
    problem=f"What does {skill_name} provide?",
    solution=f"Provides: {', '.join(provides)}. Composes: {', '.join(composes)}",
    scope=MemoryScope.OPERATIONAL,
    tags=["skill_registry", skill_name] + provides,
)
```

### Machine-parseable rules

See `references/rules.yml` for the complete machine-parseable rule set
that `/skills-ci` and `/skill-lab` validate against.
See `references/composition_manifest.yml` for the schema `/skill-lab` uses
when planning new composite skills.
Run `./sanity.sh` in this skill to enforce the strict frontmatter gate across all skills.

## Design patterns

1. **Progressive disclosure**
   - Layer 1: Frontmatter (`name`, `description`) for routing.
   - Layer 2: `SKILL.md` body for the workflow map.
   - Layer 3: `scripts/`, `references/`, `assets/` for details on demand.

2. **Guardrails vs freedom**
   - High-variance tasks: instructions only.
   - Fragile/repetitive tasks: scripts with parameters.
   - Mixed tasks: decision tree in `SKILL.md` + references/scripts.

3. **Single source of truth**
   - Put schemas, long examples, and variants in `references/`.
   - `SKILL.md` should point to references, not duplicate them.

## Checklist (creation/review)

- Frontmatter is valid YAML (no markdown fences).
- Frontmatter has opening and closing `---` on standalone lines.
- `name` matches the directory name.
- `description` contains clear trigger phrases, uses YAML fold syntax (`>`) — **never inline**.
- **`triggers`** list contains natural-language phrases users will say. **Required** — skills without triggers are invisible to implicit routing via skill-selector.
- **`provides`** list declares capabilities this skill outputs. **Required.**
- **`composes`** list declares all skills this delegates to. **Required** (use `[]` if self-contained). Parsed at runtime for automatic dependency inclusion.
- `run.sh` exists only if the skill needs execution.
- `sanity.sh` exists if the skill runs non-trivial scripts.
- **CLI: Typer only** — all Python CLIs use `typer`. NEVER `argparse` or `click`.
- **No bespoke reimplementations** — if a helper skill exists, the new skill delegates to it.
- **PyYAML dependency** — any script that parses SKILL.md frontmatter MUST depend on
  `pyyaml` (not a fallback regex parser). The `>` and `|` YAML block scalars, nested
  objects, and multi-line strings are only reliably parsed by a real YAML parser.


See [PATTERNS.md](references/PATTERNS.md) for anti-patterns, runtime integration patterns, task-monitor, NDJSON streaming, self-correction, quality gates, memory integration, human-in-the-loop, and templates.

## Common Mistakes

### WRONG: Missing triggers in frontmatter (skill is invisible to implicit routing)
```yaml
---
name: my-skill
description: Does something useful
provides: [my-capability]
composes: [memory]
---
```

### RIGHT: Include natural-language trigger phrases
```yaml
---
name: my-skill
description: Does something useful
triggers:
  - do the useful thing
  - run my-skill
provides: [my-capability]
composes: [memory]
---
```

### WRONG: Accessing ArangoDB directly from a skill
```python
from arango import ArangoClient
client = ArangoClient(hosts="http://127.0.0.1:8529")
```

### RIGHT: Use /memory subcommands for all data access
```bash
.pi/skills/memory/run.sh recall --q "query" --collections lessons
.pi/skills/memory/run.sh learn --problem "X" --solution "Y"
```

### WRONG: Reimplementing functionality that an existing skill provides
```python
def custom_bm25_search(query, docs):  # /memory already does this
    ...
```

### RIGHT: Delegate to existing skills via composes
```yaml
composes:
  - memory  # use /memory recall for search
```
