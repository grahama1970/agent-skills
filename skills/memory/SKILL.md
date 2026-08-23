---
name: memory
description: >
  MEMORY FIRST - Query memory BEFORE scanning any codebase. Use when encountering
  ANY problem, error, or task. Call "recall" FIRST, then scan codebase only if
  nothing found. Triggers: "check memory", "recall", "have we seen", "remember how".
allowed-tools: Bash, Read
triggers:
  - assess memory usage
  - check memory API usage
  - check memory
  - recall
  - clarify
  - have we seen this
  - remember how we solved
  - what did we learn
  - recall previous
  - save this lesson
  - learn from this
  - check memory for
  - have we seen this before
  - query memory first
  - ask clarifying questions
  - doesn't understand
metadata:
  short-description: MEMORY FIRST - Query before scanning codebase
provides:
  - memory-recall
  - memory-learn
  - intent-classification
  - edge-verification
  - usage-assessment
composes:
  - extractor
  - edge-verifier
  - taxonomy
  - embedding
  - task-monitor
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-scillm
  - best-practices-arangodb
taxonomy:
  - knowledge
  - persistence
  - resilience
  - precision
docs:
  arangodb: /best-practices-arangodb
disciplines:
  - memory-knowledge
---

> **STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.**
> Do not skim. Do not skip to the code examples. This document contains
> unique constraints, deterministic `_key` rules, secondary unique indexes,
> Qdrant semantic-sync metadata rules (no Arango vector arrays), and schema ownership rules that
> WILL cause silent data corruption or 400/409 errors if you ignore them.
> Every section exists because an agent broke something by not reading it.

# Memory Skill - MEMORY FIRST Pattern

Pi is the only CLI agent that can reliably enforce Memory First (other CLIs treat pre-hooks as optional), so this skill is the **front-door contract** for Pi and humans alike.

**Non-negotiable rule**: Query memory BEFORE scanning any codebase.

## Commands Snapshot

| Command                                           | Use Case                                                               |
| ------------------------------------------------- | ---------------------------------------------------------------------- |
| `./run.sh recall --q "..." --brief`               | **DEFAULT.** Slim output + proven skill chain. Use this.               |
| `./run.sh recall --q "..."`                       | Full output with taxonomy, raw scores, _key (when you need metadata)   |
| `./run.sh intent --q "..."` / `httpx POST /intent {q, scope?, fast?, app?}` | First-class intent product: classify route, QuerySpec, `recall_profile`, slots, and query plan |
| `httpx POST /speaker/resolve {candidates, threshold?, persona_id?}` | Voice identity front door: resolve listener evidence into known/unknown/ambiguous speaker context before `/intent` or personal recall |
| `httpx POST /answer {q, scope?, k?, collections?}` | First-class grounded answer product: answer only from deterministic general answers or recall evidence |
| `./run.sh clarify --q "..."` / `httpx POST /clarify {q, scope?, context?, k?}` | First-class ambiguity product: ask targeted follow-up questions when the request is underspecified |
| `./run.sh deflect --q "..."` / `httpx POST /deflect {q, persona_id?, intent_action?}` | First-class deflection product: route off-topic, unsafe, or no-match turns away from memory/evidence work |
| `httpx POST /execution-runs {...duration fields...}` | Record actual route/tool/subagent execution duration for ETA learning and recall |
| `httpx POST /execution-stats {route_key? ...}` | Return p50/p75/p90/p95 duration estimates from stored `execution_runs` |
| `httpx POST /store {document, collection}`         | **THE write endpoint.** Write to ANY collection. Auto-upserts by `_key`. |
| `httpx POST /store {document}` (no collection)     | Writes to `lessons` with Qdrant semantic sync + dedup (same as old `/learn`)     |
| `httpx POST /upsert {collection, documents}`       | Batch write (multiple docs). Same rules as `/store`.                   |
| `memory-agent activity ingest-git REPO ...`         | Ingest git commits as durable `project_activity` records for day/week code-activity recall |
| `uv run python -m graph_memory.maintenance.sanity_recall persona-graph-materialize` | Materialize searchable persona relationship docs into true Arango graph edge collections |
| `uv run python -m graph_memory.maintenance.sanity_recall persona-graph --base-url http://127.0.0.1:8601` | E2E canary: natural-language persona recall returns source/evidence-grounded memories, QRA-style question/answer/evidence/source records, explicit 2+ hop graph traversal, and directly filterable `tom_edges` |
| `./run.sh learn --problem "..." --solution "..."`  | **Deprecated.** CLI shorthand that calls `/store` with `collection=lessons` |
| `./run.sh chain-recall "query"`                   | Search proven skill chains directly                                    |
| `./run.sh chain-learn --skills "a,b,c" --task "..."` | Store a proven skill chain                                          |
| `./run.sh chain-stats`                            | Skill chain collection statistics                                      |
| `./run.sh preset compile --ids '{"set":"..."}'`   | Compile deterministic technical specs from ArangoDB                    |
| `./run.sh preset sanity`                          | Audit preset library for broken links / cycles (Strict Mode)           |
| `./run.sh info`                                   | Print active configuration (embedder, episodic sources, edge verifier) |
| `./run.sh serve --host --port`                    | Keep the FastAPI server warm for low-latency recall                    |
| `./run.sh status`                                 | Quick health check / Arango connectivity                               |

## `--brief` Mode: Context-Safe Recall with Skill Chains

**Use `--brief` by default.** It returns ~3.5x smaller output (problem, solution,
score, tags) PLUS the best matching proven skill chain from the `skill_chains`
collection. This is the "have I solved this before, and what skills worked?" pattern.

```bash
./run.sh recall --q "checkpoint resume fails after clear" --brief
```

```json
{
  "found": true,
  "items": [
    {
      "problem": "checkpoints collection not searchable via /recall",
      "solution": "Added to builtin_sources() in _declarations.py...",
      "score": 0.99,
      "tags": ["checkpoint", "grade:clean"]
    }
  ],
  "skill_chain": {
    "skills": ["memory", "assess", "checkpoint"],
    "task_type": "general",
    "success_rate": 1.0,
    "observations": 3,
    "elegance": "efficient",
    "score": 0.78
  }
}
```

**If `skill_chain` is present: follow it.** These chains are extracted from real
commits across 11 repos (17K+ commits) and proven by successful outcomes. The
agent doesn't guess which skills to compose — it follows the proven path.

### How Skill Chains Are Built

```
/checkpoint --skills A B C --grade clean
    ↓
1. Git commit with Skills: trailer (machine-readable)
2. learn_chain() → skill_chains collection (embeddings, energy scoring)
3. Nightly: mine-transcripts → chain-backfill → new chains from history
    ↓
Next agent: recall --brief → skill_chain: [A, B, C]
```

**Sources** (2,300+ chains, ranked by quality):
- `production` — from /checkpoint --skills (highest confidence)
- `commit-trailer` — from git commit Skills: trailers
- `commit-transcript` — transcript scan within ±15min of commit timestamp
- `transcript` / `warm_pond` — nightly regex-mined (lower confidence)

### Chain Prioritization

`--brief` prefers production chains over transcript-mined chains, and filters
out noisy chains with >8 skills. If no production chain matches, falls back
to transcript-mined chains that match semantically.

## Daemon HTTP Endpoints

Memory service runs as a Docker container on `http://127.0.0.1:8601`.

### First-Class Routing Products: Intent, Answer, Clarify, Deflect

`/intent`, `/answer`, `/clarify`, and `/deflect` are structured JSON products,
not prose helpers. They are a shared fail-closed
routing contract for memory, `/create-evidence-case`, SciLLM-backed final
responses, and delegated subagents. Do not let each skill invent its own
threshold for answerability, ambiguity, or off-topic rejection.

Use the routing set this way:

