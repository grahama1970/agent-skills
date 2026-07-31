# prompt.contract.v1 — Fixture-Backed Prompt Verification Integrated With Tau

Status: DRAFT for review (2026-07-31)
Owner: agent-skills
Provenance: synthesized from a 7-seat panel (WebGPT, Claude, Gemini, Kimi,
Grok, DeepSeek, Perplexity — raw captures under the 2026-07-31 session
scratchpad) plus the existing contracts of `/tau`, `/scillm`, `/ask`,
`/review-prompt`, `/prompt-lab`, `/agentic-evals`, and `/cleanup`.
DeepSeek-sourced claims are used only where independently corroborated: its
transcript showed fabricated citations.

## 1. Problem and governing rule

Bad/vague prompts have repeatedly cost days-to-weeks (e.g. QRA generation over
thousands of CVE controls). They pass static review, then fail in production,
and nothing records which prompt text, under which contract, produced the bad
output.

Governing rule (panel-converged):

> No production prompt contract is current unless a trusted attestation binds
> the exact contract materials, exact rendered request, declared model
> profile, fixtures, validators, and proof scope — and every critical gate
> passes.

A docstring or comment saying "reviewed" is never evidence. The verifier
signs; hashes bind; anything else is an unverified assertion.

## 2. Unit of governance: the prompt contract (WebGPT)

Certify prompt CONTRACTS at production callsites, not prompt strings:

```
prompt contract = renderer + model-visible source fragments + input schema
                + tool definitions + response format + consumer schema
                + fixtures + validators + model profile
```

Contract IDs name a behavior + consumer, not a file path:
`sparta.qra.generate.v3`, `memory.intent.route.v2`.

Contract classes (evaluate differently): `production_generation`,
`classification_or_routing`, `extraction`, `agent_workflow`,
`tool_description`, `repair_or_retry_prompt`, `grader_or_judge`,
`development_only`, `documentation_example`. SKILL.md instructions are
`agent_workflow` contracts (trajectory-evaluated via `/agentic-evals`), not
text-generation prompts.

## 3. Layout: colocated packs + generated index (panel dissent, resolved)

4 of 6 non-WebGPT seats (Claude, Gemini, Grok, Kimi-partially) rejected a
central `artifacts/prompt-receipts/` directory as a merge-contention and
ownership-ambiguity magnet at ~300 packages. Resolution: colocate, generate
the index.

```
skills/<skill>/prompt-contracts/<contract-id>/
├── contract.yaml            # schema: prompt.contract.v1
├── fixtures/
│   ├── golden.jsonl         # typical positives
│   ├── boundary.jsonl
│   ├── adversarial.jsonl    # incl. injection cases
│   └── incidents.jsonl      # grown by the failure-to-fixture rule
├── validators/              # deterministic checks (schema, grounding, forbidden claims)
├── receipts/
│   ├── current.json         # compact pointer, schema prompt.attestation.v1
│   └── history-index.json   # immutable content-addressed attestation refs
└── judge/                   # only for grader_or_judge or judge-using contracts
    ├── rubric.md
    └── calibration.jsonl    # human labels
```

Repo-level generated (never hand-edited) indexes:
`artifacts/prompt-contracts/index.json`, `attestation-index.json`,
`inventory.json`. `/cleanup` and CI read these; humans edit only the packs.

`contract.yaml` minimum fields: `schema`, `id`, `owner`, `risk`
(`critical|high|normal|development`), `class`, `callsite` (path+symbol),
`renderer` (path+symbol), `input_schema`, `consumer_schema`, `model_profile`,
`tool_schemas`, `response_format`, `fixtures`, `validators`, `gates`
(see §7), `judge` (optional, see §8).

## 4. Two-level identity (WebGPT; Gemini refinement)

`prompt_sha256` alone is insufficient — renderer, tools, validators, fixtures,
and model can change while prompt text stays green.

- **contract_fingerprint** = SHA256 over a canonical material manifest:
  digests of renderer source, fragments, input schema, message-order logic,
  tool definitions, response-format schema, consumer schema, validators,
  fixture inputs AND expected outcomes, judge rubric + calibration set,
  eval policy, retry/correction policy, model profile, harness lockfile.
  Hash the UNRENDERED template + variable schema (Gemini) — never a
  runtime-rendered string. If dependency resolution is uncertain,
  over-invalidate (hash the whole renderer module) and record
  `dependency_resolution: incomplete`; fail closed for release authority.
