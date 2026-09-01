---
name: triage-error
description: >
  Turn an ambiguous or generic pipeline error into ONE unambiguous {code, cause,
  next_command}. Classifies a raw error or lane receipt from any skill/layer
  (/ask -> /tau -> {/surf | /scillm}, or any skill) against a canonical failure-code
  catalog; when the signal is ambiguous it mints a deterministic code and can
  compose /ticket (draft or file), /agentic-evals (scaffold a repro), and /memory
  (store the code). Use when a skill surfaces a generic error, when diagnosing a
  failing lane receipt, or when adding a new failure code to the catalog.
triggers:
  - triage error
  - classify error
  - ambiguous error
  - error code
  - failure code
  - unify error messages
  - what error is this
allowed-tools:
  - Bash
  - Read
metadata:
  short-description: Classify ambiguous pipeline errors into unambiguous codes
provides:
  - error-classification
  - failure-code-catalog
  - error-to-ticket-eval-loop
composes:
  - ticket
  - agentic-evals
  - debugger
  - memory
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-security
taxonomy:
  - validation
  - observability
  - self-improvement
disciplines:
  - engineering-standards
  - observability-operations
runtime_self_improvement: basic
---

# triage-error

A generic failure code (`browser_handler_timeout`, `NEEDS_ATTENTION`) at a layer
boundary hides the real cause and fragments diagnosis. `triage-error` is the one
place that maps any layer's raw signal to a canonical `{code, cause,
next_command}` — and, when the signal is genuinely new, opens the loop to pin it
down (ticket + agentic-eval + memory).

## Commands

```bash
./run.sh classify --receipt <lane.meta.json> [--layer surf]      # signal -> code (JSON)
./run.sh classify --text "zip contains 9 files; maximum is 5"    # inline signal
./run.sh triage   --receipt <receipt> --layer surf               # classify + (if ambiguous) act
./run.sh catalog                                                 # list canonical codes
```

`triage`, when the signal is **ambiguous** (no catalog match), mints a
deterministic code and composes:

- **/ticket** — drafts a bug ticket by default; publishes only with `--file`
  (filing a GitHub issue is a publish action, so it is gated).
- **/agentic-evals** — `--scaffold-eval` writes a first-pass repro fixture.
- **/memory** — stores the new code + resolution via `memory/run.sh learn`
  (never touches ArangoDB directly).
- **/debugger** — the human/agent may run it for two focused fix attempts; the
  ticket + eval remain as the durable handoff.

## Catalog

`failure_codes.json` is the source of truth: each entry maps `match` tokens from
any layer to one `{code, layer, cause, next_command, recoverable, not_this}`.
Grow it by adding an entry whenever a minted `*_unclassified_*` code recurs.

## How other skills use it (best-practices-skills mandate)

Any skill surfacing a failure routes the raw signal through triage-error rather
than emitting a bare generic code:

- Python skills: `subprocess` `./run.sh classify --text "<err>" --layer <l>` (or
  import `triage_error.classify`).
- Non-Python skills (e.g. surf cjs/bash): shell out to `./run.sh classify`.

The classifier is language-agnostic (it reads text and returns JSON), so it
covers every skill. Rollout is incremental — pipeline skills (ask/surf/scillm)
first; see `best-practices-skills` for the contract clause.

Files: `triage_error.py` (Typer CLI), `failure_codes.json` (catalog), `run.sh`,
`sanity.sh`, `fixtures/agentic_eval.json`, `tests/`.

## Ecosystem

Member of the agent-governance ecosystem (see `skills/agent-ecosystem/SKILL.md`
for the shared map, mermaid graph, and the `pi.receipt_envelope.v1` boundary
envelope). Produces: `{code, cause, next_command}` classifications, minted codes. Consumes: raw error text from any layer. Envelope-wrapped
boundary events: durable failure (minted-code ticket/eval loop). Failure names come only from the triage-error
catalog or minted `*_unclassified_<8hex>` codes; ambiguous labels are
unrepresentable ecosystem-wide.
