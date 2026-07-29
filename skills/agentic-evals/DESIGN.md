# Agentic Eval Design

Principles:

1. Run repeated trials before claiming stability.
2. Include positive, negative, and adversarial cases when the workflow supports them.
3. Score outcomes, trajectory expectations, and safety constraints separately.
4. Prefer deterministic grading before optional model judges.
5. Emit immutable JSON evidence for every run.
6. Use explicit readiness states: `READY`, `USABLE_WITH_GAPS`, `NOT_READY`, and `NOT_ESTABLISHED`.

This first implementation covers deterministic command cases. LLM judges and
live-service fixtures should be added only after this runner is integrated with
the existing `eval-skills` fixture ecosystem.
