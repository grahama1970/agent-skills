# Competition Report: `add_numbers(*values)`

## Task

Implement a Python function `add_numbers(*values)` that accepts N numbers and returns their sum, evaluated on **best-practices Python compliance** and **correctness**.

## Competitors & Approaches

Both competitors arrived at the same minimal, idiomatic implementation—delegating to Python's built-in `sum()`:

```python
def add_numbers(*values):
    return sum(values)
```

The differentiator was not the code itself but the **accuracy and precision of the supporting explanation** each competitor provided alongside their solution.

- **handler-opencode-go-deepseek-v4-pro** — Submitted the correct function but made two factual overclaims in its receipt: (1) that `sum()` works for "any type supporting `+`" (it does not—e.g., `sum(["a", "b"])` raises `TypeError`), and (2) that the return type is "an integer if all operands are integers, else float," ignoring valid numeric types like `complex`, `Decimal`, and `Fraction`.

- **handler-gpt-5-5-medium** — Submitted the identical function with examples covering integers, mixed int/float input, negatives, and the empty-input edge case. Crucially, its explanation avoided the inaccurate generalizations present in the other submission.

## Position

**Winner: handler-gpt-5-5-medium** with a score of **19.5/20** versus **19/20** for handler-opencode-go-deepseek-v4-pro.

Both solutions are functionally identical and fully correct. The half-point margin comes entirely from best-practices scoring, where the winning submission demonstrated more careful, accurate documentation of behavior—a core tenet of Python best practices.

## Evidence

| Criterion | handler-opencode-go-deepseek-v4-pro | handler-gpt-5-5-medium |
|---|---|---|
| Correctness | 10/10 | 10/10 |
| Best-practices Python | 9/10 | 9.5/10 |
| **Total** | **19/20** | **19.5/20** |

- Both correctly handle zero arguments (returning `0`), arbitrary positional numeric arguments, and mixed int/float inputs.
- Neither included type annotations or a docstring—a minor gap noted for both, though not required for this trivial task.
- The decisive factor: handler-gpt-5-5-medium's receipt contained **no factual errors**, while handler-opencode-go-deepseek-v4-pro's contained two demonstrably incorrect claims about `sum()`'s behavior.

## Uncertainties

- The specification did not clarify whether zero arguments must be accepted, whether non-numeric inputs require explicit validation, or which numeric protocols must be supported.
- Both submissions reasonably preserved Python's native `sum()` semantics, making these ambiguities non-impactful.

## Blockers

None. Both implementations are correct and production-ready. The competition is cleanly resolved.

## Winning Function

```python
def add_numbers(*values):
    return sum(values)
```