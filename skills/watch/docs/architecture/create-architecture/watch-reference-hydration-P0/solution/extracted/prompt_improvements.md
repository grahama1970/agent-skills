# Prompt Improvements for Next Watch Reference-Hydration Round

Ask the project agent to include these items in the next WebGPT bundle:

1. Exact current repo tree for `skills/watch/scripts`, `skills/watch/tests`, and `skills/watch/docs/architecture/generated` so patch paths can be smaller and less speculative.
2. The current `build_identity_reference_manifest.py` and `verify_tracking_identity.py` contents, not just filenames, so the next bundle can patch existing code instead of adding isolated P0 helpers.
3. One real movie metadata sample and one real non-movie source manifest sample with sensitive fields redacted.
4. The desired approval representation for reference images: manual JSON flag, UI review artifact, or signed manifest field.
5. The exact Qdrant collection names and embedding model already used by the memory skill, if fixed.
6. The Arango collection naming convention and whether Watch collections already exist.
7. The expected `$memory` write/evidence-case API shape, including required fields and receipt format.
8. A negative-control recall query to prove that unsupported identities are not retrieved.
9. Whether YouTube should be treated as `source-provided manifest required` for all channels or only for non-cinema/OSINT streams.
10. Raw command outputs from the local P0 tests after porting, separated into dry-run, mocked, and live sections.

Remove or avoid:

- claims that Brave/movie-domain candidate URLs prove scene visibility;
- claims that YOLO/ByteTrack labels identify named characters;
- claims that planned Qdrant pointers are writes;
- broad UI redesign asks while the persistence/identity contract is still unproven.

Phrase the next objective as a bounded rung:

> Port P0 reference-hydration contracts into the existing Watch ingest preflight, prove movie candidate hydration and non-movie manifest fail-closed behavior, then stop before live Qdrant/Arango/memory writes.
