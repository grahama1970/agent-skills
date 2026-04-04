## Example Session

```bash
$ ./run.sh draft --project ~/pi-mono

[INTERVIEW] Paper Type?
> b (System paper)

[INTERVIEW] Target venue?
> ICSE 2026 Tool Demo

[INTERVIEW] Main contributions? (one per line, 'done' when finished)
> Interview-driven skill orchestration
> Episodic memory with ArangoDB
> Human-in-the-loop paper generation
> done

[INTERVIEW] Audience?
> a (Software engineering researchers)

[INTERVIEW] Prior work areas? (space-separated)
> agent-architectures memory-systems tool-use

[STAGE 1] Scope defined ✓

[STAGE 2] Running /assess on ~/pi-mono...
[STAGE 2] Found 15 features, 3 architectural patterns
[INTERVIEW] Analysis shows: [summary]. Accurate? (y/n/refine)
> y

[STAGE 2] Running /dogpile on: "Interview-driven skill orchestration"...
[STAGE 2] Found 12 related projects

[INTERVIEW] Analysis complete. Continue to literature search? (y/n)
> y

[STAGE 3] Generating arxiv context from scope...
[STAGE 3] Searching arxiv for: "agent memory BDI architecture"...
[STAGE 3] Found 20 papers

[INTERVIEW] 5 HIGH, 8 MEDIUM, 7 LOW relevance. Extract which?
> all-high

[STAGE 4] Extracting 5 papers... (this may take 5-10 min)
[STAGE 4] Extracted 47 Q&A pairs

[INTERVIEW] Review extractions? (y/quick/skip)
> quick

[STAGE 5] Generating draft structure...
[INTERVIEW] 7 sections proposed. Approve? (y/custom)
> y

[STAGE 5] Drafting Abstract...
[INTERVIEW] Abstract draft ready. (view/regen/accept)
> view

[Abstract text shown]

[INTERVIEW] Feedback for regeneration? (or 'accept')
> Make it more concise, emphasize novelty
> regen

[STAGE 5] Abstract regenerated.
[INTERVIEW] (view/accept)
> accept

[Continues for each section...]

✓ Draft complete: paper_output/draft.tex
  Compile with: cd paper_output && pdflatex draft.tex

[STAGE 6] Store paper metadata in memory? (y/n)
> y

✓ Paper draft session complete
```

---

## RAG Grounding

RAG (Retrieval-Augmented Generation) grounding prevents hallucination by ensuring all generated content is traceable to source material.

### Enabling RAG

```bash
./run.sh draft --project /path/to/project --rag
```

### How RAG Works

1. **Code Snippet Extraction**: Extracts function/class definitions from project
2. **Project Facts**: Compiles verified facts from analysis (features, LOC, patterns)
3. **Paper Excerpts**: Uses Q&A pairs from learned papers as grounding
4. **Research Facts**: Incorporates findings from dogpile research

### Grounding Constraints

Each section has specific constraints:

| Section | Constraints |
|---------|-------------|
| **Abstract** | Only mention features in project_facts |
| **Intro** | Contributions must map to specific features |
| **Related** | Every claim must cite paper_excerpts |
| **Design** | Architecture must match code_snippets |
| **Impl** | Code examples must be real excerpts |
| **Eval** | Metrics must be derived from sources |
| **Discussion** | Limitations from analysis issues |

### Verifying Grounding

```bash
./run.sh verify ./paper_output --project /path/to/project
```

Checks generated content for:
- Unsupported claims (novel, achieves, outperforms)
- Fabricated metrics
- Missing source attribution

---

## Multi-Template Support

Support for major academic venues:

| Template | Venue | Usage |
|----------|-------|-------|
| `ieee` | IEEE conferences (default) | `--template ieee` |
| `acm` | ACM conferences (SIGCHI, SIGMOD) | `--template acm` |
| `cvpr` | CVPR/ICCV/ECCV | `--template cvpr` |
| `arxiv` | arXiv preprints | `--template arxiv` |
| `springer` | Springer LNCS | `--template springer` |

```bash

## Iterative Refinement

The `refine` command enables section-by-section improvement with LLM feedback:

```bash

## Quality Dashboard

Comprehensive metrics and warnings:

```bash
./run.sh quality ./paper_output
./run.sh quality ./paper_output --verbose
```

Displays:
- Section word counts with targets
- Citation counts per section
- Figure/table/equation counts
- Citation checker (missing/unused BibTeX)
- Warnings for sections outside target ranges

### Section Word Targets

| Section | Min | Max |
|---------|-----|-----|
| Abstract | 150 | 250 |
| Intro | 800 | 1500 |
| Related | 600 | 1200 |
| Design | 800 | 1500 |
| Impl | 600 | 1200 |
| Eval | 800 | 1500 |
| Discussion | 400 | 800 |

---

## Aspect Critique (SWIF2T-style)

Multi-aspect feedback system inspired by SWIF2T research:

```bash

## Academic Phrase Palette

Section-specific academic writing suggestions:

```bash

## Agent Persona Integration

Write papers in a specific agent's voice for consistent style and authority.

### Built-in Persona: Horus Lupercal

```bash

## Venue Policy Compliance (2024-2025)

Based on dogpile research into current venue policies:

### Venue Disclosure Generator

Generate LLM-use disclosure statements compliant with venue policies:

```bash

## Jan 2026 Cutting-Edge Features (from dogpile research)

These features are based on January 2026 academic policy changes and state-of-the-art research.

### Claim-Evidence Graph (BibAgent/SemanticCite Pattern)

Link every claim to its evidence sources for peer review defense:

```bash

## Horus Lupercal: Research Paper Workflow

Horus has access to all skills in `/home/graham/workspace/experiments/pi-mono/.pi/skills` and can compose them to write research papers about his projects.

### Example: Writing a Paper on the Memory Project

```bash
