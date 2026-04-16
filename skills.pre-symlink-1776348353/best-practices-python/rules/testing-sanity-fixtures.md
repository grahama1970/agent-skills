---
title: Prefer real small fixtures for parsing/IO code
impact: MEDIUM
impactDescription: exercises real code paths without heavy integration dependencies
tags: testing, fixtures
---

## Prefer real small fixtures for parsing/IO code

**Incorrect:**
```py
def test_parse():
    payload = {"hard": "to maintain"}
    assert parse(payload)["id"] == "x"
```

**Correct:**
```py
def test_parse_fixture():
    payload = load_fixture_json("tests/fixtures/payload.json")
    result = parse(payload)
    assert result.id == "x"
```

### Notes
- Fixtures are easier to extend and match production shapes.
