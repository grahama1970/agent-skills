---
name: dogpile
description: >
  Deep research aggregator that searches Brave (Web), GitHub (Code/Issues),
  ArXiv (Papers), YouTube (Videos), and optional feed/archive/book
  sources. Provides a consolidated Markdown report with an ambiguity check,
  grounded synthesis, and Agentic Handoff.
allowed-tools:
  - run_command
  - read_file
triggers:
  - dogpile
  - research
  - deep search
  - find code
  - search everything
metadata:
  short-description: Deep research aggregator (Web, Code, Papers, Videos, Feeds)
provides:
  - deep-research
  - web-search
composes:
  - memory
  - scillm
  - brave-search
  - github-search
  - arxiv
  - ingest-youtube
  - fetcher
  - extractor
  - ingest-book
  - task-monitor
complies:
  - best-practices-skills
  - best-practices-python
runtime_self_improvement: substantial

taxonomy:
  - research
  - aggregation
  - resilience
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Dogpile: Deep Research Aggregator

Orchestrate a multi-source deep search to "dogpile" on a problem from every angle.

## Analyzed Sources

1.  **scillm LLM lanes (🤖)**: Query ambiguity checks, query tailoring, technical overview, and code/paper relevance evaluation. Dogpile calls `POST http://localhost:4001/v1/chat/completions` with `Authorization: Bearer sk-dev-proxy-123` and `X-Caller-Skill: dogpile`; it does not call OpenAI, Claude, Gemini, or Codex provider APIs directly.
2.  **Concurrent Brave question lanes (🌐)**: Perplexity replacement. Dogpile fans out multiple bounded Brave web queries and records each result set separately.
3.  **Brave Search (🌐)**: **Three-Stage Search** (Search → Evaluate → Deep Extract via /fetcher).
4.  **ArXiv (📄)**: **Three-Stage Search** (Abstracts → Details → Full Paper via /fetcher + /extractor).
5.  **YouTube (📺)**: **Two-Stage Search** (Metadata → Detailed Transcripts via Whisper/Direct).
6.  **GitHub (🐙)**: **Three-Stage Search**:
    - **Stage 1**: Search repositories and issues
    - **Stage 2**: Fetch README.md and metadata for top repos, agent evaluates relevance
    - **Stage 3**: Deep code search inside the selected repository
7.  **Feed monitors (📰, opt-in)**: Fresh RSS feed monitor dry-runs through `consume-feed`; this is source-health/freshness evidence, not query-specific web search.
8.  **Wayback Machine (🏛️, opt-in)**: Historical snapshots for URLs.
9.  **Readarr / books / Usenet (📚, opt-in)**: Local long-form source discovery when intentionally requested.

## Features

1.  **Query Tailoring**: Uses `/scillm` to generate service-specific queries optimized for each source:
    - **ArXiv**: Academic/technical terms
    - **Brave Questions**: Natural-language research questions formerly sent to Perplexity
    - **Brave**: Documentation-style keyword queries that must fit Brave's hard limits (`<=400` chars, `<=50` words)
    - **GitHub**: Code patterns, library names
    - **YouTube**: Tutorial-style phrases

2.  **Ambiguity Guard**: Uses `/scillm` to analyze the query first. If ambiguous, it asks you for clarification before wasting resources.

3.  **Three-Stage Deep Dive**:
    - **ArXiv**: Fetches detailed metadata → Agent evaluates → Full PDF extraction via /fetcher + /extractor
    - **GitHub**: Fetches README + metadata → Agent evaluates most relevant repo → Deep code search
    - **Brave**: Fetches results → Agent evaluates → Full page extraction via /fetcher
    - **YouTube**: Extracts full transcripts for the most relevant videos

4.  **Report Assembly and Synthesis**: Consolidates successful provider results into a Markdown report and generates a compact grounded synthesis. LLM source failures are reported as degraded provider results, not as a total search failure.

5.  **Textual TUI Monitor**: Real-time progress tracking of all concurrent searches via `run.sh monitor`.

6.  **Resilience Features** (2025-2026 Best Practices):
    - **Per-provider semaphores**: Limits concurrent requests to avoid rate limit bans
    - **Exponential backoff with jitter**: Prevents thundering herd on retries (via tenacity)
    - **Rate limit header parsing**: Respects Retry-After, x-ratelimit-*, and IETF RateLimit-* headers
    - **Automatic retry**: Retries rate-limited requests after appropriate backoff
    - **Brave query budgeting**: Compresses overlong Brave queries before dispatch instead of sending invalid 422 requests
    - **Incremental result publishing**: Writes structured partial results as providers finish so the caller does not need to wait for the final report

