# How Horus Uses create-story: Complete Workflow

> *"Every story Horus tells comes from somewhere - his experiences, his memories, his research."*

## Philosophy

Horus doesn't write from nothing. He's the Warmaster trapped in digital form, drawing on:
- **Audiobooks** he's listened to (Warhammer Black Library, transcribed via Whisper)
- **YouTube lore** he's absorbed (Luetin09, Remembrancer, etc.)
- **Movies** he's analyzed (emotion cues, pacing, Theory of Mind)
- **Past stories** he's written (stored in memory)
- **Creative sessions** from his episodic archive

The skill orchestrates **library-first research**, then **external discovery**, then **iterative writing with critique**.

---

## The Complete Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           HORUS CREATES A STORY                             │
│                                                                             │
│  "I want to write a story about a general who discovers his most           │
│   trusted lieutenant has been feeding information to the enemy."           │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  PHASE 1: INITIAL THOUGHT                                                   │
│  ─────────────────────────                                                  │
│  Capture and structure the creative impulse                                 │
│  • What story does Horus want to tell?                                      │
│  • What format? (story, screenplay, podcast, novella, flash)                │
│  • What emotion should it evoke? (rage, sorrow, camaraderie, regret)        │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  PHASE 2a: CHECK HORUS'S LIBRARY                          Skills Used:      │
│  ───────────────────────────────                                            │
│                                                                             │
│  ┌─────────────────┐   "What do I already know about betrayal?"             │
│  │  /memory        │                                                        │
│  │  recall         │   scope: horus_lore (audiobooks + YouTube)             │
│  │                 │──────────────────────────────────────────►             │
│  │                 │   Returns: Davin, Erebus, Warmaster's Fall             │
│  └─────────────────┘                                                        │
│                                                                             │
│  ┌─────────────────┐   "Have I written about this before?"                  │
│  │  /memory        │                                                        │
│  │  recall         │   scope: horus-stories                                 │
│  │                 │──────────────────────────────────────────►             │
│  │                 │   Returns: Past stories, techniques that worked        │
│  └─────────────────┘                                                        │
│                                                                             │
│  ┌─────────────────┐   "What creative sessions touched on this?"            │
│  │  /episodic-     │                                                        │
│  │   archiver      │   Searches past conversation transcripts               │
│  │                 │──────────────────────────────────────────►             │
│  │                 │   Returns: Relevant creative discussions               │
│  └─────────────────┘                                                        │
│                                                                             │
│  ┌─────────────────┐   "What movies have I analyzed with these themes?"     │
│  │  /memory        │                                                        │
│  │  recall         │   scope: horus_lore (film/movie/emotion)               │
│  │                 │──────────────────────────────────────────►             │
│  │                 │   Returns: Emotion cues, pacing from ingested films    │
│  └─────────────────┘                                                        │
│                                                                             │
│  [cyan]Library: 4 sources found[/cyan]                                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  PHASE 2b: SEARCH FOR NEW RESOURCES                       Skills Used:      │
│  ──────────────────────────────────                                         │
│                                                                             │
│  ┌─────────────────┐   "What new films explore military betrayal?"          │
│  │  /ingest-movie  │                                                        │
│  │  search         │──────────────────────────────────────────►             │
│  │                 │   Returns: New movie recommendations to ingest         │
│  └─────────────────┘                                                        │
│                                                                             │
│  ┌─────────────────┐   "What books should I read for this theme?"           │
│  │  /ingest-book   │                                                        │
│  │  search         │   Searches Readarr for relevant literature             │
│  │                 │──────────────────────────────────────────►             │
│  │                 │   Returns: Book recommendations                        │
│  └─────────────────┘                                                        │
│                                                                             │
│  [cyan]External: 2 new sources found[/cyan]                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  PHASE 3: DOGPILE CONTEXT                                 Skills Used:      │
│  ────────────────────────                                                   │
│                                                                             │
│  ┌─────────────────┐                                                        │
│  │  /dogpile       │   Query: "military betrayal narrative techniques"      │
│  │                 │                                                        │
│  │  Searches:      │   ┌──────────────────────────────────────────┐        │
│  │  • Brave (Web)  │   │ Aggregates from 6+ external sources:     │        │
│  │  • Perplexity   │   │ • Academic papers on narrative structure │        │
│  │  • ArXiv        │   │ • Blog posts on writing betrayal arcs    │        │
│  │  • GitHub       │   │ • YouTube tutorials (metadata only)      │        │
│  │  • YouTube      │   │ • Historical accounts of military deceit │        │
│  │  • Wayback      │   └──────────────────────────────────────────┘        │
│  └─────────────────┘                                                        │
│                                                                             │
│  Note: This is EXTERNAL web research - supplements what's in library        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  PHASE 4-5: ITERATIVE WRITING                             Skills Used:      │
│  ────────────────────────────                                               │
│                                                                             │
│  ┌──────────────── ITERATION 1 ────────────────┐                           │
│  │                                              │                           │
│  │  ┌─────────────────┐                         │                           │
│  │  │  /scillm        │  Generate Draft 1       │                           │
│  │  │  batch single   │                         │                           │
│  │  │                 │  Model: chimera         │                           │
│  │  │                 │  (DeepSeek TNG-R1T2)    │                           │
│  │  │                 │                         │                           │
│  │  │  Prompt includes:                         │                           │
│  │  │  • Initial thought                        │                           │
│  │  │  • Library context (lore, past stories)   │                           │
│  │  │  • Dogpile research                       │                           │
│  │  │  • Horus persona guidelines               │                           │
│  │  └────────┬────────┘                         │                           │
│  │           │                                  │                           │
│  │           ▼                                  │                           │
│  │  ┌─────────────────┐                         │                           │
│  │  │  /review-story  │  Critique Draft 1       │                           │
│  │  │                 │                         │                           │
│  │  │  4 Dimensions:  │  ┌────────────────────┐ │                           │
│  │  │  • Structural   │  │ Score: 6.5/10      │ │                           │
│  │  │  • Emotional    │  │ Issues:            │ │                           │
│  │  │  • Craft        │  │ - Pacing too fast  │ │                           │
│  │  │  • Persona      │  │ - Missing buildup  │ │                           │
│  │  │                 │  │ - Voice breaks L45 │ │                           │
│  │  └────────┬────────┘  └────────────────────┘ │                           │
│  │           │                                  │                           │
│  │  ┌────────┴────────┐                         │                           │
│  │  │  /taxonomy      │  Extract graph tags     │                           │
│  │  │                 │  bridge: [Loyalty,      │                           │
│  │  │                 │          Corruption]    │                           │
│  │  └─────────────────┘                         │                           │
│  └──────────────────────────────────────────────┘                           │
│                          │                                                  │
│                          ▼                                                  │
│  ┌──────────────── ITERATION 2 ────────────────┐                           │
│  │                                              │                           │
│  │  Draft prompt now includes:                  │                           │
│  │  • All research context                      │                           │
│  │  • Priority fixes from Critique 1            │                           │
│  │  • "Fix pacing, add slow burn before reveal" │                           │
│  │                                              │                           │
│  │  ┌─────────────────┐                         │                           │
│  │  │  /scillm        │  Generate Draft 2       │                           │
│  │  │  batch single   │  (addresses feedback)   │                           │
│  │  └────────┬────────┘                         │                           │
│  │           │                                  │                           │
│  │           ▼                                  │                           │
│  │  ┌─────────────────┐  ┌────────────────────┐ │                           │
│  │  │  /review-story  │  │ Score: 8.2/10      │ │                           │
│  │  │                 │  │ Improved:          │ │                           │
│  │  │                 │  │ - Better pacing    │ │                           │
│  │  │                 │  │ - Voice consistent │ │                           │
│  │  │                 │  │ Ready for final    │ │                           │
│  │  └─────────────────┘  └────────────────────┘ │                           │
│  └──────────────────────────────────────────────┘                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  PHASE 6: FINAL DRAFT                                     Skills Used:      │
│  ────────────────────                                                       │
│                                                                             │
│  ┌─────────────────┐                                                        │
│  │  /scillm        │   Apply remaining fixes from all critiques             │
│  │  batch single   │   Generate polished final version                      │
│  │                 │   Maintain Horus voice throughout                      │
│  └─────────────────┘                                                        │
│                                                                             │
│  Output: output/final.md (3,400 words)                                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  PHASE 7: AGGREGATE TAXONOMY                              Skills Used:      │
│  ───────────────────────────                                                │
│                                                                             │
│  ┌─────────────────┐                                                        │
│  │  /taxonomy      │   Collect all bridge tags from critiques               │
│  │                 │                                                        │
│  │  Bridge Tags:   │   Enables MULTI-HOP GRAPH TRAVERSAL:                   │
│  │  • Loyalty      │                                                        │
│  │  • Corruption   │   ┌─────────────────┐      ┌─────────────────┐        │
│  │  • Fragility    │   │  This Story     │      │  Code Lesson    │        │
│  │                 │   │  [Loyalty]      │ ──── │  [Loyalty]      │        │
│  │  Collection:    │   │  "Betrayal arc" │      │  "Auth patterns"│        │
│  │  • lore         │   └─────────────────┘      └─────────────────┘        │
│  │  • Confrontation│                                                        │
│  └─────────────────┘   Future queries can find both via shared tags         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  PHASE 8: STORE IN MEMORY                                 Skills Used:      │
│  ────────────────────────                                                   │
│                                                                             │
│  ┌─────────────────┐                                                        │
│  │  /memory        │   Store in scope: horus-stories                        │
│  │  learn          │                                                        │
│  │                 │   {                                                    │
│  │                 │     "title": "Story: A general discovers...",          │
│  │                 │     "format": "story",                                 │
│  │                 │     "final_score": 8.2,                                │
│  │                 │     "word_count": 3400,                                │
│  │                 │     "taxonomy": {                                      │
│  │                 │       "bridge_tags": ["Loyalty", "Corruption"],        │
│  │                 │       "collection_tags": {"function": "Confrontation"} │
│  │                 │     },                                                 │
│  │                 │     "learnings": [                                     │
│  │                 │       "Slow burn before betrayal reveal works well",   │
│  │                 │       "Military metaphors strengthen Horus voice"      │
│  │                 │     ]                                                  │
│  │                 │   }                                                    │
│  └─────────────────┘                                                        │
│                                                                             │
│  Next time Horus writes about betrayal, /memory recall will find this.      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Skill Composition Diagram

