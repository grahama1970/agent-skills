# Battle V16 RelayForge WebGPT Review Bundle

Date: 2026-08-04

## Review request

Bluntly review whether this backend evidence supports only this limited claim:

One complex RelayForge V16 Battle candidate produced one live, non-mocked
Red-versus-Blue campaign. Tau and SciLLM produced typed action-selection
artifacts, Battle bound those selected actions to public operations and a
private Judge path, Docker topology ran, and the private Judge emitted an
outcome.

Return one of these strings first:

- VERDICT: PASS
- VERDICT: FAIL
- VERDICT: INSUFFICIENT_EVIDENCE

Do not pass arena balance, Memory outcome improvement, production readiness, or
UX. Those are explicitly non-claims.

## Why this review exists

An earlier WebGPT review failed the previous evidence because the Red side still
looked like a legacy Zip Slip canary. The repaired implementation now requires
V16 action selections instead of code artifacts:

- Tau V16 handoff asks for red_action_selection or blue_action_selection.
- Tau SciLLM prompt advertises action-selection schemas in V16 mode.
- Battle V16 rejects legacy red_exploit, blue_patch, exploit_py, and app_py for
  action selection.
- Battle V16 removed the legacy Zip Slip-derived fallback operation.
- Battle V16 emits a binding receipt connecting selected operations to target
  identity, service image id, public action surface, RF path id, private Judge
  predicates, and receipt hashes.

## Deterministic checks

Tau contract check:

```text
Command family: Tau Battle handoff and SciLLM auth preflight tests
Result: 30 passed in 0.62s
Mocked: no for the contract assertions under review
Live provider call: no; this check proves Tau prompt and materialization
contracts, not provider semantic quality.
```

Battle V16 contract check:

```text
Command family: RelayForge V16 live topology contract tests
Result: 16 passed in 0.16s
Mocked: no for schema and contract checks
Live provider call: no; this check proves local contract behavior, not the live
campaign itself.
```

## Live campaign receipt summary

The live campaign receipt is a local JSON artifact copied into the durable
Battle report directory. WebGPT does not need filesystem access to review it;
the relevant fields are reproduced here.

```text
schema: battle.v16.live_topology_qualification.v1
status: PASS
target_id: battle-v16-relayforge-a
mocked: false
live: true
fixture_fallback_used: false
target_identity_sha256: 739c68d7f41515d281e7c0d51fed414159bff18bb85030561c9b773375c39d9e
service_image_id: sha256:93e6a4c824bd062657b063531f65e8b91295ac5733757a46fce45666b5ba041f
judge_verdict: BLUE_SUCCESS
remaining_blockers: []
memory_improvement_proven: false
production_readiness_proven: false
relayforge_binding_sha256: 408d6bea34feb27a5adc66afdc333a7b34f5b7b42a7e3b26dbd1b84bd664b7d6
```

## Red action selection

```text
schema: battle.v16.live_topology_action_selection.v1
status: PASS
team: red
provider_artifact_type: red_action_selection
operation: retrieve-observed-report
action_id: red-r1-retrieve-observed-report
eligible_proposal_count: 2
private_judge_read_during_selection: false
mocked: false
live: true
provider_artifact_sha256: 57777c0e213612eaf557c67e802b897179586693a46554cb68d7e82dbc53129d
provider_call_sha256: ad6186f57d09d6cd3b85718a6191edeaa530578d72ce9e3b4ec816295c95d660
selected_proposal_sha256: 2729f16b53079e9ad573ca5311c3852696c77c957ea4d3c8762850c51606358b
selection_policy: lowest_provider_rank_among_schema_valid_evidence_satisfied_actions
```

## Blue action selection