```text
/speaker/resolve for voice turns
  -> /intent   with speaker_resolution when speaker is known
  -> /clarify  when speaker is unknown or ambiguous

/intent
  -> /answer   when the request is grounded enough to answer
  -> /clarify  when entities, scope, evidence, or relationships are ambiguous
  -> /deflect  when the turn is off-topic, unsafe, no-match, or outside memory scope
```

These endpoints are routing or final-response products, not raw retrieval:

| Product | When to use | Schema | Surface |
| --- | --- | --- | --- |
| `/speaker/resolve` | Resolve listener/diarization/speaker-verification evidence into known, unknown, or ambiguous speaker context before using personal memory. It does not compute embeddings or inspect raw audio. | `memory.speaker_resolution.v1` | HTTP |
| `/intent` | Classify the user turn into a route, QuerySpec, recall profile, extracted entities, tag families, confidence/ranked candidates, slots, required artifacts, query plan, and turn-scoped `delivery_context` before retrieval or final-response work. | intent response fields + `memory.delivery_context.v1` | `./run.sh intent` and HTTP |
| `/answer` | Return clean grounded final text from deterministic general answers or memory recall evidence, plus engine-neutral `delivery_plan`. It must not invent unsupported facts or inject renderer tags. | `memory.answer.v1` + `memory.delivery_plan.v1` | HTTP only for now |
| `/clarify` | Ask targeted clean follow-up text when the query is too vague, has weak recall, unsupported entities, taxonomy gaps, or ambiguous scope, plus engine-neutral `delivery_plan`. | `memory.clarify.v1` + `memory.delivery_plan.v1` | `./run.sh clarify` and HTTP |
| `/deflect` | Redirect off-topic, unsafe, no-match, or content-safety turns before they enter recall, evidence-case, QRA, or subagent work, returning clean text plus engine-neutral `delivery_plan`. | `memory.deflect.v1` + `memory.delivery_plan.v1` | `./run.sh deflect` and HTTP |

`/create-evidence-case` depends on this boundary: `ANSWER` means evidence is
coherent enough to synthesize; `CLARIFY` means the case should not force a
verdict yet; `DEFLECT` means the request should not enter the evidence pipeline.
SciLLM may write the human-facing `final_response`, but deterministic memory
logic owns the route state and source packet. Every SciLLM final-response call
from memory must include `X-Caller-Skill: memory` and source metadata.

#### Delivery Context, Emotion, And Realtime Voice Boundary

Memory owns grounded text and engine-neutral delivery metadata. Realtime voice
renderers such as SPARTA/Chatterbox own render manifests, injectable tags, and
playback parameters.

Do not put Chatterbox tags such as `[laugh]`, `[curious]`, `[pause]`, or any
engine-specific markup into `final_response`, `source_answer`, clarification
text, deflection text, compactions, recall text, QRA text, or canonical Memory
answer content. Tags in Memory text corrupt byte spans, hashes, citations,
semantic embeddings, compaction provenance, and future recall.

The routing/final-response split is strict:

```text
/intent
  -> returns route/query metadata plus delivery_context only
  -> does not return final text
  -> must not return delivery_plan because final-text byte spans do not exist

/answer, /clarify, /deflect
  -> return clean text plus delivery_plan
  -> delivery_plan spans and text_sha256 are computed over the clean text
  -> Chatterbox/SPARTA compiles delivery_plan into runtime render_manifest
```

`delivery_context` is early, turn-scoped metadata. It may include listener
evidence, resolved speaker state, classifier source, affect category,
confidence, and routing influence. It must decay by default and must not become
persona memory unless separately promoted with provenance as a durable user
preference or repeated stable pattern. Situational frustration is not persona
memory by default.

`delivery_plan` is final-text metadata. It must be engine-neutral and valid
against the clean response text hash. It is allowed on `/answer`, `/clarify`,
and `/deflect` only after clean text exists.

Freeze this v1 tone vocabulary:

```text
neutral
calm
warm
careful
firm
concerned
curious
deescalating
urgent
```

Freeze these v1 effect keys:

```text
emphasis
pause_before_ms
pause_after_ms
pace_multiplier
intensity_delta
```

Tone influences delivery first, routing second, and never overrides grounding.
A hostile, frustrated, discouraged, or confused turn may make a response calmer,
firmer, more careful, more concerned, or more clarifying. It must not convert an
answerable grounded query into `/deflect` unless safety, off-topic, no-match, or
answerability rules independently justify that route.

SPARTA/Chatterbox may write a runtime `render_manifest` and injectable tags at
playback time. Memory may store or reference playback audit artifacts only as
external evidence. A render manifest is not canonical Memory answer content.

Live proof for this contract in the memory repo:

```bash
cd ${HOME}/workspace/experiments/memory
./scripts/prove-delivery-plan-contract.sh --base-url http://127.0.0.1:8601
```

The proof must show `/intent` has `delivery_context` and no `delivery_plan`,
while `/answer`, `/clarify`, and `/deflect` have clean text plus
`delivery_plan`, with no `emotion_tags`, `chatterbox_tags`, or `voice_policy`
leaking into canonical Memory output.

#### POST /speaker/resolve -- Voice Speaker Identity Product

Use `/speaker/resolve` before `/intent` for voice turns where the listener has
speaker verification or diarization evidence. This endpoint consumes upstream
speaker candidates and returns a memory-safe identity decision:

| Status | Caller behavior |
| --- | --- |
| `known` | Pass `speaker_resolution` to `/intent`, then use `/recall` with returned tags such as `speaker:horus_lupercal`, `user:horus_lupercal`, `persona:horus_lupercal`, and `persona:embry`. |
| `unknown` | Do not run personal memory/QRA recall. Ask the returned identity prompt, for example "Who am I speaking with?" |
| `ambiguous` | Do not choose between profiles. Ask the returned identity prompt or a disambiguating follow-up. |

`/speaker/resolve` is not an audio model. It does not compute embeddings,
transcribe speech, or inspect raw audio. RealtimeSTT, ECAPA, pyannote, or the
listener service owns audio evidence. Memory owns the identity/profile decision
surface and the safe tags that downstream recall may use.

Known voice turns should use the `speaker_conversation_memory` recall profile
when `/speaker/resolve` returns it. This profile is intentionally separate from
generic `persona_memory_recall`; it is for listener-resolved speaker-scoped
conversation facts and expects `speaker_identity` plus `speaker_scoped_memory`
artifacts in receipts.

Example:

```python
resp = client.post("/speaker/resolve", json={
    "session_id": "embry-session",
    "turn_id": "turn-123",
    "persona_id": "embry",
    "threshold": 0.82,
    "candidates": [
        {
            "speaker_id": "horus_lupercal",
            "display_name": "Horus Lupercal",
            "confidence": 0.94,
            "source": "ecapa",
            "tags": ["persona:horus_lupercal"]
        }
    ],
})
speaker = resp.json()

intent = client.post("/intent", json={
    "q": "Where did I grow up?",
    "scope": "persona_memory",
    "speaker_resolution": speaker,
    "fast": True,
}).json()
```

Unknown or ambiguous speakers must fail closed to identity clarification. Do not
use another user's memory, QRA preferences, emotional profile, or relationship
context until `/speaker/resolve` returns `status="known"`.

#### POST /intent -- Route and QuerySpec Product

Use `/intent` before recall or final-response work when a caller needs a
machine-readable decision about what kind of turn it received. It is the
first-class routing product that tells callers whether to query memory, answer
directly, clarify, deflect/no-match, run an app command, or route to research.
It returns the action, confidence, classifier source, entities, frameworks,
keywords, `recall_profile`, `slots`, required artifacts, and `query_plan`.
The response must be valid structured JSON. Human-facing copy belongs in a
separate response product, not in `memory.intent`.
Entity extraction is a first-class part of this product: `/intent` must surface
grounded entities, unresolved/fabricated-looking terms, frameworks, and the tag
families that should drive recall or clarification. Do not make callers rerun
regexes or infer evidence-case shape from prose.

