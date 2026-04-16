---
title: Include non-mocked sanity tests
impact: HIGH
impactDescription: catches integration breakage unit tests miss
tags: testing, sanity, integration
---

## Include non-mocked sanity tests

**Incorrect:**
```py
def test_ingest():
    # everything mocked
    ...
```

**Correct:**
```py
def test_sanity_ingest_smoke(tmp_path):
    # minimal real-path test: parse real fixture and write to temp output
    out = tmp_path / "out.json"
    n = ingest_fixture_to_path("tests/fixtures/sample.json", out)
    assert n > 0
    assert out.exists()
```

### Notes
- Sanity tests should be small and deterministic.
- Prefer local fixtures + temp dirs; avoid real network unless explicitly allowed.
