---
name: agent-ecosystem
description: >
  Canonical map and shared contracts for the agent-governance ecosystem: the
  pi.receipt_envelope.v1 boundary envelope, the component graph, and the rules
  for which component owns which schema. Use when wiring a skill or extension
  into the shared receipt world, when asking how shame, triage-error, tau, ask,
  project-watchdog, ops-herdr, ponytail, and Memory fit together, or when
  validating an envelope.
provides:
  - receipt-envelope-schema
  - ecosystem-map
composes:
  - triage-error
  - shame
  - tau
  - ask
  - project-watchdog
  - ops-herdr
complies:
  - best-practices-skills
taxonomy:
  - observability
  - engineering-standards
disciplines:
  - engineering-standards
  - agentic-orchestration
---

# Agent Ecosystem

One layered governance loop. Each component owns exactly one concern; they
couple only through typed JSON contracts, never by importing each other's
state machines.

## The graph

![Agent-governance ecosystem](./ecosystem.svg)

Rendered with $create-svg (`scene.yml` is the source; regenerate with
`skills/create-svg/run.sh render skills/agent-ecosystem/scene.yml skills/agent-ecosystem/ecosystem.svg`).
Until the machine-readable membership manifest from issue 1584 exists and
generates them, the SVG above and the mermaid block below are NON-NORMATIVE
illustrations; the ownership table and member `## Ecosystem` sections are the
normative topology.


```mermaid
flowchart TB
    subgraph SHAPE[Generation shaping]
        PONY[ponytail\nYAGNI ladder, no receipts]
    end
    subgraph TURN[Turn layer - Pi session]
        SHAME[shame extension\npi.agent_status.v1\nvalidate, compile, swallow]
        TRIAGE[triage-error\nfailure vocabulary\ncode, cause, next_command]
    end
    subgraph WORK[Workflow layer]
        ASK[ask\ncompiles intent to DAG contracts]
        TAU[tau\nexecutes DAGs, owns acceptance\ntyped node receipts, goal_hash]
    end
    subgraph OPS[Operations layer]
        WD[project-watchdog\ncron dispatch, leases,\nproof gates, tick receipts]
        HERDR[ops-herdr bridge\ninbox, quiescence,\nTTL dead-letters]
    end
    MEM[(Memory\ntraining examples,\ntriage resolutions,\nproject knowledge)]

    PONY -.-> SHAME
    SHAME -->|failed.triage.code| TRIAGE
    SHAME -->|needs_* compiled commands| ASK
    ASK -->|tau.dag_contract.v1| TAU
    TAU -->|node receipts / handoff v2 carries status| SHAME
    WD -->|ticket_repair via ask| ASK
    WD -->|reads verdicts| TAU
    HERDR -->|dead-letter triage codes| TRIAGE
    SHAME -->|labeled examples| MEM
    TRIAGE -->|minted codes| MEM
    TAU -->|post-run export of bad node receipts| MEM
```

## Ownership table

| Component | Owns | Emits | Consumes |
| --- | --- | --- | --- |
| triage-error | failure vocabulary (`failure_codes.json`) | `{code, cause, next_command}` | raw error text from any layer |
| shame | turn status (`pi.agent_status.v1`) | status objects, training examples | triage codes, human labels |
| ask | intent-to-DAG compilation | `tau.dag_contract.v1`, recovery packets | status escalation payloads |
| tau | DAG execution and acceptance | node receipts, `tau.agent_handoff.v1/v2`, goal hashes | DAG contracts, embedded status objects |
| project-watchdog | scheduled dispatch | tick receipts, proof gates, locks | GitHub tickets, tau verdicts |
| ops-herdr | cross-session transport | inbox records, dead-letters | triage codes |
| ponytail | generation minimalism | `ponytail:` debt comments (not receipts) | nothing from the receipt world |
| Memory | recall | store/recall readback responses (not envelope receipts; recalls are observations, never wrapped) | everything durable |

## pi.receipt_envelope.v1 - the boundary envelope

Wrap a payload in the envelope ONLY at authority-changing boundaries:
dispatch, handoff, acceptance, escalation, closure, durable failure.
Internal objects stay unwrapped (reviewed YAGNI ruling: no universal event
bus, no envelope on every artifact).

```json
{
  "schema": "pi.receipt_envelope.v1",
  "receipt_id": "stable-id",
  "payload_schema": "pi.agent_status.v1",
  "producer": "shame",
  "emitted_at": "RFC3339",
  "goal_hash": "sha256:<64hex> (optional)",
  "parent_refs": [
    {"receipt_id": "id", "expected_schema": "s", "expected_producer": "p", "digest": "sha256:<64hex> (optional)"}
  ],
  "triage_code": "catalog or minted code (optional)",
  "payload": {}
}
```

Validate with:

```bash
skills/agent-ecosystem/run.sh validate <envelope.json>
echo '{...}' | skills/agent-ecosystem/run.sh validate -
```

Rules enforced by `scripts/receipt_envelope.py` (pydantic, extra=forbid):

- `triage_code`, when present, must be a triage-error catalog code or a minted
  `*_unclassified_<8hex>` code - same rule as `pi.agent_status.v1.failure`.
- `goal_hash` and `parent_refs[].digest` must be `sha256:` + 64 lowercase hex.
- `parent_refs` require `goal_hash`: an evidence edge without a shared goal is
  untrusted and fails validation.
