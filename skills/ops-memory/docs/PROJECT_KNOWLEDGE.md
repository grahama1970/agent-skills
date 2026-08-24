# ops-memory — Project Knowledge (design spec, pre-build)

**Status:** DESIGN / NOT_ESTABLISHED (skill not yet implemented).
**Mission:** the memory/database setup must no longer be opaque. `ops-memory`
is the natural-language front door that explains and health-checks the whole
memory stack — Qdrant + ArangoDB + the embedder + the memory daemon — and
routes human questions to the right underlying skill.

## Composition (valence shell)

```
ops-memory  (orchestrator, read-only + fix-trigger)
├── composes ops-arango   → ArangoDB health, integrity, backups
├── composes ops-qdrant   → Qdrant vector-store health, collections, dense probe
├── composes memory       → /recall, /store features; daemon endpoints
├── composes phart-dag-chart → render "how /memory works" + DB topology as ASCII
├── composes analytics    → metrics tables for point counts, coverage, staleness
└── composes agentic-evals → standard gate
```

Boundary (non-negotiable): detection + orchestration live here and in
ops-arango/ops-qdrant; **all Qdrant/Arango mutation and semantic sync stay in
the memory repo** (`~/workspace/experiments/memory`, per memory/SKILL.md line
1372 "ALL AQL must reside ONLY in ~/workspace/experiments/memory/"). `--fix`
drives the memory repo's sanctioned `migrate_arango_embeddings_to_qdrant.py`;
it never reimplements sync.

## Natural-language requests ops-memory must answer

The skill must route a variety of human phrasings, not just flags:

| Human asks… | Routes to | Answer surface |
|---|---|---|
| "is the database healthy?" / "memory health" | ops-arango check + ops-qdrant check | merged health report |
| "how does /memory work?" / "show me the memory architecture" | phart-dag-chart | ASCII topology/DAG |
| "how is the database constructed?" / "what's the schema?" | ops-arango stats + ops-qdrant collections | topology table |
| "how many embeddings / vectors are stored?" | ops-qdrant | analytics metrics table |
| "which collections aren't vector-synced?" | ops-qdrant dense/coverage | metrics + gap list |
| "recall X" / "what do we know about X" | memory /recall | passthrough |
| "are the Arango backups current?" / "backup status" | ops-arango dump/retention | backup status |
| "fix semantic recall" | memory repo migrate (via --fix) | receipt + re-probe |

## Verified topology (this de-opaques the setup — receipts 2026-08-24)

Established live this session; keep current as the stack changes.

**Services / ports**
- `embry-memory` — the memory daemon, host `http://127.0.0.1:8601`. Owns
  `/recall`, `/store`, `/intent`, etc. Runs `MemoryClient.recall()` in-process.
- `embry-qdrant` — Qdrant vector store, host `http://127.0.0.1:6333` (REST) /
  6334 (gRPC). **Healthy.**
