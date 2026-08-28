# DriveWealth ↔ Our Systems: The Bridge

One row per thing THEY know (their API docs are the interviewer's mental
model). Each maps to a mechanism WE run today, with the receipt that proves it.
Answers in the room walk left to right: their primitive → our mechanism → why
it matters for a regulated broker.

| They know (their stack) | We run (our mechanism) | Receipt / artifact |
| --- | --- | --- |
| Event-driven sync via SQS (accounts, orders, positions, KYC status, settlements, corporate actions) | Receipt-gated event consumption: every consumed unit leaves a node receipt with status + failure_code; absence is reported, never dropped | Tau node receipts; ask stage ladder (COMPILED→SETTLED); run projection over 1695-run corpus surfacing 1290 silent nodes |
| Duplicate/late event delivery (queue semantics) | Idempotent identity at the choke point: one wall hit three times is one blocker; receipts keyed by (target, failure_code) | ask blocker ledger `~/.ask/blockers.jsonl` |
| Session-token, server-to-server auth; secrets hygiene | Key-drift detection and fail-closed auth handling in the live pipeline; keys resolved most-authoritative-first, stale keys excluded from the chain | live-evidence `resolver_key()` (SCILLM drift documented in code); today's 401→200 fix receipt |
| Orders API — live mutation endpoints | Human-approval gates in front of any mutating action: compile-preview before execute, NEEDS_INTERVIEW on missing goal, approval-gated action lane | ask compile-only + chart confirm; live-evidence action lane (human-approved, destination-readback) |
| KYC documents, W-8/W-9, 871(m) — PII at rest and in flight | PII fencing at choke points: prompt preflight rejects unsafe payloads pre-submit; debugger-side secret redaction; purpose policies freeze capabilities into a digest | browser_prompt_preflight; policy_digest bound to every artifact |
| AutoPilot rebalancing — automated advice reaching customers | Answers are admitted, not assumed: answerability gate before generation, independent verifier after, source-bound cards with content hashes | spartaChat answerabilityGate/verifier; evidence_card.v1 with sha256 |
| Clearing/settlement reconciliation | Deterministic checks own the numbers; agentic second pass owns judgment; disagreement routes to receipts-first diagnosis ladder | agentic-evals gates; debugger dispatch table |
| Regulatory reporting / "prove what happened on this account 3 weeks ago" | Every run is an audit trail by construction: frozen contract, events.jsonl, per-node receipts, handoff chain, immutable goal hash | tau.dag_contract.v1; handoff.json chains; goal hash in every receipt |
| Sandbox/UAT by hostname | Live/mocked proof boundaries declared on every claim; fixture lanes never count as live proof | eval fixtures vs live-seat probes; mocked/live fields in receipts |
| Rate limits (provider + their own APIs) | Lane-local degradation: a rate-limited seat is removed and refilled family-for-family, never a whole-panel failure; bounded cooldowns, no bypass retries | browser-provider-selection.json; DEGRADED join receipts |
| Multiple internal teams building on one platform | Versioned capability contracts + eval gates + executable standards (panel-audit turns protocol prose into checkable verdicts) | 340+ SKILL.md contracts; agentic-evals READY receipts; panel-audit COMPLIANT |
| AWS stack, Python | All of the above is Python; orchestration is transport-agnostic (browser seats and API seats are peers behind one handler name) — the same posture ports to Strands/Bedrock primitives | ask handler grammar; scillm route table |

## The one-sentence bridge

"Your platform already thinks in events and receipts — SQS topics, order
statuses, KYC states. My work makes agents live inside that discipline instead
of beside it: every agent action produces the same kind of auditable receipt
your clearing pipeline already demands."

## Tuesday-morning answer, in their vocabulary

Bad agent output in production: the join receipt or reconciliation check trips
(not a customer complaint) → events.jsonl names the run → node receipt names
the failing lane and failure_code → recovery packet names the next command →
if no artifact explains it, breakpoint at the failing transition (state nothing
wrote down) → regulator-ready timeline already exists because it was written
during execution, not reconstructed after.
