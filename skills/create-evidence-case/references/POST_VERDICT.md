## POST-VERDICT: QRA Quarantine + Human Review

After the verdict, evidence cases can generate new knowledge for the corpus.

### SATISFIED → Candidate QRA

When the verdict is SATISFIED, the evidence case produces a synthesized answer grounded in real QRAs. This becomes a **candidate QRA** for human review:

```python
from runner import quarantine_as_candidate_qra

result = quarantine_as_candidate_qra(
    question="What SPARTA countermeasures protect...",
    answer="CM0028 (Tamper Protection) addresses T1542.001...",
    case_result=case_result,
    evidence_items=qra_items,
)

## Plausibility Prompt Optimization (via /prompt-lab)

The plausibility gate (Step 3 answerability check) uses an LLM to decide whether
a question is answerable from the corpus. The prompt and model are optimized via
`/prompt-lab`, NOT hand-tuned.

### Eval Fixtures

`ground_truth/plausibility_answerability.json` — 36 labeled cases:
- 6 false rejects (plausibility LLM wrongly said not answerable)
- 10 adversarial FPs (should have been caught as not answerable)
- 10 true positives + 10 true negatives for balance

### Running the Eval

```bash