- `embry-embedding-mm` — jina multimodal embedder. **Published host port
  `:8603`** (internal container port 8602 is NOT published — CLI code that
  targets 8602 fails and falls back to local BERT; that is a bug, see #145).
  `POST :8603/embed/batch` returns **1024-dim** vectors.

**Store ownership (contract)**
- ArangoDB (via embry-memory) stores documents + **pointer metadata only**
  (`qdrant_collection`, `qdrant_point_id`, `embedding_model`, `text_hash`,
  `semantic_sync_state`). It must **never** store embedding arrays.
- Qdrant stores **all vectors**. jina v4/v5 unifies text+image in one 1024-dim
  space (arxiv 2506.18902), so multimodal collections use **named vectors**
  `text_mm` and `image_mm` (both 1024, Cosine); some collections use a single
  unnamed 1024 vector.

**Qdrant collections (11, 2026-08-24)** — sample:
- `memory_chunks_mm_jina_v5_omni_small_1024` — **1,338,129 pts**, text_mm+image_mm
- `memory_chunks_mm_jina_v4_1024` — **701,448 pts**, text_mm+image_mm
- `nist_pages_mm_jina_v4_1024`, `persona_dream_visual_assets_v1`,
  `readme_to_pitchdeck_visual_assets_v1`, `pitchdeck_house_slides_v1`,
  `watch_*` (reference/track/replay), `watch_reference_image_embeddings_jina_v5_1024`
  (single unnamed 1024 vector).

**Known gap (grahama1970/graph-memory-operator#145)**
- No `lessons` and no `skill_chains` Qdrant collection → `/recall` returns
  `dense:0.0` (BM25-only) for those record types. `skill_chains` has 1 doc.
  Remediation is memory-repo work; ops-memory's `--fix` will trigger it.

## Command surface (planned)

```
ops-memory health [--json]        # merged ops-arango + ops-qdrant health
ops-memory topology [--chart]     # how the stack is wired; --chart via phart-dag-chart
ops-memory metrics [--json]       # analytics table: points, coverage, dense-health, staleness
ops-memory explain "<question>"   # NL router over the table above
ops-memory recall "<query>"       # passthrough to memory /recall
ops-memory backups                # ArangoDB backup/retention status via ops-arango
ops-memory fix [--dry-run]        # trigger memory-repo migration; re-probe dense>0 as proof
ops-memory config doctor --json   # non-interactive readiness (needs_attention + safe_default)
```

## Readiness posture

Complex orchestrator → requires `fixtures/agentic_eval.json` with positive,
negative, and adversarial cases, a `sanity.sh` behavioral gate, and a live E2E
gate (`sanity-e2e.sh`) that calls the real ops-arango/ops-qdrant/memory
entrypoints and fails closed on a missing downstream receipt. Never mark a
feature READY on exit-0 alone.


## Session Handoff — 2026-08-24

Written before a Claude Code restart. If you are the next session, read this first.

### RESTART REQUIRED to activate (read only at process startup; NOT active in the writing session)
- `~/.claude/settings.json`: `skillOverrides` = 373 skills set to `name-only` (trims the
  403-skill listing that crowded every turn); `autoMemoryEnabled: false` (honors /memory-first);
  `claude-md-size-guard` PostToolUse hook wired (blocks CLAUDE.md rebloat > 14 KB).
- `~/.claude/CLAUDE.md`: distilled 20,583 -> 11,234 bytes (backup
  `~/.claude/CLAUDE.md.bak-20260824T123454Z`). New sessions load the lean version.
- `/clear` does NOT reload settings.json — do a full process restart.

### Already active (no restart needed)
- `~/.claude/hooks/operator-directive.sh` (UserPromptSubmit) — injects the 5-point operator
  directive every turn. Was a DANGLING reference (file absent); recreated this session.
- `~/.claude/hooks/no-candor-filler.sh` (Stop) — blocks vague/candor final messages. Was
  missing; created.
- herdr integration installed for Claude: `herdr integration status` -> `claude: current (v7)`.
  Previously `not installed` while Codex was `current` — herdr (the stalled-agent supervisor)
  had been blind to Claude. Likely a major reason Claude underperformed Codex in this env.

### Shipped to agent-skills@main this session
- ops-qdrant: read-only Qdrant health skill; `./sanity.sh` PASS; reproduces the #145 dense=0.
- ops-memory: DESIGN DOC ONLY (this file). NOT a runnable skill yet — no SKILL.md / run.sh.
- References sweep: 14 external-facing ops-* skills gained References sections with canonical
  docs + llms.txt / llms-full.txt (all verified HTTP 200 on 2026-08-24).

### Next steps (priority order)
1. Build ops-memory to the spec above (DB-transparency orchestrator: merged health+metrics,
   `/phart-dag-chart` topology, `/analytics` table, NL front door). Highest-value build.
2. Codify the References convention in best-practices-skills ("external-service ops-* skills
   require a References section with llms.txt where present").
3. ops-compliance References decision: cite AICPA / EU-GDPR / HHS-HIPAA / PCI-SSC, or leave.
4. memory repo / graph-memory-operator#145: vector-sync `lessons` + `skill_chains` into Qdrant
   and fix the CLI embed port 8602 -> 8603 so `/recall` returns dense > 0. Separate repo;
   ticketed. Re-verify with `skills/ops-qdrant/run.sh check --json` (dense_probe.dense_ok true).

### Shared-tree caution
- agent-skills working tree is shared by ~180 lanes and is dirty. `skills/ops-calendly/SKILL.md`
  carries ANOTHER lane's uncommitted change — never commit it wholesale. All pushes this session
  used temp-index plumbing off origin/main to avoid clobbering lanes.
