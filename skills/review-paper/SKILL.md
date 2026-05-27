---
name: review-paper
description: >
  Review papers for AI-generation signals, humanization scoring, persona-section alignment,
  and LLM-powered section-level quality assessment. Deterministic diagnostics detect low
  burstiness, transition overuse, buzzword clustering, and flat epistemic stance. LLM layer
  scores accuracy, voice, completeness, clarity, and humanness per section.
allowed-tools: [Bash, Read, Write, Task, Glob, Grep]
triggers:
  - review paper
  - review document
  - review docs
  - review documentation
  - paper review
  - doc review
  - critique paper
  - humanize paper
  - check if paper sounds AI generated
  - AI detection paper
  - review technical writing
  - persona review docs
  - check documentation quality
  - paper diagnostics
  - humanization score
metadata:
  short-description: Paper review with humanization scoring and LLM-powered section analysis
  version: "1.0.0"

provides:
  - review-paper
composes:
  - scillm
  - task-monitor

taxonomy:
  - validation
  - documentation
  - quality-assessment
---

## Standard Review Iteration Parameters

This `review-*` skill follows the shared contract in
`skills/.system/review-iteration-contract.md`.

Canonical parameters:

- `--max-rounds N`
- `--output-dir PATH`
- `--ask-gate`
- `--ask-model MODEL` (default `gpt-5.5`)
- `--ask-reasoning LEVEL` (default `high`)
- `--ask-timeout SECONDS`
- `--ask-focus LABELS`

When `--max-rounds > 1` is supplied, the skill must behave as a bounded
gate-producing controller or fail closed if that mode is not implemented. The
canonical gate artifact is `review_result.json` with verdict
`PASS`, `NEEDS_CHANGES`, `BLOCKED`, or `INSUFFICIENT_EVIDENCE`.

# review-paper

Review papers for AI-generation signals, persona-section alignment, and section-level quality.
Two layers: deterministic diagnostics (always runs) and LLM-powered review (interactive or batch).

## What It Detects

### Humanization Scoring (deterministic)

Scores 0-1 (higher = more human). Checks for:

- **Low sentence burstiness** — AI writes uniform sentence lengths (stddev < 4)
- **Uniform paragraph lengths** — AI paragraphs cluster around the same word count
- **Low lexical diversity** — repetitive vocabulary (diversity < 0.35)
- **Transition overuse** — "furthermore", "moreover", "in addition" appearing 3+ times
- **Repeated paragraph openings** — same 3-word start across paragraphs
- **Flat epistemic stance** — no hedging or certainty markers
- **Excessive certainty** — "clearly", "obviously", "definitely" overuse
- **Buzzword clustering** — "leverages", "paradigm", "unprecedented", "synergy"
- **Missing section-purpose elements** — abstract without "contribution", methods without "procedure"

### Persona-Section Alignment (deterministic)

4-dimensional scoring when persona profiles are provided:

| Dimension | What It Measures |
|-----------|-----------------|
| Style alignment | Preferred vs discouraged markers |
| Rhetorical alignment | Persona rhetorical preferences present |
| Epistemic alignment | Hedging density matches persona target |
| Section fitness | Persona affinity for section type |

Cross-persona consistency detects stylistic fragmentation across adjacent sections.

### LLM Section Review (interactive or batch)

Scores each section 0-10 across 5 dimensions:

| Dimension | Weight | What It Checks |
|-----------|--------|---------------|
| Accuracy | 30% | Technical claims correctness |
| Voice | 25% | Persona voice consistency |
| Completeness | 25% | Missing content, gaps |
| Clarity | 15% | Prose quality, readability |
| Humanness | 5% | AI-generation signals |

Also flags contradictions, buzzwords, and generates rewrite suggestions.

## Two LLM Modes

| Mode | When | LLM Source |
|------|------|------------|
| **Interactive** | Single paper via `review` | Calling agent (Claude/Pi) processes prompts in-context |
| **Batch** | Corpus via `batch --llm` | scillm/Chutes for cheap parallel completions |

