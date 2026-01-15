# Clarify Skill

Interactive form system for gathering structured user input. Supports text, choice, and multi-choice questions with visual assets, docs links, and artifact references.

## When to Use

- Gathering multi-part user requirements
- Clarifying ambiguous instructions
- Collecting structured feedback
- Any situation where text prompts aren't sufficient

## Quick Start

```python
from clarify import ask_questions, ClarifyQuestion, ClarifyOption

# Simple text question
responses = ask_questions([
    {"prompt": "What is the project name?"}
])

# Multiple choice with options
responses = ask_questions([
    ClarifyQuestion(
        id="auth_method",
        prompt="Which authentication method should we use?",
        kind="single-choice",
        options=[
            ClarifyOption(id="jwt", label="JWT tokens", description="Stateless, scalable"),
            ClarifyOption(id="session", label="Session cookies", description="Traditional, simpler"),
            ClarifyOption(id="oauth", label="OAuth 2.0", description="Third-party providers"),
        ]
    )
])
```

## API

### `ask_questions(questions, timeout_sec=300, context="")`

Launch clarifying UI and wait for user responses.

**Parameters:**
- `questions`: List of question dicts or `ClarifyQuestion` objects
- `timeout_sec`: How long to wait for responses (default: 5 minutes)
- `context`: Optional context string shown in UI header

**Returns:** List of response dicts with user's answers

### Question Types

| Kind | Description | Response |
|------|-------------|----------|
| `text` | Single-line text input | `{"value": "user input"}` |
| `textarea` | Multi-line text input | `{"value": "user input"}` |
| `single-choice` | Radio button selection | `{"selectedOptions": ["option_id"]}` |
| `multi-choice` | Checkbox selection | `{"selectedOptions": ["opt1", "opt2"]}` |

### ClarifyQuestion Fields

```python
@dataclass
class ClarifyQuestion:
    id: str                    # Unique identifier
    prompt: str                # Question text
    kind: str = "text"         # text, textarea, single-choice, multi-choice
    options: List[ClarifyOption] = []  # For choice questions
    docs_link: Optional[str] = None    # Link to relevant docs
    artifact_paths: List[str] = []     # Paths to related files
    visual_assets: List[str] = []      # Images to display
    required: bool = True              # Must answer?
    allow_multiple: bool = False       # For multi-choice
```

### ClarifyOption Fields

```python
@dataclass
class ClarifyOption:
    id: str                            # Option identifier
    label: str                         # Display text
    description: Optional[str] = None  # Help text
```

## CLI Usage

```bash
# Single question (TUI mode)
clarify ask "What database should we use?"

# Multiple questions (opens browser UI)
clarify ask --json '[{"prompt": "Project name?"}, {"prompt": "Description?", "kind": "textarea"}]'
```

## Response Format

```json
{
  "step": "context_name",
  "attempt": 1,
  "responses": [
    {
      "id": "q1",
      "kind": "text",
      "value": "user's answer"
    },
    {
      "id": "auth_method",
      "kind": "single-choice",
      "selectedOptions": ["jwt"],
      "note": "optional user note"
    }
  ],
  "submittedAt": "2026-01-11T15:30:00Z"
}
```

## Building the UI

```bash
cd /path/to/agent-skills/clarify/ui
npm install
npm run build
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `CLARIFY_TIMEOUT` | Timeout in seconds | 300 |
| `CLARIFY_BROWSER` | Browser to open | system default |

## Integration Example

```python
from clarify import ask_questions

def gather_requirements():
    """Interactively gather project requirements."""
    responses = ask_questions([
        {
            "id": "project_type",
            "prompt": "What type of project is this?",
            "kind": "single-choice",
            "options": [
                {"id": "web", "label": "Web Application"},
                {"id": "api", "label": "REST API"},
                {"id": "cli", "label": "CLI Tool"},
            ]
        },
        {
            "id": "description",
            "prompt": "Describe the main functionality:",
            "kind": "textarea"
        },
        {
            "id": "features",
            "prompt": "Select required features:",
            "kind": "multi-choice",
            "options": [
                {"id": "auth", "label": "Authentication"},
                {"id": "db", "label": "Database"},
                {"id": "cache", "label": "Caching"},
                {"id": "queue", "label": "Job Queue"},
            ]
        }
    ], context="New Project Setup")

    return responses
```
