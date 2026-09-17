# agent-skills integration run — 2026-09-17

Executed on the primary agent-skills checkout with the current origin/main
setup-project and agentic-evals contracts (`AGENT_SKILLS_ROOT`).

| Gate | Result |
|---|---|
| `bash sanity.sh` (core behavioral suite) | 88 passed |
| `scripts/verify.sh --profile full --trials 3 --samples 128` | 3/3 trials exit 0; browser journey EXECUTED, readback PASS |
| setup-project `plan` (native) | PASS |
| setup-project `audit` (native) | FAIL, fail-closed: acceptance/battle/create-report chain not yet produced by owning workflows (by design) |
| agentic-evals mechanisms (native) | READY — 27/27 live trials, mocked=false |
| agentic-evals release (native) | USABLE_WITH_GAPS — 12 PASS, 0 FAIL, efficacy BLOCKED pending real human study |
| best-practices-skills validator | PASS |
| ruff (project profile) | clean |

Integration repairs (all root-cause, retained in git): CSP-safe Playwright waits;
premature `revokeObjectURL` removed (aborted export downloads); snap-Chromium
avoidance (namespaced /tmp yields empty artifacts); fixtures upgraded to the
current runner contract (`claim_semantics`, live-path commands); `sanity.sh`
repointed at the real core test files (it previously named two nonexistent
files and silently ran nothing); `python-dotenv` + `load_dotenv` added at env
entrypoints; venv redirected to /mnt/storage12tb via `UV_PROJECT_ENVIRONMENT`;
`uv.lock` resolved and committed.

Not established by this run: real-human/any-provider detection efficacy, Docker
deployment, acceptance/battle/create-report artifacts, independent human review,
accessibility. Release readiness remains NOT_ESTABLISHED.
