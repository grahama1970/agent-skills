POSITION

The gate passed because the claim changed. V1 attempted to establish positive visual resemblance. V2 establishes only that each slide avoids three weak lower-tail anomalies: semantically remote content, insufficient nonwhite pixels, and a globally off-corpus color histogram.

That is a defensible smoke test. It is not a defensible “looks like a Graham pitchdeck” gate.

The diagnosis of V1 was correct: the retrieval embedding is dominated by rendered words and should not be the primary style metric. The acceptance change was not clean, however. The intermediate gate used a duplicate-free per-slide floor of 0.452 plus a deck-median floor of 0.547. The commit that flipped the north-star to PASS lowered the per-slide threshold to the positive corpus minimum, 0.395, and deleted the deck-median requirement. The current code still calculates the deck median but does not use it. That is post-hoc threshold relaxation, even though the reason for distrusting the embedding is sound.

The committed agentic eval contains one positive north-star style case and no matched style-negative case. Its negative case tests unrelated design-lint defects. The fixture also explicitly says the result does not prove human “recognizably mine” acceptance. The eval therefore contradicts its own “looks like Graham” label.

My blunt verdict:

Accept V2 as HOUSE_NON_ANOMALOUS. Reject it as LOOKS_LIKE_GRAHAM.

EVIDENCE-GAPS
1. The threshold was selected on the deck it was used to certify

The Sparta deck was simultaneously:

the development target;

the source of the observed failures;

the target of thirteen visual iterations;

the reason for changing the metric interpretation;

the artifact used to declare the redesigned gate successful.

That is test-set leakage. It does not mean the deck is bad. It means the PASS says nothing yet about the gate’s behavior on an unseen generated deck.

The historical sequence is especially problematic: V1 failed, an intermediate duplicate-robust deck bar still failed, and then the deck-level bar disappeared in the PASS commit.

2. The new pixel channels are spatially blind

ink_fraction is the proportion of non-background pixels. palette_similarity is a 6×6×6 RGB histogram coefficient over those pixels. Neither metric records where any pixel occurs. A random spatial permutation of the content pixels preserves both scores exactly.

They therefore cannot distinguish:

a Graham composition from a three-column startup card grid;

a well-scaled illustration from colored noise;

a speech bubble from a rectangle elsewhere;

a deliberate asymmetric scene from mechanically tiled panels;

correct hierarchy from arbitrary object placement;

valid typography from an ugly font/size/alignment mixture.

The implementation also has only a lower ink bound. A grossly overfilled page can pass just as easily as a well-composed one.

3. The palette calibration remains duplicate-contaminated

You correctly identified duplicates as invalidating embedding percentiles. But corpus_mean_histogram() still averages every PNG equally. Repeated pages therefore receive repeated votes in:

the corpus mean palette;

the ink distribution;

the palette-similarity distribution.

The new channels inherit the same independence problem you diagnosed in the old channel. They need either:

one vote per unique visual-design cluster; or

separate usage-weighted and unique-design-weighted calibrations.

The current mean is also calculated across all archetypes. That creates an averaged palette distribution that may describe no actual archetype particularly well.

4. The gate ignores the ten archetypes it claims to implement

The corpus has ten explicitly measured archetypes with substantially different page anatomy. Assertion-plus-art pages, sparse section dividers, dense reference pages, close pages, and TOCs should not share one ink floor, one palette distribution, or one composition model.

The catalog already provides the useful structural information: element counts, visual area, word density, bounding-box patterns, picture counts, screenshot stacking, and per-archetype exemplars. Yet the current similarity command sees only PNGs and cannot know which archetype a slide claims to implement.

This produces both failure directions:

an underfilled content slide can masquerade as a legitimate divider;

a legitimate sparse close or divider can be forced to add meaningless art to clear global density floors.

5. The supposed structural backup is itself weak and internally inconsistent

house-conformance counts any authored PICTURE, GROUP, or FREEFORM object as a visual, irrespective of size, area, content, or role. Two tiny meaningless groups can satisfy the density rule. It then turns the corpus median of two pictures into a universal minimum.

That contradicts the measured archetypes:

bullet slides have at most one picture;

close pages sometimes have one drawing;

sparse dividers deliberately contain little;

