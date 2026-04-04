# Skill Modularization Task File

## Overview
Refactor all Python scripts over 1000 lines in `.pi/skills` into modular, debuggable components following the movie-ingest pattern.

## Quality Gates (All Tasks)
- **Pre-hook**: `./sanity.sh` must exist and pass before modularization
- **Post-hook**: `./sanity.sh` must pass after modularization
- **Code Review**: 2-round GPT-5 review via `/code-review`
- **Preserve Original**: Keep `*_monolith.py` backup

## Definition of Done (Per Skill)
1. Original file renamed to `{name}_monolith.py`
2. New modular structure with files < 500 lines each
3. `sanity.sh` passes all CLI help checks
4. 2-round code review completed and fixes applied
5. No circular imports

---

## CRITICAL PRIORITY (2000+ lines)

### Task 1: Modularize create-paper (5609 lines)
- **File**: `create-paper/paper_writer.py`
- **Lines**: 5609 (WORST)
- **Suggested Modules**: config.py, utils.py, research.py, outline.py, sections.py, citations.py, formatting.py, export.py, cli.py
- **Definition of Done**: `create-paper/sanity.sh` passes, code review complete
- **Parallel**: No

### Task 2: Modularize fixture-graph (5397 lines)
- **File**: `fixture-graph/fixture_graph.py`
- **Lines**: 5397
- **Suggested Modules**: config.py, utils.py, graphviz_backend.py, mermaid_backend.py, networkx_backend.py, matplotlib_backend.py, plotly_backend.py, analysis.py, cli.py
- **Definition of Done**: `fixture-graph/sanity.sh` passes, code review complete
- **Parallel**: No

### Task 3: Modularize battle (3720 lines)
- **File**: `battle/battle.py`
- **Lines**: 3720
- **Suggested Modules**: config.py, utils.py, red_team.py, blue_team.py, scoring.py, insights.py, orchestrator.py, cli.py
- **Definition of Done**: `battle/sanity.sh` passes, code review complete
- **Parallel**: No

### Task 4: Modularize prompt-lab (2497 lines)
- **File**: `prompt-lab/prompt_lab.py`
- **Lines**: 2497
- **Suggested Modules**: config.py, utils.py, templates.py, evaluation.py, optimization.py, cli.py
- **Definition of Done**: `prompt-lab/sanity.sh` passes, code review complete
- **Parallel**: No

### Task 5: Modularize memory/horus_lore_ingest (2111 lines)
- **File**: `memory/horus_lore_ingest.py`
- **Lines**: 2111
- **Suggested Modules**: config.py, utils.py, parser.py, embeddings.py, storage.py, cli.py
- **Definition of Done**: `memory/sanity.sh` passes, code review complete
- **Parallel**: No

### Task 6: Modularize dogpile (2065 lines)
- **File**: `dogpile/dogpile.py`
- **Lines**: 2065
- **Suggested Modules**: config.py, utils.py, brave.py, perplexity.py, arxiv.py, github.py, youtube.py, wayback.py, synthesis.py, cli.py
- **Definition of Done**: `dogpile/sanity.sh` passes, code review complete
- **Parallel**: No

---

## HIGH PRIORITY (1000-2000 lines)

### Task 7: Modularize code-review (1930 lines)
- **File**: `code-review/code_review.py`
- **Lines**: 1930
- **Suggested Modules**: config.py, utils.py, providers/github.py, providers/anthropic.py, providers/openai.py, providers/google.py, diff_parser.py, cli.py
- **Definition of Done**: `code-review/sanity.sh` passes, code review complete
- **Parallel**: No

### Task 8: Modularize distill (1814 lines)
- **File**: `distill/distill.py`
- **Lines**: 1814
- **Suggested Modules**: config.py, utils.py, pdf_handler.py, url_handler.py, text_handler.py, qra_generator.py, cli.py
- **Definition of Done**: `distill/sanity.sh` passes, code review complete
- **Parallel**: No

### Task 9: Modularize task-monitor (1490 lines)
- **File**: `task-monitor/monitor.py`
- **Lines**: 1490
- **Suggested Modules**: config.py, utils.py, tui.py, http_api.py, scheduler_integration.py, cli.py
- **Definition of Done**: `task-monitor/sanity.sh` passes, code review complete
- **Parallel**: No

### Task 10: Modularize scheduler (1283 lines)
- **File**: `scheduler/scheduler.py`
- **Lines**: 1283
- **Suggested Modules**: config.py, utils.py, cron_parser.py, job_registry.py, executor.py, cli.py
- **Definition of Done**: `scheduler/sanity.sh` passes, code review complete
- **Parallel**: No

### Task 11: Modularize extractor (1233 lines)
- **File**: `extractor/extract.py`
- **Lines**: 1233
- **Suggested Modules**: config.py, utils.py, pdf_extractor.py, docx_extractor.py, html_extractor.py, image_extractor.py, cli.py
- **Definition of Done**: `extractor/sanity.sh` passes, code review complete
- **Parallel**: No

