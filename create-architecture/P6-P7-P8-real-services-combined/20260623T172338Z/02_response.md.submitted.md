# Clarify, Then Create Full Architecture And Code Solution

## Objective

Create one combined solution zip for PersonaPlex P6+P7+P8 — wiring the existing
deterministic adapters to real live services. The creation bundle is attached as a
zip (`creation-bundle-attachment.zip`). Read all files in the zip before asking
clarifying questions or creating the solution.

## Required Output

Return ONE downloadable solution zip named:
```
personaplex-p6-p7-p8-real-services-combined-solution.zip
```

`MANIFEST.json.bundle_filename` must match. Do not return PASS/NEEDS_CHANGES/BLOCKED.

If any material ambiguity remains, return only numbered clarifying questions.
If no material ambiguity remains, return the complete solution zip.

The zip must include finished repo-relative files under `skills/personaplex/...`:
- Updated adapter modules wiring real endpoints  
- Tests and sanity scripts for each real-service target  
- Deterministic fallback fixtures when services are unavailable  
- MANIFEST.json, ARCHITECTURE.md, prompt_improvements.md  
- Exact commands to run and expected exit codes

## Key Discovery Results

**Memory daemon:** http://127.0.0.1:8601  
  - POST /upsert body: {"collection": str, "documents": [{_key, ...}], "skip_embedding": bool}  
  - POST /create-evidence-case body: {"question": str, "context_framework": "SPARTA", "enable_llm": false, "include_cae_tree": false, "fail_on_degraded_evidence": false}

**Deepgram WebSocket:** wss://api.deepgram.com/v1/listen, API key from DEEPGRAM_API_KEY env var

## Constraints

- Keep P0/P1/P2/P3-P5 architecture; extend existing adapter modules.
- Do not claim real service proof from deterministic fixture receipts.
- Receipts must honestly record real_* flags (true/false) per attempt.
- No inline vectors in memory payloads. Audio by path/hash metadata.

---

Completion contract for browser automation:

At the very end of your final answer, print exactly:

<<<WEBGPT_DONE:20260623T174309Z:6c6a2f88>>>

Do not print anything after that marker.