covers are layout-borne and exceptional.

A median is not an invariant and should never have become a hard per-slide floor.

6. The style result is not cryptographically bound to the deck render

house-similarity accepts an arbitrary PNG directory. The north-star script does not prove that:

every source PPTX slide produced exactly one scored PNG;

the PNGs are hashes from the render stage just completed;

no PNG was replaced with a passing corpus page;

the render DPI, renderer version, fonts, and dimensions match calibration;

the Qdrant collection and embedding model are the calibrated versions.

A failed PDF conversion producing one passing page could satisfy the style command because it requires only that at least one matching PNG exists. The document slide-count check and similarity page count are not reconciled.

The palette histogram is loaded from a mutable absolute workstation path rather than a committed, digest-bound calibration artifact.

7. The control set is much too easy

“Real page passes; off-house teal 3D art fails” proves that the histogram notices a large palette mismatch. It does not test the actual hole.

A useful negative control must hold nuisance variables constant:

identical words;

identical template chrome;

identical palette histogram;

identical ink fraction;

identical number of pictures and shapes;

while changing only layout, typography, hierarchy, or illustration register.

No such matched negative appears in the committed agentic eval.

RISKS

Goodharted artwork: generated art is explicitly requested in the house palette, while the decisive visual metrics are ink quantity and house-palette distribution. The asset generator is being optimized against the gate’s easiest dimensions.

Generic-deck false passes: a conventional card-grid deck can inherit the template chrome, reuse the correct SPARTA words, include two nominal visuals, and histogram-match its colors.

Legitimate-archetype false failures: global lower floors pressure sparse dividers, close pages, and covers toward unnecessary visual material.

Calibration drift: the mutable histogram file, live embedding service, live Qdrant index, renderer, fonts, and DPI can change the result without a source change.

Single-project overfitting: the eval proves assembly of one heavily curated Sparta bundle, not that a new README will produce a similar result.

Semantic overclaim: “all slides avoided extreme anomalies” is being reported as “the deck looks like Graham.”

VERDICT-ON-EACH-QUESTION
1. Is the embedding anomaly floor defensible?

Demoting the embedding is defensible. The 0.395 calibration is not.

The evidence shows that this embedding should not decide style. Treating it as a secondary anomaly signal is reasonable. But the positive-corpus minimum is the weakest possible threshold:

it guarantees zero false negatives on the calibration positives by construction;

it is determined by one outlier;

it has no safety margin;

it provides no estimate of false-positive behavior;

it was selected after observing the candidate deck;

the deck-level requirement was removed at the same time.

That is threshold-shopping in the acceptance decision, even though the underlying metric diagnosis was legitimate.

I would do one of two things:

Preferred: remove embedding from the style verdict entirely and report it as SEMANTIC_RENDER_DIAGNOSTIC. Claim authorization already establishes content provenance.

Acceptable alternative: calibrate it as an anomaly detector using:

exact/perceptual duplicate clusters;

leave-one-entire-deck-out folds;

exclusion of the source deck and duplicate cluster from each real-page query;

fixed renderer, DPI, dimensions, font set, model digest, and index digest;

hard negatives containing the same text but foreign composition;

a predeclared false-reject and false-pass target;

cluster- or deck-level bootstrap intervals;

a north-star deck that is not inspected until thresholds are frozen.

If the channel cannot distinguish same-text house pages from same-text foreign pages, delete it from the verdict rather than lowering its threshold again.

2. Are ink fraction and palette histogram sufficient?

No. They leave the central style question completely open.

They are useful cheap rejectors for blank pages and gross palette drift. They are not positive evidence of composition, typography, or layout.

My ranking is:

1. (a) Archetype-conditioned structural distance over the existing JSON records

This is clearly the first addition. It is already available, deterministic, interpretable, and directly measures the dimensions the old gate’s field diffs identified.

Do not reduce it to scalar counts. Include:

normalized bounding boxes by semantic role;

visual, text, and empty-space area;

element-type counts;

picture and screenshot area, not merely count;

horizontal and vertical occupancy;

alignment lines;

overlap and containment;

title/body/footer regions;

number and placement of chevrons;

screenshot-stack geometry;

bubble and connector geometry;

font-size distribution;

