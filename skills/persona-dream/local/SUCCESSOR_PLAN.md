# Successor Revision Implementation Plan

**Created:** 2026-07-18
**Source of truth:** `GOAL.md` (immutable 42-step goal), `local/HANDOFF.md`
(2026-07-18 refresh). This plan operationalizes HANDOFF section 5 into four
serial phases. It changes nothing about the immutable goal.

**Hard stop condition (all phases):** no paid Kling/provider call. The
acceptance rung for this plan is HANDOFF step 8: successor revision
active/consistent, Memory exact reread passes, and 8/8 storyboard frames pass
actual-pixel continuity review. Steps 9-12 (new hash-bound paid authorization,
submit, post-return review) are explicitly out of scope and human-gated.

## Phase A — Clean git baseline (HANDOFF step 0)

Verified starting facts (2026-07-18):

- Repo `/home/graham/workspace/experiments/agent-skills-main`, branch `main`,
  ahead 4 / behind 6 of `origin/main`.
- All 4 local commits (`fecff7aa`, `655efa86`, `a33b45d7`, `1f041b87`) are
  patch-equivalent to commits already on `origin/main` (`git cherry` = all `-`;
  origin twins `c4380817`, `10bc2065`, `c870698c`, `4c392a9d`).
- Incoming-only commits: `c79bc820` (tau durable workflow lifecycle),
  `a6d14d14` (battle worktree fix). Merge preview shows zero conflicts.

Work:

1. Commit dirty paths in logical commits (handoff refresh + this plan;
   phase13 review-bundle artifacts; ui-verification markers; anything else
   `git status` shows, grouped sensibly). Delete nothing.
2. `git rebase origin/main` — the 4 patch-equivalent commits drop out; new
   commits replay on top.
3. Normal `git push origin main`. Never force-push.

Done when: `git status` clean, `main` == `origin/main` + new commits, pushed.

## Phase B — Successor immutable revision (HANDOFF steps 1-3)

1. Build `scripts/create_successor_revision.py` modeled on
   `scripts/reconstruct_upstream_contract_revision.py`. Do not assemble the
   revision by hand. Do not mutate `rev_upstream_bf3b05d47fb8`.
2. Successor requirements:
   - Derived from `rev_upstream_bf3b05d47fb8`.
   - `revisionRoot` is a durable repo-rooted path under
     `reports/pipeline-complete/.persona-dream/revisions/`; activation fails
     closed if `revisionRoot` resolves outside the repository.
   - Bind identity source `embry_contact_sheet_v3`
     (`sha256:3ce40b3b6839ebba0f468d75a1adbb7f82e0d95457aefd3627e222eb569de00c`,
     qualification receipt
     `reports/embry-contact-sheet-qualification-20260717.json`, Memory key
     `b11474f2fd5b54f332223a253fd743d1`).
   - Emit an upstream invalidation ledger marking every Phase 07-11 artifact
     derived from the rejected montage as stale.
3. Write the successor `state/active_revision.json`, run
   `prepare_revision_qualification.py` and activation qualification to PASS,
   persist Memory step records with exact reread.
4. Tests + commit.

## Phase C — Regenerate 8 storyboard frames (HANDOFF steps 4-6)

1. Regenerate all eight Phase 07 start/end frames with GPT Image 2 through the
   Tau/Scillm creator path, referenced to `embry_contact_sheet_v3`.
2. Tau creator/reviewer actual-pixel review per frame: Embry identity, Kai
   identity, wardrobe/equipment, lighting, reef boundary, dialogue intent,
   panel action, inter-frame continuity. Raise Tau command-loop `max_steps`
   above 2 so the panel-specific node executes.
3. Fail closed on drift; persist repair attempts and final statuses to Memory
   with exact reread. Image generation via GPT Image 2 is authorized; Kling is
   not.

## Phase D — Rebuild + acceptance rung (HANDOFF steps 7-8)

1. Rebuild successor artifact index, phase bindings, active-revision
   qualification; require Memory verification.
2. Prove the acceptance rung: successor active/consistent, Memory exact
   reread, 8/8 frames PASS actual-pixel review.
3. Only then refresh `README.md` proof-boundary table and `local/HANDOFF.md`;
   commit and push. Stop. Report to human for hash-bound paid authorization.
