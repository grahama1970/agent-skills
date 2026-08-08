---
name: best-practices-opportunities
description: >
  Canonical rubric for evaluating, scoring, ranking, and gating career and
  consulting opportunities for Graham Anderson, so the "top opportunities"
  selection is principled and repeatable rather than bespoke per run. Use when
  discovering, evaluating, reviewing, ranking, or deciding which opportunities
  to apply to in monitor-opportunities, or when building or reviewing the
  opportunity-evaluator / opportunity-evaluation-reviewer subagents or the
  ranker. The evaluator scores AGAINST this rubric; the reviewer reviews AGAINST
  it; the ranker orders BY it. No hand-built top-N lists.
triggers:
  - best practices opportunities
  - how to rank opportunities
  - which opportunities are the top ones
  - evaluate this opportunity
  - is this a good fit for Graham
  - opportunity targeting rules
  - should we apply to this role
provides:
  - opportunity-evaluation-rubric
  - opportunity-ranking-order
  - opportunity-targeting-rules
composes:
  - memory
  - brave-search
  - extract-entities
complies:
  - best-practices-skills
runtime_self_improvement: none
taxonomy:
  - precision
  - resilience
---

# Best Practices: Opportunities

The single source of truth for judging opportunities for Graham. It exists so no
agent ever bespokes a "top opportunities" list from intuition. Three consumers:

- **opportunity-evaluator** (creator) produces subscores + a verdict AGAINST this rubric.
- **opportunity-evaluation-reviewer** (reviewer) issues VERDICT PASS/FAIL AGAINST this rubric.
- **the ranker** orders the shortlist BY this rubric (mandate-first, §6).

If a rule here conflicts with a hand-written list, the rule wins. Update the
rubric; do not special-case a run.

## 0. Candidate profile is authoritative

Read `skills/monitor-opportunities/config/candidate_profile.json` and `/memory`
(`morning_opportunities`) for who Graham is. Never infer preferences. Key facts:

- **Principal AI Architect**, Buffalo NY, US citizen, authorized to work in US.
- **Dual-track:** senior full-time employment AND consulting clients (§7).
- **Seniority floor:** Principal / Staff+ / Architect / Senior. Below is deprioritized.
- **Workplace:** remote or hybrid **preferred**; on-site OK **only** Buffalo/WNY; **no relocation**.
- **Mandates:** agentic-compliance, document-extraction, agentic pipelines/LLM systems, verification-oriented AI (§3).
- Claims are approved-claim-bound (test-enforced). No fabricated credentials.

## 1. Core rule — evaluate, never merely collect

A title is not an evaluation. Every opportunity MUST be judged on its **job-description
text** (acquired via ATS API, read-only surf DOM, or the evidence URL) and, when the
text is thin or the employer is unfamiliar, **brave-search** on the employer / domain /
role. An opportunity with no acquired JD and no research is `NEEDS_REVIEW`, never a KEEP.

## 2. Eligibility gates (hard rejects, before scoring)

Reject and stop if any hold (lane A job postings):

- **Recency:** a parseable `published_at`/`updated_at` older than 2 weeks → `REJECT_STALE_AGE`. Missing/unparseable date is NOT rejected here but is **penalized** in scoring (§8) and never treated as fresh.
- **Relocation required** outside Buffalo/WNY → reject.
- **Work-authorization mismatch** → reject.
- **Role type** off-mandate (§5) → `REJECT_ROLE_TYPE`.
- **Clearance:** distinguish *active-clearance-required-at-start* (reject unless attested) from *obtainable clearance / public-trust / citizenship-eligible* (Graham is a US citizen with federal experience — do NOT auto-reject obtainable-clearance roles; mark `NEEDS_REVIEW`).

Federal (lane B) and commercial-signal (lane C) opportunities are NOT title/role-filtered.

## 3. Mandate-fit (weighted, cite the JD)

Score each mandate 0–1 from the JD responsibilities (not boilerplate); every subscore > 0
MUST cite a JD/source quote:

| Mandate | Positive JD signals |
|---|---|
| agentic-compliance | GRC, model assurance, auditability, controls/evidence, regulated deployment, formal methods, evaluation |
| document-extraction | PDF, OCR, layout understanding, IDP, multimodal documents, extraction, provenance |
| agentic pipelines / LLM systems | orchestration, tool-use, memory, retrieval, multi-agent, guardrails, observability |
| verification-oriented AI | evaluation harnesses, model verification, red-team/assurance, correctness |

**Relevance is vocabulary-driven, NOT regex.** Mandate matching uses
`/extract-entities` (deterministic Flashtext + fuzzy, zero LLM) against the
`opportunity_vocabulary` ArangoDB collection — never substring regex, which
mis-fires ("ai" inside unrelated words). Tune relevance by editing the
vocabulary (concepts + aliases) in `/memory`, not by editing code
(`best-practices-python` regex-only-known-grammar; `best-practices-arangodb`
domain-terms-in-ArangoDB). This is a cheap first-pass filter; residual fuzzy
false positives (e.g. "Agency"→"agentic") are resolved by the JD-reading
evaluator (§1), which is the authoritative second pass.

## 4. Seniority & ownership

Score Principal-level scope from the JD: architecture ownership, technical strategy,
cross-team influence, mentorship, decision authority, hands-on-vs-managerial balance.
"Senior" at a startup can equal Staff+ scope — judge scope, not just the title word.

## 5. Role-type targeting (off-mandate hard negatives)

