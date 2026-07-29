Issue #1097 proof

mocked: no
live: yes

What was exercised:
- Fresh live CDP discovery against `http://127.0.0.1:8775/discovery_defects.html`.
- `ticket-findings` preview mode through `skills/test-interactions/run.sh`.
- `ticket-findings` apply-confirmed mode through `skills/test-interactions/run.sh`, delegated to `skills/ticket/run.sh`.
- GitHub issue read-back for the created issue.
- Duplicate suppression against the same source fingerprint after the issue existed.
- CDP screenshot hook against the seeded fixture.

Live source-finding command:
`skills/test-interactions/run.sh discover --url http://127.0.0.1:8775/discovery_defects.html --output-dir /tmp/test-interactions-1097-live-20260729T125800Z/discovery --manifest-output /tmp/test-interactions-1097-live-20260729T125800Z/manifest.generated.json --max-depth 1 --max-states 4 --max-actions 12`

Source finding:
- artifact: `skills/test-interactions/proofs/issue-1097/one-finding.jsonl`
- normalized fingerprint: `c4d0f09bbe52e68ec88f77f4`
- finding kind: `missing_qid`

Preview result:
- command used `--policy preview`
- candidate_count: 1
- preview_count: 1
- created_count: 0
- artifact: `skills/test-interactions/proofs/issue-1097/preview-result.json`

Apply-confirmed result:
- command used `--policy apply-confirmed --max-apply 1`
- created_count: 1
- created issue: https://github.com/grahama1970/agent-skills/issues/1098
- read-back verified: true
- artifact: `skills/test-interactions/proofs/issue-1097/apply-result.json`

Created issue read-back:
- artifact: `skills/test-interactions/proofs/issue-1097/created-issue-1098-readback.json`
- read-back body contains target `skills/test-interactions`, route `backend_python_or_skill_runtime`, agent `coder`, replay command, required proof section, source fingerprint, and evidence path.

Duplicate suppression:
- command reran `--policy preview` for the same source finding after #1098 existed.
- duplicate_count: 1
- preview_count: 0
- created_count: 0
- artifact: `skills/test-interactions/proofs/issue-1097/duplicate-result.json`
- proposed comment artifact: `skills/test-interactions/proofs/issue-1097/ticket-duplicate-comments.json`

Deterministic gates:
- `uv run --project skills/test-interactions python -m py_compile skills/test-interactions/test_interactions.py skills/test-interactions/cdp_client.py skills/test-interactions/assertions.py skills/test-interactions/visual_evidence.py skills/test-interactions/discovery.py skills/test-interactions/ticket_integration.py` passed.
- `uv run --project skills/test-interactions python -m unittest discover -s skills/test-interactions/tests -v` passed, 18 tests.
- `skills/test-interactions/sanity.sh` passed.
- `python3 skills/best-practices-skills/scripts/validate_skill.py skills/test-interactions` passed with one pre-existing `.venv` warning.
- `python3 scripts/check_mock_evidence_claims.py` passed, 570 files checked.

Browser proof:
- `~/.codex/hooks/verify-ui-cdp.sh --url http://127.0.0.1:8775/discovery_defects.html --name test-interactions-1097-ticket-fixture`
- screenshot: `skills/test-interactions/proofs/issue-1097/cdp-screenshot.png`
- readback: `skills/test-interactions/proofs/issue-1097/cdp-read.json`

What remains unverified:
- This issue does not close, lease, block, release, or otherwise mutate lifecycle state for generated repair issues. Created issue #1098 remains open for the normal repair workflow.
