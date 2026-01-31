---
name: interview
description: >
  Structured human-agent Q&A via HTML or TUI forms. Wizard-style interface with
  tabbed navigation, numbered options with descriptions, automatic "Other" option,
  and image support. Mirrors Claude Code's AskUserQuestion UX.
allowed-tools: Bash, Read
triggers:
  - interview user
  - get user feedback
  - review items with user
  - human review
  - ask user to review
  - structured Q&A
  - clarifying questions
metadata:
  short-description: Wizard-style Q&A forms with tabbed navigation and image support
  version: "2.0"
---

# Interview Skill v2

Structured human-agent Q&A with wizard-style interface. Mirrors Claude Code's AskUserQuestion UX with tabbed navigation, numbered options with descriptions, automatic "Other" option, and image support.

## Quick Start

```bash
# TUI mode (terminal)
.pi/skills/interview/run.sh --mode tui --file questions.json

# HTML mode (browser)
.pi/skills/interview/run.sh --mode html --file questions.json

# Auto-detect (HTML if browser available, else TUI)
.pi/skills/interview/run.sh --file questions.json
```

## Question Format (v2)

```json
{
  "title": "Clarifying Questions",
  "context": "The agent needs your input before proceeding.",
  "questions": [
    {
      "id": "tts_model",
      "header": "TTS Model",
      "text": "Which TTS model should we use for narration?",
      "options": [
        {
          "label": "horus_final_prod (Recommended)",
          "description": "Latest production checkpoint from XTTS training"
        },
        {
          "label": "horus_qwen3_06b_final",
          "description": "Qwen3 0.6B model checkpoint"
        },
        {
          "label": "Need new training",
          "description": "Current models are insufficient"
        }
      ],
      "multi_select": false
    },
    {
      "id": "voice_anchors",
      "header": "Voice",
      "text": "Which voice anchors should we use?",
      "images": ["examples/voice_samples.png"],
      "options": [
        {"label": "Audiobook anchors", "description": "Consistent formal tone"},
        {"label": "Podcast anchors", "description": "Conversational, dynamic"}
      ],
      "multi_select": false
    },
    {
      "id": "research_areas",
      "header": "Research",
      "text": "Which research areas should Dogpile prioritize?",
      "options": [
        {"label": "Voice cloning", "description": "XTTS, Coqui, RVC methods"},
        {"label": "Audio preprocessing", "description": "Noise removal, enhancement"},
        {"label": "Dataset curation", "description": "Finding training data"},
        {"label": "Evaluation metrics", "description": "MOS scores, similarity"}
      ],
      "multi_select": true
    }
  ]
}
```

## Question Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Unique identifier |
| `text` | string | Yes | Full question text |
| `header` | string | No | Short tab label (max 12 chars) |
| `options` | array | No | List of options with label/description |
| `images` | array | No | List of image paths to display |
| `multi_select` | bool | No | Allow multiple selections (default: false) |
| `type` | string | No | Question type: "select", "multi", "text", "image_compare" |
| `recommendation` | string | No | Agent's recommended answer |
| `reason` | string | No | Why agent recommends this |
| `allow_custom_image` | bool | No | Allow user to paste/upload custom image |
| `comparison_images` | array | No | Images for image_compare type |

### Options Format

Options can be specified as:

```json
// New format (v2) - with descriptions
"options": [
  {"label": "Option A", "description": "Detailed explanation"},
  {"label": "Option B", "description": "Another explanation"}
]

// Legacy format (v1) - string only
"options": ["Option A", "Option B"]
```

### Image Support

Images display differently by mode:

| Mode | Display |
|------|---------|
| TUI | `[Image 1] (800x600)` placeholder with dimensions |
| HTML | Actual image embedded as base64 (max 600px wide) |

Image paths can be absolute or relative to the questions file.

## Image Collaboration (v2.1)

The interview skill supports rich image collaboration between human and agent. Users can provide their own images via paste, drag-drop, or file paths.

### Image Comparison Questions

For "which image do you prefer?" scenarios:

```json
{
  "id": "ui_design",
  "header": "UI Design",
  "text": "Which UI design do you prefer for the dashboard?",
  "type": "image_compare",
  "comparison_images": [
    {
      "path": "designs/option_a.png",
      "label": "Modern Dark",
      "description": "Dark theme with gradient accents"
    },
    {
      "path": "designs/option_b.png",
      "label": "Clean Light"
    }
  ],
  "allow_custom_image": true
}
```

Users see a grid of images and can:
1. Click an image to select it
2. Paste their own image (Ctrl+V)
3. Drag-drop an image file
4. Provide a reason for their choice

### Custom Image Input

Every question with options now includes an enhanced "Other" option that accepts images:

| Input Method | TUI | HTML |
|--------------|-----|------|
| Paste (Ctrl+V) | Detects file paths | Full clipboard image support |
| Drag-drop | N/A | Supported |
| File path | Type path, shows preview | Via paste zone click |
| Click to browse | N/A | Opens file dialog |

#### TUI File Path Detection

In TUI mode, if the user types something that looks like an image path:
- `/path/to/image.png`
- `~/screenshots/design.jpg`
- `./local/image.gif`

The skill validates the image and shows: `[Your Image] (800x600) - filename.png`

#### HTML Clipboard Paste

In HTML mode, users can:
1. Copy an image to clipboard (screenshot, from browser, etc.)
2. Press Ctrl+V anywhere on the question
3. Image appears in the "Other" option paste zone
4. User can add text explanation alongside

