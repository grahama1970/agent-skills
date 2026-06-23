# Rendered goal / progress page (HTML/CSS)

> **This is where the human checks your work.** Open this page — not the agent chat — to see what was fixed and what remains.

> **Blocking rules:** see **`REPORT_ENFORCEMENT.md`** before claiming any round closed.


This skill uses a **living HTML/CSS page** as the visual creation artifact.
It is **not** the Excalidraw / UX Lab pipeline workflow (`pipeline.yaml` →
`localhost:3002/#architecture`). If you only see that shorter skill body, you
have a **stale attachment** — use this directory's `SKILL.md`.

## What it is

| Name | Also called | Purpose |
|------|-------------|---------|
| **Rendered goal page** | `GOAL_PAGE.html`, HTML/CSS report, progress page | Source-derived target model WebGPT compares against local evidence |
| **Per-round progress** | Same file, updated each slice | Gaps/sanity table, proof commands, next slice id |

The page is **context for creation**, not proof of implementation. Live proof
still comes from daemon tests and `gap-report.md`.

## Where it lives (no global path)

There is **one rendered page per project engagement**, chosen by the project
agent and named in `GOAL.md`:

```markdown
**Rendered goal:** `<repo-relative-path-to>.html`
```

### Packaging for WebGPT (≤5-file creation zip)

When attaching to `$surf webgpt.submit --attach-file`, copy or symlink the
project HTML as slot 4:

| Zip member | Contents |
|------------|----------|
| `GOAL_PAGE.html` | The rendered goal/progress page (this document's subject) |

In concatenated bundles, cite the repo path and paste a short HTML excerpt or
attach the file separately.

### Engagement artifacts (markdown, not the HTML page)

These live under the target repo, not in `agent-skills/`:

```text
<target-repo>/docs/create-architecture/<slice-id>/
  HANDOFF.md
  GOAL.md              # must name the rendered goal path
  gap-report.md        # per-round closure (markdown)
  sanity-report.md
  run-<timestamp>/
    {project}-{slice-id}-solution.zip   # never source.zip
    ...
```

Do **not** confuse `gap-report.md` with the HTML/CSS page. Update **both**
after each round.

## Required content (minimum)

Derived from the same facts as `GOAL.md`:

1. **Executive summary** — lanes, endpoints, what is LIVE vs MISSING
2. **Master flow** — end-to-end diagram (Mermaid or equivalent)
3. **Gaps / sanity table** — rows marked **LIVE**, **PARTIAL**, **MISSING**, or **UNIT**
4. **Roadmap priorities** — P0, P1, … with current status
5. **Worked examples** — at least one happy path and one clarify/fail path
6. **Technical appendix** — schemas, gate order, test names, proof commands
7. **Round footer** (after each port) — slice id, solution zip sha256, proof commands + exit codes

## Update cadence (every round)

After solution zip port + tests:

1. Edit the rendered HTML gaps/sanity rows (LIVE / PARTIAL / MISSING).
2. Update roadmap slice status (e.g. P0 → DONE (LIVE)).
3. Write or refresh `<slice-id>/gap-report.md` in the target repo.
4. Optionally CDP-verify a served URL and save receipt under
   `<target-repo>/.codex/ui-verification/latest.json`.
5. Include the rendered page path (or `GOAL_PAGE.html`) in the **next**
   creation bundle.

A stale HTML page when submitting to WebGPT is a **creation-bundle defect**.

## Serving and CDP verification

**File path** is authoritative for git. For browser/CDP proof, serve the repo
or copy HTML to a stable review URL:

```bash
# Example: static server from repo root (adjust port)
cd /path/to/target-repo && python -m http.server 8771

# CDP read proof (optional but recommended before citing as progress)
~/.codex/hooks/verify-ui-cdp.sh \
  --url "http://127.0.0.1:8771/docs/<YOUR_PAGE>.html" \
  --name "<project>-rendered-goal"
cp "/tmp/codex-ui-verification/<project>/<surface>/<timestamp>.read.json" \
  .codex/ui-verification/latest.json
```

Reuse the same URL across rounds when possible so humans and WebGPT can diff
progress.

## Example: memory / SPARTA routing

| Field | Value |
|-------|-------|
| Project | `memory` (`/home/graham/workspace/experiments/memory`) |
| Rendered goal | `docs/SPARTA_ROUTING_EVIDENCE_CASE_FLOW.html` |
| GOAL.md slice dirs | `docs/create-architecture/sparta-routing-P0/`, `P1/`, … |
| Live proof script | `scripts/sanity/domain_recall_live.sh` |
| WebGPT tab binding | `agents/memory.webgpt.example.yaml` |
| Binding yaml | `agents/memory.rendered-goal.example.yaml` |

P0/P1 rows in the HTML sanity table must match `gap-report.md` in each slice
directory.

## WebGPT delivery

**Never rename** the download to `source.zip`. Use `{project}-{slice-id}-solution.zip`
in Downloads and in the run dir.


When WebGPT produces **more than one file**, it must return a **single
solution zip** + `MANIFEST.json`, named `{project}-{slice-id}-solution.zip`
(e.g. `memory-sparta-routing-P0-solution.zip`). Generic names = routing failure.

## Anti-patterns

- Using only `gap-report.md` and skipping HTML updates
- Pointing WebGPT at a path without inlining or attaching `GOAL_PAGE.html`
- Treating Excalidraw UX Lab output as this skill's rendered goal page
- Marking a gap **LIVE** in HTML before live daemon tests pass
