---
name: review-readme
description: >
  Read-only, evidence-based adjudication of README.md files for onboarding,
  usage, and maintenance quality. Composes $ask webkimi for prose/voice/flow
  review with deterministic T0 checks. Use when asked to review, audit, validate,
  or critique a README. Does not edit the repository unless explicitly instructed.
triggers:
  - review readme
  - readme review
  - audit readme
  - validate readme
  - critique readme
  - /review-readme
allowed-tools: [Bash, Read, Glob, Grep]
provides:
  - readme-review-report
  - review_result.json
composes:
  - ask
  - surf
read_before_use:
  - review_readme.py
  - references/readme_review_rubric.md
metadata:
  short-description: Adjudicate README quality (read-only)
  version: "0.1.0"
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE RUNNING.

# /review-readme

Review a `README.md` as a **technical onboarding, usage, and maintenance** document.

This skill **adjudicates** README quality. It does **not** edit the repository unless the human explicitly asks for edits. Keep review separate from `/repair-readme` or `/write-readme` (future companions).

## Primary command

```bash
./run.sh README.md --kimi-tab-id <chrome_tab_id>
```

### Options

| Flag | Purpose |
|------|---------|
| `--audience "…"` | Target reader (default: competent developer or agent new to the project) |
| `--goal "…"` | Reader goal (default: understand, install/run, know next steps) |
| `--domain "…"` | Technical domain context for the oracle |
| `--check-implementation` | Ask oracle to judge implementation accuracy (source not inlined by default) |
| `--prereq-doc "…"` | Prerequisite doc name or path (context only) |
| `--strict` | Elevate missing structural sections to HIGH in T0 |
| `--max-rounds N` | Bounded cycles (default 1; use 2–3 for convergence workflows) |
| `--output-dir PATH` | Gate artifacts directory |
| `--kimi-tab-id ID` | **Required** for webkimi (authenticated Kimi tab in Chrome) |
| `--ask-timeout SEC` | Oracle timeout (default 900) |
| `--skip-oracle` | T0 deterministic checks only |
| `--json` | Emit `review_result.json` on stdout |

## Default assumptions

- **Audience:** competent developer or technical agent new to the project.
- **Goal:** understand the project, install or run it, know what to do next.
- **Mode:** adjudication-only; repository edits forbidden.
- **Evidence:** README text first; implementation files only when requested or necessary.

## Pipeline

```
T0 deterministic checks
  → build readme_review_bundle.md (rubric + README inlined)
  → $ask webkimi --once (single path in question for auto-attach)
  → parse VERDICT + write review_result.json
  → exit 0 on PASS, nonzero otherwise
```

### Bounded iteration (usually 2–3 rounds)

`--max-rounds N` is a **controller**, not automatic rewriting:

1. Round 1: review current README → `NEEDS_CHANGES` + `next_iteration_plan`.
2. Human or project agent applies revisions to the README.
3. Round 2+: re-run `/review-readme` (same flags). Each round rebuilds the bundle from disk.

If the README **mtime is unchanged** between rounds in one invocation, the controller stops early (`readme_unchanged_between_rounds`) so the oracle is not asked to re-judge identical text.

For multi-round **dialogue on the same Kimi tab**, the project agent may instead run sequential `$ask webkimi` calls with an updated bundle and prior executive summary (this skill inlines prior summary when `round > 1` in a single invocation).

## Web oracle rules (non-negotiable)

WebKimi cannot read the filesystem. The skill:

- Inlines rubric + README into `readme_review_bundle.md`.
- Puts **only the bundle path** in the `$ask` question for auto-attach.
- Avoids `$skill` shorthand and bare local paths in the **question text** (paths inside the README body are fine).

Capacity-busy Kimi messages are handled by `/ask` retry (`ASK_KIMI_CAPACITY_RETRIES`, default 3).

## Review dimensions

See `references/readme_review_rubric.md` for the full rubric and required oracle output template:

1. Reader contract  
2. Clarity  
3. Implementation accuracy (optional)  
4. Contradictions  
5. Missing instructions  
6. Voice and trust  
7. Flow  

Severities: `BLOCKER`, `HIGH`, `MEDIUM`, `LOW`, `INFO`.

## Gate artifact

`review_result.json` schema `review_readme.gate.v1`:

- Verdict: `PASS`, `NEEDS_CHANGES`, `BLOCKED`, or `INSUFFICIENT_EVIDENCE`
- T0 findings, ask artifacts, `next_iteration_plan`
- Per-round artifacts under `round-N/`

## Verdict policy

- **PASS** — usable, accurate, complete enough for the intended audience.
- **NEEDS_CHANGES** — important gaps or clarity issues.
- **BLOCKED** — missing file, capacity busy, or T0 blocker.
- **INSUFFICIENT_EVIDENCE** — oracle response missing parseable `VERDICT:` line.

T0 **HIGH** findings can override an oracle `PASS`.

## Guardrails

- Do not rewrite the README unless explicitly asked.
- Do not invent implementation behavior.
- Distinguish README evidence from implementation evidence.
- Prefer actionable findings over broad prose.
- Do not reward attractive formatting without operational truth.

## Composing /ask to author this skill

Yes: you can start from a spec like this document and use `$ask` (webgpt or webkimi) in **2–3 collaboration rounds** to draft or refine `SKILL.md` and the rubric — same bounded iteration pattern as README review itself. Runtime execution remains **coded** in `review_readme.py` (loops, bundles, gates), not agent-improvised.

## Examples

```bash
# Full gate with Kimi
./run.sh ../surf/README.md --kimi-tab-id 837344521 --max-rounds 3

# Strict T0 + oracle
./run.sh ./README.md --kimi-tab-id 837344521 --strict

# Deterministic only (CI / offline)
./run.sh ./README.md --skip-oracle --json
```
