---
name: create-paper
description: >
  Orchestrate paper writing from project analysis. Composes assess, dogpile, arxiv,
  and review-code skills. Interview-driven workflow with frequent human collaboration
  to resolve ambiguity and validate each stage.
allowed-tools: Bash, Read
triggers:
  - write paper
  - draft paper
  - generate paper
  - paper from project
  - research paper
metadata:
  short-description: Interview-driven academic paper generation from code
provides:
  - paper-generation
  - research-synthesis
composes:
  - assess
  - dogpile
  - arxiv
  - review-code
  - interview
  - scillm
  - memory
  - task-monitor
  - agentic-evals
taxonomy:
  - precision
  - resilience
  - validation
disciplines:
  - content-creation
  - research-retrieval
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Paper Writer Skill

Generate academic papers from project analysis through **interview-driven orchestration**.

---

## Implementation Status

> **Current State**: Core 5-stage workflow fully implemented with real skill integrations.

| Feature | Status | Notes |
|---------|--------|-------|
| **Stage 1: Scope Interview** | ✅ Implemented | Typer prompts + /interview skill integration |
| **Stage 2: Project Analysis** | ✅ Implemented | /assess + /dogpile + optional /review-code |
| **Stage 3: Literature Search** | ✅ Implemented | Full arxiv JSON parsing with relevance triage |
| **Stage 4: Knowledge Learning** | ✅ Implemented | /arxiv learn with progress tracking |
| **Stage 5: Draft Generation** | ✅ Implemented | Multi-template support, LLM-powered sections |
| **LLM Content Generation** | ✅ Implemented | /scillm batch single, stub fallback |
| **Memory Storage** | ⚠️ Partial | Attempts to call /memory |
| **Auto-generated Figures** | ✅ Implemented | /fixture-graph integration (Seaborn/Graphviz/Mermaid) |
| **Interview Skill Integration** | ✅ Implemented | Used in Stage 1 scope definition |
| **Iterative Refinement** | ✅ Implemented | `refine` command with LLM feedback loop |
| **MIMIC Feature** | ✅ Implemented | Exemplar paper style learning & transfer |
| **BibTeX Citations** | ✅ Implemented | Auto-generated from arxiv paper IDs |
| **RAG Grounding** | ✅ Implemented | Prevent hallucination with --rag flag |
| **Multi-Template** | ✅ Implemented | IEEE, ACM, CVPR, arXiv, Springer |
| **Citation Checker** | ✅ Implemented | Verify citations match BibTeX entries |
| **Quality Dashboard** | ✅ Implemented | Word counts, citation stats, warnings |
| **Academic Phrases** | ✅ Implemented | Section-specific phrase suggestions |
| **Aspect Critique** | ✅ Implemented | SWIF2T-style multi-aspect feedback |
| **Agent Persona** | ✅ Implemented | Horus Lupercal + custom persona.json support |
| **Venue Disclosure** | ✅ Implemented | LLM disclosure for arXiv, ICLR, NeurIPS, ACL, AAAI |
| **Citation Verifier** | ✅ Implemented | Detect hallucinated/missing references |
| **Weakness Analysis** | ✅ Implemented | Generate explicit limitations section |
| **Pre-Submit Check** | ✅ Implemented | Rubric-based submission checklist |
| **Claim-Evidence Graph** | ✅ Implemented | Jan 2026: BibAgent/SemanticCite pattern |
| **AI Usage Ledger** | ✅ Implemented | ICLR 2026 disclosure compliance |
| **Prompt Sanitization** | ✅ Implemented | CVPR 2026 ethics requirement |
| **Horus Paper Pipeline** | ✅ Implemented | Full Warmaster publishing workflow |

### All Core Features Complete

1. ~~Implement MIMIC feature~~ ✅ DONE - Exemplar paper style learning
2. ~~Add figure generation~~ ✅ DONE - /fixture-graph integration
3. ~~Iterative section refinement~~ ✅ DONE - `refine` command
4. ~~Multi-round review loop~~ ✅ DONE - via `critique` and `refine`
5. ~~Add RAG grounding~~ ✅ DONE - Use --rag flag
6. ~~Multi-template support~~ ✅ DONE - IEEE, ACM, CVPR, arXiv, Springer
7. ~~Citation checker~~ ✅ DONE - `quality` command
8. ~~Academic phrase palette~~ ✅ DONE - `phrases` command
9. ~~Agent persona integration~~ ✅ DONE - Horus Lupercal authoritative style