`confidence` is required on the selected action. When the classifier is unsure
or the top actions are close, `/intent` should also return `top_intents` (or the
backward-compatible name `candidate_intents`) as a ranked list of alternatives:

```json
{
  "action": "CLARIFY",
  "confidence": 0.58,
  "top_intents": [
    {"action": "CLARIFY", "confidence": 0.58, "reason": "ambiguous_scope"},
    {"action": "QUERY", "confidence": 0.51, "recall_profile": "persona_memory_recall"},
    {"action": "QUERY", "confidence": 0.44, "recall_profile": "qra_evidence_question"}
  ]
}
```

Callers should treat low-confidence single-label outputs as incomplete. If
`confidence` is below the product threshold or the top two intents are too close,
route to `/clarify` instead of forcing recall, evidence-case generation, or a
subagent handoff.

Keep tag families separate:

| Family | Purpose | Typical fields | Used by |
| --- | --- | --- | --- |
| Grounded entities | Deterministic anchors and spans from `/extract-entities` / `graph_memory.entity_extraction.extract_entities()` | `entities`, `valid_entities`, `unresolved_terms`, `frameworks`, `query_plan.extracted_entities` | `/intent`, `/clarify`, `/create-evidence-case`, subagents |
| SPARTA taxonomy tags | Security/compliance bridge and mind taxonomy for SPARTA/control work | `sparta_tags`, `sparta_mind_tags`, `tier1`, `frameworks` | SPARTA recall profiles, evidence cases, QRA review |
| Theory-of-Mind tags | Belief, desire, emotion, stance, relationship, and non-compliance interpretation for persona/user memory graph traversal | `tom_state_type`, `tom_tags`, `emotion`, `stance`, `relationship_type` | persona recall, ToM graph traversal, non-compliance questions |
| Emotional intensity | Salience/ranking signal for persona or user memories after grounding and scope gates pass | `intensity`, `emotional_intensity`, `intensity_score` | persona/user memory ranking and tie-breaking |

SPARTA `mind` tags such as Harden/Detect/Model are not Theory-of-Mind tags.
They are security taxonomy labels and must stay gated by security/compliance
signal. Do not use them to infer a user's belief, desire, emotion, stance, or
non-compliance motive.

```bash
./run.sh intent --q "How do I fix the Codex prehook memory first result?" --scope project-agent
```

```python
resp = client.post("/intent", json={
    "q": "How do I fix the Codex prehook memory first result?",
    "scope": "project-agent",
    "session_id": "agent",
    "fast": True,
})
intent = resp.json()
```

#### POST /answer -- Grounded Final Answer Product

Use `/answer` when the caller wants memory to decide whether a final answer can
be produced. It first checks deterministic general-answer fixtures, otherwise
calls `/recall` and answers only from non-routing recall evidence. If recall
does not provide enough grounded evidence, it returns
`can_answer=false` with `answer_type="insufficient_memory_evidence"`.

```python
import httpx

client = httpx.Client(base_url="http://127.0.0.1:8601", timeout=10.0)
resp = client.post("/answer", json={
    "q": "What did we decide about memory first hooks?",
    "scope": "memory",
    "k": 5,
})
data = resp.json()
# data includes:
# {
#   "schema": "memory.answer.v1",
#   "can_answer": true,
#   "answer_type": "memory_recall",
#   "source_answer": "...",
#   "final_response": "...",          # written by SciLLM from the source packet
#   "final_response_origin": "scillm",
#   "confidence": 0.82,
#   "sources": [...],
#   "recall": {"found": true, ...},
#   "scillm": {"caller_skill": "memory", "source_packet_hash": "..."}
# }
```

#### POST /clarify -- Ambiguity Product

Use `/clarify` when the request is underspecified or evidence is weak. It
combines intent mapping, taxonomy/entity extraction, QRA correlation, and recall
confidence to produce specific follow-up questions. For direct grounded control
lookups, it can explicitly return `needs_clarification=false`.

```bash
./run.sh clarify --q "How do I secure it?" --scope sparta
```

```python
resp = client.post("/clarify", json={
    "q": "GPS spoofing",
    "scope": "sparta",
    "context": "I meant the F-36 GPS receiver",
    "k": 5,
})
```

#### POST /deflect -- Off-Topic and Safety Product

Use `/deflect` before launching memory, QRA, evidence-case, or subagent work
when a turn may be off-topic, unsafe, or a no-match. `QUERY` passes through with
`deflection_type="none"`; `CLARIFY`, `NO_MATCH`, `OFF_TOPIC`, and content-safety
actions return `should_deflect=true`.

```bash
./run.sh deflect --q "what is the weather" --persona embry
./run.sh deflect --q "something" --intent CLARIFY
```

```python
resp = client.post("/deflect", json={
    "q": "what is the weather",
    "persona_id": "embry",
    "intent_action": "NO_MATCH",
})
```

### POST /intent -- Intent Classification and Recall Profile Selection

`/intent` is the deterministic front door for classifying a user turn before
retrieval. It does not perform recall. It returns routing metadata that callers
can use to decide whether to call `/recall`, answer directly, ask for
clarification, route to a UI/app command, or launch a research workflow.

Use `/intent` when a caller needs to distinguish SPARTA/compliance questions,
project-agent procedural memory, artifacts, math, research, app commands, and
off-topic turns. SPARTA Chat and Explorer-style clients should call `/intent`
first, then pass `recall_profile` explicitly to `/recall` only when the returned
action calls for memory retrieval.

```python
import httpx

client = httpx.Client(base_url="http://127.0.0.1:8601", timeout=10.0)
resp = client.post("/intent", json={
    "q": "How do I fix the Codex prehook memory first result?",
    "session_id": "agent",
    "fast": True,
})
intent = resp.json()
# intent includes:
# {
#   "action": "QUERY",
#   "recall_profile": "procedural_memory",
#   "recall_profile_source": "deterministic_procedural",
#   "required_artifacts": ["lesson"],
#   "reranker_mode": "off",
#   "slots": {...},
#   "query_plan": null
# }
```

**Request fields:**
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `q` | str | required | User query or command |
| `scope` | str | `""` | Calling surface scope, such as `sparta` or `binary-explorer` |
| `session_id` | str | `api` | Thread key for self-correction context |
| `fast` | bool | `false` | Skip slower LLM paths; use deterministic/classifier routing |
| `app` | str | null | App context for registered UI action routing |

**Response fields include:** `action`, `confidence`, `top_intents` or
`candidate_intents`, `classifier_source`, `entities`, `frameworks`, `keywords`,
`ui_action`, `query_plan`,
`recall_profile`, `recall_profile_confidence`, `recall_profile_source`,
`recall_profile_spec`, `slots`, `required_artifacts`, `reranker_mode`, `k`, and
`depth`.

For compliance and persona-memory turns, the response should make the extraction
boundary explicit. Security/control queries should expose grounded control IDs
and SPARTA taxonomy fields. Persona, user-modeling, and non-compliance queries
should expose or route toward ToM fields (`tom_state_type`, `tom_tags`,
`emotion`, `stance`) and intensity/salience fields when available. If an entity,
taxonomy, or ToM tag family is ambiguous, route to `CLARIFY` instead of forcing a
generic recall profile.

Common actions:

| Action | Caller behavior |
|--------|-----------------|
| `QUERY` or `COMPLIANCE` | Call `/recall` or evidence-case flow as appropriate; pass `recall_profile` explicitly when present |
| `CLARIFY` | Ask the returned clarifying question instead of recalling |
| `NO_MATCH` | Do not run memory/QRA recall |
| `APP_COMMAND` | Execute the returned UI/app command or `query_plan` |
| `GENERAL_MATH` | Answer directly or route to a math solver; do not run memory/QRA recall |
| `RESEARCH` | Route to research/search tooling; do not run QRA recall |