### Response Format with Images

When user provides a custom image:

```json
{
  "ui_design": {
    "decision": "override",
    "value": "custom_image",
    "custom_image": {
      "source": "clipboard",
      "data_uri": "data:image/png;base64,...",
      "reason": "I prefer this rounded corner style"
    }
  }
}
```

Or via file path (TUI):

```json
{
  "ui_design": {
    "decision": "override",
    "value": "/home/user/my_design.png",
    "custom_image": {
      "source": "file_path",
      "path": "/home/user/my_design.png",
      "dimensions": [1200, 800],
      "data_uri": "data:image/png;base64,..."
    }
  }
}
```

### Terminal Graphics Protocol Support

The TUI can display actual images (not just placeholders) if your terminal supports graphics protocols:

| Protocol | Terminals |
|----------|-----------|
| Kitty | Kitty, WezTerm, Ghostty |
| iTerm2 | iTerm2 (macOS) |
| Sixel | foot, mlterm, some xterm configs |

Optional packages for enhanced display:
- `textual-image` - Full image support in Textual TUI
- `rich-pixels` - Unicode-based image rendering

```bash
# Install optional image support
pip install textual-image rich-pixels
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Enter` | Select current option (auto-advances for single-select) |
| `Space` | Toggle option (multi-select mode) |
| `Tab` / `Shift+Tab` | Navigate between question tabs |
| `Arrow Up/Down` | Move between options |
| `1-5` | Quick select option by number |
| `Esc` | Cancel interview |

## Response Format

```json
{
  "session_id": "abc123",
  "completed": true,
  "duration_seconds": 45,
  "responses": {
    "tts_model": {
      "decision": "override",
      "value": "horus_final_prod (Recommended)"
    },
    "research_areas": {
      "decision": "override",
      "value": ["Voice cloning", "Dataset curation"]
    },
    "custom_answer": {
      "decision": "override",
      "value": "My custom response",
      "other_text": "My custom response"
    }
  }
}
```

### Response Fields

| Field | Description |
|-------|-------------|
| `decision` | "accept" (used recommendation), "override" (chose different), "skip" |
| `value` | Selected option label(s). Array for multi_select. |
| `other_text` | Present when "Other" was selected with custom text |
| `note` | Legacy refinement note (v1 compat) |

## Visual Reference

### TUI Mode

```
┌─────────────────────────────────────────────────────────┐
│ Clarifying Questions                                    │
├─────────────────────────────────────────────────────────┤
│ ← □ TTS Model  □ Voice Anchors  □ Research  ✓ Submit → │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ Which TTS model should we use for narration?            │
│                                                         │
│   [Image 1] (800x600)                                   │
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

### HTML Mode

- Dark theme with chip-style tab navigation
- Actual images displayed (base64 embedded)
- Same keyboard shortcuts as TUI
- Auto-advances on single-select

## Integration Example

```python
from interview import Interview, Question, Option

# Create questions with v2 format
questions = [
    Question(
        id="model_choice",
        header="Model",
        text="Which model should we use?",
        options=[
            Option(label="GPT-4", description="Most capable, higher cost"),
            Option(label="Claude 3", description="Good balance of capability/cost"),
            Option(label="Local LLM", description="Privacy-focused, lower cost"),
        ],
        multi_select=False,
    ),
    Question(
        id="features",
        header="Features",
        text="Which features should we enable?",
        options=[
            Option(label="Caching", description="Reduce API calls"),
            Option(label="Streaming", description="Real-time output"),
            Option(label="Logging", description="Debug capability"),
        ],
        multi_select=True,
    ),
]

# Run interview
interview = Interview(title="Configuration Options")
result = interview.run(questions, mode="auto")

# Process responses
model = result["responses"].get("model_choice", {}).get("value")
features = result["responses"].get("features", {}).get("value", [])
```

## Migration from v1

### Question Format

```python
# v1 format (still works)
{
    "id": "q1",
    "text": "Keep this Q&A?",
    "type": "yes_no_refine",
    "recommendation": "keep",
    "options": ["Option A", "Option B"]  # String options
}

# v2 format (recommended)
{
    "id": "q1",
    "header": "Q&A Review",  # NEW: Tab label
    "text": "Keep this Q&A?",
    "options": [  # NEW: Dict options with descriptions
        {"label": "Option A", "description": "Explanation A"},
        {"label": "Option B", "description": "Explanation B"}
    ],
    "images": ["path/to/image.png"],  # NEW: Image support
    "multi_select": false  # NEW: Explicit multi-select
}
```

### Response Format

Both v1 and v2 responses are compatible. The `other_text` field is new in v2 for custom "Other" responses.

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

## Files

```
.pi/skills/interview/
├── SKILL.md           # This file
├── run.sh             # Entry point
├── interview.py       # Main module (Question, Session, Interview classes)
├── tui.py             # Textual TUI implementation
├── server.py          # HTTP server for HTML mode
├── images.py          # Image validation, graphics detection, collaboration
├── templates/
│   └── form.html      # HTML template with clipboard paste support
├── examples/
│   ├── claude_style.json           # v2 format example
│   ├── full_demo.json              # All v2 features demo
│   ├── image_collaboration_demo.json  # Image comparison demo
│   └── test_image.png              # Test image
├── sanity/            # Dependency verification scripts
└── sessions/          # Auto-saved sessions
```
