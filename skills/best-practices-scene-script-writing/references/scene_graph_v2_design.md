# Scene graph v2 design (WebGPT-reviewed, 2026-09-08)

Source: $brave-search prior-art sweep + $ask webgpt design review.
Full response: /mnt/storage12tb/skills/ask/outputs/.ask_artifacts/tau-dag-runs/ask-tau-help-me-design-a-classification--390bbf402028/node-artifacts/handler-webgpt/response.md

## Prior art (brave-verified)

- Scene graphs (entity/attribute/relation decomposition) are the established
  formalism; Visual Genome proves the decomposition, NOT the vocabulary
  (75k object labels — too big). VidOR (80 objects / 50 predicates, temporal
  start/end per relation) and Action Genome (25 relations split
  attention/spatial/contact) prove SMALL closed vocabularies work.
- SG-PVR (arxiv 2606.11838): decompose video prompts into atomic
  Entity/Attribute/Action/Spatial/Temporal claims, verify each against
  temporally grounded visual evidence. Critical/Minor claim distinction.
- GenEval: presence/count/position/color are reliably VLM-checkable.
- ScreenPy: useful for parsing prose actions into claims, not as ontology.

## Decisions for scene_script.scene_graph.v2 (additive, not a rewrite)

1. Element taxonomy: add `structure` only →
   `character | creature | prop | structure | surface | effect`.
   Orthogonal `roles: [agent, light_emitter, sound_emitter]` — never new
   top-level types. Wind/rain/sunlight are `env.*` namespace, not elements
   (a VLM sees consequences, not wind).
2. Relations become closed-vocabulary triples with metadata:
   `{subject_ref, predicate, object_ref, relation_family
   (spatial|contact|attention|motion|manipulation|environment|audio),
   temporal {whole_clip | interval | ordered_phase}, frame_of_reference
   (screen|scene|subject), evidence_mode (direct|proxy), criticality
   (required|desired), observable_evidence[]}`.
   env.wind → causes_deformation_of → umbrella + observable_evidence
   replaces free-text environment_interaction as the VERIFICATION source
   (free text stays as generation prose).
3. Attributes are unary, separate from relations:
   `{name, value, criticality}`.
4. Verifier contract: one atomic claim per VLM query; closed verdicts
   `supported | contradicted | insufficient_evidence`. "Partial" is computed
   by a deterministic reducer from frame coverage (>=0.70 supported), never
   chosen by the VLM. Audio claims need an audio verifier; visual-only
   returns insufficient_evidence.
5. Per-class rubric: common dims PRESENT / ATTRIBUTE / RELATION / TEMPORAL,
   specialized per class (surfaces use region evidence not boxes; effects
   skip identity tracking; characters skip face-ID unless critical).
6. Camera gets its own track (`camera.shot/motion/framing/focus`), never
   entity relations.

## Pitfalls (do NOT let strictness hurt Kling prompts)

- criticality=desired for mood words; only concrete facts are `required`.
- Don't over-atomize motion (verify state transitions, not micro-poses).
- Relative phases over exact timestamps unless time actually matters.
- Renderer must know backend capabilities (Kling element/voice binding —
  don't restate bound facts in prose).
- The model-facing prompt stays fluent cinematic prose; the graph is the
  verification/planning IR underneath.

## Layer rule

```text
Pydantic decides whether the requested world is specified precisely.
The graph decides what facts must be true.
The prompt renderer decides how to ask the video model.
The verifier decides which atomic facts are supported.
A deterministic reducer — not the VLM — decides PASS/FAIL.
```

## Migration

- description → keep as prose + extract unary attributes
- environment_interaction → deprecate as verification source; compile to triples
- action → keep as prose + compile to action/motion/temporal claims
- v1 table stays valid; v2 adds `roles`, `attributes`, `relations`, `camera`.
