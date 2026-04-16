# Mimic Feature Design

## Concept

The **Mimic Feature** allows create-paper to learn and replicate the writing style, structure, and conventions of exemplar papers from prestigious sources (MIT, Stanford, CMU, Berkeley, etc.).

## Workflow: Mimic-Driven Paper Generation

```
1. SELECT EXEMPLARS   → User chooses 2-3 target papers to mimic
2. DEEP ANALYSIS      → Extract structure, style, patterns
3. COLLABORATIVE EDIT → Agent proposes, user refines, iteratively
4. STYLE TRANSFER     → Apply learned patterns to project content
5. VALIDATION         → Compare generated vs. exemplar metrics
```

---

## Stage 1: Exemplar Selection (Human-Driven)

```bash
./run.sh mimic --select

# Interactive prompt:
Mimic Feature: Select Exemplar Papers
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Choose 2-3 papers whose style you want to mimic:

1. Provide arXiv IDs manually
2. Search for papers from prestigious sources
3. Use pre-curated collections

Your choice (1-3)?
> 2

Searching papers from: MIT, Stanford, CMU, Berkeley
Venue: ICSE, FSE, PLDI
Years: 2020-2025

[Shows 20 papers with citations, authors, venue]

Select 2-3 papers (comma-separated numbers):
> 1, 5, 12

Selected:
  [1] "A Theory of Compositional Systems" (MIT, PLDI 2024, 89 citations)
  [5] "Formal Verification of..." (Stanford, FSE 2023, 124 citations)
  [12] "Automated Reasoning in..." (CMU, ICSE 2022, 201 citations)

Download and analyze these papers? (y/n)
> y
```

---

## Stage 2: Deep Analysis (Automated + Human Validation)

The system performs **multi-level analysis** on selected exemplars:

### 2.1 Structure Extraction

```python
analyze_structure(exemplar_papers) -> {
    "section_order": ["Abstract", "Intro", "Background", "Method", "Eval", "Related", "Conclusion"],
    "subsection_depth": 2,  # e.g., 3.2.1 is max depth
    "intro_length": 1850,  # words
    "method_sections": ["Overview", "Algorithm", "Implementation"],
    "figure_placement": {
        "intro": 0,
        "method": 3,
        "eval": 4,
    },
}
```

### 2.2 Style Analysis

```python
analyze_style(exemplar_papers) -> {
    "voice": "active",  # vs. passive
    "tense": {
        "intro": "present",
        "method": "present",
        "eval": "past",
    },
    "transition_phrases": [
        "To address this challenge, we...",
        "Our key insight is that...",
        "The intuition behind this approach...",
    ],
    "technical_density": 0.42,  # ratio of technical terms
    "citation_density": {
        "intro": 0.8,  # citations per sentence
        "related": 2.1,
        "method": 0.3,
    },
}
```

### 2.3 Content Patterns

```python
analyze_content(exemplar_papers) -> {
    "intro_structure": [
        "Problem statement (2-3 sentences)",
        "Motivation with real-world example",
        "Existing limitations (1 paragraph)",
        "Our contribution (numbered list)",
        "Paper organization",
    ],
    "method_detail_level": "high",  # include algorithms, proofs
    "eval_metrics": ["precision", "recall", "time", "comparison_with_baselines"],
    "figure_captions": "verbose",  # detailed vs. minimal
}
```

### 2.4 Human Validation Gate

```
Analysis Summary of 3 Exemplar Papers
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Structure:
  - Standard order: Intro → Background → Method → Eval → Related → Conclusion
  - All use 2-level subsections (3.2 but not 3.2.1)
  - Method section split into: Overview, Core Algorithm, Implementation

Style:
  - Active voice dominates (87% of sentences)
  - Present tense for general claims, past tense for eval results
  - High citation density in intro (0.8 per sentence)

Content:
  - Intros start with concrete example, then generalize
  - Methods include formal notation + algorithm pseudocode
  - Evaluations compare against 3-4 baselines

Does this match the style you want to mimic? (y/n/refine)
> y

Should I apply all patterns, or select specific aspects?
(all/structure-only/style-only/custom)
> all
```

---

## Stage 3: Collaborative Generation (Iterative)

Generate paper **section-by-section** with human collaboration at EACH step.

### 3.1 Abstract (Mimic-Driven)

```
Generating Abstract (Mimicking: MIT PLDI 2024 style)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Applying patterns:
  ✓ Problem statement (2 sentences)
  ✓ Solution overview (1 sentence)
  ✓ Key technical contribution (1 sentence)
  ✓ Evaluation result (1 sentence)
  ✓ Active voice, present tense

Generated Abstract:
━━━━━━━━━━━━━━━━━━━━━━
Agent memory systems lack compositional reasoning capabilities,
limiting their ability to generalize across tasks. We present
a novel episodic memory architecture that enables compositional
recall through graph-based belief tracking. Our key insight is
that treating memories as composable graph nodes allows agents
to infer connections between unrelated episodes. We demonstrate
our approach on the pi-mono agent framework, achieving 34%
improved task success rate compared to flat memory baselines.
━━━━━━━━━━━━━━━━━━━━━━

Options:
a) Accept and continue
b) Regenerate with feedback
c) Manual edit
d) Compare side-by-side with exemplar

Your choice (a-d)?
> d

Side-by-Side Comparison:
━━━━━━━━━━━━━━━━━━━━━━

MIT Paper Abstract (exemplar):
  "Compositional program synthesis..."
  [Shows full abstract]

Your Generated Abstract:
  "Agent memory systems lack..."
  [Shows full abstract]

Differences:
  ✓ Similar length (120 vs. 118 words)
  ✓ Both use present tense
  ✗ Your abstract lacks quantitative result in opening
  ✗ Exemplar has stronger "gap" statement

Apply fixes? (y/n)
> y

Regenerating with fixes...

[New abstract with fixes]

Accept? (y/n)
> y
```

