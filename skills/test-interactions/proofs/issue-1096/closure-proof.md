Issue #1096 proof

mocked: no
live: yes

What was exercised:
- Live CDP discovery against `http://127.0.0.1:8775/discovery_defects.html`.
- Generated QID-only manifest replay through `skills/test-interactions/run.sh run`.
- CDP screenshot hook against the seeded fixture.
- Focused Python compile, unit tests, skill sanity, skill validator, and mock-claim checker.

Live discovery command:
`skills/test-interactions/run.sh discover --url http://127.0.0.1:8775/discovery_defects.html --output-dir /tmp/test-interactions-1096-live-20260729T124520Z/discovery --manifest-output /tmp/test-interactions-1096-live-20260729T124520Z/manifest.generated.json --max-depth 2 --max-states 12 --max-actions 40`

Live discovery result:
- states_seen: 4
- actions_run: 40
- bounds: max_depth=2, max_states=12, max_actions=40
- emitted deterministic findings for missing_qid, duplicate_qid, qs_action_missing, title_missing, manifest_uncovered_interactive, keyboard_unreachable, inert_interaction, unexpected_url_drift, console_exception, network_failure, console_error, and focus_return_defect.

Generated manifest replay:
`skills/test-interactions/run.sh run --manifest /tmp/test-interactions-1096-live-20260729T124520Z/manifest.generated.json --output-dir /tmp/test-interactions-1096-live-20260729T124520Z/captures`

Replay result:
- passed: 11
- failed: 0
- warned: 0
- total: 11

Deterministic gates:
- `uv run --project skills/test-interactions python -m py_compile skills/test-interactions/test_interactions.py skills/test-interactions/cdp_client.py skills/test-interactions/assertions.py skills/test-interactions/visual_evidence.py skills/test-interactions/discovery.py` passed.
- `uv run --project skills/test-interactions python -m unittest discover -s skills/test-interactions/tests -v` passed, 10 tests.
- `skills/test-interactions/sanity.sh` passed.
- `python3 skills/best-practices-skills/scripts/validate_skill.py skills/test-interactions` passed with one pre-existing `.venv` warning.
- `python3 scripts/check_mock_evidence_claims.py` passed, 569 files checked.

Browser proof:
- `~/.codex/hooks/verify-ui-cdp.sh --url http://127.0.0.1:8775/discovery_defects.html --name test-interactions-1096-discovery-fixture`
- screenshot: `skills/test-interactions/proofs/issue-1096/cdp-screenshot.png`
- readback: `skills/test-interactions/proofs/issue-1096/cdp-read.json`

Durable artifacts:
- `skills/test-interactions/proofs/issue-1096/receipt.json`
- `skills/test-interactions/proofs/issue-1096/discovery-inventory.json`
- `skills/test-interactions/proofs/issue-1096/discovery-findings.jsonl`
- `skills/test-interactions/proofs/issue-1096/state-graph.json`
- `skills/test-interactions/proofs/issue-1096/manifest.generated.json`
- `skills/test-interactions/proofs/issue-1096/results.json`
- `skills/test-interactions/proofs/issue-1096/visual-findings.jsonl`

What remains unverified:
- Arbitrary application exhaustive state exploration is outside this ticket's non-goals.
