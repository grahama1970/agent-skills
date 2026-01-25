name: dogpile
description: >
Deep research aggregator that searches Brave (Web), Perplexity (AI), GitHub (Code/Issues),
ArXiv (Papers), YouTube (Videos), and Wayback Machine simultaneously.
Provides a consolidated Markdown report with an ambiguity check and Agentic Handoff.
allowed-tools: ["run_command", "read_file"]
triggers:

- dogpile
- research
- deep search
- find code
- search everything
  metadata:
  short-description: Deep research aggregator (Web, AI, Code, Papers, Videos)

---

# Dogpile: Deep Research Aggregator

Orchestrate a multi-source deep search to "dogpile" on a problem from every angle.

## Analyzed Sources

1.  **Codex (🤖)**: High-reasoning technical starting point and final synthesis (gpt-5.2).
2.  **Perplexity (🧠)**: AI-synthesized deep answers and reasoning (Sonar Reasoning).
3.  **Brave Search (🌐)**: Broad web context, news, and official docs.
4.  **ArXiv (📄)**: **Two-Stage Search** (Abstracts → Deep Dive on relevant papers).
5.  **YouTube (📺)**: **Two-Stage Search** (Metadata → Detailed Transcripts via Whisper/Direct).
6.  **GitHub (🐙)**:
    - **Repositories**: Finding relevant libraries and tools.
    - **Deep Code Search**: Searching _inside_ the most relevant repo for definitions.
    - **Issues**: Finding discussions, bugs, and workarounds.
7.  **Wayback Machine (🏛️)**: Historical snapshots for URLs.

## Features

1.  **Ambiguity Guard**: Uses Codex High Reasoning to analyze the query first. If ambiguous, it asks you for clarification before wasting resources.
2.  **Two-Stage Deep Dive**:
    - **ArXiv**: Fetches detailed metadata and long abstracts for the top matches.
    - **YouTube**: Extracts full transcripts for the most relevant videos to provide textual insights.
3.  **Codex Synthesis**: Consolidates all results into a coherent, high-reasoning conclusion.
4.  **Textual TUI Monitor**: Real-time progress tracking of all concurrent searches via `run.sh monitor`.

## New Commands

- `./run.sh search "query"`: Run a search.
- `./run.sh monitor`: Open the Real-time TUI Monitor.

## Usage

```bash
# Search for everything on a topic
./run.sh search "AI agent memory systems"
```

## Agentic Handoff

The skill automatically analyzes queries for ambiguity.

- If the query is clear (e.g., "python sort list"), it proceeds.
- If ambiguous (e.g., "apple"), it returns a JSON object with clarifying questions.
  - The calling agent should interpret this JSON and ask the user the questions.
