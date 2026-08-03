# Acceptance and Proof

Extracted from `README.md` so the README stays a map rather than an
encyclopedia. The README links here; this file is the detail.

### Research Acceptance Boundary

The founding experiment is complete only when one non-mocked run proves all of
the following. Per-item state as of 2026-07-18 (Phase 16 completion):

1. A persona autonomously selects grounded multimodal residue and current events.
   — **PROVEN** (phase 01 idea/residue selection, live).
2. It creates a synthetic dream with complete source provenance.
   — **PROVEN** (canonical `dream_dream_successor_943b01ecd9a3`,
   `synthetic_origin: true`, 3 source memories + Watch/ToM provenance).
3. When media is rendered, the returned artifact is technically valid and
   independently analyzed by `watch`.
   — **PROVEN for the frozen historical return** (watch post-return gauntlet,
   5/5). The accepted successor return is validated; the observation packet is
   `DEGRADED` (authoritative verdicts carried by the step-36 v2 receipt).
4. Self-interpretation claims cite Watch observations and source memories.
   — **PROVEN** (phase 13, 4 interpretations, deterministic citation gate).
5. Accepted ToM records and graph edges are written through Memory and Graph
   Memory. — **PROVEN** (phase 15, 19 canonical records, exact reread-by-key).
6. Qdrant retrieves the dream from a semantically related, differently worded
   query. — **PROVEN** (phase 16 probe a: dream returned by 3 differently-worded
   queries, ranks 1/3/7; negative control excludes it).
7. ArangoDB traverses from the persona through the dream to source memories,
   observations, people, events, and ToM state. — **PROVEN** (phase 16 probe b:
   14/14 canonical edges resolve live to 3 sources + 7 Watch observations + 4
   ToM nodes; actual vertex/edge keys recorded).
8. A later persona response uses the dream appropriately while preserving the
   synthetic-versus-literal distinction. — **PROVEN** (phase 16 probes c and d:
   grounded dream use marked as a dream; literal occurrence denied; DB flags
   reread exactly). LLM routed through the Tau node; checks deterministic.
9. Identity-consistency probes show bounded evolution without destructive
   identity drift. — **PROVEN for the honest slice** (phase 16 probe e: the dream
   loop's canonical write-set is dream+edges+ToM only — it never wrote/updated an
   identity or source record; source anchors reread as literal/unchanged;
   create-persona working tree clean; Tau values/relationship Q&A stable). No
   standalone Embry persona-definition file or runnable create-persona identity
   suite exists; labeled as the honest slice.
10. Chatterbox audibly expresses the resulting persona state without becoming
    the authority that invented it. — **NOT PROVEN / OUT OF SCOPE this slice**
    (no Chatterbox/voice runtime exercised; factually out of scope). Human
    subjective acceptance of the dream video also remains the human's.

### Proof Discipline

- Do not invent memory residue when recall is empty.
- Label fixture, synthetic, inferred, observed, and literal evidence distinctly.
- Preserve source IDs, scopes, hashes, timestamps, and revision boundaries.
- Treat prompts as intent, not proof of generated-media contents.
- Treat Watch observations as evidence, not automatic psychological conclusions.
- Treat image, video, graph, embedding, persona, and Memory receipts as claims
  until their underlying artifacts and side effects are inspected.
- Do not turn one dream into an unreviewed durable identity rewrite.
- Never claim final video or personality-evolution success without concrete
  media, Watch evidence, persisted graph and embedding receipts, and later
  behavior proof.

### Common Mistakes

| Mistake | Better move |
|---|---|
| Calling Persona Dream a finished movie generator | Treat media generation as one optional part of a graph-memory consolidation experiment |
| Treating the script as proof of what the dream video contains | Run `watch` and interpret observed evidence |
| Creating a second persona or memory database | Persist through `create-persona`, `memory`, and Graph Memory Operator |
| Letting a dream silently rewrite canonical identity | Store bounded synthetic memory and ToM state; promote durable changes only through the owning gate |
| Making React Flow mandatory for autonomous dreaming | Use it as the human inspection and correction canvas over the same graph-native backend |
| Treating a contact sheet as final output | Use it as an inspectable review artifact |
| Treating provider selection as research completion | Close Watch, graph and Qdrant persistence, and future-behavior evaluation |

---