### Task 12: Modularize social-bridge (1220 lines)
- **File**: `social-bridge/social_bridge.py`
- **Lines**: 1220
- **Suggested Modules**: config.py, utils.py, telegram.py, twitter.py, discord_webhook.py, graph_storage.py, cli.py
- **Definition of Done**: `social-bridge/sanity.sh` passes, code review complete
- **Parallel**: No

### Task 13: Modularize youtube-transcripts (1182 lines)
- **File**: `youtube-transcripts/youtube_transcript.py`
- **Lines**: 1182
- **Suggested Modules**: config.py, utils.py, downloader.py, transcriber.py, formatter.py, cli.py
- **Definition of Done**: `youtube-transcripts/sanity.sh` passes, code review complete
- **Parallel**: No

### Task 14: Modularize arxiv (1177 lines)
- **File**: `arxiv/arxiv_learn.py`
- **Lines**: 1177
- **Suggested Modules**: config.py, utils.py, search.py, download.py, extraction.py, memory_storage.py, cli.py
- **Definition of Done**: `arxiv/sanity.sh` passes, code review complete
- **Parallel**: No

### Task 15: Modularize ops-discord (1102 lines)
- **File**: `ops-discord/discord_ops.py`
- **Lines**: 1102
- **Suggested Modules**: config.py, utils.py, webhook_monitor.py, keyword_matcher.py, graph_persistence.py, cli.py
- **Definition of Done**: `ops-discord/sanity.sh` passes, code review complete
- **Parallel**: No

### Task 16: Modularize batch-report (1088 lines)
- **File**: `batch-report/report.py`
- **Lines**: 1088
- **Suggested Modules**: config.py, utils.py, manifest_parser.py, analysis.py, markdown_generator.py, cli.py
- **Definition of Done**: `batch-report/sanity.sh` passes, code review complete
- **Parallel**: No

### Task 17: Modularize github-search (1051 lines)
- **File**: `github-search/github_search.py`
- **Lines**: 1051
- **Suggested Modules**: config.py, utils.py, repo_search.py, code_search.py, readme_analyzer.py, cli.py
- **Definition of Done**: `github-search/sanity.sh` passes, code review complete
- **Parallel**: No

### Task 18: Modularize hack (1031 lines)
- **File**: `hack/hack.py`
- **Lines**: 1031
- **Suggested Modules**: config.py, utils.py, container_manager.py, tools/nmap.py, tools/semgrep.py, tools/nuclei.py, cli.py
- **Definition of Done**: `hack/sanity.sh` passes, code review complete
- **Parallel**: No

### Task 19: Modularize qra (1016 lines)
- **File**: `qra/qra.py`
- **Lines**: 1016
- **Suggested Modules**: config.py, utils.py, extractor.py, validator.py, storage.py, cli.py
- **Definition of Done**: `qra/sanity.sh` passes, code review complete
- **Parallel**: No

---

## Completion Checklist

| # | Skill | Lines | Modules | Status | Sanity |
|---|-------|-------|---------|--------|--------|
| 1 | create-paper | 5609 | 10 | ✅ | ✔️ |
| 2 | fixture-graph | 5397 | 13 | ✅ | ✔️ |
| 3 | battle | 3720 | 14 | ✅ | ✔️ |
| 4 | prompt-lab | 2497 | 13 | ✅ | ✔️ |
| 5 | memory/horus_lore_ingest | 2111 | 8 | ✅ | ✔️ |
| 6 | dogpile | 2065 | 19 | ✅ | ✔️ |
| 7 | code-review | 1930 | 7 | ✅ | ✔️ |
| 8 | distill | 1814 | 13 | ✅ | ✔️ |
| 9 | task-monitor | 1490 | 3 | ✅ | ✔️ |
| 10 | scheduler | 1283 | 11 | ✅ | ✔️ |
| 11 | extractor | 1233 | 2 | ✅ | ✔️ |
| 12 | social-bridge | 1220 | 2 | ✅ | ✔️ |
| 13 | youtube-transcripts | 1182 | 7 | ✅ | ✔️ |
| 14 | arxiv | 1177 | 9 | ✅ | ✔️ |
| 15 | ops-discord | 1102 | 2 | ✅ | ✔️ |
| 16 | batch-report | 1088 | 2 | ✅ | ✔️ |
| 17 | github-search | 1051 | 8 | ✅ | ✔️ |
| 18 | hack | 1031 | 7 | ✅ | ✔️ |
| 19 | qra | 1016 | 10 | ✅ | ✔️ |

**COMPLETED: 2026-01-29** - All 19 skills modularized and passing sanity tests.

**Legend**: ⏳ Pending | 🔄 In Progress | ✅ Complete | ⬜ Not Started | ✔️ Passed