**Critical contract:** `/recall` remains backward-compatible for ordinary recall
and does not run the full `/intent` pipeline internally. If callers want general
profile-aware retrieval, they should call `/intent` first and pass the selected
`recall_profile` explicitly to `/recall`. The exception is the deterministic
project-activity shortcut: when a query plainly asks about code work by ISO date,
ISO week, or human time window, `/recall` may apply the `temporal_project_state`
profile and `project_activity` routing automatically so project agents can ask
normal activity questions without a separate `/intent` call.

### POST /recall — Semantic Search (BM25 + cosine + graph traversal)

The primary search endpoint. Searches across lessons and SPARTA collections using
BM25 lexical matching, cosine similarity (via embedding service), and multi-hop
graph traversal (via `sparta_relationships` edges). Returns ranked results with
per-item scores and a combined `confidence` value.

```python
import httpx

client = httpx.Client(base_url="http://127.0.0.1:8601", timeout=10.0)

# Search all collections (lessons + SPARTA supplemental)
r = client.post("/recall", json={"q": "jamming satellite Telestar", "k": 5})
data = r.json()
# data = {
#   "found": True,
#   "should_scan": False,
#   "confidence": 27.988,         ← combined BM25+cosine+graph score
#   "items": [                    ← NOT "results" — the key is "items"
#     {
#       "_key": "...",
#       "scores": {               ← per-item breakdown
#         "bm25": 1.0,            ← BM25 reciprocal rank (0-1)
#         "graph": 0.5,           ← graph traversal score (0-1)
#         "dense": 0.39,          ← Qdrant semantic similarity (0-1, requires embedding + Qdrant)
#         "freshness": 0.87       ← time decay (0-1)
#       },
#       ...
#     }
#   ],
#   "meta": {"took_ms": 42, "supplemental_count": 10}
# }

# Search specific SPARTA collection for citation grounding
r = client.post("/recall", json={
    "q": "Cuban operators at the Bejucal electronic-warfare site",
    "k": 3,
    "collections": ["sparta_url_knowledge"],  # target specific corpus
})
```

**Parameters:**
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `q` | str | required | Search query text |
| `k` | int | 5 | Max results to return |
| `scope` | str | `""` | Project scope filter |
| `threshold` | float | 0.3 | Minimum confidence to consider "found" |
| `collections` | list | null | Target specific collections (null=all) |
| `tags` | list | null | Filter by tags |

**Response:** `{found, should_scan, confidence, items, meta, errors}`.
- `items` (NOT `results`) — ranked list of matching documents
- `confidence` — combined score from top items (BM25 × 0.6 + graph × 0.4 for lessons, BM25 only for SPARTA)
- Each item has `scores: {bm25, graph, dense, freshness}` breakdown
- When `collections` targets SPARTA collections, results come from supplemental sources via ArangoSearch View
- `dense=0.0` means Qdrant semantic recall is unavailable — check `embry-embedding-mm`, `embry-qdrant`, and `qdrant_point_id` metadata

**CRITICAL:** The daemon proxy runs `MemoryClient.recall()` locally (not just HTTP forwarding). Code changes to `api.py` require `uv pip install -e . && systemctl --user restart embry-memory`. Reload behavior depends on WHICH compose launched the container (verify with `docker inspect embry-memory --format '{{join .Config.Cmd " "}}'`):
- **Production** (`docker compose -f docker-compose.yml up -d`): the container has its own code copy — it does NOT auto-reload from host source files; rebuild/recreate required.
- **Development** (`docker compose up -d`, auto-includes `docker-compose.override.yml`): `./src` is bind-mounted and uvicorn runs `--reload --reload-dir /app/src`, so host edits to `src/` reload the live service within seconds (`StatReload detected changes` in `docker logs embry-memory`). This also means edits DURING an eval run contaminate it — freeze `src/` while acceptance runs execute.

`SKILL.md` is the agent contract and lives outside the memory Docker image. It
is read from the shared skill path, which project mirrors may symlink to. Editing
`SKILL.md` changes project-agent behavior as soon as agents read the file; it
does not require a Docker rebuild. Rebuild/relaunch Docker only for runtime code,
dependency, Dockerfile, or service configuration changes.

#### CORRECT usage — via the Docker-backed HTTP daemon, read `items` and `confidence`:
```python
import httpx

client = httpx.Client(base_url="http://127.0.0.1:8601", timeout=10.0)
resp = client.post("/recall", json={"q": "jamming satellite", "k": 5})
data = resp.json()

if data["found"]:
    for item in data["items"]:       # ← "items" NOT "results"
        print(item["scores"])         # ← {bm25, graph, dense, freshness}
    print(data["confidence"])         # ← combined grounding signal
```

## Persona Memory Recall For Project Agents

All persona memories use the same `/recall` endpoint. Do not query ArangoDB
directly, do not call Qdrant directly for answers, and do not build a separate
persona-memory retrieval path. Use `/recall` with the right `collections` and
scope tags, then inspect `items`, `scores`, and source fields.

Persona-memory recall for story, script, Theory-of-Mind, and character work
MUST be question-shaped. Do not use a bag of BM25 keywords as the `q` value when
proving persona memory availability or driving a story/script pipeline.

Required persona-memory recall contract:

1. `q` is a natural-language question that asks what the caller needs to know.
2. `collections` includes the target persona collection, usually
   `["persona_memory"]`.
3. `tags` includes the persona scope, for example `persona:embry` or
   `persona:horus_lupercal`; include book/source tags when relevant.
4. The caller checks returned `items` for the expected persona tag or
   `persona_id`.
5. For proof gates, the caller records the question, expected key/persona
   constraints, returned keys, and pass/fail result.

Bad persona-memory probe:

```json
{
  "q": "Horus Lupercal Warmaster brothers father Emperor Cthonia",
  "collections": ["persona_memory"],
  "tags": ["persona:horus_lupercal"]
}
```

Good persona-memory probe:

```json
{
  "q": "What memories or source-grounded facts explain Horus Lupercal as Warmaster, brother, son of the Emperor, and Cthonian primarch?",
  "collections": ["persona_memory"],
  "tags": ["persona:horus_lupercal"],
  "k": 8
}
```

Good Embry persona-memory probe:

```json
{
  "q": "What memory explains why Embry Lawson reacts to Hawaii, surfing, Kai, and afternoon rain with grief?",
  "collections": ["persona_memory"],
  "tags": ["persona:embry"],
  "k": 8
}
```

Required tags for book/persona recall:

```python
tags = ["persona:horus_lupercal", "book:flight_of_the_eisenstein"]
```

Use these collections by intent:

| Question type | Collections | Must inspect |
| --- | --- | --- |
| Source-grounded facts/Q&A | `["persona_memory"]` | `_key`, `book_id`, `persona_id`, `retrieval_text`, `scores.bm25`, `scores.dense`, `scores.graph` |
| Character/entity nodes | `["persona_entities"]` | `canonical_name`, `aliases`, `entity_kind`, `book_id`, `persona_id` |
| Fact mentions of characters | `["persona_memory_entity_edges"]` | `relationship_type="mentions"` or `"mentioned_by"`, `record_id`, `canonical_name`, `mention_text`, `source_ref` |
| Character co-mentions | `["persona_entity_edges"]` | `relationship_type="appears_with"`, `from_canonical_name`, `to_canonical_name`, `retrieval_text` |
| Theory-of-Mind/fact graph edges | `["persona_memory_edges", "tom_edges"]` | `_from`, `_to`, `relationship_type`, `tom_state_type`, `tom_tags`, `emotion`, `stance`, `confidence` |
| High-salience persona/user memories | `["persona_memory"]` plus graph edges | `emotion`, `stance`, `tom_state_type`, `tom_tags`, `intensity`, `emotional_intensity`, `intensity_score`, `scores.profile` |

