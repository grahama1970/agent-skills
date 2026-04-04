# Sections (order + grouping)

1. Correctness (correctness) — CRITICAL/HIGH  
   Prevent hidden failures, make behavior explicit, and preserve debugging context.

2. Security (security) — CRITICAL/HIGH  
   Prevent injection, unsafe parsing, and misuse of untrusted input.

3. Conventions (conventions) — HIGH  
   House rules: Loguru, Typer, httpx, uv/pyproject, functions-first, docstrings.

4. Testing & Sanity (testing) — HIGH/MEDIUM  
   Deterministic tests, non-mocked sanity checks, and helpful fixtures.

5. Async & Concurrency (async) — HIGH/MEDIUM  
   Prevent event-loop blocking, cancellation leaks, and concurrency hazards.

6. Performance (perf) — MEDIUM  
   Avoid accidental O(n²), redundant work, and hot-path inefficiencies.

7. Packaging (packaging) — MEDIUM  
   Reproducible installs and clean dependency boundaries with uv + pyproject.

8. Logging & Observability (logging) — MEDIUM  
   Diagnosable failures with structured, contextual logs.

9. Style & Maintainability (style) — MEDIUM/LOW  
   Readability, reviewability, and small modules with clear boundaries.