- Pydantic proves STRUCTURE only. Reference RESOLUTION is a separate
  consumer-side step with four mandatory checks: the referenced receipt exists;
  its schema equals `expected_schema`; its producer equals `expected_producer`;
  and `resolved_parent.goal_hash == envelope.goal_hash` (a present hash is not
  a shared goal until compared). Digest verification applies when `digest` is
  set. A structurally valid envelope is not yet a trusted one.
- `payload.schema` is REQUIRED in every wrapped payload and must equal the
  envelope `payload_schema`; an anonymous payload fails validation.
- Field-set changes to any `extra=forbid` schema are breaking by construction;
  they require a new schema version, never an in-place edit.

## Shared JSON field conventions

The fields below are the actual shared surface. A component "shares" a field
when it emits or validates the same name, shape, and semantics as the owner.

| Field | Shape | Owner | Shared by |
| --- | --- | --- | --- |
| `schema` | versioned id, e.g. `pi.agent_status.v1` | each schema owner | every contract object; version bumps are additive-or-new-name |
| `code` (triage) | catalog entry or `<prefix>_unclassified_<8hex>` | triage-error | shame `failure.triage.code`, envelope `triage_code`, herdr dead-letters, ask recovery packets |
| `cause` / `next_command` | plain string / exact runnable command | triage-error | every consumer of a triage classification; `next_command` is also the shame `continuing` keep-going field |
| `goal_hash` | `sha256:` + 64 lowercase hex | tau (immutable goal packet) | shame status (optional), envelope (optional), every tau node receipt |
| `verified[]` | `{command, result}` pairs | shame | done-state proof everywhere a status object is embedded |
| `proof[]` | concrete paths/URLs/ids | shame | status objects; watchdog proof gates name the same artifacts |
| `parent_refs[]` | `{receipt_id, expected_schema, expected_producer, digest?}` | agent-ecosystem envelope | escalation evidence (replaces ad hoc paths in `needs_webgpt`) |
| `producer` / `receipt_id` / `emitted_at` | string / stable id / RFC3339 | agent-ecosystem envelope | any boundary-wrapped receipt |
| `payload_schema` | versioned id; must equal `payload.schema` when the payload declares one | agent-ecosystem envelope | any boundary-wrapped receipt |
| terminal verdicts | `PASS FAIL BLOCKED NEEDS_ATTENTION` | tau | ask joins, watchdog proof gates, stream monitors |
| `recoverable` / `not_this` | bool / exclusion list | triage-error catalog | consumers deciding retry vs escalate |

### triage-error conventions (normative here, implemented there)

1. One raw signal maps to ONE `{code, cause, next_command}`; a generic code at
   a layer boundary is a bug, not a classification.
2. Catalog entries live in `skills/triage-error/failure_codes.json` with
   `{code, layer, match[], cause, next_command, recoverable, not_this[]}`.
   Matching is deterministic: normalization is exactly
   `" ".join(text.lower().split())` (lowercase, all whitespace runs collapsed
   to single spaces, ends trimmed); an entry matches when ANY of its `match[]`
   tokens (also lowercased) is a substring of the normalized signal; when
   `--layer` is given, entries with a different `layer` are skipped; the FIRST
   matching entry in file order wins. Never regex, never LLM judgment.
   Prohibited as terminal classifications (they are symptoms, not causes, and
   must be re-triaged from the underlying signal): `NEEDS_ATTENTION`,
   `BLOCKED`, `browser_handler_timeout`, `unknown_error`, `generic_failure`,
   and any bare terminal verdict word.
3. Unmatched signals mint `<layer-or-unknown>_unclassified_<8hex>` where the
   8 hex chars are the first 8 of sha256 over the normalized signal text, so
   the same signal always mints the same code. Minting opens the ticket +
   agentic-eval + memory loop. Recurrence threshold: the SECOND observation of
   the same minted code triggers promotion or aliasing. Alias representation:
   a top-level `aliases` map in the catalog file maps minted code -> canonical
   code; because minting is deterministic over the normalized signal, a
   recurring signal re-mints the same code and the classifier resolves it
   through the map to the canonical entry (recorded as `aliased_from`); the
   minted code is never a second canonical identity. The ticket/eval/memory
   side effects are idempotent per minted code (keyed by the code string).
4. Every ecosystem component that names a failure uses a catalog or minted
   code. Both pydantic validators (status schema, envelope) enforce this at
   parse time, so an ambiguous label cannot exist in a valid object.

## Design rulings (from the external review)

1. Strictness applies to DECISIONS, not observations. Keep raw evidence
   permissive; keep accepted outcomes strict. A typed `unknown` observation is
   legal; an ambiguous decision is not.
2. Minted `*_unclassified_*` codes get a provisional lifecycle: promote to the
   catalog or alias to an existing code when they recur; never let them sprawl.
3. Schema changes are additive; breaking shape changes get a new version
   (`tau.agent_handoff.v2` pattern), never in-place edits.
4. Do not build: a universal governance event bus; receipts for ponytail
   comments, Memory recalls, or internal retries.

## Membership

A skill or extension joins the ecosystem by adding an `## Ecosystem` section to
its SKILL.md naming: which schemas it produces, which it consumes, and which
boundary events it wraps in the envelope. Current members: shame, triage-error,
tau, ask, project-watchdog, ops-herdr. Ponytail is adjacent by design.
