# Dataset and study contract

Every line is one `Record` from `src/ai_detection/dataset.py`. The supplied example
is deliberately synthetic. Never promote its role labels into human ground truth.

```json
{"sample_id":"study-001","session_id":"session-001","task_id":"task-001","author_id":"participant-001","repository_id":"task-set-001","split":"train","language":"python","source":"def solve(value):\n    return value + 1\n","label":"human","model_family":null,"origin":"synthetic","provenance_ref":"FORMAT_EXAMPLE_ONLY_NOT_A_HUMAN_SAMPLE","collected_at":"2026-09-17T00:00:00+00:00"}
```

## Admitted labels and provenance

`label` is human, machine, hybrid or unknown. `origin` is real or synthetic.
Machine/hybrid examples must declare a generator family; human examples must not.
The loader refuses synthetic examples unless `--allow-synthetic` is explicit.
Mixed/unknown labels are excluded from binary metrics and counted, never silently
relabeled as machine. Timestamp and identity fields are required; provenance is
recorded as declared and not independently verified.

A public dataset's old “human” column is not sufficient proof that a current
assessment population is represented. Review licenses, collection methodology,
contamination, permitted aids and ground-truth confidence before admitting it.
No external benchmark data or model weights were bundled or silently downloaded.

## Four independent splits

**Train:** fit the feature scaler and classifier.
**Tune:** choose a fixed score threshold using separate labels.
**Calibration:** certify that frozen threshold on independent human sessions.
**Test:** measure unseen model families and report per-family results.

The audit rejects cross-split reuse of session, author, task, repository, exact
source and normalized-token source. Final-test model families must not occur in
train, tune or calibration. Renaming and literal changes alone cannot create an
independent normalized-code test example. A chronological holdout is measured;
the efficacy request can require it.

The code does not create trustworthy split IDs for you. Imported corpora without
reliable author or repository relationships cannot honestly receive invented
unique IDs merely to pass the gate. Record the missing information and keep the
real-world claim unqualified.

## Statistical units

Multiple records in a session aggregate to its maximum score, so fragment scanning
does not hide a per-session false-positive problem. Threshold qualification uses
a one-sided exact binomial upper bound on human-session false positives. Zero
errors on ten sessions is not persuasive evidence of a 1% limit.

The optional efficacy gate replays the frozen corpus, checks the calibration,
requires a chosen number of held-out families/human sessions, and checks test FPR
and each family's TPR using Bonferroni-adjusted one-sided bounds. It rejects repeated
declared human authors across calibration/test sessions rather than assuming
those are independent. Independence and representative sampling still require
study review, not just software checks. `min_tpr` is an explicit owner-selected
study requirement; the example 0.5 is illustrative, not a scientifically established
or product-approved operating point.

## Needed real study

Collect consented unaided sessions, allowed non-generative-tool sessions,
AI-generated solutions, human-edited AI solutions and mixed-authorship examples.
Separate accommodations/input workflows from authorship labels. Pre-register
false-positive limits and operating targets, include author/task/repository/time
holdouts, and retain evidence of the actual tools allowed in each session.

The project records a research basis for multilingual, mixed-authorship, and
unseen-generator evaluation, but implements binary Python scoring only. Temporal
model drift, line-level authorship, semantic clone filtering and large-scale dataset
adapters remain next-stage work.
