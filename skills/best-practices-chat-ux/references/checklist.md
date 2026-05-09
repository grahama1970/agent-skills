# Chat UX Checklist

Use this checklist for UX design, mockups, or frontend implementation of private
operator chat, evidence chat, run-card chat, and compliance-review chat
interfaces.

A design is not ready unless all required items pass.

## 1. Product Scope

- [ ] The design is a private operator/evidence chat, not a generic consumer
  chatbot.
- [ ] The design is not dashboard-first.
- [ ] The design focuses on commands, structured operational objects, artifacts,
  validation, and next actions.
- [ ] Public SaaS assumptions are absent unless explicitly requested.

Failure if:

- [ ] The primary screen is a generic dashboard.
- [ ] The chat command surface is hidden.
- [ ] The design introduces unrelated metrics, charts, or decorative cards.

## 2. Routing And Scope Visibility

For delegated runs, visibly show:

- [ ] Selected project.
- [ ] Selected subagent or worker.
- [ ] Run mode.
- [ ] Selected skills.
- [ ] Repo path, branch, worktree, or workspace when applicable.
- [ ] Commit, merge, and push policy when applicable.

For evidence/compliance chat, visibly show:

- [ ] Evidence case ID.
- [ ] Artifact or source document.
- [ ] Technique, control, framework, or taxonomy terms.
- [ ] Source turn, citation, or lineage.
- [ ] Readiness state such as blocked, runnable, pending trace, or verified.

Failure if:

- [ ] The user cannot tell what project, artifact, or evidence case was acted on.
- [ ] The user cannot tell which skills, controls, or evidence path were used.
- [ ] The user cannot tell whether the result is validated or merely runnable.

## 3. Structured Cards

Run cards should include:

- [ ] Run status.
- [ ] Project id/name.
- [ ] Worker or subagent.
- [ ] Run mode.
- [ ] Selected skill chips.
- [ ] Branch/worktree/commit when present.
- [ ] Postflight status.
- [ ] Open details / inspect artifacts action.
- [ ] Next TODO summary.

Evidence cards should include:

- [ ] Evidence case ID.
- [ ] Artifact/source.
- [ ] Numbered claims.
- [ ] Citations/source turns.
- [ ] Technique/control/framework terms.
- [ ] Trace/readiness state.
- [ ] Expand/collapse action.
- [ ] Separation from final answer.

Failure if:

- [ ] A delegated run appears only as assistant prose.
- [ ] An evidence case appears only as a paragraph.
- [ ] The user must open raw logs to know whether the run or trace passed.

## 4. Timeline And Typed Events

The UI should render typed events by role:

- [ ] `status` events in a timeline.
- [ ] `skills` events as chips or lists.
- [ ] `artifact` events as artifact links/tabs.
- [ ] `approval` events as buttons/cards.
- [ ] `done` events as success/failure summaries.
- [ ] `error` events as visible failure states.
- [ ] `stdout` and `stderr` in logs, collapsed or deprioritized by default.

Failure if:

- [ ] Every event is rendered as chat text.
- [ ] stdout/stderr spam the main conversation.
- [ ] The user cannot tell which phase failed.

## 5. Artifact Inspector

The UI supports inspection of:

- [ ] report or final answer.
- [ ] diff or trace.
- [ ] result JSON.
- [ ] stdout/stderr logs.
- [ ] events JSONL.
- [ ] prompt/request.
- [ ] memory context or selected skill snapshots when relevant.
- [ ] source evidence or citations when relevant.

Rendering standards:

- [ ] Markdown is readable.
- [ ] Diffs and logs are monospace and scannable.
- [ ] JSON is formatted.
- [ ] Logs are collapsed or deprioritized by default.
- [ ] Artifact names are visible and selectable.

Failure if:

- [ ] Artifacts are hidden or only downloadable.
- [ ] Logs are the primary artifact view.
- [ ] Reports, diffs, JSON, logs, prompts, and evidence are visually
  indistinguishable.

## 6. Progressive Disclosure

Default view answers:

- [ ] What happened?
- [ ] Did it pass, fail, or remain pending?
- [ ] What changed or what evidence supports the answer?
- [ ] What should the human do next?

Expanded view answers:

- [ ] Full logs.
- [ ] Raw JSON.
- [ ] Prompt/request.
- [ ] Events.
- [ ] Skill snapshots.
- [ ] Full evidence/citation trail.

Failure if:

- [ ] Implementation noise is required to understand the result.
- [ ] Expanded content is unavailable for audit.
- [ ] The compact state hides blocked/pending/failed status.

## 7. Safety Boundaries

Clearly communicate:

- [ ] Whether the run is read-only or patch-capable.
- [ ] Whether a worktree was created.
- [ ] Whether the main repo was untouched.
- [ ] Whether a commit was created.
- [ ] Whether merge/push did or did not happen.
- [ ] Whether postflight validators passed.
- [ ] Whether failed diffs/logs were preserved.
- [ ] Whether an evidence answer is blocked, runnable, pending trace, or
  verified.

Failure if:

- [ ] The UI implies a patch landed when only a diff was created.
- [ ] The UI implies success without validator/postflight status.
- [ ] The UI hides whether an evidence answer is proven or merely runnable.

