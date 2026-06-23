# PersonaPlex Decision Tree Greenfield Sanity Report

## Scope

This is a `create-architecture` greenfield sanity artifact only. It proves the
WebGPT-created chart/doc bundle was downloaded, extracted, and internally
validated. It does not prove the live PersonaPlex wrapper is implemented.

## Source Bundle

- WebGPT tab id: `837354889`
- WebGPT URL: `https://chatgpt.com/g/g-p-6a3925407da08191a9a7c47ebd2bc948-orpheus-persona-plex/c/6a3a8d6e-9544-83ea-8287-c7653b6a42aa`
- Surf run dir: `/mnt/storage12tb/skills/ask/outputs/personaplex-chart-create-architecture-surf/personaplex-chart-create-architecture-surf-20260623T1352Z`
- Downloaded zip: `/home/graham/Downloads/personaplex-decision-tree-update-bundle.zip`
- Isolated source zip: `source.zip`
- SHA-256: `d28ae4b1be74f2b2874a8bb4c807382af205fc2845ea8b419607c3e8d6504841`

## Transport Evidence

- `response.receipt.json`: `submitted_to_chatgpt: true`
- `response.meta.json`: `raw_contains_sentinel: true`
- `response.meta.json`: `controlled_tab_id: 837354889`
- `response.meta.json`: `status: recovered_focus_changed`
- `response.meta.json`: `transport_degraded: true`

The response is usable degraded transport evidence because focus changed during
`--no-activate`. It is not clean background-mode proof.

## Bundle Contents

- `reviews/personaplex-deepgram/compliance-memory-decision-tree.dag.json`
- `reviews/personaplex-deepgram/compliance-memory-decision-tree.html`
- `scratch.md`
- `MANIFEST.json`

## Checks

- Zip downloaded locally: pass
- Zip extracted into isolated sanity directory: pass
- Manifest checksums match extracted files: pass
- DAG validation: pass
  - `ok: true`
  - `node_count: 23`
  - `layer_count: 16`
  - `warnings: []`
  - `errors: []`
- Extracted files contain no `TODO implement`: pass
- Extracted files do not retain `personaplex_turns as canonical`: pass
- HTML contains required anchors:
  - `conversation_history`
  - `conversation_history_summaries`
  - `personaplex_sessions`
  - `conversation_audio_artifacts`
  - `non-authoritative`

## Next Gate

Before porting into the repository, inspect the extracted HTML and scratch
content for human alignment. If accepted, copy the three replacement files from
`extracted/` into the real paths and run chart rendering/browser verification.
