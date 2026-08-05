# Handoff Report: monitor-opportunities

**Timestamp**: 2026-08-05T08:25:00-04:00
**Active Agent**: Claude (Claude Code)

## 0. 2026-08-05 morning update (supersedes items below where noted)

- **Repo risk (section 4, "Repository state is risky") is RESOLVED.** The
  48-path uncommitted delta was a stale lane that wrote files from the Aug 3
  baseline at 01:05, reverting the Aug 4 commits in the working tree. The Aug 4
  code (application/ATS/outreach/Buzz modules and tests) was restored from HEAD;
  only the genuinely new pieces were kept: `requires-python <3.13` pin,
  `run.sh` `unset VIRTUAL_ENV` fix, test-lab test headers, matching `uv.lock`.
  Landed as `e4825ff73` on `main` (pushed; `origin/main..HEAD` empty). Full
  pre-reconciliation delta backed up at
  `/tmp/claude-1000/-home-graham-workspace-experiments-agent-skills/6f1e978f-21be-4223-89ee-b4e54796dc5e/scratchpad/monitor-opps-full-dirty-backup.patch`.
- Gates on the reconciled tree: `sanity.sh` from repo root: **71 passed**;
  `python3 scripts/check_mock_evidence_claims.py`: OK over 586 test files.
  Note: several tests hardcode repo-root-relative fixture paths, so sanity must
  run with cwd at the repo root.
- **Fresh morning run (step 2) done**: `/tmp/monitor-opportunities-20260805T120849Z`
  — `live: true`, `mocked: false`, `external_effects: false`, terminal
  `AWAITING_HUMAN`, 5 opportunities, 10 outreach packets, 3 applications,
  `hidden_total: 0`, lanes A/B/C all `MATCHES` (3/20, 1/1, 1/1).
- **Loopback serve (step 3, local half) proven**: served on port 8797 with
  `--allow-remote`; `curl http://127.0.0.1:8797/health` returned
  `{"status":"PASS","external_effects":false}`. Tailnet URL printed for
  100.102.12.64. Remote/iPad readback still requires another Tailscale client —
  not provable from this machine. Port 8791 is held by an older leftover serve
  (pid 2528421), left running.
- **Buzz path (step 4) restored and proven**: `run.sh buzz-summary --post` to
  channel `ed942a5f-609d-4849-9128-3168c6dfac8c` succeeded (requires
  `BUZZ_IDENTITY_KEY`/`BUZZ_RELAY_URL` from `~/.zshrc`; ops-buzz maps it to
  `BUZZ_PRIVATE_KEY`). Independent readback via
  `buzz messages get --channel … --limit 1` returned today's run summary.
  Receipt: `/tmp/monitor-opportunities-20260805T120849Z/buzz/buzz-summary-receipt.json`.
- Remaining next steps are human-gated: remote iPad readback (step 3, remote
  half), Gmail draft / LinkedIn handoff / ATS promotions (steps 5–7), and
  scheduler registration (step 8, gated on the remote readback).

### Later on 2026-08-05: outreach promotion executed (steps 5–6 resolved)

- Graham authorized draft creation ("all drafts are allowed"; send remains
  forbidden). Promotion receipts:
  `/tmp/monitor-opportunities-20260805T120849Z/promotions/`.
- Ask roundtable gate ran live through API seats (gpt-5.5-high +
  chutes deepseek-ai/DeepSeek-V3.2-TEE; the claude-sonnet-4-6 seat failed with
  `scillm_auth_invalid_api_key` and was dropped). Round 1 split
  (DO_NOT_SEND vs SEND_WITH_REVISIONS over `CONTACT_UNKNOWN` recipients);
  Round 2 converged: SEND_WITH_REVISIONS for all 10 packets with recipient
  placeholder, internal-note removal, and a Discord claim-relevance human gate.
  Runs under `/tmp/monitor-opportunities-20260805T120849Z/outreach-roundtable/runs/`.
- Receipt map validated by the pipeline: run
  `/tmp/monitor-opportunities-20260805T-permitted` renders all 10 packets
  `PASS / REVIEW_PERMITTED / SEND_WITH_REVISIONS`, `hidden_total: 0`.
