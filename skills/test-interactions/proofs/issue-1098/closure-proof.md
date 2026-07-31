# Issue 1098 Closure Proof

Issue: https://github.com/grahama1970/agent-skills/issues/1098

Target: `skills/test-interactions`

## Source Finding

The issue body names source fingerprint `c4d0f09bbe52e68ec88f77f4`, but the source artifact at `/tmp/test-interactions-1097-live-20260729T125800Z/one-finding.jsonl` contains fingerprint `fdaf36f7e4a9db0c59f9c787`.

Retained source artifact: `skills/test-interactions/proofs/issue-1098/source-one-finding.jsonl`

Source finding kind: `missing_qid`

## Repair

Updated `skills/test-interactions/fixtures/discovery_defects.html` so the previously unmanifestable `Missing QID` button now has:

- `data-qid="fixture:missing-qid"`
- `data-qs-action="FIXTURE_MISSING_QID"`
- `title="Exercise repaired QID control"`

## Live Proof

Served the fixture from this `main` checkout:

```bash
cd /home/graham/workspace/experiments/agent-skills-main-clean/skills/test-interactions/fixtures
python3 -m http.server 8775 --bind 127.0.0.1
```

Replay command:

```bash
skills/test-interactions/run.sh discover --url http://127.0.0.1:8775/discovery_defects.html --output-dir /tmp/test-interactions-1098-main-20260729/discovery --manifest-output /tmp/test-interactions-1098-main-20260729/manifest.generated.json --max-depth 1 --max-states 4 --max-actions 12
```

Replay result:

- command exit: `0`
- `finding_count`: `25`
- `missing_qid_count`: `0`
- `manifest_uncovered_missing_qid_count`: `0`
- generated manifest includes `fixture:missing-qid`
- generated manifest does not include `.missing-qid` selector fallback

Retained artifacts:

- `skills/test-interactions/proofs/issue-1098/discovery-findings.jsonl`
- `skills/test-interactions/proofs/issue-1098/discovery-inventory.json`
- `skills/test-interactions/proofs/issue-1098/state-graph.json`
- `skills/test-interactions/proofs/issue-1098/manifest.generated.json`
- `skills/test-interactions/proofs/issue-1098/served-main-fixture.html`
- `skills/test-interactions/proofs/issue-1098/cdp-read.json`
- `skills/test-interactions/proofs/issue-1098/cdp-fixture.png`

## CDP Readback

Command:

```bash
~/.codex/hooks/verify-ui-cdp.sh --url http://127.0.0.1:8775/discovery_defects.html --name test-interactions-1098-main-fixture
```

Result:

- command exit: `0`
- screenshot: `/tmp/codex-ui-verification/agent-skills-main-clean/test-interactions-1098-main-fixture/20260729T185059Z.png`
- read JSON: `/tmp/codex-ui-verification/agent-skills-main-clean/test-interactions-1098-main-fixture/20260729T185059Z.read.json`
- visual inspection: fixture page is visible and the `Missing QID` button is present in the control row
- CDP readback element index `5`: `tag=button`, `text=Missing QID`, `qid=fixture:missing-qid`

## Focused Checks

```bash
python3 skills/test-interactions/tests/test_discovery.py
```

Result: `Ran 6 tests in 0.000s`, `OK`

```bash
python3 scripts/check_mock_evidence_claims.py
```

Result: `OK: checked 968 test file(s); no mock+proof claim violations`

Attempted:

```bash
uv run --project skills/test-interactions python -m pytest skills/test-interactions/tests/test_discovery.py -q
```

Result: environment lacks pytest: `No module named pytest`. The same unittest file passed through its built-in `unittest` entrypoint.

## Evidence Classification

- mocked: `no`
- live: `yes`
- exercised: live CDP discovery and live CDP browser readback against a local HTTP server started from the `main` checkout
- remains unverified: unrelated discovery findings still present in the intentionally defective fixture