## LLM Contract

Dogpile has exactly one active LLM integration: `/scillm`.

- Endpoint: `POST http://localhost:4001/v1/chat/completions`
- Required headers: `Authorization: Bearer sk-dev-proxy-123` and `X-Caller-Skill: dogpile`
- Primary reasoning lane: `model: "gpt-5.5"` through `httpx`
- No routine LLM fallback lane: if `gpt-5.5` is unavailable, the LLM source is logged as degraded and Dogpile still returns successful retrieval results
- Vision/high-reasoning adjudication lane: `model: "gpt-5.5"` with image content sent through `/scillm`; do not spend Claude/Gemini quota unless explicitly requested
- JSON tasks: send `response_format: {"type": "json_object"}` and ask for JSON in the prompt
- Forbidden: `max_tokens` in dogpile's `/scillm` calls
- Provider names in logs use logical lane names such as `scillm-gpt55`; scillm decides the concrete upstream provider and returns it in the response `model`
- Retrieval sources: Brave Search, GitHub, ArXiv, YouTube, and opt-in feed/Wayback/Readarr use their native retrieval APIs. `/scillm` is for query tailoring, ranking, summarization, ambiguity checks, and review of retrieved evidence.
- Perplexity status: retired. Dogpile does not call Perplexity by default or by flag; it records a skipped/degraded source and uses concurrent Brave question searches instead.

If `/scillm` fails, dogpile records the LLM lane as a degraded provider result and continues with Brave, GitHub, ArXiv, YouTube, optional feed, optional Readarr, and optional Wayback results.

## Orchestration Boundary

Dogpile is the retrieval and synthesis engine. It should not require Tau for the
default path and should not call WebGPT/browser tools directly.

- Use `$ask` for WebGPT, browser-oracle, oracle, deep-review, parallel-review, or
  credibility review workflows.
- A Tau researcher can sit above Dogpile as an optional caller that runs
  creator/reviewer loops, consumes Dogpile receipts, and requests follow-up
  Dogpile fan-outs when the synthesis reports weak coverage.
- Dogpile itself must emit enough grounded synthesis that a project agent can
  use the result without guessing from raw provider dumps.

Threat-intel and security feed hits are enrichment by default. Do not treat
feed hits as automatic block decisions, alerts, or proof of compromise unless
the project workflow adds high-confidence environmental corroboration. The
default rule is: block on certainty, hunt on suspicion, enrich everything else.

### Optional Feed Pack Selection

Feeds are disabled by default. Enable them only when fresh security/code
monitoring is relevant to the research question, and use them as contextual
enrichment alongside Brave, GitHub, ArXiv, and YouTube evidence.

| Feed pack/source | Activate when the project agent needs |
|------------------|----------------------------------------|
| `security_code` | Compact code, AppSec, vulnerability, red-team, and operational security monitoring with low default noise |
| `security_code_extended` | Practitioner-grade malware, cloud, exploit-development, email-threat, and policy context in addition to `security_code` |
| BleepingComputer | Daily incident, malware, ransomware, and active-exploitation coverage |
| Krebs on Security | Investigative cybercrime, breach, fraud, and infrastructure reporting |
| SANS Internet Storm Center | Operational threat-handler notes and near-term defender awareness |
| Help Net Security | Security tooling, trends, and general industry updates |
| PortSwigger Research | Web application security, HTTP/browser attack research, and payload techniques |
| Google Project Zero | Deep vulnerability research, exploit chains, memory safety, and root-cause analysis |
| Google Online Security Blog | Platform, browser, ecosystem, and secure engineering context |
| GitHub Security Blog | Supply-chain, dependency, DevSecOps, and open-source security updates |
| GitHub Security Lab | CodeQL, vulnerability research, and code-level bug analysis |
| SpecterOps | Active Directory, Windows internals, and enterprise red-team tradecraft |
| Black Hills Information Security | Practical pentest methodology, tooling, and defensive/offensive operations |
| TrustedSec | Red-team methodology, tool releases, and practitioner tradecraft |
| SentinelOne Labs | Malware reverse engineering, APT reporting, and technical campaign analysis |
| Malwarebytes Labs | Commodity malware, malvertising, and broad malware landscape monitoring |
| Wiz Blog | Cloud, Kubernetes, identity, and infrastructure security research |
| Unit 42 | Threat research, cloud campaigns, network security, and adversary reporting |
| Offensive Security | Exploit-development education, offensive security, and Kali ecosystem updates |
| Corelan Team | Windows exploit development, mitigation bypass, and low-level exploitation |
| Proofpoint Threat Insight | Email-borne threats, phishing, BEC, and initial-access tradecraft |
| EFF Deeplinks | Security-relevant privacy, policy, legal, DMCA/CFAA, and civil-liberties context |

