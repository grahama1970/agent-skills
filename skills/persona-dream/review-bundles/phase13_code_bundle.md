# Persona Dream Phase 13 code gate

## current_gate

Implement only the real Phase 13 grounded self-interpretation and Theory-of-Mind validation boundary for the existing provider-return observation.

## one blocking defect

`skills/persona-dream/scripts/write_cognitive_loop_dry_run.py` emits a fixed proposal, always-blocked ToM, zero accepted interpretations, and no executable validator. There is no command that can produce and validate Phase 13 artifacts from the real `dream_observation_packet.v1.json`.

## Live authority

- Base repository: `agent-skills@main`, commit `0854cd9b`.
- Run: `pipeline-complete`.
- Revision: `rev_idea_f3f9c48d5cc2`.
- Dream: `dream_ff2ce7f310fdda2d`.
- Provider request ID: `019f6bef-0c0f-7921-8a5e-a1f12890fb75`.
- Provider MP4 SHA-256: `sha256:2545394fb8e48694acb2751b25cbf6fc55a4dfdbde66e241deecfb5f2f1ecd33`.
- Observation packet: `skills/persona-dream/reports/pipeline-complete/.persona-dream/revisions/rev_idea_f3f9c48d5cc2/phase_12_watch_observation/dream_observation_packet.v1.json`.
- Observation SHA-256: `sha256:835ae475ac26ae3a7e8fb79da2f570949285fd8aafbe39203ef5033adb2f95f7`.
- Observation proof: `mocked:false`, `live:true`, one attempt for the successful request hash, 12/12 frames described, no audio expected, and no checker errors.

## Required behavior

Write an apply-ready unified diff or finished-file ZIP that:

1. Adds an executable Phase 13 writer and independent validator.
2. Reads and rehashes the real Phase 12 packet and every cited frame.
3. Resolves original source-memory residue from existing Phase 01/02 immutable artifacts or exact Memory reads; do not invent residue text.
4. Produces `phase_13_interpretation/dream_self_interpretation.v1.json` containing bounded interpretation candidates, uncertainty, exact observation fact/frame references, exact source-memory references, and explicit synthetic/non-factual labeling.
5. Produces `phase_13_interpretation/tom_validation_receipt.v1.json` with independently accepted and rejected ToM candidates, evidence/support reasons, uncertainty, persona-scope checks, and identity-drift blockers.
6. Rejects any interpretation or ToM claim lacking both observation evidence and applicable source-memory evidence.
7. Keeps model output as a candidate claim; deterministic validation decides acceptance.
8. Adds `run.sh` commands to write and check the real Phase 13 artifacts.
9. Adds focused tests for fixture rejection, unsupported ToM rejection, wrong-persona residue, hash mismatch, and valid real-shaped evidence wiring. Tests are wiring-only; the real command below is the gate.
10. Makes no provider call and leaves the existing provider attempt ledgers unchanged.

If a live model call is necessary to generate candidate interpretation text, use the existing Scillm contract and emit a prompt/request/response receipt. Do not hard-code a supposedly meaningful interpretation in Python.

## allowed files or module boundary

- `skills/persona-dream/run.sh`
- new or existing `skills/persona-dream/scripts/*phase13*`
- `skills/persona-dream/schemas/*interpretation*`
- `skills/persona-dream/schemas/*tom*`
- `skills/persona-dream/tests/*phase13*`

## required live proof

This exact command must pass against the real run after the writer executes:

```bash
skills/persona-dream/run.sh check-phase13-grounded \
  --run-root skills/persona-dream/reports/pipeline-complete \
  --revision-id rev_idea_f3f9c48d5cc2 \
  --json
```

The receipt must report `mocked:false`, `live:true`, the exact observation hash, positive accepted interpretation count, explicit accepted/rejected ToM counts, zero unsupported claims, persona scope `embry`, and provider attempts unchanged.

## stop condition

Stop when the unified diff or finished-file ZIP implements the writer, validator, schemas, commands, and focused tests needed for the real Phase 13 proof. Do not return a roadmap.

## forbidden adjacent scope

Do not implement Memory writes, graph recall, semantic recall, behavior probes, UI, server routes, provider calls, documentation, Phase 14, Phase 15, or Phase 16 in this patch.

## Research context

The required Brave Search pre-step was attempted through `skills/brave-search/brave_search.py` with a valid configured key and then directly against Brave's API with a 15-second bound. Both failed before returning results; the direct request failed with DNS resolution timeout. No external claims are therefore being supplied as research evidence. Use current authoritative sources if needed, but the code gate is primarily governed by the repository's immutable observation, Memory, Scillm, and Persona Dream contracts.
