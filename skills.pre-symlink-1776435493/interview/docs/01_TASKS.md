# Task List: Interview Skill v2 - Claude Code UX

**Created**: 2026-01-30
**Goal**: Mirror Claude Code's AskUserQuestion UX with tabbed wizard, numbered options, automatic Other, and image support

## Context

Upgrade the interview skill to provide a polished human-agent collaboration UX matching Claude Code's pattern. The TUI will use Textual's TabbedContent for wizard-style navigation, display images as `[Image X]` placeholders, and include automatic "Other" options for custom text input. HTML mode will show actual images and match the keyboard navigation.

## Crucial Dependencies (Sanity Scripts)

| Library | API/Method | Sanity Script | Status |
|---------|------------|---------------|--------|
| textual | `TabbedContent`, `TabPane` | `sanity/textual_tabs.py` | [ ] PENDING |
| PIL/Pillow | Image validation | `sanity/pillow.py` | [ ] PENDING |

> All sanity scripts must PASS before proceeding to implementation.

## Questions/Blockers

None - requirements clear from Claude Code's AskUserQuestion pattern.

## Tasks

### P0: Setup & Sanity Scripts (Sequential)

- [x] **Task 1**: Create sanity scripts for dependencies
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: none
  - Files to create:
    - `sanity/textual_tabs.py` - Verify TabbedContent, TabPane, Label work
    - `sanity/pillow.py` - Verify PIL can validate image files
  - **Definition of Done**:
    - Test: `bash sanity/run_all.sh`
    - Assertion: Both scripts exit 0, print PASS

- [x] **Task 2**: Create test fixtures for new question format
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 1
  - Files to create:
    - `examples/claude_style.json` - Sample questions with headers, options, images
    - `examples/test_image.png` - Small test image (100x100 placeholder)
  - **Definition of Done**:
    - Test: `python -c "import json; json.load(open('examples/claude_style.json'))"`
    - Assertion: JSON parses without error, contains at least 3 questions with headers

### P1: Data Model Updates (Sequential after P0)

- [x] **Task 3**: Update question schema in interview.py
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 2
  - Changes to `interview.py`:
    - Add `header: str` field (max 12 chars, used as tab label)
    - Add `options: List[dict]` with `label` and `description` fields
    - Add `images: List[str]` for image paths
    - Add `multi_select: bool` for multiple choice
    - Keep backward compatibility with old format
  - **Definition of Done**:
    - Test: `python -c "from interview import Question; q = Question(id='q1', header='Test', text='Question?', options=[{'label': 'A', 'description': 'Desc'}])"`
    - Assertion: Question instantiates with new fields, old format still works

- [x] **Task 4**: Add image validation and [Image X] rendering logic
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 2
  - Create `images.py` module:
    - `validate_image(path: str) -> bool` - Check file exists and is valid image
    - `get_image_placeholder(index: int) -> str` - Returns `[Image {index}]`
    - `load_image_for_html(path: str) -> str` - Returns base64 data URI
  - **Definition of Done**:
    - Test: `python -c "from images import validate_image, get_image_placeholder; assert get_image_placeholder(1) == '[Image 1]'"`
    - Assertion: Functions return expected values

### P2: TUI Implementation (Parallel after P1)

- [x] **Task 5**: Refactor tui.py to use TabbedContent wizard
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 3, Task 4
  - Major changes to `tui.py`:
    - Replace ScrollableContainer with TabbedContent
    - Each question becomes a TabPane with `header` as tab label
    - Add "Submit" as final tab
    - Update CSS for chip-style tab headers
  - **Definition of Done**:
    - Test: `uv run python -c "from tui import InterviewApp; print('TUI imports OK')"`
    - Assertion: No import errors, TabbedContent used in compose()

- [x] **Task 6**: Create QuestionPane widget with numbered options
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 3
  - New widget in `tui.py`:
    - Displays question text
    - Shows `[Image X]` for each image
    - Renders numbered options: `1. Label\n   Description`
    - Automatic "Other" option at end with Input field
    - Arrow key navigation between options
    - Enter to select
  - **Definition of Done**:
    - Test: Create test that renders QuestionPane with 3 options
    - Assertion: All options visible, Other option present, navigation works

- [x] **Task 7**: Add navigation footer with key hints
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 5
  - Footer updates:
    - Show: `Enter to select · Tab/Arrow to navigate · Esc to cancel`
    - Update key bindings to match
    - Add Esc handler to cancel/exit
  - **Definition of Done**:
    - Test: Visual inspection of footer text
    - Assertion: Footer shows navigation hints, Esc exits app

