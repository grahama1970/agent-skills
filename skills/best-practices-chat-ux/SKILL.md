---
name: best-practices-chat-ux
description: >
  Best practices for designing, reviewing, and implementing operator chat,
  evidence chat, run-card chat, artifact-inspector chat, and compliance-review
  chat surfaces. Use when users ask for chat UX, operator console UX, agent run
  UX, evidence receipts, trace cards, artifact drawers, progressive disclosure,
  or dashboard-drift prevention.
triggers:
  - best practices chat ux
  - chat UX
  - operator chat
  - evidence chat
  - agent run card
  - artifact inspector
  - receipt card
  - trace card
  - dashboard drift
  - chat command surface
  - progressive disclosure chat
  - subagent control plane
  - compliance chat interface
provides:
  - chat-ux-guidelines
  - operator-chat-patterns
  - evidence-chat-patterns
  - run-card-patterns
  - artifact-inspector-patterns
  - progressive-disclosure-rules
  - dashboard-drift-guards
composes:
  - best-practices-react
  - best-practices-codex-design
taxonomy:
  - design
  - ui
  - chat
  - operator-experience
  - evidence
  - validation
disciplines:
  - engineering-standards
  - ui-design-engineering
---

# Chat UX Best Practices

Use this skill for private operator chat, evidence review chat, agent delegation
chat, and compliance-oriented chat surfaces. These interfaces are not consumer
chatbots and not generic dashboards. The chat is the command surface; structured
run, evidence, trace, receipt, and artifact objects are the operational surface.

This skill was created from the local `chat-operator-ux` guidance and generalized
so it can apply to SPARTA Chat, PDF Lab, subagent control planes, evidence-case
review, and similar agent-operated tools.

## Core Doctrine

1. **Do not build dashboard-first chat.** The default surface should be a
   focused conversation with structured operational objects, not KPI cards,
   decorative charts, or broad dashboard sections.
2. **Treat operational objects as first-class UX.** Runs, evidence cases,
   receipts, traces, artifacts, approvals, and validation results should render
   as inspectable cards or panels, not as prose-only assistant text.
3. **Keep routing and scope auditable.** The human should see which project,
   artifact, evidence case, skill, worker, mode, or validation path the system
   used.
4. **Render typed events by type.** Status events belong in timelines, artifacts
   in artifact lists, logs in collapsed log views, approvals in controls, and
   errors in visible failure states.
5. **Use progressive disclosure.** The default view answers what happened,
   whether it passed, what changed, and what to do next. Expanded views expose
   full logs, JSON, prompts, events, memory, or source evidence.
6. **Make durable actions explicit.** Commit, merge, push, discard, approve,
   rerun, and similar actions require visible controls, not prose-only
   confirmation.
7. **Never expose private chain-of-thought.** It is acceptable to show run
   timelines, tool calls, evidence summaries, validator results, and operational
   reasoning. Do not render hidden model reasoning or fake reasoning panels.

## Required Chat Structure

Prefer this default structure for operator and evidence chat:

```text
Header: project/case context | mode/status | primary actions
Conversation: user messages, agent summaries, run/evidence cards
Inspector: timeline, receipts, artifacts, logs, approvals, TODOs
Prompt bar: input, upload/attach, mode controls, send
```

On narrow screens, the inspector should become a drawer. The conversation must
remain the command surface.

## Message Differentiation

User and agent messages must be visually distinct without becoming noisy:

- User messages should use a slightly different surface color or alignment.
- Agent messages should use a neutral response surface.
- Product/agent identity may use a small brand icon when it improves scanning.
- Structured objects should have their own treatment distinct from both user and
  agent prose.

For SPARTA-style surfaces, a Spartan shield icon is preferable to a bare `S`
avatar because it encodes product identity without adding another assistant
persona.

## Structured Object Patterns

### Run Card

Use when a chat request delegates execution to a worker or subagent. Show:

- status
- project
- subagent or worker
- mode
- selected skills
- branch/worktree or repo path when applicable
- postflight status
- changed artifacts or files
- next TODOs
- open details action

### Evidence Case Card

Use when a chat answer depends on compliance, evidence, traceability, or source
grounding. Show:

- case ID
- artifact or source document
- technique/control/framework terms
- readiness or blocked state
- numbered claims
- citations/source turns
- trace status
- expand/collapse affordance

The compact state should be scannable. The expanded state should contain the
full audit trail. The final agent answer should remain visually separate from
the evidence case.

### Receipt / Trace Card

Use when the system needs to prove why an answer was allowed, blocked, runnable,
or pending. Show:

- state badge
- source turn
- binding status
- validation gates
- timestamp or run ID
- expandable details

Receipts should stay near the agent response they justify. Do not move them into
a detached dashboard unless the user explicitly asks for a separate audit view.

### Artifact Inspector

Use when a run or evidence object produces durable files. Prioritize:

1. human-readable report or answer
2. diff or evidence trace
3. structured result JSON
4. stdout/stderr logs
5. prompt, events, memory, or skill snapshots

Logs should be available but not primary.

## Interaction Rules

- The running state should be a compact timeline or run card, not a raw terminal
  transcript.
- Failure states must show failure phase, failed check or command, exit code
  when known, available artifacts, and next TODOs.
- Success states must show validation/postflight status and must not imply
  merge, push, approval, or finality unless that action happened.
- Follow-up prompts such as `show diff`, `why did it fail`, `rerun`, or `expand
  evidence` should preserve the relevant run/evidence context.
- Uploads should be explicit when the workflow depends on PDFs, source
  documents, logs, or evidence packets.

## Visual Rules

- Use calm operator-console styling: dark or neutral background, clear borders,
  small status chips, high contrast, and monospace for paths, commands, logs, and
  IDs.
- Keep accent colors limited and semantic.
- Avoid decorative gradients, oversized cards, fake charts, marketing sections,
  and animated clutter.
- Long paths, hashes, filenames, citations, and artifact names must wrap or
  scroll cleanly.
- Interactive controls need visible hover/focus states and useful `title` or
  accessible labels.

## Anti-Patterns

Do not ship chat UX where:

- every event is rendered as an assistant bubble
- raw logs dominate the main conversation
- artifacts are hidden or only downloadable
- approval actions are represented only by prose
- the user cannot tell what project, evidence case, worker, or mode was used
- the chat becomes a generic SaaS dashboard
- the final answer and evidence record collapse into one indistinct blob
- ambiguous terms, controls, artifacts, or framework IDs lack hover/focus
  explanation

## Checklist

Use [references/checklist.md](references/checklist.md) for the full readiness
checklist before implementing or approving an operator/evidence chat design.