alignment, underline, bold, and line-spacing distributions;

archetype-specific visual density.

Compare only against the declared archetype and return field-level differences.

2. (d) A text-masked spatial-pyramid channel

Create a semantic render in which:

text glyphs become neutral text-region masks;

pictures, lines, bubbles, connectors, and whitespace receive separate mask classes;

color histograms are calculated by spatial region rather than globally;

edge density and occupancy are measured at several scales.

This is cheap, deterministic, and catches the exact attack global histograms miss: moving the same ink and colors into the wrong places.

3. (b) A DINOv2-class non-aligned vision embedding

Use it only on text-masked images and only after structural calibration. It may add useful sensitivity to scene composition, drawing register, and object scale, but it can still reward matching subject matter rather than matching design.

It must prove incremental value on frozen negatives before becoming a gate.

4. (c) Gram-matrix texture statistics

Last place. They can measure texture and rendering character, but they are weak on layout and hierarchy and will likely reward palette-matched diffusion art. They duplicate much of what the current histogram already measures.

3. Is “no slide is anomalous” the right gate semantics?

No. It is the right semantics for an anomaly filter and the wrong semantics for “looks like a Graham pitchdeck.”

A deck in which every slide sits just above three low floors need not resemble any real page or real deck. Separate marginal p5 constraints also do not define the corpus’s joint typical region. A combination of ink and palette values can pass even when that combination never occurs on a real page.

Reinstate a deck-level positive bar, but do not reinstate embedding median >= 0.547 as the style bar. That embedding remains text-confounded. The current 0.475 median says the deck is semantically less similar to the corpus than the duplicate-free originals; it does not reliably say the design is wrong.

The replacement should aggregate valid channels:

each slide passes its declared archetype’s structural contract;

the deck median structural percentile lies inside the held-out author-deck range;

the lower-decile structural percentile is not an outlier;

sparse and dense archetypes are evaluated against their own distributions;

required profile-level arc elements exist;

an optional text-masked vision score supplies independent positive evidence;

no single exact duplicate or repeated title dominates the result.

The output should have two distinct states:

HOUSE_NON_ANOMALOUS: all hard floors passed;

HOUSE_POSITIVE_MATCH: calibrated structural/deck-level positive evidence passed.

Until the second exists, the north-star should not print “looks like a Graham deck.”

4. Does pinned AI-generated art break reproducibility?

It does not break artifact-level reproducibility. It does expose that this is not a cold compiler eval.

The generated images were added to the bundle as preselected, project-specific assets and are not generated during the north-star run. Hash-pinning them makes repeated evaluation deterministic, subject to renderer and metric-version stability.

What the eval proves is therefore:

Given this approved outline, this tailored asset bundle, this template, and these approvals, the compiler assembles a passing deck.

It does not prove:

Given an unseen README, the compiler autonomously produces the visual material needed for a Graham-style deck.

The human effectively supplied part of the answer key. That is acceptable when stated honestly. It becomes a problem only when the eval is described as a cold README-to-deck capability.

Split the evaluation:

artifact eval: network disabled, pinned assets only, fully deterministic;

authoring eval: unseen README, no project-specific art, expected either to use an approved reusable asset pool or stop at NEEDS_APPROVED_ART;

stochastic image proposal benchmark: separate from publication and allowed to be nondeterministic.

Do not regenerate assets inside the deterministic release gate.

5. Most likely false PASS

A generic startup/card-grid deck skinned with Graham chrome and palette.

The construction is straightforward:

Use the real Graham template, so band, title, footer, page number, and identity mark pass.

Paste the correct SPARTA wording, so the text-dominated embedding clears 0.395.

Add two arbitrary image or group objects per slide, possibly tiny, so house-conformance clears its visual count.

Recolor the content area to match the corpus mean histogram.

Ensure at least 15.34% of pixels are nonwhite.

Retain generic cards, mechanical symmetry, poor typography, weak hierarchy, and stock 3D imagery.

Every current metric can pass while the deck remains unmistakably off-house.

The cleanest deterministic attack fixture is a content-layout shuffle: preserve each passing slide’s text, colors, element types, areas, and object counts, but randomly permute the nonchrome bounding boxes. The current pixel marginals remain unchanged or nearly unchanged, the embedding still reads the same words, and the structural gate still sees the same object classes.