- Drafts of record: ArangoDB `memory.outreach_drafts`, 10 docs
  (`draft-20260805-<packet>`), verified by direct AQL keyed readback.
  Gmail mailbox drafts were trialed (5 created via surf, never sent) and
  deleted the same day at Graham's direction; see the PROJECT_KNOWLEDGE
  draft-storage decision. One pre-existing Aug 4 "Readback proof only" UB
  draft was intentionally left in the mailbox.
- Infra fixed en route: surf CLI was globally wedged behind a dead Jul 31
  lock owner (`/tmp/surf-lock-*`) plus a kernel-stuck `npm ci` holding
  `vendor/surf-cli/.ensure-surf-cli-build.lock`; cleared, `tab.list`/`js` live.

### Still later on 2026-08-05: contact identification + ats_form_inspect

- Recall integration: `outreach_drafts` is linked into the `unified_search`
  view AND semantically synced to Qdrant; `/recall` finds drafts by keyword,
  collections filter, and paraphrase. Memory-side commits `fd0dee29`
  (view-derived unified collections) and `b9dd7910` (keyed `/store` runs
  semantic sync) on graph-memory-operator@main.
- Contact identification (human-verify leads, no LinkedIn automation):
  `/tmp/monitor-opportunities-20260805T-permitted/contact-targets.json` —
  UB UBIT official leadership/jobs routes (site blocks curl; read via
  browser), DARPA per-BAA PM route plus the official BAA-response info
  sheet, and 5 public Discord recruiter leads as manual LinkedIn search
  targets. All 10 memory drafts now carry `contact_candidates`.
- `ats_form_inspect` promoted (read-only) and exercised: promotion receipt
  plus three Greenhouse form-schema receipts under
  `/tmp/monitor-opportunities-20260805T-permitted/ats-inspect/` (13/13/14
  questions, `form_schema_digest` per posting, sensitive/free-text fields
  marked `human_required`, `writes_performed: false`). Captured via the
  public Greenhouse job-board API — no browser writes.
- `ats-inspect` is now an implemented CLI command (`b0cd8b9f9`):
  Greenhouse adapter (`ats/greenhouse.py`) feeding the existing
  `application_plan.inspect_ats_form` gate, site-scoped human policy
  receipt required, fixture-backed tests, sanity 77 passed. All three
  Discord postings inspected live via the CLI.
- Application plans built for all three Discord postings
  (`ats-inspect/application-plan-greenhouse-discord-*.json`): state
  `PREPARED`, 4 prefillable fields each (First Name, Email, Website,
  "How did you hear"), and the plans fail closed on unresolved required
  fields that only Graham can answer: Last Name, Phone, the "Why
  Discord?" free-text, work-authorization and US-location selects, and
  Bay-Area/relocation questions (note: two roles ask about SF Bay Area
  relocation — eligibility-relevant). `authorize_application_plan`
  refuses any plan with unresolved required fields, so prefill/submit
  remain blocked on those answers plus per-site `ats_form_prefill`
  promotion.
- Graham supplied Last Name (Anderson) and Phone (310-402-3980) on
  2026-08-05; the answer bank lives at `ats-inspect/answer-bank.json` and
  in memory `career_answers/graham-core-application-answers` (synced).
  Plans rebuilt: 6 prefillable fields per posting. Remaining unresolved
  required fields are the contract floor that stays human-in-browser by
  design (gate tests prove required free-text/choice/sensitive fields can
  never be machine-authorized): the "Why Discord?" free-text, work
  authorization and US-location selects, Bay-Area/relocation questions,
  and Resume/CV upload on 8537955002. Next automation increment is
  `ats_form_prefill:greenhouse:discord` promotion: browser-prefill the six
  fillable fields with screenshot receipt; Graham completes the rest and
  transmits.
- Course correction (Graham, 2026-08-05): the rendered DOM is the
  authoritative inspect surface, not the job-board API — the live form
  requires Country, Location (City), and demographic selects the API
  omits. `form_from_dom_capture` now builds the canonical form from a
  surf read-only DOM query (API refines input kinds where labels match);
  inspections and plans for all three Discord postings were rebuilt from
  DOM (new digests; demographic fields human_required). Selector
  knowledge is stored ahead of any apply attempt: provider-stable core
  ids in `config/ats_selectors/greenhouse.json` (repo), per-posting
  `question_*` bindings in memory `ats_selector_bindings` (digest-bound,
  Qdrant-synced, recallable). Sanity 81 passed.

