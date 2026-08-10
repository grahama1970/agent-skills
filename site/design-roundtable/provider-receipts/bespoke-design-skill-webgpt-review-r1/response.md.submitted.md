# WebGPT Review Bundle: best-practices-bespoke-design on grahama.co

## Objective

Review `skills/best-practices-bespoke-design/SKILL.md` as an operational skill,
using the recent grahama.co work as the case study. Identify what worked, what
was kludgy, where the process caused agent spiraling, and what concrete skill,
checker, artifact, or collaboration-UX changes would reduce future failure.

This is a review request, not a closure request. WebGPT output is advisory only.
Local deterministic receipts remain required before any `PASS`, `READY`, or
closure claim.

## Current Local State

- Repository: `agent-skills` checkout on the local workstation; relevant
  repo-relative paths are listed below.
- Local site under review: `http://127.0.0.1:3003/`
- Production deployment constraint: do not push/deploy this local render to
  `grahama.co` without explicit human authorization.
- Latest local skill/tool repair commit: `087303adf4 Tighten bespoke design gate validation`
- Current monitor receipt:
  `site/design-roundtable/design-world-check.latest.json`
- Current monitor status: `NOT_TESTED`
- Current G11 status: `NOT_TESTED`
- G11 failure signature:
  `fresh_blind_raters_not_run_for_current_segmented_corpus`
- Current usable fresh raters for the current corpus: `0`
- Current section corpus:
  `site/design-roundtable/rendered-screens/responsive-section-corpus-20260810T030534Z/manifest.json`
- Corpus SHA-256:
  `5edd2f32f1ffa69c368b79e310d66dc992141e1cb780997630bf61eb8fd17f0d`
- Corpus counts: `5` viewports, `10` sections, `147` cropped screenshots,
  `0` capture failures.
- Craft render gate: `PASS`

## Recent Project-Knowledge Entry

On 2026-08-10, `PROJECT_KNOWLEDGE.md` was updated with this lesson:

> `best-practices-bespoke-design` is useful when it forces evidence-first
> visual-world work, section/page-state crop review, stale-evidence rejection,
> and explicit G0-G20 gate status. It became kludgy when site implementation,
> screenshot-corpus capture, WebGPT/rater transport, formal gate validation, and
> status UX were treated as one blended lane. Future grahama.co work must not
> send whole-site images as primary proof; it must use section/subsection crops
> or contact sheets, preserve raw rater outputs, and keep the primary lane
> explicit: implementation, corpus capture, rater submission, checker repair, or
> final receipt generation.

The update command reported:

```text
Updated section 'Current Understanding'
Synced project knowledge to /memory (66 chunks)
```

## What Worked Well

- The skill's core standard is strong: brand truth -> personality -> narrative
  premise -> visual grammar -> rendered proof.
- It now explicitly bans whole-site screenshots as primary review evidence and
  requires section/component/page-state crops.
- It correctly distinguishes missing proof from failure and from readiness.
- It now covers G0-G20, including craft integrity, type fidelity, material
  fidelity, amend-loop separation, world persistence, and asset provenance.
- The grahama.co flow produced a real segmented corpus, not one giant page:
  `147` section/subsection crop screenshots across `5` viewports.
- The skill helped surface concrete design/process facts: stale rater evidence,
  missing fresh G11 raters, old schema drift, and missing gate enforcement.

## What Was Kludgy Or Caused Spiraling

- The skill was initially clearer as a design philosophy than as an executable
  operating loop.
- The formal proof requirement expanded faster than the monitor/checker
  implementation. The skill required G0-G20 while `validate_receipt.py`, the
  schema, and fixtures still enforced only G0-G14.
- The agent blended multiple lanes: site repair, section-crop capture, rater
  transport debugging, formal gate validation, and status reporting. That made
  the human unable to tell where the work was blocked.
- WebGPT/rater transport failures were confused with design failures and with
  skill failures. Browser-review submission proof, rater output proof, and
  local deterministic gate proof need separate states.
- The human repeatedly had to restate the section-crop requirement even though
  the skill should have made it impossible to proceed with whole-site images as
  primary review artifacts.
- The process used a formal gate vocabulary (`blocked`, `NOT_TESTED`,
  `craft`, `G11`) without enough plain operational UX showing: current phase,
  exact artifact, current count, failed command, and next command.
- Old favorable rater output was allowed to remain psychologically tempting
  even after the corpus changed. The checker needed to fail closed on stale
  source/corpus/hash/rater mismatches.

## Repairs Already Made Locally