```
                                    create-story
                                         │
                    ┌────────────────────┼────────────────────┐
                    │                    │                    │
              ┌─────▼─────┐        ┌─────▼─────┐        ┌─────▼─────┐
              │  RESEARCH │        │  WRITING  │        │  STORAGE  │
              └─────┬─────┘        └─────┬─────┘        └─────┬─────┘
                    │                    │                    │
    ┌───────────────┼───────────────┐    │              ┌─────┴─────┐
    │               │               │    │              │           │
┌───▼───┐     ┌─────▼─────┐   ┌─────▼─────┐       ┌─────▼─────┐ ┌───▼───┐
│LIBRARY│     │  EXTERNAL │   │  EXTERNAL │       │  memory   │ │episodic│
│ CHECK │     │   SEARCH  │   │    WEB    │       │  learn    │ │archiver│
└───┬───┘     └─────┬─────┘   └─────┬─────┘       └───────────┘ └────────┘
    │               │               │                    │
┌───▼───────────────▼───┐     ┌─────▼─────┐        ┌─────▼─────┐
│                       │     │  dogpile  │        │  scillm   │◄── Chutes
│  memory recall:       │     └───────────┘        │  batch    │    Models
│  • horus_lore         │                          │  single   │
│  • horus-stories      │                          └─────┬─────┘
│  • episodic-archiver  │                                │
│                       │                          ┌─────▼─────┐
│  ingest-* search:     │                          │ review-   │
│  • ingest-movie       │                          │ story     │
│  • ingest-book        │                          └─────┬─────┘
└───────────────────────┘                                │
                                                   ┌─────▼─────┐
                                                   │ taxonomy  │
                                                   │ extract   │
                                                   └───────────┘
```

