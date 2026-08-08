---
name: github-search
description: >
  Deep GitHub repository and code search. For implementation research, uses the
  sibling brave-search skill to discover candidates, ranks them by requested
  criteria, stars, and relevance, clones the leaders to /tmp, verifies a detected
  entry point, then locates and evaluates the requested code.
allowed-tools: ["Bash", "Read"]
triggers:
  - github search
  - search github
  - find on github
  - github code
  - search repos
  - find implementation
  - evaluate github repos
  - find working implementation
  - test github repository
metadata:
  short-description: Search, run, and evaluate GitHub implementations

provides:
  - github-search
composes:
  - brave-search
  - task-monitor
  - agentic-evals
disciplines:
  - research-retrieval
---

# GitHub Search

Search GitHub repositories and code with two complementary workflows:

1. **Executable implementation evaluation** — Brave discovery, deterministic ranking, cloning, entry-point verification, local code evidence, and evaluation.
2. **Direct GitHub search** — repository, code, symbol, path, issue, and file lookup through `gh`.

For requests to find a usable implementation, prefer the executable evaluation workflow rather than trusting stars or search snippets alone.

## Prerequisites

- `gh` installed and authenticated: `gh auth login`
- `git`, Python 3.11+, and either `uv` or `venv`/`pip`
- `BRAVE_API_KEY` or `BRAVE_SEARCH_API_KEY` available to the sibling `brave-search` skill
- Optional but recommended: `bwrap` for filesystem and network isolation during untrusted execution

Check GitHub authentication:

```bash
./run.sh check
```

## Executable Evaluation Workflow

```bash
./run.sh evaluate "Python OAuth device-code flow" \
  --criteria "library, maintained, typed API" \
  --min-stars 100 \
  --language Python \
  --updated-after 2025-01-01 \
  --top 3 \
  --json
```

The pipeline runs in this order:

1. Call `../brave-search/run.sh web` with a `site:github.com` query.
2. Normalize Brave result URLs to unique `owner/repo` candidates.
3. Enrich candidates with GitHub metadata through `gh repo view`.
4. Apply hard filters such as language, minimum stars, update date, license, archive/fork status, and repository size.
5. Rank survivors with a transparent weighted score:
   - requested-query and criteria relevance: 55%
   - logarithmic GitHub star score: 25%
   - Brave result position: 20%
6. Clone up to five top repositories beneath `/tmp/github-search-eval-*`.
7. Detect an entry point from standard manifests and files, then invoke its help path with a timeout and resource limits.
8. Only when the entry point exits with code 0, search the clean clone for the requested implementation and collect scored snippets.
9. Produce a heuristic assessment using discovery rank, code evidence breadth/strength, and repository signals such as tests, CI, license, README, and package manifests.

The JSON result records rejected candidates and filter reasons, ranking components, clone paths, exact commands, exit status, sandbox mode, captured output, relevant files and snippets, score components, limitations, and the best successful candidate.

### Ranking and Filter Options

| Option | Meaning |
|---|---|
| `--criteria TEXT` | Additional free-text relevance criteria |
| `--min-stars N` | Minimum GitHub stars |
| `--language NAME` | Required primary language |
| `--updated-after YYYY-MM-DD` | Required latest update date |
| `--license SPDX` | Required SPDX license identifier |
| `--candidates N` | Brave results to inspect, 1–20 |
| `--top N` | Repositories to clone and execute, 1–5 |
| `--max-size-mb N` | Reject repositories above the metadata size limit |
| `--include-archived` | Permit archived repositories |
| `--include-forks` | Permit forks |

### Entry-Point Options

Detection checks, in order:

- `[project.scripts]` and Poetry scripts in `pyproject.toml`
- Python package `__main__.py`
- root `main.py`, `cli.py`, or `app.py`
- `package.json` `bin` or `start`/`cli`/`demo` scripts
- `Cargo.toml`, `go.mod`, root `run.sh`, and executable files in `bin/`

Override detection without invoking a shell:

```bash
./run.sh evaluate "streaming parser" --entrypoint "python3 examples/demo.py --help"
```

The automatic check does not install dependencies. A failure caused by missing dependencies remains a failed candidate rather than silently executing package-install scripts.

### Untrusted Execution Controls