- [x] **Task 8**: Implement multi-select mode
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 6
  - When `multi_select: true`:
    - Show checkboxes instead of radio buttons
    - Allow multiple selections
    - "Other" becomes additional input, not replacement
  - **Definition of Done**:
    - Test: `examples/claude_style.json` includes multi-select question
    - Assertion: Multiple options can be selected simultaneously

### P3: HTML Mode Updates (Parallel with P2)

- [x] **Task 9**: Update HTML template for wizard style
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 3, Task 4
  - Changes to `templates/interview.html`:
    - Tab bar with chip-style headers
    - One question per pane
    - JavaScript for tab navigation
    - Match TUI keyboard shortcuts (Tab, Enter, Esc)
  - **Definition of Done**:
    - Test: Open HTML in browser, navigate with keyboard
    - Assertion: Tab switches panes, Enter selects, Esc cancels

- [x] **Task 10**: Add actual image display in HTML mode
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 4, Task 9
  - HTML updates:
    - Embed images as base64 data URIs
    - Responsive sizing (max-width: 100%)
    - Fallback to `[Image X]` if load fails
  - **Definition of Done**:
    - Test: HTML displays `examples/test_image.png`
    - Assertion: Image visible in browser, correct dimensions

### P4: Integration & Documentation (Sequential after P2, P3)

- [x] **Task 11**: Update response format for new features
  - Agent: general-purpose
  - Parallel: 3
  - Dependencies: Task 6, Task 8
  - Response changes:
    - Track which option index selected
    - Include "other_text" if Other used
    - Include selected image references if relevant
    - Multi-select returns list of values
  - **Definition of Done**:
    - Test: Run full interview, check response JSON
    - Assertion: Response includes all new fields

- [x] **Task 12**: Update SKILL.md documentation
  - Agent: general-purpose
  - Parallel: 3
  - Dependencies: Task 11
  - Documentation updates:
    - New question format with examples
    - Image support explanation
    - Keyboard shortcuts table
    - Migration guide from v1 format
  - **Definition of Done**:
    - Test: Read SKILL.md, all new features documented
    - Assertion: Examples for header, options, images, multi_select

- [x] **Task 13**: Create comprehensive example demonstrating all features
  - Agent: general-purpose
  - Parallel: 3
  - Dependencies: Task 11
  - Create `examples/full_demo.json`:
    - 4 questions showing all question types
    - At least one with images
    - At least one multi-select
    - Headers following 12-char limit
  - **Definition of Done**:
    - Test: `./run.sh --mode tui --file examples/full_demo.json`
    - Assertion: Demo runs successfully, all features visible

### P5: Final Validation (Sequential after P4)

- [x] **Task 14**: End-to-end testing
  - Agent: general-purpose
  - Parallel: 4
  - Dependencies: all previous tasks
  - Tests to run:
    - TUI mode with full_demo.json
    - HTML mode with full_demo.json
    - Backward compatibility with old question format
    - Image placeholder rendering
    - Response collection accuracy
  - **Definition of Done**:
    - Test: `./sanity.sh` (update to include new tests)
    - Assertion: All tests pass, no regressions

## Completion Criteria

- [x] All sanity scripts pass
- [x] All tasks marked [x]
- [x] TUI shows tabbed wizard with chip headers
- [x] Options display as numbered list with descriptions
- [x] "Other" option appears automatically on all questions
- [x] Images show as `[Image X]` in TUI, actual images in HTML
- [x] Keyboard navigation matches Claude Code (Tab/Arrow/Enter/Esc)
- [x] Old question format still works (backward compatible)
- [x] SKILL.md fully documents new features

## Visual Reference

Target TUI appearance:
```
┌─────────────────────────────────────────────────────────┐
│ Clarifying Questions                                    │
├─────────────────────────────────────────────────────────┤
│ ← □ TTS Model  □ Voice Anchors  □ Research  ✓ Submit → │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ Which TTS model should we use for narration?            │
│                                                         │
│   [Image 1]                                             │
│                                                         │
│  1. horus_final_prod (Recommended)                      │
│     Latest production checkpoint from XTTS training     │
│  2. horus_qwen3_06b_final                               │
│     Qwen3 0.6B model checkpoint                         │
│  3. Need new training                                   │
│     Current models insufficient                         │
│ › 4. Other: [________________]                          │
│                                                         │
├─────────────────────────────────────────────────────────┤
│ Enter to select · Tab/Arrow to navigate · Esc cancel    │
└─────────────────────────────────────────────────────────┘
```

## Notes

- Tab headers limited to 12 characters to match Claude Code's AskUserQuestion
- Images stored as paths, loaded on demand (not embedded in JSON)
- HTML mode uses base64 data URIs to avoid server complexity
- Backward compatibility critical - existing interview JSON must still work
