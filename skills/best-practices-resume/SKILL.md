---
name: best-practices-resume
description: >
  Canonical rules for writing, formatting, exporting, and verifying Graham
  Anderson's resume and its public surfaces, so an agent never re-derives them
  by trial and error. Use when editing RESUME.md, changing the resume PDF, DOCX,
  Markdown or /resume page, reconciling LinkedIn with the resume, deciding page
  count or section order, judging whether a claim may be made, or verifying a
  built resume artifact. /resume executes; this skill decides.
triggers:
  - best practices resume
  - resume rules
  - how should the resume be written
  - resume page count
  - is this resume claim allowed
  - resume formatting rules
  - ATS resume rules
  - verify a resume artifact
provides:
  - resume-content-rules
  - resume-format-rules
  - resume-verification-rules
  - resume-surface-consistency-rules
composes:
  - resume
  - brave-search
  - surf
  - agentic-evals
complies:
  - best-practices-skills
runtime_self_improvement: none
taxonomy:
  - precision
  - validation
domains:
  - marketing
disciplines:
  - engineering-standards
  - content-creation
---

# Best Practices: Resume

The rules layer for Graham's resume. `/resume` holds the executable checks;
this holds the judgements those checks cannot make. Every rule below was
established by a measurement or a mistake recorded in this repository, and the
evidence is cited so a future agent can re-test it rather than trust it.

## The purpose of the document

A resume is read by software before a person sees it. Both readers matter and
they want different things, so the rules split accordingly: content rules serve
the human who decides, format rules serve the parser that filters, and
verification rules exist because both are easy to break silently.

Never optimise one to zero. Keyword coverage that a person finds unreadable
fails the second reader; prose a parser cannot extract never reaches the first.

## Content rules

1. **Lead with current capability, not biography.** The first paragraph states
   what he builds now. The unusual creative-to-DARPA arc is a differentiator and
   belongs in the document, but a client reading for "can you build my agentic
   pipeline" must not have to reach paragraph three to find out.
2. **Date the capability.** In agentic AI only recent work reads as a
   credential. State recency explicitly with evidence — commit volume over the
   last six months, "built or materially advanced in 2026" — because a reader
   cannot otherwise tell a current stack from a past chapter.
3. **Every declared competency must appear in an experience bullet.** A skills
   list naming capabilities the bullets never demonstrate is the pattern
   Workday's screening layer flags hardest. Enforced by
   `/resume screening_audit.py support`, which excludes web-only sections from
   evidence because a PDF reader never sees them.
4. **Never invent a metric, a date, an employer, or a client.** Where a real
   outcome exists, state it. Where it does not, say less. A claim that clears a
   filter and collapses in an interview costs more than the filter did.
5. **Client names withheld under ITAR are not an absence.** Sell the engagement
   shape instead: the client class, the deliverable, the constraint. "Short,
   scoped engagements for aerospace primes and federally funded laboratories"
   carries what a logo would.
6. **Cut duplication before substance.** When over length, the first candidates
   are paragraphs that restate an experience bullet, not the bullets themselves.
7. **Older roles are colour.** Beyond roughly fifteen years, compress to one
   line under an "Earlier" heading. Keep the proper nouns that do work; drop the
   detail.
8. **The timeline must be continuous.** Gaps invite questions a screener will
   not stop to ask. Where a practice genuinely spans the gap, name the practice.
   Do not fabricate one.

## Format rules

9. **Two pages.** A 2025 survey of 1,013 HR professionals puts the ideal at 1–2
   pages, with 51% preferring two; three pages is reserved for academic CVs and
   senior executives, not engineering roles. Hold the line by cutting
   duplication, not by shrinking type below ~8.9pt.
10. **Single column, real text, conventional headings, standard date ranges, no
    tables, no images, no sidebars.** Multi-column layouts drop parse scores
    sharply on the older trackers.
11. **Link text must be the visible URL.** Parsers strip anchors, so
    `[LinkedIn](…)` loses the destination entirely while
    `[linkedin.com/in/name](…)` survives as text.
