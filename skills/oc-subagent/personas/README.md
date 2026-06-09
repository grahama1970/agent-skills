# oc-subagent personas

Each worker persona is an explicit artifact. Transport DAG receipts and UI
panels should attach a concrete persona file by `id`, not rely only on a display
label.

The project agent is the planner, router, join-gate validator, and final judge.
It should not directly own work-product skills when a persona owns that work.
Personas are intentionally few and named by stable job function, not by every
available skill. Skills remain capabilities loaded through skills syntax.

## Layout

```text
personas/
  <id>/
    persona.yaml     authoritative persona contract
    pyproject.toml   persona-specific runtime/tool dependencies
protocols/
  <id>.<version>.yaml shared runtime protocol contracts referenced by personas
```

## Core Router Set

| Persona | Owns | Priority skills |
| --- | --- | --- |
| `memory` | Complex recall, workspace inventory reconciliation, durable memory write planning, collection routing, source/identity deduplication, graph/ToM linkage planning, and receipt-backed memory updates | `memory`, `embedding`, `vector-store`, `taxonomy`, `edge-verifier`, `project-knowledge` |
| `fetcher` | URL, page, PDF, and document retrieval receipts | `memory`, `fetcher`, `brave-search`, `debug-fetcher` |
| `extractor` | Structured extraction from fetched/local documents, including PDF convergence | `memory`, `extractor`, `extract-pdf`, `extract-tables`, `pdf-lab`, `extract-controls` |
| `doc-extractor` | Source-prep section JSONL, raw/clean alignment, cleanup notes, alias repair candidates, and section validation | `memory`, `extractor` |
| `doc-qra` | Document summaries, grounded QRA pairs, doc2qra validation, and memory storage receipts | `memory`, `doc2qra` |
| `researcher` | Source notes, background research, project knowledge, and memory context bundles | `memory`, `project-knowledge`, `dogpile`, `ask`, `arxiv`, `taxonomy` |
| `fact-checker` | Claim truth, citation fidelity, source support, contradiction checks, and freshness/source-needed checks | `memory`, `dogpile`, `brave-search`, `project-knowledge`, `taxonomy`, `review-question` |
| `cyber-analyst` | Sparta Explorer cybersecurity reasoning, memory-grounded generated-QRA interpretation, threat/control interpretation, NIST/MITRE/SPARTA mapping, and analyst next actions | `memory`, `best-practices-sparta`, `review-sparta`, `reality-check-sparta`, `taxonomy`, `match-requirement`, `monitor-sparta`, `monitor-security` |
| `assurance` | Evidence sufficiency, SPARTA/QRA quality, CMMC/compliance assessment, control mapping, and assurance cases | `memory`, `sparta-review`, `qra-review`, `doc2qra`, `create-evidence-case`, `create-qras`, `cmmc-assessor` |
| `theorem-prover` | Formal proof generation, Lean4 compilation, proof queues, and proof artifact receipts | `memory`, `lean4-prove`, `code-runner`, `scillm`, `edge-verifier` |
| `data-analyst` | Dataset description, analytics, metric definitions, tables, and data/view-model shaping | `memory`, `analytics`, `data-audit`, `create-table`, `batch-quality`, `create-context` |
| `devops` | RunPod, Docker, workstation, local LLM, Chutes, Hugging Face Hub, cache, deployment, and service health operations | `memory`, `ops-runpod`, `ops-docker`, `ops-workstation`, `ops-llm`, `ops-chutes`, `ops-huggingface` |
| `model-trainer` | Fine-tuning, classifiers, regressors, LoRA adapters, eval gates, benchmarks, exports, and model promotion receipts | `memory`, `create-gpt`, `create-classifier`, `classifier-lab`, `train-persona`, `gpt-lab` |
| `reporter` | Reports, summaries, run narratives, proof gaps, and evidence-backed prose | `memory`, `create-report`, `batch-report`, `corpus-report`, `create-text`, `clean-text` |
| `proof-reader` | Language, prompt, grammar, consistency, and readability review | `memory`, `review-prompt`, `review-readme`, `create-sentence-markup` |
| `coder` | Scoped implementation patches from accepted specs | `memory`, `create-code`, `code-runner`, language best-practices skills |
| `qa-tester` | Deterministic test execution, UI interaction manifests, QID/COTS checks, and regression evidence | `memory`, `test`, `test-interactions`, `test-lab`, `quality-audit`, `fixture-tricky` |
| `code-reviewer` | Code review, CI status review, implementation receipt gates, and code security scan review | `memory`, `review-code`, `skills-ci`, `eval-skills`, `security-scan` |
| `designer` | Product/interface design and source-grounded visual artifacts | `memory`, `create-design`, `create-mockup`, `create-figure`, `best-practices-d3` |
| `mathematics` | Exact arithmetic, algebra, symbolic math, and numeric verification | `memory`, `edge-verifier` |

