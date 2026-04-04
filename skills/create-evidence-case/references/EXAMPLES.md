## Example 1: SATISFIED — Firmware Tampering

Question: "What SPARTA countermeasures protect F-36 flight software from firmware tampering during avionics maintenance windows?"

**Step 1 — Decomposition:**
- Given: F-36 flight software, avionics maintenance windows
- Then: SPARTA countermeasures, firmware tampering

**Step 2 — Per-component recall:**
- "firmware tampering" → 4 QRAs about CM0028 (Tamper Protection) tags=["Harden","Detect"]
- "maintenance windows" → 3 QRAs about SV-MA (Maintenance Access) tags=["Harden"]
- "SPARTA countermeasures" → broad, covered by the above

**Step 3 — Entity extraction:**
- control_ids: [CM0028, SV-MA-4, SI-7]
- related_pairs: [(CM0028, SV-MA-4, "technique_bridge")]

**Step 4 — Same-technique check:**
- CM0028 and SV-MA share "Harden" technique → SAME TECHNIQUE ✓
- T1542.001 appears in BOTH firmware and maintenance recall → bridge confirmed

**Step 5 — Clarify:** Confirms entities are related via SV-AV-7 technique family.

**Step 6 — Lean4 proof:** Formalizes "Harden(firmware) ∧ Harden(maintenance) → Protected(flight_software)". Proof succeeds.

**Step 7 — Verdict: SATISFIED.** Components resolve, same technique bridge confirmed, proof succeeds.

## Example 2: INCONCLUSIVE — FPGA Supply Chain + CMMC

Question: "Given the F-36's use of third-party FPGA vendors, which SPARTA supply chain attack vectors should we prioritize in our CMMC Level 3 compliance audits?"

**Step 1 — Decomposition:**
- Given: F-36, third-party FPGA vendors
- Then: SPARTA supply chain attack vectors, CMMC Level 3 compliance audits

**Step 2 — Per-component recall:**
- "FPGA vendors" → 0 QRAs with FPGA-specific supply chain
- "supply chain attack vectors" → 5 QRAs about IA-0001.02 (Software Supply Chain)
- "CMMC Level 3" → 0 QRAs (framework, not technique)

**Step 3 — Entity extraction:**
- control_ids: [SI-3] (only 1, weak)
- related_pairs: [] (empty — no cross-component bridge)

**Step 4 — Same-technique check:**
- Supply chain QRAs exist but are SOFTWARE supply chain, not HARDWARE (FPGA)
- CMMC Level 3 is a process framework — no SPARTA technique mapping
- Tactical tags scatter: Isolate/Harden/Exploit/Detect/Persist — NO coherent cluster ✗

**Step 5 — Clarify:** Identifies 3 gaps: FPGA hardware chain, CMMC↔SPARTA mapping, HW vs SW distinction.

**Step 6 — Lean4 proof:** Cannot construct theorem — missing FPGA→technique bridge. Proof fails.

**Step 7 — Verdict: INCONCLUSIVE.** Supply chain QRAs exist but don't address FPGA specifically. CMMC L3 mapping needs Tier 3 research.

**Conditional — /dogpile:** Research "FPGA supply chain SPARTA techniques" and "CMMC Level 3 SPARTA mapping" for Tier 3 evidence.

## Stress Test (50-Question Bank)

Run the full 50-question F-36 bank (40 real + 10 adversarial) as agent-driven evidence cases:

```bash
# Generate task file for /orchestrate
./run.sh stress-test

# Limit to first 10 questions
./run.sh stress-test --count 10

# Custom question bank
./run.sh stress-test --questions my_questions.json

# Then run via orchestrate
/orchestrate 01_EVIDENCE_STRESS_TEST_TASKS.md
```

Each question becomes a task where the AGENT follows the full 7-step flow above.
The agent reads grounding evidence and decides — deterministic code only provides evidence.
Adversarial questions test that fabricated entities, misspelled frameworks, and absurd
technology combinations are correctly rejected.

**Convergence criteria:**
- Adversarial false positive rate = 0%
- Real question SATISFIED rate >= 85%
- Every verdict has visible grounding evidence

**Shadow-Lego**: After enough labeled evidence cases exist, train classifiers via `/assistant`
for automated batch mode. The agent-driven path is always the source of truth.

# Compare models on the plausibility prompt
cd ~/.claude/skills/prompt-lab
./run.sh compare \
  --prompt ~/.claude/skills/create-evidence-case/ground_truth/prompts/plausibility_v1.txt \
  --ground-truth ~/.claude/skills/create-evidence-case/ground_truth/plausibility_answerability.json \
  --models "deepseek,text,claude-subagent"

# Find minimum accurate model
./run.sh find-minimum \
  --ground-truth ~/.claude/skills/create-evidence-case/ground_truth/plausibility_answerability.json \
  --threshold 0.95
```

### How It Works

1. `/prompt-lab compare` tests the plausibility prompt across models
2. Winner is written to `ground_truth/prompt_lab_winner.json`
3. `plausibility.py` reads `prompt_lab_winner.json` at runtime
4. If no winner file exists, defaults to: DeepSeek V3 → scillm → OpenRouter → claude -p

### When to Re-Evaluate

- After adding new adversarial questions to the eval set
- After changing the plausibility prompt
- After `/evidence-case-lab` reveals new false positive/negative patterns
- Store results in `/memory learn` for convergence tracking

## Common Mistakes

### WRONG: Regex-parsing control IDs from recall results
```python
import re
ids = re.findall(r'[A-Z]{2}-\d+', result_text)  # fragile regex
```

### RIGHT: Read structured fields from recall results
```python
control_ids = [qra["control_id"] for qra in recall_results]
```

### WRONG: Skipping the same-technique check and auto-passing
```python
if len(recall_results) > 0:
    verdict = "SATISFIED"  # entities exist but may span unrelated domains!
```

### RIGHT: Verify entities from different components share a technique
```python
# Check tactical_tags cluster into 1-2 techniques across components
# Check related_pairs for cross-component edges
# If no shared technique → INCONCLUSIVE
```

### WRONG: Using /memory recall without specifying collections
```bash
.claude/skills/memory/run.sh recall --q "firmware tampering"  # searches everything
```

### RIGHT: Scope recall to sparta_qra collection
```bash
.claude/skills/memory/run.sh recall --q "firmware tampering" --collections sparta_qra --k 10
```

## Standards Alignment

- **CAE** (Adelard): Claims → Arguments → Evidence
- **OSCAL** (NIST): TEST/EXAMINE/COMPUTE methods
- **GSN** (ISO 15026): Goal structuring notation (via /create-gsn-diagram)
- **CMMC** (DoD): Cybersecurity Maturity Model Certification (via /cmmc-assessor)
- **Lean4**: Formal verification of evidence chains (via /lean4-prove)
- **UCT**: Upper Confidence Bound for Trees (strategy selection history)
