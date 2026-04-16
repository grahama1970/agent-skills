# Brandon/Embry Persona - Handoff Context

**Date:** 2026-02-08
**Status:** Classifier integrated, ready for testing

**Path placeholders:**
- `$REPO_ROOT`: repository root
- `$WORKSPACE_ROOT`: workspace root containing this repo
- `$HOME`: user home directory


## What Was Accomplished

### 1. Space Classifier (DistilBERT)
- **Location:** `$REPO_ROOT/.pi/skills/create-classifier/models/space_classifier_distilbert/best_model`
- **Training:** 11,700 samples, 100% accuracy on validation
- **Purpose:** Pre-filter queries as `space_cybersecurity` vs `generic_it`
- **Wrapper:** `$REPO_ROOT/.pi/skills/memory/space_classifier.py`

### 2. Intent Mapper (Ollama)
- **Model:** `qwen2.5-coder:7b-instruct` (non-reasoning model - critical!)
- **Location:** `$REPO_ROOT/.pi/skills/memory/intent_mapper.py`
- **Purpose:** Convert queries to QuerySpec JSON for SPARTA retrieval
- **Accuracy:** 83% on test queries
- **Key Fix:** Double-braced JSON examples in prompt template (escaping for `.format()`)

### 3. QRA Retrieval (DuckDB)
- **Database:** `$WORKSPACE_ROOT/sparta/data/runs/run-recovery-verify-8k-backup-20260205_193440/backups/sparta_2540qras_20260205_131019.duckdb`
- **Total QRAs:** 2,540
- **Wrapper:** `$REPO_ROOT/.pi/skills/memory/qra_retrieval.py`

### 4. Brandon Simulacrum Integration
- **Location:** `$REPO_ROOT/.pi/skills/memory/brandon_simulacrum.py`
- **Persona:** Embry (Brandon Bailey's intern at Aerospace Corp)
- **Architecture:**
  ```
  Query → Classifier (pre-filter) → Intent Mapper (QuerySpec) → DuckDB (QRAs) → Grounding Gate (0.7) → Embry Response
  ```

### 5. Reality-Check-SPARTA Classifier Integration
- **New file:** `$REPO_ROOT/.pi/skills/reality-check-sparta/classifier_validation.py`
- **Integration:** Added to `check.py` as `classifier_validation` check
- **Purpose:** ML-based detection of generic IT content in QRAs

## Current Blockers

### Transformers Version
- Model trained with `transformers==5.1.0`
- Required reinstall: `pip install --break-system-packages transformers==5.1.0`
- Also required: `pip install --break-system-packages --force-reinstall torch torchvision`
- **Warning:** Creates dependency conflicts with `sentence-transformers` (wants <5.0.0)

### Reality-Check-SPARTA Test Pending
The full assessment with classifier hasn't completed yet. Command to run:
```bash
cd $REPO_ROOT/.pi/skills/reality-check-sparta
python check.py \
  --db $WORKSPACE_ROOT/sparta/data/runs/run-recovery-verify-8k-backup-20260205_193440/backups/sparta_2540qras_20260205_131019.duckdb \
  --run-id brandon-with-classifier \
  --samples 30 \
  --json
```

## Files Created/Modified

### New Files
| File | Purpose |
|------|---------|
| `.pi/skills/memory/space_classifier.py` | DistilBERT classifier wrapper |
| `.pi/skills/memory/intent_mapper.py` | Ollama QuerySpec generator |
| `.pi/skills/memory/qra_retrieval.py` | SPARTA DuckDB search |
| `.pi/skills/memory/brandon_gate.py` | 0.7 grounding threshold gate |
| `.pi/skills/memory/scope_enforcement.py` | Out-of-scope handler |
| `.pi/skills/memory/brandon_audit.py` | Session logging |
| `.pi/skills/memory/brandon_simulacrum.py` | Main integration script |
| `.pi/skills/memory/BRANDON_INTERN_PERSONA.md` | Embry character definition |
| `.pi/skills/reality-check-sparta/classifier_validation.py` | ML-based QRA validation |

### Modified Files
| File | Change |
|------|--------|
| `.pi/skills/reality-check-sparta/check.py` | Added classifier validation import and check |

## Key Lessons Learned

1. **Non-reasoning models for JSON generation**: `qwen3:8b` has thinking mode that breaks JSON output. Use `qwen2.5-coder:7b-instruct` instead.

2. **Prompt template escaping**: JSON examples in Python f-strings or `.format()` need double braces `{{` `}}` to avoid KeyError.

3. **Canonical skill location**: ALL skills go in `$REPO_ROOT/.pi/skills/` - NOT in `$WORKSPACE_ROOT/memory/.agents/skills/`.

4. **Transformers compatibility**: Models saved with transformers 5.x need transformers 5.x to load.

## Next Steps

1. **Run full reality-check-sparta assessment** with classifier validation
2. **Address QRA structure issues** (1759 orphan QRAs found in previous assessment)
3. **Test end-to-end Brandon persona** with all components integrated
4. **Federated Taxonomy bridge integration** (from SEAL plan)

## Test Commands

```bash
# Test classifier
cd $REPO_ROOT/.pi/skills/memory
python space_classifier.py "How do I detect RF jamming attacks?"

# Test intent mapper (requires Ollama running)
python intent_mapper.py "What controls protect satellite uplinks?"

# Test QRA retrieval
python qra_retrieval.py "jamming"

# Test full simulacrum
python brandon_simulacrum.py --query "How do I detect command injection in uplink?"

# Test classifier validation module
cd $REPO_ROOT/.pi/skills/reality-check-sparta
python -c "from classifier_validation import classifier_status; print(classifier_status())"
```

## Related Plan

Full SEAL training pipeline plan at: `$HOME/.claude/plans/cheeky-sauteeing-fox.md`
