# Handoff Report: Dogpile

**Timestamp**: 2026-07-27T19:08:00Z
**Active Agent**: Codex

## 1. Project Overview

- **Ecosystem**: Python skill in `agent-skills`.
- **Core Purpose**: Dogpile is the broad research lane for agents. It retrieves
  and synthesizes evidence from Brave, concurrent Brave question fan-out,
  GitHub, ArXiv, YouTube, Fetcher, optional RSS feeds, optional Wayback,
  optional Readarr/books, optional website ingestion, and optional
  credentialed enrichment APIs.
- **Runtime Contract**: `SKILL.md` is authoritative. `README.md` is the
  operator guide.
- **Model Boundary**: Tau owns model-backed query tailoring, ranking,
  synthesis, ambiguity checks, and reviewer loops. Dogpile project-agent
  workflows must not call SciLLM directly, though legacy adapter code still
  exists and is labeled migration work.

## 2. Current State (Doc-Code Alignment)

- **Documented Features**:
  - Perplexity retired and default-off; Brave question fan-out is the
    replacement.
  - Brave web/local uses free key by default.
  - Brave AI lanes require explicit project-agent request: `context`,
    `summarize`, or `web --summary-key`.
  - `BRAVE_API_KEY_PAID` is an explicit-spend key, not proof that Summarizer,
    Answers, or LLM Context entitlement exists.
  - Feeds, Wayback, Readarr, DARPA, website ingestion, and credentialed APIs are
    optional lanes with documented activation criteria.
  - Security repositories discovered through Dogpile must flow through
    `$github-search` isolated evaluation; do not run untrusted repo code on the
    host.
  - Dogpile research should store a structured JSON document in Memory
    collection `dogpile_research` when `/memory` is reachable.

- **Implemented Reality**:
  - `memory_integration.py` writes JSON docs to `_DOGPILE_COLLECTION =
    "dogpile_research"` through `/memory /store`.
  - `cli.py` calls `learn_research(...)` after a search and reports when Memory
    returns zero entries.
  - `dogpile_partial_results.json` remains the local fallback and incremental
    recovery surface.
  - `scripts/feature_channel_eval.py` now checks the documented Memory JSON
    projection and implementation hooks.

- **Drift/Misalignments**:
  - Full live Dogpile E2E was not rerun after the README/project-knowledge
    update. The narrow live Memory helper was exercised directly and stored one
    `dogpile_research` doc, but that is not the same proof as a full
    `./sanity.sh --live-e2e` run proving automatic storage from a complete
    search.
  - Brave LLM Context returned `HTTP 400 OPTION_NOT_IN_PLAN` in the latest live
    probe. Treat this lane as unavailable until entitlement changes.
  - Brave Summarizer returned `skipped_no_summary_key` for the live test query.
    Do not synthesize a Brave summary when no `summarizer.key` is returned.
  - Legacy direct SciLLM adapter paths remain in implementation. They are not
    the desired contract; migrate model work behind Tau when the stable adapter
    exists.

## 3. What is Working Well

- `./skills/dogpile/run.sh feature-eval` passes with 25/25 feature-channel
  contract checks.
- `./skills/dogpile/sanity.sh --quick` passes local module/import/CLI checks.
- `./skills/eval-skills/run.sh eval --skill dogpile` passes the standard skill
  eval wrapper.
- `python3 scripts/check_mock_evidence_claims.py` reports no mock/proof claim
  violations.
- Project-knowledge update synced to `/memory`: first update wrote 62 chunks;
  decision update wrote 63 chunks.
- Narrow live Memory helper proof stored and recalled Dogpile JSON research
  document key `9bc0a7dc266c742f`.
- Remote `origin/main` points to
  `acc431b988b8f2b99886d180bf3a04e2494df73e`.

## 4. What is Currently Broken