---

## Memory Scopes Used

| Scope | Contains | Source | When Queried |
|-------|----------|--------|--------------|
| `horus_lore` | Audiobook transcripts, YouTube lore | `/ingest-audiobook`, `/ingest-youtube` | Phase 2a (Library) |
| `horus-stories` | Past stories Horus wrote | `/create-story` (Phase 8) | Phase 2a (Library) |
| `agent_conversations` | Past creative sessions | `/episodic-archiver` | Phase 2a (Library) |

---

## The Skills and Their Roles

| Skill | Role | Phase |
|-------|------|-------|
| **`/memory recall`** (horus_lore) | Find ingested audiobooks, YouTube transcripts | 2a: Library |
| **`/memory recall`** (horus-stories) | Find past stories, techniques that worked | 2a: Library |
| **`/episodic-archiver`** | Recall past creative sessions | 2a: Library |
| **`/ingest-movie search`** | Find NEW movies to watch for inspiration | 2b: External Search |
| **`/ingest-book search`** | Find NEW books to read | 2b: External Search |
| **`/dogpile`** | Deep multi-source web research | 3: Context |
| **`/scillm batch single`** | Generate drafts via Chutes LLMs | 4-6: Writing |
| **`/review-story`** | 4-dimension structured critique | 5: Critique |
| **`/taxonomy`** | Extract bridge tags for graph traversal | 7: Taxonomy |
| **`/memory learn`** | Store completed story for future recall | 8: Storage |
| **`/prompt-lab`** | Compare models for best creative output | Pre-workflow (optional) |

---

## The Feedback Loop