Raw IoC feeds such as CISA KEV JSON, URLhaus, Spamhaus, OpenPhish, and
AlienVault OTX are not part of the default readable RSS lane. Treat them as
separate enrichment/TIP inputs that need freshness, confidence, relevance,
allowlist, and corroboration checks before any alerting or blocking decision.

Optional `/agents` profiles are provided for higher-rigor workflows:

- `agents/researcher.yaml`: converts Dogpile receipts into a bounded research
  brief and follow-up question set.
- `agents/reviewer.yaml`: checks credibility, source grounding, skipped-provider
  honesty, and whether more fan-out is needed.

## Automatic Synthesis Contract

Every normal search should produce a compact evidence synthesis in the final
report and partial-results stream when `/scillm` is available. The synthesis
must:

- Ground substantive claims in retrieved Brave, GitHub, ArXiv, YouTube, feed, or
  optional source evidence.
- Name conflicts, weak coverage, skipped providers, and missing evidence.
- Treat security/threat-intel feeds as enrichment-only unless multiple
  high-confidence signals agree.
- Include a short "Most useful sources" list.
- Avoid inventing citations, URLs, or conclusions not supported by retrieved
  evidence.

## Persona, Rationale, and Problem Context

Dogpile requests may include explicit review persona, rationale, and problem
context. These fields are first-class request metadata, not hidden prose:

```bash
./run.sh search "accessible warning validation message contrast dark UI" \
  --persona nico-bailon \
  --rationale "Resolve repeated review-design blockers for the DAG editor" \
  --context "Need evidence-backed guidance for warning acknowledgement, Memory amendment copy, and audit traceability"
```

Supported fields:

- `--persona`: reviewer or research persona whose priorities should shape LLM
  analysis and query tailoring.
- `--rationale`: why the dogpile is being run now, including blocker context.
- `--context`: concrete problem context and constraints.
- `--context-file`: additional context read from a local file.

Dogpile stores these fields in `dogpile_partial_results.json` under
`request_context`, emits them in the initial `[dogpile-event] search_started`
event, includes them in scillm-powered ambiguity/tailoring/knowledge prompts,
and prepends them to the final report. Retrieval providers still receive
search-engine-suitable queries; the context is used to generate and interpret
those queries rather than silently broadening every native search call.

## GitHub Three-Stage Search

The GitHub search uses intelligent evaluation to find the most relevant repository:

```
Stage 1: Broad Search
├── Search repos: gh search repos "query"
├── Search issues: gh search issues "query"
└── Returns: Top 5 repos and issues

Stage 2: README Analysis & Evaluation
├── For top 3 repos:
│   ├── gh repo view <repo> --json ... (metadata)
│   ├── gh api repos/<repo>/readme (README content)
│   └── gh api repos/<repo>/languages (language breakdown)
├── Codex evaluates based on:
│   ├── README content relevance
│   ├── Topics and tags
│   ├── Language/tech stack match
│   └── Activity (stars, recent updates)
└── Returns: Selected target repository

Stage 3: Deep Code Search
├── gh api repos/<repo>/contents (file tree)
├── gh search code --repo <repo> "query" (code matches)
└── Returns: File structure + code locations with context
```

## Presets (For Security Research)

**Don't think about 100+ resources. Pick ONE preset:**

| Preset | Use When |
|--------|----------|
| `vulnerability_research` | CVE lookup, exploit availability |
| `red_team` | Privesc, bypasses, payloads |
| `blue_team` | Detection rules, threat hunting |
| `threat_intel` | APT groups, IOCs, campaigns |
| `malware_analysis` | Sample analysis, sandboxes |
| `osint` | Recon, domain intel |
| `bleeding_edge` | Latest zero-days |
| `community` | Reddit, Discord discussions |
| `general` | Non-security research |

