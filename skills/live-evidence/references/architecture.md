# Architecture

## Data flow

```text
RealtimeSTT callback / transcript HTTP event
  -> TranscriptEvent boundary validation
  -> RuntimeState append + SSE broadcast
  -> TriggerEngine decision
  -> EvidenceCoordinator
       -> MemoryClient (/intent, /recall)
       -> Memory CLI code-search/code-node
       -> RipgrepClient (allowlisted roots, fixed strings)
       -> manual-only Brave/Dogpile clients
  -> public-safe collection/tag/path filter
  -> EvidenceRanker
  -> ExtractiveSummarizer
  -> EvidenceCard validation
  -> append-only journal + SSE broadcast
```

## Trust boundaries

- RealtimeSTT owns audio-to-text. Live Evidence does not reinterpret raw audio.
- Memory/GMO owns ArangoDB, BM25, Qdrant/Jina, graph traversal, and code-index
  lifecycle. Live Evidence only calls supported HTTP and skill CLI boundaries.
- Ripgrep reads current source bytes and is a lexical fallback, not a semantic
  authority. It uses fixed strings, a repository allowlist, a finite deadline,
  and a global match cap.
- Brave and Dogpile are outbound network lanes and cannot activate from an
  automatic transcript trigger.
- The summarizer is extractive by default. It cannot add unsupported facts.

## Runtime layout

- FastAPI: `127.0.0.1:8765` by default.
- The live listener polls the backend session state; an operator Stop ends audio capture.
- Vite development server: `127.0.0.1:5173`, proxies `/api` to FastAPI.
- Production UI: built into `ui/dist` and served by FastAPI.
- Journals: `/mnt/storage12tb/skills/live-evidence/sessions` when available,
  otherwise `~/.local/share/live-evidence/sessions`.

See `gmo-integration.md` for the supported GMO seams and recommended future recall profile.