### 3.2 Introduction (Mimic + User Collaboration)

```
Generating Introduction Section
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Mimicking: Stanford FSE 2023 intro structure
  1. Concrete motivating example (1 paragraph)
  2. Problem generalization (1 paragraph)
  3. Limitations of existing work (1 paragraph)
  4. Our contributions (numbered list)
  5. Paper organization (1 paragraph)

Step 1/5: Concrete Motivating Example
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

I need your input:

Q: What's a real-world scenario that motivates your work?
   (Think: "User Alice wants to...", "System X fails when...")

Your answer:
> An agent managing a software project needs to recall
> how it fixed a similar bug 3 months ago, but current
> memory systems can't connect related but temporally
> distant episodes.

Good! Generating paragraph...

[Generated paragraph using that scenario]

Generated:
━━━━━━━━━━
Consider an agent managing a software project that encounters
a build failure. The agent previously fixed a similar issue
three months ago, but the solution is buried in thousands of
logged interactions. Current memory systems rely on recency
or keyword matching, failing to recognize that the old solution
shares structural similarity with the new problem despite
different surface-level symptoms.
━━━━━━━━━━

Accept / Regenerate / Edit?
> accept

Step 2/5: Problem Generalization
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Q: How does this example represent a broader challenge?

Your answer:
> Agents need compositional reasoning over episodic memory
> to connect related events across time.

[Generates paragraph... continues iteratively]
```

---

## Stage 4: Style Transfer (Automated + Validation)

Apply learned patterns to ALL sections:

```python
apply_style_transfer(generated_sections, learned_patterns):
    for section in generated_sections:
        # 1. Voice correction (passive → active)
        section = convert_passive_to_active(section)

        # 2. Tense alignment
        section = align_tense(section, patterns.tense[section.name])

        # 3. Transition phrases
        section = insert_transitions(section, patterns.transitions)

        # 4. Technical density adjustment
        section = adjust_technical_density(section, patterns.density)

        # 5. Citation insertion
        section = suggest_citations(section, patterns.citation_density)

        return section
```

**Human Validation:**

```
Style Transfer Complete
━━━━━━━━━━━━━━━━━━━━━━

Changes applied:
  ✓ Converted 12 passive voice sentences to active
  ✓ Aligned tense (intro: present, eval: past)
  ✓ Added 8 transition phrases matching exemplar style
  ✓ Adjusted technical density: 0.38 → 0.42
  ✓ Suggested 15 citation locations

Review changes? (y/quick/skip)
> quick

[Shows 3 example transformations]

Accept all changes? (y/n/custom)
> y
```

---

## Stage 5: Validation (Metrics-Driven)

Compare generated paper against exemplar metrics:

```
Validation Report: Generated vs. Exemplar
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Structure:
  ✓ Section order matches exemplar
  ✓ Subsection depth: 2 (target: 2)
  ✓ Intro length: 1820 words (target: 1850)
  ⚠ Method section: 2800 words (target: 3200)

Style:
  ✓ Active voice: 85% (target: 87%)
  ✓ Tense alignment: 94% (target: 95%+)
  ✓ Citation density (intro): 0.75 (target: 0.8)
  ⚠ Technical density: 0.39 (target: 0.42)

Content:
  ✓ Intro has concrete example
  ✓ Method includes algorithm pseudocode
  ✗ Evaluation compares 2 baselines (target: 3-4)

Recommendations:
  1. Expand method section by 400 words (add implementation details)
  2. Increase technical term usage by ~8%
  3. Add 1-2 more baseline comparisons in evaluation

Apply recommendations? (y/n/manual)
> y

[Regenerates affected sections with recommendations]
```

---

## Implementation: Mimic Command

Add to `paper_writer.py`:

```python
@app.command()
def mimic(
    select: bool = typer.Option(False, "--select", help="Select exemplar papers"),
    analyze: bool = typer.Option(False, "--analyze", help="Analyze selected exemplars"),
    exemplars: str = typer.Option("", help="Comma-separated arXiv IDs"),
):
    """
    Mimic the style of exemplar papers from prestigious sources.

    Workflow:
    1. ./run.sh mimic --select            # Choose exemplars interactively
    2. ./run.sh mimic --analyze           # Analyze selected papers
    3. ./run.sh draft --mimic             # Generate using mimic patterns
    """
    if select:
        exemplars = select_exemplar_papers()
        store_exemplars(exemplars)
    elif analyze:
        exemplars = load_exemplars()
        patterns = analyze_exemplars(exemplars)
        store_patterns(patterns)
    else:
        typer.echo("Use --select or --analyze")
```

---

## Key Features of Mimic

1. **Exemplar Curation**: Focus on MIT/Stanford/CMU/Berkeley + A\* venues
2. **Multi-Level Analysis**: Structure + Style + Content patterns
3. **Human Validation Gates**: User approves EACH pattern before application
4. **Iterative Collaboration**: Agent proposes, user refines, section-by-section
5. **Metrics-Driven**: Compare generated vs. exemplar quantitatively
6. **Style Transfer**: Apply patterns consistently across all sections

---

## Benefits

- **Quality**: Match publication standards of top-tier venues
- **Consistency**: Unified style throughout the paper
- **Efficiency**: Agent handles tedious formatting/style work
- **Learning**: User understands "what makes a good paper"
- **Customization**: Can mimic different styles for different venues

The Mimic Feature transforms create-paper from a basic orchestrator into a **publication-quality writing assistant** that learns from the best and collaborates closely with the user.
