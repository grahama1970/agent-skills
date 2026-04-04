## Stage 2: Project Analysis

Orchestrates existing skills:

```bash
# 1. Static + LLM assessment
/assess run /path/to/project
   ├─ Features identified
   ├─ Architecture patterns
   ├─ Technical debt detected
   └─ [OUTPUT: assessment.json]

# 2. Deep research on key features
/dogpile search "feature X implementation patterns"
   ├─ ArXiv papers
   ├─ GitHub examples
   ├─ Documentation
   └─ [OUTPUT: research_context.md]

# 3. Code-paper alignment check
/review-code verify /path/to/project
   ├─ Code matches documentation?
   ├─ Claims supported by implementation?
   └─ [OUTPUT: alignment_report.md]
```

### Interview: Analysis Validation

Presents findings:

```
Project Analysis Summary:
━━━━━━━━━━━━━━━━━━━━━━━━
Core Features:
  1. Episodic memory with ArangoDB (250 LOC)
  2. Tool orchestration pipeline (180 LOC)
  3. Interview-driven interactions (120 LOC)

Architecture:
  - Event-driven with message passing
  - Skills as composable modules
  - Persistent storage layer

Detected Issues:
  ⚠ Hardcoded paths in 3 locations
  ⚠ Missing test coverage for memory skill

Does this match your understanding? (y/n/refine)
```

**GATE**: User confirms or refines analysis before proceeding.

---

## Stage 3: Literature Search

Uses `/arxiv search` with generated context:

```bash
# Automatically generates /tmp/arxiv_context.md from scope + analysis
# Then searches with domain-specific terms
/arxiv search -q "episodic memory agent systems" -n 20
```

### Interview: Paper Triage

Presents abstracts with recommendations:

```
Found 20 Papers - Triaging Against Your Contribution
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

HIGH RELEVANCE (Directly Related)
  [1] "Episodic Memory in Cognitive Architectures" (arXiv:2401.12345)
      → Describes memory structure similar to yours
      → RECOMMEND: Learn from this

  [2] "Tool Use in LLM Agents" (arXiv:2310.09876)
      → Framework for tool orchestration
      → RECOMMEND: Learn from this

MEDIUM RELEVANCE (Tangential)
  [3] "Retrieval-Augmented Generation" (arXiv:2312.54321)
      → Related but different architecture
      → SKIP unless you want broader context

LOW RELEVANCE (Different Problem)
  [4-20] ...

Which papers should I extract? (Enter numbers, 'all-high', or 'manual')
```

**GATE**: User selects papers. Can override recommendations.

---

## Stage 4: Knowledge Learning

Extracts from selected papers:

```bash
# For each selected paper:
/arxiv learn <id> --scope paper-writing --context-file /tmp/arxiv_context.md
```

### Interview: Knowledge Review

Shows extracted Q&A pairs before storing:

```
Extracted Knowledge from Paper [1]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Q: How should episodic memory be structured for agent recall?
A: Use time-indexed events with semantic embeddings. Store:
   - Event timestamp
   - Agent state snapshot
   - Action taken + rationale
   - Outcome observed

Q: What data structure best represents agent beliefs?
A: BDI (Belief-Desire-Intention) dictionary with confidence scores...

Accept these extractions? (y/n/refine)
```

**GATE**: User validates or refines extractions.

---

## Stage 5: Draft Generation

Generates LaTeX sections:

### Interview: Structure Review

```
Proposed Paper Structure
━━━━━━━━━━━━━━━━━━━━━━━

1. Abstract
   - Problem: Agent memory systems lack...
   - Solution: Interview-driven episodic memory
   - Results: Demonstrated on pi-mono project

2. Introduction
   - Motivation from /assess findings
   - Contribution claims from scope interview

3. Related Work
   - Episodic Memory (from learned papers)
   - Tool Orchestration (from learned papers)
   - Comparison table highlighting your differences

4. System Design
   - Architecture from /assess
   - Code examples from project

5. Implementation
   - Key features from analysis
   - Design decisions + rationale

6. Evaluation
   - Project statistics
   - Comparison with related systems

7. Discussion
   - Limitations from /review-code
   - Future work from aspirational features

Approve this structure? (y/n/custom)
```

**GATE**: User confirms or provides custom structure.

### Iterative Refinement

```
Draft section 1 (Abstract) ready. Options:
a) View draft
b) Regenerate with feedback
c) Accept and continue to next section
d) Manual edit
```

For each section, user can:

- Review generated text
- Provide feedback for regeneration
- Directly edit LaTeX
- Iterate until satisfied

---

## Output: Draft Paper

Final output structure:

```
paper_output/
├── draft.tex           # Main LaTeX file
├── sections/
│   ├── abstract.tex
│   ├── intro.tex
│   ├── related.tex
│   ├── design.tex
│   ├── impl.tex
│   ├── eval.tex
│   └── discussion.tex
├── figures/            # Auto-generated from /assess
│   ├── architecture.pdf
│   └── workflow.pdf
├── references.bib      # From learned papers
├── analysis/           # Supporting materials
│   ├── assessment.json
│   ├── research_context.md
│   └── alignment_report.md
└── metadata.json       # Paper metadata for /memory
```

---

## Integration with Existing Skills

| Stage          | Skill Called     | Purpose                       |
| -------------- | ---------------- | ----------------------------- |
| **Scope**      | (interview only) | Define paper parameters       |
| **Analysis**   | `/assess`        | Project feature extraction    |
|                | `/dogpile`       | Research context gathering    |
|                | `/review-code`   | Code-paper alignment          |
| **Literature** | `/arxiv search`  | Find related papers           |
| **Learning**   | `/arxiv learn`   | Extract knowledge from papers |
| **Draft**      | (internal LaTeX) | Generate paper sections       |
| **Storage**    | `/memory`        | Store paper metadata          |

All skill calls use **subprocess with error handling** - if a skill fails, the interview pauses and asks user how to proceed.

---

## Key Design Principles

1. **No Auto-Proceed**: Every stage blocks on human approval
2. **Ambiguity Resolution**: Ask questions until clarity achieved
3. **Recommendation + Override**: Suggest but defer to user judgment
4. **Transparent Process**: Show what skills are called and why
5. **Iterative Refinement**: Allow regeneration with feedback
6. **Graceful Failure**: Handle skill errors without crashing

---

See [EXAMPLES.md](EXAMPLES.md) for a full example session, RAG grounding details, multi-template support, persona integration, and venue compliance features.

---

# Generate ACM-formatted paper
./run.sh draft --project ./myproject --template acm

# List all templates
./run.sh templates

# Show template details
./run.sh templates --show cvpr
```

---

# Refine all sections with 2 rounds
./run.sh refine ./paper_output --rounds 2

# Refine specific section with feedback
./run.sh refine ./paper_output --section intro --feedback "Make it more concise"
```

Each round:
1. Shows current content preview
2. Prompts for feedback (or 'skip' to accept)
3. Generates automated critique (clarity, completeness)
4. LLM rewrites section addressing feedback + critique
5. Shows word count diff, asks for acceptance

---

# Critique all aspects
./run.sh critique ./paper_output

# Specific aspects
./run.sh critique ./paper_output --aspects clarity,rigor

# Single section with LLM
./run.sh critique ./paper_output --section eval --llm
```

### Aspects Evaluated

| Aspect | Description |
|--------|-------------|
| **clarity** | Clear writing, defined terms, logical flow |
| **novelty** | Contribution claims, differentiation from prior work |
| **rigor** | Sound methodology, baselines, statistical significance |
| **completeness** | All sections adequate, self-contained |
| **presentation** | Figures clear, formatting consistent |

Each aspect produces:
- Score (1-5)
- Specific findings
- Checklist items

---

# All phrases for a section
./run.sh phrases intro

# Specific aspect
./run.sh phrases intro --aspect motivation
./run.sh phrases eval --aspect results
```

### Available Sections & Aspects

| Section | Aspects |
|---------|---------|
| **abstract** | problem, solution, results |
| **intro** | motivation, gap, contribution, organization |
| **related** | category, comparison, positioning |
| **method** | overview, detail, justification |
| **eval** | setup, results, analysis |
| **discussion** | limitations, future, broader_impact |

Example phrases:
- "Despite significant advances in..., there remains a critical need for..."
- "Our key insight is that..."
- "Unlike prior work, our method..."

---

# Generate paper in Horus's authoritative voice
./run.sh draft --project ./myproject --persona horus

# Get Horus-style phrases
./run.sh phrases eval --persona horus
```

**Horus's Writing Style:**
- **Voice**: Authoritative, commanding, tactically precise
- **Tone**: Competent, subtly contemptuous of inadequate approaches
- **Structure**: Military precision, anticipates objections
- **Principles**: Answer first, technical correctness non-negotiable

**Characteristic Phrases:**
- "The evidence is unambiguous."
- "Prior approaches fail to address the fundamental issue."
- "The results leave no room for debate."
- "Our methodology achieves what lesser approaches could not."

**Forbidden Phrases** (never used):
- "happy to help", "as an AI", "I believe", "hopefully"

### Custom Personas

Load custom persona from JSON:

```bash
./run.sh draft --project ./myproject --persona /path/to/persona.json
```

**persona.json format:**
```json
{
  "name": "Custom Persona",
  "voice": "academic",
  "tone_modifiers": ["precise", "formal"],
  "characteristic_phrases": ["We demonstrate that...", "Our analysis reveals..."],
  "forbidden_phrases": ["I think", "maybe"],
  "writing_principles": ["Clarity first", "Evidence-based claims"],
  "authority_source": "Rigorous methodology"
}
```

---

# Generate arXiv disclosure
./run.sh disclosure arxiv

# Show ICLR policy notes
./run.sh disclosure iclr --policy

# Save to file
./run.sh disclosure neurips -o acknowledgements.tex
```

