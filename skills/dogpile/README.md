# dogpile

![Dogpile card](../../docs/assets/project-cards/dogpile.webp)

Dogpile is the broad research lane for agents: search everything useful, keep
the citations, and report which providers were used, skipped, or degraded. It
combines web search, GitHub, ArXiv, YouTube, Wayback, source-specific helpers,
and Scillm-backed synthesis so the final answer has traceable evidence instead
of a pile of uncited links.

Agents must treat [`SKILL.md`](SKILL.md) as the runtime contract. This README is
the human/operator guide.

## Use It For

| Need | Start here |
|---|---|
| Research a topic with citations | `./run.sh search "your query"` |
| Produce a browsable report | `./run.sh search "your query" --html-report` |
| Use a focused source preset | `./run.sh search "your query" --preset <name>` |
| Inspect recent provider failures | `python cli.py errors --json` |

## Source Model

| Source | Role |
|---|---|
| Brave Search | Primary fresh web search |
| GitHub | Code, issues, pull requests, and repo evidence |
| ArXiv | Papers and research leads |
| YouTube | Video metadata and transcript-oriented leads |
| Wayback | Archived pages when live pages drift |
| Scillm | Query expansion, ranking, synthesis, and ambiguity handling |

Perplexity is treated as a skipped or degraded lane when quota or access is not
available. Dogpile should report that status instead of pretending the source
was searched. It should not call Claude, Gemini, Codex, or other provider APIs
directly; LLM work goes through Scillm.

## What It Writes

| Artifact | Purpose |
|---|---|
| Markdown report | Human-readable synthesis with citations |
| HTML report | Browsable version of the research bundle |
| Partial results | Recoverable source outputs when a run degrades |
| Provider status | What ran, skipped, failed, or timed out |
| Error records | Hints for fixing source or quota problems |

## Proof Discipline

- Prefer cited source snippets over unsourced synthesis.
- Report skipped providers explicitly.
- Preserve partial results when a source fails after other sources succeeded.
- Treat model-written synthesis as a summary, not a replacement for source
  evidence.
- Use Brave Search as the default web lane unless the contract says otherwise.

## Common Mistakes

| Mistake | Better move |
|---|---|
| Using one web search and calling it dogpile | Let the skill fan out and record provider status |
| Hiding skipped providers | Report skipped/degraded lanes in the output |
| Calling provider APIs directly | Route model work through Scillm |
| Returning uncited prose | Keep citations attached to claims |

## References

- [`SKILL.md`](SKILL.md) is the operational contract.
- [`resources/README.md`](resources/README.md) describes resource presets.