- **rendered_request_hash** = SHA256 of the exact provider request envelope
  (ordered messages, tools, tool_choice, response_format, model_requested,
  model_resolved, parameters) captured after rendering, before transport.
  For retrieval-augmented prompts, bind retrieved doc IDs/content digests.
- Dynamic prompts: no universal static hash exists. Each contract with
  runtime assembly MUST expose a per-skill **render-for-eval entry point**
  (Grok) that materializes the exact production request from fixture
  variables; a missing harness is itself a coverage failure.

## 5. Tau is the single authority; scillm is the single transport

`/tau` is the singular orchestration path for production prompt execution.
Skills stop OWNING prompt execution and start DECLARING contracts Tau
executes. This is a legacy-debt migration, not a parallel system.

### 5.1 Node-contract extension
Extend the Tau node prompt contract (`ask.tau_dag_prompt_contract.v1` /
`tau.generic_dag_spec.v1` node context) with:

```yaml
prompt_contract_id: sparta.qra.generate.v3
contract_fingerprint: sha256:...
```

Same discipline as the goal hash: the fingerprint is the goal-hash of the
prompt materials.

### 5.2 Node receipts carry the runtime attestation half
Tau node receipts add `rendered_request_hash`, `model_requested`,
`model_resolved`, parameters, cache mode. Capture point is the
scillm adapter / surf submit wrapper (the layers that see the final payload).
UNVERIFIED until implemented: exact hook location in tau/scillm code —
confirm before claiming capture works.

### 5.3 Governed transport + ratchet (WebGPT; DeepSeek corroborated by Claude)
- scillm governed mode: requests without a `contract_id` stamp are flagged
  (rollout) then rejected (steady state). Surf submit wrappers record the
  contract id in response meta JSON.
- **No-new-direct-call ratchet**: inventory existing direct scillm/provider
  callsites into a committed baseline file; CI blocks any NEW unregistered
  callsite immediately; any CHANGED callsite must register a contract; burn
  the baseline down by risk (QRA generation first). Legacy debt is
  enumerated, never accepted as a second path.
- Staging guard (DeepSeek): in staging/test runs, an unregistered execution
  raises rather than flags — dynamic complement to the static lint.
- Escape hatch: `# inline-prompt-exempt: <reason>` pragma (Kimi), counted
  and reported, never silent.

### 5.4 Batch is a Tau-owned node type
3,000-item batch generation does NOT become 3,000 DAG nodes. A Tau batch
node carries contract id + goal hash + one receipt; scillm executes the
batch under it (rolling-window scheduler as today). `create-qras`-style
direct batch calls are the first ratchet targets.

### 5.5 Eval runs ARE Tau DAGs
An executed-eval attestation is produced by a Tau DAG:
fixture-render node → provider node (through the SAME production
renderer/adapters — tests the production request by construction) →
deterministic validator node(s) → optional calibrated-judge node → attestation
join. `/agentic-evals` and `/prompt-lab` define fixtures and trial policy;
Tau executes and signs. The signer is the trusted harness/CI policy engine,
never a model. Local developer runs are marked `self_attested` and never
satisfy release gates.

## 6. Discovery: closed-world, receipted denominator

- Primary mechanism is the boundary (§5.3), not scanning. Claude's framing:
  a **leak-detector lint** — fail any LLM-client call whose prompt argument
  does not trace to a registered contract — converts discovery from an
  unprovable recall problem into an exhaustiveness check.
- AST/LibCST sink-first scanning is MIGRATION-TIME inventory (find current
  callsites, trace literals/f-strings/imports/templates/tool descriptions)
  plus a CI tripwire; it is never the ongoing authority. Known limitation:
  the current prompt-lab extractor catches only literal `*_PROMPT`
  assignments and skips f-strings (WebGPT, verified against source).
  Expect false positives from docstrings/log messages/SQL; triage with role
  markers, output-format instructions, adjacency to LLM calls (Grok).
