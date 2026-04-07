---
name: episodic-archiver
description: >
  Episodic Memory Archiver. Stores full conversation transcripts with embeddings
  and analysis into ArangoDB. Tracks UNRESOLVED sessions for reflection with
  structured failure episodes (trigger/diagnosis/action/outcome), K~4 similar
  failure retrieval, user behavioral profiling, and federated taxonomy classification.
internal: true
allowed-tools: Bash
triggers:
  - archive conversation
  - save episode
  - store transcript
  - remember this conversation
  - list unresolved
  - fix success rate
  - similar failures
  - user profile
metadata:
  short-description: Analyzes and stores episodic conversation memory with failure learning and user profiling

provides:
  - episodic-archiver
composes:
  - memory
  - edge-verifier
  - scheduler
  - treesitter
  - interview
  - task-monitor
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Episodic Archiver

Analyzes conversation transcripts, embeds them for search, categorizes turns, **tracks unresolved sessions** for later reflection, and **builds per-user behavioral profiles**. Implements the **self-healing agentic pattern** with:

- **Structured failure episodes** (trigger/diagnosis/action/outcome)
- **K~4 similar failure retrieval** (research shows K~4 is optimal)
- **Fix outcome tracking** (what worked, which lessons helped)
- **User behavioral profiling** (communication style, expertise, bridge affinities)
- **Federated taxonomy** with high-fidelity LLM mode for nightly analysis

## Commands

```bash
# Archive a conversation transcript
./run.sh archive transcript.json

# Archive recent sessions from all registered sources
./run.sh archive-recent --hours 24

# Deep LLM analysis of an archived session
./run.sh analyze <session_id>

# List unresolved sessions (for reflection)
./run.sh list-unresolved

# Mark a session as resolved WITH fix tracking
./run.sh resolve <session_id> --fix "What fixed it" --lessons lesson1,lesson2 --outcome success

# View fix success rate metrics
./run.sh stats

# Register a transcript source
./run.sh register <name> <path> <glob>
```

## User Behavioral Profiling

Each session is analyzed to extract:

```json
{
  "communication_style": "technical|casual|formal|mixed",
  "expertise_domains": ["python", "security"],
  "expertise_level": "beginner|intermediate|advanced|expert",
  "response_preferences": {
    "verbosity": "concise|balanced|detailed",
    "format": "code-first|explanation-first|mixed"
  },
  "bridge_affinities": {"Precision": 0.8, "Resilience": 0.6}
}
```

Profiles are incrementally merged into `user_priors` collection (RGMem-style):
- Bridge affinities: weighted average across sessions
- Expertise domains: union (accumulate)
- Communication style: most-recent-3-sessions voting

## LLM Model Selection

- **Real-time archiving**: scillm `quick_completion()` (fast, low latency)
- **Nightly analysis**: `deepseek-ai/DeepSeek-V3.1-TEE` via `CHUTES_MODEL_ID`
- All LLM calls go through scillm (no raw httpx)

## Storage

**Collections:**
- `agent_conversations` - Individual turns with embeddings, user_id, persona_id
- `unresolved_sessions` - Sessions needing follow-up (with failure episodes)
- `session_summaries` - LLM-analyzed session assessments with taxonomy
- `user_priors` - Per-user behavioral profiles (incrementally updated)

**Turn categories:** Task, Question, Solution, Error, Chat, Meta

## Input Format

```json
{
  "session_id": "task_123",
  "user_id": "graham",
  "persona_id": "pi",
  "messages": [
    {"from": "User", "content": "Fix the bug in auth", "timestamp": 1234567890},
    {"from": "Agent", "content": "Looking at auth.py...", "timestamp": 1234567891}
  ]
}
```

## Integration

| Skill | How |
|-------|-----|
| `monitor-episodic-archiver` | Nightly pipeline, health monitoring |
| `memory` | Stores lessons from resolved sessions |
| `dogpile` | Researches unresolved gaps |
| `taxonomy` | Federated bridge classification |
| `scillm` | All LLM calls (quick_completion, acompletion) |
| `train-convo-steering` | State bucket estimation for steering |

## Common Mistakes

### WRONG: Archiving without tracking resolution status
```bash
./run.sh archive transcript.json  # archived but never resolved
```

### RIGHT: Track unresolved sessions and resolve with fix tracking
```bash
./run.sh archive transcript.json
./run.sh list-unresolved  # check what needs follow-up
./run.sh resolve <session_id> --fix "What fixed it" --lessons lesson1 --outcome success
```

### WRONG: Using raw httpx for LLM calls instead of scillm
```python
resp = httpx.post("https://api.chutes.ai/...", ...)  # bypass scillm
```

### RIGHT: All LLM calls go through scillm
```python
from scillm import quick_completion
result = quick_completion("Analyze this session...")
```

### WRONG: Forgetting to register transcript sources
```bash
./run.sh archive-recent  # no sources registered, archives nothing
```

### RIGHT: Register sources first, then archive
```bash
./run.sh register pi-sessions ~/.pi/sessions/ "*.json"
./run.sh archive-recent --hours 24
```