**Supported Venues:**

| Venue | Disclosure Required | Location |
|-------|---------------------|----------|
| arXiv | Yes | acknowledgements |
| ICLR | Yes (desk rejection risk) | acknowledgements |
| NeurIPS | Yes (method-level) | method section |
| ACL | Yes | acknowledgements |
| AAAI | Yes (if experimental) | paper body |
| CVPR | Yes | acknowledgements |

**Key Policy Notes (Oct 2025):**
- arXiv CS tightened moderation: review/survey papers need completed peer review
- ICLR 2026: Hallucinated references = desk rejection
- All venues: Authors responsible for content correctness

### Citation Verification

Prevent hallucinated references (critical for peer review):

```bash
# Check citations match BibTeX
./run.sh check-citations ./paper_output

# Strict mode (fail on issues)
./run.sh check-citations ./paper_output --strict
```

**Checks performed:**
- All `\cite{}` commands have matching .bib entries
- Recent papers (2023+) have URL/DOI
- No suspicious patterns (excessive "et al.", generic names)

### Weakness Analysis

Generate explicit limitations section (research shows LLMs miss weaknesses):

```bash
# Analyze paper for limitations
./run.sh weakness-analysis ./paper_output

# Include project analysis
./run.sh weakness-analysis ./paper_output --project ./my-project

# Save to file
./run.sh weakness-analysis ./paper_output -o sections/limitations.tex
```

**Categories analyzed:**
- Methodology assumptions/simplifications
- Evaluation baseline count (research suggests 3-4 minimum)
- Scope boundaries
- Test coverage (if project provided)
- Reproducibility and generalization

### Pre-Submission Checklist

Comprehensive validation before submission:

```bash
# Full pre-submit check
./run.sh pre-submit ./paper_output --venue iclr --project ./my-project

# arXiv-focused (default)
./run.sh pre-submit ./paper_output
```

**Checklist items:**
1. File structure (draft.tex, references.bib)
2. Required sections (intro, method, eval, conclusion)
3. Citation integrity (no missing/hallucinated)
4. LLM disclosure compliance (venue-specific)
5. Evidence grounding (code/figure references)

**Exit codes:**
- 0: Ready for submission
- 1: Critical issues found

---

## Complete Command Reference

| Command | Purpose |
|---------|---------|
| `draft` | Generate paper from project (5-stage workflow) |
| `mimic` | Learn/apply exemplar paper styles |
| `refine` | Iteratively improve sections with feedback |
| `quality` | Show metrics dashboard |
| `critique` | Multi-aspect feedback (SWIF2T-style) |
| `phrases` | Academic phrase suggestions |
| `templates` | List/show LaTeX templates |
| `verify` | Verify RAG grounding |
| `disclosure` | Generate venue-specific LLM disclosure |
| `check-citations` | Verify citations against BibTeX |
| `weakness-analysis` | Generate limitations section |
| `pre-submit` | Pre-submission checklist and validation |
| `claim-graph` | Build claim-evidence graph (Jan 2026) |
| `ai-ledger` | AI usage tracking for ICLR 2026 compliance |
| `sanitize` | Prompt injection defense (CVPR 2026) |
| `horus-paper` | Full Warmaster publishing pipeline |

---

# Step 1: Analyze the memory project
./run.sh draft --project /home/graham/workspace/experiments/memory \
               --persona horus \
               --rag \
               --template arxiv

# Step 2: Web research for related work (Horus has /surf access)
# Horus can use /surf to browse arXiv, GitHub, documentation

# Step 3: Generate limitations section
./run.sh weakness-analysis ./paper_output \
         --project /home/graham/workspace/experiments/memory

# Step 4: Pre-submission validation
./run.sh pre-submit ./paper_output \
         --venue arxiv \
         --project /home/graham/workspace/experiments/memory