- **The denominator itself gets a receipt** (Grok): publish a
  discovery-coverage score with a first-class `suspected_unregistered`
  verdict. Until egress is fully governed, the only honest claim is
  "coverage of known and registered callsites", never "every prompt".
- Scan canonical git-tracked roots only (exclude `skills.pre-symlink-*`,
  generated output, vendored docs).
- Migration accelerator (Gemini): an AST codemod that extracts inline
  f-strings into contract packs and stubs template fixtures.

## 7. Evaluation gates

Layered oracle hierarchy (WebGPT), strongest oracle per requirement:
0 assembly (request snapshot) → 1 deterministic (parse/schema/enums/IDs/tool
args) → 2 grounding & invariants (source-span, citation-subset, forbidden
facts, abstention, metamorphic) → 3 multi-trial behavior → 4 calibrated judge
→ 5 production drift.

- **Hard/soft split** (Gemini): deterministic critical assertions must pass
  100% of trials (`aggregation: all_trials`); probabilistic/soft metrics use
  a predeclared pass-rate with confidence bounds and retry-on-transport-error
  so rate-limit noise doesn't fail builds. A single critical failure fails
  the case regardless of averages.
- **Every registered prompt requires at least one fixture** — even a smoke
  fixture. `no_fixture` gates as `unreceipted` (Kimi, per operator intent:
  an untestable prompt is underspecified by definition).
- Fixture families for critical contracts: golden, boundary,
  negative/no-answer, adversarial+injection, historical incidents,
  consumer-integration, metamorphic variants (remove evidence → abstain;
  inject conflicting instruction → governing instruction wins; perturb an
  ID → no silent "repair").
- **Failure-to-fixture rule** (Claude): every production prompt failure adds
  an `incidents.jsonl` fixture BEFORE the fix merges.
- **First-attempt vs corrected** (WebGPT): record
  `first_attempt_verdict`, `final_after_correction_verdict`,
  `correction_rounds`, tokens/latency-to-success. A prompt failing 70% of
  first attempts that self-corrects is hidden waste, not a pass.
- Trial statistics (WebGPT; Claude corroborates): 3 PR trials = regression
  smoke only. Bounding failure <5% @95% confidence needs 59 clean trials;
  <1% needs 299. PR = affected contracts, shallow; nightly = critical
  contracts, deep; release = full critical suite, cache disabled.
- Fixture/validator changes are GOVERNED materials: owner review required;
  weakening a validator to go green is caught by mutation/negative-control
  tests over the validators themselves.
- Cost envelope (Perplexity, indicative only): ~$0.50–2 per prompt per
  full re-eval (10 trials × 50 fixtures); ~$150–600 per model migration at
  300 contracts — tier by risk (§9) to control it.

## 8. LLM-as-judge: calibrated statistical evidence, never proof

Permitted only when the requirement is not expressible deterministically, and
ALL of: concrete rubric with rejection conditions; calibrated against
human labels on a held-out set; judge model+rubric+params+ordering pinned;
pairwise/pass-fail/reference-guided grading; position bias controlled by
order swapping; verbosity penalized (Kimi); rationale-before-score;
disagreement or low calibration fails closed.

- The judge prompt is ITSELF a `grader_or_judge` contract with its own
  fixtures, calibration receipt, and fingerprint. It never self-certifies.
- Judge noise is real (Claude, from measurement research): semantically
  equivalent judge templates flip ~25% of majority outcomes; ~11 repeated
  trials for 95% majority-vote stability. Treat judge output as a floor.
- Ongoing audit (Kimi/DeepSeek): weekly human audit of a sample of judge
  decisions; auto-suspend the judge assertion when disagreement exceeds the
  declared threshold — suspension gates as `blocked`, not `pass`.

## 9. Staleness: causal invalidation graph + calendar

Any change to: fragment, renderer/message-order logic, input schema, tools,
response/consumer schema, fixtures (inputs OR expected), validators, judge
rubric/calibration, model snapshot, params, provider adapter,
retry/correction policy, retrieval corpus, eval harness → receipt is STALE
for current authorization (old attestation remains historical evidence).

- Record `model_requested` and `model_resolved`; alias drift stales.
- **Model deprecation calendar** (Kimi): machine-readable provider
  deprecation dates compute `expires_at` and bulk-stale receipts ahead of
  forced migrations. On model change, run old-vs-new paired eval on a fixture
  sample; bulk-migrate receipts only within declared tolerance.
