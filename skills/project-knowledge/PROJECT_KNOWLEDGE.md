# Project Knowledge: pi-mono

**Last updated:** 2026-04-21 07:45 by agent (refreshed)
**Status:** Active development

## Current Understanding

- Project initialized, knowledge tracking started

## Recent Decisions

| Date | Decision | Why |
|------|----------|-----|
| 2026-04-12 | Initialize project knowledge | Enable shared human/agent context |

## Open Questions

- [ ] What are the key architectural decisions?
- [ ] What are the known issues?

## Key Files

| File | Purpose |
|------|---------|
| PROJECT_KNOWLEDGE.md | Shared project knowledge |

## Infrastructure State

```
# Embry OS Project State -- 2026-04-21 (quick mode)

## Phase 1: Infrastructure

### Daemons (4/7 up)

| Daemon | Status |
|--------|--------|
| state | OK |
| voice | OK |
| sparta | DOWN |
| memory | OK |
| inference | OK |
| datalake | DOWN |
| discord | DOWN |

### Tests: 419 collected

### 3-Tier Cascade

| Tier | Status |
|------|--------|
| Tier 2 Teacher | MISSING |
| Tier 1 5 Gpt | NOT_TRAINED |
| Tier 0 5 Classifier | NONE |

**Model Registry**: 0V / 0C / 0R / 0G
**Shadow Entries**: 0 usable / 1532 total

### Cascade Wiring: inference-daemon=YES, sparta-daemon=YES, datalake-daemon=YES

### Skills: 269 total
  - 7 dirs without SKILL.md
  - 17 skills without sanity.sh

### Frontend: 52 TSX / 4 Rust
### Deploy: 10 systemd units

### Component Projects (5/5 found)

| Project | Tests | Last Commit | Dirty | Role |
|---------|-------|-------------|-------|------|
| graph-memory | ERR | ee257f2 10 days ago fix: batch-preflight hook excludes file operations on .jsonl | YES (447) | ArangoDB graph store, ToM, recall/learn |
| extractor | 788 | 1b0a9bb3 6 weeks ago fix(s10): guard parents[2] access in sync_to_codebase | YES (560) | PDF/DOCX 3-tier cascade extraction |
| sparta | 558 | 4fd75030 11 days ago fix: chunk CAPEC QRA requests to avoid proxy queue timeout | YES (49) | NIST/D3FEND/ATT&CK compliance pipeline |
| streamdeck | 500 | 2fd85fb 8 weeks ago feat: add health_check.sh for post-crash diagnostics | YES (224) | Stream Deck XL dynamic layout engine |
| pi-mono | n/a | 76c8edcd 5 days ago nightly: safety snapshot before skills-ci-nightly (2026-04-16) | YES (247) | Agent framework, 194+ skills |

## Phase 6: Gap Analysis (4 gaps)

1. **[HIGH]** Tier 1.5 GPT not trained -- needs GPU + 2000+ labels for QLoRA fine-tuning
   Action: Use /create-gpt on local RTX A5000 (24GB VRAM) to train Qwen2.5-1.5B QLoRA from shadow labels
2. **[MEDIUM]** Shadow data: 0/1532 usable (1532 legacy entries)
   Action: Run prime_shadow.py --all --samples 200 to accumulate more usable entries
3. **[MEDIUM]** Daemons down: sparta, datalake, discord
   Action: Start missing daemons with uv run python services/<name>-daemon/main.py
4. **[LOW]** 7 skill dirs without SKILL.md
   Action: Run /skills-ci to audit and fix


```