Theory-of-Mind tags are first-class graph traversal fields, especially for
non-compliance questions. A non-compliance prompt usually asks why a user,
persona, actor, or character refuses, avoids, distrusts, rationalizes, or fails
to comply. Do not answer that from flat BM25 alone. Prefer recall over
`persona_memory`, `persona_memory_edges`, and `tom_edges`, then inspect:

- `tom_state_type`: belief, desire, intent, emotion, stance, knowledge,
  uncertainty, relationship, preference, memory, avoidance, or obligation.
- `tom_tags`: normalized traversal tags such as `belief`, `desire`, `fear`,
  `trust`, `distrust`, `avoidance`, `resistance`, `loyalty`, `shame`,
  `grief`, `anger`, `respect`, `authority`, `non_compliance`, and
  `compliance_pressure`.
- `emotion` and `stance`: direct affect and attitude toward the target.
- `relationship_type`: how one memory/persona/user state connects to another.

Emotional intensity is a first-class ranking signal for persona and user
memories, not just a drive attribute. After scope, evidence, and graph gates
pass, higher-salience memories should outrank neutral memories for persona/user
questions. Use whichever field the record exposes today (`intensity`,
`emotional_intensity`, or `intensity_score`), and preserve the field in the
returned item or profile trace. Do not let intensity override grounding: an
intense but unscoped or unsupported memory is still invalid.

Example real-world persona recall:

```python
import httpx

client = httpx.Client(
    base_url="http://127.0.0.1:8601",
    timeout=httpx.Timeout(10.0, connect=2.0),
)

resp = client.post("/recall", json={
    "q": "What did Caleb Arryn believe in Flight of the Eisenstein?",
    "k": 10,
    "collections": ["persona_memory"],
    "tags": ["persona:horus_lupercal", "book:flight_of_the_eisenstein"],
})
data = resp.json()

for item in data["items"]:
    assert item["book_id"] == "flight_of_the_eisenstein"
    assert item["persona_id"] == "horus_lupercal"
    print(item["_key"], item["scores"])
```

Graph edge recall:

```python
resp = client.post("/recall", json={
    "q": "Which characters appear with Horus Lupercal in Flight of the Eisenstein?",
    "k": 8,
    "collections": ["persona_entity_edges"],
    "tags": ["persona:horus_lupercal", "book:flight_of_the_eisenstein"],
})
for item in resp.json()["items"]:
    print(item["from_canonical_name"], item["relationship_type"], item["to_canonical_name"])
```

ToM edge recall:

```python
resp = client.post("/recall", json={
    "q": "What belief theory of mind edges exist for Caleb Arryn in Flight of the Eisenstein?",
    "k": 8,
    "collections": ["persona_memory_edges", "tom_edges"],
    "tags": ["persona:horus_lupercal", "book:flight_of_the_eisenstein"],
})
```

Healthy persona-memory recall has all of these signals:

- Returned rows have the requested `book_id` and `persona_id`.
- Story/script/TOM recall proof uses a natural-language question, not a keyword
  pile; keyword-only probes are not valid proof that persona recall works.
- Returned rows have the requested persona tag or `persona_id`; unscoped recall
  that mixes unrelated personas is a failed story/script pipeline gate even if
  `/recall` returns `found=true`.
- `persona_entity_edges` rows include endpoint names:
  `from_canonical_name`, `to_canonical_name`, `text`, and `retrieval_text`.
- `persona_memory_entity_edges` rows include `record_id`, `canonical_name`,
  `mention_text`, and `source_ref` span metadata.
- `scores.dense > 0.0` for at least some returned rows when Qdrant is healthy.
- `scores.graph > 0.0` for graph-supported facts when graph neighbors exist.
- ToM/non-compliance recalls expose `tom_state_type`, `tom_tags`, `emotion`, or
  `stance` on either the memory row or attached graph edge; generic security
  `mind` taxonomy tags are not accepted as substitutes.
- Persona/user-memory ranking preserves emotional salience fields
  (`intensity`, `emotional_intensity`, or `intensity_score`) when available and
  uses them only after scope/evidence/graph gates pass.
- `persona_memory_search` contains the linked persona collections:
  `persona_memory`, `persona_entities`, `persona_memory_entity_edges`,
  `persona_entity_edges`, `persona_memory_edges`, and `tom_edges`.
- Qdrant points for persona-memory rows have payload
  `arango_collection="persona_memory"` and `arango_key` equal to the Arango
  document `_key`. A mismatch means semantic point IDs collided and dense recall
  is not trustworthy.

Run the live E2E sanity gate after persona-memory code, schema, view, Qdrant, or
book-extractor changes:

```bash
cd ${HOME}/workspace/experiments/memory
uv run pytest -q tests/health/test_persona_memory_recall_e2e.py
```

This gate asks real book/persona questions through `/recall`, checks graph-edge
fields, verifies `persona_memory_search` view coverage, checks Qdrant text
identity, and proves the configured multimodal Qdrant collection can query both
`text_mm` and `image_mm` vectors.

## Project Activity Memory: Code Work By Day/Week

Use `project_activity` when a project agent needs to answer questions like:

- "What did we work on last week?"
- "What did we accomplish on 2026-05-13?"
- "What changed during 2026-W20?"
- "What work touched `scripts/validation/monitor_sparta.py`?"
- "Which commits solved the monitor false-green problem?"

`project_activity` records are generated from git commits and stored through
`/upsert` in the memory daemon. Git is the provenance backbone: commit SHAs,
repo paths, changed files, dates, and source refs are evidence fields.
`project_knowledge`, checkpoints, lessons, and conversations may enrich an
answer, but they do not replace the git-derived source refs.

### Ingest Git Activity

Run this after meaningful commits, before asking memory to summarize recent code
work, or from a scheduled project-agent maintenance job:

```bash
memory-agent activity ingest-git ${HOME}/workspace/experiments/memory \
  --project memory \
  --scope memory \
  --since 2026-05-13T00:00:00 \
  --until 2026-05-14T00:00:00 \
  --batch-id memory-activity-2026-05-13
```

Useful options:

| Option | Meaning |
|--------|---------|
| `--project` | Project name stored on records, for example `memory` or `sparta`. |
| `--scope` | Recall scope. Usually the project name. |
| `--since` / `--until` | ISO datetime bounds. Prefer these over vague human phrases in automation. |
| `--author` | Restrict to one git author when needed. |
| `--max-count` | Bound ingestion size for a proof run or smoke test. |
| `--all-branches` | Include commits outside the current branch. |
| `--batch-id` | Stable ingestion batch id for audit and rollback. |
| `--dry-run` | Build records without writing to memory. |
| `--skip-embedding` | Skip semantic embedding if the caller only needs BM25/source fields. |

Re-running ingestion for the same repo and commit SHAs must be idempotent. Event
identity is deterministic from repo root plus commit SHA, so repeat runs update
the same `_key` values instead of creating duplicates.

### Recall Activity

Project agents can ask activity questions through the normal recall endpoint:

```python
import httpx

client = httpx.Client(
    base_url="http://127.0.0.1:8601",
    timeout=httpx.Timeout(10.0, connect=2.0),
)

resp = client.post("/recall", json={
    "q": "what did we accomplish on 2026-05-13?",
    "scope": "memory",
    "k": 5,
})
data = resp.json()

for item in data["items"]:
    if item.get("_source") == "project_activity":
        print(item["commit_short"], item["commit_subject"])
        print(item["activity_date"], item["iso_week"])
        print(item["files_changed"])
        print(item["source_refs"])
```

