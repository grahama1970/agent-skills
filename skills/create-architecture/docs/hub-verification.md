# Source-Grounded Hub Verification

Verified locally on 2026-09-06 in the primary agent-skills checkout on main.

## Implemented Boundary

- The invoking agent reads code, chooses a semantic view, then a specialist.
  The CLI inventories sources; it does not infer architecture from filenames.
- Executable draft routes: PHART, create-svg, create-figure, GSN.
- Agent handoffs: application-owned React Flow, Excalidraw, project-infographic.
  No new generic React Flow adapter or Archify integration.
- Native inputs stay specialist-owned. Typed requests bind current source
  fingerprints and artifact hashes; outputs remain drafts.
- SVG previews compose create-svg's existing viewer. Legacy human mutation
  gates and execution-lock validation remain in place.

## Receipts

From the repository root:

```bash
./skills/agentic-evals/run.sh run skills/create-architecture/fixtures/agentic_eval.json --output /mnt/storage12tb/skills/create-architecture/outputs/hub-agentic-eval-final.json
```

Report readback: run `a1748422b5e4`, readiness `READY` for the declared local
draft-delivery scope; 4 cases, 12 trials, all passed. `mocked=false`,
`live=true`. SHA-256 of report:
`da2f077547183baa3b2dc418b6e376cdbbd8f4af949d4185ce9b99ac27f2d63e`.

Commands traverse the real run.sh and real specialist entrypoints, using
current production source, not canned diagram fixtures. Oracles separately
read receipts, hash file bytes, parse SVG labels, and check that rejected
requests did not publish output. Coverage includes caller-relative/default
targets, seven routes, stale evidence, cycles, unknown edges, identity
collisions, selector injection, non-executable handoffs, and preserving
existing bundles. GSN uses actual memory-backed control `AC-1`, not dry-run.

Additional checks:

- `uv tool run ruff check` on hub.py, hub_models.py, hub_cli.py and
  scripts/eval_hub.py: all checks passed. Every modified/new Python module
  is below 800 lines.
- From this skill: `uv run --project . --with pytest python -m pytest tests -q`
  with `UV_PROJECT_ENVIRONMENT=/mnt/storage12tb/skills/create-architecture/.venv`:
  nine existing regression tests passed. These are supplementary, not live proof.
- `best-practices-skills/scripts/validate_skill.py skills/create-architecture`:
  no errors, three warnings for the pre-existing capability names absent from
  the shared vocabulary. The shared registry has unrelated edits and was left
  untouched. The local .venv now resolves to storage12tb.
- Fresh Surf preview captures inspected:
  `/mnt/storage12tb/skills/create-architecture/outputs/hub-preview-surf.png` and
  `hub-preview-bottom-surf.png`. All four import labels are readable; vertical
  scrolling remains necessary in the short viewport. This is observation of
  one draft, not the create-svg human acceptance gate.
- Pi and Codex skill paths resolve through symlinked parents to the primary
  checkout; no provider-local copies were added.

## Proof Boundary

The eval manifest is retained, but renderer input authority is live source and
GSN memory data. No renderer/service is mocked. This does not establish that
an arbitrary agent correctly interprets every codebase, that every GSN claim
is true, or that interactive React Flow/Excalidraw service workflows work.
Those handoffs require the owning skill's live evidence. All hub receipts
remain `DRAFT`, with semantic and visual approval explicitly not established.