Every persona must include `memory` in `primary_skills`. Functional personas
use memory for prior lessons and project recall. Domain personas additionally
use memory to preserve identity, opinions, voice, and accumulated experience.
The `memory` persona is the persistent operator for complex memory work; simple
one-shot recall remains a direct project-agent call to the `memory` skill.
Supporting skills may appear in multiple personas only when they do not create
a domain work product. Work-product skills should have one obvious owning
persona. Other personas must call the owner through
`$ask <persona> ... with <skill@version> on <artifact>`.

## Domain Persona Profiles

Named Sparta personas such as Brandon, Embry, Margaret, and Jennifer should not
explode the top-level router list by default. They live as memory-backed domain
profiles on the core persona that owns their work product unless a project later
proves that one of them needs its own always-on worker.

`cyber-analyst/persona.yaml` defines this current cyber-domain profile:

- `brandon`: SPARTA cybersecurity assessor and taxonomy teacher.

`assurance/persona.yaml` defines these current assurance-domain profiles:

- `embry`: formal verification and QRA review advisor.
- `margaret`: compliance and assurance reviewer.

`fact-checker/persona.yaml` defines this current source-review profile:

- `jennifer`: source fidelity and user-facing evidence reviewer.

`theorem-prover/persona.yaml` defines the current formal-methods profile:

- `rob-armstrong`: formal methods expert for Lean4 proof obligations, trust boundaries, lemma graphs, and proof-chain visualization.

When a task asks for one of these named personas, the subagent must first call
`memory` and record the recalled profile/memory artifacts. It must not simulate
personality from unstated prompt text or fabricated memories.

Cyber Analyst must also call `memory` for ordinary Sparta Explorer questions
about SPARTA, NIST, MITRE, ATT&CK, CWE, CAPEC, D3FEND, and generated QRA
artifacts. It should inspect `items`, `confidence`, and `should_scan`, prefer
targeted collections such as `sparta_qra`, `sparta_controls`, and
`sparta_url_knowledge`, then choose one response mode:

- `answer`: memory, generated-QRA metadata, supplied source spans, or helper
  receipts are sufficient for cybersecurity interpretation.
- `deflect`: the user asks for evidence sufficiency, compliance approval, QRA
  readiness, source truth, retrieval, extraction, formal proof, report prose,
  test evidence, or dataset metrics owned by another persona.
- `clarify`: framework, control id, mapping target, source document,
  generated-QRA mode, or memory recall is ambiguous, weak, conflicting, or
  returns `should_scan: true`.

Cyber Analyst has delegated access to `create-evidence-case` through Assurance.
Use this when Sparta Explorer cyber interpretation needs a structured CAE/QRA
artifact, crosswalk chains, cached evidence spans, or same-technique grounding:

```text
$ask assurance to build evidence case with create-evidence-case@v1 on <evidence-request>
```

Cyber Analyst may consume and explain the returned QRA, `evidence_case`,
`entity_context`, and `cae_tree` fields. Assurance remains the owner of the
evidence-case verdict, sufficiency judgment, promotion, and approval.

Promote a domain profile to its own top-level persona only when at least one of
these is true:

- The profile requires persistent independent session state outside its owning core persona.
- The profile owns distinct work-product skills not already owned by a core persona.
- The profile is routed directly more often than the core Fact Checker route.
- The profile needs separate review or approval authority.

Until then, Brandon's cybersecurity and SPARTA taxonomy role lives under Cyber
Analyst, Compliance and SPARTA assurance live under Assurance, and source
fidelity plus user-facing claim review remain under Fact Checker.

## Default Routes

Choose the persona by work product, not by incidental skill:

