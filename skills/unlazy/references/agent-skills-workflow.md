# agent-skills Workflow Customization

Use `unlazy` in this repository when the task is long, disputed, high-risk, or
has a history of premature stopping. It adds a gate ledger; it does not replace
the project skill, `$agentic-evals`, `$ask`, `$project-watchdog`, or human
approval gates.

## Required Gate Types

For agent-skills work, a ledger should normally include gates for:

- Skill contract read: named `SKILL.md` files were read before action.
- Artifact outcome: the requested local artifact or behavior exists.
- `$agentic-evals`: the retained fixture case ran and its receipt path is named.
- Narrow proof: focused pytest, script validator, live endpoint, or artifact
  readback exercised the changed surface.
- Status boundary: if the immutable goal is not met, the final report must say
  what remains and include `Immutable Goal: NOT_MET` or a concrete blocker.
- Retention: relevant files were staged narrowly, committed, pushed, and remote
  `refs/heads/main` was read back when repo policy requires it.

## Persona Dream Example

For `$persona-dream`, do not let one narrower proof close the research goal.
Separate gates for:

- live audible Horus/Embry dream conversation;
- post-dream journal and spoken journal;
- provider/Kling readiness;
- human listener/perception evidence;
- PD-CORRECTED-GOAL-V1 paired proof;
- `$agentic-evals` regression receipts.

The expected stop state can be valid `NOT_MET` when the remaining gate is a
human listener artifact, paid-call authorization, credential, or external
service state.

## Reporting Rule

Report the gate ids and evidence paths. Do not summarize a gate ledger as
"done" when any required gate remains unmet or abandoned.