EXECUTABLE_SLICES
Slice 1 — Bind the style gate to a frozen calibration and exact render

Capability: one content-addressed house_gate_calibration.v1 containing corpus membership, duplicate cluster, archetype, page hash, record hash, render profile, histogram, model identity, index digest, thresholds, and calibration split.

Bash
cd skills/pitchdeck

./run.sh calibrate-house-gate \
  --corpus-manifest fixtures/house-gate/corpus.v1.json \
  --records-dir /mnt/storage12tb/skills/pitchdeck/outputs/house-slides/records \
  --renders-dir /mnt/storage12tb/skills/pitchdeck/outputs/house-slides/pages \
  --output fixtures/house-gate/calibration.v1.json

python -m pytest -q tests/test_house_gate_binding.py

Acceptance:

The 203 indexed, 233 rendered, and 263 catalogued populations are explicitly reconciled.

Every page has deck_id, archetype_id, duplicate_cluster_id, image hash, and record hash.

Calibration thresholds and histogram derive from the artifact, never hard-coded constants.

house-gate requires the PPTX, render receipt, calibration artifact, and expected page count.

Replacing one PNG with a real corpus page fails RENDER_HASH_MISMATCH.

Dropping or adding one PNG fails PAGE_COUNT_MISMATCH.

A 70-DPI render presented with the 50-DPI calibration fails.

Changing the histogram, model, index, renderer, or font digest invalidates the gate receipt.

Slice 2 — Add matched adversarial style negatives

Capability: deterministic counterfactual decks that preserve nuisance variables while breaking one style dimension.

Bash
python scripts/build_house_gate_adversaries.py \
  --source-pptx fixtures/house-gate/heldout-house.pptx \
  --output-dir /tmp/pitchdeck-house-adversaries

./run.sh benchmark-house-gate \
  --cases /tmp/pitchdeck-house-adversaries/cases.json \
  --calibration fixtures/house-gate/calibration.v1.json

Required mutants:

bbox-shuffle: preserve text, colors, object types, and areas; move content objects.

palette-matched-card-grid: generic card layout with exact house histogram.

typography-swap: preserve text and bboxes; replace sizes, alignment, emphasis, and spacing.

two-tiny-visuals: satisfy object count with meaningless small visuals.

art-register-swap: same text/layout/palette, generic 3D art instead of drawn scene art.

archetype-mismatch: content slide rendered as a divider.

arc-shuffle: individually valid pages in an implausible deck sequence.

Acceptance:

At least one of these must be demonstrated to pass V2; otherwise the suspected hole was not reproduced.

The redesigned full gate rejects every seeded mutant.

Unchanged controls pass.

No threshold is modified after viewing the north-star result.

Results report false-pass and false-reject rates by deck, duplicate cluster, and archetype.

Slice 3 — Implement archetype-conditioned structural and typography distance

Capability: every slide declares one of the ten archetypes and is scored only against duplicate-free examples of that archetype.

Bash
./run.sh calibrate-house-structure \
  --corpus-manifest fixtures/house-gate/corpus.v1.json \
  --output fixtures/house-gate/structure-calibration.v1.json

./run.sh house-structure \
  --document /tmp/pitchdeck-e2e/deck.document.json \
  --pptx /tmp/pitchdeck-e2e/deck.pptx \
  --calibration fixtures/house-gate/structure-calibration.v1.json \
  --json

Acceptance:

Missing or unknown archetype fails.

A recipe-to-archetype mismatch fails.

Bounding-box shuffle fails while a color-only change leaves the structural score stable.

A palette-matched generic card grid fails.

Typography swap fails.

Visual area is measured; two tiny visuals do not satisfy an assertion-plus-art page.

Sparse close/divider pages are not required to meet assertion-plus-art density.

Rare archetypes such as cover and TOC use explicit contracts rather than pretending that n=2 or n=5 supports a reliable percentile.

Failure output names the concrete dimensions: visual area, occupancy, typography, screenshot stack, alignment, or bubble geometry.

Slice 4 — Restore a duplicate-robust deck-level positive bar