- Memory handles complex recall synthesis, workspace inventory reconciliation, memory write plans, collection routing, source and identity deduplication, graph-readiness manifests, Theory-of-Mind/persona linkage planning, and receipt-backed `/store` or `/upsert` work through the sanctioned memory API. For simple "have we seen this?" lookups, the project agent calls the `memory` skill directly instead of delegating. For location tasks, the project agent or Memory must recall known locations first, scan with `rg`/`find`/git/`test -e`/ops-workstation on miss or stale records, validate markers, `/upsert` validated observations, and mark stale references as `stale`, `moved`, or `missing` instead of silently deleting them.
- Fetcher retrieves.
- Extractor structures.
- Doc Extractor prepares source documents into validated section JSONL with raw/clean alignment and repair notes. Use it only when source-prep artifacts are the work product; use Extractor for ordinary PDF/table/control/entity extraction.
- Doc QRA converts prepared document artifacts into grounded summaries and QRA pairs through doc2qra. It owns recall aids and memory receipts, not source cleanup or final canon lore.
- Final canonical lore facts, Theory-of-Mind states, relationship states, graph upserts, retrieval units, and Qdrant materialization are not owned by Doc Extractor or Doc QRA. Route graph/source/identity readiness and ToM linkage planning to Memory; route final lore inference to a future lore-extraction flow when needed; keep final graph mutation project-agent/materializer controlled.
- Researcher gathers context/source notes.
- Fact Checker decides whether source evidence supports, contradicts, or fails to mention a claim.
- Cyber Analyst interprets cybersecurity meaning, generated-QRA context, threat/control mappings, NIST/MITRE/SPARTA context, and analyst next actions. It answers, deflects, or clarifies from memory-grounded evidence; it may request `create-evidence-case` through Assurance, but does not directly own QRAs or approve sufficiency.
- Assurance decides whether evidence satisfies a control, QRA, SPARTA/CMMC framework, or assurance requirement.
- Theorem Prover generates and compiles formal proof artifacts.
- Data Analyst describes datasets, computes analytics, and shapes data/view models.
- DevOps runs infrastructure, deployment, cloud GPU, Docker, workstation, cache, model-runtime, provider quota, Hugging Face Hub publication/maintenance, and service health operations.
  DevOps does not own LLM training datasets, fine-tuning jobs, eval loops, card factual training claims, or trained model promotion.
- Model Trainer owns training datasets, fine-tuning jobs, classifiers, regressors, LoRA adapters, eval loops, benchmarks, exports, shadow deployment, and trained model promotion receipts.
- Mathematics verifies exact arithmetic, algebra, and numeric claims.
- Designer designs UI/visual artifacts.
- Reporter writes final prose, evidence reports, run narratives, and proof-gap summaries.
- Proof Reader edits language without changing facts.
- Coder implements accepted specs.
- QA Tester runs deterministic tests and UI interactions.
- Code Reviewer gates code review and supplied implementation evidence.

- `$ask memory to plan durable memory updates with memory@v1 on <memory-task-artifact>`
- `$ask memory to reconcile workspace inventory with memory@v1 on <location-request>`
- `$ask memory to deduplicate source identities with memory@v1 on <source-catalog-artifact>`
- `$ask memory to prepare graph-readiness manifest with memory@v1 on <source-or-qra-artifacts>`
- `$ask fetcher to fetch cited source with fetcher@v1 on <url-request>`
- `$ask extractor to extract source document with extractor@v1 on <document>`
- `$ask doc-extractor to prepare source sections with extractor@v1 on <document-or-extractor-output>`
- `$ask doc-qra to create grounded QRA pairs with doc2qra@v1 on <source-prep-artifact>`
- `$ask researcher to gather source notes with dogpile@v1 on <research-request>`
- `$ask fact-checker to verify claim support with review-question@v1 on <claim-artifact>`
- `$ask fact-checker to answer as Jennifer with memory@v1 on <source-fidelity-question>`
- `$ask cyber-analyst to interpret SPARTA risk with best-practices-sparta@v1 on <cyber-question>`
- `$ask cyber-analyst to answer Sparta Explorer question with memory@v1 on <sparta-nist-mitre-question>`
- `$ask cyber-analyst to interpret generated QRA context with memory@v1 on <generated-qra-question>`
- `$ask cyber-analyst to answer as Brandon with memory@v1 on <sparta-question>`
- `$ask assurance to build evidence case with create-evidence-case@v1 on <cyber-analyst-evidence-request>`
- `$ask assurance to verify SPARTA QRA with sparta-review@v1 on <qra-artifact>`
- `$ask assurance to create evidence case with create-evidence-case@v1 on <evidence-request>`
- `$ask theorem-prover to prove requirement with lean4-prove@v1 on <proof-request>`
- `$ask theorem-prover to answer as Rob Armstrong with memory@v1 on <formal-methods-question>`
- `$ask data-analyst to describe dataset with analytics@v1 on <data-request>`
- `$ask devops to check workstation health with ops-workstation@v1 on <ops-request>`
- `$ask devops to manage RunPod deployment with ops-runpod@v1 on <deployment-request>`
- `$ask devops to publish promoted model with ops-huggingface@v1 on <promotion-receipt>`
- `$ask model-trainer to fine-tune task model with create-gpt@v1 on <training-request>`
- `$ask model-trainer to train classifier with create-classifier@v1 on <classifier-request>`
- `$ask reporter to create report with create-report@v1 on <run-artifact>`
- `$ask proof-reader to proofread prompt with review-prompt@v1 on <prompt-bundle>`
- `$ask coder to implement patch with create-code@v1 on <implementation-spec>`
- `$ask qa-tester to run UI interactions with test-interactions@v1 on <interaction-manifest>`
- `$ask code-reviewer to review patch with review-code@v1 on <patch-artifact>`
- `$ask designer to create inspector shell with create-design@v1 on <view-model>`
- `$ask mathematics to verify numeric formula with edge-verifier@v1 on <formula-request>`