12. **Ship DOCX as well as PDF.** Measured 2026 parse rates: DOCX ~97% against
    text-PDF ~91% on average, and 97% against 83% on Taleo. The PDF is what a
    human reads; the DOCX is what to upload when a form offers the choice.
13. **Keep the exports one source.** RESUME.md builds the PDF, DOCX, Markdown
    and page. Where a cut differs, express it as a rule
    (`--omit-section`, `<!-- pdf-only -->`), never as a second document.
14. **Do not publish a phone number.** The PDF sits at a public URL in a public
    repository and its history is permanent. Contact by email; add a number only
    to a locally built copy that never enters git.

## Surface consistency

15. **LinkedIn, the resume, and the site must tell one story.** Cross-checking is
    routine and an inconsistency reads as a verification risk rather than an
    oddity. Reconcile roles, dates, employer names and counts.
16. **RESUME.md is canonical.** Where LinkedIn disagrees, LinkedIn changes.
17. **Map resume phrasing onto LinkedIn's taxonomy rather than dropping it.**
    LinkedIn has no "AI Observability" but does index `MLOps`; no "Regression
    Gates" but `Regression Testing`. Confirm each mapping against its own
    autocomplete — do not assume the absence of a term means the absence of the
    capability.
18. **Feature the resume on LinkedIn as a link, never an uploaded file.** An
    uploaded PDF in Featured is a snapshot: it goes stale the moment RESUME.md
    changes, and `/surf` cannot replace it — the CLI has no upload verb (only
    `webgpt.download`), so a stale upload can only be fixed by hand. A Featured
    link to `https://grahama.co/resume` tracks the source automatically. Add it
    through the Featured overflow menu → "Add a link"; the flow is two steps
    (URL, then a title/description form) and the *second* Save is the one that
    commits — a single Save click after entering the URL silently does nothing.
    LinkedIn exposes no edit control for an existing Featured item, so
    correcting one means delete-and-re-add: treat the wording as expensive and
    prefer open-ended counts ("340+ skills") over exact ones that decay.
19. **The site is a machine surface too.** `llms.txt`, `robots.txt`,
    `sitemap.xml` and a schema.org `Person` with a real `jobTitle` and non-empty
    `knowsAbout` are read before any prose. `jobTitle` takes one title, not the
    keyword headline.

## Verification rules

20. **Verify the artifact that was served, not the one you built.** A stale PDF
    once reached production because it was built correctly, then committed after
    a concurrent process reverted the working tree. Fetch the public URL.
21. **Normalise before asserting a string is missing from a PDF.** PyMuPDF
    returns typographic ligatures, so "Brie**fi**ng" extracts as "Brieﬁng" and
    "Bu**ff**alo" as "Buﬀalo"; line wrapping splits phrases across newlines.
    Apply `unicodedata.normalize("NFKC", …)` and collapse whitespace first. This
    produced three separate false alarms in one session, twice nearly prompting
    a "fix" to content that was never broken.
22. **A green local build is not a green deploy.** A `GITHUB_TOKEN` push cannot
    trigger another workflow, so an artifact committed by one workflow will not
    redeploy the site. Build the artifact in the deploying workflow instead.
23. **Do not run a production build beside a running dev server.** `next build`
    overwrites the `.next` a running `next dev` holds, and the dev server then
    serves module-not-found errors that look like application bugs.

## Anti-patterns

| Pattern | Why it fails |
|---|---|
| A composite "ATS score" | Collapses actionable component failures into an unauditable number |
| Keyword stuffing | Trips the padding heuristic and reads badly to the human |
| A second resume document per audience | Guarantees drift; use one source with declared cuts |
| Trusting a tool's refusal as fact | "No LinkedIn equivalent" was true for 9 terms and false for 8 |
| Counting rows to confirm a profile write | The list paginates; read back by name |

## Evaluation posture

`eval_not_required`: this skill states rules and holds no runtime. The rules are
enforced executably by `/resume` (`validate`, `competencies scan`,
`screening_audit support|surfaces`, `linkedin_sync`), and that skill's
`sanity.sh` is where they are proven.