## 8. Approvals

Dangerous or durable actions must have explicit controls:

- [ ] Commit approval.
- [ ] Merge approval.
- [ ] Push approval.
- [ ] Discard failed worktree.
- [ ] Keep failed worktree.
- [ ] Rerun.
- [ ] Run follow-up.
- [ ] Approve evidence case.
- [ ] Request trace.

V1 may show placeholders or disabled controls if backend actions are not
implemented, but the pattern must exist.

Failure if:

- [ ] Merge, push, approval, or evidence acceptance can happen from ambiguous
  prose.
- [ ] Approval state is only represented by assistant text.

## 9. Message Differentiation

- [ ] User requests are visually distinct from agent responses.
- [ ] Agent identity is scannable without creating a fake persona.
- [ ] Product identity icons are small, calm, and meaningful.
- [ ] Evidence/run/receipt cards are visually distinct from prose bubbles.
- [ ] Final answers are visually separate from evidence cases.

Failure if:

- [ ] User and agent messages blend together.
- [ ] Evidence case and final answer collapse into one blob.
- [ ] Avatars or icons add decorative noise without improving scanability.

## 10. Failure UX

On failure, show:

- [ ] Failure phase.
- [ ] Failed command/check if known.
- [ ] Exit code if known.
- [ ] Error message.
- [ ] Link to failed diff, trace, or evidence receipt if present.
- [ ] Link to stdout/stderr.
- [ ] Next TODOs.
- [ ] Whether worktree/evidence artifacts were preserved.
- [ ] Whether no commit/approval was created.

Failure if:

- [ ] The user sees only `failed`.
- [ ] The user has to hunt through logs to find the failure phase.
- [ ] Failed artifacts are not inspectable.

## 11. Success UX

On success, show:

- [ ] Postflight or trace passed.
- [ ] Branch/commit if created.
- [ ] Changed files or artifacts when available.
- [ ] Report/evidence artifact.
- [ ] Diff/trace artifact.
- [ ] Next TODOs.
- [ ] Merge/push/approval did not happen unless explicitly performed.

Failure if:

- [ ] The UI says `done` without validation context.
- [ ] The UI hides branch, commit, or artifact state.
- [ ] The UI suggests final approval when the system only produced a draft.

## 12. Conversation Behavior

The conversation pane:

- [ ] Shows user requests.
- [ ] Shows main-agent routing or evidence summaries.
- [ ] Shows run/evidence cards.
- [ ] Shows concise success/failure summaries.
- [ ] Does not show raw logs by default.
- [ ] Preserves previous run/evidence context for follow-ups.
- [ ] Supports follow-ups like `show diff`, `why did it fail`, `expand
  evidence`, `request trace`, and `rerun`.

Failure if:

- [ ] The chat becomes a raw terminal transcript.
- [ ] Follow-ups lose context.
- [ ] Prior run/evidence cards cannot be inspected.

## 13. Mobile / Private Workstation Use

- [ ] Works on laptop/tablet widths.
- [ ] Inspector becomes a drawer on narrow screens.
- [ ] Buttons are touch-friendly.
- [ ] Long logs, paths, hashes, citations, and filenames wrap or scroll cleanly.
- [ ] No public sharing features are assumed unless requested.

Failure if:

- [ ] The UI requires a wide desktop monitor.
- [ ] The artifact/evidence inspector is inaccessible on mobile.
- [ ] Long logs or evidence strings destroy layout.

## 14. Copy Quality

Required language:

- [ ] Precise.
- [ ] Operational.
- [ ] Validator-aware.
- [ ] Explicit about uncertainty.
- [ ] Explicit about what happened and what did not happen.

Avoid:

- [ ] `I handled it.`
- [ ] `Everything looks good.`
- [ ] `The agent thought...`
- [ ] `Probably fixed.`
- [ ] `Done` without validation context.

Failure if:

- [ ] Copy claims success without evidence.
- [ ] Copy hides uncertainty.
- [ ] Copy anthropomorphizes the worker instead of reporting operations.

## 15. Anti-Bloat Check

The design must not include:

- [ ] Generic KPI dashboard cards.
- [ ] Decorative charts unrelated to run or evidence decisions.
- [ ] Marketing hero sections.
- [ ] Fake agent productivity metrics.
- [ ] Multiple panels that duplicate the same state.
- [ ] Raw JSON/logs in the main chat.
- [ ] Unused navigation categories.

Failure if:

- [ ] The design looks like a generic SaaS dashboard.
- [ ] The primary task requires scanning irrelevant boxes.
- [ ] Run cards, evidence cases, receipts, traces, and artifacts are not the
  center of the experience.

## Final Gate

A design passes only if all are true:

- [ ] Chat remains the command surface.
- [ ] Structured operational objects are first-class.
- [ ] Scope/routing/evidence state is visible.
- [ ] Artifacts are first-class.
- [ ] Logs are hidden by default but accessible.
- [ ] Safety boundaries are visible.
- [ ] Approvals are explicit controls.
- [ ] Failure inspection is strong.
- [ ] No fake reasoning panels.
- [ ] No dashboard bloat.
