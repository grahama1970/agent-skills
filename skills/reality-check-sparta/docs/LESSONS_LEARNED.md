# SPARTA QRA Quality Improvement - Lessons Learned

**Date**: 2026-02-06 (Updated: 2026-02-09)
**Persona**: Brandon Bailey (SPARTA Creator, Aerospace Corporation)
**Grade Achieved**: A+ EXCELLENT

## Summary

Domain expert personas dramatically improve content quality. By implementing Brandon Bailey as a quality reviewer persona with explicit space terminology requirements, we improved QRA quality from **F FAIL to A+ EXCELLENT**.

---

## Session 2026-02-09: Batch Generation Debugging

### Issue: API Key Not Loaded

**Symptom**: Chutes API returning "Missing or invalid authorization header(s)"

**Root Cause**: `.env` file existed but `load_dotenv()` wasn't being called before API calls

**Fix**: Explicitly pass `CHUTES_API_KEY` environment variable when running batch:
```bash
CHUTES_API_KEY="cpk_xxx" \
CHUTES_TEXT_MODEL="deepseek-ai/DeepSeek-V3-0324-TEE" \
python -m sparta.pipeline_duckdb.12_qra --run-id run-recovery-verify
```

**Lesson**: Always verify env vars are loaded. Don't assume `.env` loading happens automatically.

### Issue: Reasoning Models Hang Async Pipeline

**Symptom**: Batch stuck at "Phase 1: Generating simple QRAs" with no progress despite litellm warnings

**Root Cause**: Reasoning models (e.g., `moonshotai/Kimi-K2.5-TEE`) don't play well with `parallel_acompletions_iter` in "tenacious" mode. The extended thinking/reasoning process causes timeouts or hangs.

**Bad Choices**:
- `moonshotai/Kimi-K2.5-TEE` (reasoning model) - HANGS
- `Qwen/Qwen3-235B-A22B-fp8-tee` (very large) - SLOW

**Good Choices**:
- `deepseek-ai/DeepSeek-V3` (non-TEE, fast) - WORKS
- `deepseek-ai/DeepSeek-V3-0324-TEE` (TEE, recommended) - BEST

**Lesson**: For batch QRA generation, use non-reasoning models. Reasoning models are for complex single-query tasks, not high-throughput batch operations.

### Issue: litellm RuntimeWarnings

**Symptom**: Logs flooded with:
```
RuntimeWarning: coroutine 'Logging.async_success_handler' was never awaited
```

**Root Cause**: litellm's internal async logging. This is a benign warning, not a functional issue.

**Fix**: Ignore - these warnings don't affect batch progress or quality.

**Lesson**: Not all warnings indicate problems. Understand the warning source before debugging.

### Best Practice: Model Selection for QRA Batch

| Use Case | Recommended Model | Why |
|----------|-------------------|-----|
| High-throughput batch | DeepSeek-V3-0324-TEE | Fast, reliable, good quality |
| Single complex query | Kimi-K2.5-TEE | Deep reasoning for hard problems |
| Cost-sensitive batch | DeepSeek-V3 (non-TEE) | Faster, cheaper |
| Maximum quality | DeepSeek-V3-0324-TEE | Balance of speed and quality |

### Checkpoint Monitoring

**Best Practice**: Run `reality-check-sparta watch` during long batches:
```bash
./run.sh watch --run-id run-recovery-verify --checkpoint 5000 --samples 20
```

This triggers Brandon Bailey quality review every 5000 QRAs and stops the batch on FAIL.

---

## Results

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Space-Aware QRAs | 11.7% | 81.6% | +69.9% |
| Generic IT QRAs | 88.3% | 18.4% | -69.9% |
| Grade | F FAIL | A+ EXCELLENT | Maximum |
| Total QRAs | 26,446 | 1,105 | Fresh regeneration |
| Avg Grounding | 0.911 | 0.895 | Maintained |

## Key Techniques

### 1. SPACE DOMAIN REQUIREMENT Section

Added mandatory section to all 4 QRA prompts:

```
==============================================================================
SPACE DOMAIN REQUIREMENT (MANDATORY - READ CAREFULLY):
==============================================================================

This is SPARTA - Space Attack Research and Tactic Analysis. ALL content MUST
reflect the SPACE DOMAIN context. Generic IT/cybersecurity language without
space context will be REJECTED.

REQUIRED: Every answer MUST include AT LEAST ONE of these space-specific elements:
1. SPACE SEGMENT CONTEXT: Ground segment, link segment, or space segment
2. SPACE ASSETS: Satellite, spacecraft, payload, bus, ground station, mission control
3. SPACE COMMUNICATIONS: RF, SATCOM, uplink, downlink, telemetry, tracking, command (TT&C)
...
```

### 2. IT-to-Space Mapping

Created explicit mappings for MITRE ATT&CK techniques:

| IT Domain | Space Mapping |
|-----------|---------------|
| Cloud/web attacks | Ground segment: mission operations centers, ground station cloud infrastructure |
| Network attacks | Link segment: SATCOM links, RF communication channels, ground-to-space networks |
| Software/system attacks | Space segment: spacecraft flight software, satellite operating systems |
| Credential/identity attacks | All segments: TT&C authentication, ground station operator access |
| Data exfiltration | Telemetry channels, downlink encryption, spacecraft memory |

### 3. NO EXCEPTIONS Enforcement

Added explicit enforcement clause:

```
CRITICAL: Even if the technique is from MITRE ATT&CK (generic IT), your answer
MUST explain how it applies to space systems. NO EXCEPTIONS.
```

## Grading Scale

| Grade | Threshold | Description |
|-------|-----------|-------------|
| A+ EXCELLENT | <20% generic | Brandon approves for production |
| A GOOD | 20-30% generic | Minor improvements needed |
| B ACCEPTABLE | 30-50% generic | Significant work required |
| C NEEDS WORK | 50-70% generic | Major revision needed |
| F FAIL | >70% generic | Rejected - not space-aware |

## Required Space Terminology

Every answer must include at least one of:

- **Space Segment Context**: Ground segment, link segment, space segment
- **Space Assets**: Satellite, spacecraft, payload, bus, ground station, mission control
- **Space Communications**: RF, SATCOM, uplink, downlink, telemetry, TT&C
- **Space Threats**: Jamming, spoofing, signal interference, ASAT
- **Space Standards**: CCSDS, SpaceWire, MIL-STD
- **Mission Context**: LEO/MEO/GEO, constellation, space vehicle

## Lessons Learned

1. **Generic IT prompts produce generic IT content** - even when explicitly about space systems
2. **Explicit domain terminology requirements are essential** - the model follows instructions
3. **IT-to-Space mapping helps adapt MITRE ATT&CK** - provides clear transformation rules
4. **Persona-driven quality review catches domain-specific issues** - Brandon asks the right questions
5. **Grading scale provides clear targets** - A+ gives everyone a goal
6. **Fresh regeneration may be needed** - existing QRAs won't auto-update

## Files Modified

### QRA Prompts (12_qra.py)
- `SPARTA_SYSTEM_PROMPT` (line 318)
- `RELATIONSHIP_SYSTEM_PROMPT` (line 439)
- `SIMPLE_SYSTEM_PROMPT` (line 564)
- `TACTIC_CONTROL_PROMPT` (line 690)

Path: `${HOME}/workspace/experiments/sparta/src/sparta/pipeline_duckdb/12_qra.py`

## Brandon Bailey Persona Files

- `BRANDON_BAILEY_PERSONA.md` - Full persona definition
- `brandon_bailey_persona.yaml` - Create-persona manifest

Path: `${HOME}/workspace/experiments/memory/.agents/skills/reality-check-sparta/`

## Recommended Batch Configuration

For production QRA batch generation:

```bash
# Recommended environment
CHUTES_API_KEY="cpk_xxx"
CHUTES_TEXT_MODEL="deepseek-ai/DeepSeek-V3-0324-TEE"
STAGE12_BATCH_SIZE=50
QRA_CONCURRENCY=6

# Run with exhaustive mode for complete coverage
python -m sparta.pipeline_duckdb.12_qra \
  --run-id run-recovery-verify \
  --exhaustive \
  --max-pairs 50000

# In parallel terminal, monitor with Brandon review
cd ${HOME}/workspace/experiments/pi-mono/.pi/skills/reality-check-sparta
./run.sh watch --run-id run-recovery-verify --checkpoint 5000 --samples 20
```

## QRA Error Identification Checklist

Brandon Bailey should check for these quality issues:

### 1. Space Domain Violations
- [ ] Generic IT language without space context
- [ ] Missing segment context (ground/link/space)
- [ ] No space-specific assets mentioned
- [ ] MITRE ATT&CK techniques not mapped to space systems

### 2. Grounding Issues
- [ ] Answers not matching source text (hallucination)
- [ ] Citations to wrong documents
- [ ] Grounding score below 0.7 threshold

### 3. Structure Issues
- [ ] Empty or null answers
- [ ] Orphan QRAs (no relationship to control)
- [ ] Duplicate questions

### 4. Batch Generation Issues
- [ ] Stalled progress (no new QRAs for >10 minutes)
- [ ] API rate limiting (check Chutes dashboard)
- [ ] Model timeouts (switch to non-reasoning model)

## Future Work

1. **Backup before truncation** - Always export old QRAs for contrastive training
2. **Automate persona-based review** - Integrate Brandon into CI/CD pipeline
3. **Extend to other domain experts** - Create personas for other SPARTA stakeholders
4. **Store lessons in memory** - Use `/memory` skill for persistent storage
5. **Add model selection heuristics** - Auto-detect when reasoning models are causing issues
6. **Integrate with /ops-chutes** - Health check before starting batch

## Related Skills

| Skill | Usage |
|-------|-------|
| `/reality-check-sparta` | Runs Brandon Bailey quality assessment |
| `/create-persona` | Registers Brandon as formal persona |
| `/prompt-lab` | Optimizes prompts based on Brandon's criteria |
| `/memory` | Stores lessons learned |
