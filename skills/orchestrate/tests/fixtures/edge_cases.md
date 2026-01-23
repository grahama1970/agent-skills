# Task List: Parser Edge Cases

## Context
Test fixture for parser edge case testing.
Contains unusual but valid task formats.

## Tasks

- [ ] **Task 1**: Simple task with colon: in title
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: none
  - **Definition of Done**:
    - Test: Manual verification
    - Assertion: Task completed successfully

- [ ] **Task 2**: Task with unicode emoji in description
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1
  - **Definition of Done**:
    - Test: Manual verification
    - Assertion: Output contains expected text

  Description with special chars: "quotes" and 'apostrophes' and backslash\ and emoji

- [ ] 3. Alternative numbering format
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: 1
  - **Definition of Done**:
    - Test: Manual verification
    - Assertion: Numbered format parsed

- [x] **Task 4**: Already completed task
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 2, Task 3
  - **Definition of Done**:
    - Test: Manual verification
    - Assertion: Already done

- [ ] **Task 5**: Task with multiline description
  - Agent: explore
  - Parallel: 2
  - Dependencies: none

  This is a longer description
  that spans multiple lines
  and should be preserved.

  Including blank lines.

## Questions/Blockers
None
