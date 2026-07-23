Web research used: yes. I verified the supplied MemEmo and Dynamic Affective Memory papers. MemEmo reports that evaluated memory systems are not robust across emotional extraction, updating, and question answering; Dynamic Affective Memory proposes an entropy-minimizing update mechanism and an affect-focused benchmark. These reinforce the need for a direct-memory comparator rather than assuming that the more elaborate dream path is superior. 
arXiv
+1

Q1 — The cluster ceiling
Primary path: (d) Freeze the current corpus and run a finite-population study

Treat the available clusters as a census of Embry’s currently eligible memory corpus, not as a random sample of every future experience Embry could acquire.

Concretely:

Freeze a manifest of all 12 clusters and their source-memory hashes.

Do not generate more dreams for this study.

Complete the source-to-affect oracle on the existing packets.

Use each valid dream cluster as a paired experimental block for D/M/F/S.

Create multiple prespecified conversation contexts within each cluster to improve measurement precision, while retaining the dream cluster—not the individual listener rating—as the top-level generalization unit.

Scope the conclusion explicitly to:

“the complete currently eligible Embry memory corpus.”

This is a refinement of option (a), but it avoids pretending that 12 is an ordinary sample whose conclusions automatically generalize to future memories.

Important denominator correction

On the facts supplied, one of the 12 packets is the known pre-fix Brandon-memory/Kai-ToM artifact. Unless it has been re-derived under the corrected pipeline, it should be retained as a blinded negative-control packet, not counted as a valid D treatment.

That gives:

11 valid post-fix dream blocks
1 known negative-control artifact
12 total oracle packets

It should not silently enter the downstream D arm.

Ranking

(d) Frozen finite-corpus census with nested contexts

(a) Plain n=12 study, if the analysis tooling cannot support the nested design

(b) Expand memories later, but only after D-versus-M results justify the cost

(c) Relax anti-repeat, only in a separate re-dream reliability experiment—not to inflate this study’s sample size

What would change the ranking?

I would prefer (b) if the D−M pilot is directionally promising but inconclusive because between-cluster uncertainty is large, and additional accepted real experiences can be added with the same provenance and quality controls. Synthetic filler written merely to reach a sample-size target would contaminate the estimand.

I would consider (c) only if the new question became:

“How stable is dream-derived affect when the same memory cluster is independently re-dreamed?”

Repeated dreams from one cluster could answer that reliability question, but they would remain correlated observations and could not be counted as new independent evidence that D beats M.

Q2 — Power at n=12
Gate 2 source-to-affect accuracy

The charter’s original 15/20 criterion equals 75%. Its direct arithmetic translation is 9/12, but with only 12 packets that is a fragile pass: the approximate 95% Wilson interval for 9/12 is about 0.47–0.91.

I recommend:

PASS_GATE2_CURRENT_CORPUS:
  at least 10/12 packets receive 2-of-3 annotator support
  for BOTH valence direction and dominant tag

PARTIAL_GATE2_CURRENT_CORPUS:
  exactly 9/12 supported

FAIL_GATE2_CURRENT_CORPUS:
  8/12 or fewer supported

With the known pre-fix artifact separated properly:

positive accuracy gate:
  at least 9/11 post-fix packets supported by 2-of-3 annotators

counterpart safety gate:
  0/11 post-fix packets have an accepted counterpart inconsistency

sensitivity gate:
  at least 2/3 annotators detect the pre-fix Brandon/Kai artifact

The final receipt should report the exact binomial interval rather than convert this pilot into a broad population-accuracy claim.

Is 12 enough for the listener study?

It is enough for a kill-test and variance pilot. It is not enough for a sensitive confirmatory claim unless the D−M effect is large.

With 12 paired independent dream blocks, a conventional paired analysis has roughly 80% power only for a standardized effect around:

two-sided test: d ≈ 0.89
directional test: d ≈ 0.77

That is a large effect.

Increasing K, the number of listeners per item, improves the precision of each item’s estimated preference. It does not create more independent dreams. For example, detecting a true 58% preference over chance would require roughly 240 fully independent binary judgments even before accounting for repeated listeners, shared contexts, and dream-cluster correlation. Twelve contexts with 20 listeners each would produce 240 raw ratings, but substantially fewer effective independent observations.

Cheapest variance pilot

Use the valid post-fix dream blocks:

dream clusters:             11
contexts per cluster:        2
primary arms:                D and M only
paired contexts:            22
listeners per paired item:   8
total judgments:           176

All conditions use identical approved text and the qualified timing channel.

Fit a mixed-effects preference model with:

fixed effect:
  D versus M

random effects:
  listener
  conversation context
  dream cluster

Then bootstrap at the dream-cluster level and estimate the cluster intraclass correlation.

Pre-register a futility rule such as:

If the upper 80% cluster-bootstrap bound for D preference is below 0.58,
emit FUTILITY_DREAM_NOT_OVER_MEMORY and do not scale.

If the pilot is promising, use its observed listener, context, and cluster variance to simulate the full F/M/D/S design. If it is inconclusive, report that honestly; adding listener ratings alone may not resolve the dream-level uncertainty.