**Previous handoff (2026-08-05 07:57, Codex) follows.**
**Target**: `/home/graham/workspace/experiments/agent-skills/skills/monitor-opportunities`
**Authoritative branch target**: `grahama1970/agent-skills@main`

This handoff replaces the stale 2026-08-03 snapshot. The old snapshot said the
skill only had `SKILL.md`; that is no longer true. The current tree has a
Python package, `run.sh`, `sanity.sh`, fixtures, schemas, report/service code,
and tests, but it is still Stage 0 and does not meet the immutable goal.

## 1. Project Overview

- **Ecosystem**: Python package driven by `run.sh`, Typer CLI, JSON schemas,
  local HTML report renderer, loopback report service, local decision ledger,
  and pytest-based behavioral gates.
- **Core Purpose**: Nightly opportunity monitor that finds a bounded, highly
  relevant set of job/contract leads, ranks them, prepares claim-bound targeted
  resume variants, and presents one interactive morning report/interview.
- **Immutable goal**:

  > Daily top opportunities that are highly targeted, delivered in an
  > interactive report/interview, with auto-apply using a custom targeted resume
  > given the algorithm likely employed by the employer or client.

- **Current stage**: `STAGE_0_RESEARCH_ONLY`.
- **Current external-effect rule**: `external_effects: false`. Gmail send and
  LinkedIn automation are permanently forbidden. Gmail mailbox draft creation,
  LinkedIn human-handoff promotion, and ATS inspect/prefill/submit remain
  separate promotions, not Stage 0 behavior.

## 2. Current State (Doc-Code Alignment)

`skills/monitor-opportunities/run.sh status --json` on 2026-08-05 reported:

- `contract_version: 0.2.0`
- `operational_readiness: NOT_ESTABLISHED`
- `network_access: true`
- `external_effects: false`
- implemented commands: `status`, `report`, `verify`, `sweep`, `rank`,
  `tailor`, `decision`, `replay`, `run`, `resume`, `schedule`, `serve`
- not implemented command: `apply`
- blocked Stage 0 capabilities: `gmail_mailbox_draft`, `linkedin_handoff`,
  `ats_inspect`, `ats_prefill`, `ats_submit`
- permanently forbidden capabilities: `gmail_send`, `linkedin_automation`

Fresh local handoff run:

- command: `skills/monitor-opportunities/run.sh run --out /tmp/monitor-opportunities-handoff-run-20260805`
- run receipt: `/tmp/monitor-opportunities-handoff-run-20260805/run-receipt.json`
- report: `/tmp/monitor-opportunities-handoff-run-20260805/report/index.html`
- report JSON: `/tmp/monitor-opportunities-handoff-run-20260805/report/report.json`
- reported `live: true`, `mocked: false`, `external_effects: false`
- terminal state: `AWAITING_HUMAN`
- ranking receipt: 22 inspected, 5 shortlisted, 17 rejected or human-review
- report JSON: 5 opportunities, 5 outreach packets, 3 applications
- artifact accounting: `action_worthy_total: 14`, `visible_total: 14`,
  `hidden_total: 0`, `hidden_ids: []`
- lane A: searched, `MATCHES`, 20 observed, 3 admitted; receipts for
  hiddenjobs.dev, Indeed, Greenhouse
- lane B: searched, `MATCHES`, 1 observed, 1 admitted; receipts for DARPA and
  SAM.gov
- lane C: searched, `MATCHES`, 1 observed, 1 admitted; primary-company-source
  receipt

Proof scope: this proves the current local Stage 0 runner can produce a
read-only report artifact from the current code path. It does not prove nightly
reliability, iPad/Tailscale reachability, Buzz-agent availability, Gmail draft
creation, LinkedIn handoff promotion, ATS form inspection, ATS prefill, ATS
submit, or real successful applications.

Doc-code drift to preserve:

- `docs/PROJECT_KNOWLEDGE.md` still says the project is
  `CONTRACT_ONLY / STAGE_0_RESEARCH_ONLY / NOT_ESTABLISHED` and describes PR
  #1180 as the first executable state. Code has moved past pure contract-only:
  Stage 0 commands now exist and pass local checks.
- `SKILL.md` correctly says `run.sh status --json` and
  `docs/PROJECT_KNOWLEDGE.md` are authoritative for current implementation
  state, and `status` currently says `apply` is still not implemented.
- The immutable goal includes auto-apply, but current code intentionally fails
  that command closed.

