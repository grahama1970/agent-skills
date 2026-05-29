# Project Knowledge: ask

**Last updated:** 2026-05-25 15:04 by agent
**Status:** Active development

## Current Understanding

- Project initialized, knowledge tracking started
- 2026-05-20: A real `$ask --deep-review` run against the scillm DAG viewer-editor exposed two deep-review verifier/schema gaps. The prompt now explicitly requires top-level `blocking_issues` and `significant_risks` to include `severity`, `issue`, `evidence`, `evidence_citations`, `impact`, `fix`, and `verification`; the normalizer now backfills missing plain `evidence` from structured citations and filters incomplete section-local notes so they do not masquerade as formal findings. Final rerun `dag-ux-gpt55-round2-final` reached `state: answered`, verdict `SAFE_WITH_CONDITIONS`, verifier `PASS`.
- 2026-05-25: Visible collaborator subagents such as Nico are not one-shot oracle answers and not hidden manual tmux fallbacks. The corrected product contract is that Nico is a third collaborator whose discourse must be surfaced in the project agent terminal and recorded in ask artifacts. Human tmux attachment is optional/debug only; the primary proof is the ask request/status/events plus the actual Nico response text printed by the project agent.

## Recent Decisions

| Date | Decision | Why |
|------|----------|-----|
| 2026-05-20 | Initialize project knowledge | Enable shared human/agent context |
| 2026-05-20 | Deep-review verifier schema must normalize evidence-bearing findings before gating | The DAG UX review runs showed that model outputs may provide structured evidence_citations without a plain evidence field and may emit informal section notes; verifier gates should fail closed but the prompt/normalizer must convert or discard those shapes deterministically instead of requiring manual artifact surgery. |
| 2026-05-25 | Visible Nico collaborator output must be terminal-visible through ask artifacts, not aspirational tmux theater | The human clarified that manual tmux visibility is not required; reliability means the project agent can show Nico's response in this terminal and preserve artifacts. Codex App Server/scillm may be the right primary transport if it returns actual response text reliably; subagent-runner/tmux is only acceptable as an artifact-backed fallback, never a hidden workaround. |

## Open Questions

- [ ] What are the key architectural decisions?
- [ ] What are the known issues?

## Agent Takeover Notes

Current active work: Continue scillm DAG planner-editor visual/browser proof after the ask deep-review verifier repair.\nEvidence pointers: ask runtime status /home/graham/workspace/experiments/agent-skills/skills/ask/.ask_artifacts/runs/dag-ux-gpt55-round2-final/dag-ux-gpt55-round2-final.status.json; final review /home/graham/workspace/experiments/scillm/.ask_artifacts/deep-review/20260520T121424Z/review.md; final review JSON /home/graham/workspace/experiments/scillm/.ask_artifacts/deep-review/20260520T121424Z/review.json; changed files src/ask/deep_review.py and tests/test_deep_review_protocol.py.\nNext action: Capture or build fresh browser proof for the scillm DAG planner-editor showing the review-code fanout row with model, agent, contract, prompt, review level, proof floor, and editable Best-practice skills visible and not clipped.\nBlockers/caveats: examples/exec-graph-debugger currently has no standalone runnable harness; do not claim final DAG UX readiness from code/DOM assertions alone. The ask review verdict is SAFE_WITH_CONDITIONS, not final visual PASS.\nLast verified command/artifact: PYTHONPATH=src pytest -q tests/test_deep_review_protocol.py tests/test_deep_review_section_citations.py tests/test_deep_review_telemetry.py => 14 passed; dag-ux-gpt55-round2-final status.json => state answered, verifier PASS.
- Current active work: repair ask visible-subagent routing so 'Ask/Bring Nico' produces an actual Nico response in the project-agent terminal with request/status/events proof, rather than only reporting a running worker or relying on manual tmux send-keys. Evidence pointers: skills/ask/src/ask/ask.py visible_subagent route and _run_visible_subagent_scillm/_run_visible_subagent_tmux; skills/ask/tests/test_ask_cli_protocols.py visible_subagent tests; skills/scillm/SKILL.md long-running streaming and Codex/App Server boundary; this session's tmux proof showed manual Codex communication works but is not the target contract. Next action: prove or reject Codex App Server for synchronous/observable Nico discourse; if sufficient, make it the ask primary path and print Nico's actual response text. Blockers/caveats: do not claim success from 'worker running' or tmux attach metadata; proof requires actual Nico text in terminal/artifacts. Last verified command/artifact: PYTHONPATH=src uv run pytest tests/test_ask_cli_protocols.py -k 'visible_subagent or visible-nico or Nico' -q => 16 passed, 10 deselected before this project-knowledge correction.

## Key Files

| File | Purpose |
|------|---------|
| PROJECT_KNOWLEDGE.md | Shared project knowledge |
| docs/PROJECT_KNOWLEDGE.md | Existing curated ask project knowledge projection |
| src/ask/deep_review.py | Deep-review prompt, normalization, verifier, and artifacts |
| tests/test_deep_review_protocol.py | Deterministic deep-review verifier regression tests |

## Infrastructure State

<!-- Auto-populated from /project-state --quick -->
