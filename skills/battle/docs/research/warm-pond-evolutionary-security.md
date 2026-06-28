# Warm-Pond Evolutionary Security Search

## Status

This note records the intended Battle search model and related research
precedent. It is a design/research note, not proof that production Battle has
already implemented the full loop.

Current proven Battle layer:

- Deterministic local fixture.
- Red, Blue, and scorekeeper receipts.
- Scoreboard derived from scorekeeper evidence.
- Artifact-backed monitor.

Intended production layer:

- Persona-attached Tau/scillm subagents.
- Docker-bound exploit and defense execution.
- High-throughput mutation search.
- Memory-backed promotion, negative evidence, and graph recall.
- Tree-sitter/code-ingestion weighted code-surface targeting.

## Core Model

Battle should behave like a genetic warm pond:

1. Generate many Red exploit candidates and Blue defense candidates.
2. Combine high-level ideas with low-level mutations.
3. Execute each attempt in an isolated Docker runtime or snapshot.
4. Keep only runtime evidence and durable learning after each attempt.
5. Promote attempts that crash, exploit, patch, preserve behavior, or improve
   score.
6. Reset failed execution state to the clean base, while storing failures as
   negative evidence.
7. Let later subagents recombine successful and near-miss strategies.

The "lightning hitting a warm pond" analogy maps to randomized generation under
selection pressure. Randomness creates novelty; runtime score and memory decide
what survives.

## Attraction Weighting

Battle can weight exploit/defense combinations as if they were reactive
chemical elements. A candidate is not chosen uniformly at random; it receives an
attraction score from multiple evidence sources:

```text
attraction(candidate, target_surface) =
  memory_success_weight
+ memory_near_miss_weight
+ graph_multihop_relatedness
+ crosswalk_chain_affinity
+ code_structural_proximity
+ cwe_taxonomy_match
+ runtime_feedback_bonus
- negative_evidence_penalty
- resource_cost_penalty
- stale_context_penalty
```

Recommended signal sources:

- `$memory` graph/BM25 recall: prior successful attempts, failed attempts,
  related CVEs/CWEs, persona strategies, target families, and multi-hop links.
  Giving a Battle subagent `$memory` access also gives it the memory front-door
  products: `/intent`, `/answer`, `/clarify`, `/deflect`, `/recall`, and
  entity-aware routing used by evidence-case workflows.
- `$ingest-code`: repo-level code symbols, imports, call edges, string
  literals, structured `code_symbols`, CWE summaries, and ingestion markers.
- `$treesitter`: function/class/symbol extraction and source span targeting for
  candidate mutation placement.
- `$create-evidence-case`: crosswalk chains such as
  `CWE -> CAPEC -> ATT&CK -> SPARTA` that reveal attack pattern,
  weakness, technique, and countermeasure relationships.
- Runtime receipts: crash/no-crash, exploit replay, regression status,
  coverage, latency, resource pressure, patch quality, and scorekeeper verdict.
- Research skills: `$dogpile` and `$brave-search` for outside tactics, public
  writeups, CVEs, docs, and examples.

Multi-hop graph traversal should produce "chemical affinity" between ideas:

- exploit family -> CWE -> code symbol -> prior target -> successful payload
- exploit primitive -> CWE -> CAPEC -> ATT&CK technique -> related primitive
- exploit primitive -> CWE -> CAPEC -> SPARTA countermeasure -> Blue hardening
- patch pattern -> failing regression -> related symbol -> safer variant
- persona -> past successful tactic -> target language -> mutation operator

Tree-sitter and ingest-code should bias the random search toward code regions
where an exploit or patch is structurally plausible, instead of spraying every
mutation evenly across the codebase.

## Crosswalk Chains As Combination Edges

Battle can reuse the evidence-case crosswalk pattern as an exploit-composition
graph. In `/create-evidence-case`, entity extraction and graph traversal build
chains across frameworks such as CWE, CAPEC, ATT&CK, and SPARTA. For Battle,
those chains can become typed edges between exploit ingredients and defensive
countermoves.

Example relation shapes:

```text
code_symbol -> possible_CWE
CWE -> CAPEC_attack_pattern
CAPEC -> ATT&CK_technique
ATT&CK_technique -> exploit_family
SPARTA_countermeasure -> blue_defense_family
exploit_family -> prior_successful_payload
exploit_family -> incompatible_payload
defense_family -> prior_regression_failure
```

This helps answer the core warm-pond question:

```text
Which exploit elements combine well together on this target?
```

The graph should not only connect "similar" ideas. It should connect ideas that
have useful reaction potential:

- shared CWE or CAPEC path,
- same code symbol or adjacent call graph region,
- one exploit unlocks preconditions for another,
- one payload family bypasses a defense that blocked another,
- one defense hardens the exact technique family Red is exploiting,
- prior failure is close enough to mutate instead of discard.

For Red, crosswalk chains can propose exploit bundles. For Blue, the same
chains can propose patch, hardening, detection, and regression-test bundles.
Runtime scorekeeper receipts decide whether the proposed chemistry actually
reacted.

## Subagent Knowledge Front Door

Battle should not give each subagent a bespoke pile of partial knowledge tools.
The clean contract is:

```text
Battle orchestrator
  -> chooses persona, team, target, budget, Docker scenario, and objective
  -> grants approved skills such as $memory, $dogpile, $brave-search
  -> dispatches Tau/scillm subagent

Subagent
  -> calls $memory /intent to classify the turn or strategy question
  -> calls /deflect before unsafe/off-scope memory or evidence work
  -> calls /clarify when target, exploit family, or evidence is ambiguous
  -> calls /recall for BM25/dense/graph prior attempts and code knowledge
  -> calls /answer only for grounded memory-backed answers
  -> may route to crosswalk/evidence-case when CWE/CAPEC/ATT&CK/SPARTA chains
     are useful for exploit or defense composition
```

This keeps Battle as the control plane. Battle owns persona assignment,
container isolation, runtime execution, receipts, scorekeeping, and promotion.
The subagent owns strategy formation and research within the approved capability
envelope.

## Rollback Semantics

Failed candidates should be discarded from active execution state, similar to a
`git revert`, but stronger:

- Reset Docker container, filesystem overlay, worktree, or VM snapshot.
- Keep the attempt receipt, logs, and score.
- Store the failure in memory as negative evidence.
- Reduce promotion weight unless the failure was a near miss.

Successful candidates are promoted as reusable material, not blindly accepted as
global truth. They still need replay checks and scorekeeper receipts.

## Research Precedent

The full Battle design is broader than any one paper, but the pieces have clear
precedent:

- **V-Fuzz: Vulnerability-Oriented Evolutionary Fuzzing**
  (arXiv:1901.01142) combines vulnerability prediction with an evolutionary
  fuzzer that biases input generation toward vulnerable locations.
  https://arxiv.org/abs/1901.01142

- **NEUZZ: Efficient Fuzzing with Neural Program Smoothing**
  (arXiv:1807.05620) discusses evolutionary fuzzing as common guidance for
  input generation and proposes learned surrogate guidance for hard-to-trigger
  branches.
  https://arxiv.org/abs/1807.05620

- **ARJA: Automated Repair of Java Programs via Multi-objective Genetic
  Programming** (arXiv:1712.07804) is directly relevant to Blue-side patch
  search: it decomposes patch search spaces and uses genetic programming for
  automated repair.
  https://arxiv.org/abs/1712.07804

- **GenProg / automatic program repair using genetic programming** provides the
  classic precedent for evolving program variants and retaining ones that pass
  defect and regression tests.
  https://web.eecs.umich.edu/~weimerw/p/weimer-tse2011-genprog-preprint.pdf

- **Co-evolutionary Dynamics of Attack and Defence in Cybersecurity**
  (arXiv:2505.19338) supports modeling attacker and defender populations as an
  asymmetric evolutionary game.
  https://arxiv.org/abs/2505.19338

- **Evolutionary and Coevolutionary Multi-Agent Design Choices and
  Optimization in Adversarial Cybersecurity Environments** studies
  evolutionary algorithms for autonomous agents in CybORG-like cyber security
  simulations.
  https://arxiv.org/html/2507.05534v1

- **Revisiting Neural Program Smoothing for Fuzzing** (arXiv:2309.16618) is an
  important caution: ML-guided fuzzing needs rigorous evaluation because
  compute-heavy guidance can underperform strong gray-box fuzzers if measured
  incorrectly.
  https://arxiv.org/abs/2309.16618

## Implementation Implications For Battle

1. Keep randomness, but weight it with memory, code structure, taxonomy, and
   runtime feedback.
2. Treat failed attempts as first-class negative evidence, not noise.
3. Promote near misses separately from wins.
4. Require scorekeeper replay before a candidate becomes a durable strategy.
5. Keep host code as control plane; execute mutations only in isolated
   runtimes.
6. Use the monitor to show active candidates, ancestry, score, target code
   surface, and promotion status rather than generic dashboard metrics.

## Non-Claims

This note does not prove:

- live Docker mutation throughput,
- Tau/scillm subagent execution,
- memory graph promotion,
- Tree-sitter weighted targeting,
- D3 live visualization,
- overnight Battle reliability.

Those require separate runnable receipts and browser-visible evidence.