Capability: a deck score derived from valid per-slide channels, calibrated by leave-one-entire-deck-out evaluation.

Bash
./run.sh calibrate-house-deck-gate \
  --corpus-manifest fixtures/house-gate/corpus.v1.json \
  --fold-by deck \
  --group-by duplicate_cluster_id \
  --output fixtures/house-gate/deck-calibration.v1.json

./run.sh house-gate \
  --pptx /tmp/pitchdeck-e2e/deck.pptx \
  --document /tmp/pitchdeck-e2e/deck.document.json \
  --render-receipt /tmp/pitchdeck-e2e/render-receipt.json \
  --calibration fixtures/house-gate/deck-calibration.v1.json

Acceptance:

Each of the five real decks is evaluated while entirely excluded from its calibration fold.

Exact and near-duplicate slide clusters never cross folds.

All held-out real decks pass the positive deck region without lowering the threshold to the worst observed deck.

Palette-matched generic decks and shuffled-arc decks fail.

The north-star Sparta deck is excluded from all calibration and threshold selection.

The score uses structural/typographic and, if validated, text-masked vision channels—not the raw 0.547 retrieval-embedding median.

The command emits HOUSE_NON_ANOMALOUS separately from HOUSE_POSITIVE_MATCH.

Slice 5 — Evaluate a text-masked vision channel before adopting it

Capability: an ablation benchmark for a pinned non-aligned vision embedding over text-masked renders.

Bash
./run.sh benchmark-house-channel \
  --channel dinov2-masked \
  --cases fixtures/house-gate/benchmark.v1.json \
  --calibration fixtures/house-gate/calibration.v1.json \
  --output /tmp/dinov2-house-channel.json

Acceptance:

Model identifier and weights digest are pinned.

Text regions are masked from PPTX-derived text bounding boxes.

Evaluation uses frozen held-out positives and matched negatives.

The channel must materially reduce false passes over structure + spatial masks without materially increasing false rejects.

Suggested promotion rule: improve balanced accuracy by at least 0.05 on the frozen holdout and introduce no additional held-out deck failure.

If it fails that rule, it remains research-only.

Gram-matrix statistics are not implemented unless they beat this channel specifically on art-register mutants.

Slice 6 — Split deterministic artifact evaluation from cold authoring evaluation
Bash
env NO_NETWORK=1 \
  ./scripts/eval_readme_to_deck.sh \
  --mode artifact \
  --work-dir /tmp/pitchdeck-artifact-eval

env NO_NETWORK=1 \
  ./scripts/eval_readme_to_deck.sh \
  --mode cold \
  --fixture fixtures/e2e/unseen-readme-02 \
  --work-dir /tmp/pitchdeck-cold-eval

Acceptance:

Artifact mode makes no image-generation or network call.

Pinned asset hashes, normalized PPTX hash, render hashes, and style scores repeat.

Deleting or changing one generated asset fails closed.

Cold mode cannot access Sparta-specific generated assets.

With no approved art, cold mode emits NEEDS_APPROVED_ART, not a fake visual and not a style PASS.

A separately approved reusable asset pool may be used only through the asset registry.

The eval claim is rewritten as “README + approved outline + approved assets → deck” unless image production is independently evaluated.

Slice 7 — Either validate the phrase “looks like Graham” or stop printing it

Freeze a blinded holdout containing:

real Graham pages excluded from calibration;

generated pages;

foreign pages;

palette-matched generic pages;

layout-shuffled pages;

typography-swapped pages.

Bash
./run.sh evaluate-house-gate \
  --labels fixtures/house-gate/blind-holdout-labels.v1.json \
  --calibration fixtures/house-gate/deck-calibration.v1.json \
  --output /tmp/house-gate-confusion-matrix.json

Acceptance:

Thresholds are frozen before labels are opened for scoring.

At least 18 of 20 held-out house examples pass.

At most 1 of 20 matched off-house examples passes.

Results are grouped by deck and duplicate cluster, not treated as 40 independent pages when they are correlated.

Failure to meet that bar forces the public status string to remain HOUSE_NON_ANOMALOUS.

Only a validated positive classifier may emit LOOKS_LIKE_GRAHAM.

<<<WEBGPT_DONE:20260811T222241Z:ffc04eb0>>>