Repository code is untrusted. The evaluator:

- clones to a dedicated `/tmp` workspace;
- runs a disposable copy, preserving a clean source clone for evidence search;
- strips inherited credentials and uses a minimal environment and temporary home;
- removes symlinks escaping the execution copy;
- applies CPU, memory, process, file-size, file-descriptor, timeout, and output limits;
- prefers Bubblewrap isolation, then network namespaces, then a clearly labeled host-limited fallback;
- disables network where the selected sandbox supports it;
- never runs through `shell=True`;
- searches and scores code only after a zero exit status.

Use strict Bubblewrap-only execution for higher assurance:

```bash
./run.sh evaluate "request router" --sandbox strict --json
```

Network access is off by default. Enable it only when explicitly needed and accepted:

```bash
./run.sh evaluate "client SDK example" --allow-network --json
```

`--allow-network` permits untrusted code to communicate externally; it still receives a scrubbed environment without Brave or GitHub credentials.

Clones remain under `/tmp` by default. Use `--cleanup` to remove the workspace after producing the report.

## Direct GitHub Search

```bash
# Search repositories
./run.sh search "AI agent memory systems" --limit 5

# Search with current activity/star filters
./run.sh search "satellite security" \
  --updated ">=2026-07-20" \
  --stars ">0" \
  --sort updated \
  --order desc \
  --limit 10 \
  --json

# Existing deep GitHub metadata/code analysis
./run.sh search "langchain memory" --deep --json

# Analyze a repository
./run.sh repo langchain-ai/langchain --json

# Search a symbol definition
./run.sh code "BaseMemory" --repo langchain-ai/langchain --symbol BaseMemory

# Search a path
./run.sh code "retrieval" --repo owner/repo --path src/

# Search issues
./run.sh issues "memory leak" --state open

# Fetch a file
./run.sh file owner/repo src/main.py
```

### Sparse Security Domain Workflow

For niche domains such as satellite, rocket, avionics, embedded, ICS, RF, or
space-hardware penetration testing, do not rely on one GitHub query. Fan out
multiple `$brave-search` `site:github.com` questions first, normalize the
result URLs to `owner/repo`, then validate candidates with this skill.

Recommended sequence:

```bash
../brave-search/run.sh web "site:github.com satellite security testbed penetration testing" --count 10
../brave-search/run.sh web "site:github.com spacecraft cybersecurity penetration testing satellite" --count 10
../brave-search/run.sh web "site:github.com cubesat security attack defense testbed" --count 10

./run.sh search "satellite security" \
  --updated ">=2026-07-20" \
  --stars ">0" \
  --sort updated \
  --order desc \
  --limit 20 \
  --json

./run.sh repo owner/repo --json
./run.sh file owner/repo README.md --json
./run.sh code "attack exploit testbed telemetry command" --repo owner/repo --json
```

Use GitHub filter flags such as `--updated`, `--stars`, `--sort`, and `--order`
instead of embedding range qualifiers inside the query string. The GitHub CLI
parses those flags more reliably than a single mixed query argument.

Promotion criteria for security repositories:

- Prefer non-archived, non-fork repositories with real stars, a recent
  `pushedAt` or `updatedAt`, clear license, README, testbed/lab framing, and
  relevant code paths or documentation.
- Treat `updatedAt` as repository activity. Prefer `pushedAt` when the question
  requires code changed this week.
- Down-rank generic curated lists unless the user asked for resources rather
  than a runnable repo.
- Do not run untrusted penetration-testing, exploit, malware, red-team, or
  dual-use code on the host. Use the executable evaluation workflow with
  `--sandbox strict` where possible, or hand the selected repo to a disposable
  Docker/container harness.

## Evaluation Guidance

Treat the automated assessment as triage, not proof. A successful `--help`-style entry point demonstrates that the detected surface loads and exits cleanly under the selected environment; it does not establish full functional correctness. Read the cited snippets, inspect tests and license terms, and explain any missing dependencies, reduced sandboxing, weak evidence, stale metadata, or ambiguous matches in the final recommendation.

## Optional Integrations

Fetched code can still be passed to `/treesitter` for symbol extraction and `/taxonomy` for classification. The executable evaluation path performs local evidence search first so that post-run analysis is based on the exact cloned revision.
