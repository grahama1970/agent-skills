---
name: captcha
description: >
  Authorization-gated CAPTCHA security evaluation using the pinned ReCAP agent,
  synthetic dynamic CAPTCHA challenges on loopback, Surf transport proof, and
  Ask DAG composition. Use when the user says "evaluate CAPTCHA security",
  "benchmark ReCAP", "test a local CAPTCHA agent", or "measure CAPTCHA robustness".
triggers:
  - evaluate CAPTCHA security
  - benchmark ReCAP
  - local CAPTCHA evaluation
  - test a CAPTCHA agent
  - measure CAPTCHA robustness
  - captcha security benchmark
provides:
  - security-scan
composes:
  - surf
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-security
runtime_self_improvement: basic
taxonomy:
  - security
  - validation
  - browser
  - resilience
  - authorization
allowed-tools:
  - Bash
  - Read
  - Write
disciplines:
  - compliance-security
  - browser-automation
  - agentic-orchestration
---

# captcha

> STOP. Read this entire skill before invoking a live command.

`captcha` is a **defensive research and evaluation skill**, not a general CAPTCHA
bypass utility. It measures a pinned ReCAP agent against ReCAP's synthetic
`dynamic` provider on a literal loopback target. It refuses public hosts,
Halligan/real-provider modes, credentials, proxies, stealth, session reuse, and
ordinary live-site CAPTCHA solving.

When an unrelated browser workflow encounters a CAPTCHA, stop for human handoff.
Do not silently route it through this skill.

## Ownership boundaries

- **Ask owns orchestration.** Ask declares `captcha` in `composes:` and invokes it
  through an `ask.dag.v1` `skill.run` node.
- **captcha owns authorization, bounded execution, and receipts.** No browser or
  model action occurs before a typed authorization PASS.
- **Surf owns browser-transport proof.** Live runs require a validated
  `surf.capabilities.v1` artifact plus an isolated exact-URL navigation,
  challenge-identity observation, screenshot, and created-tab cleanup before
  ReCAP starts.
- **ReCAP owns the benchmark interaction loop.** The approved upstream source is
  pinned in `references/upstream.json`; it is not vendored or auto-updated.

Surf proof establishes the local browser transport contract and proves that a
freshly created Surf window remained on the exact authorized loopback challenge.
ReCAP performs the synthetic benchmark interaction through its own Playwright
runner. Those are separate receipts and must not be conflated.

## DOM-unavailable pointer planning

`captcha` also exposes a deterministic pointer-motion planner for authorized
synthetic drag/click challenges. This is a planning receipt only: it does not
dispatch browser input, does not use cookies or sessions, and does not route
ordinary public-site CAPTCHA encounters through the skill.

The planner incorporates the browser-control lessons from
`captivus/chrome-agent` pinned at
`3b46bb9b09167fe60ab94821dedc9f6e01453014`:

- screenshots and layout metrics are the fallback observation plane when DOM
  nodes, accessibility refs, shadow roots, cross-origin iframe internals, or
  canvas contents are not available;
- target coordinates are expressed first in screenshot pixels, then mapped into
  Chrome viewport CSS coordinates;
- downstream consumers should dispatch trusted viewport-relative input through
  Surf/CDP and then re-observe the page rather than treating a click/drag call
  as proof.

The selected human-mouse-movement package reference is `ghost-cursor`
(`https://github.com/Xetera/ghost-cursor`), chosen on 2026-08-20 because it had
the highest GitHub star count among the searched human mouse-movement packages.
The package is used as a reviewed design reference only. The runtime does not
vendor or execute the package; instead it emits a local, seeded, hashable
`clamped_cubic_b_spline_with_seeded_jitter.v1` path that can be reproduced from
the request.

