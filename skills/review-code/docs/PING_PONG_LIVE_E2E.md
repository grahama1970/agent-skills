# Ping-Pong Live E2E

`tests/test_ping_pong_live_e2e.py` is an opt-in, non-mocked smoke test for the
`review-code ping-pong` controller and the real `/ask` GPT-5.5 High reviewer
boundary.

Run it from the repository root:

```bash
REVIEW_CODE_LIVE_PINGPONG_E2E=1 \
  uv run --project skills/review-code \
  python skills/review-code/tests/test_ping_pong_live_e2e.py
```

The test uses the real review bundle at
`/home/graham/workspace/experiments/pi-mono/local/docs/scratch.md`, invokes
`skills/review-code/run.sh ping-pong`, and requests:

- reviewer: `ask:gpt-5.5`
- reasoning: `high`
- rounds: `1`

It verifies that the composed CLI produces durable `state.json` and
`events.jsonl` artifacts, records the requested and actual GPT-5.5/high route,
preserves the `scratch.md` bundle path, and returns either a terminal review or
a structured clarification/attention state.

This check intentionally does not set `ASK_REVIEWER_CLI` or use a deterministic
fake reviewer. It requires valid live `/ask` credentials and may take several
minutes because it starts a real GPT-5.5 High subagent run.

The test is skipped unless `REVIEW_CODE_LIVE_PINGPONG_E2E=1` is set so it does
not run accidentally in ordinary unit-test loops.
