---
name: resume
description: >
  Maintain a canonical Markdown resume and create claim-bound, evidence-referenced
  resume variants for a specific opportunity. Use when the user asks to update a
  resume, validate resume links, tailor a resume, create a resume PDF handoff, or
  prepare resume artifacts for /monitor-opportunities.
triggers:
  - update my resume
  - validate my resume
  - tailor my resume
  - create a targeted resume
  - create a resume PDF
  - prepare resume artifacts
  - resume for this opportunity
  - resume handoff
provides:
  - canonical-resume-validation
  - claim-bound-resume-tailoring
  - resume-artifact-handoff
composes:
  - handoff
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
taxonomy:
  - precision
  - validation
  - human-in-the-loop
metadata:
  short-description: Canonical resume validation and evidence-bound tailoring
  author: Graham Anderson
runtime_self_improvement: basic
---

# Resume

This skill owns resume artifacts; it does not discover opportunities, send outreach,
submit applications, or invent claims. `/monitor-opportunities` composes this skill
when it needs a per-opportunity resume artifact.

## Source of truth

- Human-edited baseline: repository `RESUME.md`.
- Generated PDF: `docs/resume/graham-anderson-resume.pdf`, produced by the repository
  resume workflow.
- Per-opportunity output: an explicitly named directory supplied to `tailor`.
- Claim evidence: an input JSON document containing approved claims and evidence refs.

Never edit the generated PDF by hand. Validate the Markdown source first, then use the
repository's converter or workflow to regenerate the PDF.

## Commands

```bash
./run.sh validate /path/to/RESUME.md
uv run --project . python scripts/competencies.py report
uv run --project . python scripts/competencies.py match /path/to/posting.txt
uv run --project . python scripts/competencies.py scan /path/to/posting.txt --resume RESUME.md
uv run --project . python scripts/screening_audit.py support
uv run --project . python scripts/screening_audit.py surfaces https://grahama.co
./run.sh tailor /path/to/RESUME.md /path/to/tailoring-request.json \
  --output-dir /path/to/resume-variant
./sanity.sh
```

`validate` checks that the source exists, is non-empty, contains a top-level heading,
and contains no unresolved placeholder markers. `tailor` preserves the source, selects
only approved claims with at least one evidence reference, writes a Markdown variant,
and emits `resume-variant.json` with hashes and a producer-side seam receipt.

## Competency evidence

Resumes get customised per employer, so "which competencies do I lead with for
this posting?" is a repeated question. `competencies.py` answers it from
`skills/project-taxonomy/references/disciplines.yml` — the canonical closed
18-discipline vocabulary and its explicit, fail-closed per-skill mapping. It
never re-derives or guesses a discipline, so every competency claim is backed
by a countable set of named skills.

- `report` ranks demonstrated competencies by skill count and cites examples.
- `match POSTING` ranks them by term overlap with a real job posting and names
  which to lead with, weighted by how much evidence backs each one.
- `scan POSTING --resume FILE --floor N` is the pre-send gate: it takes the
  requirement terms from that client's posting, checks whether the resume
  actually says them, and exits non-zero below the coverage floor. Missing terms
  are split into ones the skills catalog can back — safe to add — and ones it
  cannot, which must not be claimed. Run it before every send.

## Screening audit

A resume is read by software before a person sees it. `screening_audit.py`
checks the two structural things 2026 screening stacks reject on, neither of
which is about whether the work was real:

```bash
uv run --project . python scripts/screening_audit.py support
uv run --project . python scripts/screening_audit.py surfaces https://grahama.co
```

- `support` fails if a declared competency never appears in the experience text.
  A skills list naming capabilities the bullets do not demonstrate reads as
  padding, and Workday's AI layer flags it hardest. Web-only sections are
  excluded from evidence, because a PDF screener never sees them.
- `surfaces` fetches what a crawler or agent gets cold: `robots.txt`,
  `sitemap.xml`, `llms.txt`, the resume page, PDF, Markdown, and the homepage
  schema.org `Person`. Public surfaces that disagree read as a verification risk.

Both exit non-zero on failure, so either can gate a send. Neither judges whether
the resume is good — only that it cannot be dismissed for a structural reason.

`match` reports what a posting actually says. It models no employer's private
ranking system, and it is deterministic term overlap, not semantic matching.

## Claim safety

Tailoring is presentation work, not fact generation. The request must provide:

- `opportunity_id` and `target_title`;
- optional `target_terms` for a short, non-claim keyword section;
- `claims`, each with `claim_key`, `text`, `approved`, and `evidence_refs`;
- `claim_keys`, selecting only records from `claims`.

The command exits non-zero when a selected claim is missing, unapproved, empty, or
unsupported by evidence. It does not call an LLM and it does not modify external
systems.

## Composition with `/monitor-opportunities`

`/monitor-opportunities` remains responsible for discovery, ranking, opportunity
schemas, human review, and application/outreach gates. It passes an approved claim
snapshot to this skill, consumes `resume-variant.json`, and carries the emitted digest
and `claim_refs` into its report and application packet. The candidate remains the
sender and application authorizer.

## Anti-patterns

- Do not edit `docs/resume/graham-anderson-resume.pdf` directly.
- Do not select an unapproved claim or a claim without evidence refs.
- Do not use this skill to research jobs, contact people, submit applications, or
  infer proprietary ATS ranking logic.
- Do not treat a local smoke result as proof of PDF visual quality or live integration.

## Handoff

After creating or materially changing this skill, run the handoff skill from the
repository root so the next agent receives current project context:

```bash
bash skills/handoff/run.sh
```

The resulting `local/HANDOFF.md` is operational context, not proof of readiness.

## Evaluation posture

`eval_not_required`: this is a deterministic one-shot artifact validator/compiler;
its behavior is covered by the positive and negative controls in `sanity.sh`, with
no LLM routing or durable agent behavior.

## Readiness

The smoke profile establishes only local deterministic validation and tailoring. It
does not establish PDF visual quality, ATS compatibility, opportunity fit, or live
integration with `/monitor-opportunities`.
