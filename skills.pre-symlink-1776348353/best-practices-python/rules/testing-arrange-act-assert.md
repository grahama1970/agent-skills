---
title: Write tests with Arrange/Act/Assert structure
impact: MEDIUM
impactDescription: improves readability and reduces brittle assertions
tags: testing, pytest
---

## Write tests with Arrange/Act/Assert structure

**Incorrect:**
```py
def test_it():
    assert do(1) == 2
    assert do(2) == 3
```

**Correct:**
```py
def test_increment():
    # Arrange
    x = 1
    # Act
    y = do(x)
    # Assert
    assert y == 2
```

### Notes
- Prefer one behavior per test.
- Parametrize instead of duplicating structure.
