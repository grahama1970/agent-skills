# Skill Triggers Index

Central reference for all skill trigger phrases. Edit triggers in each skill's `SKILL.md` frontmatter.

> **How it works:** Claude Code reads `SKILL.md` frontmatter and uses `description` + `triggers` to match user requests to skills.

---

## assess
**When user says:** "assess the project", "step back", "fresh eyes", "sanity check", "health check", "gap analysis", "project status", "what's working"

```yaml
# .agents/skills/assess/SKILL.md
triggers:
  - assess the project
  - assess this
  - assess this directory
  - assess this folder
  - reassess this
  - reassess the project
  - re-evaluate the project
  - step back and analyze
  - step back
  - take a step back
  - fresh eyes
  - big picture check
  - check alignment
  - does the code match the docs
  - what's working and what isn't
  - evaluate code quality
  - reality check
  - sanity check
  - health check
  - project health check
  - quick audit
  - project audit
  - gap analysis
  - status check
  - project status
  - take stock
```

---

## arxiv
**When user says:** "find papers on", "search arxiv", "look up research", "academic papers about", "recent papers on", "arxiv search", "use your arxiv tool"

```yaml
# .agents/skills/arxiv/SKILL.md
triggers:
  - find papers on
  - search arxiv
  - look up research
  - academic papers about
  - recent papers on
  - arxiv search
  - use your arxiv tool
```

---

## context7
**When user says:** "library documentation", "show me docs for", "API reference", "how to use this library", "latest docs for", "context7 lookup"

```yaml
# .agents/skills/context7/SKILL.md
triggers:
  - library documentation
  - show me docs for
  - API reference
  - how to use this library
  - latest docs for
  - context7 lookup
```

---

## fetcher
**When user says:** "fetch this URL", "download page", "crawl website", "extract content from", "get the PDF", "scrape this site", "retrieve document"

```yaml
# .agents/skills/fetcher/SKILL.md
triggers:
  - fetch this URL
  - download page
  - crawl website
  - extract content from
  - get the PDF
  - scrape this site
  - retrieve document
```

---

## memory (MEMORY FIRST)
**MANDATORY FIRST STEP:** Before any codebase scan, call `recall` to get context

**When user says:** "check memory", "recall", "have we seen this", "remember how we solved", "what did we learn", "save this lesson", "learn from this", "query memory first"

```yaml
# .agents/skills/memory/SKILL.md
triggers:
  - check memory
  - recall
  - have we seen this
  - remember how we solved
  - what did we learn
  - recall previous
  - save this lesson
  - learn from this
  - check memory for
  - have we seen this before
  - query memory first
```

**Memory First Contract:** Always call `recall` BEFORE scanning any codebase. Memory returns context that helps make better decisions. If `found=true`, apply solution. If `found=false`, review context then scan codebase. After solving, call `learn`.

---

## pdf-fixture
**When user says:** "create test PDF", "generate PDF fixture", "make sample PDF", "PDF for testing", "create PDF with tables"

```yaml
# .agents/skills/pdf-fixture/SKILL.md
triggers:
  - create test PDF
  - generate PDF fixture
  - make sample PDF
  - PDF for testing
  - create PDF with tables
```

---

## perplexity
**When user says:** "what's the latest", "current pricing", "recent news", "search the web", "fact check", "what's new in", "look up online", "research this topic", "paid search"

```yaml
# .agents/skills/perplexity/SKILL.md
triggers:
  - what's the latest
  - current pricing
  - recent news
  - search the web
  - fact check
  - what's new in
  - look up online
  - research this topic
  - paid search
```

---

## brave-search
**When user says:** "brave search", "search with brave", "brave web search", "brave local search", "local search", "find businesses near", "find restaurants near", "near me", "free search"

```yaml
# .agents/skills/brave-search/SKILL.md
triggers:
  - brave search
  - search with brave
  - brave web search
  - brave local search
  - local search
  - find businesses near
  - find restaurants near
  - near me
  - free search
```

---

## runpod-ops
**When user says:** "spin up GPU", "create RunPod", "terminate pod", "GPU instance", "provision server", "check pod status", "RunPod management"

```yaml
# .agents/skills/runpod-ops/SKILL.md
triggers:
  - spin up GPU
  - create RunPod
  - terminate pod
  - GPU instance
  - provision server
  - check pod status
  - RunPod management
```

