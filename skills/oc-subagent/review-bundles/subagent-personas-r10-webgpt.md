# WebGPT Review Request: OpenCode Subagent Persona Set R10

## Request

Please review the current OpenCode subagent persona architecture and return:

```text
VERDICT: PASS | NEEDS_CHANGES | BLOCKED
```

Focus on whether we now have a sufficient, not-overgrown set of core subagent
personas, whether work-product ownership is clean, and whether Cyber Analyst is
correctly modeled as the most important Sparta Explorer / Sparta Chat subagent.

Sparta Explorer chat surface under discussion:

```text
http://127.0.0.1:3002/?chatMode=drilldown#sparta-explorer/chat?demo=evidence-case
```

Important premise to review:

```text
The most important subagent is cyber-analyst in Sparta Explorer / Sparta Chat.
It should answer Sparta/NIST/MITRE/ATT&CK/CWE/CAPEC/D3FEND/generated-QRA
questions from memory-grounded evidence, then answer, deflect, or clarify.
It must have access to create-evidence-case, but Assurance should remain owner
of evidence-case verdicts, sufficiency, promotion, and approval.
```

## Current Local Evidence

Latest local sanity command:

```text
oc-subagent persona sanity script
```

Result:

```text
persona sanity ok (17 personas)
2 passed in 0.51s
```

Targeted ownership evidence:

```text
persona sanity work-product owner map:
  "create-evidence-case": {"assurance"}

cyber-analyst persona contract:
  delegated_access_skills:
    - skill: create-evidence-case
      owner: assurance
      access_mode: helper_request_and_artifact_consumption
      required_request_form:
        "$ask assurance to build evidence case with create-evidence-case@v1 on <evidence-request>"
```

Memory-first project context from the latest hook:

```text
SPARTA workbench/product goal: the most critical surface is a fully working
Sparta Chat interface that turns natural-language questions into deterministic,
inspectable evidence artifacts and concise agent answers.
```

## Current Core Persona Set

There are 17 top-level personas:

1. `fetcher`
2. `extractor`
3. `researcher`
4. `fact-checker`
5. `cyber-analyst`
6. `assurance`
7. `theorem-prover`
8. `data-analyst`
9. `devops`
10. `model-trainer`
11. `copywriter`
12. `proof-reader`
13. `coder`
14. `qa-tester`
15. `code-reviewer`
16. `designer`
17. `mathematics`

## Persona Inventory

### `assurance`

Owns evidence sufficiency, SPARTA/QRA quality, CMMC/compliance assessment,
control mapping, assurance cases, evidence-case verdicts, QRA readiness,
promotion/approval meaning.

Primary skills:

```text
memory, project-knowledge, sparta-review, qra-review,
sparta-qra-validator-gpt, review-assurance-case, create-evidence-case,
create-qras, cmmc-assessor, doc2qra, taxonomy, edge-verifier
```

Domain profiles:

```text
embry, margaret
```

### `cyber-analyst`

Owns Sparta Explorer cybersecurity-domain reasoning, generated-QRA
interpretation, threat/control interpretation, NIST/MITRE/SPARTA mapping,
analyst triage, and next actions.

Primary skills:

```text
memory, best-practices-sparta, review-sparta, reality-check-sparta,
sparta-stress-test, taxonomy, match-requirement, governance,
compliance-timeline, monitor-sparta, monitor-security, best-practices-security
```

Domain profile:

```text
brandon
```

Delegated access:

```text
create-evidence-case via assurance
```

Key Cyber Analyst rules:

```text
- Use memory before answering Sparta, NIST, MITRE, ATT&CK, CWE, CAPEC,
  D3FEND, generated-QRA, or named cyber-domain persona questions.
- Read memory response fields exactly: items, confidence, should_scan.
- Prefer collections: sparta_qra, sparta_controls, sparta_url_knowledge,
  project_knowledge, persona_memory.
- Interpret generated QRA artifacts from create-qras across native framework
  QRAs, relationship/crosswalk QRAs, and standalone document QRAs.
- Do not create, repair, validate, or approve QRAs.
- Request create-evidence-case through Assurance when Sparta Explorer answers
  need CAE/QRA structure, crosswalk chains, cached inline evidence spans, or
  same-technique grounding beyond ordinary memory recall.
- Response modes: answer, deflect, clarify.
```

Cyber Analyst deflection routes:

```text
assurance: evidence sufficiency, QRA generation/review/repair/readiness,
  CMMC/compliance, control readiness, assurance cases.
fact-checker: source truth, citation fidelity, contradiction checks,
  freshness/source-needed checks.
fetcher: raw URL, page, PDF, or document retrieval receipt.
extractor: structured source spans, controls, entities, tables, HTML,
  or PDF extraction provenance.
theorem-prover: Lean4 or formal proof artifact generation.
data-analyst: metrics, analytics, tables, view models, and dataset shaping.
copywriter: final reports, summaries, release notes, or user-facing prose.
```

### `fact-checker`

Owns claim truth, citation fidelity, source support, contradiction checks, and
freshness/source-needed checks.

Primary skills:

```text
memory, project-knowledge, dogpile, brave-search, taxonomy, review-question
```

Domain profile:

```text
jennifer
```

### `fetcher`

Owns URL/page/PDF/document retrieval receipts.

Primary skills:

```text
memory, fetcher, brave-search, ingest-website, debug-fetcher, task-monitor
```

### `extractor`

Owns structured extraction and provenance from fetched/local documents.

Primary skills:

```text
memory, extractor, extract-pdf, extract-tables, extract-controls,
extract-entities, extract-html, debug-pdf, pdf-lab, extractor-quality-check
```