- Tiered recertification (Claude/Grok): critical = nightly/release-bound
  full re-run; high = rotating canary subset + random 5% unchanged-receipt
  sample per PR window (Kimi's drift canary); normal = change-triggered +
  periodic sampling with lazy `stale_model` marking; development =
  change-triggered only. TTL (~90d) supplements, never replaces, causal
  invalidation.
- **Static-review receipts expire hard** (Claude): `/review-prompt` receipts
  are provisional — valid ≤60 days or until first prompt edit, and NEVER
  satisfy the quality gate alone (Goodhart guard: the cheap path must not
  close the gate).
- Emergency path (DeepSeek): audited waiver file with expiry +
  `grace_period_days` so a hotfix isn't blocked by re-eval; waivers are
  reported debt, never silent.
- **Shadow receipts for critical pipelines** (Grok): high-value contracts
  also sample live production telemetry against the same fixtures/validators;
  a green offline receipt never stands alone for `risk: critical`.
- Fresh-trial rule: cached outputs never count as fresh trials for
  authoritative recertification (`--no-cache` semantics).

## 10. /cleanup projection lane (report-only)

`/cleanup --prompt-receipt-coverage` consumes the generated indexes (§3) and
Tau attestation receipts. It never rediscovers prompts, re-derives hashes, or
re-decides eval outcomes. One primary row per CONTRACT/callsite (not per
fragment); a fragment→contract appendix preserves the many-to-many reality.

Orthogonal columns (never one overloaded enum):

| Column | Values |
|---|---|
| discovery | registered / unregistered / suspected_unregistered / unresolved / excluded(reason) |
| fixture_state | valid / missing / invalid |
| receipt_state | current / stale / missing / unreadable / untrusted / waived(expiry) |
| eval_verdict | pass / fail / blocked / insufficient_evidence / not_run |
| evidence_class | static_review / deterministic_eval / stochastic_eval / calibrated_judge / shadow |
| risk | critical / high / normal / development |
| production_parity | exact_renderer / copied_prompt / unknown |
| rerun | exact command or named blocker |

Authorization condition: `registered ∧ fixture_valid ∧ receipt_current ∧
receipt_trusted ∧ eval_verdict=PASS ∧ proof_scope satisfies risk policy ∧
production_parity=exact_renderer`. Non-claims section is mandatory:
"authorized" ≠ "performs well in production"; coverage claim is bounded by
the receipted denominator (§6).

Gating (Gemini's skill-scoped model): report-only for legacy debt; but a PR
touching a skill requires THAT skill's contracts current with zero new
`unregistered` — repo-wide gates only after the denominator is controlled.

## 11. Rollout order

1. Fix the Ask↔Tau contract skew (agent-skills#1123) — contract stamping is
   pointless while the installed Tau rejects Ask-emitted DAGs.
2. Define `prompt.contract.v1`, `prompt.attestation.v1`, model profiles,
   deprecation calendar format.
3. Add contract fields to the Tau node prompt contract + node receipts;
   confirm the rendered-request capture point in scillm/surf (§5.2).
4. Ratchet on: baseline direct-callsite inventory committed; CI lint blocks
   new unregistered callsites; staging guard raises.
5. Register the highest-risk contracts first: QRA generation, routing,
   grounding, judges. Wire their evals as Tau DAGs.
6. `/cleanup` projection lane + generated indexes.
7. Backfill legacy baseline by risk; skill-scoped PR gates as skills reach
   zero unregistered; repo-wide gates last.
8. Prove the machinery on a synthetic fixture repo (literals, f-strings,
   imports, file templates, dynamic branches, tool descriptions, deliberately
   unresolved constructs) with an exact expected inventory; mutation-test
   staleness by changing each material class and asserting the receipt goes
   stale.

## 12. Non-claims

- This spec does not claim current discovery finds every prompt; the honest
  denominator is registered + governed-boundary callsites (§6).
- A green attestation proves declared fixtures on the declared model profile;
  it does not prove production performance (shadow receipts narrow, never
  close, that gap).
- Panel provenance is model judgment, not deterministic proof; every
  mechanism above closes only through its own executable gate.