```bash
./run.sh pointer-plan \
  --manifest /path/to/authorization.json \
  --request fixtures/pointer-motion-request-valid.json \
  --out /tmp/captcha-pointer-plan.json \
  --json

./run.sh pointer-dispatch-plan \
  --manifest /path/to/authorization.json \
  --plan /tmp/captcha-pointer-plan.json \
  --out /tmp/captcha-pointer-dispatch-plan.json \
  --json
```

The manifest gate is the same loopback synthetic authorization gate used by
`plan` and `evaluate`. Public targets, real providers, credentials, stealth,
proxies, and session reuse remain refused.

`pointer-dispatch-plan` does not dispatch input. It validates that the pointer
plan is bound to the current authorization manifest and emits the exact Surf
command that can produce `surf.pointer_dispatch_receipt.v1`. Surf owns browser
transport and input delivery; captcha owns authorization, defensive scope, and
the pointer-plan contract. Post-dispatch observation is mandatory and a Surf
dispatch receipt never proves that a CAPTCHA was solved.

## Safe default

No arguments performs a zero-network readiness report, which makes generic Ask
`skill.run` discovery safe:

```bash
cd skills/captcha
./run.sh
./run.sh status --json
```

Readiness is `PASS` only when Ask declares the composition, Surf is executable,
the storage-backed ReCAP checkout is at the approved commit, and its dedicated
Python runtime exists. Missing evidence is `NOT_ESTABLISHED`, never inferred
success.

## Authorization first

Use JSON manifests conforming to the Pydantic contract and
`references/authorization.schema.json`.

```bash
./run.sh authorization-preflight \
  --manifest /path/to/authorization.json \
  --action plan \
  --receipt-out /tmp/captcha-authorization.json \
  --json
```

Non-negotiable policy:

- `target_url` is the ReCAP dynamic server root and must be literal loopback;
- `model_base_url` must also be literal loopback;
- provider is exactly `dynamic`;
- modes are bounded `once` or `custom` only;
- the manifest is time-bounded and explicitly authorizes each action;
- all ownership, synthetic-only, non-bypass, and defensive-use acknowledgements
  are true;
- ReCAP commit equals the approved pin.

A manifest cannot widen these rules.

## Plan, execute, verify

```bash
# Compile the exact argv, environment-key allowlist, artifacts, and blockers.
./run.sh plan \
  --manifest /path/to/authorization.json \
  --recap-root /mnt/storage12tb/skills/captcha/vendor/ReCAP-Agent \
  --recap-python /mnt/storage12tb/skills/captcha/vendor/ReCAP-Agent/.venv/bin/python \
  --output-root /mnt/storage12tb/skills/captcha/outputs \
  --out /tmp/captcha-plan.json \
  --json

# Live effects require both manifest authorization and --execute.
./run.sh evaluate \
  --manifest /path/to/authorization.json \
  --recap-root /mnt/storage12tb/skills/captcha/vendor/ReCAP-Agent \
  --recap-python /mnt/storage12tb/skills/captcha/vendor/ReCAP-Agent/.venv/bin/python \
  --output-root /mnt/storage12tb/skills/captcha/outputs \
  --execute \
  --json

# Re-hash and validate a completed or blocked run without re-execution.
./run.sh verify --run-dir /mnt/storage12tb/skills/captcha/outputs/<run-id> --json
```

Generated evidence includes `request.json`, authorization and plan receipts,
Surf capabilities, `surf-target-preflight.json`, its PNG screenshot, independent
HTTP target and model-catalog preflights, append-only events, digest-bound status,
ReCAP stdout and stderr, the upstream summary, and
`captcha.run-receipt.json`. A `PASS` claim is
bounded to the exact commit, manifest, local model, synthetic tasks, and hashes
recorded by that run.

`pointer-plan` emits `captcha.pointer_motion_plan.v1`, including the manifest
digest, coordinate mapping, source-package reference, B-spline/jitter algorithm
id, CDP-style pointer samples, limitations, and a seam-validation stamp.
`pointer-dispatch-plan` emits `captcha.pointer_dispatch_plan.v1`, which points
to Surf's dispatch command and expected receipt schema. Neither artifact is a
ReCAP capability measurement or evidence that any challenge was solved.