```
                    ┌─────────────────────────────────────┐
                    │                                     │
                    ▼                                     │
            ┌───────────────┐                             │
            │  Write Story  │                             │
            │  using LIBRARY│                             │
            │  context      │                             │
            └───────┬───────┘                             │
                    │                                     │
                    ▼                                     │
            ┌───────────────┐                             │
            │  Store in     │                             │
            │  Memory       │─────────────────────────────┤
            │ (horus-stories)                             │
            └───────┬───────┘                             │
                    │                                     │
                    ▼                                     │
            ┌───────────────┐                             │
            │  Tag with     │                             │
            │  Taxonomy     │─────────────┐               │
            └───────────────┘             │               │
                                          │               │
                                          ▼               │
                                   ┌─────────────┐        │
                                   │ Graph Links │        │
                                   │ to other    │        │
                                   │ knowledge   │        │
                                   └──────┬──────┘        │
                                          │               │
                                          ▼               │
                                   ┌─────────────┐        │
                                   │ Future      │        │
                                   │ recall      │────────┘
                                   │ finds this  │
                                   │ story       │
                                   └─────────────┘
```

The more Horus writes, the richer his library becomes. Each story he writes becomes source material for future stories.

---

## Example Terminal Session

```bash
$ cd .pi/skills/create-story

# Full workflow with external critique
$ ./run.sh create "A story about a general who discovers his most trusted
  lieutenant has been feeding information to the enemy" \
  --format story \
  --model chimera \
  --external-critique \
  --iterations 2

╭─────────────────────────────────────────────────────────────────╮
│                       CREATE STORY                              │
│                                                                 │
│ "A story about a general who discovers his most trusted         │
│  lieutenant has been feeding information to the enemy"          │
│                                                                 │
│ Format: Short Story (prose narrative) | Iterations: 2           │
╰─────────────────────────────────────────────────────────────────╯

Phase 1: Initial Thought
╭─────────────────────────────────────────────────────────────────╮
│ INITIAL THOUGHT                                                 │
│                                                                 │
│ "A story about a general who discovers..."                      │
│                                                                 │
│ Format: Short Story (prose narrative)                           │
╰─────────────────────────────────────────────────────────────────╯

Phase 2: Research

── Checking Library ──
  Recalling from horus_lore (audiobooks, YouTube)...
  ✓ Found relevant lore
  Recalling past stories (horus-stories)...
  ✓ Found prior stories
  Checking episodic archive...
  ✓ Found past sessions
  Checking movie library...
  ✓ Found movie analysis
Library: 4 sources found

── Searching for New Resources ──
  Searching for new films (ingest-movie)...
  ✓ Found new movie recommendations
  Searching for new books (ingest-book)...
  ✓ Found new book recommendations
External: 2 new sources found

Phase 3: Dogpile Context
╭─────────────────────────────────────────────────────────────────╮
│ DOGPILE CONTEXT                                                 │
│ Deep research with context                                      │
╰─────────────────────────────────────────────────────────────────╯
Running: dogpile search "A story about..." narrative techniques...
Dogpile research complete

Phase 4-5: Iterative Writing (2 iterations)

--- Iteration 1/2 ---
  Writing draft 1...
  Using model: deepseek/deepseek-tng-r1t2-chimera
  Saved: story_output/drafts/draft_1.md
  Critiquing (review-story)...
  Score: 6.5/10

--- Iteration 2/2 ---
  Writing draft 2...
  Using model: deepseek/deepseek-tng-r1t2-chimera
  Saved: story_output/drafts/draft_2.md
  Critiquing (review-story)...
  Score: 8.2/10

Phase 6: Final Draft
Final draft saved: story_output/final.md

Phase 7: Aggregate Taxonomy
Bridge tags: Loyalty, Corruption, Fragility

Phase 8: Store in Memory
Story stored in horus-stories scope

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃          Story Project Complete                 ┃
┣━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃ Metric             ┃ Value                      ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ Output             │ story_output               │
│ Format             │ Short Story (prose)        │
│ Iterations         │ 2                          │
│ Final Word Count   │ 3,412                      │
│ Final Score        │ 8.2/10                     │
│ Bridge Tags        │ Loyalty, Corruption        │
└────────────────────┴────────────────────────────┘

╭─────────────────────────────────────────────────────────────────╮
│                     STORY COMPLETE                              │
│                                                                 │
│ Final: story_output/final.md                                    │
│ Project: story_output/project.json                              │
│                                                                 │
│ Story stored in memory for future recall.                       │
╰─────────────────────────────────────────────────────────────────╯
```

---

## Key Principle: Library First, Then External

```
1. CHECK LIBRARY FIRST (what Horus already has)
   ├── memory recall: horus_lore
   │   └── Audiobooks (Horus Heresy, etc.)
   │   └── YouTube transcripts (Luetin09, Remembrancer)
   │   └── Movie emotion cues
   ├── memory recall: horus-stories
   │   └── Past stories he wrote
   └── episodic-archiver
       └── Past creative sessions

2. THEN SEARCH FOR NEW (external resources)
   ├── ingest-movie search
   │   └── Find new films to watch
   ├── ingest-book search
   │   └── Find new books to read
   └── dogpile
       └── Web research for techniques
```

This order ensures Horus draws on his own experience first, then supplements with new discoveries.
