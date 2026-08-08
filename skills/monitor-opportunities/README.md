# monitor-opportunities

A nightly, human-in-the-loop pipeline that finds highly-targeted **jobs and consulting
prospects** for Graham Anderson (Principal AI Architect, Buffalo NY), tailors a
claim-bound resume for the top ones, learns each employer's application form, and tracks
the full opportunity lifecycle on a private board — **without ever auto-applying or
auto-sending anything.** The human transmits every application and every outreach.

## What it does each night (2 AM, via the scheduler)

1. **Discovers** opportunities: SAM.gov + LinkedIn (read-only capture of *your own*
   authenticated session), Greenhouse/Ashby ATS boards, and brave-search client research.
2. **Filters** to what fits: within 2 weeks, right role type/seniority, and mandate-relevant
   (agentic-compliance, document-extraction, agentic pipelines, verification) — relevance is
   matched by `/extract-entities` against a curated ArangoDB terms corpus, not regex.
3. **Tailors** a custom, approved-claim-bound resume for the top jobs and **captures the
   live ATS application form** so it can be prefilled — submit stays human-authorized.
4. **Tracks** every opportunity as an issue in the **private** repo
   `grahama1970/opportunities`, deduped and lifecycle-labeled, in two queues:
   `track:employment` and `track:consulting` (federal solicitations + commercial signals).
5. **Delivers** the morning report to `/memory` + a Buzz summary you can chat with.

## Guarantees (by design, enforced in code)

- **No auto-submit, no auto-send.** Applications are human-authorized; outreach drafts go
  to `/memory` and you transmit them.
- **Dead API → website fallback**, always (enforced + tested).
- **No fabricated claims** — resumes use only approved-claim wordings (test-enforced).
- **Private** — job-search data never touches the public repo.

## Rubric & evaluation

Ranking/evaluation follows **`best-practices-opportunities`** (the canonical rubric).
Behavior is gated by `/agentic-evals` (`fixtures/agentic_eval.json`) — including a live
nightly real-world case and an adversarial relevance-corpus case.

## Usage

```bash
./run.sh nightly                 # full nightly (discovery → tailor → track → deliver)
./run.sh run --out DIR           # the deterministic pipeline (needs browser evidence)
./run.sh tailor --posting ... --claims ... --out DIR   # one claim-bound resume
python scripts/load_vocabulary.py        # (re)load the terms corpus into /memory
python scripts/relevance_eval.py         # adversarial relevance eval
```

## Current state & honest gaps

See `docs/PROJECT_KNOWLEDGE.md`. The nightly is **operational and scheduled**. Written but
not yet live-proven: the per-opportunity `/tau` creator-reviewer evaluation loop,
mandate-first ranking, and the learned relevance classifier (label flywheel accumulating
toward the training threshold).
