# dogpile

> **Disciplines:** research-retrieval

![Dogpile card](../../docs/assets/project-cards/dogpile.webp)

Dogpile is the broad research lane for agents: search everything useful, keep
the citations, and report which providers were used, skipped, or degraded. It
combines web search, GitHub, ArXiv, YouTube, Wayback, source-specific helpers,
and Tau-owned synthesis so the final answer has traceable evidence instead
of a pile of uncited links.

Agents must treat [`SKILL.md`](SKILL.md) as the runtime contract. This README is
the human/operator guide.

## Use It For

| Need | Start here |
|---|---|
| Research a topic with citations | `./run.sh search "your query"` |
| Produce a browsable report | `./run.sh search "your query" --html-report` |
| Use a focused source preset | `./run.sh search "your query" --preset <name>` |
| Check all documented feature channels | `./run.sh feature-eval` |
| Check credentials without spending default quota | `./run.sh doctor` |
| Inspect recent provider failures | `python cli.py errors --json` |

## Source Model

| Source | Role |
|---|---|
| Brave Search | Primary fresh web search |
| Brave question fan-out | Concurrent natural-language web questions, replacing Perplexity |
| GitHub | Code, issues, pull requests, and repo evidence |
| ArXiv | Papers and research leads |
| YouTube | Video metadata and transcript-oriented leads |
| Context7 | Optional current library/API documentation for named code dependencies |
| Feed packs | Optional fresh security/code enrichment; public RSS packs need no API keys |
| Fetcher | Internal deep-fetch primitive after a URL is selected |
| Wayback | Optional archived pages when live pages drift |
| Readarr/books | Optional local long-form source discovery |
| Tau | Query expansion, ranking, synthesis, ambiguity handling, and reviewer loops |

Perplexity is retired. Dogpile records it as skipped/degraded and uses
concurrent Brave question searches instead. Project agents should not call
SciLLM or model providers directly from Dogpile; model-backed work belongs
behind Tau. Brave `web` and `local` use the free key by default. The paid Brave
key is used only when the caller explicitly requests `context`, `summarize`, or
`web --summary-key`; a paid key does not prove Summarizer, Answers, or LLM
Context entitlement.
Use Context7 only when a code-related question depends on current docs for a
known library or Context7 library ID:

```bash
./run.sh search "FastAPI dependency injection security scopes" \
  --with-context7 \
  --context7-library fastapi
```

Context7 requires `CONTEXT7_API_KEY`, is skipped by default, and does not prove
runtime behavior, exploitability, patch effectiveness, or repository safety.

## What It Writes

| Artifact | Purpose |
|---|---|
| Markdown report | Human-readable synthesis with citations |
| HTML report | Browsable version of the research bundle |
| Partial results | Recoverable source outputs when a run degrades |
| Memory research JSON | Automatic `/memory` document in `dogpile_research` with query, sources, synthesis, key URLs, topic tags, and taxonomy bridges when Memory is reachable |
| Provider status | What ran, skipped, failed, or timed out |
| Error records | Hints for fixing source or quota problems |

The Memory write is a structured JSON document, not only a Markdown note. If
`/memory` is unavailable, Dogpile must report the skipped/degraded Memory write
and preserve local partial results instead of treating the research as lost.

## Proof Discipline

- Prefer cited source snippets over unsourced synthesis.
- Report skipped providers explicitly.
- Preserve partial results when a source fails after other sources succeeded.
- Treat threat-intel feeds as enrichment by default; block or alert only with
  high-confidence environment-specific corroboration.
- Treat model-written synthesis as a summary, not a replacement for source
  evidence.
- Use Brave Search as the default web lane unless the contract says otherwise.
- Treat security repositories as untrusted code; validate through
  `$github-search` isolated evaluation before any Docker/Bubblewrap execution.

## Common Mistakes

| Mistake | Better move |
|---|---|
| Using one web search and calling it dogpile | Let the skill fan out and record provider status |
| Hiding skipped providers | Report skipped/degraded lanes in the output |
| Calling model/provider APIs directly | Route model work through Tau |
| Returning uncited prose | Keep citations attached to claims |
| Treating paid Brave key as summary proof | Request the summary lane explicitly, then report `skipped_no_summary_key` or `OPTION_NOT_IN_PLAN` honestly |
| Using Context7 for broad research | Use it only after a library/API target is known; use Brave/GitHub/ArXiv/YouTube for discovery |
| Running security repos on the host | Use `$github-search` isolated evaluation and only escalate to containers for bounded lab-safe checks |

## References

- [`SKILL.md`](SKILL.md) is the operational contract.
- [`resources/README.md`](resources/README.md) describes resource presets.