- **Failed Tests**: None from the latest focused proof set.
- **Known Issues**:
  - `skills/dogpile/sanity.sh --quick` warns that `cli.py` is 1354 lines, over
    the 500-line module guideline.
  - `dogpile_monolith.py` backup is missing; sanity reports this as a warning
    and it may be intentional.
  - LLM Context entitlement is not available on the current Brave account/key
    based on `OPTION_NOT_IN_PLAN`.
  - Summarizer/Answers entitlement remains unproven.
  - Full Tau provider DAG synthesis proof is still not covered by the
    deterministic feature eval.
- **Recent Regressions**: No recent Dogpile regression was observed in this
  handoff pass.

## 5. Next Steps

1. Run `./skills/dogpile/sanity.sh --live-e2e` after deciding the live-call
   budget is acceptable, and inspect the receipt for report generation,
   provider evidence, partial-results integrity, and Memory write behavior.
2. Add a live E2E receipt field for automatic `dogpile_research` Memory storage
   if it is not already captured, separating `memory_write_attempted`,
   `memory_write_stored_count`, and `memory_doc_key`.
3. Migrate remaining legacy direct SciLLM code paths behind Tau or explicitly
   keep them as migration-only checks.
4. Keep Brave AI lanes explicit-spend only. If the paid Brave plan changes,
   rerun `brave-search context` and `brave-search summarize` probes and update
   this handoff with the exact result.
5. Continue using `$github-search` plus Brave `site:github.com` fan-out for
   sparse security/tooling repository discovery, then isolate any untrusted repo
   checks before execution.

## 6. Project Context for Success

- **Key Files**:
  - `SKILL.md`: Dogpile operational contract.
  - `README.md`: Human/operator guide.
  - `cli.py`: main search orchestration, partial-results publisher, and
    post-search Memory learn hook.
  - `memory_integration.py`: prior-research recall and structured
    `dogpile_research` JSON storage.
  - `scripts/feature_channel_eval.py`: deterministic contract eval.
  - `scripts/live_e2e_sanity.py`: live full-search sanity harness.
  - `scripts/live_service_matrix_sanity.py`: live provider matrix harness.
  - `resources/security.yaml`: optional security/API source registry.
  - `config/feed_packs/*.yaml`: public RSS pack definitions.

- **Recent Changes**:
  - `acc431b98 Document Dogpile memory projection`: updated
    `PROJECT_KNOWLEDGE.md`, `README.md`, `SKILL.md`, and feature-channel eval
    for structured Memory JSON storage and current Tau/Brave policy.
  - `a1bfe6903 Add Brave context and GitHub freshness search guidance`: added
    Brave LLM Context/Summarizer commands, free-vs-paid key policy, and typed
    GitHub freshness/star filters.
  - `ad4fe17b9 Document dogpile Battle and DARPA research boundaries`: added
    Battle consumer limits, DARPA optional lane guidance, and related eval
    coverage.

- **Latest Proof Commands**:
  - `./skills/dogpile/run.sh feature-eval --out-dir /tmp/dogpile-readme-project-knowledge-memory-feature-eval-20260727T2135Z`
  - `./skills/dogpile/sanity.sh --quick`
  - `./skills/eval-skills/run.sh eval --skill dogpile --report-json /tmp/dogpile-readme-project-knowledge-memory-eval-final.json --report-md /tmp/dogpile-readme-project-knowledge-memory-eval-final.md`
  - `python3 scripts/check_mock_evidence_claims.py`
  - `PYTHONPATH=skills uv run --project skills/dogpile python - <<'PY' ... learn_research(...) ... PY`
  - `PYTHONPATH=skills uv run --project skills/dogpile python - <<'PY' ... recall_prior_research(...) ... PY`

- **Working Tree Notes**:
  - Generated untracked report directories and some `uv.lock` files are present
    from previous tool runs. They were intentionally not staged.
  - Commit only task-relevant tracked docs/eval changes unless the human asks
    to preserve generated reports in Git.