## Status vocabulary
The README uses these proof terms consistently:
| Status | Meaning |
|---|---|
| **Implemented** | Code, scripts, artifacts, or a UX surface exist |
| **Accepted evidence** | The selected run contains a receipt-backed artifact accepted by its current gate |
| **Fixture-proven** | Deterministic fixture-backed checks pass; no live external behavior is implied |
| **Live slice proven** | A real external operation or generated artifact was executed and inspected |
| **Qualified revision** | The immutable revision, required evidence, Memory projection, active pointer, and terminal repair event agree |
| **Blocked** | A named prerequisite is missing or intentionally disallowed |
| **Designed** | The architecture and evidence contract exist, but the implementation proof does not |
| **Not implemented** | No working rung currently exists |

## Per-boundary evidence detail

Moved out of `README.md`: these rows carry revision ids, request hashes,
receipt paths, and per-phase narrative. The README keeps the state and one
artifact pointer per boundary; the full chain lives here.

| Boundary | State | What that proves |
|---|---|---|
| Grounded dream packets | **Implemented** | Source links, contradiction reports, reflections, and receipts exist |
| Image and storyboard production | **Live slices proven** | Live image generation, visual review, creator/reviewer repair, and accepted-frame evidence exist |
| Phases 01-10 - Qualified successor revision | **Qualified revision at acceptance rung** | `rev_successor_943b01ecd9a3` is `PASS_ACTIVE_CONSISTENT`; the explicit human idea has 10/10 phase lineage bindings, 10 phase + 16 required-artifact Memory records and the 42-step bundle exactly reread, and the rebuilt artifact index makes the eight Phase C storyboard frames (8/8 actual-pixel identity PASS, 7/7 continuity) the active Phase 07 evidence while the montage-derived frames stay stale |
| Phase 11 - Submit and Return | **Live successor return received and accepted (agent level)** | The successor made exactly one hash-bound authorized submit (request `sha256:97688ec5…`, fal request id `019f77f0…`) and received a valid 10.041667s H.264 720p return (`sha256:59b9ff31…`). Step 36 continuity PASS v2 (ArcFace + Tau-routed pose/occlusion adjudication); steps 37-38 PASS v2 (exact line muxed and force-aligned 4.74-7.86s; visible-speaker inapplicable-by-composition per the lane C design). The earlier `rev_upstream_bf3b05d47fb8` return remains superseded historical evidence. Human subjective acceptance of the video remains open |
| Phase 12 - Watch Observation | **Live slice proven for perception-on-historical-return** | The `watch` post-return gauntlet (`scripts/watch_post_return_gauntlet.py`) runs the `watch` skill over the frozen historical Kling return, extracts scene-driven frames + Whisper transcript, and independently localizes the identity-drift and visible-speaker windows. Validated against ground truth: `watch_gauntlet/991c311f365f/watch_gauntlet_validation_receipt.v1.json` (`PASS_WATCH_GAUNTLET_VALIDATED`, 5/5 expectations). The gauntlet has since also run on the accepted successor return (`watch_gauntlet/59b9ff3155d6/`); its observation packet remains `DEGRADED` (per-frame VLM entities pending), with the authoritative visual verdicts carried by the step-36 v2 receipt |
| Phases 13-15 - Interpretation through persistence | **Live slice proven on accepted return** | On the ACCEPTED successor return, phase 13/14 text reasoning routes through the Tau node (tau `09e64a44`; no direct scillm), 4 interpretations + 4 ToM candidates pass the deterministic gates, and phase 15 wrote the FIRST canonical dream memory (19 records, exact reread-by-key) permitted only by a binding agent-level acceptance receipt; superseded/historical returns stay fail-closed |
| Phase 16 - Recall and later persona behavior | **Machine-decidable slice LIVE-PROVEN (`PASS`)** | `scripts/phase16_behavior_evaluation.py` → `phase_16_behavior_evaluation/phase16_behavior_evaluation_receipt.v1.json` (`overall_status: PASS`): (a) semantic recall returns the dream from 3 differently-worded queries (ranks 1/3/7, dense 0.59/0.43/0.74) while a `orbital telemetry` negative control does NOT; (b) multi-hop traversal resolves all 14 canonical edges live to 3 source memories + 7 Watch observations + 4 ToM nodes; (c) the persona uses the dream and marks it as a dream, with context assembled ONLY from live recall; (d) it denies literal occurrence and the `synthetic_origin=true`/`literal_historical_event=false` flags reread exactly; (e) identity is stable (loop write-set is dream+edges+ToM only, source anchors literal/unchanged, Tau values Q&A stable). All LLM probes route through the Tau node (no direct scillm). **Out of scope this slice: Chatterbox voice expression (item 10) and human subjective acceptance of the video** |
The screenshots below come from an archived Embry/Kai run. That run has not been
regenerated with every newer provider artifact. A blocked screenshot describes
the selected run root, not the full set of current development capabilities.
Provider selection is near the end of the media-production spine. It is not the
end of the founding research experiment.
---