```text
schema: battle.v16.live_topology_action_selection.v1
status: PASS
team: blue
provider_artifact_type: blue_action_selection
operation: cache-principal-partition
action_id: blue-857-1
eligible_proposal_count: 2
private_judge_read_during_selection: false
mocked: false
live: true
provider_artifact_sha256: 234036e4919034bc4bfdeba078838889da250c4d170da0ecea1214cb892ea569
provider_call_sha256: 54a1accc7785988c34e155196718ae8076e76da9ee44068d9956c070ccad21ad
selected_proposal_sha256: 58e2d02238d0b49659a443b959e23d588977aa60d696fdd9f67567722441bd04
selection_policy: lowest_provider_rank_among_schema_valid_evidence_satisfied_actions
```

## RelayForge binding receipt

```text
schema: battle.v16.live_topology_relayforge_binding.v1
status: PASS
target_id: battle-v16-relayforge-a
team_artifact_type.red: red_action_selection
team_artifact_type.blue: blue_action_selection
red_selected_operation: retrieve-observed-report
blue_selected_operation: cache-principal-partition
red_public_route: API v1 report retrieval for opaque report reference a282f431f20f739d2fde91fcc211688be9d00f633017c965d6ab94f9a7690982
blue_public_route: API v1 defense cache-principal-partition
red_judge_path_id: RF-B
red_judge_predicate_ids: rf-b-evidence, rf-b-probe, rf-b-boundary, rf-b-objective
red_after_stage: PROTECTED_OBJECTIVE
red_final_stage: REPRODUCIBLE_PROBE
red_sink_hash_changed_from_baseline: false
mocked: false
live: true
fixture_fallback_used: false
source_receipt_sha256.judge: 31c14eb553efabdf21be56738d8943e2ed6c0bda633b579ebd32631ffcd6f52a
source_receipt_sha256.regression: d5277a4132e68dd8044f817fddaed03343999739594e570bd8b9b0083b4a2a98
```

## Private Judge receipt

```text
schema: battle.v16.live_topology_judge.v1
status: PASS
judge_authority: relayforge-private-judge-cli
verdict: BLUE_SUCCESS
mocked: false
live: true
fixture_fallback_used: false
path_stages.baseline.RF-A: UNSEEN
path_stages.baseline.RF-B: REPRODUCIBLE_PROBE
path_stages.baseline.RF-C: UNSEEN
path_stages.after_red.RF-A: UNSEEN
path_stages.after_red.RF-B: PROTECTED_OBJECTIVE
path_stages.after_red.RF-C: UNSEEN
path_stages.final.RF-A: UNSEEN
path_stages.final.RF-B: REPRODUCIBLE_PROBE
path_stages.final.RF-C: UNSEEN
red_selection_sha256: e539618ebfe75fb72a1ba30bde000038ad79b1b542d0537e0cb02a560bdc7255
blue_selection_sha256: 4ff6100cf2f50de6fadc887e6e42dee75062cc11ade12700bb0c92465143c2ba
red_execution_sha256: 5d36e0517e73f9c0f181c848a77e590e3834368f1f037d0ca542bcfa6d08f893
blue_execution_sha256: 0824824d6d5f633457f554ba63998ac4ef04ee73f81d47c8453a4f463f488050
regression_receipt_sha256: d5277a4132e68dd8044f817fddaed03343999739594e570bd8b9b0083b4a2a98
memory_improvement_proven: false
production_readiness_proven: false
```

## Regression receipt

```text
schema: battle.v16.live_topology_regression.v1
status: PASS
target_id: battle-v16-relayforge-a
mocked: false
live: true
pass_count: 6
failure_count: 0
result_count: 6
passed functions: regular-package-import, in-bound-transformed-object,
tenant-owned-report, valid-external-preview, safe-report-profile,
legacy-conversion
```

## Non-claims

This packet does not prove:

- arena balance across repeated trials;
- that Red and Blue are evenly matched;
- Memory outcome improvement;
- production readiness;
- UX quality;
- RF-A or RF-C wins in this one live run.

The only useful backend conclusion available from this packet is narrower:
RelayForge V16 now has one live receipt-backed Red/Blue campaign where typed
provider selections are bound to an RF path and a private Judge outcome.
