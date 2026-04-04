<p>
  <img src="banner.png" alt="/interview" width="800">
</p>

# Interview Skill

A composable skill for agent ecosystems that opens an ugly form to gather human responses. On Linux, uses a Textual TUI that looks like a mainframe. Falls back to an HTML form that looks like a government website from 2009.

```
┌─────────────────────────────────────────────────────────┐
│ Clarifying Questions                                    │
├─────────────────────────────────────────────────────────┤
│ ← □ TTS Model  □ Voice Anchors  □ Research  ✓ Submit → │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ Which TTS model should we use for narration?            │
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

## Installation

```bash
cd .pi/skills/interview
uv sync
```

No restart needed. No npm. No native windows.

**Requirements:**
- Python 3.10+
- A terminal (mandatory)
- A browser (optional, for the slightly-less-ugly HTML mode)

## Features

- **Question Types**: Single-select, multi-select, text input, image compare, bbox annotation
- **Code Blocks**: Embed code and diffs directly in questions (v2.3)
- **"Other" Option**: Every question gets one automatically. Can include images.
- **Pre-selection**: Agent recommendations shown with `recommendation` + `reason`
- **Conviction & Weight**: How strongly do you feel? How much does it matter? (v2.3)
- **Image Collaboration**: Side-by-side image comparison, paste, drag-drop, file paths
- **Keyboard Navigation**: Full keyboard support. Mouse optional. Mouse discouraged.
- **Auto-save**: Sessions saved to disk. Resume with `--resume latest`
- **Session Timeout**: Configurable. Default 10 minutes. You're answering questions, not writing a novel.
- **Dual Mode**: TUI (Textual) and HTML (local HTTP server). Same JSON out either way.
- **Plugin Registry**: Custom question types without touching core code
- **Composable**: 20+ skills call this programmatically. It's `stdin` for human-agent collaboration.

## How It Works

```
Agent ──── questions.json ───▶ /interview ──── responses ───▶ Agent
                               (TUI or HTML)
                               30-90 seconds of ugly UI
                               then it's gone
```

The agent builds questions. The human answers them. The agent gets JSON back. Nobody looks at the form longer than they have to.

## Usage

```bash
# Auto-detect mode (TUI if SSH/tmux, HTML if browser available)
./run.sh --file questions.json

# Force the ugly TUI
./run.sh --mode tui --file questions.json

# Force the slightly-less-ugly HTML
./run.sh --mode html --file questions.json

# Resume interrupted session
./run.sh --resume latest

# JSON output for piping
./run.sh --file questions.json --json
```

## Question Schema

```json
{
  "title": "Code Review",
  "context": "Reviewing auth middleware replacement",
  "questions": [
    {
      "id": "approve_change",
      "header": "Review",
      "text": "Should we apply this refactor?",
      "code_block": "- old_auth(token)\n+ new_auth(token, compliance=True)",
      "code_lang": "diff",
      "options": [
        {"label": "Approve", "description": "Apply the change"},
        {"label": "Reject", "description": "Keep current code"}
      ],
      "recommendation": "Approve",
      "reason": "Passes all 47 compliance checks"
    }
  ]
}
```

### Question Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Unique identifier |
| `text` | string | Yes | Question text |
| `header` | string | No | Tab label, max 12 chars |
| `options` | array | No | `[{label, description}]` or `["string"]` |
| `multi_select` | bool | No | Allow multiple selections |
| `code_block` | string | No | Code/diff to display (v2.3) |
| `code_lang` | string | No | Language hint: `"python"`, `"diff"` (v2.3) |
| `images` | array | No | Image paths to display |
| `type` | string | No | `select`, `multi`, `text`, `image_compare`, `bbox_annotation` |
| `recommendation` | string | No | Agent's suggested answer |
| `reason` | string | No | Why the agent recommends it |
| `allow_custom_image` | bool | No | Let user paste/upload an image |
| `comparison_images` | array | No | Images for `image_compare` type |

Options support both formats:

```json
// v2 (recommended) — with descriptions
"options": [
  {"label": "Option A", "description": "Why this is good"},
  {"label": "Option B", "description": "Why this is also good"}
]

