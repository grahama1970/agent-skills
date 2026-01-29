# Pi Skills Directory

Skills are modular capabilities that extend the Pi agent with specialized knowledge and tools. Each skill defines **when** it should be activated (triggers) and **how** to execute its task (commands, APIs, or instructions).

## Quick Start

```bash
# List all available skills
ls .pi/skills/*/SKILL.md

# Use a skill via natural language
> "check memory for authentication errors"    # Activates memory skill
> "assess this project"                        # Activates assess skill
> "search arxiv for transformer papers"        # Activates arxiv skill

# Direct invocation
.pi/skills/memory/run.sh recall --q "error description"
.pi/skills/brave-search/brave_search.py web "site:openai.com"
```

## How Skills Work

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER REQUEST                              │
│                "check memory for auth errors"                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      TRIGGER MATCHING                            │
│  Pi reads SKILL.md frontmatter, matches "check memory" trigger   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      SKILL ACTIVATION                            │
│  Pi loads skill instructions from SKILL.md body                  │
│  Restricts tools to `allowed-tools` list                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      SKILL EXECUTION                             │
│  Pi follows skill instructions, runs commands/scripts            │
└─────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
.pi/skills/
├── README.md              # This file
├── TRIGGERS.md            # Index of all skill triggers (auto-generated reference)
├── common.sh              # Shared bash utilities (env loading)
├── dotenv_helper.py       # Python .env file loader
├── json_utils.py          # JSON parsing utilities
│
├── memory/                # Skill directory
│   ├── SKILL.md           # Skill definition (required)
│   ├── run.sh             # Entry point script
│   └── ...                # Additional skill files
│
├── assess/
│   └── SKILL.md
│
├── brave-search/
│   ├── SKILL.md
│   └── brave_search.py
│
└── ... (other skills)
```

## SKILL.md Format

Each skill has a `SKILL.md` file with **YAML frontmatter** and a **markdown body**.

### Frontmatter (Required)

```yaml
---
name: my-skill
description: >
  Brief description of what this skill does. Include key trigger phrases
  so Pi can match user requests. Use when user says "do X" or "perform Y".
allowed-tools: Bash, Read, Glob, Grep
triggers:
  - do X
  - perform Y
  - my-skill action
  - another trigger phrase
metadata:
  short-description: One-line summary for listings
---
```

| Field           | Required | Description                                                             |
| --------------- | -------- | ----------------------------------------------------------------------- |
| `name`          | Yes      | Unique skill identifier (matches directory name)                        |
| `description`   | Yes      | What the skill does + when to use it. Include trigger phrases here too. |
| `allowed-tools` | No       | Comma-separated list of tools Pi can use when this skill is active      |
| `triggers`      | Yes      | Phrases that activate this skill (case-insensitive matching)            |
| `metadata`      | No       | Additional fields like `short-description`                              |

### Body (After Frontmatter)

The markdown body contains:

- Detailed instructions for the agent
- Command usage and examples
- API documentation
- Workflow steps
- Configuration options

Pi reads this body when the skill is activated and follows the instructions.

## Available Skills

### Core Skills

| Skill      | Description                                   | Key Triggers                                |
| ---------- | --------------------------------------------- | ------------------------------------------- |
| **memory** | MEMORY FIRST - Query before scanning codebase | "check memory", "recall", "learn from this" |
| **assess** | Step back and reassess project state          | "assess", "step back", "sanity check"       |

### Search & Research

| Skill            | Description                             | Key Triggers                              |
| ---------------- | --------------------------------------- | ----------------------------------------- |
| **brave-search** | Free web/local search via Brave API     | "brave search", "local search", "near me" |
| **perplexity**   | Deep research with LLM synthesis (paid) | "research this", "what's the latest"      |
| **arxiv**        | Academic paper search                   | "find papers on", "search arxiv"          |
| **context7**     | Library documentation lookup            | "library docs", "API reference"           |

### Content Processing

| Skill                   | Description                     | Key Triggers                           |
| ----------------------- | ------------------------------- | -------------------------------------- |
| **fetcher**             | Fetch URLs, PDFs, web content   | "fetch this URL", "download page"      |
| **pdf-screenshot**      | Render PDF pages/regions to PNG | "screenshot pdf", "verify pdf element" |
| **youtube-transcripts** | Extract video transcripts       | "get transcript", "youtube transcript" |
| **tts-horus**           | Horus TTS dataset + training    | "horus tts", "voice coloring"          |
| **tts-train**           | TTS dataset + training pipeline | "tts train", "voice cloning"           |

### Knowledge Management

| Skill                 | Description                          | Key Triggers                           |
| --------------------- | ------------------------------------ | -------------------------------------- |
| **episodic-archiver** | Archive conversations to memory      | "archive conversation", "save episode" |
| **edge-verifier**     | Verify knowledge graph relationships | "verify edges", "check edge quality"   |

### Code & Development

| Skill           | Description                  | Key Triggers                           |
| --------------- | ---------------------------- | -------------------------------------- |
| **code-review** | Get code reviews and patches | "code review", "review this code"      |
| **treesitter**  | Parse code structure         | "parse this code", "extract functions" |

### Infrastructure

| Skill          | Description                         | Key Triggers                            |
| -------------- | ----------------------------------- | --------------------------------------- |
| **ops-runpod** | Manage GPU instances                | "spin up GPU", "create RunPod"          |
| **ops-arango** | Manage ArangoDB operations          | "backup arangodb", "restore snapshot"   |
| **ops-docker** | Safe Docker cleanup & management    | "prune containers", "redeploy stack"    |
| **ops-llm**    | Local LLM health & cache management | "clean model cache", "check llm health" |
| **surf**       | Browser automation                  | "open browser", "click on", "fill form" |

### Agent Management

| Skill           | Description                 | Key Triggers                     |
| --------------- | --------------------------- | -------------------------------- |
| **agent-inbox** | Inter-agent messaging       | "check inbox", "send message to" |
| **skills-sync** | Sync skills across projects | "sync skills", "push skills"     |

## Creating a New Skill

### 1. Create Directory

```bash
mkdir -p .pi/skills/my-skill
```

### 2. Create SKILL.md

```markdown
---
name: my-skill
description: >
  Does X and Y. Use when user says "do X", "perform Y", or asks about Z.
