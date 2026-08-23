---
title: Dynamic Pages Use Semantic Requests And Guarded Deployment
impact: CRITICAL
impactDescription: Dynamic Stream Deck pages can affect hardware and workstation workflows; generation must be staged, approved, bounded, and deny-by-default.
tags: dynamic-pages, voice, sparta, safety, approval, controls
---

## Dynamic Pages Use Semantic Requests And Guarded Deployment

Dynamic pages are task-specific control surfaces built at runtime. They must be
compiled from safe semantic inputs, not generated as ad hoc button JSON or shell
commands.

### Required Pipeline

```text
streamdeck.dynamic_page_request.v1
  -> bounded recipe/action plan
  -> deterministic manifest compiler
  -> staged preview
  -> hash-bound approval
  -> explicit deployment
```

Staging, preview, approval, and diff commands are `external_effects=false`.
They must not open `/tmp/streamdeck_ui.sock`, mutate `~/.streamdeck_ui.json`,
restart services, or touch live hardware. Only the deploy step may talk to the
Layer 1 Stream Deck socket.

### Allowed Adapter Output

Voice and SPARTA adapters may emit semantic request fields only:

- `source`
- `request_id`
- `intent_text`
- `context_refs`
- `transcript_confidence`
- `requested_lifetime`

Adapters must not emit buttons, commands, Stream Deck page indexes, socket
writes, config writes, display actions, audio actions, window actions, service
actions, process actions, filesystem writes, or network writes.

### Compiler And Identity Rules

Use a versioned recipe catalog and action catalog. The resolver selects known
recipes/actions and validates parameters. The manifest compiler creates fixed
dispatcher bindings such as:

```bash
streamdeck-cli action invoke --binding <binding_id>
```

Do not put arbitrary shell in generated manifests. Preserve these identities:

- `qid`: stable logical control identity
- `action_id`: stable semantic action identity
- `binding_id`: compiler-owned executable binding
- `page_instance_id`: staged page instance identity
- `deployment_id`: approved deployment identity
- `event_id`: emitted action receipt identity

### Lifecycle

Use explicit states: `REQUESTED`, `NEEDS_CONFIRMATION`, `RESOLVED`, `STAGED`,
`APPROVED`, `DEPLOYED`, `BLOCKED`, `REJECTED`, `SUPERSEDED`, `EXPIRED`,
`ROLLBACK_APPROVED`, `ROLLED_BACK`, and `REVOKED`.

Pages `0-9` are static/manual pages. Dynamic pages use `10+`, leases, owner
metadata, compare-and-swap deployment, and rollback receipts.

### Denied Primitives

Dynamic page generation must deny by default. Reject any semantic request,
recipe, or manifest that attempts:

- KDE, KWin, KDED, Plasma, X11, display, global scale, audio, window, process,
  service, sudo, arbitrary filesystem, or arbitrary network control
- `xrandr`, `kscreen-doctor`, `nvidia-settings`, raw shell, shell pipes,
  command chaining, redirection, executable paths, `keys`, or `write`
- direct edits of `~/.streamdeck_ui.json`
- direct writes to `/tmp/streamdeck_ui.sock` before explicit approved deploy

Meeting-off buttons must be receipt-only unless they call an already-cataloged
safe action.

### SPARTA And Memory

SPARTA and memory-backed context must pass explicit context ids or bounded,
cached projections. Do not put broad Memory `/list`, ArangoDB scans, graph
hydration, or dynamic recipe discovery in the UI request path.

### Regression Guard

Every change to request handling, recipes, actions, compiler output,
approval/deploy state, or dispatch must update
`fixtures/agentic_eval.json`. Live hardware, voice, SPARTA, and physical-button
claims require separate canary receipts.
