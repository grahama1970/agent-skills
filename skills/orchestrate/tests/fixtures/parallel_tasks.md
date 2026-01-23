# Task List: Parallel Execution Test

## Context
Test fixture for verifying parallel group execution.
Tasks in the same parallel group should run concurrently.

## Tasks

- [ ] **Task 1**: Create file A
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: none
  - **Definition of Done**:
    - Test: Creates /tmp/orchestrate-test/file_a.txt
    - Assertion: File exists with content "Task 1 complete"

- [ ] **Task 2**: Create file B (parallel with Task 3)
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1
  - **Definition of Done**:
    - Test: Creates /tmp/orchestrate-test/file_b.txt
    - Assertion: File exists with content "Task 2 complete"

- [ ] **Task 3**: Create file C (parallel with Task 2)
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1
  - **Definition of Done**:
    - Test: Creates /tmp/orchestrate-test/file_c.txt
    - Assertion: File exists with content "Task 3 complete"

- [ ] **Task 4**: Merge files (depends on parallel tasks)
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 2, Task 3
  - **Definition of Done**:
    - Test: Creates /tmp/orchestrate-test/merged.txt
    - Assertion: File contains contents of A, B, and C

## Questions/Blockers
None
