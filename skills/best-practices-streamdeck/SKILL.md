---
name: best-practices-streamdeck
description: >
  Project-specific best practices for the Stream Deck control suite: icon format constraints,
  socket vs config boundaries, widget button lifecycle, page creation via build_page,
  ArangoDB fallback patterns, and NVIS palette compliance.
triggers:
  - best practices streamdeck
  - stream deck
  - streamdeck widget
  - streamdeck button
  - NVIS palette
license: MIT
metadata:
  hardware: Stream Deck XL (32 buttons, 96x96 native, 72x72 rendered)
  defaults:
    icon_format: 72x72 RGB PNG
    socket_path: /tmp/streamdeck_ui.sock
    config_path: ~/.streamdeck_ui.json
    page_indexing: 0-9 static, 10+ dynamic
    palette: nvis (MIL-STD-3009)
    logging: loguru
    cli: typer

provides:
  - best-practices-streamdeck
composes:
  - task-monitor
  - agentic-evals
disciplines:
  - engineering-standards
  - developer-tooling
---

# Stream Deck Best Practices (Project Skill)

Curated rules for building and maintaining the Stream Deck control suite.
Covers hardware constraints, service architecture, and the widget lifecycle.

## Project Architecture

- **streamdeck-ui**: Qt app reading `~/.streamdeck_ui.json`, rendering buttons
- **Socket API**: `/tmp/streamdeck_ui.sock` for real-time updates (fast, no disk)
- **Config file**: `~/.streamdeck_ui.json` for persistent state (slow, locked)
- **Widget services**: background daemons rendering icons on schedule
- **Context monitor**: polls environment every 2s, switches pages via templates
- **ArangoDB**: memory graph for pages/buttons (optional, filesystem fallback)

## When to Apply

Use this skill whenever you:
- Create or modify Stream Deck pages, buttons, or templates
- Build a new widget renderer or data source
- Write scripts that update the deck config
- Modify the socket API, context monitor, or page builder
- Work with icons, palettes, or the NVIS display layer

## Categories (priority order)

1. **Hardware Constraints** — icon format, button count, display limits
2. **Socket vs Config** — when to use each, race condition avoidance
3. **Widget Lifecycle** — self-updating buttons, render scripts, cache busting
4. **Page Management** — creation, indexing, context rules, anticipation
5. **ArangoDB Integration** — fallback patterns, collection conventions
6. **NVIS Palette** — MIL-STD-3009 colors, font stack, rendering primitives

## Dynamic Page Contract

Dynamic Stream Deck pages must use the standard request-to-deployment pipeline;
do not bespoke-code page generators for voice, SPARTA Explorer, meeting mode,
or task-specific control surfaces.

Required flow:

```text
streamdeck.dynamic_page_request.v1
  -> bounded recipe/action plan
  -> deterministic manifest compiler
  -> staged preview
  -> hash-bound approval
  -> explicit deployment
```

Voice and SPARTA adapters may emit only semantic requests with source,
request_id, intent_text, context_refs, transcript_confidence, and requested
lifetime. They must not emit buttons, executable commands, shell snippets,
Stream Deck page indexes, socket/config writes, display settings, audio
settings, process/service operations, or filesystem/network side effects.

Dynamic manifests must be compiled from a versioned recipe catalog and action
catalog. Button behavior is bound through stable dispatcher identities such as
`streamdeck-cli action invoke --binding <binding_id>`; generated manifests must
not contain arbitrary shell. Keep identities stable and explicit:

- `qid`: stable logical control identity
- `action_id`: stable semantic action identity
- `binding_id`: compiler-owned executable binding
- `page_instance_id`: staged page instance identity
- `deployment_id`: approved deployment identity
- `event_id`: emitted action receipt identity

Use the lifecycle states `REQUESTED`, `NEEDS_CONFIRMATION`, `RESOLVED`,
`STAGED`, `APPROVED`, `DEPLOYED`, `BLOCKED`, `REJECTED`, `SUPERSEDED`,
`EXPIRED`, `ROLLBACK_APPROVED`, `ROLLED_BACK`, and `REVOKED`. Staging,
preview, approval, and diff commands are `external_effects=false` operations:
they must not open `/tmp/streamdeck_ui.sock`, mutate `~/.streamdeck_ui.json`,
restart services, or touch the live deck.

Pages `0-9` are static/manual pages. Dynamic pages use `10+`, leases, ownership
metadata, compare-and-swap deployment, and rollback receipts. Dynamic page
generation must deny by default. Reject requests or recipes that try to control
KDE, KWin, KDED, Plasma, X11, displays, global scale, audio, windows, processes,
services, sudo, shell pipes, command chaining, redirection, arbitrary
filesystem/network writes, `xrandr`, `kscreen-doctor`, `nvidia-settings`,
`keys`, or `write` primitives. Meeting-off buttons must be receipt-only unless
they call an already-cataloged safe action.

SPARTA and memory-backed context must pass explicit context ids or bounded,
cached projections. Do not put broad Memory `/list`, ArangoDB scans, graph
hydration, or dynamic recipe discovery in the UI request path.

Every change to dynamic-page request handling, recipe/action catalogs,
compiler output, approval/deploy state, or action dispatch must add or
strengthen `fixtures/agentic_eval.json`. Live hardware, voice, SPARTA, or
physical-button claims require a separate canary receipt and must be reported
as unverified until that live proof exists.
