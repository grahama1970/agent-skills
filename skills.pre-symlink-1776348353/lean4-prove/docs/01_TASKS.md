# Lean4 Prove Skill - Task List

## Context

DeepSeek Prover V2 is dead on all serverless providers. We're building a self-contained skill that:
- Takes a requirement + tactics + persona
- Generates N proof candidates via LLM (configurable model)
- Compiles each in lean_runner Docker container
- Retries with error feedback up to max N times
- Returns successfully compiled theorem or failure diagnosis

## Prerequisites

- [ ] Verify `lean_runner` Docker container exists and works
- [ ] Verify `OPENROUTER_API_KEY` is set in environment

---

## Task 1: Create skill structure

**Description:** Set up the lean4-prove skill directory with entry points.

**Files to create:**
- `run.sh` - Bash entry point that calls prove.py
- `prove.py` - Main Python implementation
- `SKILL.md` - Agent-readable documentation
- `sanity.sh` - Health check script

**Definition of Done:**
```bash
ls -la /home/graham/workspace/experiments/pi-mono/.pi/skills/lean4-prove/
# Shows: run.sh, prove.py, SKILL.md, sanity.sh
```

---

## Task 2: Implement prove.py core logic

**Description:** Python script (~150 lines) with:
- LLM client using litellm (supports OpenRouter, Anthropic, OpenAI)
- System prompt builder with persona + tactics
- Candidate generation (N proofs per attempt)
- Docker compilation via subprocess
- Retry loop with error feedback
- JSON output

**Interface:**
```python
def prove(
    requirement: str,
    tactics: list[str] = None,
    persona: str = None,
    max_retries: int = 3,
    candidates: int = 3,
    model: str = None,
    container: str = "lean_runner",
    timeout: int = 120,
) -> dict
```

**Definition of Done:**
```bash
echo '{"requirement": "Prove n + 0 = n"}' | python prove.py
# Returns JSON with success/failure
```

---

## Task 3: Implement run.sh entry point

**Description:** Bash wrapper that:
- Parses CLI arguments (--requirement, --tactics, --persona, etc.)
- Calls prove.py with proper arguments
- Handles stdin JSON input as alternative

**Interface:**
```bash
./run.sh --requirement "Prove n + 0 = n" --tactics "simp,ring" --persona "mathematician"
# OR
echo '{"requirement": "..."}' | ./run.sh
```

**Definition of Done:**
```bash
./run.sh --help
# Shows usage with all options
```

---

## Task 4: Write SKILL.md documentation

**Description:** Agent-readable documentation covering:
- Purpose and capabilities
- Input/output format
- Environment variables required
- Example usage
- Error handling

**Definition of Done:**
```bash
head -50 SKILL.md
# Shows clear documentation
```

---

## Task 5: Implement sanity.sh health check

**Description:** Verify:
1. Docker is available
2. lean_runner container is running
3. Lean4 is installed in container
4. LLM API key is set
5. Trivial proof compiles

**Definition of Done:**
```bash
./sanity.sh
# Output: Result: PASS (or clear failure message)
```

---

## Task 6: Test full workflow

**Description:** End-to-end test with:
- Simple proof: "Prove n + 0 = n"
- Medium proof: "Prove sum of first n integers"
- Proof with persona: "As a cryptographer, prove message integrity"
- Failure case: Invalid requirement

**Definition of Done:**
```bash
./run.sh --requirement "Prove n + 0 = n" --tactics "rfl" | jq .success
# Returns: true
```

---

## Task 7: Deprecate old Certainly/scillm integration

**Description:** Update memory project to:
- Remove or deprecate scillm/prove.py
- Update SCILLM_PAVED_PATH_CONTRACT.md
- Update proof_assessment.py to use new skill or remove Tier 2
- Remove dead Prover V2 references from sanity.sh

**Files to update:**
- `/home/graham/workspace/experiments/memory/.agents/skills/scillm/prove.py`
- `/home/graham/workspace/experiments/memory/.agents/skills/scillm/sanity.sh`
- `/home/graham/workspace/experiments/memory/.agents/skills/scillm/docs/SCILLM_PAVED_PATH_CONTRACT.md`
- `/home/graham/workspace/experiments/memory/src/graph_memory/integrations/proof_assessment.py`

**Definition of Done:**
```bash
grep -r "deepseek-prover-v2" /home/graham/workspace/experiments/memory/src/
# Returns: no matches (or only in comments noting deprecation)
```

---

## Environment Variables

```bash
# Required
OPENROUTER_API_KEY=sk-or-...

# Optional (with defaults)
LEAN4_PROVE_MODEL=anthropic/claude-sonnet-4
LEAN4_CONTAINER=lean_runner
LEAN4_TIMEOUT=120
LEAN4_MAX_RETRIES=3
LEAN4_CANDIDATES=3
```

---

## Dependencies

```
litellm>=1.0.0
python-dotenv>=1.0.0
```

No scillm dependency. Direct litellm for simplicity.