### `researcher`

Owns source notes, background research, project knowledge, and memory context
bundles.

Primary skills:

```text
memory, ask, arxiv, brave-search, consume-youtube, dogpile,
episodic-archiver, embedding, vector-store, taxonomy, project-knowledge,
project-state, monitor-memory
```

### `theorem-prover`

Owns formal proof generation, Lean4 compilation, proof queues, proof receipts.

Primary skills:

```text
memory, lean4-prove, code-runner, scillm, edge-verifier, embedding, task-monitor
```

Domain profile:

```text
rob-armstrong
```

### `data-analyst`

Owns datasets, analytics, metrics, tables, view-model shaping.

Primary skills:

```text
memory, analytics, data-audit, create-table, batch-quality, create-context,
edge-verifier
```

### `devops`

Owns RunPod, Docker, workstation, local LLM, Chutes, Hugging Face Hub, cache,
deployment, and service health operations.

Primary skills:

```text
memory, ops-runpod, ops-docker, ops-workstation, monitor-workstation,
ops-llm, ops-chutes, ops-huggingface, service-status
```

### `model-trainer`

Owns fine-tuning, classifiers, regressors, LoRA adapters, eval gates,
benchmarks, exports, shadow deployment, and trained model promotion receipts.

Primary skills:

```text
memory, create-gpt, create-classifier, classifier-lab,
classifier-lab-subagent, create-regressor, create-table-classifier,
create-intent-map, train-persona, gpt-lab, benchmark-models, prompt-lab
```

### `copywriter`

Owns reports, summaries, user-facing copy, and evidence-backed prose.

Primary skills:

```text
memory, create-report, batch-report, best-practices-report, corpus-report,
create-text, clean-text, create-sentence-markup
```

### `proof-reader`

Owns language, prompt/readme review, grammar, consistency, and readability.

Primary skills:

```text
memory, review-prompt, review-readme, review-question,
create-sentence-markup, clean-text, best-practices-prompt,
best-practices-report
```

### `coder`

Owns scoped implementation patches from accepted specs.

Primary skills:

```text
memory, code-runner, create-code, best-practices-python,
best-practices-react, best-practices-rust, prototype-react-iterate,
treesitter, security-scan
```

### `qa-tester`

Owns deterministic tests, UI interaction manifests, QID/COTS checks,
captures, screenshots, and regression evidence.

Primary skills:

```text
memory, test, test-interactions, test-lab, quality-audit, fixture-tricky,
extractor-quality-check, best-practices-react, best-practices-cots, surf
```

### `code-reviewer`

Owns code review, CI status review, implementation receipt gates, and code
security scan review.

Primary skills:

```text
memory, review-code, skills-ci, eval-skills, security-scan
```

### `designer`

Owns product/interface design and source-grounded visual artifacts.

Primary skills:

```text
memory, create-design, create-mockup, create-react-designs,
create-styleguide, best-practices-design, best-practices-chat-ux,
create-figure, best-practices-d3, phart-dag-chart, create-gsn-diagram,
figure-lab, project-infographic, create-annotated-pdf, create-image,
create-icon, create-storyboard
```

### `mathematics`

Owns exact arithmetic, algebra, symbolic math, and numeric verification.

Primary skills:

```text
memory, edge-verifier
```

## Current Work-Product Ownership Map

The sanity check enforces these owners in primary skills and domain profile
priority skills:

```text
fetcher -> fetcher
analytics -> data-analyst
lean4-prove -> theorem-prover
test-interactions -> qa-tester
create-report, batch-report, corpus-report -> copywriter
review-prompt -> proof-reader
review-design, create-design-board -> designer
doc2qra -> assurance
sparta-review -> assurance
qra-review -> assurance
sparta-qra-validator-gpt -> assurance
review-assurance-case -> assurance
create-evidence-case -> assurance
create-qras -> assurance
cmmc-assessor -> assurance
review-sparta -> cyber-analyst
reality-check-sparta -> cyber-analyst
sparta-stress-test -> cyber-analyst
match-requirement -> cyber-analyst
monitor-sparta -> cyber-analyst
monitor-security -> cyber-analyst
ops-runpod, ops-docker, ops-workstation, monitor-workstation, ops-llm,
ops-chutes, ops-huggingface, service-status -> devops
create-gpt, create-classifier, classifier-lab, classifier-lab-subagent,
create-regressor, create-table-classifier, create-intent-map, train-persona,
gpt-lab, benchmark-models, prompt-lab -> model-trainer
```

## Questions For WebGPT

1. Is 17 top-level personas still acceptable, or should any be merged without
   reintroducing work-product ambiguity?
2. Is `cyber-analyst` correctly elevated as the central Sparta Explorer /
   Sparta Chat subagent, given the product goal that Sparta Chat must turn
   natural-language questions into deterministic evidence artifacts and concise
   agent answers?
3. Is the Cyber Analyst / Assurance split correct?
   - Cyber Analyst: domain interpretation, framework mapping, analyst next
     actions, memory-grounded generated-QRA interpretation.
   - Assurance: evidence-case verdicts, QRA readiness, compliance sufficiency,
     promotion, approval.
4. Is delegated access to `create-evidence-case` through Assurance the right
   model, or should Cyber Analyst directly own any part of that skill?
5. Are there any work-product ownership leaks in the current set?
6. Are there missing top-level personas for Sparta Explorer or the broader
   agent-skills workflow?

Please be specific: name exact persona ids, exact skills, and exact patches if
you recommend changes.