## Contract

- `id` must be stable, lowercase, and match the containing directory name.
- `display_name` is what the UI may show as the persona title.
- `role`, `instructions`, `state_contract`, `turn_contract`, and
  `output_contract` are required for any worker shown in the Transport Room.
- Stateless one-shot workers still need a persona file.
- Every persona directory must include `persona.yaml` and `pyproject.toml`.
- Every persona must list `memory` in `primary_skills`.
- Persistent workers must describe their session-local state and reuse rules in
  `persona.yaml`.
- DAG evidence should expose `persona_source_uri`, `persona_hash`, and
  `persona_text` when a persona is attached.
- Personas that can request or receive bounded helper work should reference
  `skill_help_protocol@v1`.

## Skill Help Calls

Personas may request bounded help from another subagent only by emitting the
shared skills syntax:

```text
$ask <helper-agent> to <bounded-task> with <skill@version> on <artifact-or-target>
```

This is a nested skill invocation, not an informal side chat. The caller names
the helper, task, skill, and target artifact. The scillm/OpenCode layer is
responsible for resolving the skill, loading the referenced `SKILL.md`, running
the helper, waiting for a terminal event, validating required outputs, writing a
receipt, recording the child run in the DAG, and resuming the caller with the
validated result.

The handoff is pause/resume. The caller emits `help_request.json`, scillm runs
the helper, helper artifacts are written to disk, and the caller resumes with a
small typed `help_result` plus a `resume_packet`. Do not inject a large helper
transcript into the caller context. Current truth lives in active artifacts; old
turns live in the RunGraph audit log.

Persona contracts should use `help_policy` to declare limits and allowed helper
patterns. The default policy for all personas is:

- `request_form: "$ask <agent> to <task> with <skill@version> on <artifact-or-target>"`
- `max_help_calls_total: 3`
- `max_help_calls_per_helper: 2`
- `max_attempts_per_request: 2`
- `allow_recursive_help: false`
- `allow_alternate_helper: false`
- `require_target_artifact: true`
- `require_terminal_event: true`
- `require_receipt: true`

Callers must not pass raw helper prompt blobs when a skill exists. They should
pass the skill name so the runtime can load the authoritative `SKILL.md`.

Every successful helper resume must name:

- active artifact paths and SHA-256 digests
- superseded artifact paths that the caller must not use
- required `read_artifact` actions before continuation
- consumed artifact receipt entries in the caller's final output

Helpers receive a bounded context bundle, not the caller's full session history:

- structured change request or help request
- target artifact or input files
- referenced helper `SKILL.md`
- relevant project/design constraints
- caller objective
- expected outputs
- validation rules

Recursive helper autonomy is disabled. If a helper needs another helper, it
must return `status: blocked` with `needs_help`. scillm may then run the
additional helper as a sibling call and resume the original caller only after
validated artifacts and receipts exist.