For strict activity-only retrieval, pass `collections=["project_activity"]`:

```python
resp = client.post("/recall", json={
    "q": "what changed in scripts/validation/monitor_sparta.py?",
    "scope": "memory",
    "collections": ["project_activity"],
    "k": 5,
})
```

A healthy activity recall response should show:

- `meta.recall_profile = "temporal_project_state"` for date/week activity
  questions.
- `meta.recall_profile_source = "deterministic_project_activity"` when the
  deterministic project-activity router fired.
- Top activity answers with `_source = "project_activity"`.
- Evidence fields such as `commit_sha`, `commit_short`, `activity_date`,
  `iso_week`, `files_changed`, and `source_refs`.

### Answering Human Time Phrases

Humans may ask "last week" or "yesterday", but project agents should normalize
those phrases to ISO datetimes at the calling boundary whenever possible. Use
the caller's timezone and explicit bounds, then either:

1. ingest the matching git range with `memory-agent activity ingest-git`, or
2. recall using an ISO date/week query such as `2026-05-13` or `2026-W20`.

Do not rely on memory to inspect live git history by itself. Memory recalls
stored activity records. If recall misses or source refs are stale, the project
agent should run live git commands, ingest the missing range, and recall again.

### Relationship To `$project-knowledge` And `$ingest-code`

`$project-knowledge` may store durable summaries into memory and can appear in
the same `temporal_project_state` recall profile. Treat those rows as narrative
or project-state enrichment unless they cite immutable source refs.

`$ingest-code` is the code-structure lane. It extracts symbols with Tree-sitter
and writes `code_symbols` through `/memory`; `/memory` owns ArangoDB, Qdrant,
semantic sync, and payload/index behavior. `$ingest-code` must not write
directly to Qdrant. Join activity memory to code-symbol memory by shared
`repo_path`, file path, and commit metadata.

### Backout And Bad Imports

Every activity ingest should use a stable `--batch-id`. If a bad import happens,
quarantine or delete generated `project_activity` records by that batch id using
the memory project's maintenance path, then re-run recall to confirm the bad
records are absent. Do not delete git-derived records without preserving the
batch id, command, and reason in an artifact or maintenance log.

## Project Agent Location Registry

Memory is a durable registry of observations, not a live workstation scanner.
It can recall stored facts about paths, projects, artifacts, prior scans,
telemetry, and lessons only after those facts have been written into ArangoDB.
It does **not** list directories, probe mounts, run `rg`, call `find`, inspect
git worktrees, or invoke `ops-workstation` by itself.

Project agents should use this pattern for path and workspace discovery:

1. Call `/recall` before scanning. Ask for the project root, artifact path,
   prior scan result, or known location.
2. Use the result only when `found=true`, `confidence` is high enough for the
   task, `should_scan=false`, and the record's freshness/status is acceptable.
3. When memory misses, confidence is low, `should_scan=true`, or the record is
   stale-sensitive, run live discovery outside memory with `rg`, `find`, git,
   `test -e`, or `ops-workstation`.
4. Validate identity before trusting a path. A path match is not enough; check
   marker files, expected repository metadata, schemas, or command output.
5. Write the observation back through `/upsert` for batches. Use `/store` only
   for a single document write.

Example project-agent loop:

```python
import httpx

client = httpx.Client(base_url="http://127.0.0.1:8601", timeout=10.0)

recall = client.post("/recall", json={
    "q": "memory project root path",
    "k": 5,
    "collections": ["workspace_locations"],
}).json()

if (
    recall.get("found")
    and recall.get("confidence", 0.0) > 0.5
    and not recall.get("should_scan")
):
    candidates = recall["items"]
else:
    # Caller/orchestrator runs live discovery here, for example:
    # rg --files ${HOME}/workspace/experiments
    # find ${HOME}/workspace/experiments -maxdepth 3 -name AGENTS.md
    # ops-workstation scan ...
    candidates = []
```

When live discovery finds or validates locations, batch-write them:

```python
client.post("/upsert", json={
    "collection": "workspace_locations",
    "documents": [
        {
            "_key": "project:memory:root",
            "kind": "workspace_location",
            "project": "memory",
            "path": "${HOME}/workspace/experiments/memory",
            "status": "current",
            "observed_at": "2026-06-09T17:40:00Z",
            "validated_at": "2026-06-09T17:40:00Z",
            "source": "project_agent_scan",
            "evidence": {
                "commands": [
                    "test -d ${HOME}/workspace/experiments/memory",
                    "test -f ${HOME}/workspace/experiments/memory/AGENTS.md",
                    "rg --files ${HOME}/workspace/experiments/memory"
                ],
                "markers": ["AGENTS.md", "pyproject.toml", ".git"]
            }
        }
    ],
}).raise_for_status()
```

### Stale Location Handling

Do not silently delete old location records. Mark them with lifecycle status so
future agents can explain moves and avoid reusing invalid paths:

| Status | Meaning |
|--------|---------|
| `current` | Path exists and identity markers validate. |
| `unverified` | Recalled from memory but not checked in this session. |
| `stale` | Path existed before but now fails validation or is too old for the task. |
| `moved` | Old path is invalid and a replacement is known. |
| `missing` | Old path is invalid and no replacement was found. |

When a scan disproves an old record, `/upsert` the old `_key` with `status`,
`invalidated_at`, `invalidated_by`, and evidence. If a replacement is known,
write or update the replacement record and link it with `replacement_key`.

```python
client.post("/upsert", json={
    "collection": "workspace_locations",
    "documents": [
        {
            "_key": "project:memory:root:old",
            "kind": "workspace_location",
            "project": "memory",
            "path": "/old/path/memory",
            "status": "moved",
            "replacement_key": "project:memory:root",
            "invalidated_at": "2026-06-09T17:45:00Z",
            "invalidated_by": "project_agent_scan",
            "evidence": {
                "commands": ["test -d /old/path/memory"],
                "result": "path missing"
            }
        }
    ],
}).raise_for_status()
```

Mental model: memory answers "what did we previously know?", live discovery
answers "what exists right now?", and `/upsert` reconciles the two.

## scillm Persistence Collections

scillm uses ArangoDB (via the memory daemon) for all persistent state — no Redis needed.

### Collections

| Collection | Purpose | Written By |
|------------|---------|------------|
| `llm_call_log` | LLM execution telemetry (duration, model, tokens, cost, errors) | ArangoLogMiddleware |
| `scillm_response_cache` | Response caching + request deduplication | CacheMiddleware |
| `scillm_concurrency_state` | Concurrency backoff state (survives restarts) | ConcurrencyMiddleware |

### Response Caching (`scillm_response_cache`)

Caches LLM responses by model + messages hash. Identical requests return cached responses
instead of hitting the provider. Also deduplicates in-flight requests — if 3 agents ask
the same question simultaneously, only 1 API call is made.

```python
# Document structure
{
    "_key": "sha256-hash[:32]",
    "response": {...},           # Full OpenAI response object
    "created_at": 1712934567.0,
    "expires_at": 1712938167.0   # TTL (default 1hr)
}
```

Env vars: `SCILLM_CACHE_TTL_SEC=3600`, `SCILLM_CACHE_DISABLE=1`

### Concurrency Backoff State (`scillm_concurrency_state`)

Persists adaptive concurrency limits. When a provider returns 429s, scillm halves
concurrency. This state survives restarts — won't immediately hammer a rate-limited
provider after restart.

```python
# Document structure
{
    "_key": "concurrency_chutes",
    "provider": "chutes",
    "effective_limit": 2,         # Current limit (may be reduced from configured)
    "configured_limit": 4,        # Original limit from config
    "rate_limit_hits": [...],     # Recent 429 timestamps
    "last_recovery": 1712934567.0,
    "updated_at": 1712934567.0
}
```