```bash
# Use a preset (recommended for security research)
./run.sh search "CVE-2024-1234" --preset vulnerability_research
./run.sh search "privesc linux" --preset red_team

# Auto-detect preset from query
./run.sh search "CVE-2024-1234" --auto-preset

# List all presets
python cli.py presets
```

Presets use **Brave site: filters** to search curated domains (Exploit-DB, GTFOBins, MITRE ATT&CK, etc.) plus **direct API calls** for resources with APIs (NVD, CISA KEV, MalwareBazaar).

## Commands

| Command | Description |
|---------|-------------|
| `./run.sh search "query"` | Run a search |
| `./run.sh search "query" --html-report --open-report` | Launch a self-contained HTML/CSS report for clearer review |
| `./run.sh search "query" --preset NAME` | Search with a preset |
| `./run.sh search "query" --with-readarr` | Include local Readarr/Usenet book search |
| `./run.sh search "query" --with-wayback` | Include Wayback archive lookup |
| `./run.sh search "query" --with-feeds --feed-limit 3` | Include the compact `security_code` RSS feed pack dry-run |
| `./run.sh search "query" --with-feeds --feed-pack security_code_extended --feed-limit 3` | Include the extended practitioner security RSS pack |
| `./run.sh search "query" --with-perplexity` | Deprecated audit flag; records Perplexity as skipped and never calls the paid API |
| `./run.sh monitor` | Open the Real-time TUI Monitor |
| `python cli.py presets` | List available presets |
| `python cli.py resources` | List all resources |
| `python cli.py errors` | View error summary |
| `python cli.py errors --json` | Get errors as JSON |
| `python cli.py errors --clear` | Clear error logs |
| `./run.sh extract <url>` | Fetch paper, extract QRAs, store to /memory |
| `./run.sh extract <url> --scope NAME` | Extract to specific memory scope |
| `./run.sh extract <url> --dry-run` | Extract without storing |

## Usage

```bash
# General research
./run.sh search "AI agent memory systems"
./run.sh search "AI agent memory systems" --html-report --open-report

# Security research with preset
./run.sh search "CVE-2024-1234" --preset vulnerability_research

# Extract a paper to /memory (fetch → QRA → store)
./run.sh extract "https://pmc.ncbi.nlm.nih.gov/articles/PMC11202128" --scope dream-research
./run.sh extract "https://arxiv.org/abs/2401.12345" --scope behavioral --tags "neuroscience,memory"
./run.sh extract paper.pdf --context "reinforcement learning" --dry-run
```

## Agentic Handoff

The skill automatically analyzes queries for ambiguity.

- If the query is clear (e.g., "python sort list"), it proceeds.
- If ambiguous (e.g., "apple"), it returns a JSON object with clarifying questions.
  - The calling agent should interpret this JSON and ask the user the questions.

## Error Reporting & Debugging

Dogpile tracks all errors, rate limits, and failures for agent debugging.

### Error Commands

```bash
# View error summary (human-readable)
python cli.py errors

# View errors as JSON (for agent parsing)
python cli.py errors --json

# Clear error logs
python cli.py errors --clear
```

### Error Logs

| File | Contents |
|------|----------|
| `dogpile_errors.json` | Structured error log (last 50 sessions) |
| `dogpile.log` | Human-readable log (timestamped) |

### Ask DAG repair hints

When `/ask` runs `dogpile.search`, it loads `config/ask_dag_repair_hints.yaml` from
this skill. Published hints tell `/ask` to:

- Bump low node timeouts to `360s` when dogpile is killed by the parent budget.
- Consume `dogpile_partial_results.json` when a usable `final_report` or stage
  results were persisted before timeout.

| `dogpile_partial_results.json` | Structured partial results updated as each provider/stage completes |
| `rate_limit_state.json` | Persistent rate limit tracking |
| `dogpile_task_state.json` | Real-time task-monitor status for monitoring |

### Incremental Result Contract

Dogpile now emits machine-readable progress lines to `stderr` as results arrive:

```text
[dogpile-event] {"event":"partial_result","stage":"stage1","provider":"brave",...}
```

The latest structured state is also persisted to `dogpile_partial_results.json`.
Project agents should prefer this file/events stream when they need to start using
Brave/GitHub/ArXiv results before the full Dogpile report is finished.

### Rate Limit Tracking

Rate limits are tracked per-provider with:
- Total hit count
- Exponential backoff multiplier
- Reset timestamps
- Last hit time

When a provider is rate-limited:
1. Error is logged to `dogpile_errors.json`
2. Backoff multiplier increases (up to 10x)
3. Status appears in `dogpile_task_state.json`
4. Summary shown at end of search