## 3. What is Working Well

- Local Stage 0 command surface exists and runs through `run.sh`.
- Current `sanity.sh` passed: `37 passed in 1.43s`.
- Mock-evidence wording gate passed:
  `python3 scripts/check_mock_evidence_claims.py` returned
  `OK: checked 583 test file(s); no mock+proof claim violations`.
- Current verification receipt passed:
  `/tmp/monitor-opportunities-handoff-verify-current/verification-receipt.json`.
  It reported `overall: PASS`, `live: true`, `mocked: false`,
  `network_used: false`, and 9 passing cases:
  `valid_stage0_report`, `hidden_action_artifact`,
  `feed_down_as_no_matches`, `relocation_shortlisted`,
  `sendable_outreach`, `ats_authorized`, `free_text_autofilled`,
  `nine_shortlisted`, and `unknown_source_status`.
- The fresh run produced a single source-of-truth report with hidden-artifact
  count zero.
- Ranking still respects the eight-opportunity cap and separates inspected,
  shortlisted, and rejected/human-review counts.
- The generated report includes outreach packets and application records as
  visible Stage 0 artifacts, without sending or submitting anything.

## 4. What is Currently Broken

- **Immutable goal is not met.** The current product is a Stage 0 read-only
  local report, not a complete daily auto-apply workflow.
- **`apply` is not implemented.** The CLI registers it as an unsupported command
  that fails closed with `NOT_IMPLEMENTED`.
- **Gmail mailbox draft creation is not promoted.** Gmail send remains
  permanently forbidden; draft creation must be a human-gated capability
  promotion with receipt and readback.
- **LinkedIn platform automation is forbidden.** The project may use
  human-supplied or human-saved LinkedIn evidence and produce local handoff
  text, but must not log in, scrape, click, message, connect, post, or otherwise
  drive LinkedIn.
- **LinkedIn human-handoff readiness is still blocked in Stage 0.** The handoff
  packet path needs promotion if the next product slice wants ready-to-send
  InMail/connection-note packets.
- **ATS inspect/prefill/submit are still blocked in Stage 0.** Each provider or
  site needs explicit capability promotion, exact payload binding, idempotency,
  readback, and `INDETERMINATE` reconciliation before any external effect.
- **Buzz integration is not proven by the current repo check.** A prior Aug 4
  run posted/read back update receipts through a fallback Buzz channel, but the
  current Stage 0 code state no longer contains the previously added
  `buzz_review.py` module in the worktree diff.
- **Tailscale/iPad reachability is not proven by the fresh Aug 5 run.** Prior
  Aug 4 artifacts showed loopback report health and Tailscale serve
  configuration, but local readback of the tailnet URL timed out with curl exit
  28. Keep loopback proof separate from remote-device proof.
- **Repository state is risky.** `git diff --stat -- skills/monitor-opportunities`
  shows 48 changed paths with 244 insertions and 3965 deletions. Deleted files
  include application/ATS/outreach/Buzz modules and tests:
  `application_packets.py`, `application_plan.py`, `buzz_review.py`,
  `gmail_handoff.py`, `linkedin_handoff.py`, `outreach.py`,
  `roundtable_gate.py`, `tests/test_application_gates.py`,
  `tests/test_buzz_review.py`, and `tests/test_outreach.py`. Treat these as
  current uncommitted state that must be reconciled before claiming the broader
  product is restored.

## 5. Next Steps

1. Preserve or reconcile the current uncommitted monitor-opportunities delta.
   Decide whether the large deletion/simplification set is intentional. If it
   is intentional, update `docs/PROJECT_KNOWLEDGE.md` and tickets to say the
   outreach/ATS/Buzz promotion modules were rolled back. If it is not
   intentional, recover the deleted modules/tests from the relevant commits
   without using broad reset/checkout.
2. Run and inspect a fresh morning report from the intended repo state:
   `skills/monitor-opportunities/run.sh run --out /tmp/monitor-opportunities-$(date -u +%Y%m%dT%H%M%SZ)`.
   Read back `run-receipt.json`, `report/report.json`, and
   `artifact_accounting.hidden_total`.
3. Serve that report through the loopback service and Tailscale. Prove both:
   loopback health with `curl http://127.0.0.1:<port>/health`, and remote/iPad
   reachability from another Tailscale client. Do not treat Tailscale serve
   config as remote readback proof.