## Compose through Ask

Generate the typed DAG rather than hand-writing a shell chain:

```bash
./run.sh ask-dag \
  --manifest /path/to/authorization.json \
  --recap-root /mnt/storage12tb/skills/captcha/vendor/ReCAP-Agent \
  --recap-python /mnt/storage12tb/skills/captcha/vendor/ReCAP-Agent/.venv/bin/python \
  --output-root /mnt/storage12tb/skills/captcha/outputs \
  --out /tmp/captcha.ask-dag.json \
  --json

cd ../ask
./run.sh ask "Run the authorized local ReCAP CAPTCHA evaluation" \
  --dag-file /tmp/captcha.ask-dag.json \
  --json
```

Ask preserves the DAG and node evidence; `captcha` still owns the authorization
and execution gates. An Ask/Tau node completion is not CAPTCHA result proof;
closure requires a valid `captcha.run_receipt.v1` and `./run.sh verify` PASS.

## Upstream setup

Heavy source, environments, model weights, screenshots, and runs belong under
`/mnt/storage12tb/skills/captcha`; do not store them in the repository.
Installation is deliberate and never performed by the runtime:

```bash
mkdir -p /mnt/storage12tb/skills/captcha/vendor
cd /mnt/storage12tb/skills/captcha/vendor
git clone https://github.com/ASTRAL-Group/ReCAP-Agent.git
git -C ReCAP-Agent checkout 577c7728ed159756a6cb6cbd1a58897fe288f73e
python3.11 -m venv ReCAP-Agent/.venv
ReCAP-Agent/.venv/bin/pip install \
  -r ReCAP-Agent/dynamic_captchas/requirements.txt \
  -r ReCAP-Agent/captcha_eval_framework/requirements.txt
ReCAP-Agent/.venv/bin/python -m playwright install chromium
```

Start the synthetic target separately from its directory and expose the local
ReCAP model through a loopback OpenAI-compatible endpoint. Follow all upstream
license and model-access terms.

## Failure semantics

Policy, Surf, target, source-pin, runtime, subprocess, summary, or receipt drift
has exactly one outcome: non-zero exit plus `BLOCKED` evidence. There is no
warning-only bypass, public-host override, provider override, `shell=True`, or
fallback that interprets missing output as success.

## Validation

```bash
./sanity.sh
./run.sh eval
CAPTCHA_LIVE_E2E=1 ./run.sh eval-live
```

`./run.sh eval` runs the committed `$agentic-evals` v2 fixture with repeated
trials, a real entrypoint case, public-target rejection, missing `--execute`
rejection, missing-runtime truthfulness, and Ask DAG composition.

`./run.sh eval-live` is opt-in because it performs live effects. It requires
`CAPTCHA_LIVE_E2E=1` plus a running loopback ReCAP dynamic target, loopback
OpenAI-compatible ReCAP model endpoint, Surf transport, pinned ReCAP checkout,
and ReCAP Python runtime. It runs a nondeterministic live campaign through
`scripts/live_e2e_agentic_eval.sh`: each inner round generates a fresh
authorization manifest with a random seed and sampled CAPTCHA type, executes
`evaluate --execute`, verifies the emitted `captcha.run_receipt.v1`, and emits a
`captcha.nondeterministic_live_agentic_eval.v1` summary. Tune campaign size with
`CAPTCHA_LIVE_NONDETERMINISTIC_ROUNDS`; the default is three live inner rounds
per `$agentic-evals` trial.

`sanity.sh` uses real CLI and filesystem boundaries, validates the local
multi-trial agentic eval fixture, validates a positive local manifest, proves a
public target is rejected, emits an Ask DAG, compiles Python, and runs
unit/integration tests. It does not claim a live ReCAP model run unless
`eval-live` is run separately and passes.