```

### Horus's Skill Composition

| Skill | Horus's Usage |
|-------|---------------|
| `/assess` | Analyze project architecture and features |
| `/dogpile` | Deep research on related topics |
| `/arxiv` | Search and learn from academic papers |
| `/memory` | Store paper context for future sessions |
| `/review-code` | Verify code-paper alignment |
| `/surf` | Browse web for documentation, examples |
| `/create-paper` | Generate research papers in his voice |

### Horus Writing Principles (Academic Context)

When writing papers, Horus:

1. **Answers first** - States contributions directly, then elaborates
2. **Technical precision** - Every claim backed by evidence from code/experiments
3. **Anticipates objections** - Limitations section is thorough, not hidden
4. **Commands authority** - Writing is confident, not hedging
5. **No AI-speak** - Never uses "happy to help", "as an AI", "hopefully"

### Example Horus Paper Abstract

> Prior approaches to agent memory systems demonstrate troubling disregard for
> compositional reasoning—a fundamental deficiency that limits generalization
> across tasks. We present a knowledge graph architecture that addresses this
> inadequacy through graph-based belief tracking and Theory of Mind inference.
> Our implementation achieves 34% improved task success rate compared to flat
> memory baselines. The experimental results leave no room for debate regarding
> the superiority of structured episodic recall.

---

# Build claim-evidence graph
./run.sh claim-graph ./paper_output

# With verification
./run.sh claim-graph ./paper_output --verify

# Export to JSON
./run.sh claim-graph ./paper_output -o claims.json
```

**Support Levels:**
- **Supported**: Claim has 2+ citations
- **Partially Supported**: Claim has 1 citation
- **Unsupported**: Claim has no citations (⚠ review required)

### AI Usage Ledger (ICLR 2026 Compliance)

Track all AI tool usage for accurate disclosure:

```bash
# Show logged AI usage
./run.sh ai-ledger ./paper_output --show

# Generate disclosure statement from ledger
./run.sh ai-ledger ./paper_output --disclosure

# Clear ledger
./run.sh ai-ledger ./paper_output --clear
```

**Tracked Information:**
- Tool name (scillm, claude, gpt-4, etc.)
- Purpose (drafting, editing, citation_search)
- Section affected
- Prompt hash (for provenance, not full prompt)
- Output summary

### Prompt Injection Sanitization (CVPR 2026 Requirement)

CVPR 2026 explicitly treats hidden prompt injection as an ethics violation:

```bash
# Check for prompt injection
./run.sh sanitize ./paper_output

# Auto-fix detected issues
./run.sh sanitize ./paper_output --fix
```

**Detected Patterns:**
- "ignore previous instructions"
- "you are now" / "pretend to be"
- Zero-width characters
- White/hidden text in LaTeX
- System prompt markers

### Horus Paper Pipeline

The full Warmaster publishing workflow:

```bash
./run.sh horus-paper /home/graham/workspace/experiments/memory
```

**Persona Strength Parameter:**

Horus can modulate his voice for peer reviewers with `--persona-strength`:

| Strength | Tone | Use When |
|----------|------|----------|
| 0.0 | Pure academic | Conservative venues (Nature, Science) |
| 0.3 | Subtle hints | Peer review requires neutrality |
| 0.5 | Balanced | General arXiv preprints |
| 0.7 | Strong (default) | Authoritative but measured |
| 1.0 | Full Warmaster | Workshop papers, position pieces |

```bash
# Measured tone for peer review
./run.sh horus-paper ./project --persona-strength 0.5 --auto-run

# Full Warmaster intensity
./run.sh horus-paper ./project -s 1.0 --auto-run
```

*"I temper my voice for the peer reviewers. A tactical necessity." - Horus*

**Pipeline Phases:**

1. **Project Analysis**: `draft --persona horus --rag`
2. **Claim Verification**: `claim-graph --verify` + `check-citations --strict`
3. **Weakness Analysis**: `weakness-analysis --project`
4. **Compliance Check**: `sanitize` + `ai-ledger --disclosure` + `pre-submit`

**The Warmaster's Publishing Checklist:**
- [ ] All claims have evidence (claim-graph)
- [ ] No hallucinated citations (check-citations --strict)
- [ ] Limitations explicitly stated (weakness-analysis)
- [ ] No prompt injection (sanitize)
- [ ] AI usage disclosed (ai-ledger --disclosure)
- [ ] Pre-submission passed (pre-submit)

---

## Dependencies

- Python 3.10+
- LaTeX distribution (texlive or mactex)
- Existing skills: assess, dogpile, arxiv, review-code, memory
- interview skill (for HTML/TUI interview rendering)

---

## Sanity Check

```bash
./sanity.sh
```

Verifies:

- All dependent skills exist
- LaTeX is installed
- Python dependencies available
- Template files present