Drop lane-A postings whose title is an off-mandate role type even with a senior prefix
(a "Senior Account Executive" is still sales). Hard negatives: account executive/manager,
sales/SDR, solutions engineer (pre-sales), growth officer, administrator, coordinator,
accounting, recruiter/talent acquisition, web designer, copywriter, editor, founder/
co-founder/founder-in-residence, data-management specialist. A bare "manager" with **no**
engineering signal is dropped; **Engineering Manager / AI Platform Manager survive**.
Below-floor (intern/junior/entry/associate-engineer) dropped. **Token-safe:** never drop
`Founding Engineer / Founding Architect` on the `founder` substring. Prefer a role-family
classifier (KEEP/REJECT/ADJACENT/CLIENT_SIGNAL/NEEDS_REVIEW) over brittle substrings when
JD text is available; hard negatives are the deterministic floor.

## 6. Ranking order — MANDATE-FIRST, not geography (webgpt P0)

Do NOT rank by an additive sum where geography can dominate. Apply eligibility gates
first, then order by, roughly in priority: **(1) mandate-fit → (2) seniority/ownership →
(3) employment-type fit → (4) workplace fit (remote or WNY-hybrid first; WNY-onsite
below) → (5) hard-requirement coverage → (6) comp/opportunity quality → (7) application
probability (referral proximity, applicant volume, freshness, ATS friction).** Keep the
subscores; the digest MUST explain each pick with positive evidence, penalties, and
unresolved requirements. A mediocre WNY role must not outrank an exceptional remote
Principal AI role.

## 7. Dual-track routing

Route into distinct objects, not one pile:

- **Employment role** → tailored resume + ATS prep.
- **Consulting engagement** (RFP/SOW/project) → capability statement + proposal prep.
- **Prospective-client signal** → evidence a company has a relevant problem/budget (an
  Account Executive posting is NOT a job for Graham but IS a signal the company invests
  in AI/compliance/public-sector) → prospect queue, not deleted.
- **Partner/referral signal** → primes/integrators/consultancies that could channel work.

The digest uses separate lane quotas so abundant jobs never starve sparse, valuable
consulting engagements.

## 8. Reviewer checklist — false-KEEP and false-REJECT

The reviewer FAILs an evaluation that has either:

- **False KEEP:** off-mandate/below-floor noise kept, or a KEEP with no evidence quotes; aggregate/evergreen listings ("Join us — Evergreen Opportunities"), tool-specific implementation roles, or generic cloud/PLM architect roles kept without mandate evidence.
- **False REJECT:** a genuine Principal-level agentic-compliance / document-extraction / verification role dropped; an obtainable-clearance federal role auto-rejected; a `Founding Engineer` dropped on the `founder` token.

Also penalize: missing posting date (uncertainty penalty, not fresh), agency/reposter vs
direct employer, office-radius "remote" masquerading as US-remote.

## 9. Verdict vocabulary

`KEEP` (pursue) · `REJECT` (off-mandate/below-floor/stale) · `ADJACENT` (relevant but
weak — needs JD evidence to promote) · `CLIENT_SIGNAL` (consulting-prospect, not a job) ·
`NEEDS_REVIEW` (JD unacquired or ambiguous requirement).

## 10. Volume, funnel, and the apply gate

Cold-application funnel (memory `job-application-funnel-metrics-2026`): ~42 applications
per interview; 100–200+ cold applications per offer; **tailoring is the biggest lever**.
Implication — surface **hundreds** of relevant opportunities and track them; do NOT
bespoke a short list. Gating tiers:

- **All passing opportunities** → evaluate + review + track on the private board (nightly, automatic).
- **Top 3 by mandate-first fit** → deep path: apply-prep + learn-the-ATS-site + outreach draft + roundtable (nightly, automatic). 3/night ≈ ~90/month — quality *at* volume. Configurable (`MONITOR_APPLY_TOP_N`).
- **Human-approved** (`state:approved` on the board) → any additional opportunity enters the deep path on demand.
- **Submit + send** → human only, always. Never auto-submit; InMail/Gmail send is permanently forbidden (draft to `/memory`, human transmits).

"Top 3 by fit" is only trustworthy once §6 mandate-first ranking is in effect.

## 11. Lifecycle (tracked, never bespoke)

Each opportunity is one issue in the **private** tracker repo (`grahama1970/opportunities`)
plus a `/memory` mirror. State machine (exclusive labels): `evaluated → shortlisted →
awaiting-human → approved → applied → responded → closed(outcome)`. Dedup by stable
`candidate_id`/`content_hash` — a re-seen posting gets a re-eval comment, never a
duplicate. The public `agent-skills` repo is for the skill's own code defects only.

## Anti-patterns (patch on sight)

- **Title-only collection** — scoring without acquiring the JD. §1.
- **Geo-dominated ranking** — additive sum where Buffalo outranks fit. §6.
- **Bespoke top-N** — a hand-picked list instead of rubric output. §1, §10.
- **Fabricated claims** — any credential not in approved-claims. §0.
- **Auto-submit / auto-send** — crossing the human gate. §10.
- **Brittle title substrings** dropping `Founding Engineer`. §5, §8.

## Evaluation posture

`eval_not_required`: this is a static rules/rubric skill (no executable entrypoint),
analogous to `best-practices-python`. Its correctness is exercised by the consumers that
comply with it — the `monitor-opportunities` role-targeting, recency, and ranking tests,
and the `opportunity-evaluator` / `opportunity-evaluation-reviewer` subagent contracts —
not by a fixture in this skill. Frontmatter validity is enforced by
`best-practices-skills` sanity.
