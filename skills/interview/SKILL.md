---
name: interview
description: >
  Structured human-agent Q&A via HTML or TUI forms. Use when you need clear
  yes/no/refine decisions from the user on multiple items. Agent provides
  recommendations, human validates or overrides.
allowed-tools: Bash, Read
triggers:
  - interview user
  - get user feedback
  - review items with user
  - human review
  - ask user to review
  - structured Q&A
metadata:
  short-description: Structured Q&A forms (HTML/TUI) with agent recommendations
---

# Interview Skill

Structured human-agent Q&A via forms. Agent leads with recommendations, human validates.

## Quick Start

```bash
# TUI mode (terminal)
.pi/skills/interview/run.sh --mode tui --file questions.json

# HTML mode (browser)
.pi/skills/interview/run.sh --mode html --file questions.json

# Auto-detect (HTML if browser available, else TUI)
.pi/skills/interview/run.sh --file questions.json
```

## Question Format

```json
{
  "title": "Review Distilled Q&As",
  "context": "Reviewing extracted knowledge from STITCH paper",
  "questions": [
    {
      "id": "q1",
      "text": "Q: What is STITCH?\nA: Intent-aware memory indexing...",
      "type": "yes_no_refine",
      "recommendation": "keep",
      "reason": "Directly relevant to plan_state design"
    },
    {
      "id": "q2",
      "text": "Q: What dataset sizes were used?\nA: 100 small, 200 large...",
      "type": "yes_no_refine",
      "recommendation": "drop",
      "reason": "Implementation detail, not generalizable"
    }
  ]
}
```

## Question Types

| Type | Options | Use Case |
|------|---------|----------|
| `yes_no` | Yes, No | Simple binary decision |
| `yes_no_refine` | Yes, No, Refine | Decision with edit option |
| `select` | Custom options | Choose one from list |
| `multi` | Custom options | Choose multiple |
| `text` | Free text | Open-ended input |
| `confirm` | Confirm, Cancel | Final confirmation |

## Response Format

```json
{
  "session_id": "abc123",
  "completed": true,
  "duration_seconds": 45,
  "responses": {
    "q1": {"decision": "accept", "value": "keep"},
    "q2": {"decision": "override", "value": "keep", "note": "Actually useful for benchmarking"}
  }
}
```

## Modes

### HTML Mode
- Opens browser with Tailwind-styled form
- Auto-saves to localStorage
- Keyboard navigation (Tab, Enter, Escape)
- Returns when form submitted or timeout

### TUI Mode
- Textual-based terminal UI
- Rich formatting with colors
- Arrow keys + Enter navigation
- Works over SSH/headless

## Integration Example

```python
from interview import Interview

# Create questions with agent recommendations
questions = [
    {
        "id": "qa_1",
        "text": "Q: What is STITCH?\nA: Intent-aware memory...",
        "type": "yes_no_refine",
        "recommendation": "keep",
        "reason": "Relevant to our memory architecture"
    }
]

# Run interview
interview = Interview(title="Review Paper Q&As")
responses = interview.run(questions, mode="auto")

# Process responses
for qid, response in responses["responses"].items():
    if response["value"] == "keep":
        store_qa(qid)
```

## Session Recovery

Sessions auto-save to `.pi/skills/interview/sessions/`. If interrupted:

```bash
# Resume last session
.pi/skills/interview/run.sh --resume

# Resume specific session
.pi/skills/interview/run.sh --resume abc123
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `INTERVIEW_MODE` | auto | Force html/tui mode |
| `INTERVIEW_TIMEOUT` | 600 | Seconds before auto-save and exit |
| `INTERVIEW_PORT` | 8765 | HTTP server port for HTML mode |
