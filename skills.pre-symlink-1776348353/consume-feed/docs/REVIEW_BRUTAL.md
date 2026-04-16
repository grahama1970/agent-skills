# Code Review Request: Consume Feed Skill (Brutal)

**Title**: Brutal 2-round assessment of consume-feed skill
**Objective**: Look for any aspirational, over-engineered, or brittle features. Focus on reliability and well-written code.
**Acceptance Criteria**:

- Robustness across network failures verified.
- Efficient state management (ETags/Last-Modified).
- Clean ArangoDB integration reusing the Memory skill connection.
- No "bespoke" or "hacked" storage wrappers.

## Files for Review

### Core

- [.pi/skills/consume-feed/cli.py](file:///home/graham/workspace/experiments/pi-mono/.pi/skills/consume-feed/cli.py)
- [.pi/skills/consume-feed/config.py](file:///home/graham/workspace/experiments/pi-mono/.pi/skills/consume-feed/config.py)
- [.pi/skills/consume-feed/storage.py](file:///home/graham/workspace/experiments/pi-mono/.pi/skills/consume-feed/storage.py)
- [.pi/skills/consume-feed/runner.py](file:///home/graham/workspace/experiments/pi-mono/.pi/skills/consume-feed/runner.py)

### Sources

- [.pi/skills/consume-feed/sources/base.py](file:///home/graham/workspace/experiments/pi-mono/.pi/skills/consume-feed/sources/base.py)
- [.pi/skills/consume-feed/sources/rss.py](file:///home/graham/workspace/experiments/pi-mono/.pi/skills/consume-feed/sources/rss.py)

### Utilities

- [.pi/skills/consume-feed/util/http.py](file:///home/graham/workspace/experiments/pi-mono/.pi/skills/consume-feed/util/http.py)
- [.pi/skills/consume-feed/util/dedupe.py](file:///home/graham/workspace/experiments/pi-mono/.pi/skills/consume-feed/util/dedupe.py)
- [.pi/skills/consume-feed/util/text.py](file:///home/graham/workspace/experiments/pi-mono/.pi/skills/consume-feed/util/text.py)

### Metadata

- [.pi/skills/consume-feed/pyproject.toml](file:///home/graham/workspace/experiments/pi-mono/.pi/skills/consume-feed/pyproject.toml)
- [.pi/skills/consume-feed/SKILL.md](file:///home/graham/workspace/experiments/pi-mono/.pi/skills/consume-feed/SKILL.md)
- [.pi/skills/consume-feed/run.sh](file:///home/graham/workspace/experiments/pi-mono/.pi/skills/consume-feed/run.sh)
- [.pi/skills/consume-feed/walkthrough.md](file:///home/graham/workspace/experiments/pi-mono/.pi/skills/consume-feed/walkthrough.md)

---

## Instructions to Reviewer

Be **BRUTAL**. Identify any parts where I am being "too clever" or making assumptions that will break in production. Check for:

1. **Concurrency issues** in the ThreadPoolExecutor.
2. **Resource leaks** (HTTP client sessions, Arango connections).
3. **Data Loss risks** in the upsert/checkpoint logic.
4. **Verbosity/Bloat**: Are there unnecessary abstractions?
5. **Sanity Tests**: Are the mock tests actually testing what they claim?

Round 1: Initial critique.
Round 2: Hardening and refinement.