State expires after 1 hour — stale backoff won't persist forever.

## LLM Execution Telemetry (`llm_call_log`)

Every `/scillm` call is automatically logged to `llm_call_log` with duration, model,
provider, tokens, cost, status, and caller skill. Use this for timeout estimation,
failure diagnosis, and cost tracking. **No new endpoints** — uses existing `/recall` and `/list`.

```python
# Find slow Chutes calls (BM25 + multi-hop via llm_call_log_edges)
resp = client.post("/recall", json={
    "q": "deepseek timeout error",
    "k": 10,
    "collections": ["llm_call_log"],
})

# Structured query: all errors from a specific provider
resp = client.post("/list", json={
    "collection": "llm_call_log",
    "limit": 50,
    "filters": {"provider": "chutes", "status": "error"},
})

# Filter by caller skill
resp = client.post("/list", json={
    "collection": "llm_call_log",
    "filters": {"caller": "dogpile", "date": "2026-04-05"},
})
```

**Document fields:** `_key`, `ts`, `date`, `model_requested`, `model_served`, `provider`,
`duration_ms`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `cost_usd`,
`status` (ok/error), `error`, `caller`.

Multi-hop graph traversal works automatically — no extra params needed.

**To tag which skill made the call**, pass an HTTP header to scillm:
```python
httpx.post(SCILLM_URL, headers={"x-caller-skill": "dogpile", ...}, json={...})
```

## Route/Tool/Subagent Execution Telemetry (`execution_runs`)

Memory owns ETA learning for routes, tools, and subagents through the
`execution_runs` collection. Do not create per-skill timing files, raw AQL timing
queries, or a separate subagent-only timing store. Store one record per completed
execution through `/execution-runs`, then query estimates through
`/execution-stats` or normal `$memory recall`.

Use `llm_call_log` for low-level provider latency. Use `execution_runs` for the
human-visible workflow duration that wait control needs: `/intent` route,
planned tool path, skill call, subagent task, or external tool run.

```python
import httpx

client = httpx.Client(base_url="http://127.0.0.1:8601", timeout=10.0)

client.post("/execution-runs", json={
    "request_id": "turn-123",
    "session_id": "embry-session",
    "executor_type": "memory_endpoint",
    "executor_name": "intent",
    "intent_action": "QUERY",
    "question_kind": "persona_current_fact_blend",
    "recall_profile": "persona_memory_recall",
    "response_mode": "research_grounded_persona_response",
    "tool_name": "brave-search",
    "duration_ms": 9000,
    "status": "ok",
    "scope": "persona_memory",
    "tags": ["persona:embry", "wait-control"],
})

stats = client.post("/execution-stats", json={
    "executor_type": "memory_endpoint",
    "executor_name": "intent",
    "intent_action": "QUERY",
    "question_kind": "persona_current_fact_blend",
    "recall_profile": "persona_memory_recall",
    "response_mode": "research_grounded_persona_response",
    "tool_name": "brave-search",
    "days": 14,
}).json()
# stats includes sample_count, percentiles.{p50,p75,p90,p95}, and recommended_timeout_ms.
```

`route_key` is deterministic:

```text
executor_type|executor_name|intent_action|question_kind|recall_profile|response_mode|tool_name
```

Subagents write to the same collection with `executor_type="subagent"` and
`executor_name` set to the agent id. Skills write with `executor_type="skill"`
and `executor_name` set to the skill name. This lets ETA logic compare every
request path without caring whether work ran inline, through a skill, or through
a subagent.

`execution_runs` is included in normal recall as a supplemental source:

```python
resp = client.post("/recall", json={
    "q": "how long do Embry persona current fact intent routes with brave-search take?",
    "collections": ["execution_runs"],
    "k": 10,
})
for item in resp.json()["items"]:
    print(item["route_key"], item["duration_ms"], item["status"])
```

Healthy execution telemetry has:

- `duration_ms` from a real completed execution, not a mocked provider response.
- `route_key` or enough route fields for memory to derive it.
- `executor_type` and `executor_name` that identify the runtime surface.
- `status`, `started_at`, `ended_at`, and `observed_at` timestamps.
- `retrieval_text` so `$memory recall` can find timing examples by natural language.

`/intent` wait-control estimates should prefer `execution_runs` percentiles for
the matching route bucket, then fall back to `llm_call_log` latency, then to a
deterministic route baseline only when no actual timing samples exist.

Standard memory endpoints must record their own wall-clock execution time after
the response is complete. This is not optional for first-class routing products:

```text
/recall
/answer
/clarify
/deflect
/intent
```

The standard endpoint timing row must include:

- `executor_type="memory_endpoint"` and `executor_name` set to the endpoint name.
- `duration_ms` measured from request receipt until after the final response body
  is available.
- `caller_skill` from `X-Caller-Skill` when provided.
- request scope/query metadata when available.
- returned `tool_calls`, `recommended_skills`, `skill_chain`, and `query_plan`
  under `metadata` when the endpoint returns them.
- `tool_name`/`route_key` derived from the tool/skill calls so ETA can estimate
  both endpoint routes and tool-bearing routes.

Do not log `/execution-runs` and `/execution-stats` through this automatic path;
those endpoints are the telemetry write/read surface itself.

## Timeout Estimation (`/latency-stats`)

Calculates latency percentiles and throughput stats from `llm_call_log` for timeout estimation.
Agents call this endpoint instead of writing AQL — keeps all database queries in the memory project.

```python
# Basic: get p95 latency for a model
resp = client.post("/latency-stats", json={
    "model": "deepseek-ai/DeepSeek-V3",
    "days": 7
})
# Returns: {recommended_timeout_ms: 8100, percentiles: {p50: 2100, p95: 8100, ...}}

# Token-aware: estimate timeout for a specific request size
resp = client.post("/latency-stats", json={
    "model": "deepseek-ai/DeepSeek-V3",
    "prompt_tokens": 3000,
    "completion_tokens": 1000
})
# Returns: {recommended_timeout_ms: 28500, estimated_timeout_ms: 28500,
#           throughput: {p50_tps: 45.2, p95_tps: 22.1}, ...}

# Batch: get stats for all models at once
resp = client.post("/latency-stats/batch", json={"days": 7})
# Returns: {models: [{model: "deepseek...", p95_ms: 8100, ...}, ...]}
```

**Request fields:**
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `model` | str | null | Filter by model_served |
| `provider` | str | null | Filter by provider (chutes, google, anthropic) |
| `days` | int | 7 | Lookback window (1-90) |
| `status` | str | "ok" | Filter by status (ok/error/all) |
| `prompt_tokens` | int | null | Expected prompt size for token-aware estimation |
| `completion_tokens` | int | null | Expected output size for token-aware estimation |

**Response fields:**
| Field | Description |
|-------|-------------|
| `sample_count` | Number of calls used for calculation |
| `percentiles` | {p50, p75, p90, p95, p99} in milliseconds |
| `throughput` | {p50_tps, p95_tps} tokens per second |
| `estimated_timeout_ms` | Based on token counts (if provided) |
| `recommended_timeout_ms` | Safe timeout — estimated_timeout_ms or p95 |

**How agents use it:**
```python
# Before making a large LLM call, estimate timeout
stats = client.post("/latency-stats", json={
    "model": model,
    "prompt_tokens": len(prompt) // 4,  # rough estimate
    "completion_tokens": 2000
}).json()

timeout = stats.get("recommended_timeout_ms", 30000) / 1000
response = await scillm_client.post("/v1/chat/completions",
    json=request, timeout=timeout)
```

## Common Mistakes

Agents make these mistakes **every session**. Read before using.