allowed-tools: Bash, Read
triggers:
  - do X
  - perform Y
  - my-skill
metadata:
  short-description: Does X and Y
---

# My Skill

Brief overview of what this skill does.

## Prerequisites

- List any required environment variables
- List any required dependencies

## Usage

\`\`\`bash

# Example command

.pi/skills/my-skill/run.sh action --arg value
\`\`\`

## Commands

| Command  | Description    |
| -------- | -------------- |
| `action` | Does something |

## Examples

\`\`\`bash

# Example 1

.pi/skills/my-skill/run.sh action --arg "example"
\`\`\`
```

### 3. Create Entry Point (Optional)

If your skill needs executable scripts:

```bash
#!/usr/bin/env bash
# .pi/skills/my-skill/run.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../common.sh"  # Load env vars

# Your skill logic here
```

### 4. Update TRIGGERS.md (Optional)

Add your skill's triggers to `TRIGGERS.md` for reference:

```markdown
## my-skill

**When user says:** "do X", "perform Y"

\`\`\`yaml
triggers:

- do X
- perform Y
  \`\`\`
```

## Skills Sync

Skills are synchronized from a canonical `agent-skills` repository using the `skills-sync` skill.

### Key Commands

```bash
# See current sync configuration
.pi/skills/skills-sync/skills-sync info

# Pull latest skills from upstream
.pi/skills/skills-sync/skills-sync pull

# Push local changes to upstream
.pi/skills/skills-sync/skills-sync push

# Push to upstream AND fan out to other projects
SKILLS_FANOUT_PROJECTS="$HOME/.codex/skills:$HOME/.pi/agent" \
  .pi/skills/skills-sync/skills-sync push --fanout
```

### Environment Variables

| Variable                 | Description                                        |
| ------------------------ | -------------------------------------------------- |
| `SKILLS_UPSTREAM_REPO`   | Path to canonical agent-skills repo                |
| `SKILLS_FANOUT_PROJECTS` | Colon-separated list of projects to receive skills |
| `SKILLS_SYNC_AUTOCOMMIT` | If `1`, auto-commit after push                     |

## Shared Utilities

### common.sh

Loads `.env` files from standard locations:

```bash
source .pi/skills/common.sh
# Now all env vars from ~/.env, ./.env, etc. are available
```

### dotenv_helper.py

Python equivalent for loading .env:

```python
from dotenv_helper import load_dotenv
load_dotenv()  # Loads from standard locations
```

### json_utils.py

JSON parsing utilities for skill scripts.

## Relationship to Pi Extensions