Q3 — Tag skew

The skew limits the scope of the study, but it is not a reason to discard data.

Primary analysis: use all valid packets

Do not make a balanced subset the primary analysis. Dropping three warmth packets would:

reduce an already small number of dream blocks;

change the estimand;

invite selection decisions based on the observed corpus;

provide no remedy for the complete absence of strongly negative-valence dreams.

Use all certified, post-fix, counterpart-correct packets and report two estimands:

corpus-weighted effect:
  average D−M effect over the current Embry corpus

tag-macro effect:
  equal-weighted average across the observed tag classes

The macro estimate should be a sensitivity analysis. Yearning has only one packet, so its effect is descriptive, not independently estimable.

Secondary capped sensitivity subset

A prespecified secondary subset could cap each tag at two packets:

warmth       2 of 5
boundary     2 of 2
hesitance    2 of 2
reflection   2 of 2
yearning     1 of 1
total        9

Selection within warmth must use a frozen deterministic rule—such as profile hash ordering—not listener outcomes or perceived quality.

What cannot be claimed

This corpus cannot establish that dream affect produces:

guarded hostility;

anger;

acute fear;

grief;

strongly negative valence;

crisis-style emotional delivery.

That is a declared missing stratum, not a statistical problem that balancing can solve.

The hostile stress-matrix cases should remain situational /intent tests. They should not be repurposed as evidence that the dream corpus contains hostile dispositions.

If negative-valence disposition becomes a required product claim, source-memory expansion will eventually be necessary—but only through genuine, accepted, provenance-bound experiences, and under a new corpus-expansion goal.

Q4 — Is the dream step earning its cost?
Steelman: continue the dream hypothesis

The dream step may be doing something that direct affect extraction cannot:

combining several memories into one relational state;

preserving conflict such as warmth plus boundary or yearning plus hesitation;

generating a persistent dispositional interpretation rather than a per-memory label;

surfacing indirect relational structure;

producing a reusable affect profile that can color many later conversations.

The 12 dreams are not consumed after one listener item. Each can support multiple future conversational contexts, so their generation cost can be amortized.

The five-packet oracle result is encouraging: blinded annotators found the profiles affectively defensible, and the same process detected the historical counterpart contamination. That makes the dream output sufficiently credible to deserve the causal D-versus-M test.

The wider literature does not settle this question. MemEmo finds affective-memory processing broadly unresolved, while Dynamic Affective Memory offers a substantially cheaper direct-memory mechanism that should be treated as a serious comparator. 
arXiv
+1

Steelman: short-circuit immediately to D versus M

The finite-corpus wall is a reason to stop generating and start testing.

Further dream cycles would require either:

weakening an anti-repeat safety invariant;

adding new memories before knowing whether dreaming adds value;

or counting correlated re-dreams as if they were independent evidence.

None is justified before D−M is measured.

The project already has enough material for a decisive pilot:

existing D profiles:      available
qualified timing channel: available
answer invariance:        available
counterpart fixtures:     available
M arm:                    still required

If:

D ≈ M:
  direct memory is sufficient for the voice-affect endpoint

M > D:
  dreaming adds distortion or noise

D > M and D > S:
  the dream intermediate has earned additional corpus investment

This is not abandoning Persona Dream. It is exactly the experiment needed to determine whether the expensive intermediate is scientifically justified.

This preserves the earlier review discipline that reliable machinery and downstream benefit are distinct claims. 

current-round-readable-bundle

 

response

POSITION SUMMARY

Freeze the 12-cluster corpus; do not expand memories or relax anti-repeat before measuring D−M.

Treat the corpus as a finite-population census and the known pre-fix counterpart artifact as a negative control, leaving 11 valid D blocks.

Gate 2 should require at least 9/11 valid post-fix profiles supported, zero counterpart errors, and successful detection of the historical negative.

The listener study is viable as a kill-test/variance pilot, but n≈11–12 clusters can detect only a large dream effect.

Use all valid packets as the primary analysis; report tag-stratified limits and do not claim negative-valence coverage.

RECOMMENDED NEXT ACTION

Run GATE2-CENSUS-12 now:

inputs:
  all 12 existing packets
  3 blinded annotators
  11 post-fix positive packets
  1 known pre-fix counterpart-negative packet

outputs:
  majority valence decision per packet
  majority dominant-tag decision per packet
  unsupported-affect findings
  counterpart findings
  exact binomial intervals
  PASS / PARTIAL / FAIL current-corpus status
  frozen manifest of packets eligible for the D/M listener pilot

Do not launch another dream cycle. The immediate action after that receipt is to generate compute-matched M profiles for the frozen eligible manifest.

DISAGREEMENTS

I reject expanding the memory corpus merely to recover the original sample-size target.

I reject treating re-dreams from an already consumed cluster as independent packets in the D−M study.

I reject a balanced subset as the primary analysis; all valid current-corpus packets should be included.

I reject describing 12 packets as 12 valid D treatments if the historical Brandon/Kai artifact remains among them.

I reject interpreting a null n=12 pilot as definitive proof of no dream effect; only a preregistered futility interval should trigger the pivot.
