# Interview template (mandatory before authoring a new workflowScript)

Run this as an `$interview` pass with the requesting human or project agent.
A workflowScript authored without these answers recorded is non-compliant with
`best-practices-workflowscript`.

## 1. Goal and scope

- What single outcome does this workflow own? (One sentence.)
- Which repo(s) may it mutate? Exact `owner/name` — and list lookalike repos to
  hard-ban in child prompts.
- What is explicitly out of scope?

## 2. Terminal states

- Name every terminal state (e.g. `ready_to_share`, `blocked_human`,
  `iteration_cap_reached`, `no_provider_capacity`, `done`).
- For `blocked_human`: what exact one-line action does the human take?
- What is the readiness command that proves the goal, run from a clean clone?

## 3. Loop policy

- Does it iterate? What is the default and hard cap, and where does the project
  agent set it (convention: `<repo>/.pi/<workflow>.json`)?
- What re-gates each iteration (readiness check, issue classification)?

## 4. Providers

- Which API models (in fallback order) and which web seats?
- What degrades when a provider dies — skip, substitute (disclosed), or abort?

## 5. Mutation surface and lifecycle

- Which paths may children touch? Which are preserved untouched?
- Who lands (gh-land explicit paths only) and who closes (`$ticket` guarded
  close, never raw label mutation)?
- Is independent review required before landing and before closure? With which
  reviewer family separation?

## 6. Failure policy

- Per-item try/catch and continue, or fail-fast? Which failures abort the run?
- What must never be bypassed (worktree audits, fail-closed gates, proof
  requirements)?

## 7. Visual explainer

- Confirm the `$create-architecture` diagram (lanes → gates → terminal states)
  was reviewed with the human at this interview, not after the first failure.

Record the answers next to the script as `<name>.diagram.md` header notes or in
the repo config file. Re-run the interview whenever a terminal state, mutation
surface, or provider roster changes.