---

## scillm
**When user says:** "batch LLM calls", "parallel completions", "prove mathematically", "formal verification", "Lean4 proof", "extract JSON from", "verify this claim"

```yaml
# .agents/skills/scillm/SKILL.md
triggers:
  - batch LLM calls
  - parallel completions
  - prove mathematically
  - formal verification
  - Lean4 proof
  - extract JSON from
  - verify this claim
```

---

## surf
**When user says:** "open browser", "click on", "fill form", "take screenshot", "navigate to", "automate browser", "browser automation", "read webpage"

```yaml
# .agents/skills/surf/SKILL.md
triggers:
  - open browser
  - click on
  - fill form
  - take screenshot
  - navigate to
  - automate browser
  - browser automation
  - read webpage
```

---

## youtube-transcripts
**When user says:** "get transcript", "transcribe video", "youtube transcript", "extract captions", "what does this video say", "get subtitles from", "youtube url text"

```yaml
# .agents/skills/youtube-transcripts/SKILL.md
triggers:
  - get transcript
  - transcribe video
  - youtube transcript
  - extract captions
  - what does this video say
  - get subtitles from
  - youtube url text
```

---

## code-review
**When user says:** "code review", "review this code", "get a patch", "fix this with copilot", "copilot review", "generate diff", "review request"

```yaml
# .agents/skills/code-review/SKILL.md
triggers:
  - code review
  - review this code
  - get a patch
  - fix this with copilot
  - copilot review
  - generate diff
  - review request
```

---

## distill
**When user says:** "distill this", "extract knowledge from", "remember this paper", "store this research", "chunk and learn"

```yaml
# .agents/skills/distill/SKILL.md
triggers:
  - distill this
  - extract knowledge from
  - remember this paper
  - store this research
  - chunk and learn
  - distill into memory
```

---

## qra
**When user says:** "extract QRA", "extract Q&A", "extract knowledge", "create Q&A pairs", "knowledge extraction", "generate questions from"

```yaml
# .agents/skills/qra/SKILL.md
triggers:
  - extract QRA
  - extract Q&A
  - extract knowledge
  - create Q&A pairs
  - knowledge extraction
  - generate questions from
```

---

## doc-to-qra
**When user says:** "convert to QRA", "document to QRA", "pdf to QRA", "remember this document", "learn from this pdf"

```yaml
# .agents/skills/doc-to-qra/SKILL.md
triggers:
  - convert to QRA
  - document to QRA
  - pdf to QRA
  - create QRA from
  - extract QRA from document
  - turn this into Q&A
  - make Q&A from this
  - remember this document
  - learn from this pdf
```

---

## skills-sync
**When user says:** "sync skills", "publish skills", "push skills", "pull skills", "update shared skills", "fanout skills"

```yaml
# .agents/skills/skills-sync/SKILL.md
triggers:
  - sync skills
  - publish skills
  - push skills
  - pull skills
  - update shared skills
  - fanout skills
```

---

## agent-inbox
**When user says:** "check your inbox", "check messages", "any pending messages", "agent sent you", "send message to", "inter-agent message"

```yaml
# .agents/skills/agent-inbox/SKILL.md
triggers:
  - check your inbox
  - check inbox
  - check messages
  - any messages
  - any pending messages
  - check for messages
  - agent sent you
  - sent you an issue
  - sent you a bug
  - address the bug
  - fix the issue from
  - message from agent
  - inter-agent message
  - send message to
  - send bug to
  - notify the agent
  - tell the other agent
  - cross-project message
  - pending issues
  - pending bugs
```

---

## treesitter
**When user says:** "parse this code", "extract functions", "list symbols", "what functions are in", "code structure"

```yaml
# .agents/skills/treesitter/SKILL.md
triggers:
  - parse this code
  - extract functions from
  - list symbols in
  - what functions are in
  - code structure
  - parse with treesitter
```

---

## Adding New Triggers

1. Edit the skill's `SKILL.md` frontmatter
2. Add phrases to the `triggers:` array
3. Update the `description:` field to include key phrases
4. Update this index file

**Example:**
```yaml
---
name: my-skill
description: >
  Do X and Y. Use when user says "do X", "perform Y", or "my-skill action".
triggers:
  - do X
  - perform Y
  - my-skill action
---
```