Commit `087303adf4` changed:

- `skills/best-practices-bespoke-design/scripts/validate_receipt.py`
  - `REQUIRED_GATES` is now G0-G20.
- `skills/best-practices-bespoke-design/schemas/bespoke-design-receipt.schema.json`
  - schema now requires G0-G20.
  - exceptions can reference G0-G20.
- `skills/best-practices-bespoke-design/fixtures/passing-receipt.json`
  and `fixtures/failing-receipt.json`
  - fixtures now include G15-G20.
- `skills/best-practices-bespoke-design/SKILL.md`
  - Phase 11 now says stale screenshot corpus, old source commit, modified
    artifact hash, or reviewer output from a different render must be
    `NOT_TESTED` or `FAIL`, not partial pass.
- `skills/monitor-website/scripts/design_world_check.py`
  - checks referenced artifact SHA-256s.
  - exposes `source_state`.
  - verifies craft rendered screenshot hashes.
  - refuses G11 `PASS` unless usable rater records and aggregate thresholds are
    present.

Focused proof commands already run:

```bash
python3 -m py_compile \
  skills/monitor-website/scripts/design_world_check.py \
  skills/best-practices-bespoke-design/scripts/validate_receipt.py

skills/best-practices-bespoke-design/sanity.sh
# PASS: best-practices-bespoke-design sanity

python3 scripts/check_mock_evidence_claims.py
# OK: checked 631 test file(s); no mock+proof claim violations

skills/monitor-website/run.sh design-world-check --json \
  | tee site/design-roundtable/design-world-check.latest.json
# status: NOT_TESTED
# distinctiveness_blind: NOT_TESTED
# g11 usable fresh raters: 0
# section corpus: 147 cropped screenshots, 0 failures
# craft_integrity_render: PASS
```

## Current Skill Behaviors To Review

Relevant current rules in `best-practices-bespoke-design`:

- Live collaboration ledger required for live site work, audits, amend loops,
  and disputed reviews.
- Only one primary lane may be active at a time.
- Phase 8 requires section/component/page-state screenshots as acceptance
  evidence; full-page captures are navigation/debug artifacts only.
- Phase 9 requires adversarial distinctiveness tests: logo-off recognition,
  competitor swap, motif semantics, cross-screen family, reference leakage, and
  template residue.
- Phase 11 requires exact source revision, implementation revision, validated
  receipt, raw rater outputs, and current artifact hashes.
- `READY` is legal only when every required gate is `PASS`.
- Missing evidence must be `NOT_TESTED`, `NOT_ESTABLISHED`, or `BLOCKED`; it
  must not be summarized as success.

## Questions For WebGPT

Please review the skill and the grahama.co failure mode as an operational
process. Return concrete recommendations, not a generic design critique.

1. Which parts of `best-practices-bespoke-design` are strong and should be kept?
2. Which parts are too opaque, too broad, or anti-collaborative during live site
   work?
3. What exact amendments would make the skill prevent the observed spirals:
   blended lanes, stale evidence, whole-site screenshots, rater-transport
   confusion, and vague status reporting?
4. Should the skill define a required status/UX artifact for the human, such as
   a live ledger with phase, gate, artifact path, counts, blocker, next command,
   and stop condition? If yes, specify its minimum schema.
5. Should G11 be split into separate sub-gates for `corpus_ready`,
   `rater_transport_ready`, `fresh_raters_complete`, `thresholds_met`,
   `raw_outputs_preserved`, and `competitor_swap_passed`? If yes, propose names
   and pass/fail semantics.
6. What should the next executable repair slice be for the skill/checker/process,
   not the grahama.co visual design?
7. What should be explicitly forbidden so a future agent cannot claim progress
   by writing failure reports, preparing prompts, or producing screenshots that
   reviewers cannot actually use?

## Requested Output Format

Return:

```markdown
## Verdict
PASS/FAIL/NEEDS_ATTENTION for the skill as an operational contract.

## What To Keep
Concrete parts that worked.

## Failure Modes
Concrete causes of spiraling in the grahama.co run.

## Skill Amendments
Patch-level wording or schema/checker changes.

## Checker/Artifact Changes
Deterministic checks or receipt fields to add.

## Human-Visible UX
Minimum status artifact or ledger the skill should require.

## Next Executable Slice
One smallest local change with proof command.
```

---

Completion contract for browser automation:

At the very end of your final answer, print exactly:

<<<WEBGPT_DONE:20260810T120755Z:96797a91>>>

Do not print anything after that marker.
