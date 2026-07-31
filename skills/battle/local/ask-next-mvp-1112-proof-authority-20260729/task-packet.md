# Battle Blocker Competition Packet - #1112 Proof Authority MVP

## Objective

Choose the smallest implementation slice that can unblock Battle issue #1115 by advancing issue #1112: replace Hack proof-file existence claims with independently validated receipts.

## Immutable Goal

Deliver production-scope Battle frontend and backend behavior with deterministic local receipts. This packet is only for the next dependency MVP; it must not claim the full Battle goal is met.

## Source-Derived Step Model

1. Implemented: Battle now has local HTTP/SSE frontend/backend receipts, packaged local deployment smoke, transport safety smoke, and `$test-interactions` 38/38 current-source proof.
2. Implemented: `#1109` target authorization manifest is closed.
3. Missing: `#1112` Hack proof authority remains open; Hack still needs an observation/validation split so a file named `proof.*` cannot become exploit truth.
4. Intended by `#1115`: Battle default rounds must use Judge-authoritative Red observation, reactive Blue, Judge replay #2, and scorekeeper receipts.
5. Blocker: `#1115` depends on `#1112`; without a strict proof-validation receipt, Battle cannot safely treat a Red observation as a Judge-confirmed finding.
6. Missing but later: `#1110` Compose policy and `#1111` sterile target environment still gate arbitrary repository-controlled target execution. The `#1112` MVP should therefore use deterministic local receipt fixtures, not a broad live target runner.

## Current Battle Receipts

- `skills/battle/local/production-scope-v16-evidence-20260729.json`
- `skills/battle/local/packaged-deployment-smoke-20260729/packaged-deployment-smoke.json`
- `skills/battle/local/transport-safety-smoke-20260729/transport-safety-smoke.json`
- `skills/battle/local/transport-safety-smoke-20260729/test-interactions-current-source/results.json`

## Ticket Constraints From #1112

Required concepts:

1. `hack.probe_observation.v1`: Hack observation records what the bounded probe observed and always starts with `exploit_confirmed=false`.
2. `hack.proof_validation_receipt.v1`: independent validation may confirm or reject only after binding authorization hash, target identity/runtime hash, probe spec hash, observation hash, validator identity, replay spec/receipt hash.
3. Default statuses: `NOT_ATTEMPTED`, `OBSERVED_UNCONFIRMED`, `CONFIRMED`, `REJECTED`, `VALIDATION_ERROR`.
4. File existence, probe exit code, hard-coded VulnerableApp copy, or Hack self-validation must not produce `CONFIRMED`.
5. Battle must be able to consume the validation receipt as the future Judge authority boundary.

## Candidate MVP Options

Compare these and pick one:

1. **Schema-and-validator MVP**: add strict Hack observation and proof-validation schemas, pure validator, mutation matrix fixtures, and a `prove-proof-authority` command. No report rewrite beyond blocking false confirmation.
2. **Report-consumer MVP**: first patch Hack report/memory consumers to stop proof-file inference and render unconfirmed status, with minimal schemas only as fixtures.
3. **Battle-adapter MVP**: add a Battle-side Judge validation receipt adapter first, leaving Hack internals mostly unchanged.
4. **Docker-replay MVP**: implement a local Docker proof authority now.

## Required Candidate Output

Return:

1. Recommended MVP and why it is the smallest useful unblocker for #1115.
2. Exact files likely touched.
3. Receipt/schema names and required fields.
4. Deterministic proof commands and one live/local artifact command.
5. What the MVP may claim.
6. What it must not claim.
7. Stop condition if it needs Docker, credentials, production infra, or a human policy decision.

## Judging Criteria

- Smallest slice that reduces the #1115 blocker.
- Fail-closed proof authority boundary.
- Does not depend on #1110/#1111 for arbitrary target execution.
- Battle can consume the resulting receipt boundary later.
- Deterministic local receipt readback is possible.
- No `$scillm` or LLM Judge.

## Forbidden Claims

- Do not claim #1112 is closed from a plan.
- Do not claim #1115 is unblocked unless the implementation and proof exist.
- Do not claim arbitrary exploitability, patch effectiveness, production readiness, WebSocket support, or unbounded swarm execution.
