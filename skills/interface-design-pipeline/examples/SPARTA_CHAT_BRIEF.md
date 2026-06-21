# Sparta Chat redesign brief

## User job

Ask a space-cyber/compliance question, read the answer immediately, and inspect the evidence or generated artifact only when deeper adjudication is needed.

## Product model

```text
ChatWell = readable conversation + compact evidence/artifact receipts
EvidenceWorkspace = full evidence-case adjudication
ArtifactPanel = full figure/table/PDF/source preview
```

Evidence-first means the answer is backed by inspectable evidence. It does not mean the full evidence case is dumped into the thread.

## Required message order

1. User question or heard voice transcript.
2. Assistant synthesis: answer, clarify, or deflect prose.
3. Compact evidence receipt.
4. Optional deduplicated artifact receipt or preview.
5. Composer.

## Evidence receipt

The receipt must show one case ID, one verdict/action state, one reason, one summary line, one artifact/provenance line, and one primary `Open in workspace` action. Full gates, claims, citations, hashes, reviewer controls, raw JSON, and full figures/tables belong outside chat.

## Required interface states

- default conversation
- running/delegated work
- satisfied answer
- inconclusive/clarify
- blocked/deflect
- artifact preview
- evidence workspace open
- narrow-screen inspector drawer

## Required interaction contracts

Preserve or add stable qids for the chat panel, thread, heard query, evidence receipt, open-workspace action, artifact receipts, artifact panel, evidence workspace tabs, composer input, and transmit action. Keyboard focus, visible focus rings, accessible names, and explicit failure states are required.

## Visual direction

Dark NVIS/Embry tactical surfaces; calm density; compact semantic status colors; monospace for IDs, paths, hashes, and commands. The conversation remains dominant. Use progressive disclosure and one primary action per structured object.

## Anti-goals

- no legacy dashboard/chat hybrid
- no KPI or health-strip theater
- no full audit console in the thread
- no generic purple AI-assistant styling
- no cloning ChatGPT, Claude, Gemini, Linear, Raycast, or other product chrome
- no invented backend status, coverage, or approval values
- no raw terminal transcript as the running state