4. Restore the Buzz availability path for ops-buzz agents. Required artifact:
   a Buzz post receipt and readback pointing to the current report/run, with the
   accepted channel identity recorded. If the restricted channel rejects the
   identity again, either add the identity to that channel or make the fallback
   channel the configured channel.
5. Promote Gmail draft creation only after the current report/outreach packet
   contract is stable. Required behavior: create mailbox drafts, never send,
   read back draft IDs/links, and render them in the report with
   `candidate_transmits: true`.
6. Promote LinkedIn local handoff only after it is separated from platform
   automation. Required behavior: use human-supplied/saved LinkedIn opportunity
   evidence, write local InMail/connection-note handoff packets, run `/ask`
   roundtable, and expose final human-transmitted text in the report.
7. Promote ATS capabilities last and per provider/site. Required order:
   inspect form, bind exact schema and fields, generate targeted resume, mark
   unknown/free-text/sensitive fields `human_required`, request exact human
   authorization, then prefill/submit only within the authorized payload.
8. Register or refresh the nightly scheduler only after the above Stage 0 report
   path and Tailscale/Buzz readbacks are current. Registration must be read back
   by name, command, working directory, cron, and enabled state.

## 6. Project Context for Success

Key files:

- `SKILL.md`: immutable goal, lane policy, command contract, capability
  authority, human-transmission rules.
- `docs/PROJECT_KNOWLEDGE.md`: implementation sequence and non-claims; currently
  stale relative to the existing command surface.
- `run.sh`: skill runtime wrapper.
- `sanity.sh`: current deterministic gate runner.
- `src/monitor_opportunities/cli.py`: command surface and capability status.
- `src/monitor_opportunities/discovery.py`: read-only source discovery.
- `src/monitor_opportunities/ranking.py`: eligibility-before-ranking path.
- `src/monitor_opportunities/tailoring.py`: claim-bound resume variant path.
- `src/monitor_opportunities/report.py`: report rendering and visibility surface.
- `src/monitor_opportunities/service.py`: token-gated loopback report service.
- `src/monitor_opportunities/verification.py`: positive and adversarial local
  Stage 0 verification.
- `schemas/report.schema.json`: report manifest contract and hidden-artifact
  invariant.
- `fixtures/reports/stage0_mixed_lanes.json`: built-in Stage 0 fixture.

Recent commits touching this skill:

- `e9c5080b6 Wire monitor opportunities buzz summary`
- `7d4edda6a Add authorized LinkedIn opportunity capture`
- `283f40e0a Wire reviewed outreach receipts into opportunity report`
- `c064a117e monitor-opportunities: add ATS application gates`
- `3757710d6 monitor-opportunities: add local outreach handoff gates`
- `8f8642678 Bind application packets to resume artifacts`
- `83c27d744 Add local LinkedIn evidence intake`
- `184e02448 monitor-opportunities: render morning opportunity interview`

Prior Aug 4 evidence that may still matter during recovery/reconciliation:

- run root: `/tmp/monitor-morning-run-20260804T221811Z`
- consolidated receipt:
  `/tmp/monitor-morning-run-20260804T221811Z/morning-handoff-receipt.json`
- report manifest:
  `/tmp/monitor-morning-run-20260804T221811Z/report-manifest.json`
- report JSON:
  `/tmp/monitor-morning-run-20260804T221811Z/report/report.json`
- verification receipt:
  `/tmp/monitor-morning-run-20260804T221811Z/verify/verification-receipt.json`
- ask-gated outreach screenshot:
  `/tmp/monitor-morning-run-20260804T221811Z/report/ask-gated-outreach-section-screenshot.png`
- ask-gated live screenshot receipt:
  `/tmp/monitor-morning-run-20260804T221811Z/report/ask-gated-outreach-live-screenshot-receipt.json`
- Buzz roundtable update post receipt:
  `/tmp/monitor-morning-run-20260804T221811Z/outreach-contact-packets/ask-roundtable/buzz-roundtable-update-post-receipt.json`
- Buzz roundtable update readback:
  `/tmp/monitor-morning-run-20260804T221811Z/outreach-contact-packets/ask-roundtable/buzz-roundtable-update-readback.json`

Do not copy any local report URL token into committed docs. Use the receipt paths
above and generate a fresh token when serving a report.

Immutable Goal: NOT_MET