| Concept           | Location              | Purpose                                            |
| ----------------- | --------------------- | -------------------------------------------------- |
| **Skills**        | `.pi/skills/`         | Instruction-based capabilities loaded via SKILL.md |
| **Extensions**    | `~/.pi/agent/tools/`  | TypeScript tools with full API access              |
| **Agent Configs** | `~/.pi/agent/agents/` | Provider/model configurations for sub-agents       |

Skills are **instruction-driven** (markdown instructions Pi follows), while extensions are **code-driven** (TypeScript that Pi executes as tools).

## Memory First Pattern

The **Memory First** pattern is a core principle for all skills. Before scanning the codebase or performing expensive operations, skills should query memory for prior solutions.

### Why Memory First?

1. **Avoid Redundant Work** - Solutions may already exist in memory
2. **Leverage Prior Context** - Build on what's already been learned
3. **Faster Resolution** - Memory recall is faster than codebase scanning
4. **Knowledge Compounding** - Each solution makes the system smarter

### Using the Common Memory Client

All skills should use the standardized `common.memory_client` module for memory operations:

```python
from common.memory_client import MemoryClient, MemoryScope, recall, learn

# Quick recall (convenience function)
results = recall("authentication error handling", scope=MemoryScope.SECURITY)
if results.found:
    print(f"Found prior solution: {results.top['solution']}")

# Full client for more control
client = MemoryClient(scope=MemoryScope.OPERATIONAL)
results = client.recall("OAuth token refresh", k=5)

# Store new knowledge
client.learn(
    problem="OAuth token refresh failing silently",
    solution="Add explicit error handling in refreshToken(), log failures",
    tags=["oauth", "auth", "bug-fix"]
)
```

### Standard Scopes

Use `MemoryScope` enum for consistent scope naming:

| Scope          | Use For                      |
| -------------- | ---------------------------- |
| `OPERATIONAL`  | General operations (default) |
| `DOCUMENTS`    | Extracted documents          |
| `CODE`         | Code patterns, snippets      |
| `SOCIAL_INTEL` | Social media content         |
| `SECURITY`     | Security findings            |
| `RESEARCH`     | Research papers              |
| `HORUS_LORE`   | Persona knowledge            |

### Built-in Resilience

The common memory client includes:

- **Retry Logic** - Automatic retries with exponential backoff (3 attempts by default)
- **Rate Limiting** - Token bucket rate limiter (10 req/s default)
- **Structured Logging** - Consistent logging with PII redaction
- **Scope Validation** - Warns on non-standard scopes

### Integration Pattern

```python
# At the top of your skill
import sys
from pathlib import Path

SKILLS_DIR = Path(__file__).parent.parent
if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))

try:
    from common.memory_client import MemoryClient, MemoryScope
    HAS_MEMORY_CLIENT = True
except ImportError:
    HAS_MEMORY_CLIENT = False

# In your main function
def my_skill_function(query: str):
    # Memory First: Check for prior solutions
    if HAS_MEMORY_CLIENT:
        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        results = client.recall(query)
        if results.found:
            # Use prior knowledge to inform approach
            pass

    # ... rest of skill logic ...

    # Store new knowledge if something useful was learned
    if HAS_MEMORY_CLIENT and learned_something_new:
        client.learn(
            problem=problem_description,
            solution=solution_description,
            tags=["my-skill", "relevant-tag"]
        )
```

## Best Practices

1. **Memory First** - Always query memory before scanning codebase
2. **Descriptive Triggers** - Include common phrasings users might say
3. **Clear Instructions** - Write SKILL.md body as if explaining to a new team member
4. **Minimal Dependencies** - Skills should work with minimal setup
5. **Idempotent Commands** - Running twice should be safe
6. **Error Handling** - Provide clear error messages and recovery steps
7. **Examples** - Include working examples users can copy/paste
8. **Use Common Memory Client** - Don't implement your own memory integration

## Troubleshooting

### Skill Not Activating

1. Check trigger phrases in SKILL.md match user input
2. Verify SKILL.md frontmatter is valid YAML
3. Check Pi can read the skill directory

### Script Errors

1. Ensure scripts are executable: `chmod +x run.sh`
2. Check environment variables are set (use `common.sh`)
3. Verify dependencies are installed

### Sync Issues

```bash
# Check sync configuration
.pi/skills/skills-sync/skills-sync info

# Dry-run to see what would change
.pi/skills/skills-sync/skills-sync pull --dry-run
```