---

## Philosophy: Human-in-the-Loop

This skill does NOT automate away the researcher. Instead, it:

- **Asks clarifying questions** until ambiguity is resolved
- **Validates assumptions** before proceeding to next stage
- **Presents recommendations** for human approval/override
- **Iterates on feedback** rather than generating final output

Think of it as a research assistant that does the legwork but defers judgment to you.

---

## ⚡ Quick Start for Agents

**Don't get overwhelmed by 17+ commands!** Use domain navigation:

```bash
# List command domains by workflow stage
create-paper domains

# Filter commands by domain
create-paper list --domain generate    # Paper generation commands
create-paper list --domain verify      # Quality assurance commands
create-paper list --domain comply      # Venue compliance commands

# Get workflow recommendations based on paper stage
create-paper workflow --stage new_paper
create-paper workflow --stage pre_submission

# Show fixture-graph presets for figures
create-paper figure-presets
```

### Domain Quick Reference

| Domain | Commands | When to Use |
|--------|----------|-------------|
| `generate` | draft, mimic, refine, horus-paper | Starting new paper or revising |
| `verify` | verify, quality, critique, check-citations, weakness-analysis, pre-submit, sanitize | Before submission |
| `comply` | disclosure, ai-ledger, claim-graph | Meeting venue requirements |
| `resources` | phrases, templates | Looking up helpers |

### Agent JSON Output

All navigation commands support `--summary` for JSON output:

```bash
create-paper domains --summary          # JSON of all domains
create-paper workflow --stage new_paper --summary  # JSON recommendations
create-paper figure-presets --summary   # JSON of IEEE sizes + colormaps
```

---

## Workflow: 5 Stages with Interview Gates

```
1. SCOPE INTERVIEW    → Define paper type, audience, contribution claims
                         [GATE: User validates scope]

2. PROJECT ANALYSIS   → /assess + /dogpile + /review-code
                         [GATE: User confirms analysis accuracy]

3. LITERATURE SEARCH  → /arxiv search + triage
                         [GATE: User selects relevant papers]

4. KNOWLEDGE LEARNING → /arxiv learn on selected papers
                         [GATE: User reviews extracted knowledge]

5. DRAFT GENERATION   → LaTeX from analysis + learned knowledge
                         [GATE: User iterates on structure/content]
```

**Key principle**: Each `[GATE]` blocks until human approval. No stage proceeds with unresolved questions.

---

## Command: `draft`

```bash
./run.sh draft --project /path/to/project
```

Launches interactive paper drafting session.

### Interview Questions (Stage 1: Scope)

The skill asks:

**1. Paper Type**

```
What type of paper are you writing?
a) Research paper (novel contribution)
b) System paper (implementation/architecture)
c) Survey paper (literature review)
d) Experience report (lessons learned)
e) Demo paper (tool description)
```

**2. Target Venue**

```
Target venue/conference? (affects formatting and emphasis)
Examples: ICSE, FSE, ASE, PLDI, arXiv preprint
```

**3. Contribution Claims**

```
What are your 3-5 main contribution claims?
(e.g., "A novel agent memory architecture that...")
```

**4. Target Audience**

```
Who is the intended audience?
a) Software engineering researchers
b) AI/ML practitioners
c) Industry developers
d) Specific domain (e.g., formal methods)
```

**5. Prior Work Scope**

```
Should I search for related work in:
[x] Agent architectures
[ ] Memory systems
[ ] Tool use / function calling
[ ] Other (specify): ___________
```

**GATE**: User reviews and confirms scope. Proceeds only on explicit approval.

---


See [EXAMPLES.md](references/EXAMPLES.md) for a full example session, RAG grounding details, multi-template support, persona integration, and venue compliance features.

See [WORKFLOW.md](references/WORKFLOW.md) for detailed Stage 2-5 workflows, interview gates, and output structure.