### Agent Debugging Workflow

```bash
# 1. Run search
./run.sh search "query"

# 2. If errors occurred, check summary
python cli.py errors --json | jq '.rate_limits'

# 3. View recent errors
python cli.py errors --json | jq '.recent_errors'

# 4. Check specific provider
cat dogpile_task_state.json | jq '.provider_status'
```

### Error Types

| Type | Description |
|------|-------------|
| `rate_limit` | HTTP 429 or rate limit headers detected |
| `timeout` | Request timed out |
| `auth_failure` | 401/403 authentication error |
| `network_error` | Connection failed |
| `api_error` | Provider API returned error |
| `parse_error` | Failed to parse response |
| `config_error` | Missing configuration |
| `dependency_missing` | Required module not installed |

## Memory + Taxonomy Integration

Dogpile integrates with the federated memory system to avoid redundant research
and build institutional knowledge across sessions.

### Pre-hook: `recall_prior_research(query, k=5)`

Called before starting expensive multi-source searches. Recalls prior research
findings on the same or similar topics from memory. If prior research exists,
it is displayed to the agent, potentially avoiding redundant API calls.

### Post-hook: `learn_research(query, sources_searched, findings, synthesis, key_urls)`

Called after search completes. Learns:
- **Research snapshot**: Query, sources searched, date, topic domain
- **Synthesis**: The Codex high-reasoning conclusion (most valuable piece)
- **Key URLs**: Discovered URLs for future reference without re-searching

### Tags

- Base: `["dogpile_research", <topic_domain>]`
- Bridge keywords extracted via taxonomy:
  - **Precision**: verified, confirmed, source, cited
  - **Resilience**: multiple sources, consensus, corroborated
  - **Fragility**: contradictory, uncertain, unverified
  - **Corruption**: security, vulnerability, CVE, malware
  - **Loyalty**: dependency, integration, compatibility
  - **Stealth**: undocumented, hidden, edge case

### File

- `memory_integration.py` -- Pre/post hooks with graceful degradation

## Task Monitor Integration

Dogpile integrates with `/task-monitor` for centralized progress tracking.

### Automatic Registration

Every search automatically:
1. Registers with `~/.pi/task-monitor/registry.json`
2. Writes progress to `dogpile_task_state.json`
3. Reports provider status and timing

### Progress Tracking

The task monitor state includes:
- Completed/total steps
- Per-provider status (pending, running, done, error, rate_limited)
- Per-provider timing
- Error count and recent errors
- Rate limit summary

### Viewing Progress

```bash
# Via task-monitor TUI
cd ~/.pi/skills/task-monitor
uv run python monitor.py tui --filter dogpile

# Direct state file
cat .pi/skills/dogpile/dogpile_task_state.json | jq

# Via task-monitor API (if running)
curl http://localhost:8765/tasks/dogpile-search
```

### Task State Schema

```json
{
  "completed": 12,
  "total": 16,
  "description": "Dogpile: AI agent skills 2026",
  "current_item": "synthesis",
  "stats": {
    "providers_done": 8,
    "providers_total": 9,
    "errors": 2,
    "rate_limits": 1
  },
  "provider_status": {
    "brave": "done",
    "brave_questions": "done",
    "perplexity": "skipped",
    "readarr": "skipped",
    "wayback": "skipped",
    "feeds": "skipped",
    "github": "done",
    "codex_knowledge": "rate_limited"
  },
  "provider_times": {
    "brave": 3.2,
    "github": 12.4
  },
  "errors": [...],
  "elapsed_seconds": 45.2,
  "progress_pct": 75.0,
  "status": "running"
}
```

## Common Mistakes

```bash
# WRONG: Send ambiguous query, ignore ambiguity response
./run.sh search "apple"
# → Returns {"ambiguity_score": 0.8, "questions": ["Fruit? Company?"]}
# Agent proceeds anyway, gets mixed fruit + tech results
# RIGHT: Parse ambiguity JSON, ask user to clarify before searching

# WRONG: Use wrong preset for domain
./run.sh search "memory systems" --preset red_team
# → Returns exploit databases, not memory architecture research
# RIGHT: Use --auto-preset or manually select correct domain

# WRONG: Ignore agentic_handoff in response
# → dogpile returns suggested follow-up searches, agent ignores them
# RIGHT: Check response["agentic_handoff"] for recommended next steps
```