Interactive mode generates structured review prompts and returns them to the calling agent.
The agent has full context (persona manifests, prior reviews, code files) — it IS the reviewer.

Batch mode uses scillm for throughput when reviewing many papers. Cheaper but no project context.

## Commands

### `review` — Full review with LLM prompts

```bash
./run.sh review paper.md                          # Interactive: report + LLM prompts
./run.sh review paper.md --headless                # JSON output for /paper-lab
./run.sh review paper.md --personas personas.yml   # With persona profiles
./run.sh review paper.md --json-out diag.json      # Save diagnostics JSON
./run.sh review paper.md --report-out report.md    # Save markdown report
```

In interactive mode, outputs the deterministic report then prints structured LLM review
prompts for the calling agent to process and return JSON responses.

In headless mode (`--headless`), outputs a single JSON object containing diagnostics,
humanization, persona alignment, revision plan, AND `review_prompts` dict for the
calling agent to process in a convergence loop.

### `diagnose` — Deterministic metrics only

```bash
./run.sh diagnose paper.md                         # Quick: no LLM, fast
./run.sh diagnose paper.md --json-out diag.json
```

### `improve` — Review + normalized rewrite

```bash
./run.sh improve paper.md                          # Writes paper.normalized.md
./run.sh improve paper.md --rewrite-out clean.md   # Custom output path
./run.sh improve paper.md --allow-fact-changes      # Allow content changes
```

### `batch` — Corpus-level review

```bash
./run.sh batch papers.txt                          # Deterministic only
./run.sh batch papers.txt --llm                    # With scillm LLM review
./run.sh batch papers.txt --json-stream            # NDJSON per item
./run.sh batch papers.txt --no-task-monitor        # Skip task-monitor
./run.sh batch papers.txt --output-dir results/    # Custom output dir
```

## Headless Mode (for /paper-lab)

When invoked with `--headless`, output is structured JSON suitable for convergence loops:

```json
{
  "diagnostics": { "sentence_mean": 18.2, "sentence_stddev": 3.1, ... },
  "humanization": { "humanization_score": 0.65, "ai_signals": [...], ... },
  "persona_alignment": [...],
  "revision_plan": [...],
  "review_prompts": {
    "system": "You are a meticulous academic paper reviewer...",
    "section:Introduction": "Review this paper section...",
    "section:Methods": "..."
  }
}
```

The calling agent processes each prompt, returns JSON, and the results are parsed via
`parse_section_review()` and `merge_llm_reviews()`.

## Persona Profiles

Supply persona profiles via `--personas personas.yml`:

```yaml
introduction:
  name: "problem-framing strategist"
  preferred_markers: ["challenge", "gap", "limitation"]
  discouraged_markers: ["revolutionary", "unprecedented"]
  hedging_target: medium
  section_affinity:
    introduction: 0.95
    methods: 0.4
```

## Output Report

The markdown report includes:
1. **Humanization Score** (0-1) with AI/human signal lists
2. **Diagnostics Summary** (burstiness, diversity, hedge/certainty density)
3. **LLM Section Reviews** (table with per-dimension scores, when available)
4. **Persona Alignment** (per-section 4D scores)
5. **Cross-Persona Consistency**
6. **Revision Plan** (prioritized action items)

## Integration

| Skill | How |
|-------|-----|
| `/paper-lab` | Drives convergence loop: review → delta → fix → review |
| `/create-paper` | Calls review-paper as quality gate after drafting |
| `/scillm` | Batch LLM calls for corpus-level review |
| `/task-monitor` | Progress tracking for batch operations |

## Future Work

- Memory integration (recall prior reviews, learn findings)
- Doc-code alignment (`--verify-code`)
- Multi-provider review routing (Claude for voice, Codex for accuracy)
- Named persona reviewers (Embry/Brandon/Margaret/Jennifer)
- Cross-reference validation
- Equation grounding
- Figure-text alignment
