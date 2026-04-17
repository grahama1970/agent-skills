---
title: Do not rely on real network in tests by default
impact: MEDIUM
impactDescription: keeps tests deterministic and fast; avoids flaky CI failures
tags: testing, determinism
---

## Do not rely on real network in tests by default

**Incorrect:**
```py
def test_fetch_real():
    assert fetch("https://example.com")
```

**Correct:**
```py
def test_fetch_fixture(httpx_mock):
    httpx_mock.add_response(json={"ok": True})
    assert fetch("https://api") == {"ok": True}
```

### Notes
- Network tests can exist as explicit, opt-in smoke tests (marked/segregated).