// v1 (still works) — plain strings
"options": ["Option A", "Option B"]
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Enter` | Select current option (auto-advances for single-select) |
| `Space` | Toggle option (multi-select mode) |
| `Tab` / `Shift+Tab` | Navigate between question tabs |
| `Arrow Up/Down` | Move between options |
| `1`-`5` | Quick select option by number |
| `Esc` | Cancel interview |

No mouse required. No mouse recommended. This is a terminal tool.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `INTERVIEW_MODE` | `auto` | Force `html` or `tui` mode |
| `INTERVIEW_TIMEOUT` | `600` | Seconds before auto-save and exit |
| `INTERVIEW_PORT` | `8765` | HTTP server port for HTML mode |

No settings.json. No theme picker. No custom CSS paths. Environment variables, like nature intended.

## Response Format

```json
{
  "session_id": "abc123",
  "completed": true,
  "duration_seconds": 42,
  "responses": {
    "approve_change": {
      "decision": "override",
      "value": "Reject",
      "conviction": "strong",
      "weight": "critical"
    },
    "features": {
      "decision": "accept",
      "value": ["Caching", "Logging"]
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

| Field | Type | Description |
|-------|------|-------------|
| `decision` | string | `"accept"`, `"override"`, or `"skip"` |
| `value` | string/array | Selected option(s) |
| `conviction` | string | `"strong"`, `"neutral"`, `"slight"` (v2.3, optional) |
| `weight` | string | `"critical"`, `"important"`, `"minor"` (v2.3, optional) |
| `other_text` | string | Present when "Other" was selected |
| `custom_image` | object | Present when user pasted/uploaded an image |

## Composing with /interview

```python
from interview import Interview, Question, Option

questions = [
    Question(
        id="model",
        header="Model",
        text="Which model?",
        code_block="current: gpt-4\nproposed: claude-opus-4",
        code_lang="yaml",
        options=[
            Option(label="Keep GPT-4", description="Known quantity"),
            Option(label="Switch to Claude", description="Better at code"),
        ],
    ),
]

result = Interview(title="Config").run(questions, mode="auto")
model = result["responses"]["model"]["value"]
conviction = result["responses"]["model"].get("conviction")  # "strong", "slight", or None
```

Skills that compose `/interview`: `/create-walkthrough`, `/create-persona`, `/formalize-request`, `/review-design`, `/qra-review`, `/create-paper`, `/train-voice`, `/mockup-lab`, `/create-story`, and others.

## Session Recovery

Sessions auto-save to `sessions/`. If interrupted:

```bash
# Resume last session
./run.sh --resume latest

# Resume specific session
./run.sh --resume abc123
```

No localStorage. No browser snapshots. No HTML revival. Just a JSON file on disk.

## File Structure

```
.pi/skills/interview/
├── SKILL.md              # Agent instructions (the real spec)
├── README.md             # This file
├── banner.png            # CRT banner
├── run.sh                # Entry point
├── interview.py          # Core: Question, Response, Session, Interview
├── server.py             # HTML mode (local HTTP server, no framework)
├── tui.py                # TUI mode (Textual app)
├── tui_panes.py          # TUI tab pane widgets
├── tui_widgets.py        # TUI option/image widgets
├── images.py             # Image validation, terminal graphics detection
├── registry.py           # Plugin registry for custom question types
├── templates/form.html   # The HTML template (it's one file)
├── examples/             # Example question files
├── sessions/             # Auto-saved sessions (gitignored)
└── sanity/               # Dependency verification
```

## Theming

No.

## Version History

- **v2.3** — Code blocks in questions, conviction/weight on responses.
- **v2.2** — Bounding box annotation questions.
- **v2.1** — Image collaboration: compare, paste, drag-drop, file path detection.
- **v2.0** — Wizard-style tabs, numbered options with descriptions, HTML + TUI dual mode.
- **v1.0** — Basic yes/no/refine questions.

## Limits

- Max 5 image attachments per question
- Session timeout: 10 minutes default (configurable via `INTERVIEW_TIMEOUT`)
