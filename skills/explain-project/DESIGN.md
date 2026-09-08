# Explain Project Design

## Position

`explain-project` is a technical interview cockpit, not a deck. It should feel like a calm flight instrument for explaining code under pressure: one question enters, one reducer chooses the current explainer, and every pane shows the same revision.

## Evidence used

- evidence_status: current_evidence
- surface: `skills/explain-project/ui/src/App.tsx`, `TeleprompterStage.tsx`, `InputRail.tsx`, `EvidenceRail.tsx`, `DiagramStage.tsx`, `IntegrationHealth.tsx`
- checked_at: current agent turn
- artifacts: `assets/readme/cockpit-screenshot.png`, `assets/readme/cockpit-flow.svg`, `assets/readme/cockpit-flow.receipt.json`, `proofs/current-proof-summary.json`

## Audience and job

The primary user is a developer or candidate explaining agent-built work in a live technical interview. They need oversized cues, exact code/proof references, and safe integration controls that do not accidentally start audio capture, run a debugger, or mutate a whiteboard.

## Visual world

Narrative premise: the cockpit behaves like an evidence-bound avionics panel so the presenter can explain one system transition at a time without losing source, proof, or diagram context.

Design rules:

- **Teleprompter first:** the center pane owns attention with large type, 2-4 bullets, and a plain proof boundary.
- **Rails second:** left rail is intake/selection; right rail is evidence and integration state.
- **Revision visible:** the current reducer revision is always surfaced because it is the synchronization contract.
- **Native where sufficient:** range, number, button, and textarea controls stay native unless a verified component dependency earns its keep.
- **No decorative motion:** ArrowLeft/ArrowRight only changes reducer state; debugger and whiteboard effects require explicit controls.
- **High contrast, low flourish:** black/zinc/cyan is used as an instrumentation palette, not a brand claim.

## Component invariants

- Every interactive element must expose `data-qid`, `data-qs-action`, and `title` for `$test-interactions` and Surf-driven checks.
- Adapter receipts must be visible as state changes, not hidden logs.
- Integration health must distinguish `READY`, `PENDING`, `BLOCKED`, and unproven states without implying live proof.
- Diagrams are editable Excalidraw sources first; SVGs are portable previews after compile/render verification.

## Integration boundaries

| Integration | Design stance |
| --- | --- |
| `$ops-excalidraw` | Proposal banner/receipt semantics before mutation; the cockpit can request or ingest proposals, not silently replace a human board. |
| `$debugger` | Prepare/reveal/proof are separate controls. Navigation never runs the debugger. Runtime proof appears only after a validated debugger receipt. |
| `$live-evidence` | Consented listener is upstream. The cockpit accepts typed question candidates and exposes whether evidence came from replay or live capture. |

## Not evaluated

Formal bespoke-design certification, blind visual raters, full responsive stress corpus, and accessibility/performance certification were not run. Current proof is release-risk/developer-tooling proof: deterministic cockpit sync, retained evals, browser build, and adapter receipt contracts.