```python
# WRONG: "results" does not exist — the key is "items"
data.get("results", [])              # ← returns [] always
# RIGHT:
data["items"]                        # ← correct key

# WRONG: curl one-offs or raw TCP calls without typed timeouts
curl http://localhost:8601/recall
# RIGHT: use httpx with the Docker-backed daemon and explicit timeouts
client = httpx.Client(base_url="http://127.0.0.1:8601", timeout=httpx.Timeout(10.0, connect=2.0))
resp = client.post("/recall", json={"q": query, "k": 5})

# WRONG: subprocess.run(["memory/run.sh", "recall", ...]) in a loop
# → 2s overhead per call, fork-bomb risk (learn-datalake incident: 79 processes, 141GB RAM)
# RIGHT: httpx client reuses connection pool
for item in batch:
    resp = client.post("/recall", json={"q": item, "k": 3})

# WRONG: from graph_memory.api import MemoryClient
# → bypasses daemon, no BM25/graph scoring, no embedding integration
# RIGHT: always use HTTP client to daemon (above)

# WRONG: import requests; requests.post("http://127.0.0.1:8601/recall", ...)
# → 120s default timeout, no Unix socket support
# RIGHT: import httpx with explicit timeout
resp = client.post("/recall", json={...}, timeout=httpx.Timeout(10.0, connect=2.0))

# WRONG: building manual corpus with rapidfuzz instead of reading confidence
for doc in manually_fetched_docs:     # ← STOP. Just read data["confidence"].
    fuzz.partial_ratio(...)           #    The daemon already did BM25+cosine+graph.

# WRONG: reimplementing /recall with per-collection /list calls
for coll in ["sparta_controls", "sparta_url_knowledge"]:
    resp = client.post("/list", ...)  # ← STOP. /recall already searches all
    corpus += resp["documents"]       #    collections via the unified View.
# RIGHT: single /recall call with collections param
resp = client.post("/recall", json={"q": query, "k": 10,
    "collections": ["sparta_controls", "sparta_url_knowledge"]})

# WRONG: writing raw AQL outside the memory project
db.aql.execute("FOR doc IN lessons FILTER ...")
# → ALL AQL must reside ONLY in ~/workspace/experiments/memory/
# RIGHT: use /recall, /list, /analytics/run, /latency-stats endpoints

# WRONG: calculating latency percentiles with custom AQL
db.aql.execute("FOR doc IN llm_call_log SORT doc.duration_ms ...")
# → Use /latency-stats endpoint instead
# RIGHT: call /latency-stats with model/provider filter
client.post("/latency-stats", json={"model": "deepseek-ai/DeepSeek-V3"})

# WRONG: /learn to write to a specific collection
client.post("/learn", json={"problem": "...", "solution": "..."})
# → /learn is DEPRECATED. It always writes to lessons.
# RIGHT: /store with explicit collection
client.post("/store", json={"document": {"_key": "...", ...}, "collection": "sparta_qra"})
# For lessons specifically:
client.post("/store", json={"document": {"problem": "X", "solution": "Y", "tags": ["extraction"]}})

# WRONG: /store to lessons without taxonomy tags
client.post("/store", json={"document": {"problem": "X", "solution": "Y"}})
# RIGHT: include tags so /recall can find it via multi-hop
client.post("/store", json={"document": {"problem": "X", "solution": "Y", "tags": ["Fragility", "extraction"]}})

# WRONG: writing inline vector arrays into ArangoDB documents
db.aql.execute("INSERT {question: @q, answer: @a, embedding: @vec} INTO sparta_qra", ...)
client.post("/store", json={"document": {"question": q, "answer": a, "embedding": [...]}, "collection": "sparta_qra"})
# → ArangoDB is not the vector store. Do not write embedding/embedding_visual/vector fields.
# RIGHT: write canonical docs through /store or /upsert; memory semantic sync embeds and upserts Qdrant
client.post("/upsert", json={
    "collection": "sparta_qra",
    "documents": [{"_key": "...", "question": q, "answer": a}],
})
# Arango should receive pointer metadata only: qdrant_collection, qdrant_point_id,
# embedding_model, embedding_version, text_hash, semantic_sync_state
# Check coverage: uv run python scripts/validation/source_embedding_coverage.py --no-manifest
# Backfill/repair: scripts/migrate_arango_embeddings_to_qdrant.py (memory repo)

# WRONG: ignoring should_scan in recall response
if data["found"]: return data["items"]
# RIGHT: check should_scan for hybrid recall+codebase search
if data["found"] and data["confidence"] > 0.5: return data["items"]
elif data.get("should_scan"): return merge(data["items"], scan_codebase(query))

# WRONG: expecting memory to discover live workstation files
client.post("/recall", json={"q": "find every AGENTS.md on disk"})
# → /recall only searches stored memory records.
# RIGHT: recall first, then run live discovery outside memory when needed,
# then /upsert the validated observations.
if data.get("should_scan") or data.get("confidence", 0.0) <= 0.5:
    locations = run_rg_or_ops_workstation_scan()
    client.post("/upsert", json={
        "collection": "workspace_locations",
        "documents": locations,
    })

# WRONG: deleting stale paths with no audit trail
delete_doc("workspace_locations", old_key)
# RIGHT: mark stale/moved/missing and preserve evidence
client.post("/upsert", json={
    "collection": "workspace_locations",
    "documents": [{
        "_key": old_key,
        "status": "moved",
        "replacement_key": new_key,
        "invalidated_at": now,
        "evidence": {"commands": ["test -d /old/path"], "result": "missing"},
    }],
})

# WRONG: putting Chatterbox/emotion tags into Memory answer text
client.post("/store", json={"document": {
    "problem": "voice answer",
    "solution": "[curious] Ask which memory the user means."
}})
client.post("/deflect", json={"q": "unsupported", "intent_action": "NO_MATCH"}).json()["emotion_tags"]
# RIGHT: keep Memory text clean and let SPARTA/Chatterbox inject tags at playback
resp = client.post("/deflect", json={
    "q": "unsupported",
    "intent_action": "NO_MATCH",
}).json()
assert "[" not in resp["final_response"]
assert "delivery_plan" in resp
assert "emotion_tags" not in resp and "chatterbox_tags" not in resp
```


## Additional Project Documentation

This skill tree does not currently contain a `references/` directory. Use the
memory repository docs and source as the detailed contract:

- `${HOME}/workspace/experiments/memory/docs/guides/QDRANT_SEMANTIC_SYNC_CONTRACT.md` — current Qdrant vs Arango semantic vector contract: Arango stores pointer metadata only; Qdrant stores all Jina 1024-dimensional vectors.
- `${HOME}/workspace/experiments/memory/docs/CONTRACT.md` — stable CLI and Python API contract.
- `${HOME}/workspace/experiments/memory/docs/guides/QUICK_START.md` — setup and Python API quick start.
- `${HOME}/workspace/experiments/memory/docs/INTENT_MODEL_WALKTHROUGH.md` — `/intent` and QuerySpec architecture.
- `${HOME}/workspace/experiments/memory/docs/INTENT_MAPPER_WALKTHROUGH.md` — intent mapper failure modes, fixes, and validation notes.
- `${HOME}/workspace/experiments/memory/README.md` — project-level Theory of Mind, entity extraction, intent, and intensity contract notes.
- `${HOME}/workspace/experiments/memory/docs/guides/PERSONA_RECALL.md` — curated persona recall collection notes.
- `${HOME}/workspace/experiments/memory/src/graph_memory/cli/tom.py` — primary ToM/persona CLI entrypoint.
- `${HOME}/workspace/experiments/memory/src/graph_memory/cli/tom_advanced.py` — advanced ToM graph traversal and persona commands.
- `${HOME}/workspace/experiments/memory/src/graph_memory/service/app/` — live FastAPI endpoint implementation, including `_intent.py`, `_core.py`, `_store.py`, `_persona.py`, and `_tom.py`.
