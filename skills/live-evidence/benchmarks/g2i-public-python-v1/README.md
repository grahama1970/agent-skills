# g2i-public-python-v1 benchmark pack

Pinned external specification benchmark for Live Evidence (#1455).

- Source: `g2i/python-api-challenge` @ `25ceb5ad7005782e3015a9da750143ac99a87fde` (README task spec only; see `source-manifest.json` for digest, retrieval date, and license limitation).
- Everything else here is owned and clean-room: rubric, progressive script, oracles, fixtures. No G2i implementation code or candidate data is used.
- Scope of any comparison claim is fixed by `benchmark.json` `comparison_scope` and enforced by the claim-hygiene oracle: the report may state measured metrics on this pinned public challenge and may NOT claim to beat, copy, or outperform G2i's production product.
- Campaign cases G2I-01..G2I-07 map to tickets #1449-#1454; the release marker `LIVE_EVIDENCE_G2I_PUBLIC_BENCHMARK_READY` is emitted only when every blocking case passes twice from clean state with live receipts.
